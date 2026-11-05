"""虚拟测试卡只生成数据与固定辅助效果，不接收AI提交的Lua。"""

import copy

VIRTUAL_CODE_START = 170000000
HELPERS = ("send_to_grave", "revive", "flip_faceup", "destroy_monster")


def card_record(code, definition):
    from blocks.catalog import ATTRIBUTES, RACES
    from ygopack import cardinfo as c
    kind = definition.get("kind", "spell" if "helper" in definition else "monster")
    sub = definition.get("subtype", "normal")
    typ = {"monster": c.TYPE_MONSTER, "spell": c.TYPE_SPELL, "trap": c.TYPE_TRAP}[kind]
    if kind == "monster":
        typ |= {"normal": c.TYPE_NORMAL, "effect": c.TYPE_EFFECT, "fusion": c.TYPE_FUSION | c.TYPE_EFFECT}[sub]
    elif sub == "quickplay":
        typ |= c.TYPE_QUICKPLAY
    return {"code": code, "name": definition["name"], "type": typ,
        "level": definition.get("level", 1) if kind == "monster" else 0,
        "attribute": c.ATTRIBUTE_BITS[dict(ATTRIBUTES)[definition.get("attribute", "earth")]] if kind == "monster" else 0,
        "race": c.RACE_BITS[c.RACES.index(dict(RACES)[definition.get("race", "plant")])] if kind == "monster" else 0,
        "atk": definition.get("atk", 0), "def": definition.get("def", 0),
        "setcodes": [int(value, 16) for value in definition.get("setcodes", [])]}


def helper_effects(definition):
    from blocks.catalog import new
    helper = definition.get("helper")
    if helper == "send_to_grave":
        return [new("effect", type="activate", operation=[new("send_to_gy", cards=[new("pick", who="you",
            where=definition["source"], count=1, filter=[new("f_not_self")])])])]
    if helper == "revive":
        return [new("effect", type="activate", operation=[new("special_summon", cards=[new("pick", who="you",
            where="grave", count=1, filter=[new("f_kind", kind="monster")])])])]
    if helper in ("flip_faceup", "destroy_monster"):
        filters = [new("f_kind", kind="monster")]
        if helper == "flip_faceup":
            filters.append(new("f_position", position="facedown"))
        effect = new("effect", type="activate", target=[new("take_target", **{"as": "T"}, count=1,
            source=[new("all", who="both", where="mzone", filter=filters)])])
        effect["operation"] = [new("change_position", to="attack", cards=[new("target", name="T")]) if helper == "flip_faceup"
                               else new("destroy", cards=[new("target", name="T")])]
        return [effect]
    if helper:
        raise ValueError("未知辅助设施：" + str(helper))
    return []


def prepare(core, own_code, definitions, allowed_real):
    from blocks import SCHEMA, build
    codes = {"self": own_code}
    definitions = dict(definitions, __filler__={"name": "虚拟填充卡", "level": 1})
    for index, (key, definition) in enumerate(sorted(definitions.items())):
        code = VIRTUAL_CODE_START + index
        if code == own_code:
            code += len(definitions)
        codes[key] = code
        rec = card_record(code, definition)
        core.add_card(rec)
        model = {"schema": SCHEMA, "card": {"code": code, "name": rec["name"],
            "kind": "spell" if rec["type"] & 2 else "trap" if rec["type"] & 4 else "monster"},
            "effects": helper_effects(definition)}
        core.overrides[code] = build(model)["lua"].encode("utf-8")

    def ref(value):
        if isinstance(value, str) and value in codes:
            return codes[value]
        if type(value) is int and value in allowed_real:
            return value
        raise ValueError("未知引用或原文未明示的真实卡号：%s" % value)

    return codes, ref


def lower_field(field, ref, filler):
    result = {}
    for player in ("0", "1"):
        zones = {}
        for zone, entries in field.get(player, {}).items():
            zones[zone] = []
            for entry in entries:
                if isinstance(entry, dict):
                    item = {k: copy.deepcopy(v) for k, v in entry.items() if k not in ("ref", "repeat")}
                    item["code"] = ref(entry["ref"])
                    for index in range(entry.get("repeat", 1)):
                        clone = dict(item)
                        if "seq" in clone:
                            clone["seq"] += index
                        zones[zone].append(clone)
                else:
                    zones[zone].append(ref(entry))
        zones.setdefault("deck", [])
        zones["deck"].extend([filler] * max(0, 20 - len(zones["deck"])))
        result[player] = zones
    return result
