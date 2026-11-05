"""v0.2 的结构常量与词汇。

词汇键 = 调研构件 id 去掉大类前缀（act.destroy → "destroy"），完整条目见 effect_model/research/构件词典.json；
这里只列结构上要用的固定值。生成器已经支持哪些词，以 zh.py / lua.py 为准。
"""

import functools
import json
import os

SCHEMA = "ygodiy-effect/0.2"
SCHEMA_V01 = "ygodiy-effect/0.1"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

EFFECT_TYPES = (
    "activation",   # 魔法·陷阱卡的发动
    "ignition",     # 起动效果
    "trigger",      # 诱发效果
    "quick",        # 诱发即时效果
    "flip",         # 反转效果
    "continuous",   # 永续效果，或不入连锁的「每次……，……」（带 on + do）
    "procedure",    # 编号的特殊召唤手续「这张卡可以……从手卡特殊召唤」；不编号的手续放 summon.procedures
)
BLOCKS = ("monster", "pendulum")
LOCATIONS = ("hand", "mzone", "szone", "fzone", "field", "pzone", "grave", "deck", "banished", "extra", "linked")
PLAYERS = ("you", "opp", "both")
TIMINGS = ("when", "if")

# 处理之间的连接：依赖前项成功 × 与前项同时
LINKS = {
    "and_if_you_do": (True, True),     # 「，」「并」
    "then": (True, False),             # 「。那之后，」
    "also": (False, True),             # 「。」（默认）
    "also_after_that": (False, False),
    "and": ("mutual", True),
}

LIMIT_SCOPES = ("card", "name", "face_up")
LIMIT_UNITS = ("use", "activate_card", "procedure", "special_summon")
LIMIT_PERS = ("turn", "duel", "chain")          # 也可以是 {"phase": ...}
# this_turn：「这个回合，……」写在处理里（和 after_resolution 一样在处理时登记，只是说法不同）
RESTRICT_SPANS = ("whole_turn", "after_resolution", "this_turn", "while_applied")
# 自肃（restrict）：被限制的人与行为（任务 7 的自肃调研：特殊召唤类占核心条款三成以上）
RESTRICT_WHO = ("you", "both", "self")         # self：这张卡本身（「这张卡不能攻击」）
# attack / direct_attack：who 是 self 时限制这张卡，是 you / both 时限制那些玩家的怪兽
RESTRICT_FORBID = ("special_summon", "summon", "flip_summon", "normal_summon", "battle_phase", "attack", "direct_attack",
                   "activate", "set", "draw_by_effect", "search", "material", "half_battle_damage")
RESTRICT_UNTIL = ("end_of_turn", "end_of_next_turn")
RESTRICT_FROM = ("hand", "deck", "extra", "grave", "banished")      # 「不能从卡组·额外卡组把怪兽特殊召唤」
RESTRICT_KINDS = {"activate": ("monster", "spell_trap", "card", "spell"), "set": ("card", "spell_trap")}
RESTRICT_METHODS = ("fusion", "synchro", "xyz", "link")              # 「不能作为连接素材」
# 整回合（「这张卡发动的回合」）要查本回合做过没有，引擎有活动记录的才写得出
RESTRICT_WHOLE_TURN = ("special_summon", "summon", "flip_summon", "normal_summon", "battle_phase", "attack", "activate")
RESTRICT_FORBID_ZH = {"special_summon": "特殊召唤", "summon": "召唤", "flip_summon": "反转召唤", "normal_summon": "通常召唤",
                      "battle_phase": "进行战斗阶段", "attack": "攻击", "direct_attack": "直接攻击", "activate": "发动",
                      "set": "盖放", "draw_by_effect": "用卡的效果抽卡", "search": "从卡组加入手卡",
                      "material": "作为素材", "half_battle_damage": "战斗伤害变成一半"}
DURATIONS = ("end_of_turn", "end_phase", "end_of_next_turn", "permanent")   # 也可以是期限对象

# 只属于模型、调研清单里没有的结构
MODEL_ONLY = {
    "act": {"select", "branch", "one_of", "raw", "activate_from_deck"},   # activate_from_deck：清单外的新发现
    "cond": {"raw", "all", "any", "not"},
    "event": set(),
    "cont": set(),
}

# 引用里的固定名字；其余是对象 / 宣言 / 步骤的 as，或「效果id.绑定名」
BUILTIN_REFS = {"self", "chain", "chain.card", "event", "battle.you", "battle.opp", "materials", "overlay"}


@functools.lru_cache(maxsize=None)
def known_keys(category):
    """调研构件词典里某一大类的全部键（去掉前缀），加上模型自己的结构。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "构件清单.json")
    try:
        with open(path, encoding="utf-8") as f:
            ids = [x["id"] for x in json.load(f)]
    except OSError:
        return None
    if category == "cont":     # 任务 7 的永续细分类（沿用任务 2 的 78 个 id，另补 36 个）
        try:
            with open(os.path.join(os.path.dirname(path), "永续细分类词典.json"), encoding="utf-8") as f:
                ids += [x["id"] for x in json.load(f)]
        except OSError:
            pass
    keys = {i.split(".", 1)[1] for i in ids if i.split(".", 1)[0] == category}
    if category == "act":   # 代价也用动作的名字
        keys |= {i.split(".", 1)[1] for i in ids if i.startswith("cost.")}
    return frozenset(keys | MODEL_ONLY.get(category, set()))
