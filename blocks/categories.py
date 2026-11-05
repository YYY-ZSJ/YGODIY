"""cdb 的效果分类：第 n 位对应 strings.conf 的 !system 1100+n，只用于卡片搜索，不影响对局。"""

from .compile import walk

NAMES = ("炸魔陷", "炸怪", "除外", "送墓", "回手", "回卡组", "削手", "削卡组", "抽卡", "检索", "回收", "表示形式", "控制权", "攻守变化",
         "贯通", "多次攻击", "攻击限制", "直接攻击", "特殊召唤", "衍生物", "种族", "属性", "伤害", "回复", "破坏耐性", "效果耐性", "指示物",
         "赌博", "融合相关", "同调相关", "超量相关", "效果无效")
BLOCKS = {"banish": "除外", "send_to_gy": "送墓", "to_deck": "回卡组", "draw": "抽卡", "change_position": "表示形式", "get_control": "控制权",
          "special_summon": "特殊召唤", "create_token": "衍生物", "damage": "伤害", "recover": "回复", "add_counter": "指示物",
          "remove_counter": "指示物", "toss_coin": "赌博", "toss_dice": "赌博", "fusion_summon": "融合相关", "fusion_materials": "融合相关",
          "attach": "超量相关", "detach": "超量相关", "negate_activation": "效果无效", "negate_effect": "效果无效", "negate_summon": "效果无效",
          "f_race": "种族", "f_orig_race": "种族", "f_attr": "属性", "f_orig_attr": "属性"}
CODE_WORDS = (("PIERCE", "贯通"), ("EXTRA_ATTACK", "多次攻击"), ("ATTACK_ALL", "多次攻击"), ("DIRECT_ATTACK", "直接攻击"), ("INDESTRUCTABLE", "破坏耐性"),
              ("IMMUNE_EFFECT", "效果耐性"), ("CANNOT_BE_EFFECT_TARGET", "效果耐性"), ("RACE", "种族"), ("ATTRIBUTE", "属性"))
ATTACK_LIMITS = ("EFFECT_CANNOT_ATTACK", "EFFECT_CANNOT_ATTACK_ANNOUNCE", "EFFECT_CANNOT_DIRECT_ATTACK", "EFFECT_MUST_ATTACK")
STAT_CODES = ("EFFECT_UPDATE_", "EFFECT_SET_ATTACK", "EFFECT_SET_DEFENSE", "EFFECT_SET_BASE_")


def bit(name):
    return 1 << NAMES.index(name)


def _source(node):
    items = node.get("cards") or []
    return items[0] if items else {}


def _destroy(node):
    kinds = {part for item in walk(_source(node).get("filter") or []) if item["block"] == "f_kind" for part in str(item["kind"]).split("+")}
    if _source(node).get("block") == "this_card":
        return 0
    value = bit("炸怪") if "monster" in kinds or not kinds else 0
    return value | (bit("炸魔陷") if kinds & {"spell", "trap"} or not kinds else 0)


def _to_hand(node):
    where = str(_source(node).get("where", ""))
    return bit("检索") if "deck" in where else bit("回收") if "grave" in where else bit("回手")


def _effect_code(code):
    code = str(code or "")
    value = 0
    if code in ATTACK_LIMITS:
        value |= bit("攻击限制")
    if code.startswith(STAT_CODES) and ("ATTACK" in code or "DEFENSE" in code):
        value |= bit("攻守变化")
    for word, name in CODE_WORDS:
        if word in code and not (word == "DIRECT_ATTACK" and code == "EFFECT_CANNOT_DIRECT_ATTACK"):
            value |= bit(name)
    return value


def categories(model):
    """按积木推出分类，只是起点：玩家可以在「卡片数据」里手动改。"""
    value = 0
    for node in walk(model.get("effects", [])):
        block = node.get("block")
        if block in BLOCKS:
            value |= bit(BLOCKS[block])
        if block == "destroy":
            value |= _destroy(node)
        elif block == "to_hand":
            value |= _to_hand(node)
        elif block == "discard" and _source(node).get("who") == "opp":
            value |= bit("削手")
        elif block in ("send_to_gy", "banish") and _source(node).get("block") == "deck_top":
            value |= bit("削卡组")
        elif block == "extra_materials":
            method = node.get("method") or "synchro"
            value |= {"synchro": bit("同调相关"), "xyz": bit("超量相关")}.get(method, 0)
        if "code" in node and isinstance(node.get("code"), str):
            value |= _effect_code(node["code"])
    return value
