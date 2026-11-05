"""Lua 后端的公共部分：常量表与小工具。"""

from ..model import applies



LOC = {
    "hand": "LOCATION_HAND", "mzone": "LOCATION_MZONE", "szone": "LOCATION_SZONE", "field": "LOCATION_ONFIELD",
    "pzone": "LOCATION_PZONE", "grave": "LOCATION_GRAVE", "deck": "LOCATION_DECK", "banished": "LOCATION_REMOVED",
    "extra": "LOCATION_EXTRA", "linked": "LOCATION_MZONE",
}
TYPE = {
    "monster": "TYPE_MONSTER", "spell": "TYPE_SPELL", "trap": "TYPE_TRAP", "spell_trap": "TYPE_SPELL+TYPE_TRAP",
    "pendulum": "TYPE_PENDULUM", "effect": "TYPE_EFFECT", "tuner": "TYPE_TUNER", "normal": "TYPE_NORMAL",
    "ritual": "TYPE_RITUAL", "fusion": "TYPE_FUSION", "synchro": "TYPE_SYNCHRO", "xyz": "TYPE_XYZ", "link": "TYPE_LINK",
    "quick": "TYPE_QUICKPLAY", "continuous": "TYPE_CONTINUOUS", "equip": "TYPE_EQUIP", "field": "TYPE_FIELD",
    "counter": "TYPE_COUNTER",
}
RACE = {
    "warrior": "RACE_WARRIOR", "spellcaster": "RACE_SPELLCASTER", "fairy": "RACE_FAIRY", "fiend": "RACE_FIEND",
    "zombie": "RACE_ZOMBIE", "machine": "RACE_MACHINE", "aqua": "RACE_AQUA", "pyro": "RACE_PYRO", "rock": "RACE_ROCK",
    "winged_beast": "RACE_WINDBEAST", "plant": "RACE_PLANT", "insect": "RACE_INSECT", "thunder": "RACE_THUNDER",
    "dragon": "RACE_DRAGON", "beast": "RACE_BEAST", "beast_warrior": "RACE_BEASTWARRIOR", "dinosaur": "RACE_DINOSAUR",
    "fish": "RACE_FISH", "sea_serpent": "RACE_SEASERPENT", "reptile": "RACE_REPTILE", "psychic": "RACE_PSYCHO",
    "divine": "RACE_DIVINE", "wyrm": "RACE_WYRM", "cyberse": "RACE_CYBERSE", "illusion": "RACE_ILLUSION",
}
ATTRIBUTE = {
    "earth": "ATTRIBUTE_EARTH", "water": "ATTRIBUTE_WATER", "fire": "ATTRIBUTE_FIRE", "wind": "ATTRIBUTE_WIND",
    "light": "ATTRIBUTE_LIGHT", "dark": "ATTRIBUTE_DARK", "divine": "ATTRIBUTE_DIVINE",
}
STAT_FN = {
    ("atk", "<="): "IsAttackBelow", ("atk", ">="): "IsAttackAbove", ("atk", "=="): "IsAttack",
    ("def", "<="): "IsDefenseBelow", ("def", ">="): "IsDefenseAbove", ("def", "=="): "IsDefense",
    ("level", "<="): "IsLevelBelow", ("level", ">="): "IsLevelAbove", ("level", "=="): "IsLevel",
}
POSITION = {"attack": "IsAttackPos", "defense": "IsDefensePos", "faceup": "IsFaceup", "facedown": "IsFacedown"}
CATEGORY = {
    "destroy": "CATEGORY_DESTROY", "banish": "CATEGORY_REMOVE", "send_to_gy": "CATEGORY_TOGRAVE",
    "add_to_hand": "CATEGORY_TOHAND", "special_summon": "CATEGORY_SPECIAL_SUMMON", "set_spell_trap": "CATEGORY_SSET",
    "change_position": "CATEGORY_POSITION", "draw": "CATEGORY_DRAW", "negate_activation": "CATEGORY_NEGATE",
    "negate_effect": "CATEGORY_DISABLE", "negate_card_effects": "CATEGORY_DISABLE",
    "return_to_extra": "CATEGORY_TOEXTRA", "negate_summon": "CATEGORY_DISABLE_SUMMON", "discard": "CATEGORY_HANDES",
    "swap_control": "CATEGORY_CONTROL", "toss_coin": "CATEGORY_COIN", "damage": "CATEGORY_DAMAGE",
}
HINT = {
    "destroy": "HINTMSG_DESTROY", "banish": "HINTMSG_REMOVE", "send_to_gy": "HINTMSG_TOGRAVE",
    "add_to_hand": "HINTMSG_ATOHAND", "special_summon": "HINTMSG_SPSUMMON", "set_spell_trap": "HINTMSG_SET",
    "release": "HINTMSG_RELEASE", "negate_card_effects": "HINTMSG_DISABLE",
    "attach_xyz_material": "HINTMSG_XMATERIAL",
}
LANDED = {"banish": "LOCATION_REMOVED", "add_to_hand": "LOCATION_HAND", "send_to_gy": "LOCATION_GRAVE"}
SHORT = {
    "destroy": "破坏", "banish": "除外", "send_to_gy": "送去墓地", "add_to_hand": "加入手卡",
    "special_summon": "特殊召唤", "set_spell_trap": "盖放", "change_position": "改变表示形式", "draw": "抽卡",
    "negate_activation": "发动无效", "negate_effect": "效果无效", "negate_attack": "攻击无效",
    "negate_card_effects": "效果无效", "apply_continuous": "适用效果",
    "return_to_extra": "回到额外卡组", "copy_effect": "复制卡名·效果", "attach_xyz_material": "放入超量素材",
    "activate_from_deck": "从卡组发动", "one_of": "加入手卡或特殊召唤", "toss_coin": "投掷硬币",
    "create_token": "特殊召唤衍生物", "select": "选择怪兽", "negate_summon": "召唤无效", "perform_summon": "仪式召唤",
    "schedule_operation": "预约处理", "discard": "丢弃",
}
REASON_EFFECT = "REASON_EFFECT"
SUMMON_EVENTS = {"normal_summon_success": "EVENT_SUMMON_SUCCESS", "special_summon_success": "EVENT_SPSUMMON_SUCCESS",
                 "flip_summon_success": "EVENT_FLIP_SUMMON_SUCCESS"}


def indent(lines, n=1):
    return ["\t" * n + l for l in lines]


def sides(sel):
    mask = "+".join(dict.fromkeys(LOC[w] for w in sel["where"])) or "0"
    return {"you": (mask, "0"), "opp": ("0", mask), "both": (mask, mask)}[sel["who"]]


def cmp_lua(op, n):
    return "%s%d" % ({"==": "==", "<=": "<=", ">=": ">=", "<": "<", ">": ">", "!=": "~="}[op], n)


def step_refs(step):
    """这一步引用了哪些绑定（what 与持续适用内容里的 ref）。"""
    out = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("ref"), str):
                out.add(node["ref"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(step.get("what"))
    for ap in applies(step):
        walk({k: v for k, v in ap.items() if k != "do"})
    return out


def able(act):
    return {
        "add_to_hand": ["$c:IsAbleToHand()"],
        "banish": ["$c:IsAbleToRemove()"],
        "send_to_gy": ["$c:IsAbleToGrave()"],
        "special_summon": ["$c:IsCanBeSpecialSummoned(e,0,tp,false,false)"],
        "set_spell_trap": ["$c:IsSSetable()"],
        "negate_card_effects": ["aux.NegateMonsterFilter($c)"],
        "attach_xyz_material": ["$c:IsCanOverlay()"],
    }.get(act, [])
