"""从官方中文效果文本解析出 Effect Model v0.2：zh.py 的逆过程，用于全卡库回归（devtools/regress_corpus.py）。

只认 zh.py 写得出来的句式。解析结果再交给 zh.py 渲染，和原文一致才算成功——解析器猜错了也不会混进覆盖率。
区域、卡种、阶段这类小的封闭集合不手抄措辞，而是把 zh.py 对所有取值的输出倒过来查（analysis by synthesis），
两边永远一致。解析不了的片段抛 ParseError，带上种类（发动部分 / 处理 / 永续……）和那一段原文，回归报告按句式归类。
"""

import functools
import itertools
import os
import re

from . import names, zh
from .model import SCHEMA, normalize


class ParseError(Exception):
    def __init__(self, part, fragment):
        super().__init__("%s：%s" % (part, fragment))
        self.part = part              # 发动部分 / 条件 / 代价 / 对象 / 处理 / 永续 / 结构
        self.fragment = fragment


# ---------------------------------------------------------------- 封闭集合：倒查 zh.py 的输出

ZONE_KEYS = ["hand", "mzone", "szone", "field", "pzone", "fzone", "grave", "deck", "banished", "extra"]


@functools.lru_cache(maxsize=None)
def zone_table():
    """zone_phrase 的全部输出 → [(who, where)]（同一段文字可能有几种写法，按偏好排序）。"""
    out = {}
    common = ["hand", "field", "grave", "deck", "banished", "extra", "mzone", "szone"]
    combos = [[z] for z in ZONE_KEYS]
    combos += [list(p) for p in itertools.permutations(common, 2)]
    combos += [list(p) for p in itertools.permutations(common[:6], 3)]
    for who in ("you", "opp", "both"):
        for where in combos:
            if "mzone" in where and "field" in where:
                continue
            text = zh.zone_phrase(who, where)
            out.setdefault(text, []).append((who, where))
    return out


def _kinds_table():
    return {v: list(k) for k, v in zh.ACTIVATION_KINDS.items()}


KIND_SUFFIX = [("魔法·陷阱卡", "spell_trap"), ("魔法卡", "spell"), ("陷阱卡", "trap"), ("怪兽", "monster"), ("卡", "card")]
POSITION_INV = sorted(((v, k) for k, v in zh.POSITION.items()), key=lambda x: -len(x[0]))
SUBTYPE_INV = {v: k for k, v in zh.SUBTYPE.items()}
RACE_INV = {v + "族": k for k, v in zh.RACE.items()}
ATTR_INV = {v + "属性": k for k, v in zh.ATTRIBUTE.items()}
STAT_INV = {v: k for k, v in zh.STAT.items()}
PHASE_INV = {v: k for k, v in zh.PHASE_NAME.items()}
METHOD_INV = {v: k for k, v in zh.METHOD_WORD.items()}
SUMMON_INV = {v: k for k, v in zh.SUMMON_WORD.items()}
CMP_INV = {"以下": "<=", "以上": ">="}


@functools.lru_cache(maxsize=None)
def setcodes():
    """字段名 → 编号（MDPro3 的 strings.conf）；查不到的字段编号写 0x0，只影响 Lua 不影响文字。"""
    out = {}
    try:
        from ygopack import mdpro3
        root = os.path.dirname(os.path.dirname(mdpro3.app_dir()))
    except Exception:
        root = None
    for path in (r"D:\Game\MDPro3\Data\locales\zh-CN\strings.conf",):
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("!setname "):
                        parts = line[9:].rstrip("\n").split(" ", 1)
                        if len(parts) == 2:
                            out.setdefault(parts[1].split("\t")[0].strip(), parts[0])
        except OSError:
            pass
    return out


# ---------------------------------------------------------------- 名词短语

def parse_noun(text, card=None):
    """「攻击力1500以下的灵摆怪兽」→ (过滤条件, 卡种)。卡种：monster / spell / trap / spell_trap / card / named。
    只认 zh.noun_parts 的语序：表示形式 → 数值 → 种族·属性 →（的）字段 → 同名 → 子类 → 卡种。"""
    if re.fullmatch(r"(「[^「」]+」)+", text):
        filters = []
        for name in re.findall(r"「([^「」]+)」", text):
            code = names.code_of(name, card)
            if code is None:
                raise ParseError("卡名", name)
            filters.append({"name": code})
        return filters, "named"
    kind = None
    for suffix, k in KIND_SUFFIX:
        if text.endswith(suffix):
            kind, text = k, text[:-len(suffix)]
            break
    if kind is None:
        raise ParseError("名词", text)
    filters = []
    rest = text
    for word, key in POSITION_INV:          # 表示形式写在 sel 上，这里先当过滤条件，选择器里再挪
        if rest.startswith(word):
            filters.append({"position": key})
            rest = rest[len(word):]
            break
    while True:
        m = re.match(r"(攻击力|守备力)(\d+)(以下|以上)?的", rest)
        if m:
            op = CMP_INV.get(m.group(3), "==")
            filters.append({STAT_INV[m.group(1)]: [op, int(m.group(2))]})
            rest = rest[m.end():]
            continue
        m = re.match(r"(\d+)星(以下的|以上的)?", rest)
        if m:
            op = CMP_INV.get((m.group(2) or "")[:2], "==")
            filters.append({"level": [op, int(m.group(1))]})
            rest = rest[m.end():]
            continue
        break
    m = re.match(r"((?:[^·「」]+?(?:族|属性))(?:·[^·「」]+?(?:族|属性))*)", rest)
    if m and all(p in RACE_INV or p in ATTR_INV for p in m.group(1).split("·")):
        for p in m.group(1).split("·"):
            filters.append({"race": RACE_INV[p]} if p in RACE_INV else {"attribute": ATTR_INV[p]})
        rest = rest[m.end():]
        if rest.startswith("的「"):
            rest = rest[1:]
    while rest.startswith("「"):
        m = re.match(r"「([^「」]+)」", rest)
        filters.append({"set": m.group(1), "setcode": setcodes().get(m.group(1), "0x0")})
        rest = rest[m.end():]
    same = False
    if rest.startswith("同名"):
        same, rest = True, rest[2:]
    while rest:
        for word, key in sorted(SUBTYPE_INV.items(), key=lambda x: -len(x[0])):
            if rest.startswith(word):
                filters.append({"subtype": key})
                rest = rest[len(word):]
                break
        else:
            raise ParseError("名词", text + {"monster": "怪兽", "card": "卡"}.get(kind, ""))
    if same:
        filters.append({"_same": True})
    return filters, kind


def parse_pre(text, card=None):
    """数量前面的修饰：「「X」以外的」→ 过滤条件。"""
    out = []
    for name in re.findall(r"「([^「」]+)」以外的", text):
        code = names.code_of(name, card)
        if code is None:
            raise ParseError("卡名", name)
        out.append({"not": {"name": code}})
    if re.sub(r"「[^「」]+」以外的", "", text):
        raise ParseError("名词", text)
    return out


def build_sel(who, where_opts, filters, kind, count=None):
    """把名词短语的结果放进选择器：卡种落到 card_type 或区域上，表示形式挪到 sel.position。"""
    sel = {"who": who}
    filters = list(filters)
    pos = [f for f in filters if "position" in f]
    filters = [f for f in filters if "position" not in f]
    same = any(f.get("_same") for f in filters)
    filters = [f for f in filters if "_same" not in f]
    where = where_opts[0]
    if kind == "monster":
        mz = next((w for w in where_opts if set(w) <= {"mzone"}), None)
        has_sub = any("subtype" in f for f in filters)
        if mz and not has_sub:
            where = mz
        elif not has_sub:
            filters.insert(0, {"card_type": "monster"})
    elif kind in ("spell", "trap"):
        filters.insert(0, {"card_type": kind})
    elif kind == "spell_trap":
        filters.insert(0, {"card_type": ["spell", "trap"]})
    if kind in ("card", "spell", "trap", "spell_trap"):
        where = next((w for w in where_opts if "mzone" not in w), where)
    sel["where"] = list(where)
    if pos:
        p = pos[0]["position"]
        if p == "faceup":
            sel["face"] = "up"
        elif p == "facedown":
            sel["face"] = "down"
        else:
            sel["position"] = p
    if filters:
        sel["filter"] = filters
    if same:
        sel["relation"] = {"same": ["name"]}
    if count is not None:
        sel["count"] = count
    return sel


def split_zone(text):
    """开头的区域短语：返回 (who, where 候选, 剩下的文字)，按最长匹配。"""
    for z in sorted(zone_table(), key=len, reverse=True):
        if text.startswith(z):
            opts = zone_table()[z]
            who = opts[0][0]
            return who, [w for w_, w in opts if w_ == who], text[len(z):]
    raise ParseError("区域", text)


# ---------------------------------------------------------------- 解析时的上下文

class PCtx:
    def __init__(self, card, eff):
        self.card = card              # {"card": {...}} 卡的基本信息（卡名、卡种）
        self.eff = eff                # 正在组装的效果
        self.targets = []             # [as]
        self.steps = []               # 已解析的处理（找「这个效果除外的卡」）
        self.n_as = 0

    def new_as(self, prefix):
        self.n_as += 1
        return "%s%d" % (prefix, self.n_as)

    def ref(self, text):
        """「这张卡」「那只怪兽」「作为对象的卡」「这个效果加入手卡的卡」→ 引用；不是引用返回 None。"""
        if text == "这张卡":
            return {"ref": "self"}
        if text in ("那只怪兽", "那张卡", "那些怪兽", "那些卡") or text.startswith("作为对象的"):
            if self.targets:
                return {"ref": self.targets[-1]}
            return None
        m = re.fullmatch(r"这个效果(除外|加入手卡|送去墓地|特殊召唤|破坏|解放)的(卡|怪兽)", text)
        if m:
            act = {v: k for k, v in zh.BOUND_VERB.items()}[m.group(1)]
            for step in reversed(self.steps):
                if step["act"] == act:
                    step.setdefault("as", self.new_as("b"))
                    return {"ref": step["as"]}
        return None


def parse_obj(text, pctx, allow_all=True):
    """动作的宾语：引用，或「对方场上的怪兽全部」「自己墓地1只怪兽」。"""
    r = pctx.ref(text)
    if r:
        return r
    if allow_all and text.endswith("全部"):
        who, opts, rest = split_zone(text[:-2])
        if not rest.startswith("的"):
            raise ParseError("宾语", text)
        filters, kind = parse_noun(rest[1:], pctx.card)
        return build_sel(who, opts, filters, kind, "all")
    who, opts, rest = split_zone(text)
    m = re.fullmatch(r"(.*?)(\d+)(只|张)(.+)", rest)
    if not m:
        raise ParseError("宾语", text)
    pre = parse_pre(m.group(1), pctx.card)
    filters, kind = parse_noun(m.group(4), pctx.card)
    if kind == "named":
        kind = "monster" if names.is_monster(filters[0]["name"], pctx.card) else "card"
        sel = build_sel(who, opts, [], kind, int(m.group(2)))
        sel.pop("filter", None)
        sel["filter"] = filters
        sel["filter"] = [f for f in sel["filter"] if "card_type" not in f]
        return sel
    sel = build_sel(who, opts, pre + filters, kind, int(m.group(2)))
    return sel


def parse_from_form(text, verb, pctx):
    """「从卡组把「X」以外的1只「Y」怪兽加入手卡」/「从卡组选1张卡除外」。"""
    m = re.fullmatch(r"从(.+?)(把|选)(.*?)(\d+)(只|张)(.+?)%s" % verb, text)
    if not m:
        return None
    zone = m.group(1)
    if zone not in zone_table():
        raise ParseError("区域", zone)
    opts = zone_table()[zone]
    who = opts[0][0]
    pre = parse_pre(m.group(3), pctx.card)
    filters, kind = parse_noun(m.group(6), pctx.card)
    if kind == "named":
        sel = {"who": who, "where": list(opts[0][1]), "filter": pre + filters, "count": int(m.group(4))}
        return sel
    return build_sel(who, [w for w_, w in opts if w_ == who], pre + filters, kind, int(m.group(4)))


# ---------------------------------------------------------------- 事件

def parse_event(seg, pctx):
    """事件短语（带「时 / 的场合」）→ (on, timing, 额外条件)；不是事件返回 None。"""
    for suffix, timing in (("的场合", "if"), ("时", "when")):
        if seg.endswith(suffix):
            core = seg[:-len(suffix)]
            r = _event_core(core, pctx)
            if r:
                return r[0], timing, r[1]
    m = re.fullmatch(r"(自己·对方的|自己|对方)?(%s)" % "|".join(PHASE_INV), seg)
    if m and m.group(2) != "主要阶段1":
        on = {"event": "phase_window", "phase": PHASE_INV[m.group(2)]}
        turn = {"自己": "you", "对方": "opp", "自己·对方的": "any"}.get(m.group(1) or "")
        if turn:
            on["turn"] = turn
        return on, None, []
    m = re.fullmatch(r"(自己·对方的|自己|对方)?(%s)结束时" % "|".join(PHASE_INV), seg)
    if m:
        on = {"event": "phase_end", "phase": PHASE_INV[m.group(2)]}
        turn = {"自己": "you", "对方": "opp", "自己·对方的": "any"}.get(m.group(1) or "")
        if turn:
            on["turn"] = turn
        return on, "when", []
    return None


def _event_core(core, pctx):
    words = "|".join(sorted(SUMMON_INV, key=len, reverse=True))
    m = re.fullmatch(r"这张卡((?:%s)(?:·(?:%s))*)" % (words, words), core)
    if m:
        events = [SUMMON_INV[w] for w in m.group(1).split("·")]
        return {"event": events[0] if len(events) == 1 else events, "subject": {"ref": "self"}}, []
    m = re.fullmatch(r"这张卡(%s)" % "|".join(METHOD_INV), core)
    if m:
        return {"event": "special_summon_success", "subject": {"ref": "self"}, "method": METHOD_INV[m.group(1)]}, []
    m = re.fullmatch(r"(对方|自己)?把怪兽((?:%s)(?:·(?:%s))*)" % (words, words), core)
    if m:
        events = [SUMMON_INV[w] for w in m.group(2).split("·")]
        on = {"event": events[0] if len(events) == 1 else events}
        if m.group(1):
            on["by"] = {"对方": "opp", "自己": "you"}[m.group(1)]
        return on, []
    if core == "这张卡被破坏送去墓地":
        return {"event": "sent_to_gy", "subject": {"ref": "self"}, "reason": ["destroyed"]}, []
    if core == "这张卡被送去墓地":
        return {"event": "sent_to_gy", "subject": {"ref": "self"}}, []
    m = re.fullmatch(r"这张卡(?:在(自己|对方)回合)?(?:从(.+?))?送去墓地", core)
    if m and (m.group(1) or m.group(2)):
        on = {"event": "sent_to_gy", "subject": {"ref": "self"}}
        if m.group(1):
            on["turn"] = {"自己": "you", "对方": "opp"}[m.group(1)]
        if m.group(2):
            inv = {v: k for k, v in zh.ZONE.items() if k not in ("mzone",)}
            parts = m.group(2).split("·")
            if not all(p in inv for p in parts):
                return None
            on["from"] = [inv[p] for p in parts]
        return on, []
    m = re.fullmatch(r"(对方怪兽|自己怪兽|自己或对方的怪兽)的攻击宣言", core)
    if m:
        return {"event": "attack_declared", "by": {"对方怪兽": "opp", "自己怪兽": "you", "自己或对方的怪兽": "any"}[m.group(1)]}, []
    if core == "这张卡被选择作为攻击对象":
        return {"event": "becomes_attack_target", "subject": {"ref": "self"}}, []
    if core == "这张卡没有超量素材的状态被选择作为攻击对象":
        return ({"event": "becomes_attack_target", "subject": {"ref": "self"}},
                [{"cond": "material_possession", "what": {"ref": "self"}, "cmp": ["==", 0]}])
    kinds = _kinds_table()
    kind_re = "|".join(sorted(kinds, key=len, reverse=True))
    m = re.fullmatch(r"和这张卡相同纵列有(%s)发动" % kind_re, core)
    if m:
        return {"event": "effect_activated", "what": "card", "kinds": kinds[m.group(1)],
                "where": {"column_of": {"ref": "self"}}}, []
    m = re.fullmatch(r"(自己或者对方|对方|自己)把(%s)发动" % kind_re, core)
    if m and m.group(2) != "怪兽":
        return {"event": "effect_activated", "what": "card", "kinds": kinds[m.group(2)],
                "by": {"自己或者对方": "both", "对方": "opp", "自己": "you"}[m.group(1)]}, []
    m = re.fullmatch(r"(%s)发动" % kind_re, core)
    if m and m.group(1) != "怪兽" and "魔法·陷阱·怪兽" != m.group(1):
        return {"event": "effect_activated", "what": "card", "kinds": kinds[m.group(1)]}, []
    m = re.fullmatch(r"要让场上的卡破坏的(%s)的效果发动" % kind_re, core)
    if m:
        return {"event": "effect_activated", "kinds": kinds[m.group(1)], "includes": ["destroy_on_field"]}, []
    m = re.fullmatch(r"包含从墓地把怪兽特殊召唤效果的(%s)的效果(由对方)?发动" % kind_re, core)
    if m:
        on = {"event": "effect_activated", "kinds": kinds[m.group(1)], "includes": ["special_summon_from_gy"]}
        if m.group(2):
            on["by"] = "opp"
        return on, []
    m = re.fullmatch(r"包含以下其中任意种效果的(%s)的效果发动" % kind_re, core)
    if m:
        return {"event": "effect_activated", "kinds": kinds[m.group(1)], "includes": ["_bullets"]}, []
    m = re.fullmatch(r"(.+?)为对象的(%s)的效果(由对方)?发动" % kind_re, core)
    if m and "的" in m.group(1):
        zone, noun = m.group(1).split("的", 1) if not m.group(1).startswith("自己或对方的") else (None, None)
        if zone and zone in zone_table():
            opts = zone_table()[zone]
            filters, kind = parse_noun(noun, pctx.card)
            t = build_sel(opts[0][0], [w for w_, w in opts if w_ == opts[0][0]], filters, kind)
            on = {"event": "effect_activated", "kinds": kinds[m.group(2)], "targets": t}
            if m.group(3):
                on["by"] = "opp"
            return on, []
    m = re.fullmatch(r"(对方把)?(%s)的效果发动" % kind_re, core)
    if m:
        on = {"event": "effect_activated", "kinds": kinds[m.group(2)]}
        if m.group(1):
            on["by"] = "opp"
        return on, []
    m = re.fullmatch(r"(自己或对方|对方|自己)?把怪兽(特殊召唤)之际", core)
    return None


QUICK_EVENTS = ("effect_activated", "attack_declared", "summon_attempt")


# ---------------------------------------------------------------- 条件

def parse_cond(seg, pctx):
    if seg == "只有对方场上才有怪兽存在":
        return [{"cond": "card_count", "sel": {"who": "you", "where": ["mzone"]}, "cmp": ["==", 0]},
                {"cond": "card_count", "sel": {"who": "opp", "where": ["mzone"]}, "cmp": [">=", 1]}]
    if seg in ("自己回合", "对方回合"):
        return [{"cond": "own_turn" if seg == "自己回合" else "opponent_turn"}]
    if seg == "盖放的这张卡发动":
        return [{"cond": "self_location", "where": ["szone"], "activated_from": "set"}]
    for pattern, cmp in ((r"(.+?)没有(.+)存在", ["==", 0]), (r"(.+?)有(.+)存在", [">=", 1])):
        m = re.fullmatch(pattern, seg)
        if m:
            try:
                who, opts, rest = split_zone(m.group(1))
                if rest:
                    continue
                filters, kind = parse_noun(m.group(2), pctx.card)
            except ParseError:
                continue
            sel = build_sel(who, opts, filters, kind)
            return [{"cond": "card_count", "sel": sel, "cmp": cmp}]
    raise ParseError("条件", seg)


# ---------------------------------------------------------------- 代价

SELF_AT_INV = {"墓地的": ["grave"], "场上的": ["mzone"], "手卡的": ["hand"]}


def parse_cost(seg, pctx):
    """返回 (代价步骤, 由它推出的发动位置或 None)。"""
    if seg == "把这张卡从手卡丢弃":
        return {"act": "discard", "what": {"ref": "self"}}, ["hand"]
    if seg == "把这张卡从手卡送去墓地":
        return {"act": "send_to_gy", "what": {"ref": "self"}}, ["hand"]
    if seg == "把这张卡送去墓地":
        return {"act": "send_to_gy", "what": {"ref": "self"}}, None
    if seg == "把这张卡解放":
        return {"act": "release", "what": {"ref": "self"}}, None
    m = re.fullmatch(r"把(墓地的|场上的|手卡的)?这张卡除外", seg)
    if m:
        return {"act": "banish", "what": {"ref": "self"}}, SELF_AT_INV.get(m.group(1) or "")
    m = re.fullmatch(r"把这张卡(\d+)个超量素材取除", seg)
    if m:
        return {"act": "detach_xyz_material", "from": {"ref": "self"}, "count": int(m.group(1))}, None
    m = re.fullmatch(r"支付(\d+)基本分", seg)
    if m:
        return {"act": "pay_lp", "amount": int(m.group(1))}, None
    m = re.fullmatch(r"把这张卡(\d+)个魔力指示物取除", seg)
    if m:
        return {"act": "remove_counter", "from": {"ref": "self"}, "counter": "spell", "count": int(m.group(1))}, None
    for verb, act in (("送去墓地", "send_to_gy"), ("除外", "banish")):
        sel = parse_from_form(seg, verb, pctx) if seg.startswith("从") else None
        if sel:
            return {"act": act, "what": sel}, None
    for verb, act in (("送去墓地", "send_to_gy"), ("除外", "banish"), ("解放", "release")):
        m = re.fullmatch(r"把(.+)%s" % verb, seg)
        if m:
            inner = m.group(1)
            lm = re.fullmatch(r"这张卡所连接区(\d+)(只|张)(自己|对方)(.+)", inner)
            if lm:
                filters, kind = parse_noun(lm.group(4), pctx.card)
                sel = build_sel({"自己": "you", "对方": "opp"}[lm.group(3)], [["linked"]], filters, kind, int(lm.group(1)))
                sel["where"] = ["linked"]
                sel["filter"] = [f for f in sel.get("filter", []) if "card_type" not in f]
                if not sel["filter"]:
                    sel.pop("filter")
                return {"act": act, "what": sel}, None
            return {"act": act, "what": parse_obj(inner, pctx, allow_all=False)}, None
    raise ParseError("代价", seg)


# ---------------------------------------------------------------- 处理

def parse_step(text, pctx):
    if text == "那个发动无效":
        return {"act": "negate_activation", "what": {"ref": "chain"}}
    if text == "那个效果无效":
        return {"act": "negate_effect", "what": {"ref": "chain"}}
    if text == "那次攻击无效":
        return {"act": "negate_attack"}
    if text == "那次特殊召唤无效":
        return {"act": "negate_summon", "what": {"ref": "event"}}
    m = re.fullmatch(r"(自己|对方)从卡组抽(\d+)张", text)
    if m:
        return {"act": "draw", "player": {"自己": "you", "对方": "opp"}[m.group(1)], "count": int(m.group(2))}
    m = re.fullmatch(r"双方各自从卡组抽(\d+)张", text)
    if m:
        return {"act": "draw", "player": "both", "count": int(m.group(1))}
    m = re.fullmatch(r"给与对方(\d+)伤害", text)
    if m:
        return {"act": "damage", "player": "opp", "amount": int(m.group(1))}
    m = re.fullmatch(r"自己受到(\d+)的伤害", text)
    if m:
        return {"act": "damage", "player": "you", "amount": int(m.group(1))}
    if text == "这张卡回到手卡":
        return {"act": "add_to_hand", "what": {"ref": "self"}}
    m = re.fullmatch(r"(.+)的效果直到回合结束时无效", text)
    if m:
        return {"act": "negate_card_effects", "what": parse_obj(m.group(1), pctx), "until": "end_of_turn"}
    m = re.fullmatch(r"(.+?)的全部(.+)的效果无效化", text)
    if m:
        who, opts, rest = split_zone(m.group(1))
        if rest:
            raise ParseError("处理", text)
        filters, kind = parse_noun(m.group(2), pctx.card)
        return {"act": "negate_card_effects", "what": build_sel(who, opts, filters, kind, "all"), "until": "permanent"}
    m = re.fullmatch(r"(.+)的攻击力直到回合结束时(上升|下降)(\d+)", text)
    if m:
        v = int(m.group(3)) * (-1 if m.group(2) == "下降" else 1)
        return {"act": "apply_continuous", "until": "end_of_turn",
                "apply": {"cont": "atk_update", "affects": parse_obj(m.group(1), pctx), "value": v}}
    m = re.fullmatch(r"(.+)变成(表侧表示|里侧守备表示|表侧攻击表示|表侧守备表示)", text)
    if m:
        to = {"表侧表示": "faceup", "里侧守备表示": "facedown", "表侧攻击表示": "attack", "表侧守备表示": "defense"}[m.group(2)]
        return {"act": "change_position", "what": parse_obj(m.group(1), pctx), "to": to}
    for verb, act in (("加入手卡", "add_to_hand"), ("送去墓地", "send_to_gy"), ("除外", "banish"),
                      ("特殊召唤", "special_summon"), ("在自己场上盖放", "set_spell_trap")):
        if text.startswith("从"):
            sel = parse_from_form(text, verb, pctx)
            if sel:
                return {"act": act, "what": sel}
    m = re.fullmatch(r"选(.+?)(\d+)(只|张)(.+)破坏", text)
    if m:
        who, opts, rest = split_zone(m.group(1))
        if not rest:
            filters, kind = parse_noun(m.group(4), pctx.card)
            return {"act": "destroy", "what": build_sel(who, opts, filters, kind, int(m.group(2)))}
    m = re.fullmatch(r"(.+?)(在自己场上)?特殊召唤", text)
    if m:
        what = parse_obj(m.group(1), pctx)
        step = {"act": "special_summon", "what": what}
        if m.group(2):
            step["player"] = "you"
        return step
    for verb, act in (("破坏", "destroy"), ("除外", "banish"), ("加入手卡", "add_to_hand"), ("送去墓地", "send_to_gy"),
                      ("回到额外卡组", "return_to_extra")):
        if text.endswith(verb):
            return {"act": act, "what": parse_obj(text[:-len(verb)], pctx)}
    raise ParseError("处理", text)


def parse_steps(text, pctx):
    """处理部分（不含最后的「。」）→ 步骤列表。句号是 also，「那之后，」是 then，逗号是 and_if_you_do。"""
    steps = []
    sentences = text.split("。")
    for si, sent in enumerate(sentences):
        link = "also"
        if sent.startswith("那之后，"):
            link, sent = "then", sent[4:]
        clauses = sent.split("，")
        pending_if = None
        for ci, cl in enumerate(clauses):
            if ci:
                link = "and_if_you_do" if pending_if is None else link
            if cl.endswith("的场合") and ci + 1 < len(clauses):
                pending_if = parse_conds([cl[:-3]], pctx)
                continue
            if cl.endswith("并破坏") and cl[:-3] in ("那个发动无效", "那个效果无效"):
                first = parse_step(cl[:-3], pctx)
                _add(steps, first, link, pending_if, pctx)
                _add(steps, {"act": "destroy", "what": {"ref": "chain.card"}}, "and_if_you_do", None, pctx)
            else:
                _add(steps, parse_step(cl, pctx), link, pending_if, pctx)
            pending_if = None
    return steps


def _add(steps, step, link, cond, pctx):
    if steps:
        step["link"] = link
    if cond:
        step["if"] = cond
    steps.append(step)
    pctx.steps.append(step)


def parse_conds(segs, pctx):
    out = []
    for s in segs:
        out.extend(parse_cond(s, pctx))
    return out


# ---------------------------------------------------------------- 永续效果

def parse_continuous(body, pctx, kind):
    """「只要这张卡在怪兽区域存在，……」→ (apply, range)；body 不含最后的「。」。"""
    rng = None
    for prefix, r in (("只要这张卡在怪兽区域存在，", ["mzone"]), ("只要这张卡在魔法与陷阱区域存在，", ["szone"])):
        if body.startswith(prefix):
            body, rng = body[len(prefix):], r
    m = re.fullmatch(r"(自己|对方)怪兽不能攻击宣言", body)
    if m:
        return {"cont": "cannot_attack", "declare": True,
                "affects": {"who": {"自己": "you", "对方": "opp"}[m.group(1)], "where": ["mzone"]}}, rng
    m = re.fullmatch(r"(.+)的攻击力(上升|下降)(\d+)", body)
    if m:
        v = int(m.group(3)) * (-1 if m.group(2) == "下降" else 1)
        target = m.group(1)
        if target == "这张卡":
            return {"cont": "atk_update", "affects": {"ref": "self"}, "value": v}, rng
        who, opts, rest = split_zone(target)
        if rest.startswith("的"):
            filters, k = parse_noun(rest[1:], pctx.card)
            sel = build_sel(who, opts, filters, k)
            return {"cont": "atk_update", "affects": sel, "value": v}, rng
    m = re.fullmatch(r"(.+?)的(.+)的效果无效化", body)
    if m and m.group(1) in zone_table():
        opts = zone_table()[m.group(1)]
        filters, k = parse_noun(m.group(2), pctx.card)
        sel = build_sel(opts[0][0], [w for w_, w in opts if w_ == opts[0][0]], filters, k)
        return {"cont": "effects_disabled", "scope": "dynamic", "affects": sel}, rng
    m = re.fullmatch(r"(自己|对方)不能特殊召唤", body)
    if m:
        return {"cont": "cannot_special_summon", "player": {"自己": "you", "对方": "opp"}[m.group(1)]}, rng
    raise ParseError("永续", body)


# ---------------------------------------------------------------- 一个编号效果

HEAD_END = re.compile(r"^(.*?)(才能发动|发动)。")


def parse_effect(text, card, block="monster", bullets=()):
    """「①：」后面的一段（含最后的「。」）→ (效果, limits)。card 是 {"card": {...}}。"""
    info = card["card"]
    kind = info["kind"]
    eff = {"id": "e1"}
    limits = {}
    if block == "pendulum":
        eff["block"] = "pendulum"
    pctx = PCtx(card, eff)
    if not text.endswith("。"):
        raise ParseError("结构", text[-12:])
    if text.startswith("只要这张卡在") or text.startswith("每次"):
        ap, rng = parse_continuous(text[:-1], pctx, kind)
        eff.update(type="continuous", apply=ap)
        if rng:
            eff["range"] = rng
        return eff, limits
    head, body = None, text
    m = HEAD_END.match(text)
    if m and not m.group(1).startswith("作为这张卡的发动时的效果处理"):
        head, body = m.group(1), text[m.end():]
        optional = m.group(2) == "才能发动"
    if head is None or head == "":
        # 没有发动部分：魔陷的卡的发动，或者能直接读成永续
        if kind == "monster" and block == "monster":
            try:
                ap, rng = parse_continuous(text[:-1], pctx, kind)
                eff.update(type="continuous", apply=ap)
                return eff, limits
            except ParseError:
                pass
        eff["type"] = "activation"
        lasting = "作为这张卡的发动时的效果处理，"
        if body.startswith(lasting):
            body = body[len(lasting):]
        eff["do"] = parse_steps(body[:-1], pctx)
        return eff, limits
    segs = head.split("，")
    on, timing, extra_conds, conds, costs, targets = None, None, [], [], [], []
    marker = None
    pending = []
    for i, seg in enumerate(segs):
        m_n = re.fullmatch(r"1回合(?:1|最多(\d+))次", seg)
        if m_n and not (on or conds or costs or targets):
            limits["l1"] = {"scope": "card", "per": "turn", "n": int(m_n.group(1) or 1)}
            continue
        if seg == "只在这张卡表侧表示存在才有1次" and not (on or conds or costs or targets):
            limits["l2"] = {"scope": "face_up", "n": 1}
            continue
        if seg in ("自己主要阶段", "自己·对方回合") and i == len(segs) - 1 or seg == "自己·对方回合":
            marker = seg
            continue
        if on is None and not conds and not costs and not targets and not pending:
            ev = parse_event(seg, pctx)
            if ev:
                on, timing, extra_conds = ev
                continue
        if seg == "宣言1个卡名":
            eff["declare"] = [{"kind": "card_name", "as": "named"}]
            continue
        if seg.startswith("以") and seg.endswith("为对象"):
            sel = parse_obj(seg[1:-3], pctx, allow_all=False)
            if "ref" in sel:
                raise ParseError("对象", seg)
            name = pctx.new_as("t")
            targets.append({"as": name, "sel": sel})
            pctx.targets.append(name)
            continue
        if seg.endswith("的场合"):
            conds.extend(parse_conds(pending + [seg[:-3]], pctx))
            pending = []
            continue
        if seg.startswith("把") or seg.startswith("支付") or seg.startswith("从"):
            step, rng = parse_cost(seg, pctx)
            costs.append(step)
            if rng:
                eff["range"] = rng
            continue
        pending.append(seg)       # 多个条件用逗号隔开，最后一个才带「的场合」
    if pending:
        raise ParseError("发动部分", "，".join(pending))
    # 效果种类
    if on:
        eff["on"] = on
        if timing:
            eff["timing"] = timing
        quick = on["event"] in QUICK_EVENTS and timing == "when"
        if kind == "monster" or block == "pendulum" or eff.get("range") == ["grave"]:
            eff["type"] = "quick" if quick else "trigger"
        else:
            eff["type"] = "activation" if quick or not _lasting_card(info) else "trigger"
        if eff["type"] == "trigger":
            eff["optional"] = optional
    elif marker == "自己·对方回合":
        eff["type"] = "quick"
    elif kind == "monster" or block == "pendulum" or eff.get("range") == ["grave"] or _lasting_card(info):
        eff["type"] = "ignition"
    else:
        eff["type"] = "activation"
    if marker == "自己主要阶段" and eff["type"] != "ignition":
        raise ParseError("发动部分", head)
    if not optional and eff["type"] != "trigger":
        raise ParseError("发动部分", head + "发动")
    conds = extra_conds + conds
    if conds:
        eff["condition"] = conds
    if costs:
        eff["cost"] = costs
    if targets:
        eff["target"] = targets
    if limits:
        eff["limit"] = list(limits)
    if on and "_bullets" in on.get("includes", []):
        on["includes"] = _parse_include_bullets(bullets)
    eff["do"] = parse_steps(body[:-1], pctx)
    return eff, limits


def _lasting_card(info):
    return any(s in info.get("subtypes", []) for s in ("continuous", "field", "equip"))


def _parse_include_bullets(bullets):
    inv = {"●" + v: k for k, v in zh.INCLUDES.items()}
    out = []
    for b in bullets:
        if b not in inv:
            raise ParseError("发动部分", b)
        out.append(inv[b])
    return out


# ---------------------------------------------------------------- 验证：再渲染回去

def render_effect(eff, limits, card):
    """把解析结果放进一张只有这个效果的卡里，渲染「①：」后面的文字（含 ● 行）。"""
    model = {"schema": SCHEMA, "card": dict(card["card"]), "effects": [eff], "limits": limits}
    full = normalize(model)
    e = full["effects"][0]
    ctx = zh.Ctx(full, e)
    text = zh.effect_text(e, ctx)
    return text, ctx.bullets
