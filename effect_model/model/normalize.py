"""读取、补默认值。zh.py 和 lua.py 都从 normalize() 的结果出发。"""

import copy
import json

from .upgrade import upgrade
from .vocab import CIRCLED, EFFECT_TYPES, SCHEMA, SCHEMA_V01


class ModelError(ValueError):
    pass


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _default_range(card, eff):
    if eff["block"] == "pendulum":
        return ["pzone"]
    t = eff["type"]
    if card["card"]["kind"] != "monster":
        return ["szone"] if t in ("continuous", "trigger", "ignition", "quick") else []
    if t == "procedure":
        return ["hand"]
    if t in ("ignition", "quick", "continuous"):
        return ["mzone"]
    if t == "trigger":
        return [] if is_ref((eff.get("on") or {}).get("subject"), "self") else ["mzone"]
    return []


def _walk(node):
    """所有嵌套的 dict（处理步骤、代价、预约里的处理……）。"""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def diy_tokens(card):
    """没写卡号的衍生物（DIY 卡的衍生物没有现成卡号）：按出现顺序编号 1、2……，导出时卡号＝这张卡的卡号＋编号
    （卡号段默认每张卡隔 100，导出时还会重排，所以不存死卡号）。返回 [(编号, token 节点)]。"""
    out = []
    for node in _walk(card.get("effects", [])):
        if node.get("act") == "create_token" and "code" not in (node.get("token") or {}):
            out.append((len(out) + 1, node["token"]))
    return out


def is_numbered(eff):
    """卡面上编号①②的效果。只有代价、没有处理的卡的发动（「支付1000基本分才能把这张卡发动。」）不编号。"""
    return not (eff["type"] == "activation" and not eff["do"] and not eff.get("modes"))


def normalize(card):
    """补默认值：效果编号、发动位置、选卡器的 count 等。v0.1 的数据先升级。返回新的对象，不改动传入的数据。"""
    schema = card.get("schema")
    if schema == SCHEMA_V01:
        card = upgrade(card)
    elif schema != SCHEMA:
        raise ModelError("schema 应为 %r，实际为 %r" % (SCHEMA, schema))
    card = copy.deepcopy(card)
    info = card["card"]
    info.setdefault("subtypes", [])
    info.setdefault("rule_names", [])
    summon = card.setdefault("summon", {})
    for key in ("cannot", "procedures", "restrictions", "material_permissions"):
        summon.setdefault(key, [])
    card.setdefault("rules", [])
    card.setdefault("counters", {})
    # 放置 / 取除了指示物却没声明的（工作台只在「放置」那一步写上限）：补上声明，「最多N个」取那一步的 max
    for node in _walk(card.get("effects", [])):
        if node.get("act") in ("add_counter", "remove_counter") and node.get("counter"):
            spec = card["counters"].setdefault(node["counter"], {})
            if node.get("max") and "max" not in spec:
                spec["max"] = node["max"]
    for n, token in diy_tokens(card):
        token["code_offset"] = n
    card.setdefault("limits", {})
    for lim in card["limits"].values():
        lim.setdefault("per", "turn")
        lim.setdefault("n", 1)
        lim.setdefault("unit", "use")
    # 变量与函数的序号：规则在前，效果在后（与 v0.1 的卡面顺序一致）
    for i, rule in enumerate(card["rules"]):
        rule.setdefault("id", "r%d" % (i + 1))
        rule["index"] = i + 1
        rule.setdefault("condition", [])
    numbers = {}
    seen = {r["id"] for r in card["rules"]}
    for i, eff in enumerate(card["effects"]):
        if eff.get("type") not in EFFECT_TYPES:
            raise ModelError("第 %d 个效果的 type 未知：%r" % (i + 1, eff.get("type")))
        eff.setdefault("id", "e%d" % (i + 1))
        if eff["id"] in seen:
            raise ModelError("效果 id %r 重复" % eff["id"])
        seen.add(eff["id"])
        eff.setdefault("block", "monster")
        eff["index"] = len(card["rules"]) + i + 1
        for key in ("condition", "cost", "target", "declare", "restrict", "do"):
            eff.setdefault(key, [])
        lim = eff.get("limit") or []
        eff["limit"] = [lim] if isinstance(lim, str) else list(lim)
        if eff["type"] in ("trigger", "quick", "flip"):
            eff.setdefault("optional", True)
        if is_numbered(eff):
            n = numbers.get(eff["block"], 0)
            eff["label"] = CIRCLED[n]
            numbers[eff["block"]] = n + 1
        else:
            eff["label"] = ""
        if "range" not in eff:
            eff["range"] = _default_range(card, eff)
        for t in eff["target"]:
            t["sel"].setdefault("count", 1)
            t["sel"].setdefault("filter", [])
        for r in eff["restrict"]:
            r.setdefault("who", "you")
            r.setdefault("until", "end_of_turn")
    return card


def effect_by_id(card, eid):
    for eff in card["effects"]:
        if eff["id"] == eid:
            return eff
    raise ModelError("找不到 id 为 %r 的效果" % eid)


def item_by_id(card, eid):
    """规范化后的效果或规则文字。v0.1 的 rule 效果升级后在 card["rules"] 里，按下标找会错位，要按 id 找。"""
    for item in card["effects"] + card["rules"]:
        if item["id"] == eid:
            return item
    raise ModelError("找不到 id 为 %r 的效果或规则" % eid)


def is_ref(sel, name=None):
    return isinstance(sel, dict) and "ref" in sel and (name is None or sel["ref"] == name)


def applies(node):
    """持续适用的内容：apply 可以是一项，也可以是列表。"""
    ap = node.get("apply")
    if not ap:
        return []
    return ap if isinstance(ap, list) else [ap]


def limits_of(card, eff, **match):
    """这个效果引用的额度里，字段都符合 match 的那些：[(id, 额度)]。"""
    out = []
    for key in eff["limit"]:
        lim = card["limits"][key]
        if all(lim.get(k) == v for k, v in match.items()):
            out.append((key, lim))
    return out
