"""卡片上的意图情景、最低覆盖清单和过期判断；不依赖界面或网络。"""

import copy
import hashlib
import json

from .test_templates import TEMPLATES, apply_template, required

MAX_SCENARIOS = 60
MAX_INTENTS = 30
CHECKS = {"count", "lp", "atk", "def", "level", "disabled", "faceup", "overlay", "event", "drawn", "offered"}
COMMANDS = {"activate", "summon", "spsummon", "mset", "sset", "reposition", "attack", "battle", "main2", "end_turn", "flip"}
ZONES = {"deck", "hand", "grave", "banished", "extra", "mzone", "szone"}
OFFERED = {"activate", "summon", "spsummon", "reposition", "mset", "sset", "attack", "chain", "battle_phase"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def intent_text(document):
    """测试依据的原文：有设计稿用设计稿，否则用卡面效果文字。"""
    return (document.get("diy") or {}).get("design_text") or (document.get("data") or {}).get("effect_text", "")


def revision(document):
    fields = ("name", "effect_text", "lb_text", "cardpass", "card_type", "call_way", "extra1", "extra2",
              "level", "rank", "ATK", "DEF", "attribute", "race", "mt_type")
    diy = document.get("diy") or {}
    value = {"card_uid": document.get("_card_uid"), "data": {k: document.get("data", {}).get(k) for k in fields},
             "blocks": diy.get("blocks"), "setcodes": diy.get("setcodes", [])}
    for key in ("design_text", "script"):
        if diy.get(key):
            value[key] = diy[key]
    return digest(value)


def suite(document):
    return copy.deepcopy((document.get("diy") or {}).get("tests") or {"version": 1, "scenarios": [], "results": []})


def _reference(value, names, path):
    if isinstance(value, dict) and set(value) - {"ref", "player", "in", "repeat", "pos", "seq"}:
        raise ValueError(path + "：引用包含未知字段。")
    value = value.get("ref") if isinstance(value, dict) else value
    if not ((isinstance(value, str) and value in names) or (type(value) is int and 0 < value < 0x100000000)):
        raise ValueError(path + "：须为self、虚拟卡引用或原文明确引用的卡片密码。")


def _definitions(definitions):
    if not isinstance(definitions, dict) or len(definitions) > 16 or {"self", "__filler__"}.intersection(definitions):
        raise ValueError("virtual_cards最多16张，不得声明self或__filler__。")
    from .fixtures import card_record, helper_effects
    for key, definition in definitions.items():
        if not isinstance(key, str) or not isinstance(definition, dict) or set(definition) - {
                "name", "kind", "subtype", "attribute", "race", "level", "atk", "def", "setcodes", "helper", "source"}:
            raise ValueError("virtual_cards只接受属性描述与固定辅助设施，不能提供脚本。")
        try:
            card_record(1, definition)
            helper_effects(definition)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("virtual_cards.%s：%s" % (key, error)) from None
    return set(definitions) | {"self"}


def _field(field, names):
    if not isinstance(field, dict) or set(field) - {"0", "1"}:
        raise ValueError("field须以字符串0、1为双方编号。")
    for player, zones in field.items():
        if not isinstance(zones, dict) or set(zones) - ZONES:
            raise ValueError("field.%s包含未知区域。" % player)
        for zone, cards in zones.items():
            if not isinstance(cards, list) or len(cards) > 40:
                raise ValueError("field.%s.%s须为最多40张的数组。" % (player, zone))
            occupied = 0
            for item in cards:
                _reference(item, names, "field." + zone)
                if isinstance(item, dict):
                    if set(item) - {"ref", "repeat", "pos", "seq"} or type(item.get("repeat", 1)) is not int or not 1 <= item.get("repeat", 1) <= 40:
                        raise ValueError("布场卡片只支持ref/repeat/pos/seq。")
                    if item.get("pos", "attack") not in ("attack", "defense", "set"):
                        raise ValueError("pos须为attack/defense/set。")
                    if "seq" in item and (type(item["seq"]) is not int or not 0 <= item["seq"] < 5 or item["seq"] + item.get("repeat", 1) > 5):
                        raise ValueError("seq及repeat超出场上格子范围。")
                occupied += item.get("repeat", 1) if isinstance(item, dict) else 1
            if occupied > (5 if zone in ("mzone", "szone") else 40):
                raise ValueError("field.%s.%s卡片过多。" % (player, zone))


def _intents(intents, names):
    if not isinstance(intents, list) or len(intents) > MAX_INTENTS:
        raise ValueError("intents须为最多30个意图的数组。")
    for index, intent in enumerate(intents):
        if not isinstance(intent, dict) or intent.get("do") not in COMMANDS or set(intent) - {
                "do", "card", "player", "from", "effect", "choose", "decline", "method", "by", "target", "option"}:
            raise ValueError("intents[%d]：只写发动/召唤/翻开等意图，不写select/yes/no底层动作。" % index)
        if intent.get("player", 0) not in (0, 1):
            raise ValueError("intent.player须为0或1。")
        if intent["do"] not in {"battle", "main2", "end_turn"} and "card" not in intent:
            raise ValueError("intents[%d].card缺失。" % index)
        if intent["do"] == "flip" and (intent.get("method") not in {"summon", "battle", "effect"} or
                (intent["method"] != "summon" and "by" not in intent)):
            raise ValueError("flip须填method，battle/effect还须填by。")
        if "effect" in intent and (type(intent["effect"]) is not int or not 1 <= intent["effect"] <= 20):
            raise ValueError("intent.effect须为1～20的编号。")
        for key in ("card", "target", "by"):
            if key in intent:
                _reference(intent[key], names, "intents[%d].%s" % (index, key))
        if not isinstance(intent.get("choose", []), list) or len(intent.get("choose", [])) > 30:
            raise ValueError("choose须为引用数组。")
        for card in intent.get("choose", []):
            _reference(card, names, "choose")


def _expectations(expectations, names):
    if not isinstance(expectations, list) or len(expectations) > 30:
        raise ValueError("expect须为最多30个预期的数组。")
    for index, check in enumerate(expectations):
        if not isinstance(check, dict) or check.get("check") not in CHECKS or len({"eq", "ge", "le"}.intersection(check)) != 1:
            raise ValueError("expect[%d]须为已开放检查并且只填eq/ge/le中的一项。" % index)
        if set(check) - {"check", "player", "card", "in", "eq", "ge", "le", "as", "name", "effect", "from"}:
            raise ValueError("expect[%d]含未知字段。" % index)
        if check["check"] in {"count", "atk", "def", "level", "faceup", "disabled", "overlay"} and (
                (check["check"] == "count" and check.get("in") not in ZONES) or (check["check"] != "count" and "card" not in check)):
            raise ValueError("count须填区域in；数值及卡片状态检查须填card。")
        if check.get("in") is not None and check["in"] not in ZONES:
            raise ValueError("expect.in包含未知区域。")
        if "card" in check:
            _reference(check["card"], names, "expect.card")
        if check.get("check") == "offered" and check.get("as") not in OFFERED:
            raise ValueError("offered.as取值无效。")
        if check.get("check") == "event":
            from .messages import NAMES
            if check.get("name") not in NAMES.values():
                raise ValueError("event.name不是引擎消息名，不能把未知事件计成0来证明通过。")


def _parameters(result, field):
    if not isinstance(result.setdefault("parameters", {}), dict):
        raise ValueError("parameters须为对象。")
    params = result["parameters"]
    if set(params) - {"availability", "player", "source", "excluded", "limit"}:
        raise ValueError("parameters包含未知模板参数。")
    if type(params.get("limit", 1)) is not int or not 1 <= params.get("limit", 1) <= 20:
        raise ValueError("parameters.limit须为1～20。")
    availability = params.get("availability", {})
    if not isinstance(availability, dict) or set(availability) - {"card", "player", "as", "effect", "from"}:
        raise ValueError("parameters.availability只收card/player/as/effect/from。")
    if availability.get("as", "activate") not in OFFERED - {"battle_phase"}:
        raise ValueError("parameters.availability.as须为activate/chain等已开放操作。")
    if "effect" in availability and (type(availability["effect"]) is not int or not 1 <= availability["effect"] <= 20):
        raise ValueError("parameters.availability.effect须为1～20。")
    if result["template"] in {"same_name_only", "count_exceeded", "condition_unmet", "no_target", "insufficient_cost"}:
        actor = availability.get("card", "self")
        zones = field.get(str(availability.get("player", 0)), {})
        eligible = [availability["from"]] if "from" in availability else [z for z in zones if z not in ("deck", "extra")]
        present = any((c.get("ref") if isinstance(c, dict) else c) == actor for z in eligible for c in zones.get(z, []))
        if not present:
            raise ValueError("不能把发动者漏放或只放进卡组后证明不能发动；请在availability.from对应区域布置发动者。")


def validate(value, text):
    if not isinstance(value, dict):
        raise ValueError("scenario须为对象。")
    allowed = {"id", "name", "effect", "basis", "template", "parameters", "virtual_cards", "field", "intents", "expect"}
    if set(value) - allowed:
        raise ValueError("scenario包含未开放字段：" + ",".join(sorted(set(value) - allowed)))
    result = copy.deepcopy(value)
    for key, limit in (("id", 80), ("name", 160), ("basis", 2000)):
        if not isinstance(result.get(key), str) or not 0 < len(result[key]) <= limit:
            raise ValueError("scenario.%s为空或过长。" % key)
    if result["basis"] not in text:
        raise ValueError("scenario.basis须为当前效果原文中的连续片段。")
    if type(result.get("effect")) is not int or not 1 <= result["effect"] <= 20:
        raise ValueError("scenario.effect须为1～20的编号。")
    if result.get("template") not in TEMPLATES:
        raise ValueError("scenario.template须为：" + "/".join(TEMPLATES))
    names = _definitions(result.setdefault("virtual_cards", {}))
    field = result.get("field")
    _field(field, names)
    _intents(result.get("intents"), names)
    expectations = result.get("expect")
    _expectations(expectations, names)
    _parameters(result, field)
    apply_template(copy.deepcopy(result))
    if not expectations and result["template"] not in {"same_name_only", "count_exceeded", "condition_unmet", "no_target", "insufficient_cost"}:
        raise ValueError("情景须有实际结果断言。")
    return result


def coverage(document, tests=None):
    tests = tests if tests is not None else suite(document)
    current = revision(document)
    results = {r["scenario_id"]: r for r in tests.get("results", [])}
    def state(scene):
        result = results.get(scene["id"], {})
        if result and (result.get("revision") != current or result.get("scenario_revision") != digest(scene)):
            return "过期"
        return result.get("status", "未验证")
    rows = []
    for need in required(intent_text(document)):
        scenes = [s for s in tests["scenarios"] if s["effect"] == need["effect"] and s["template"] == need["template"]]
        states = [state(scene) for scene in scenes]
        status = ("失败" if "失败" in states else "过期" if "过期" in states else
                  "通过" if states and all(s == "通过" for s in states) else "未验证")
        rows.append(dict(need, status=status))
    outstanding = [{"id": s["id"], "name": s["name"], "basis": s["basis"], "status": state(s)}
                   for s in tests["scenarios"] if state(s) != "通过"]
    return {"requirements": rows, "passed": sum(r["status"] == "通过" for r in rows),
            "total": len(rows), "unverified_scenarios": outstanding,
            "verified": bool(rows) and not outstanding and all(r["status"] == "通过" for r in rows)}
