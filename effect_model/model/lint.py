"""语义检查，返回 [(级别, 位置, 说明)]，级别是 error / warn。

先查结构（字段、词汇、引用都能对上），再查 research/重点易错规则.json 里能在模型上看出来的几条。
"""

from .normalize import ModelError, applies, effect_by_id, normalize
from .vocab import (BLOCKS, BUILTIN_REFS, LIMIT_PERS, LIMIT_SCOPES, LIMIT_UNITS, LINKS, RESTRICT_FORBID, RESTRICT_FROM,
                    RESTRICT_FORBID_ZH, RESTRICT_KINDS, RESTRICT_METHODS, RESTRICT_SPANS, RESTRICT_UNTIL, RESTRICT_WHO,
                    RESTRICT_WHOLE_TURN, TIMINGS, known_keys)

_LASTING = "「发动后继续留在场上」要和这张卡的「魔法·陷阱卡的发动」效果一起用"


def _walk(node, fn):
    if isinstance(node, dict):
        fn(node)
        for v in node.values():
            _walk(v, fn)
    elif isinstance(node, list):
        for v in node:
            _walk(v, fn)


def _steps(steps):
    """连同 branch / schedule_operation / apply 里嵌套的步骤一起展开。"""
    for s in steps or []:
        yield s
        for case in s.get("cases", []):
            yield from _steps(case.get("do"))
        if s.get("act") == "schedule_operation":
            yield from _steps(s.get("do"))
        for ap in applies(s):
            yield from _steps(ap.get("do"))


def _known(category, key, out, where, what):
    keys = known_keys(category)
    for k in key if isinstance(key, list) else [key]:
        if keys is not None and k not in keys:
            out.append(("error", where, "未知的%s %r" % (what, k)))


def lint(card):
    out = []
    try:
        card = normalize(card)
    except ModelError as ex:
        return [("error", "整张卡", str(ex))]
    limits = card["limits"]
    for key, lim in limits.items():
        if lim.get("scope") not in LIMIT_SCOPES:
            out.append(("error", "额度 " + key, "scope 应为 %s" % "/".join(LIMIT_SCOPES)))
        if lim["unit"] not in LIMIT_UNITS:
            out.append(("error", "额度 " + key, "unit 应为 %s" % "/".join(LIMIT_UNITS)))
        if not (lim["per"] in LIMIT_PERS or isinstance(lim["per"], dict)):
            out.append(("error", "额度 " + key, "per 应为 %s 或阶段" % "/".join(LIMIT_PERS)))
        if not isinstance(lim["n"], int) or isinstance(lim["n"], bool) or lim["n"] < 1:
            out.append(("error", "额度 " + key, "次数 n 应为 1 以上的整数"))
    kept = {}
    for eff in card["effects"]:
        for s in list(_steps(eff["cost"])) + list(_steps(eff["do"])):
            if s.get("as") and s.get("keep"):
                kept["%s.%s" % (eff["id"], s["as"])] = True
        for t in eff["target"]:
            if t.get("keep"):
                kept["%s.%s" % (eff["id"], t["as"])] = True
    has_materials = bool(card["summon"].get("materials") or card["summon"]["procedures"])
    for rule in card["rules"]:
        if rule["rule"] == "lasting" and not any(e["type"] == "activation" for e in card["effects"]):
            out.append(("error", "规则 " + rule["id"], _LASTING))
    for eff in card["effects"]:
        where = "效果%s(%s)" % (eff["label"] or "-", eff["id"])
        t = eff["type"]
        if eff["block"] not in BLOCKS:
            out.append(("error", where, "block 应为 monster / pendulum"))
        if t == "activation" and card["card"]["kind"] == "monster":
            out.append(("error", where, "怪兽卡没有「卡的发动」，请用 ignition / quick / trigger"))
        if t == "trigger" and not eff.get("on"):
            out.append(("error", where, "诱发效果必须写 on（什么时候诱发）"))
        if t == "continuous" and not applies(eff) and not eff.get("on"):
            out.append(("error", where, "永续效果要写 apply（持续适用什么），或者 on + do（每次……，……）"))
        for key in eff["limit"]:
            if key not in limits:
                out.append(("error", where, "引用了不存在的额度 %r" % key))
        for r in eff["restrict"]:
            if r.get("span") not in RESTRICT_SPANS:
                out.append(("error", where, "誓约 / 制约的 span 应为 %s" % "/".join(RESTRICT_SPANS)))
            if r["who"] not in RESTRICT_WHO:
                out.append(("error", where, "自肃的 who 应为 %s" % "/".join(RESTRICT_WHO)))
            bad = [f for f in r.get("forbid", []) if f not in RESTRICT_FORBID]
            if not r.get("forbid") or bad:
                out.append(("error", where, "自肃的 forbid 应从 %s 里选（写了 %r）" % ("/".join(RESTRICT_FORBID), bad or [])))
            if r["until"] not in RESTRICT_UNTIL:
                out.append(("error", where, "自肃的 until 应为 %s" % "/".join(RESTRICT_UNTIL)))
            forbid = set(r.get("forbid", []))
            if r["who"] == "self" and forbid - {"attack", "direct_attack"}:
                out.append(("error", where, "who: self（这张卡）只能限制攻击 / 直接攻击，其余限制的是玩家"))
            if r.get("from") and not forbid & {"special_summon", "summon"}:
                out.append(("error", where, "from（从哪里）只用于召唤和特殊召唤的限制"))
            if r.get("only") and not forbid & {"special_summon", "summon", "attack", "direct_attack", "activate", "material"}:
                out.append(("error", where, "only（只能是什么卡）只用于召唤、特殊召唤、攻击、发动效果、作为素材的限制"))
            if set(r.get("from") or []) - set(RESTRICT_FROM):
                out.append(("error", where, "自肃的 from 应从 %s 里选" % "/".join(RESTRICT_FROM)))
            for f, kinds in RESTRICT_KINDS.items():
                if f in forbid and r.get("kinds", kinds[0]) not in kinds:
                    out.append(("error", where, "「%s」的 kinds 应为 %s" % (f, "/".join(kinds))))
            if "material" in forbid and r.get("method") not in RESTRICT_METHODS:
                out.append(("error", where, "「不能作为素材」要写 method：%s" % "/".join(RESTRICT_METHODS)))
            if (r.get("except") or {}).get("card") and not forbid & {"attack", "direct_attack"}:
                out.append(("error", where, "except.card（这张卡 / 对象以外的怪兽）只用于攻击的限制"))
            later = forbid & set(RESTRICT_FORBID) - set(RESTRICT_WHOLE_TURN)     # 写错的 forbid 上面已经报过
            if r.get("span") == "whole_turn" and r["who"] != "self" and later:
                out.append(("error", where, "整回合（这张卡发动的回合）的「%s」还没有写法：引擎没有本回合做过没有的记录，"
                                            "请改用「这个效果的发动后」或「这个回合」" % "、".join(
                                                RESTRICT_FORBID_ZH[f] for f in sorted(later))))
        ons = [(eff.get("on"), eff.get("timing"))] + [(m.get("on"), m.get("timing"))
                                                     for m in (eff.get("modes") or {}).get("options", [])]
        for on, timing in ons:
            if not on:
                continue
            _known("event", on.get("event"), out, where, "事件")
            phase = on.get("event") in ("phase_window", "phase_start")
            if t in ("trigger", "quick", "activation", "flip") and not phase and timing not in TIMINGS:
                out.append(("error", where, "有事件的效果要写 timing：when「……时」或 if「……的场合」"))
        conds = list(eff["condition"])
        for s in _steps(eff["do"]):
            conds.extend(s.get("if") or [])
        for c in conds:
            _known("cond", c.get("cond"), out, where, "条件")
            if c.get("cond") == "named_card_used":
                try:
                    effect_by_id(card, c["effect"])
                except ModelError as ex:
                    out.append(("error", where, str(ex)))
            if c.get("cond") == "raw":
                out.append(("warn", where, "条件使用了自定义 Lua，生成器无法检查它"))
        for ap in applies(eff):
            if "cont" in ap:
                _known("cont", ap["cont"], out, where, "持续内容")
        # 绑定与引用
        bound = {t["as"] for t in eff["target"]} | {d["as"] for d in eff["declare"]}
        for k, step in enumerate(list(_steps(eff["cost"])) + list(_steps(eff["do"]))):
            act = step.get("act")
            _known("act", act, out, where, "动作")
            if step.get("link") and step["link"] not in LINKS:
                out.append(("error", where, "第 %d 步：未知的连接 %r" % (k + 1, step["link"])))
            if step.get("optional") and step.get("link") != "then":
                out.append(("error", where, "第 %d 步：「可以选择不做」只用于「那之后，可以……」（link 要是 then）" % (k + 1)))
            for ap in applies(step):
                if "cont" in ap:
                    _known("cont", ap["cont"], out, where, "持续内容")
            if act == "raw":
                if not (step.get("lua") and step.get("zh")):
                    out.append(("error", where, "第 %d 步：raw 必须同时写 lua 和 zh" % (k + 1)))
                out.append(("warn", where, "第 %d 步使用了自定义 Lua，生成器无法检查它" % (k + 1)))
            for name in (step.get("as"), step.get("each_as")):
                if name:
                    bound.add(name)
        refs = []
        _walk({k: v for k, v in eff.items() if k not in ("id", "label")},
              lambda n: refs.append(n["ref"]) if isinstance(n.get("ref"), str) else None)
        for r in refs:
            if r in BUILTIN_REFS or r in bound or r in kept:
                if r == "materials" and not has_materials:
                    out.append(("error", where, "引用了 materials，但这张卡没有素材"))
                continue
            out.append(("error", where, "引用了未定义的 %r" % r))
    for rule in card["rules"]:
        for c in rule["condition"]:
            _known("cond", c.get("cond"), out, "规则 " + rule["id"], "条件")
    return out
