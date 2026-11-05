"""积木树 → 中文（文本辅助）。每块积木有自己的读法，拼起来是一句通顺的效果文字；
认得出的常见拼法换成官方说法（「从卡组把1只4星以下的战士族怪兽加入手卡」「那个发动无效并破坏」）。
卡面文字最终由玩家决定，可以手改。
"""

import os

from .catalog import (
    ATTRIBUTES, CMPS, COUNTERS, KINDS, PHASES, PLAYERS, RACES, RANGES, SUBTYPES, SUMMON_METHODS, TO_POSITIONS, ZONES, code_zh,
    EVENTS, MultiMap, events_of, multi_parts,
)
from .compile import one

ZONE_ZH = MultiMap(dict(ZONES, mzone="场上"), "·",
                   alias={"mzone": "场上", "szone": "场上", "fzone": "场上", "pzone": "场上", "field": "场上"})
# 多选的值读成「A·B」：「兽族·兽战士族」「光·暗属性」「魔法·陷阱卡」「融合·同调召唤」「因战斗·效果」
RACE_NAMES = MultiMap(dict(RACES), "·")
PHASE_NAMES = MultiMap(dict(PHASES), "或者")
ATTR_NAMES = MultiMap(dict(ATTRIBUTES), "·")
KIND_NAMES = MultiMap(dict(KINDS), "·", strip=True)
SUBTYPE_NAMES = MultiMap(dict(SUBTYPES), "·")
SUMMON_NAMES = MultiMap(dict(SUMMON_METHODS), "·", strip=True)
OFF_FIELD_PLACES = {"hand", "grave", "banished", "deck", "extra"}
WHO_ZH = {"you": "自己", "opp": "对方", "both": "双方"}
CMP_WORD = {">=": "以上", "<=": "以下"}
VERB = {"destroy": "破坏", "to_hand": "加入手卡", "send_to_gy": "送去墓地", "banish": "除外", "to_deck": "回到卡组",
        "special_summon": "特殊召唤", "set_card": "盖放", "discard": "丢弃", "release": "解放"}
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
# 几个地方一起时，场上的格子都说「场上」（「手卡·场上·墓地」）
RANGE_ZH = MultiMap(dict(RANGES, mzone="怪兽区域"), "·",
                    alias={"mzone": "场上", "szone": "场上", "fzone": "场上", "pzone": "场上"})


def off_field(rng):
    """不在场上（也不只是手卡）的位置：「这张卡在墓地存在的场合」要写出来。"""
    ps = multi_parts(rng, dict(RANGES))
    return bool(ps) and ps != ["hand"] and all(p in ("hand", "grave", "banished") for p in ps)
SPAN = {"permanent": "", "end_of_turn": "直到回合结束时", "end_of_next_turn": "直到下个回合结束时",
        "next_standby": "直到下次的自己准备阶段", "opp_turn_end": "直到对方回合结束时"}
PLAYER_SPAN = {"permanent": "这次决斗中，", "end_of_turn": "这个回合，", "end_of_next_turn": "直到下个回合结束时，",
               "next_standby": "直到下次的自己准备阶段，", "opp_turn_end": "直到对方回合结束时，"}
CHAIN_ZH = {"destroy": "要让卡破坏的", "special_summon": "包含特殊召唤的", "search": "包含从卡组加入手卡的",
            "remove": "要让卡除外的", "to_grave": "要把卡送去墓地的", "draw": "包含抽卡的", "negate": "要让发动无效的",
            "to_hand": "要让卡回到手卡的"}
SPELL_SUB = {"normal": "通常", "quick": "速攻", "continuous": "永续", "equip": "装备", "field": "场地", "ritual": "仪式",
             "counter": "反击"}
# 数值类效果代码：「{卡}的攻击力{期限}上升{数}」
STAT = {"EFFECT_UPDATE_ATTACK": ("的攻击力", "上升", "下降"), "EFFECT_UPDATE_DEFENSE": ("的守备力", "上升", "下降"),
        "EFFECT_UPDATE_LEVEL": ("的等级", "上升", "下降"), "EFFECT_SET_ATTACK": ("的攻击力", "变成", None),
        "EFFECT_SET_ATTACK_FINAL": ("的攻击力", "变成", None), "EFFECT_SET_DEFENSE": ("的守备力", "变成", None),
        "EFFECT_CHANGE_LEVEL": ("的等级", "变成", None)}
# 卡片的状态：「{卡}{期限}不会被战斗破坏」
PHRASE = {"EFFECT_INDESTRUCTABLE_BATTLE": "不会被战斗破坏", "EFFECT_INDESTRUCTABLE_EFFECT": "不会被效果破坏",
          "EFFECT_CANNOT_ATTACK": "不能攻击", "EFFECT_CANNOT_DIRECT_ATTACK": "不能直接攻击",
          "EFFECT_DIRECT_ATTACK": "可以直接攻击", "EFFECT_PIERCE": "向守备表示怪兽攻击的场合，给与对方贯穿伤害",
          "EFFECT_CANNOT_BE_EFFECT_TARGET": "不会成为效果的对象", "EFFECT_CANNOT_BE_BATTLE_TARGET": "不会成为攻击对象",
          "EFFECT_DISABLE": "效果无效化", "EFFECT_CANNOT_TRIGGER": "不能把效果发动",
          "EFFECT_IMMUNE_EFFECT": "不受其他卡的效果影响", "EFFECT_EXTRA_ATTACK": "在同1次的战斗阶段中可以作2次攻击",
          "EFFECT_CANNOT_CHANGE_POSITION": "不能把表示形式变更", "EFFECT_CANNOT_RELEASE": "不能解放",
          "EFFECT_UNRELEASABLE_SUM": "不能作为上级召唤的解放",
          "EFFECT_INDESTRUCTABLE_COUNT": "只有1次不会被战斗以及卡的效果破坏"}
# 「只对对方的效果」的抗性
PHRASE_OPP = {"EFFECT_CANNOT_BE_EFFECT_TARGET": "不会成为对方的效果的对象", "EFFECT_INDESTRUCTABLE_EFFECT": "不会被对方的效果破坏",
              "EFFECT_IMMUNE_EFFECT": "不受对方的效果影响"}
REASON_PRE = {"battle": "因战斗", "effect": "因效果", "cost": "作为代价", "material": "作为素材", "release": "被解放",
              "discard": "被丢弃", "destroy": "被破坏", "fusion": "作为融合素材", "synchro": "作为同调素材",
              "xyz": "作为超量素材", "link": "作为连接素材", "return": "回到手卡·卡组", "reveal": "被翻开", "draw": "被抽到"}
REASON_PRE = MultiMap(REASON_PRE, "·", strip=True)      # 「因战斗·效果」
# 时机：(说法里的事件, 后缀)；{w} 是「谁的」
EVENT_READ = {"summon": ("这张卡召唤", "的场合"), "spsummon": ("这张卡特殊召唤", "的场合"),
              "summon_both": ("这张卡召唤·特殊召唤", "的场合"), "to_grave": ("这张卡被送去墓地", "的场合"),
              "destroyed": ("这张卡被破坏", "的场合"), "draw": ("{w}抽卡", "的场合"), "attack": ("{w}怪兽的攻击宣言", "时"),
              "chaining": ("{w}把卡的效果发动", "时"), "standby": ("{w}准备阶段", ""), "end": ("{w}结束阶段", ""),
              "be_attacked": ("这张卡被选择作为攻击对象", "时"), "battle_end": ("{w}战斗阶段结束", "时"),
              "battle_destroyed": ("这张卡被战斗破坏", "的场合"), "effect_destroyed": ("这张卡被效果破坏", "的场合"),
              "battle_destroying": ("这张卡战斗破坏对方怪兽", "时"), "leave_field": ("这张卡从场上离开", "的场合"),
              "field_to_grave": ("这张卡从场上送去墓地", "的场合"), "banished": ("这张卡被除外", "的场合"),
              "released": ("这张卡被解放", "的场合"), "to_hand": ("这张卡加入手卡", "的场合"),
              "flip_summon": ("这张卡反转召唤", "的场合"), "flip": ("这张卡反转", "的场合"), "be_material": ("这张卡作为素材", "的场合"),
              "battle_damage": ("这张卡给与对方战斗伤害", "时"), "be_targeted": ("这张卡成为{w}的效果的对象", "时"),
              "monster_summoned": ("{w}把怪兽召唤", "的场合"), "monster_spsummoned": ("{w}把怪兽特殊召唤", "的场合"),
              "summon_attempt": ("{w}把怪兽召唤", "之际"), "spsummon_attempt": ("{w}把怪兽特殊召唤", "之际"),
              "battle_start": ("这张卡进行战斗的伤害步骤开始", "时"), "pre_damage_calc": ("这张卡进行战斗的伤害计算前", ""),
              "battle_confirm": ("这张卡进行战斗的伤害步骤开始", "后"),
              "battled": ("这张卡进行战斗的伤害计算后", ""), "damage_step_end": ("这张卡进行战斗的伤害步骤结束", "时"),
              "monster_summoned_both": ("{w}把怪兽召唤·特殊召唤", "的场合"),
              "player_battle_damaged": ("{w}受到战斗伤害", "时"), "player_damaged": ("{w}受到伤害", "时"),
              "equip_battle_damage": ("装备怪兽给与对方战斗伤害", "时"),
              "cards_to_grave": ("{w}的卡被送去墓地", "的场合"), "cards_banished": ("{w}的卡被除外", "的场合"),
              "cards_destroyed": ("{w}的卡被破坏", "的场合"), "cards_to_hand": ("{w}的卡加入手卡", "的场合"),
              "cards_to_deck": ("{w}的卡回到卡组", "的场合"), "cards_leave_field": ("{w}的卡从场上离开", "的场合"),
              "monster_battle_destroyed": ("{w}的怪兽被战斗破坏", "的场合"),
              "monster_battle_start": ("{w}的怪兽进行战斗的伤害步骤开始", "时"),
              "monster_damage_step_end": ("{w}的怪兽进行战斗的伤害步骤结束", "时"),
              "chain_solved": ("{w}的卡的效果处理完", "时"), "chain_negated": ("{w}的卡的发动被无效", "时"),
              "chain_end": ("连锁处理完", "时"), "bp_start": ("{w}战斗阶段开始", "时"),
              "cards_set": ("{w}把魔法·陷阱卡盖放", "的场合"), "monsters_set": ("{w}把怪兽里侧守备表示盖放", "的场合"),
              "pos_changed": ("{w}的怪兽的表示形式变更", "的场合"), "detached": ("{w}的超量素材被取除", "的场合"),
              "recovered": ("{w}回复基本分", "的场合"), "equipped": ("{w}的卡被装备装备卡", "的场合"),
              "leaving": ("这张卡从场上离开", "前"), "cards_moved": ("{w}的卡移动", "的场合"),
              "predraw": ("{w}抽卡阶段的通常抽卡前", "")}
CHAIN_IS_ZH = {"monster": "怪兽的效果", "spell": "魔法卡", "trap": "陷阱卡", "activation": "魔法·陷阱卡的发动",
               "from_hand": "在手卡发动的效果", "from_grave": "在墓地发动的效果", "from_field": "在场上发动的效果"}
POS_ZH = [("faceup", "表侧表示"), ("facedown", "里侧表示"), ("attack", "攻击表示"), ("defense", "守备表示")]
STAT_ZH = {"atk": "攻击力", "def": "守备力", "level": "等级"}
DELAY_ZH = {"this_end": "这个回合的结束阶段", "next_standby": "下次的自己准备阶段", "next_end": "下个回合的结束阶段"}
ACT_ZH = {"draw": "抽卡的数量", "spsummon": "特殊召唤的次数", "summon": "召唤的次数", "attack": "攻击的次数",
          "chain": "发动卡和效果的次数"}
ANNOUNCE_ZH = {"attribute": "属性", "race": "种族", "type": "卡的种类", "level": "等级", "card": "卡名", "number": "数字", "race_or_attr": "种族或者属性"}
SS_HOW = {"attack": "表侧攻击表示", "defense": "守备表示", "facedown": "里侧守备表示"}
VAR_DONE = {}             # 记下的卡被处理过了：名字 → 动词（读一张卡时从头记）
PLACE_VERB = {"szone": "在自己场上表侧表示放置", "fzone": "在自己的场地区域表侧表示放置", "pzone": "在自己的灵摆区域放置"}
FUSION_MATS_ZH = {"hf": "手卡·场上", "hfg": "手卡·场上·墓地", "hfd": "手卡·场上·卡组", "hand": "手卡", "field": "场上"}
RITUAL_FROM_ZH = {"hand": "手卡", "hand_grave": "自己的手卡·墓地", "hand_deck": "自己的手卡·卡组"}
# 玩家受到的限制：「{谁}不能把{卡}特殊召唤」（{n} 是卡片条件读出的名词，没有条件时用后面的默认词）
PLAYER_READ = {"EFFECT_CANNOT_SUMMON": ("不能把{n}召唤", "怪兽"), "EFFECT_CANNOT_SPECIAL_SUMMON": ("不能把{n}特殊召唤", "怪兽"),
               "EFFECT_CANNOT_FLIP_SUMMON": ("不能把{n}反转召唤", "怪兽"), "EFFECT_CANNOT_MSET": ("不能把{n}盖放", "怪兽"),
               "EFFECT_CANNOT_SSET": ("不能把{n}盖放", "魔法·陷阱卡"), "EFFECT_CANNOT_ACTIVATE": ("不能把{n}的效果发动", "卡"),
               "EFFECT_CANNOT_TO_HAND": ("不能把{n}加入手卡", "卡"), "EFFECT_CANNOT_REMOVE": ("不能把{n}除外", "卡"),
               "EFFECT_CANNOT_TO_GRAVE": ("不能把{n}送去墓地", "卡"), "EFFECT_CANNOT_TO_DECK": ("不能把{n}回到卡组", "卡"),
               "EFFECT_CANNOT_DRAW": ("不能抽卡", ""), "EFFECT_CANNOT_BP": ("不能进行战斗阶段", ""),
               "EFFECT_CANNOT_EP": ("不能进行结束阶段", ""), "EFFECT_SKIP_DP": ("跳过抽卡阶段", ""),
               "EFFECT_AVOID_BATTLE_DAMAGE": ("不会受到战斗伤害", ""), "EFFECT_NO_BATTLE_DAMAGE": ("不会受到战斗伤害", ""),
               "EFFECT_REFLECT_BATTLE_DAMAGE": ("受到的战斗伤害由对方代受", ""),
               "EFFECT_DRAW_COUNT": ("在抽卡阶段的通常抽卡变成{v}张", "")}


# ------------------------------------------------------------ 卡片条件、卡片组
def filter_noun(filters, default="卡"):
    """卡片条件 → 名词：「4星以下的战士族怪兽」「这张卡以外的表侧表示怪兽」「「魔导书」卡或者魔法师族怪兽」。"""
    flat = []
    for f in filters:                      # 「并且」只是把几条包成一条：摊开
        flat += f.get("filter") or [] if f["block"] == "f_all" else [f]
    filters = flat
    anyf = next((f for f in filters if f["block"] == "f_any"), None)
    if anyf:
        rest = [f for f in filters if f is not anyf]
        nouns = [filter_noun(rest + (it.get("filter") or [] if it["block"] == "f_all" else [it]), default)
                 for it in anyf.get("items") or []]
        return "或者".join(nouns) or filter_noun(rest, default)
    kind, pre, tribe, sub, named = default, [], [], [], None
    monster = lambda k: "怪兽" if k == "卡" else k            # noqa: E731
    for f in filters:
        b = f["block"]
        if b == "f_kind":
            kind = "怪兽" if f["kind"] == "monster" else KIND_NAMES[f["kind"]]
        elif b == "f_subtype":
            sub.append(f["subtype"])
        elif b == "f_race":
            tribe.append(RACE_NAMES[f["race"]])
            kind = monster(kind)
        elif b == "f_attr":
            tribe.append(ATTR_NAMES[f["attribute"]] + "属性")
            kind = monster(kind)
        elif b in ("f_level", "f_atk", "f_def") and (f.get("value_n") or []):
            word = {"f_level": "等级", "f_atk": "攻击力", "f_def": "守备力"}[b]
            vn = f["value_n"][0]
            same = {"f_level": "level_of", "f_atk": "atk_of", "f_def": "def_of"}[b]
            if f["op"] == "==" and vn["block"] == same:       # 「和那只怪兽相同等级的」
                pre.append("和%s相同%s的" % (Reader().cards((vn.get("card") or [None])[0]), word))
                kind = monster(kind)
                continue
            value = _number_text(vn)
            pre.append("%s在%s%s的" % (word, value, CMP_WORD[f["op"]]) if f["op"] in CMP_WORD else
                       "%s%s%s的" % (word, {"==": "和", "!=": "不是", ">": "比", "<": "比"}[f["op"]] + value,
                                    {"==": "相同", "!=": "", ">": "高", "<": "低"}[f["op"]]))
            kind = monster(kind)
        elif b == "f_level":
            pre.append("%d星%s的" % (f["value"], CMP_WORD.get(f["op"], "")) if f["op"] in CMP_WORD or f["op"] == "=="
                       else "等级%s%d的" % (dict(CMPS)[f["op"]], f["value"]))
            kind = monster(kind)
        elif b in ("f_atk", "f_def"):
            word = "攻击力" if b == "f_atk" else "守备力"
            pre.append("%s%d%s的" % (word, f["value"], CMP_WORD.get(f["op"], "")) if f["op"] in CMP_WORD
                       else "%s%s%d的" % (word, dict(CMPS)[f["op"]], f["value"]))
            kind = monster(kind)
        elif b == "f_name":
            named = "「%s」" % (f.get("name") or f["code"])
        elif b == "f_set":
            tribe.insert(0, "「%s」" % (f.get("name") or f["setcode"]))
        elif b == "f_position":
            pre.insert(0, dict([("faceup", "表侧表示的"), ("facedown", "里侧表示的"), ("attack", "攻击表示的"),
                                ("defense", "守备表示的")])[f["position"]])
        elif b == "f_not_self":
            pre.insert(0, "这张卡以外的")
        elif b == "f_controller":
            pre.insert(0, "%s的" % dict(PLAYERS)[f["who"]])
        elif b == "f_summon_type":
            pre.append("%s的" % SUMMON_NAMES[f["method"]])
            kind = monster(kind)
        elif b == "f_prev_location":
            pre.append("从额外卡组特殊召唤的" if f["where"] == "extra" else "从%s离开的" % ZONE_ZH[f["where"]])
        elif b == "f_prev_position":
            pre.insert(0, "原本是%s的" % dict(POS_ZH)[f["position"]])
        elif b == "f_lists_code":
            pre.append("记述了「%s」的" % (f.get("name") or f["code"]))
        elif b == "f_same_code":
            src = (f.get("card") or [None])[0]
            if src and src.get("block") == "var" and src["name"] in VAR_DONE and len(filters) == 1:
                named = "%s以及那些同名卡" % Reader().cards(src)       # 官方说法
            else:
                pre.append("和%s原本卡名相同的" % Reader().cards(src))
        elif b == "f_by_player":
            pre.append("被%s移动的" % dict(PLAYERS)[f["who"]])
        elif b == "f_declared":
            if f["what"] == "card":
                named = "宣言的卡"
            else:
                pre.append("宣言的%s的" % ANNOUNCE_ZH[f["what"]])
                if f["what"] in ("attribute", "race", "level"):
                    kind = monster(kind)
        elif b == "f_zone_seq":
            pre.append({"main": "主要怪兽区域的", "extra": "额外怪兽区域的", "middle": "正中间的怪兽区域的"}[f["seq"]])
            kind = monster(kind)
        elif b == "f_has_effect":
            pre.append("适用着「%s」的" % code_zh(f["code"]))
        elif b == "f_not_destroying":
            pass                              # 规则上的细节，卡上不写
        elif b == "f_chaining":
            pre.append("发动中的")
        elif b == "f_battle_pair":
            if f["who"] == "both":
                named = "进行战斗的这张卡和那只怪兽"
            else:
                pre.append("和这张卡进行战斗的")
                kind = monster(kind)
        elif b == "f_battled_opp":
            pre.append("和对方怪兽进行过战斗的")
            kind = monster(kind)
        elif b == "f_can_attack":
            pre.append("可以攻击的")
            kind = monster(kind)
        elif b == "f_prev_name":
            named = "原本在场上的「%s」" % (f.get("name") or f["code"])
        elif b == "f_activated_effect":
            pass
        elif b == "f_orig_race":
            tribe.append("原本种族是%s的" % RACE_NAMES[f["race"]])
            kind = monster(kind)
        elif b == "f_orig_attr":
            tribe.append("原本属性是%s属性的" % ATTR_NAMES[f["attribute"]])
            kind = monster(kind)
        elif b == "f_prev_kind":
            pre.insert(0, "在场上时是%s的" % KIND_NAMES[f["kind"]])
        elif b == "f_by_this":
            pre.insert(0, "因为这张卡的")
        elif b == "f_prev_set":
            tribe.insert(0, "原本在场上的「%s」" % (f.get("name") or f["setcode"]))
        elif b == "f_prev_race":
            tribe.append("原本是%s的" % RACE_NAMES[f["race"]])
            kind = monster(kind)
        elif b == "f_prev_attr":
            tribe.append("原本是%s属性的" % ATTR_NAMES[f["attribute"]])
            kind = monster(kind)
        elif b == "f_same_column":
            pre.insert(0, "和这张卡相同纵列的")
        elif b == "f_linked":
            pre.insert(0, "这张卡所连接区的")
            kind = monster(kind)
        elif b == "f_link_state":
            pre.insert(0, "连接状态的")
            kind = monster(kind)
        elif b in ("f_rank", "f_link"):
            word = "阶" if b == "f_rank" else "连接"
            if b == "f_rank":
                pre.append("%d阶%s的" % (f["value"], CMP_WORD.get(f["op"], "")) if f["op"] in CMP_WORD or f["op"] == "=="
                           else "阶级%s%d的" % (dict(CMPS)[f["op"]], f["value"]))
            else:
                pre.append("连接%d%s的" % (f["value"], CMP_WORD.get(f["op"], "")) if f["op"] in CMP_WORD or f["op"] == "=="
                           else "连接值%s%d的" % (dict(CMPS)[f["op"]], f["value"]))
            kind = monster(kind)
        elif b in ("f_same_attr", "f_same_race"):
            pre.append("和%s相同%s的" % (Reader().cards((f.get("card") or [None])[0]), "属性" if b == "f_same_attr" else "种族"))
            kind = monster(kind)
        elif b == "f_by_proc":
            pre.insert(0, "用这个方法出场的")
        elif b == "f_prev_controller":
            pre.insert(0, "原本由%s控制的" % dict(PLAYERS)[f["who"]])
        elif b == "f_reason":
            pre.append("%s的" % REASON_PRE[f["reason"]])
        elif b == "f_not":
            pre.insert(0, "%s以外的" % filter_noun(f.get("filter", [])))
    if named:
        return "".join(pre) + named
    if kind == "怪兽":                   # 「表侧表示怪兽」：表示形式直接接怪兽，不加「的」
        pre = [x[:-1] if x in ("表侧表示的", "里侧表示的", "攻击表示的", "守备表示的") else x for x in pre]
    for s in sub:
        ps = multi_parts(s, SUBTYPE_NAMES)          # 可以勾几个：「融合·同调·超量怪兽」「速攻·永续魔法卡」
        p0 = ps[0]
        if kind == "卡" and p0 in ("quick", "equip", "field", "ritual_spell"):      # 只有魔法卡才有的种类
            kind = "魔法卡"
        elif kind == "卡" and p0 == "counter":
            kind = "陷阱卡"
        elif kind == "卡" and p0 == "continuous":
            kind = "魔法·陷阱卡"
        if kind in ("魔法卡", "陷阱卡", "魔法·陷阱卡"):
            kind = "·".join(SPELL_SUB.get(p, "") for p in ps) + kind
        else:
            kind = SUBTYPE_NAMES[s] + ("" if p0 in ("tuner", "token", "trapmonster") else "怪兽")
            if s == "tuner":
                kind = "调整"
    return "".join(pre) + "".join(tribe) + kind


def _number_text(node):
    return Reader().number(node)


def default_noun(node):
    """怪兽区域里的卡就是怪兽：没有卡片条件时说「怪兽」。"""
    return "怪兽" if node.get("where") == "mzone" else "卡"


def measure(noun):
    return "只" if noun.endswith("怪兽") or noun.endswith("调整") else "张"


def zone(node):
    if node["who"] == "both" and node["where"] in ("mzone", "field"):
        return "场上"                    # 官方说法「场上」就是双方场上
    return WHO_ZH[node["who"]] + ZONE_ZH[node["where"]]


class Reader:
    def __init__(self):
        self.target = None          # 当前效果的取对象积木
        self.each = None            # 「对每一张」里「当前这张」读作什么
        self.last_verb = None       # 前一个动作怎么说（「不能除外的场合」「这个效果特殊召唤的卡」）
        self.targets = []
        self.carried_verb = None

    def qty(self, node, noun):
        """选卡的张数：「2只」「最多2只」「这个回合自己抽卡的数量的」。"""
        n = one(node, "count_n")
        if n is not None and n["block"] == "num":
            return "%s%d%s" % ("最多" if node.get("upto") == "yes" else "", n["value"], measure(noun))
        if n is not None and n["block"] == "count_of":       # 「对方场上的怪兽数量的怪兽」
            return "%s数量的" % self.cards(one(n, "cards"))
        if n is not None:
            return "%s的" % self.number(n)
        return "%s%d%s" % ("最多" if node.get("upto") == "yes" else "", node["count"], measure(noun))

    def count_text(self, node, unit):
        n = one(node, "count_n")
        if n is not None and n["block"] == "num":
            return "%d%s" % (n["value"], unit)
        return self.number(n) + "的" if n is not None else "%d%s" % (node["count"], unit)

    def target_noun(self, count=None):
        t = self.target
        noun = filter_noun((one(t, "source") or {}).get("filter", [])) if t else "卡"
        n = t["count"] if t else count or 1
        return ("那只" if measure(noun) == "只" else "那张") + ("怪兽" if measure(noun) == "只" else "卡") if n == 1 \
            else "那些" + ("怪兽" if measure(noun) == "只" else "卡")

    def cards(self, node):
        """卡片组 → 名词短语。"""
        if node is None:
            return "（哪些卡？）"
        b = node["block"]
        if b == "this_card":
            return "这张卡"
        if b == "target":
            many = [t for t in (self.targets or []) if t["as"] == node.get("name")]
            if len(self.targets or []) > 1 and many:
                src = one(many[0], "source") or {}
                noun = filter_noun(src.get("filter", []), default_noun(src))
                return "作为对象的%s%s" % ({"you": "自己", "opp": "对方"}.get(src.get("who"), ""), noun) if src else "作为对象的卡"
            return self.target_noun()
        if b == "var":
            if node["name"] in VAR_DONE:          # 「这个效果送去墓地的卡」
                return "这个效果%s的卡" % VAR_DONE[node["name"]]
            return "记下的卡%s" % node["name"]
        if b == "operated":
            if self.last_verb:          # 「这个效果破坏的卡」「这个效果除外的「玄化」卡」
                default = "怪兽" if "召唤" in self.last_verb else "卡"
                return "这个效果%s的%s" % (self.last_verb, filter_noun(node.get("filter") or [], default))
            return "那些卡"
        if b == "each":
            return self.each or "那张卡"
        if b == "chain_card":
            return "那张卡"
        if b == "event_cards":
            return "那些卡中的%s" % filter_noun(node["filter"]) if node.get("filter") else "那些卡"
        if b == "attacker":
            return "攻击怪兽"
        if b == "attack_target":
            return "被攻击的怪兽"
        if b == "battling":
            return "进行战斗的%s怪兽" % dict(PLAYERS)[node["who"]]
        if b == "equip_target":
            return "装备怪兽"
        if b == "cost_cards":
            return "作为代价的卡"
        if b == "random_pick":
            noun = filter_noun(node.get("filter", []), default_noun(node))
            return "随机选%s%d%s%s" % (zone(node), node["count"], measure(noun), noun)
        if b == "equip_group":
            return "这张卡装备着的卡"
        if b == "card_target":
            return "那只怪兽"
        if b == "prev_equip_target":
            return "这张卡装备过的怪兽"
        if b == "column_group":
            return "和这张卡相同纵列的其他卡"
        if b == "linked_group":
            return "这张卡所连接区的怪兽"
        if b == "max_of":
            inner = one(node, "cards")
            word = {"atk": "攻击力", "def": "守备力", "level": "等级"}[node["stat"]] + \
                ("最高" if node["which"] == "max" else "最低")
            if inner and inner["block"] in ("all", "pick"):
                return "%s的%s的%s" % (zone(inner), word, filter_noun(inner.get("filter", []), default_noun(inner)))
            return "%s中%s的卡" % (self.cards(inner), word)
        if b == "carried":
            if not self.carried_verb:
                return "那些卡"
            return "这个效果%s的%s" % (self.carried_verb, "怪兽" if "召唤" in self.carried_verb else "卡")
        if b == "overlay":
            return "这张卡的超量素材"
        if b == "battle_opp":
            return "和这张卡进行战斗的对方怪兽"
        if b == "deck_top":
            n = one(node, "count_n")
            if n is not None:
                return "%s卡组上面%s的卡" % (dict(PLAYERS)[node["who"]], self.number(n))
            return "%s卡组最上面%d张卡" % (dict(PLAYERS)[node["who"]], node["count"])
        if b == "all":
            return "%s的%s" % (zone(node), filter_noun(node.get("filter", []), default_noun(node)))
        if b == "pick":
            noun = filter_noun(node.get("filter", []), default_noun(node))
            return "%s%s%s" % (zone(node), self.qty(node, noun), noun)
        return "（？）"

    # ------------------------------------------------------------ 数值、条件
    def number(self, node):
        if node is None:
            return "（多少？）"
        b = node["block"]
        if b == "num":
            return str(node["value"])
        if b in ("atk_of", "def_of", "level_of", "base_atk_of", "base_def_of", "text_atk_of", "text_def_of", "scale_of", "attacked_count", "prev_overlay_count"):
            return "%s的%s" % (self.cards(one(node, "card")),
                              {"atk_of": "攻击力", "def_of": "守备力", "level_of": "等级", "base_atk_of": "原本攻击力",
                               "text_atk_of": "卡上记载的攻击力", "text_def_of": "卡上记载的守备力", "scale_of": "灵摆刻度",
                               "attacked_count": "攻击次数", "prev_overlay_count": "在场上时的超量素材数量",
                               "base_def_of": "原本守备力"}[b])
        if b == "battle_damage":
            return "%s受到的战斗伤害" % dict(PLAYERS)[node["player"]]
        if b == "flag_count":
            return "%s的标记%d的数量" % ("这张卡" if node["on"] == "card" else "自己", node["name"])
        if b == "material_count":
            return "这张卡召唤用的素材数量"
        if b == "prev_atk_of":
            return "%s在场上的攻击力" % self.cards(one(node, "card"))
        if b in ("rank_of", "link_of"):
            return "%s的%s" % (self.cards(one(node, "card")), "阶级" if b == "rank_of" else "连接值")
        if b == "turn_count":
            return "这个回合%s%s" % (dict(PLAYERS)[node["player"]], ACT_ZH[node["what"]])
        if b == "chain_count":
            return "连锁数"
        if b == "turn_number":
            return "现在的回合数"
        if b == "declared_num":
            return "宣言的等级"
        if b == "dice_value":
            return "出现的数目"
        if b == "event_value":
            return "那个数值"
        if b == "counter_of":
            return "%s的%s数量" % (self.cards(one(node, "card")), dict(COUNTERS)[node["counter"]])
        if b == "sum_of":
            return "%s的%s合计" % (self.cards(one(node, "cards")), STAT_ZH[node["stat"]])
        if b == "name_kinds":
            return "%s的卡名的种类数" % self.cards(one(node, "cards"))
        if b == "count_of":
            return "%s的数量" % self.cards(one(node, "cards"))
        if b == "lp_of":
            return "%s基本分" % dict(PLAYERS)[node["player"]]
        if b == "math":
            l, r = self.number(one(node, "left")), self.number(one(node, "right"))
            if node["op"] == "*":
                return "%s×%s" % (l, r)
            if node["op"] == "//":
                return "%s的%s分之1" % (l, r) if r.isdigit() else "%s÷%s" % (l, r)
            return "%s%s%s" % (l, node["op"], r)
        return "（？）"

    def amount(self, node):
        """伤害、回复的数值：算出来的数值说「……数值的」（「那只怪兽的攻击力数值的伤害」）。"""
        text = self.number(node)
        if node is None or node["block"] == "num":
            return text
        return text + ("的" if text.endswith("数值") else "数值的")

    def cond(self, node):
        if node is None:
            return "（什么条件？）"
        b = node["block"]
        if b == "compare":
            op = node["op"]
            left, right = self.number(one(node, "left")), self.number(one(node, "right"))
            if op in CMP_WORD:
                return "%s是%s%s" % (left, right, CMP_WORD[op])
            return "%s%s%s" % (left, {"==": "是", "!=": "不是", ">": "比", "<": "比"}[op], right) + \
                {">": "高", "<": "低"}.get(op, "")
        if b == "exists":
            src = one(node, "cards")
            if src and src["block"] == "all":
                return "%s有%s存在" % (zone(src), filter_noun(src.get("filter", []), default_noun(src)))
            return "%s存在" % self.cards(src)
        if b == "turn":
            return "%s回合" % dict(PLAYERS)[node["player"]]
        if b == "phase":
            return PHASE_NAMES[node["phase"]]
        if b == "coin_heads":
            return "硬币是表"
        if b == "coin_right":
            return "猜中"
        if b == "can_chain_attack":
            return "这张卡可以继续攻击"
        if b == "not_sent_this_turn":
            return "不是这张卡送去墓地的回合"
        if b == "player_affected":
            return "%s受到「%s」的效果" % (dict(PLAYERS)[node["player"]], code_zh(node["code"]))
        if b == "can_enter_bp":
            return "这个回合可以进行战斗阶段"
        if b == "can_normal_draw":
            return "自己可以进行通常抽卡"
        if b == "materials_are":
            noun = filter_noun(node.get("filter") or [], "怪兽")
            return ("用%s作为素材召唤" if node["mode"] == "any" else "只用%s作为素材召唤") % noun
        if b == "this_battled":
            return "这张卡在这个回合进行过战斗"
        if b == "this_attacked":
            return "这张卡在这个回合攻击过"
        if b == "gemini_state":
            return "这张卡再度召唤的状态"
        if b == "union_state":
            return "这张卡当作装备卡使用中"
        if b == "chain_is":
            return "那个发动的是%s" % CHAIN_IS_ZH[node["what"]]
        if b == "chain_does":
            return "那个发动的效果是%s效果" % CHAIN_ZH[node["what"]]
        if b == "has_flag":
            return "%s有标记%d" % ("这张卡" if node["on"] == "card" else "自己", node["name"])
        if b == "card_is":
            filters = node.get("filter", [])
            if filters and all(f["block"] == "f_summon_type" for f in filters):   # 「这张卡是同调召唤的」
                return "%s是%s的" % (self.cards(one(node, "cards")),
                                    "·".join(SUMMON_NAMES[f["method"]] for f in filters))
            return "%s是%s" % (self.cards(one(node, "cards")), filter_noun(filters))
        if b in ("all_of", "any_of"):
            items = [self.cond(x) for x in node.get("items", [])]
            return ("并且" if b == "all_of" else "或者").join(items) or "（什么条件？）"
        if b == "not_cond":
            inner = one(node, "item")
            if inner and inner["block"] == "exists":
                src = one(inner, "cards")
                if src and src["block"] == "all":
                    return "%s没有%s存在" % (zone(src), filter_noun(src.get("filter", []), default_noun(src)))
            return "不是「%s」" % self.cond(inner)
        return "（？）"

    # ------------------------------------------------------------ 适用的效果
    def apply(self, subject, code, value, span, against=None, vcards=None):
        """卡片适用效果代码：「这张卡的攻击力直到回合结束时上升500」。vcards：数值只对这样的卡成立。"""
        if vcards:
            activated = any(x["block"] == "f_activated_effect" for x in vcards)
            vcards = [x for x in vcards if x["block"] != "f_activated_effect"]
            noun = filter_noun(vcards) if vcards else "卡"
            if code == "EFFECT_IMMUNE_EFFECT":
                return "%s%s不受%s%s的效果影响" % (subject, span, noun, "发动" if activated else "")
            if code == "EFFECT_INDESTRUCTABLE_EFFECT":
                return "%s%s不会被%s的效果破坏" % (subject, span, noun)
            if code == "EFFECT_CANNOT_BE_EFFECT_TARGET":
                return "%s%s不会成为%s的效果的对象" % (subject, span, noun)
            if code == "EFFECT_EQUIP_LIMIT":
                return "%s只能给%s装备" % (subject, noun)
            return "%s%s适用「%s」（只对%s）" % (subject, span, code_zh(code), noun)
        if against == "opp" and code in PHRASE_OPP:
            return "%s%s%s" % (subject, span, PHRASE_OPP[code])
        if code in STAT:
            prop, up, down = STAT[code]
            if down and value and value["block"] == "num" and value["value"] < 0:
                return "%s%s%s%s%d" % (subject, prop, span, down, -value["value"])
            return "%s%s%s%s%s" % (subject, prop, span, up, self.number(value) if value else "")
        if code in PHRASE:
            return "%s%s%s" % (subject, span, PHRASE[code])
        return "%s%s适用「%s」%s" % (subject, span, code_zh(code), "（数值：%s）" % self.number(value) if value else "")

    def apply_player(self, who, code, filters, value):
        """玩家适用效果代码：「自己不能把怪兽特殊召唤」「对方不是暗属性怪兽不能特殊召唤」。"""
        if code not in PLAYER_READ:
            extra = "（只针对%s）" % filter_noun(filters) if filters else ""
            return "%s适用「%s」%s%s" % (who, code_zh(code), extra, "（数值：%s）" % self.number(value) if value else "")
        tmpl, default = PLAYER_READ[code]
        tmpl = tmpl.replace("{v}", self.number(value) if value else "?")
        if len(filters) == 1 and filters[0]["block"] == "f_not" and "不能把{n}" in tmpl:
            return who + tmpl.replace("不能把{n}", "不是%s不能" % filter_noun(filters[0].get("filter", []), default))
        return who + tmpl.replace("{n}", filter_noun(filters, default) if filters else default)

    # ------------------------------------------------------------ 处理
    def verb(self, st):
        b = st["block"]
        if b == "banish" and st.get("face") == "down":
            return "里侧表示除外"
        if b == "banish" and st.get("temp") == "yes":
            return "除外"
        if b == "to_hand" and st.get("to") == "opp":
            return "加入对方手卡"
        if b == "to_deck" and st.get("seq") == "bottom_order":
            return "用喜欢的顺序回到卡组最下面"
        if b == "to_deck" and st.get("seq") in ("top", "bottom"):
            return "回到卡组%s" % {"top": "最上面", "bottom": "最下面"}[st["seq"]]
        if b == "special_summon":
            how = ("在对方场上" if st.get("to") == "opp" else "") + SS_HOW.get(st.get("position"), "")
            return "%s%s特殊召唤" % ("无视召唤条件" if st.get("ignore") == "yes" else "", how)
        if b == "place":
            return PLACE_VERB[st.get("where") or "szone"]
        return VERB.get(b)

    def act(self, st, src):
        """移动卡片的动作：「对方场上的怪兽全部破坏」「从卡组把1只……加入手卡」「选对方场上1张卡破坏」。"""
        b = st["block"]
        verb = self.verb(st)
        if b == "get_control":
            return "得到%s的控制权" % self.cards(src)
        if b == "change_position":
            return None
        if src and src["block"] == "all":
            return "%s全部%s" % (self.cards(src), verb)
        if src and src["block"] == "pick":
            noun = filter_noun(src.get("filter", []))
            if src["who"] == "you" and all(p in OFF_FIELD_PLACES for p in multi_parts(src["where"], ZONE_ZH)):
                if b == "discard" and src["where"] == "hand":
                    return "选%s%s丢弃" % (self.qty(src, noun), "手卡" if noun == "卡" else noun)
                diff = "卡名不同的" if src.get("different") == "yes" else ""
                return "从%s把%s%s%s%s" % ({"banished": "除外状态"}.get(src["where"], ZONE_ZH[src["where"]]), diff,
                                          self.qty(src, noun), noun, verb)
            return "选%s%s" % (self.cards(src), verb)
        return "%s%s" % (self.cards(src), verb)

    def statement(self, st, rest):
        """一块语句 → (句子, 吃掉了后面几块)。"""
        b = st["block"]
        if b in VERB or b in ("get_control", "place"):
            self.last_verb = self.verb(st)
            return self.act(st, one(st, "cards")), 0
        if b == "delay":
            old = self.carried_verb
            self.carried_verb = self.last_verb if st.get("carry") == "yes" else None
            body = self.statements(st.get("body", [])) or "（做什么？）"
            self.carried_verb = old
            return "%s，%s" % (DELAY_ZH[st["when"]], body), 0
        if b == "fail":
            what = (self.last_verb or "这样做").replace("里侧表示", "").replace("表侧表示", "")
            return "不能%s的场合，%s" % (what, self.statements(st.get("body", [])) or "（做什么？）"), 0
        if b == "announce":
            return "%s宣言1个%s" % (dict(PLAYERS)[st["player"]], ANNOUNCE_ZH[st["what"]]), 0
        if b == "toss_coin":
            return ("猜硬币的里表，进行1次投掷硬币" if st.get("call") == "yes" else "进行1次投掷硬币"), 0
        if b == "toss_dice":
            return "掷1次骰子", 0
        if b == "fusion_summon":
            mats = st.get("mats") or "hf"
            noun = filter_noun(st.get("filter") or [], "融合怪兽")
            noun = noun if noun.endswith("融合怪兽") else noun.replace("怪兽", "") + "融合怪兽"
            extra = "（墓地的怪兽除外）" if mats == "hfg" else ""
            return "自己的%s的怪兽作为融合素材%s，从额外卡组把1只%s融合召唤" % (FUSION_MATS_ZH[mats], extra, noun), 0
        if b == "ritual_summon":
            noun = filter_noun(st.get("filter") or [], "仪式怪兽")
            noun = noun if noun.endswith("仪式怪兽") else noun.replace("怪兽", "") + "仪式怪兽"
            lv = "和仪式召唤的怪兽相同" if st.get("level") == "equal" else "仪式召唤的怪兽的等级以上"
            return "等级合计直到变成%s为止，把自己的手卡·场上的怪兽解放，从%s把1只%s仪式召唤" % (
                lv, RITUAL_FROM_ZH[st.get("from") or "hand"], noun), 0
        if b == "change_position":
            return "%s变成%s" % (self.cards(one(st, "cards")), dict(TO_POSITIONS)[st["to"]]
                                .replace("攻击 ↔ 守备", "相反的表示形式")), 0
        if b == "select":
            src = one(st, "source") or {}
            nxt = rest[0] if rest else None
            # 「让自己选1张……记作A」接「加入手卡 A」：官方说法「从卡组把1只……加入手卡」
            if (nxt and nxt["block"] in VERB and (one(nxt, "cards") or {}).get("block") == "var"
                    and one(nxt, "cards")["name"] == st["as"] and st["player"] == "you" and src.get("block") == "all"):
                noun = filter_noun(src.get("filter", []))
                where = ZONE_ZH[src["where"]] if src["who"] == "you" and src["where"] in ("deck", "hand", "extra", "grave") \
                    else zone(src)
                diff = "卡名不同的" if st.get("different") == "yes" else ""
                q = ("等级合计是%s的" % (self.number(one(st, "sum_n")) if one(st, "sum_n") else st["count"])
                     if st.get("sum") == "level_eq" else self.qty(st, noun))
                return "从%s把%s%s%s%s" % (where, diff, q, noun, self.verb(nxt)), 1
            noun = filter_noun(src.get("filter", []), default_noun(src) if src else "卡")
            if st.get("sum") == "level_eq":
                n = self.number(one(st, "sum_n")) if one(st, "sum_n") else str(st["count"])
                return "%s从%s选等级合计是%s的%s（记作%s）" % (dict(PLAYERS)[st["player"]], zone(src) if src else "（哪里？）",
                                                    n, noun, st["as"]), 0
            return "%s从%s选%s%s（记作%s）" % (dict(PLAYERS)[st["player"]], zone(src) if src else "（哪里？）",
                                         ("卡名不同的" if st.get("different") == "yes" else "") + self.qty(st, noun),
                                         noun, st["as"]), 0
        if b == "draw":
            self.last_verb = "抽卡"
            n = one(st, "count_n")
            if n is not None:
                return "%s从卡组抽%s的卡" % (dict(PLAYERS)[st["player"]], self.number(n)), 0
            return "%s从卡组抽%d张" % (dict(PLAYERS)[st["player"]], st["count"]), 0
        if b == "damage":
            return "给与%s%s伤害" % (dict(PLAYERS)[st["player"]], self.amount(one(st, "amount"))), 0
        if b == "recover":
            return "%s回复%s基本分" % (dict(PLAYERS)[st["player"]], self.amount(one(st, "amount"))), 0
        if b == "pay_lp":
            return "支付%s基本分" % self.number(one(st, "amount")), 0
        if b == "detach":
            who = self.cards(one(st, "cards")) if one(st, "cards") else "这张卡"
            if st.get("all") == "yes":
                return "%s的超量素材全部取除" % who, 0
            return "把%s%s超量素材取除" % (who, self.count_text(st, "个")), 0
        if b == "add_counter":
            return "给%s放置%s%s" % (self.cards(one(st, "cards")), self.count_text(st, "个"), dict(COUNTERS)[st["counter"]]), 0
        if b == "remove_counter":
            return "把%s%s%s取除" % ("场上" if st.get("from") == "field" else "这张卡", self.count_text(st, "个"),
                                    dict(COUNTERS)[st["counter"]]), 0
        if b == "create_token":
            return "在自己场上把%s「%s」（%s·%s·%d星·攻%d/守%d）特殊召唤" % (
                self.count_text(st, "只"), st["name"], RACE_NAMES[st["race"]], ATTR_NAMES[st["attribute"]], st["level"],
                st["atk"], st["def"]), 0
        if b == "negate_activation":
            nxt = rest[0] if rest else None
            body = (nxt or {}).get("body", []) if (nxt or {}).get("block") == "after" else [nxt] if nxt else []
            if len(body) == 1 and body[0] and body[0]["block"] == "destroy" and \
                    (one(body[0], "cards") or {}).get("block") == "chain_card":
                return "那个发动无效并破坏", 1
            return "那个发动无效", 0
        if b == "negate_effect":
            return "那个效果无效", 0
        if b == "negate_attack":
            return "那次攻击无效", 0
        if b == "win":
            return "%s决斗胜利" % dict(PLAYERS)[st["player"]], 0
        if b == "raw":
            return st.get("zh") or "（自定义处理）", 0
        if b == "register":
            return self.apply(self.cards(one(st, "cards")), st["code"], one(st, "value"), SPAN[st["reset"]],
                              st.get("against"), st.get("value_cards")), 0
        if b == "equip":
            return "把%s给%s装备" % (self.cards(one(st, "cards")), self.cards(one(st, "to"))), 0
        if b == "attach":
            to = one(st, "to")
            return "把%s在%s下面重叠作为超量素材" % (self.cards(one(st, "cards")), self.cards(to)), 0
        if b == "return_to_field":
            return "%s回到场上" % self.cards(one(st, "cards")), 0
        if b == "end_battle_phase":
            return "战斗阶段结束", 0
        if b == "skip_phase":
            return "跳过%s的%s" % ("这个回合" if st["player"] == "you" else "对方",
                                {"draw": "抽卡阶段", "standby": "准备阶段", "main1": "主要阶段1", "battle": "战斗阶段",
                                 "main2": "主要阶段2", "end": "结束阶段"}[st["phase"]]), 0
        if b == "to_extra_faceup":
            return "%s表侧加入额外卡组" % self.cards(one(st, "cards")), 0
        if b == "stay_on_field":
            return "这张卡不送去墓地，就那样留在场上", 0
        if b == "give_up_draw":
            return "放弃通常抽卡", 0
        if b == "activate_card":
            return "从%s把1张%s发动" % ({"hand_deck": "手卡·卡组", "deck": "卡组", "hand": "手卡"}[st["where"]],
                                     filter_noun(st.get("filter") or [], "卡")), 0
        if b == "change_chain_target":
            return "那个效果的对象转移为%s" % self.cards(one(st, "cards")), 0
        if b == "change_chain_effect":
            return "那个效果变成「%s」的效果" % (self.statements(st.get("body", [])) or "（做什么？）"), 0
        if b == "keep_target":
            return "", 0                     # 官方文字不写这句：「以那只怪兽为对象」已经说了
        if b == "normal_summon":
            what = filter_noun(st.get("filter") or [], "怪兽")
            return "进行1只%s的召唤" % what, 0
        if b == "extra_summon":
            what = filter_noun(st.get("filter") or [], "怪兽")
            way = {"synchro": "同调召唤", "xyz": "超量召唤", "link": "连接召唤"}[st["method"]]
            return "用自己场上的怪兽作为素材把1只%s%s" % (what, way), 0
        if b == "trap_monster":
            return "这张卡发动后变成%s（%s·%s属性·%d星·攻%d/守%d）在怪兽区域特殊召唤（也当作陷阱卡使用）" % (
                "通常怪兽" if st.get("mtype") == "normal" else "效果怪兽", RACE_NAMES[st["race"]],
                ATTR_NAMES[st["attribute"]], st["level"], st["atk"], st["def"]), 0
        if b == "copy_effects":
            until = "直到回合结束时" if st.get("reset") != "permanent" else ""
            if st.get("name") == "yes":
                return "这张卡%s当作和%s同名卡使用，得到相同效果" % (until, self.cards(one(st, "cards"))), 0
            return "这张卡%s得到和%s相同的效果" % (until, self.cards(one(st, "cards"))), 0
        if b == "sort_deck":
            return "确认%s卡组最上面%d张卡，用喜欢的顺序回到卡组最上面" % (dict(PLAYERS)[st["player"]], st["count"]), 0
        if b == "move_zone":
            return "%s向其他的自己的主要怪兽区域移动" % self.cards(one(st, "cards")), 0
        if b == "change_attack_target":
            target = one(st, "cards")
            return ("攻击对象转移为%s" % self.cards(target) if target else "那次攻击变成直接攻击"), 0
        if b == "calc_damage":
            return "%s和%s进行伤害计算" % (self.cards(one(st, "a")), self.cards(one(st, "b"))), 0
        if b == "chain_attack":
            return "这张卡可以再1次继续攻击", 0
        if b == "confirm_top":
            return "翻开%s卡组最上面%d张卡" % (dict(PLAYERS)[st["player"]], st["count"]), 0
        if b == "shuffle":
            return "%s卡组洗切" % dict(PLAYERS)[st["player"]], 0
        if b == "set_flag":
            return "", 0                  # 标记是给条件用的，卡面上不写
        if b == "set_lp":
            return "%s基本分变成%s" % (dict(PLAYERS)[st["player"]], self.number(one(st, "amount"))), 0
        if b == "reveal":
            return "把%s给对方观看" % self.cards(one(st, "cards")), 0
        if b == "negate_summon":
            nxt = rest[0] if rest else None
            if nxt and nxt["block"] == "destroy" and (one(nxt, "cards") or {}).get("block") == "event_cards":
                return "那次召唤无效，那些怪兽破坏", 1
            return "那次召唤无效", 0
        if b == "each_player":
            body = self.statements(st.get("body", [])) or "（做什么？）"
            return "双方各自" + body.replace("自己", ""), 0
        if b == "register_player":
            return PLAYER_SPAN[st["reset"]] + self.apply_player(WHO_ZH[st["player"]], st["code"], st.get("filter", []),
                                                                one(st, "value")), 0
        if b == "register_zone":
            subject = "%s的%s" % (zone(st), filter_noun(st.get("filter", []), "怪兽" if st["where"] == "mzone" else "卡"))
            return PLAYER_SPAN[st["reset"]] + self.apply(subject, st["code"], one(st, "value"), ""), 0
        if b == "if":
            text = "%s的场合，%s" % (self.cond(one(st, "cond")), self.statements(st.get("then", [])) or "（做什么？）")
            if st.get("else"):
                text += "；不是的场合，%s" % self.statements(st["else"])
            return text, 0
        if b == "after":
            body = self.statements(st.get("body", [])) or "（做什么？）"
            return ("\0" + body if st.get("how") == "and" else "那之后，" + body), 0
        if b == "may":
            return "可以%s" % (self.statements(st.get("body", [])) or "（做什么？）"), 0
        if b == "for_each":
            group = self.cards(one(st, "cards"))
            body = st.get("body", [])
            if len(body) == 1 and body[0]["block"] == "register" and (one(body[0], "cards") or {}).get("block") == "each":
                r = body[0]
                return self.apply(group, r["code"], one(r, "value"), SPAN[r["reset"]] + "各" if r["code"] in STAT
                                  else SPAN[r["reset"]]), 0
            old, self.each = self.each, "那张卡"
            text = "对%s每一张，%s" % (group, self.statements(body) or "（做什么？）")
            self.each = old
            return text, 0
        if b == "choose":
            who = "" if st["player"] == "you" else "对方"
            lines = ["%s从以下效果选择1个适用" % who]
            for op in st.get("options", []):
                lines.append("●%s" % (self.statements(op.get("body", [])) or op.get("text") or "（做什么？）"))
            return "。\n".join(lines), 0
        return "（？）", 0

    def statements(self, stmts):
        parts, i = [], 0
        while i < len(stmts):
            text, eaten = self.statement(stmts[i], stmts[i + 1:])
            for st in stmts[i:i + 1 + eaten]:          # 「让玩家选卡」常和下一步并成一句
                src = one(st, "cards") if st["block"] in VERB else None
                if src and src.get("block") == "var" and self.verb(st):
                    VAR_DONE[src["name"]] = self.verb(st)     # 之后再提到这张卡：「这个效果……的卡」
            if text:
                parts.append(text)
            i += 1 + eaten
        # 「，」接的（做到了才继续、同时处理）跟前一句连成一句
        return "。".join(parts).replace("。\0", "，").replace("\0", "")

    # ------------------------------------------------------------ 发动部分
    def cost(self, st):
        b = st["block"]
        if b in ("pay_lp", "detach", "remove_counter"):
            return self.statement(st, [])[0]
        src = one(st, "cards")
        verb = self.verb(st) or ""
        if src is None:
            return "把（哪些卡？）%s" % verb
        if b == "reveal":
            if src["block"] == "this_card":
                return "把手卡的这张卡给对方观看"
            if src["block"] == "pick":
                noun = filter_noun(src.get("filter", []))
                return "把%s%s%s给对方观看" % ("手卡" if src["where"] == "hand" else zone(src), self.qty(src, noun), noun)
            return "把%s给对方观看" % self.cards(src)
        if src["block"] == "this_card":
            where = getattr(self, "cost_where", None)
            if where and b != "discard":         # 「把墓地的这张卡除外」「把场上·墓地的这张卡除外」
                return "把%s的这张卡%s" % (RANGE_ZH[where], verb)
            return "把这张卡%s%s" % ("从手卡" if b == "discard" else "", verb)
        if src["block"] == "pick":
            noun = filter_noun(src.get("filter", []), default_noun(src))
            if src["where"] == "hand" and src["who"] == "you":
                return "把%s%s%s" % (self.qty(src, noun), "手卡" if noun == "卡" else noun, verb)
            return "把%s%s%s%s" % (zone(src), self.qty(src, noun), noun, verb)
        return "把%s%s" % (self.cards(src), verb)

    def head(self, node):
        """发动部分：「自己主要阶段才能发动」「把1张手卡丢弃，以对方场上1只怪兽为对象才能发动」。"""
        t, ev = node["type"], node.get("event", "free")
        who = {"you": "自己", "opp": "对方"}.get(node.get("event_player"), "")
        parts = []
        # 代价是「把这张卡……」而且不只在场上发动：位置写进代价（「把场上·墓地的这张卡除外才能发动」），不另说「存在的场合」
        rng = node.get("range")
        self_cost = any((one(c, "cards") or {}).get("block") == "this_card" for c in node.get("cost") or [])
        self.cost_where = rng if self_cost and t in ("ignition", "quick_o", "quick_f") and \
            rng not in (None, "mzone", "szone", "fzone", "pzone", "hand") else None
        if node.get("limit") == "card" and not one(node, "twice_when"):
            parts.append("1回合%d次" % max(1, int(node.get("limit_n") or 1)))
        if t in ("ignition", "quick_o") and off_field(node.get("range")) and ev == "free" and not self.cost_where:
            parts.append("这张卡在%s存在的场合" % RANGE_ZH[node["range"]])
        event = self.events_text(events_of(node), who)
        if event and t in ("quick_o", "quick_f"):
            event = event.replace("这张卡进行战斗的", "")
        if event:
            parts.append(event)
        cond_node = one(node, "condition")
        when = self.time_of(cond_node)
        if when:                             # 「对方主要阶段」「对方回合」：时间，不说「……的场合」
            parts.append(when)
        elif cond_node:
            parts.append(self.cond(cond_node) + "的场合")
        stuff = [self.cost(st) for st in node.get("cost", [])]
        t_node = one(node, "target")
        if t_node:
            src = one(t_node, "source")
            noun = filter_noun((src or {}).get("filter", []))
            parts_t = []
            for tn in node.get("target") or []:
                src = one(tn, "source")
                noun = filter_noun((src or {}).get("filter", []), default_noun(src) if src else "卡")
                parts_t.append("%s%d%s%s" % (zone(src) if src else "（哪里？）", tn["count"], measure(noun), noun))
            stuff.append("以%s为对象" % "和".join(parts_t))
        if t == "flip":
            return "，".join(parts + stuff) + ("才能发动。" if stuff else "，" if parts else "")
        # 诱发即时效果：带代价 / 对象时也写「自己·对方回合，把……才能发动」（官方现在的写法）
        quick_time = t in ("quick_o", "quick_f") and not event and not cond_node and \
            not (parts and parts[-1].startswith("这张卡在"))
        if quick_time and stuff:
            parts.append("自己·对方回合")
        if not event and not cond_node and not stuff and not (parts and parts[-1].startswith("这张卡在")):
            if t == "activate":
                return "，".join(parts) + "才能发动。" if parts else ""
            parts.append("自己主要阶段" if t == "ignition" else "自己·对方回合")
        verb = "发动" if t in ("trigger_f", "quick_f") else "才能发动"
        text = "，".join(parts + stuff)
        return text + verb + "。"

    def event_text(self, ev, who, suffix=True):
        if ev not in EVENT_READ:
            return None
        base, tail = EVENT_READ[ev]
        if ev == "draw" and not who:
            who = "双方"
        if base.startswith("{w}受到") and not who:
            who = "自己或者对方"
        if not who:
            base = base.replace("{w}的", "")
        text = base.replace("{w}", who).replace("把怪兽", "把怪兽" if who else "怪兽").lstrip("把")
        return text + (tail if suffix else "")

    def events_text(self, evs, who, suffix=True):
        """几个时机：「这张卡召唤·特殊召唤的场合」「这张卡被送去墓地的场合或者被除外的场合」。"""
        order = [k for k, _ in EVENTS]
        evs = sorted(evs, key=lambda e: order.index(e) if e in order else 99)
        texts = [(self.event_text(e, who, suffix=False), EVENT_READ[e][1]) for e in evs if e in EVENT_READ]
        if not texts:
            return None
        if len(texts) == 1:
            return texts[0][0] + (texts[0][1] if suffix else "")
        bases = [b for b, _ in texts]
        pre = os.path.commonprefix(bases)
        # 官方只在召唤之间用「·」（「这张卡召唤·特殊召唤的场合」）；别的说「……的场合或者……的场合」
        if len({t for _, t in texts}) == 1 and len(pre) >= 2 and                 all(0 < len(b) - len(pre) <= 8 and b.endswith("召唤") for b in bases):
            return pre + "·".join(b[len(pre):] for b in bases) + (texts[0][1] if suffix else "")
        # 后面几句省掉相同的主语（「对方的卡被送去墓地的场合或者被除外的场合」）
        subject = pre[:pre.rfind("被")] if "被" in pre else pre
        out = []
        for i, (b, t) in enumerate(texts):
            if i and len(subject) >= 2 and b.startswith(subject):
                b = b[len(subject):]
            out.append(b + (t if suffix or i < len(texts) - 1 else ""))
        return "或者".join(out)

    def time_of(self, cond):
        """发动条件里表示时间的部分（谁的回合、哪个阶段）→「对方主要阶段」；不是这种条件返回 None。"""
        if cond is None:
            return None
        items = one(cond, "items") and cond["items"] if cond["block"] == "all_of" else [cond]
        if not items or any(x["block"] not in ("turn", "phase") for x in items):
            return None
        who = "".join(dict(PLAYERS)[x["player"]] for x in items if x["block"] == "turn")
        phase = "".join(PHASE_NAMES[x["phase"]] for x in items if x["block"] == "phase")
        return who + (phase or "回合")

    def count_turns(self, node, who):
        """「每次结束阶段做标记，标记到N个就……」→ 官方说法「用对方回合计算的N回合后的对方结束阶段……」。"""
        ops = node.get("operation", [])
        if node.get("event") != "end" or len(ops) != 2 or ops[0]["block"] != "set_flag" or ops[1]["block"] != "if"                 or ops[0].get("reset") != "permanent" or ops[1].get("else"):
            return None
        cond = one(ops[1], "cond")
        if not cond or cond["block"] != "compare" or cond["op"] not in (">=", "=="):
            return None
        left, right = one(cond, "left"), one(cond, "right")
        if not left or left["block"] != "flag_count" or left["on"] != ops[0]["on"] or left["name"] != ops[0]["name"]                 or not right or right["block"] != "num":
            return None
        then = self.statements(ops[1].get("then", []))
        side = who or "双方"
        return "用%s回合计算的%d回合后的%s结束阶段%s。" % (side, right["value"], side, then or "（做什么？）")

    def mode_line(self, mode):
        """发动时选的一个分支：「●以……为对象才能发动。那只怪兽破坏。」"""
        self.target = one(mode, "target")
        self.targets = list(mode.get("target") or [])
        parts = []
        condition = one(mode, "cond")
        if condition:
            parts.append(self.cond(condition) + "的场合")
        names = []
        for tn in mode.get("target") or []:
            src = one(tn, "source")
            noun = filter_noun((src or {}).get("filter", []), default_noun(src) if src else "卡")
            names.append("%s%d%s%s" % (zone(src) if src else "（哪里？）", tn["count"], measure(noun), noun))
        if names:
            parts.append("以%s为对象" % "和".join(names))
        body = self.statements(mode.get("operation", [])) or mode.get("text") or "（做什么？）"
        self.target, self.targets = None, []
        return "●%s%s。" % ("，".join(parts) + "才能发动。" if parts else "", body)

    def modal_effect(self, node):
        head = self.head(dict(node, target=[], operation=[], modes=[]))
        lines = [head[:-len("才能发动。")] + "才能从以下效果选择1个发动。" if head.endswith("才能发动。") else head + "从以下效果选择1个发动。"]
        return "\n".join(lines + [self.mode_line(mode) for mode in node["modes"]])

    def effect(self, node):
        if node.get("modes"):
            return self.modal_effect(node)
        self.cost_where = None
        self.target = one(node, "target")
        self.targets = list(node.get("target") or [])
        body = self.statements(node.get("operation", []))
        if node["type"] == "listener":
            who = {"you": "自己", "opp": "对方"}.get(node.get("event_player"), "")
            later = self.count_turns(node, who)
            if later:
                return later
            ev = self.events_text(events_of(node), who, suffix=False) or "（什么时候？）"
            self.target = None
            return "每次%s，%s。" % (ev, body or "（处理还没放积木）")
        text = self.head(node) + (body + "。" if body else "" if node.get("operation") else "（处理还没放积木）")
        if node.get("chain_limit") == "opp":
            text += "对方不能对应这个效果的发动把卡的效果发动。"
        elif node.get("chain_limit") == "all":
            text += "双方不能对应这个效果的发动把卡的效果发动。"
        elif node.get("chain_limit") == "opp_end":
            text += "这个效果的发动后，直到连锁结束时对方不能把卡的效果发动。"
        if node.get("unstoppable") == "yes":
            text += "这个效果的发动和效果不会被无效化。"
        if node.get("limit") == "card" and one(node, "twice_when"):
            n = max(1, int(node.get("limit_n") or 1))
            text += "这个效果1回合只能使用%d次，%s的场合，1回合可以使用最多%d次。" % (n, self.cond(one(node, "twice_when")), n + 1)
        self.target = None
        self.cost_where = None
        return text

    def summon_lines(self, rules, name):
        """召唤条件、特殊召唤手续、不用解放召唤 → 卡上不编号的几行。"""
        out = []
        rule = next((x for x in rules if x["block"] == "summon_rule"), None)
        nomi = bool(rule and rule.get("normal") == "no")
        head = "这张卡不能通常召唤。" if nomi else ""
        special = (rule or {}).get("special") or "any"
        tail = {"proc_only": "用这张卡的方法才能特殊召唤。", "own_effect": "用这张卡的效果才能特殊召唤。",
                "fusion": "这张卡用融合召唤才能从额外卡组特殊召唤。", "synchro": "这张卡用同调召唤才能从额外卡组特殊召唤。",
                "xyz": "这张卡用超量召唤才能从额外卡组特殊召唤。", "link": "这张卡用连接召唤才能从额外卡组特殊召唤。",
                "ritual": "这张卡用仪式召唤才能特殊召唤。"}.get(special, "")
        if special == "by_cards":
            tail = "用%s的效果才能特殊召唤。" % filter_noun(rule.get("by") or [])
        procs = [x for x in rules if x["block"] == "sp_proc"]
        for p in procs:
            where = RANGE_ZH[p.get("range") or "hand"]
            cond = one(p, "condition")
            costs = [self.cost(st) for st in p.get("cost") or []]
            pos = "守备表示" if p.get("position") == "defense" else ""
            if nomi:              # 「把……除外的场合才能从墓地特殊召唤」
                parts = ([self.cond(cond) + "的场合"] if cond else []) + (["，".join(costs) + "的场合"] if costs else [])
                text = "，".join(parts) + ("才能从%s%s特殊召唤。" % (where, pos) if parts else "可以从%s%s特殊召唤。" % (where, pos))
            else:                 # 「自己场上没有怪兽存在的场合，这张卡可以从手卡特殊召唤」
                text = ("%s的场合，" % self.cond(cond) if cond else "") + "这张卡可以" + \
                    ("，".join(costs) + "，" if costs else "") + "从%s%s特殊召唤。" % (where, pos)
            head += text
            if p.get("limit") == "once":
                head += "「%s」的方法的特殊召唤1回合只能有1次。" % (name or "这张卡")
        if not (special == "proc_only" and procs):      # 有召唤手续时「用这张卡的方法」就是上面那句
            head += tail
        if head:
            out.append(head)
        for p in (x for x in rules if x["block"] == "ns_proc"):
            cond = one(p, "condition")
            if int(p.get("tribute") or 0) > 0:
                out.append(("%s的场合，" % self.cond(cond) if cond else "") + "这张卡可以把%s%d只怪兽解放作召唤。" % (
                    "自己或者对方场上的" if p.get("opp") == "yes" else "", int(p["tribute"])))
            else:
                out.append(("%s的场合，" % self.cond(cond) if cond else "") + "这张卡可以不用解放作召唤。")
        return out

    def continuous(self, node):
        mode, code, value = node["mode"], node["code"], one(node, "value")
        filters = node.get("filter", [])
        against = node.get("against")
        if mode == "equipped":
            cond_node = one(node, "condition")
            pre = "%s的场合，" % self.cond(cond_node) if cond_node else ""
            return pre + self.apply("装备怪兽", code, value, "", against) + "。"
        if mode == "self":
            body = self.apply("这张卡", code, value, "", against, node.get("value_cards"))
        elif mode == "card_target":
            body = self.apply("那只怪兽", code, value, "", against)
        elif mode == "zone":
            default = "怪兽" if node["where"] == "mzone" else "卡"
            body = self.apply("%s的%s" % (zone(node), filter_noun(filters, default)), code, value, "", against)
        else:
            body = self.apply_player(WHO_ZH[node["player"]], code, filters, value)
        cond_node = one(node, "condition")
        pre = "%s的场合，" % self.cond(cond_node) if cond_node else ""
        if mode == "self" and node["range"] == "mzone":
            return pre + body + "。"
        return "只要这张卡在%s存在，%s%s。" % (RANGE_ZH[node["range"]], pre, body)


def walk_nodes(node):
    """一个积木和它所有槽里的积木。"""
    yield node
    for v in node.values():
        if isinstance(v, list):
            for x in v:
                if isinstance(x, dict) and "block" in x:
                    yield from walk_nodes(x)


def part_text(effects, name=""):
    """一栏（怪兽效果 / 灵摆效果）的中文：每个效果一句，带①②编号；「这个卡名的……1回合只能使用1次」放在最前面。"""
    r = Reader()
    lines = []
    # 编号：反转效果写「反转：」，不占编号
    marks, n = [], 0
    for e in effects:
        if e["block"] == "effect" and e["type"] == "flip":
            marks.append("反转")
        elif e["block"] in ("unique", "summon_rule", "sp_proc", "ns_proc", "fusion_materials", "extra_materials", "destroy_replace", "monster_trait", "name_as", "target_link"):
            marks.append("")
        else:
            marks.append(CIRCLED[n] if n < len(CIRCLED) else str(n + 1))
            n += 1
    numbered_count = n

    def which(kind):
        return [i for i, e in enumerate(effects) if e.get("limit") == kind]

    def label(idx):
        return "".join(marks[i] for i in idx)
    one_effect = sum(1 for e in effects
                     if e["block"] not in ("unique", "summon_rule", "sp_proc", "ns_proc", "fusion_materials", "extra_materials", "destroy_replace", "monster_trait", "name_as", "target_link")) == 1
    if which("activate_card"):
        lines.append("这个卡名的卡在1回合只能发动1张。")
    named = which("name")
    if named:
        if one_effect:
            lines.append("这个卡名的效果1回合只能使用1次。")
        elif len(named) == 1:
            lines.append("这个卡名的%s的效果1回合只能使用1次。" % label(named))
        else:
            lines.append("这个卡名的%s的效果1回合各能使用1次。" % label(named))
    shared = which("name_shared")
    if shared:
        lines.append("这个卡名的%s的效果1回合只能有1次使用其中任意1个。" % label(shared) if len(shared) > 1 else
                     "这个卡名的%s的效果1回合只能使用1次。" % ("" if one_effect else label(shared)).replace("的的", "的"))
    single = which("card_shared")
    if single:
        lines.append("这张卡的%s的效果1回合只能有1次使用其中任意1个。" % label(single))
    in_chain = which("chain")
    if lines:                                  # 「1回合2次」：把上面几行里的「1次 / 1张」换成几次
        times = max([max(1, int(e.get("limit_n") or 1)) for e in effects
                     if e.get("limit") in ("name", "name_shared", "activate_card", "card_shared")] or [1])
        if times > 1:
            lines = [x.replace("只能使用1次", "能使用%d次" % times).replace("各能使用1次", "各能使用%d次" % times)
                     .replace("只能发动1张", "能发动%d张" % times).replace("只能有1次", "能有%d次" % times) for x in lines]
    if in_chain:
        lines.append("这个卡名的%s的效果在同一连锁上只能发动1次。" % ("" if one_effect else label(in_chain)).replace("的的", "的"))
    duel = which("duel")
    duel_n = max([max(1, int(effects[i].get("limit_n") or 1)) for i in duel] or [1])
    if duel and duel_n > 1:
        lines.append("这个卡名的%s的效果在决斗中能使用%d次。" % ("" if one_effect else label(duel), duel_n))
    elif duel:
        lines.append(("这个卡名的效果在决斗中只能使用1次。" if one_effect else
                      "这个卡名的%s的效果在决斗中只能使用1次。" % label(duel)))
    for e in effects:
        if e["block"] == "extra_materials":      # 同调 / 超量 / 连接素材：卡上第一行
            n, more = max(1, int(e.get("count") or 1)), e.get("more") == "yes"
            mat = filter_noun(e.get("material") or [], "怪兽")
            if e.get("method") == "synchro":
                tuner = filter_noun(e.get("tuner") or [], "调整") if e.get("tuner") else "调整"
                if e.get("tuner") and not tuner.endswith("调整"):
                    tuner += "调整"
                lines.append("%s%s＋调整以外的%s%d只%s" % (tuner, "2只" if e.get("tuners") == "two" else "", mat, n,
                                                       "以上" if more else ""))
            elif e.get("method") == "xyz":
                rank = int(e.get("rank") or 4)
                noun = "%d星怪兽" % rank if mat == "怪兽" else mat.replace("怪兽", "%d星怪兽" % rank)
                lines.append("%s×%d%s" % (noun, n, "以上" if more else ""))
                if e.get("alter"):
                    lines.append("这张卡也能在自己场上的%s上面重叠来超量召唤。" % filter_noun(e["alter"], "怪兽"))
            else:
                inc = "包含%s的" % filter_noun(e["include"], "怪兽") if e.get("include") else ""
                lines.append("%s%s%d只%s" % (inc, mat, n, "以上" if more else ""))
        if e["block"] == "fusion_materials":     # 融合素材：卡上第一行
            second = filter_noun(e.get("second") or [], "怪兽")
            n, more = max(1, int(e.get("count") or 1)), e.get("more") == "yes"
            tail = "%s%d只以上" % (second, n) if more else (second if n == 1 else "%s×%d" % (second, n))
            if e.get("third") and e.get("first"):
                lines.append("%s＋%s＋%s" % (filter_noun(e["first"], "怪兽"), second, filter_noun(e["third"], "怪兽")))
            else:
                lines.append(("%s＋%s" % (filter_noun(e["first"], "怪兽"), tail)) if e.get("first") else tail)
            if e.get("contact"):
                lines.append("这张卡用以下方法才能从额外卡组特殊召唤。")
                lines.append("●把自己场上的上记的卡%s的场合可以从额外卡组特殊召唤（不需要「融合」）。" % {
                    "deck": "回到持有者卡组", "grave": "送去墓地", "banish": "除外"}[e["contact"]])
    rules = [e for e in effects if e["block"] in ("summon_rule", "sp_proc", "ns_proc")]
    # 和对象怪兽的关系：接在「这张卡以那只怪兽作为对象」的那个效果后面（没有的话单独一行）
    link_text = "".join({"leave_destroy": "这张卡从场上离开时那只怪兽破坏。", "target_destroyed": "那只怪兽被破坏时这张卡破坏。",
                         "target_leave": "那只怪兽从场上离开时这张卡破坏。"}[e["link"]] for e in effects if e["block"] == "target_link")
    holder = next((i for i, e in enumerate(effects) if e["block"] == "effect" and
                   any(x.get("block") == "keep_target" for x in walk_nodes(e))), None)
    if link_text and holder is None:
        lines.append(link_text)
    for e in effects:
        if e["block"] == "name_as":              # 卡名当作……：不编号
            if e.get("where") == "all":
                lines.append("这张卡的卡名在规则上当作「%s」使用。" % (e.get("name") or e["code"]))
                continue
            where = {"": "场上", "field_grave": "场上·墓地", "hand_field_grave": "手卡·场上·墓地"}[e.get("where") or ""]
            lines.append("这张卡的卡名只要在%s存在当作「%s」使用。" % (where, e.get("name") or e["code"]))
        if e["block"] == "monster_trait":        # 灵魂 / 二重 / 同盟：规则文字，不编号
            t = e["trait"]
            if t == "spirit":
                lines.append("这张卡召唤·反转的回合的结束阶段发动。这张卡回到持有者手卡。")
            elif t == "gemini":
                lines.append("这张卡在场上·墓地存在的场合，当作通常怪兽使用。场上的表侧表示的这张卡可以作为通常召唤"
                             "再1次召唤，那个场合这张卡变成当作效果怪兽使用并得到以下效果。")
            else:
                lines.append("1回合1次，可以把这张卡当作装备卡使用给自己场上的%s装备，或者把装备状态的这张卡"
                             "表侧攻击表示特殊召唤。装备怪兽被战斗·效果破坏的场合，作为代替把这张卡破坏。"
                             % filter_noun(e.get("filter") or [], "怪兽"))
    for e in effects:
        if e["block"] == "destroy_replace":      # 代替破坏：不编号的一行
            who = "这张卡" if e.get("mode") != "others" else \
                "自己场上的%s" % filter_noun(e.get("protect") or [], "卡")
            costs = "，".join(r.cost(st) for st in e.get("cost") or []) or "（做什么？）"
            lines.append("%s%s被战斗·效果破坏的场合，可以作为代替%s。" % ("1回合1次，" if e.get("limit") == "card" else "", who, costs))
    if rules:                                # 召唤条件、召唤手续：不编号，放在最前面
        lines += r.summon_lines(rules, name)
    for e in effects:
        if e["block"] == "unique":            # 「场上只能有1张」：不编号，放在最前面
            lines.insert(0, "「%s」在%s只能有1张表侧表示存在。" % (name or "这张卡", "自己场上" if e.get("who") != "both" else "场上"))
    for i, e in enumerate(effects):
        if e["block"] in ("unique", "summon_rule", "sp_proc", "ns_proc", "fusion_materials", "extra_materials", "destroy_replace", "monster_trait", "name_as", "target_link"):
            continue
        if e["block"] == "custom_effect":
            text = e.get("zh") or "（自定义效果）"
        else:
            text = r.effect(e) if e["block"] == "effect" else r.continuous(e)
        if i == holder:
            text += link_text
        if marks[i] == "反转":
            lines.append("反转：" + text)
            continue
        if e["block"] == "custom_effect":       # 中文是写的人给的：卡的发动不编号，自己写了编号也不重复
            numbered = numbered_count > 1 or "EFFECT_TYPE_ACTIVATE" not in str(e.get("lua"))
            numbered = numbered and not text.startswith(tuple(CIRCLED))
        else:
            numbered = numbered_count > 1 or e["block"] != "effect" or e["type"] != "activate"
        lines.append("%s：%s" % (marks[i], text) if numbered else text)
    return "\n".join(lines)


def summon_text(card):
    """召唤手续、出场限制那几行（不编号，在效果前面）：用 Effect Model v0.2 的读法。"""
    if not card.get("summon") or "card" not in card:
        return ""
    from effect_model import zh
    from .compile import v02_shell
    try:
        return zh.render(v02_shell(card))["desc"]
    except Exception:            # 召唤手续写得不完整：只是不显示这几行
        return ""


def read_full(card):
    """→ (效果文字, 灵摆效果文字)。"""
    VAR_DONE.clear()
    effects = card.get("effects", [])
    head = summon_text(card)
    name = (card.get("card") or {}).get("name", "")
    desc = part_text([e for e in effects if e.get("part") != "pendulum"], name)
    return ("\n".join(x for x in (head, desc) if x),
            part_text([e for e in effects if e.get("part") == "pendulum"], name))


def read_card(card):
    """整张卡的中文（灵摆卡的灵摆效果另见 read_full）。"""
    return read_full(card)[0]
