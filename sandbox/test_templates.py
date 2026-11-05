"""从效果原文提取最低限度的反面清单；模板不能证明规则已穷尽。"""

import re

TEMPLATES = {
    "positive": "实际处理结果", "same_name_only": "只剩被排除的同名卡",
    "count_exceeded": "超过使用次数", "condition_unmet": "条件不满足",
    "no_target": "没有合法对象", "insufficient_cost": "代价不足",
    "decline": "选择不发动", "flip_summon": "反转召唤",
    "flip_battle": "被攻击翻开", "flip_effect": "效果翻开", "no_chain": "处理不入连锁",
}
NUMBERED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def effect_texts(text):
    matches = list(re.finditer("[" + NUMBERED + "]\\s*[:：]", text))
    if not matches:
        return [(1, text, "")]
    header = text[:matches[0].start()]
    return [(NUMBERED.index(m.group()[0]) + 1,
             text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)], header)
            for i, m in enumerate(matches)]


def required(text):
    result = []
    for number, body, header in effect_texts(text):
        keys = ["positive"]
        if re.search(r"「[^」]+」以外|同名.*以外", body):
            keys.append("same_name_only")
        if re.search(r"(?:回合|决斗).*(?:次|其中|各能)", header + body):
            keys.append("count_exceeded")
        if re.search(r"才能|的场合|不能", body):
            keys.append("condition_unmet")
        if "为对象" in body:
            keys.append("no_target")
        if re.search(r"(?:丢弃|解放|支付|把[^。]*?(?:除外|送去墓地))[^。]*?才能发动", body):
            keys.append("insufficient_cost")
        if re.search(r"才能发动|可以发动", body):
            keys.append("decline")
        if "反转" in body:
            keys.extend(("flip_summon", "flip_battle", "flip_effect"))
        if re.search(r"不入连锁|不形成连锁", body):
            keys.append("no_chain")
        for key in dict.fromkeys(keys):
            result.append({"effect": number, "template": key, "label": TEMPLATES[key],
                           "basis": (header + body).strip()})
    return result


def apply_template(scene):
    """参数化模板只添加公开的布场/断言约束，不根据被测积木反推预期。"""
    key, params = scene["template"], scene.get("parameters", {})
    if key == "same_name_only":
        player, source = str(params.get("player", 0)), params.get("source", "deck")
        if source not in ("deck", "hand", "grave", "banished"):
            raise ValueError("parameters.source须为deck/hand/grave/banished。")
        scene["field"].setdefault(player, {})[source] = [params.get("excluded", "self")]
    if key in ("same_name_only", "count_exceeded", "condition_unmet", "no_target", "insufficient_cost"):
        assertion = params.get("availability", {})
        scene["expect"].append(dict(check="offered", player=assertion.get("player", 0),
            card=assertion.get("card", "self"), effect=assertion.get("effect", scene["effect"]),
            **{"as": assertion.get("as", "activate"), **({"from": assertion["from"]} if "from" in assertion else {})}, eq=False))
    if key == "decline" and not any(i.get("decline") for i in scene["intents"]):
        raise ValueError("选择不发动模板须在发动意图中填写decline=true。")
    if key.startswith("flip_"):
        method = {"flip_summon": "summon", "flip_battle": "battle", "flip_effect": "effect"}[key]
        if not any(i.get("do") == "flip" and i.get("method") == method for i in scene["intents"]):
            raise ValueError("%s模板需要对应method=%s的flip意图。" % (TEMPLATES[key], method))
    if key == "no_chain":
        if not scene["expect"]:
            raise ValueError("不入连锁模板还须填写实际处理结果，不能只断言没有连锁。")
        scene["expect"].append({"check": "event", "name": "chaining", "card": "self", "eq": 0})
    return scene
