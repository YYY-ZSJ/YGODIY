"""v0.3 积木目录：每种积木的类型（决定能放在哪）、选项、槽，以及在列表里显示的一行字。

积木树存成 JSON：{"block": 积木名, 选项…, 槽名: [子积木…]}。槽里放的积木类型由槽规定：
    hat      效果（帽子块），一张卡的最外层：会发动的效果、永续效果
    stmt     语句：动作、登记效果、控制（如果、对每一张……）
    cards    卡片组（圆角）
    number   数值
    cond     条件（是 / 否）
    filter   卡片条件（「4星以下」「战士族」：判断某一张卡）
    target   取对象（只能放在效果的「对象」槽）
    option   ●选项（只能放在「让玩家选一个」里）
槽还可以只收某几种积木（代价槽只收能当代价的动作）。
"""

import functools
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

PLAYERS = [("you", "自己"), ("opp", "对方")]
WHO = [("you", "自己"), ("opp", "对方"), ("both", "双方")]
ANY_PLAYER = [("any", "双方")] + PLAYERS
# 区域、位置、种族、属性、卡种……都可以勾好几个（多选字段，值用「+」连起来，如 hand+grave）。
# 旧存档里的 hand_grave 这种（下划线连的地方）照样认得。
ZONES = [("mzone", "怪兽区"), ("field", "场上"), ("szone", "魔法与陷阱区域"), ("hand", "手卡"), ("deck", "卡组"),
         ("grave", "墓地"), ("banished", "除外状态"), ("extra", "额外卡组"), ("pzone", "灵摆区域"), ("fzone", "场地区域")]
# 永续效果、「让一片区域的卡适用效果」能管的区域（场上以外也行：「双方不能从卡组把卡送去墓地」）
FIELD_ZONES = [("mzone", "怪兽区"), ("szone", "魔法与陷阱区域"), ("field", "场上"), ("hand", "手卡"), ("deck", "卡组"),
               ("grave", "墓地"), ("banished", "除外状态")]
RACES = [("warrior", "战士族"), ("spellcaster", "魔法师族"), ("fairy", "天使族"), ("fiend", "恶魔族"), ("zombie", "不死族"),
         ("machine", "机械族"), ("aqua", "水族"), ("pyro", "炎族"), ("rock", "岩石族"), ("winged_beast", "鸟兽族"),
         ("plant", "植物族"), ("insect", "昆虫族"), ("thunder", "雷族"), ("dragon", "龙族"), ("beast", "兽族"),
         ("beast_warrior", "兽战士族"), ("dinosaur", "恐龙族"), ("fish", "鱼族"), ("sea_serpent", "海龙族"),
         ("reptile", "爬虫类族"), ("psychic", "念动力族"), ("divine", "幻神兽族"), ("wyrm", "幻龙族"),
         ("cyberse", "电子界族"), ("illusion", "幻想魔族")]
ATTRIBUTES = [("light", "光"), ("dark", "暗"), ("earth", "地"), ("water", "水"), ("fire", "炎"), ("wind", "风"),
              ("divine", "神")]
KINDS = [("monster", "怪兽"), ("spell", "魔法卡"), ("trap", "陷阱卡")]
SUBTYPES = [("normal", "通常"), ("effect", "效果"), ("tuner", "调整"), ("fusion", "融合"), ("synchro", "同调"),
            ("xyz", "超量"), ("link", "连接"), ("ritual", "仪式"), ("pendulum", "灵摆"), ("quick", "速攻"),
            ("continuous", "永续"), ("equip", "装备"), ("field", "场地"), ("counter", "反击"),
            ("token", "衍生物"), ("flip", "反转"), ("trapmonster", "陷阱怪兽"), ("spirit", "灵魂"), ("gemini", "二重"), ("union", "同盟"), ("toon", "卡通")]
POSITIONS = [("faceup", "表侧表示"), ("facedown", "里侧表示"), ("attack", "攻击表示"), ("defense", "守备表示")]
TO_POSITIONS = [("attack", "表侧攻击表示"), ("defense", "表侧守备表示"), ("facedown", "里侧守备表示"),
                ("swap", "攻击 ↔ 守备")]
CMPS = [(">=", "≥"), ("<=", "≤"), ("==", "="), (">", ">"), ("<", "<"), ("!=", "≠")]
EFFECT_TYPES = [("activate", "魔法·陷阱卡的发动"), ("ignition", "起动效果"), ("trigger_o", "诱发效果（可以选择发动）"),
                ("trigger_f", "诱发效果（必须发动）"), ("quick_o", "诱发即时效果"), ("quick_f", "诱发即时效果（必须发动）"),
                ("flip", "反转效果"),
                ("listener", "每次……（不入连锁）")]
EVENTS = [("free", "（没有，自由时点）"), ("summon", "这张卡召唤成功"), ("spsummon", "这张卡特殊召唤成功"),
          ("summon_both", "这张卡召唤·特殊召唤成功"),
          ("to_grave", "这张卡被送去墓地"), ("destroyed", "这张卡被破坏"), ("draw", "抽卡"),
          ("attack", "攻击宣言"), ("chaining", "卡或效果发动"), ("standby", "准备阶段"), ("end", "结束阶段"),
          ("be_attacked", "这张卡被选为攻击对象"), ("battle_end", "战斗阶段结束"),
          ("battle_destroyed", "这张卡被战斗破坏"), ("effect_destroyed", "这张卡被效果破坏"),
          ("battle_destroying", "这张卡战斗破坏对方怪兽"), ("leave_field", "这张卡从场上离开"),
          ("field_to_grave", "这张卡从场上送去墓地"), ("banished", "这张卡被除外"), ("released", "这张卡被解放"),
          ("to_hand", "这张卡加入手卡"), ("flip_summon", "这张卡反转召唤成功"), ("flip", "这张卡反转"), ("be_material", "这张卡作为素材"),
          ("battle_damage", "这张卡给与对方战斗伤害"), ("be_targeted", "这张卡成为效果的对象"),
          ("monster_summoned", "怪兽召唤成功"), ("monster_spsummoned", "怪兽特殊召唤成功"),
          ("summon_attempt", "怪兽要被召唤之际"), ("spsummon_attempt", "怪兽要被特殊召唤之际"),
          ("battle_start", "这张卡进行战斗的伤害步骤开始时"), ("pre_damage_calc", "这张卡进行战斗的伤害计算前"),
          ("battle_confirm", "这张卡进行战斗的伤害步骤开始后（翻开里侧之后）"),
          ("battled", "这张卡进行战斗的伤害计算后"), ("damage_step_end", "这张卡进行战斗的伤害步骤结束时"),
          ("monster_summoned_both", "怪兽召唤·特殊召唤成功"), ("player_battle_damaged", "玩家受到战斗伤害"),
          ("player_damaged", "玩家受到伤害（战斗·效果）"), ("equip_battle_damage", "装备怪兽给与对方战斗伤害"),
          ("cards_to_grave", "卡被送去墓地"), ("cards_banished", "卡被除外"), ("cards_destroyed", "卡被破坏"),
          ("cards_to_hand", "卡加入手卡"), ("cards_to_deck", "卡回到卡组"), ("cards_leave_field", "卡从场上离开"),
          ("monster_battle_destroyed", "怪兽被战斗破坏"), ("monster_battle_start", "怪兽进行战斗的伤害步骤开始时"),
          ("monster_damage_step_end", "怪兽进行战斗的伤害步骤结束时"),
          ("chain_solved", "卡或效果的处理完了"), ("chain_negated", "卡或效果的发动被无效"), ("chain_end", "连锁全部处理完"),
          ("bp_start", "战斗阶段开始时"), ("cards_set", "魔法·陷阱卡被盖放"), ("monsters_set", "怪兽被里侧盖放"),
          ("pos_changed", "表示形式变更"), ("detached", "超量素材被取除"), ("recovered", "回复基本分"),
          ("equipped", "装备卡被装备"), ("leaving", "这张卡要从场上离开（配合「每次……」）"), ("cards_moved", "卡移动"),
          ("predraw", "抽卡阶段的通常抽卡前")]
CHAIN_KINDS = [("monster", "怪兽的效果"), ("spell", "魔法卡（的效果）"), ("trap", "陷阱卡（的效果）"),
               ("activation", "魔法·陷阱卡的发动"), ("from_hand", "在手卡发动的"), ("from_grave", "在墓地发动的"),
               ("from_field", "在场上发动的")]
# 时机里「谁的」有意义的那些（抽卡、攻击、发动、阶段、怪兽召唤……）
PLAYER_EVENTS = ("draw", "attack", "chaining", "standby", "end", "battle_end", "be_targeted", "monster_summoned",
                 "monster_spsummoned", "summon_attempt", "spsummon_attempt", "monster_summoned_both",
                 "player_battle_damaged", "player_damaged", "cards_to_grave", "cards_banished", "cards_destroyed",
                 "cards_to_hand", "cards_to_deck", "cards_leave_field", "monster_battle_destroyed", "monster_battle_start",
                 "monster_damage_step_end", "chain_solved", "chain_negated", "bp_start", "cards_set", "monsters_set",
                 "pos_changed", "detached", "recovered", "equipped", "cards_moved", "predraw")
# 发动 / 适用的位置：可以勾好几个（「这张卡在手卡·墓地存在的场合」「把场上·墓地的这张卡除外才能发动」）
RANGES = [("mzone", "怪兽区"), ("szone", "魔法与陷阱区域"), ("fzone", "场地区域"), ("pzone", "灵摆区域"),
          ("hand", "手卡"), ("grave", "墓地"), ("banished", "除外状态")]
LIMITS = [("", "不限次数"), ("card", "这张卡1回合1次"), ("name", "这个卡名1回合1次"),
          ("name_shared", "这个卡名的这几个效果1回合只能用其中1个"), ("activate_card", "这个卡名的卡1回合只能发动1张"),
          ("chain", "同一连锁上只能发动1次"), ("card_shared", "这张卡的这几个效果1回合只能用其中1个"),
          ("duel", "这个卡名的效果1场决斗只能用1次")]
DAMAGE_STEP = [("", "不能在伤害步骤发动"), ("yes", "伤害步骤也能发动"), ("calc", "伤害计算时也能发动")]
SS_POSITIONS = [("faceup", "表侧表示（自己选攻守）"), ("attack", "表侧攻击表示"), ("defense", "表侧守备表示"),
                ("facedown", "里侧守备表示")]
DIFFERENT = [("", "卡名可以相同"), ("yes", "卡名各不相同")]
PLACE_ZONES = [("szone", "魔法与陷阱区域"), ("fzone", "场地区域"), ("pzone", "灵摆区域")]
FUSION_MATS = [("hf", "手卡·场上"), ("hfg", "手卡·场上·墓地（墓地的除外）"), ("hfd", "手卡·场上·卡组"),
               ("hand", "手卡"), ("field", "场上")]
RITUAL_LEVELS = [("greater", "等级合计在仪式怪兽的等级以上"), ("equal", "等级合计和仪式怪兽的等级相同")]
RITUAL_FROM = [("hand", "手卡"), ("hand_grave", "手卡·墓地"), ("hand_deck", "手卡·卡组")]
FLAG_ON = [("card", "这张卡"), ("player", "自己（玩家）")]
FLAG_RESETS = [("end_of_turn", "到回合结束"), ("permanent", "一直（卡离场前 / 整场决斗）")]
STATS = [("atk", "攻击力"), ("def", "守备力"), ("level", "等级")]
UNIQUE_SIDES = [("you", "自己场上"), ("both", "双方场上")]
SS_RULES = [("any", "不限"), ("proc_only", "只能用这张卡的召唤手续"), ("own_effect", "只能用这张卡自己的效果"),
            ("by_cards", "只能用这样的卡的效果（下面的槽）"), ("fusion", "只能融合召唤"), ("synchro", "只能同调召唤"),
            ("xyz", "只能超量召唤"), ("link", "只能连接召唤"), ("ritual", "只能仪式召唤")]
PROC_RANGES = [("hand", "手卡"), ("grave", "墓地"), ("banished", "除外状态"), ("deck", "卡组")]
DELAY_WHEN = [("this_end", "这个回合的结束阶段"), ("next_standby", "下次的自己准备阶段"), ("next_end", "下个回合的结束阶段")]
ACTIVITIES = [("draw", "抽卡的张数"), ("spsummon", "特殊召唤的次数"), ("summon", "召唤的次数"), ("attack", "攻击的次数"),
              ("chain", "发动卡和效果的次数")]
ANNOUNCE = [("attribute", "属性"), ("race", "种族"), ("type", "卡的种类（怪兽·魔法·陷阱）"), ("level", "等级（1～12）"),
            ("card", "卡名"), ("number", "数字（1～12）"), ("race_or_attr", "种族或者属性（先选宣言哪个）")]
FACES = [("up", "表侧表示"), ("down", "里侧表示")]
UPTO = [("", "正好这么多"), ("yes", "最多这么多（至少1张）")]
DECK_SEQ = [("shuffle", "洗进卡组"), ("top", "卡组最上面"), ("bottom", "卡组最下面"), ("bottom_order", "卡组最下面（按喜欢的顺序）")]
AGAINST = [("any", "所有效果"), ("opp", "只对对方的效果")]
SUMMON_METHODS = [("special", "特殊召唤"), ("advance", "上级召唤"), ("fusion", "融合召唤"), ("synchro", "同调召唤"),
                  ("xyz", "超量召唤"), ("link", "连接召唤"), ("ritual", "仪式召唤"), ("pendulum", "灵摆召唤")]
REASONS = [("battle", "战斗"), ("effect", "效果"), ("cost", "代价"), ("material", "作为素材"), ("release", "解放"),
           ("discard", "丢弃"), ("destroy", "破坏"), ("fusion", "作为融合素材"), ("synchro", "作为同调素材"),
           ("xyz", "作为超量素材"), ("link", "作为连接素材"), ("return", "被效果回到手卡·卡组"), ("reveal", "被翻开"),
           ("draw", "抽卡")]
PHASES = [("main", "主要阶段"), ("main1", "主要阶段1"), ("main2", "主要阶段2"), ("battle", "战斗阶段"),
          ("standby", "准备阶段"), ("end", "结束阶段"), ("draw", "抽卡阶段"), ("battle_step", "战斗步骤"),
          ("damage", "伤害步骤"), ("damage_calc", "伤害计算时")]
PARTS = [("monster", "怪兽效果 / 魔陷效果"), ("pendulum", "灵摆效果")]
RESETS = [("permanent", "一直（离场前）"), ("end_of_turn", "到回合结束"), ("end_of_next_turn", "到下个回合结束"),
          ("next_standby", "到下次的自己准备阶段"), ("opp_turn_end", "到对方回合结束")]
PLAYER_RESETS = [("end_of_turn", "到回合结束"), ("end_of_next_turn", "到下个回合结束"), ("permanent", "整场决斗"),
                 ("next_standby", "到下次的自己准备阶段"), ("opp_turn_end", "到对方回合结束")]
CHAIN_CATS = [("destroy", "破坏卡"), ("special_summon", "特殊召唤"), ("search", "从卡组把卡加入手卡"), ("remove", "除外"),
              ("to_grave", "送去墓地"), ("draw", "抽卡"), ("negate", "让发动无效"), ("to_hand", "让卡回到手卡")]
CONT_MODES = [("self", "这张卡自己"), ("zone", "一片区域里的卡"), ("player", "玩家"), ("equipped", "装备怪兽"),
              ("card_target", "这张卡的对象怪兽")]
COUNTERS = [("0x1", "魔力指示物")]


@functools.lru_cache(maxsize=None)
def effect_codes():
    """引擎的全部效果代码（259 种），常用的在前。"""
    with open(os.path.join(HERE, "effect_codes.json"), encoding="utf-8") as f:
        return json.load(f)["codes"]


def code_zh(name):
    return next((c["zh"] for c in effect_codes() if c["name"] == name), name)


class Block:
    """fields：[(名字, 中文, 类型 choice/multi（可以勾几个）/int/text/code/lua, 选项或默认值)]；
    slots：[(名字, 中文, 接受的类型, 能放几块 1/0=不限, 只收哪些积木 或 None)]。show(node) 返回列表里这一行的字。"""

    def __init__(self, key, kind, category, label, fields=(), slots=(), show=None, hint=""):
        self.key, self.kind, self.category, self.label = key, kind, category, label
        self.fields = list(fields)
        self.slots = [tuple(s) + (None,) * (5 - len(s)) for s in slots]
        self.hint = hint
        self._show = show

    def defaults(self):
        node = {"block": self.key}
        for name, _, ftype, opt in self.fields:
            node[name] = opt[0][0] if ftype in ("choice", "multi") else (effect_codes()[0]["name"] if ftype == "code" else opt)
        for slot in self.slots:
            node[slot[0]] = []
        return node

    def show(self, node):
        return self._show(node) if self._show else self.label


def multi_parts(value, keys):
    """多选字段的值 → 各个选项（「hand+grave」；旧存档的「hand_grave」也拆得开）。"""
    out = []
    for p in str(value or "").split("+"):
        if p in keys or "_" not in p or not all(x in keys for x in p.split("_")):
            out.append(p)
        else:
            out += p.split("_")
    return list(dict.fromkeys(out))


class MultiMap(dict):
    """查表时认得组合值：各个选项分别查，再用 join 连起来。
    wrap：外面加括号（Lua 表达式）；strip：去掉共同的前后缀（「魔法卡·陷阱卡」→「魔法·陷阱卡」）；
    alias：组合里改用的说法（发动位置组合里「怪兽区」说成「场上」）。"""

    def __init__(self, data, join, wrap=False, strip=False, alias=None):
        super().__init__(data)
        self.join, self.wrap, self.strip, self.alias = join, wrap, strip, alias or {}

    def __missing__(self, key):
        ps = multi_parts(key, self)
        if len(ps) < 2 or any(not dict.__contains__(self, p) for p in ps):
            raise KeyError(key)
        vals = list(dict.fromkeys(self.alias.get(p, dict.__getitem__(self, p)) for p in ps))
        if len(vals) == 1:
            return vals[0]
        if self.strip:
            pre = os.path.commonprefix(vals)
            suf = os.path.commonprefix([v[::-1] for v in vals])[::-1]
            if pre and all(len(v) > len(pre) for v in vals):
                vals = [vals[0]] + [v[len(pre):] for v in vals[1:]]
            if suf and all(len(v) > len(suf) for v in vals):
                vals = [v[:-len(suf)] for v in vals[:-1]] + [vals[-1]]
        text = self.join.join(vals)
        return "(%s)" % text if self.wrap else text


def events_of(node):
    """效果的全部时机：时机字段可以勾几个；旧存档另有一个 event2（「另一个时机」）。没有时机是 ["free"]。"""
    evs = [e for e in multi_parts(node.get("event") or "free", dict(EVENTS)) if e != "free"]
    ev2 = node.get("event2") or "free"
    if ev2 != "free" and ev2 not in evs:
        evs.append(ev2)
    return evs or ["free"]


def _opt(options, value):
    d = dict(options)
    if value in d:
        return d[value]
    ps = multi_parts(value, d)
    return "·".join(d.get(p, p) for p in ps) if all(p in d for p in ps) else value


BLOCKS = {}


def _add(*blocks):
    for b in blocks:
        BLOCKS[b.key] = b


COST_ACTS = ["discard", "send_to_gy", "banish", "release", "pay_lp", "detach", "to_deck", "remove_counter", "reveal", "to_hand"]


def _effect_show(n):
    evs = events_of(n)
    ev = "" if evs == ["free"] else " · 时机：%s%s" % (
        "" if n.get("event_player", "any") == "any" or not any(e in PLAYER_EVENTS for e in evs)
        else _opt(PLAYERS, n["event_player"]), "或".join(_opt(EVENTS, e) for e in evs))
    return "效果：%s%s%s%s" % (_opt(EFFECT_TYPES, n["type"]), ev, "" if not n.get("limit") else " · " + _opt(LIMITS, n["limit"]),
                            " · 灵摆效果" if n.get("part") == "pendulum" else "")


def _cont_show(n):
    if n["mode"] == "equipped":
        return "永续效果：装备怪兽适用「%s」" % code_zh(n["code"])
    who = {"self": "这张卡", "card_target": "这张卡的对象怪兽", "zone": "%s%s的卡" % (_opt(WHO, n.get("who")), _opt(FIELD_ZONES, n.get("where"))),
           "player": _opt(WHO, n.get("player"))}[n["mode"]]
    return "永续效果：只要这张卡在%s存在，%s适用「%s」%s" % (_opt(RANGES, n["range"]), who, code_zh(n["code"]),
                                                " · 灵摆效果" if n.get("part") == "pendulum" else "")


# ---------------------------------------------------------------- 效果（帽子块）
_add(
    Block("effect", "hat", "效果", "会发动的效果",
          [("type", "效果类型", "choice", EFFECT_TYPES),
           ("event", "时机（可以勾几个）", "multi", EVENTS),
           ("event_player", "谁的（抽卡、攻击、发动、阶段）", "choice", ANY_PLAYER),
           ("range", "在哪里发动", "multi", RANGES), ("limit", "次数", "choice", LIMITS),
           ("limit_n", "次数：几次（1回合2次就填 2）", "int", 1),
           ("damage_step", "伤害步骤", "choice", DAMAGE_STEP),
           ("chain_limit", "对应", "choice", [("", "可以对应"), ("opp", "对方不能对应这个效果的发动"), ("all", "双方都不能对应"),
                                            ("opp_end", "直到连锁结束对方不能发动卡的效果")]),
           ("unstoppable", "无效", "choice", [("", "可以被无效"), ("yes", "这个效果的发动和效果不会被无效化")]),
           ("part", "灵摆卡：写在哪一栏", "choice", PARTS)],
          [("twice_when", "1回合1次时：这个条件满足就最多2次（可以空着）", "cond", 1), ("condition", "发动条件", "cond", 1), ("cost", "代价", "stmt", 0, COST_ACTS),
           ("target", "对象（取对象；「自己1只和对方1只」放两块）", "target", 0), ("operation", "处理", "stmt", 0),
           ("modes", "发动时选一个分支（用了这个，上面的对象和处理要空着）", "option", 0, ("effect_mode",))],
          show=_effect_show,
          hint="对应引擎的 Effect.CreateEffect：类型、事件、发动位置、次数；下面四个槽是发动条件、代价、对象、处理"),
    Block("continuous", "hat", "效果", "永续效果",
          [("mode", "适用于", "choice", CONT_MODES), ("code", "效果代码", "code", None),
           ("range", "这张卡在哪里时适用", "multi", RANGES),
           ("who", "一片区域：谁的", "choice", WHO), ("where", "一片区域：哪里", "multi", FIELD_ZONES),
           ("player", "玩家：谁", "choice", WHO), ("against", "抗性只对谁（对象 / 效果破坏 / 不受影响）", "choice", AGAINST),
           ("part", "灵摆卡：写在哪一栏", "choice", PARTS)],
          [("condition", "适用条件（不需要可以空着）", "cond", 1), ("value", "数值（不需要可以空着）", "number", 1),
           ("filter", "只对这样的卡（不需要可以空着）", "filter", 0), ("value_cards", "数值：只对这样的卡成立（可以空着）", "filter", 0)],
          show=_cont_show,
          hint="不发动、一直适用：EFFECT_TYPE_SINGLE / FIELD / EQUIP（装备怪兽）+ 引擎的效果代码（259 种）"),
    Block("destroy_replace", "hat", "效果", "代替破坏",
          [("mode", "保护谁", "choice", [("self", "这张卡"), ("others", "自己场上这样的卡（下面的槽）")]),
           ("range", "这张卡在哪里时有效", "multi", RANGES), ("limit", "次数", "choice", [("", "不限"), ("card", "1回合1次")])],
          [("protect", "保护的卡（选「自己场上这样的卡」时）", "filter", 0),
           ("cost", "作为代替做什么", "stmt", 0, COST_ACTS)],
          show=lambda n: "代替破坏：%s被战斗·效果破坏时" % ("这张卡" if n["mode"] == "self" else "自己场上的卡"),
          hint="EFFECT_DESTROY_REPLACE：「被破坏的场合，可以作为代替把……」（不入连锁）"),
    Block("custom_effect", "hat", "效果", "自定义效果（Lua）",
          [("zh", "中文效果文字", "text", ""), ("lua", "注册代码（写在 initial_effect 里，可用 c）", "lua", ""),
           ("helpers", "辅助函数（写在脚本顶层，以 s.cl_ 开头）", "lua", "")],
          show=lambda n: "AI 自定义 Lua · 未经积木校验：%s" % (n.get("zh") or "（没写中文）"),
          hint="积木表达不了整个效果时才用；写完要在沙盒里测试"),
    Block("monster_trait", "hat", "效果", "怪兽的特性",
          [("trait", "特性", "choice", [("spirit", "灵魂：召唤·反转的回合的结束阶段回到手卡"),
                                       ("gemini", "二重：再1次召唤后才有效果"),
                                       ("union", "同盟：可以当作装备卡装备给怪兽")])],
          [("filter", "同盟：能装备给这样的怪兽", "filter", 0)],
          show=lambda n: "怪兽的特性：%s" % {"spirit": "灵魂", "gemini": "二重", "union": "同盟"}[n["trait"]],
          hint="aux.EnableSpiritReturn / EnableDualAttribute / EnableUnionAttribute（卡片种类也会带上对应的标记）"),
    Block("name_as", "hat", "效果", "卡名当作……使用",
          [("code", "当作哪张卡（卡号）", "int", 0), ("name", "那张卡的卡名", "text", ""),
           ("where", "在哪里时", "choice", [("", "场上"), ("field_grave", "场上·墓地"), ("hand_field_grave", "手卡·场上·墓地"), ("all", "所有地方（规则上同名）")])],
          show=lambda n: "这张卡的卡名当作「%s」使用" % (n.get("name") or n["code"]), hint="aux.EnableChangeCode"),
    Block("target_link", "hat", "效果", "和对象怪兽同生共死",
          [("link", "哪种", "choice", [("leave_destroy", "这张卡从场上离开时，那只怪兽破坏"), ("target_destroyed", "那只怪兽被破坏时，这张卡破坏"), ("target_leave", "那只怪兽从场上离开时，这张卡破坏")]), ("range", "这张卡在哪里时", "multi", RANGES)],
          show=lambda n: "对象关系：%s" % _opt([("leave_destroy", "这张卡从场上离开时，那只怪兽破坏"), ("target_destroyed", "那只怪兽被破坏时，这张卡破坏"), ("target_leave", "那只怪兽从场上离开时，这张卡破坏")], n["link"]),
          hint="配合动作「这张卡持续以那张卡为对象」：SetCardTarget / GetFirstCardTarget"),
    Block("summon_rule", "hat", "效果", "召唤条件",
          [("normal", "通常召唤", "choice", [("can", "可以通常召唤"), ("no", "不能通常召唤")]),
           ("special", "特殊召唤", "choice", SS_RULES)],
          [("by", "只能用这样的卡的效果特殊召唤（选了才用）", "filter", 0)],
          show=lambda n: "召唤条件：%s；特殊召唤%s" % (
              "不能通常召唤" if n.get("normal") == "no" else "可以通常召唤", _opt(SS_RULES, n.get("special", "any"))),
          hint="EnableReviveLimit（不能通常召唤，正规出场前不能苏生）+ EFFECT_SPSUMMON_CONDITION：卡上不编号的一行"),
    Block("sp_proc", "hat", "效果", "特殊召唤手续",
          [("range", "从哪里", "multi", PROC_RANGES),
           ("limit", "次数", "choice", [("", "不限"), ("once", "这个卡名的方法1回合1次")]),
           ("position", "表示形式", "choice", [("faceup", "表侧表示"), ("defense", "表侧守备表示")])],
          [("condition", "条件（可以空着）", "cond", 1), ("cost", "代价（可以空着）", "stmt", 0, COST_ACTS)],
          show=lambda n: "特殊召唤手续：从%s特殊召唤%s" % (_opt(PROC_RANGES, n["range"]),
                                                 "（1回合1次）" if n.get("limit") == "once" else ""),
          hint="EFFECT_SPSUMMON_PROC：「自己场上没有怪兽存在的场合，这张卡可以从手卡特殊召唤」（不入连锁）"),
    Block("extra_materials", "hat", "效果", "同调 / 超量 / 连接素材",
          [("method", "召唤方法", "choice", [("synchro", "同调"), ("xyz", "超量"), ("link", "连接")]),
           ("count", "几只（同调：调整以外的；超量：素材数；连接：最少）", "int", 1),
           ("more", "数量", "choice", [("", "正好这么多"), ("yes", "这么多以上")]),
           ("rank", "超量：素材的等级", "int", 4),
           ("tuners", "同调：调整几只", "choice", [("", "1只"), ("two", "2只")])],
          [("tuner", "同调：调整要满足（可以空着）", "filter", 0), ("material", "素材要满足（同调：调整以外的）", "filter", 0),
           ("include", "连接：素材里要包含（可以空着）", "filter", 0),
           ("alter", "超量：也能在这样的自己的怪兽上面重叠来超量召唤（可以空着）", "filter", 0)],
          show=lambda n: "素材：%s召唤，%d 只%s" % ({"synchro": "同调", "xyz": "超量", "link": "连接"}[n["method"]], n["count"],
                                               "以上" if n.get("more") == "yes" else ""),
          hint="aux.AddSynchroProcedure / AddXyzProcedure / AddLinkProcedure：卡上的素材行（写了就不用工作台的素材栏）"),
    Block("fusion_materials", "hat", "效果", "融合素材",
          [("count", "第二种素材几只", "int", 1), ("more", "第二种素材", "choice", [("", "正好这么多"), ("yes", "这么多以上")]),
           ("contact", "接触融合", "choice", [("", "不是（用「融合」等融合召唤）"), ("deck", "把自己场上的素材回到卡组特殊召唤"),
                                         ("grave", "把自己场上的素材送去墓地特殊召唤"), ("banish", "把自己场上的素材除外特殊召唤")])],
          [("first", "第一种素材（空着就只用第二种）", "filter", 0), ("second", "第二种素材", "filter", 0),
           ("third", "第三种素材（可以空着；三种各1只）", "filter", 0)],
          show=lambda n: "融合素材：第一种＋第二种×%d%s" % (n["count"], "以上" if n.get("more") == "yes" else ""),
          hint="aux.AddFusionProcFun2 / FunRep / FunFunRep：融合怪兽卡上的素材行"),
    Block("ns_proc", "hat", "效果", "不用解放 / 改变解放数的召唤",
          [("tribute", "解放几只", "int", 0), ("opp", "可以解放谁的怪兽", "choice", [("", "自己的"), ("yes", "对方的也可以")])],
          [("condition", "条件（可以空着）", "cond", 1)],
          show=lambda n: "召唤手续：%s" % ("不用解放召唤" if not n.get("tribute") else
                                       "解放%d只%s怪兽召唤" % (n["tribute"], "（对方的也可以）" if n.get("opp") else "")),
          hint="EFFECT_SUMMON_PROC：「这张卡可以不用解放作召唤」「可以把1只怪兽解放作召唤」「也能把对方怪兽解放」"),
    Block("unique", "hat", "效果", "场上只能存在1张", [("who", "在哪一边", "choice", UNIQUE_SIDES)],
          show=lambda n: "规则：这张卡在%s只能有1张表侧表示存在" % _opt(UNIQUE_SIDES, n["who"]),
          hint="c:SetUniqueOnField：卡上不编号的一行"),
)

# ---------------------------------------------------------------- 动作
for key, label, hint in (("destroy", "破坏", "Duel.Destroy"),
                         ("send_to_gy", "送去墓地", "Duel.SendtoGrave"),
                         ("set_card", "盖放", "Duel.SSet（魔法·陷阱卡）"),
                         ("discard", "丢弃", "Duel.SendtoGrave(…,REASON_DISCARD)"), ("release", "解放", "Duel.Release"),
                         ("get_control", "得到控制权", "Duel.GetControl")):
    _add(Block(key, "stmt", "动作", label, slots=[("cards", "哪些卡", "cards", 1)], hint=hint))
_add(
    Block("banish", "stmt", "动作", "除外", [("face", "表示形式", "choice", FACES),
                                          ("temp", "暂时", "choice", [("", "普通除外"), ("yes", "暂时除外（之后可以回到场上）")])],
          [("cards", "哪些卡", "cards", 1)],
          show=lambda n: "除外" + ("（里侧表示）" if n.get("face") == "down" else ""), hint="Duel.Remove"),
    Block("to_hand", "stmt", "动作", "加入手卡", [("to", "谁的手卡", "choice", [("", "持有者的手卡"), ("opp", "对方的手卡")])],
          [("cards", "哪些卡", "cards", 1)], show=lambda n: "加入%s手卡" % ("对方" if n.get("to") == "opp" else ""),
          hint="Duel.SendtoHand"),
    Block("to_deck", "stmt", "动作", "回到卡组", [("seq", "放到", "choice", DECK_SEQ)], [("cards", "哪些卡", "cards", 1)],
          show=lambda n: "回到卡组" + ("" if n.get("seq", "shuffle") == "shuffle" else "（%s）" % _opt(DECK_SEQ, n["seq"])),
          hint="Duel.SendtoDeck"),
    Block("special_summon", "stmt", "动作", "特殊召唤",
          [("position", "表示形式", "choice", SS_POSITIONS), ("to", "在谁的场上", "choice", PLAYERS),
           ("ignore", "召唤条件", "choice", [("", "要满足召唤条件"), ("yes", "无视召唤条件")])],
          [("cards", "哪些卡", "cards", 1)],
          show=lambda n: "特殊召唤%s%s" % ("（对方场上）" if n.get("to") == "opp" else "",
                                     "（%s）" % _opt(SS_POSITIONS, n["position"]) if n.get("position", "faceup") != "faceup" else ""),
          hint="Duel.SpecialSummon"),
    Block("place", "stmt", "动作", "放置到场上", [("where", "放到", "choice", PLACE_ZONES)], [("cards", "哪些卡", "cards", 1)],
          show=lambda n: "在自己的%s表侧表示放置" % _opt(PLACE_ZONES, n["where"]),
          hint="Duel.MoveToField：「从卡组把1张永续魔法卡在自己场上表侧表示放置」"),
    Block("fusion_summon", "stmt", "动作", "融合召唤", [("mats", "素材从哪里", "choice", FUSION_MATS)],
          [("filter", "融合怪兽要满足（可以空着）", "filter", 0)],
          show=lambda n: "用%s的怪兽作为素材融合召唤" % _opt(FUSION_MATS, n["mats"]),
          hint="aux.FusionEffectUltimate：从额外卡组融合召唤1只"),
    Block("ritual_summon", "stmt", "动作", "仪式召唤",
          [("level", "解放的等级", "choice", RITUAL_LEVELS), ("from", "仪式怪兽从哪里", "choice", RITUAL_FROM)],
          [("filter", "仪式怪兽要满足（可以空着）", "filter", 0)],
          show=lambda n: "仪式召唤（%s）" % _opt(RITUAL_LEVELS, n["level"]),
          hint="aux.RitualUltimate：解放手卡·场上的怪兽，仪式召唤1只"),
    Block("change_position", "stmt", "动作", "改变表示形式", [("to", "变成", "choice", TO_POSITIONS)],
          [("cards", "哪些卡", "cards", 1)], show=lambda n: "改变表示形式：%s" % _opt(TO_POSITIONS, n["to"]),
          hint="Duel.ChangePosition"),
    Block("draw", "stmt", "动作", "抽卡", [("player", "谁", "choice", PLAYERS), ("count", "几张", "int", 1)],
          [("count_n", "几张（算出来的，可以空着）", "number", 1)],
          show=lambda n: "%s抽 %d 张卡" % (_opt(PLAYERS, n["player"]), n["count"]), hint="Duel.Draw"),
    Block("damage", "stmt", "动作", "给与伤害", [("player", "给谁", "choice", [("opp", "对方"), ("you", "自己")])],
          [("amount", "多少", "number", 1)], show=lambda n: "给与%s伤害" % _opt(PLAYERS, n["player"]), hint="Duel.Damage"),
    Block("recover", "stmt", "动作", "回复基本分", [("player", "谁", "choice", PLAYERS)],
          [("amount", "多少", "number", 1)], show=lambda n: "%s回复基本分" % _opt(PLAYERS, n["player"]), hint="Duel.Recover"),
    Block("pay_lp", "stmt", "动作", "支付基本分", slots=[("amount", "多少", "number", 1)], hint="Duel.PayLPCost（代价）"),
    Block("detach", "stmt", "动作", "取除超量素材",
          [("count", "几个", "int", 1), ("all", "取除多少", "choice", [("", "取除这么多"), ("yes", "全部取除")])],
          [("count_n", "几个（算出来的，可以空着）", "number", 1), ("cards", "哪只超量怪兽的（空着是这张卡）", "cards", 1)],
          show=lambda n: "取除这张卡的 %d 个超量素材" % n["count"], hint="RemoveOverlayCard"),
    Block("add_counter", "stmt", "动作", "放置指示物", [("counter", "种类", "choice", COUNTERS), ("count", "几个", "int", 1),
                                                  ("max", "这张卡最多放几个（0 为不限）", "int", 0)],
          [("cards", "放在哪张卡上", "cards", 1), ("count_n", "几个（算出来的，可以空着）", "number", 1)],
          show=lambda n: "放置 %d 个%s" % (n["count"], _opt(COUNTERS, n["counter"])), hint="AddCounter"),
    Block("remove_counter", "stmt", "动作", "取除指示物",
          [("counter", "种类", "choice", COUNTERS), ("count", "几个", "int", 1),
           ("from", "从哪里取除", "choice", [("self", "这张卡"), ("field", "场上任意的卡")])],
          [("count_n", "几个（算出来的，可以空着）", "number", 1)],
          show=lambda n: "取除这张卡的 %d 个%s" % (n["count"], _opt(COUNTERS, n["counter"])), hint="RemoveCounter（代价）"),
    Block("create_token", "stmt", "动作", "特殊召唤衍生物",
          [("name", "名字", "text", "衍生物"), ("count", "几只", "int", 1),
           ("race", "种族", "choice", RACES), ("attribute", "属性", "choice", ATTRIBUTES), ("level", "等级", "int", 1),
           ("atk", "攻击力", "int", 0), ("def", "守备力", "int", 0),
           ("position", "表示形式", "choice", [("defense", "守备表示"), ("attack", "攻击表示")])],
          [("count_n", "几只（算出来的，可以空着）", "number", 1)],
          show=lambda n: "特殊召唤 %d 只「%s」" % (n["count"], n["name"]),
          hint="DIY 衍生物的卡片数据在导出时自动生成（卡号接在这张卡后面）"),
    Block("negate_activation", "stmt", "动作", "那个发动无效", hint="Duel.NegateActivation"),
    Block("negate_effect", "stmt", "动作", "那个效果无效", hint="Duel.NegateEffect"),
    Block("change_chain_target", "stmt", "动作", "那个效果的对象转移", slots=[("cards", "转移给哪张卡", "cards", 1)],
          hint="Duel.ChangeTargetCard（时机：卡或效果发动时）"),
    Block("change_chain_effect", "stmt", "动作", "那个效果变成……", slots=[("body", "变成的效果（这里的「自己」是发动那个效果的玩家）", "stmt", 0)],
          hint="Duel.ChangeChainOperation（时机：卡或效果发动时）"),
    Block("negate_attack", "stmt", "动作", "那次攻击无效", hint="Duel.NegateAttack"),
    Block("negate_summon", "stmt", "动作", "那次召唤无效", hint="Duel.NegateSummon（时机：怪兽要被召唤之际）"),
    Block("keep_target", "stmt", "动作", "这张卡持续以那张卡为对象", slots=[("cards", "哪张卡", "cards", 1)],
          hint="c:SetCardTarget：永续陷阱「以那只怪兽为对象」，之后用「这张卡的对象怪兽」"),
    Block("skip_phase", "stmt", "动作", "跳过阶段", [("player", "谁的", "choice", PLAYERS), ("phase", "哪个阶段", "choice", [("draw", "抽卡阶段"), ("standby", "准备阶段"), ("main1", "主要阶段1"), ("battle", "战斗阶段"), ("main2", "主要阶段2"), ("end", "结束阶段")])],
          show=lambda n: "跳过%s的%s" % (_opt(PLAYERS, n["player"]), _opt([("draw", "抽卡阶段"), ("standby", "准备阶段"), ("main1", "主要阶段1"), ("battle", "战斗阶段"), ("main2", "主要阶段2"), ("end", "结束阶段")], n["phase"])), hint="Duel.SkipPhase（这个回合的）"),
    Block("to_extra_faceup", "stmt", "动作", "表侧加入额外卡组", slots=[("cards", "哪些灵摆怪兽", "cards", 1)],
          hint="Duel.SendtoExtraP"),
    Block("stay_on_field", "stmt", "动作", "这张卡不送去墓地，留在场上", hint="c:CancelToGrave：魔法·陷阱卡发动后继续留在场上"),
    Block("give_up_draw", "stmt", "动作", "放弃通常抽卡", hint="aux.GiveUpNormalDraw（配合时机「抽卡阶段的通常抽卡前」）"),
    Block("activate_card", "stmt", "动作", "从手卡 / 卡组把卡发动",
          [("where", "从哪里", "choice", [("hand_deck", "手卡·卡组"), ("deck", "卡组"), ("hand", "手卡")])],
          [("filter", "发动什么样的卡（场地魔法 / 永续魔法·陷阱）", "filter", 0)],
          show=lambda n: "从%s把1张卡发动" % {"hand_deck": "手卡·卡组", "deck": "卡组", "hand": "手卡"}[n["where"]],
          hint="MoveToField + 发动（照尸界的班西的写法）"),
    Block("end_battle_phase", "stmt", "动作", "战斗阶段结束", hint="Duel.SkipPhase(回合玩家,PHASE_BATTLE…)：「那之后，战斗阶段结束」"),
    Block("normal_summon", "stmt", "动作", "进行1只怪兽的召唤", slots=[("filter", "召唤什么样的怪兽（可以空着）", "filter", 0)],
          hint="Duel.Summon（不占用通常召唤次数）"),
    Block("extra_summon", "stmt", "动作", "进行同调 / 超量 / 连接召唤",
          [("method", "召唤方法", "choice", [("synchro", "同调召唤"), ("xyz", "超量召唤"), ("link", "连接召唤")])],
          [("filter", "召唤什么样的怪兽（可以空着）", "filter", 0)],
          show=lambda n: "用自己场上的怪兽为素材进行%s" % {"synchro": "同调召唤", "xyz": "超量召唤", "link": "连接召唤"}[n["method"]],
          hint="Duel.SynchroSummon / XyzSummon / LinkSummon"),
    Block("trap_monster", "stmt", "动作", "这张卡变成怪兽特殊召唤",
          [("mtype", "当作", "choice", [("normal", "通常怪兽"), ("effect", "效果怪兽")]),
           ("level", "等级", "int", 4), ("atk", "攻击力", "int", 1000), ("def", "守备力", "int", 1000),
           ("race", "种族", "choice", RACES), ("attribute", "属性", "choice", ATTRIBUTES)],
          show=lambda n: "这张卡变成%s（%d星 %d/%d）特殊召唤" % ("通常怪兽" if n["mtype"] == "normal" else "效果怪兽",
                                                          n["level"], n["atk"], n["def"]),
          hint="陷阱怪兽：AddMonsterAttribute + SpecialSummon（卡片数据也要填同样的等级攻守）"),
    Block("copy_effects", "stmt", "动作", "得到那张卡的效果",
          [("name", "卡名", "choice", [("", "只得到效果"), ("yes", "也当作同名卡")]),
           ("reset", "期限", "choice", [("end_of_turn", "到回合结束"), ("permanent", "一直（离场前）")])],
          [("cards", "哪张卡", "cards", 1)], hint="c:CopyEffect（＋EFFECT_CHANGE_CODE）"),
    Block("return_to_field", "stmt", "动作", "回到场上", slots=[("cards", "哪些卡（暂时除外的）", "cards", 1)],
          hint="Duel.ReturnToField：配合「除外」选暂时除外、「之后再处理」带上的卡"),
    Block("sort_deck", "stmt", "动作", "确认卡组最上面并按喜欢的顺序放回",
          [("player", "谁的卡组", "choice", PLAYERS), ("count", "几张", "int", 3)],
          show=lambda n: "%s卡组最上面 %d 张按喜欢的顺序放回" % (_opt(PLAYERS, n["player"]), n["count"]), hint="Duel.SortDecktop"),
    Block("move_zone", "stmt", "动作", "移动到其他怪兽区域", slots=[("cards", "哪只怪兽（自己的）", "cards", 1)],
          hint="Duel.SelectDisableField + MoveSequence：「这张卡向其他的自己的主要怪兽区域移动」"),
    Block("change_attack_target", "stmt", "动作", "转移攻击对象", slots=[("cards", "转移给哪只（空着是直接攻击）", "cards", 1)],
          hint="Duel.ChangeAttackTarget"),
    Block("calc_damage", "stmt", "动作", "进行伤害计算", slots=[("a", "这只", "cards", 1), ("b", "和这只", "cards", 1)],
          hint="Duel.CalculateDamage：「那2只进行战斗的伤害计算」"),
    Block("chain_attack", "stmt", "动作", "可以再1次继续攻击", hint="Duel.ChainAttack：战斗破坏对方怪兽时用"),
    Block("equip", "stmt", "动作", "装备", slots=[("cards", "把哪张卡", "cards", 1), ("to", "装备给哪只怪兽", "cards", 1)],
          hint="Duel.Equip；装备魔法卡的发动：把「这张卡」装备给「对象」"),
    Block("set_lp", "stmt", "动作", "基本分变成", [("player", "谁的", "choice", PLAYERS)], [("amount", "变成多少", "number", 1)],
          show=lambda n: "%s的基本分变成……" % _opt(PLAYERS, n["player"]), hint="Duel.SetLP"),
    Block("attach", "stmt", "动作", "作为超量素材", slots=[("cards", "哪些卡", "cards", 1),
                                                    ("to", "给哪只超量怪兽", "cards", 1)],
          hint="Duel.Overlay（场上的卡原本的超量素材送去墓地）"),
    Block("confirm_top", "stmt", "动作", "翻开卡组最上面", [("player", "谁的卡组", "choice", PLAYERS), ("count", "几张", "int", 1)],
          show=lambda n: "翻开%s卡组最上面 %d 张" % (_opt(PLAYERS, n["player"]), n["count"]), hint="Duel.ConfirmDecktop"),
    Block("shuffle", "stmt", "动作", "洗切卡组", [("player", "谁的卡组", "choice", PLAYERS)],
          show=lambda n: "%s的卡组洗切" % _opt(PLAYERS, n["player"]), hint="Duel.ShuffleDeck"),
    Block("reveal", "stmt", "动作", "给对方观看", slots=[("cards", "哪些卡", "cards", 1)],
          hint="Duel.ConfirmCards（当代价：公开手卡）"),
    Block("win", "stmt", "动作", "决斗胜利", [("player", "谁", "choice", PLAYERS)],
          show=lambda n: "%s决斗胜利" % _opt(PLAYERS, n["player"]), hint="Duel.Win"),
    Block("raw", "stmt", "动作", "自定义 Lua",
          [("zh", "中文写法", "text", ""), ("lua", "Lua 语句（每行一句）", "lua", "")],
          show=lambda n: "自定义 Lua · 未经积木校验：%s" % (n.get("zh") or "（没写中文）"),
          hint="积木表达不了的部分，懂 Lua 的人直接写；只做安全检查，能否运行要在沙盒里测试"),
)

# ---------------------------------------------------------------- 登记效果
_add(
    Block("register", "stmt", "登记效果", "给卡片登记效果",
          [("code", "效果代码", "code", None), ("reset", "期限", "choice", RESETS),
           ("against", "抗性只对谁（对象 / 效果破坏 / 不受影响）", "choice", AGAINST)],
          [("cards", "哪些卡", "cards", 1), ("value", "数值（不需要可以空着）", "number", 1), ("value_cards", "数值：只对这样的卡成立（可以空着）", "filter", 0)],
          show=lambda n: "给卡片登记效果：%s（%s）" % (code_zh(n["code"]), _opt(RESETS, n["reset"])),
          hint="EFFECT_TYPE_SINGLE + RegisterEffect：引擎的 259 种效果代码都能选"),
    Block("register_player", "stmt", "登记效果", "让玩家适用效果",
          [("player", "谁", "choice", WHO), ("code", "效果代码", "code", None), ("reset", "期限", "choice", PLAYER_RESETS)],
          [("value", "数值（不需要可以空着）", "number", 1), ("filter", "只针对这样的卡（不需要可以空着）", "filter", 0),
           ("value_cards", "数值：只对这样的卡成立（可以空着）", "filter", 0)],
          show=lambda n: "让%s适用效果：%s（%s）" % (_opt(WHO, n["player"]), code_zh(n["code"]), _opt(PLAYER_RESETS, n["reset"])),
          hint="自肃、封锁对手：EFFECT_TYPE_FIELD + EFFECT_FLAG_PLAYER_TARGET（「不能特殊召唤」「不能发动」……）"),
    Block("register_zone", "stmt", "登记效果", "让一片区域的卡适用效果",
          [("who", "谁的", "choice", WHO), ("where", "哪里", "multi", FIELD_ZONES), ("code", "效果代码", "code", None),
           ("reset", "期限", "choice", PLAYER_RESETS)],
          [("value", "数值（不需要可以空着）", "number", 1), ("filter", "只对这样的卡（不需要可以空着）", "filter", 0),
           ("value_cards", "数值：只对这样的卡成立（可以空着）", "filter", 0)],
          show=lambda n: "让%s%s的卡适用效果：%s（%s）" % (_opt(WHO, n["who"]), _opt(FIELD_ZONES, n["where"]),
                                                 code_zh(n["code"]), _opt(PLAYER_RESETS, n["reset"])),
          hint="EFFECT_TYPE_FIELD + SetTargetRange：一片区域里（符合条件）的卡都适用"),
)

# ---------------------------------------------------------------- 控制
_add(
    Block("select", "stmt", "控制", "让玩家选卡",
          [("player", "谁选", "choice", PLAYERS), ("count", "选几张", "int", 1), ("as", "记作", "text", "A"),
           ("upto", "张数", "choice", UPTO), ("different", "卡名", "choice", DIFFERENT),
           ("sum", "按等级合计选", "choice", [("", "不按合计"), ("level_eq", "等级合计正好是下面的数值")])],
          [("source", "从哪些卡里选", "cards", 1), ("count_n", "张数（算出来的，可以空着）", "number", 1),
           ("sum_n", "等级合计（按合计选时用）", "number", 1)],
          show=lambda n: "让%s选 %d 张，记作 %s" % (_opt(PLAYERS, n["player"]), n["count"], n["as"]),
          hint="处理时选卡（不是取对象）：Duel.SelectMatchingCard"),
    Block("if", "stmt", "控制", "如果", slots=[("cond", "条件", "cond", 1), ("then", "那么", "stmt", 0),
                                              ("else", "否则", "stmt", 0)]),
    Block("after", "stmt", "控制", "那之后",
          [("how", "怎么接", "choice", [("then", "「那之后」：不同时处理"), ("and", "「，」：同时处理")])],
          slots=[("body", "做", "stmt", 0)], show=lambda n: "，做到了才继续" if n.get("how") == "and" else "那之后",
          hint="前一步做成了才做；「那之后」不同时处理（Duel.BreakEffect），「，」同时处理"),
    Block("may", "stmt", "控制", "可以选择做（问玩家）", [("ask", "问玩家的话", "text", "是否继续处理？")],
          [("body", "做", "stmt", 0)], show=lambda n: "可以选择做：%s" % n["ask"], hint="Duel.SelectYesNo"),
    Block("for_each", "stmt", "控制", "对每一张", slots=[("cards", "哪些卡", "cards", 1), ("body", "做（用「当前这张」）", "stmt", 0)],
          hint="逐张处理：for tc in aux.Next(g)"),
    Block("delay", "stmt", "控制", "之后再处理",
          [("when", "什么时候", "choice", DELAY_WHEN),
           ("carry", "带上前一步处理的卡", "choice", [("", "不带"), ("yes", "带上（里面用「带过来的卡」）")])],
          [("body", "到时候做", "stmt", 0)],
          show=lambda n: "之后再处理：%s" % _opt(DELAY_WHEN, n["when"]),
          hint="登记一个到时候才处理的效果（不入连锁）：「这个效果特殊召唤的怪兽在结束阶段破坏」"),
    Block("fail", "stmt", "控制", "做不到的场合", slots=[("body", "做", "stmt", 0)],
          hint="前一步一张也没处理成才做：「不能除外的场合，……」"),
    Block("announce", "stmt", "控制", "让玩家宣言", [("player", "谁宣言", "choice", PLAYERS), ("what", "宣言什么", "choice", ANNOUNCE)],
          show=lambda n: "让%s宣言1个%s" % (_opt(PLAYERS, n["player"]), _opt(ANNOUNCE, n["what"])),
          hint="之后用卡片条件「和宣言的一样」、数值「宣言的等级」"),
    Block("toss_coin", "stmt", "控制", "投掷硬币", [("call", "猜里表", "choice", [("", "不猜"), ("yes", "先猜里表")])],
          hint="Duel.TossCoin：之后用条件「硬币是表」，猜了的用「猜中了」"),
    Block("toss_dice", "stmt", "控制", "掷骰子", hint="Duel.TossDice：之后用数值「骰子的点数」"),
    Block("set_flag", "stmt", "控制", "做标记",
          [("on", "标记在", "choice", FLAG_ON), ("name", "标记编号（0～9）", "int", 1), ("reset", "期限", "choice", FLAG_RESETS)],
          show=lambda n: "给%s做标记 %d（%s）" % (_opt(FLAG_ON, n["on"]), n["name"], _opt(FLAG_RESETS, n["reset"])),
          hint="RegisterFlagEffect：配合条件「有标记」写「这个效果适用过的回合」「这张卡用这个效果特殊召唤的」……"),
    Block("each_player", "stmt", "控制", "双方各自", slots=[("body", "做（「自己」指正在做的那一方）", "stmt", 0)],
          hint="自己做一遍，再换对方做一遍（里面的「自己」「对方」跟着换）"),
    Block("choose", "stmt", "控制", "让玩家选一项（●选项）", [("player", "谁选", "choice", PLAYERS)],
          [("options", "选项", "option", 0, ("option",))], show=lambda n: "让%s从以下选一项" % _opt(PLAYERS, n["player"]),
          hint="Duel.SelectOption"),
    Block("option", "option", "控制", "●选项", [("text", "选项的话", "text", "选项")],
          [("cond", "能选的条件（不需要可以空着）", "cond", 1), ("body", "做", "stmt", 0)],
          show=lambda n: "●%s" % n["text"]),
    Block("effect_mode", "option", "控制", "●发动时选的分支", [("text", "选项的话", "text", "分支")],
          [("cond", "能选的条件（不需要可以空着）", "cond", 1), ("target", "这个分支的对象", "target", 0), ("operation", "这个分支的处理", "stmt", 0)],
          show=lambda n: "●%s" % n["text"], hint="发动时选好分支，分类和对象按选到的分支设置；Duel.SelectOption 写在 Target 里"),
    Block("take_target", "target", "控制", "取对象",
          [("count", "几张", "int", 1), ("as", "记作", "text", "T")], [("source", "从哪些卡里取", "cards", 1)],
          show=lambda n: "取 %d 张作为对象，记作 %s" % (n["count"], n["as"]),
          hint="只能放在效果的「对象」槽：Duel.SelectTarget；处理里用「对象」积木"),
)

# ---------------------------------------------------------------- 卡片组
_add(
    Block("this_card", "cards", "卡片", "这张卡", hint="e:GetHandler()"),
    Block("target", "cards", "卡片", "对象", [("name", "名字", "text", "T")], show=lambda n: "对象 %s" % n["name"],
          hint="效果「对象」槽里取的卡（处理时还在、还是对象的那些）"),
    Block("all", "cards", "卡片", "全部",
          [("who", "谁的", "choice", WHO), ("where", "在哪", "multi", ZONES)], [("filter", "什么样的卡", "filter", 0)],
          show=lambda n: "全部：%s%s的卡" % (_opt(WHO, n["who"]), _opt(ZONES, n["where"])), hint="Duel.GetMatchingGroup"),
    Block("pick", "cards", "卡片", "选几张",
          [("who", "谁的", "choice", WHO), ("where", "在哪", "multi", ZONES), ("count", "几张", "int", 1),
           ("upto", "张数", "choice", UPTO), ("different", "卡名", "choice", DIFFERENT)],
          [("filter", "什么样的卡", "filter", 0), ("count_n", "张数（算出来的，可以空着）", "number", 1)],
          show=lambda n: "选 %d 张：%s%s的卡" % (n["count"], _opt(WHO, n["who"]), _opt(ZONES, n["where"])),
          hint="处理时（代价里是支付时）由自己选：Duel.SelectMatchingCard"),
    Block("var", "cards", "卡片", "记下的卡", [("name", "名字", "text", "A")], show=lambda n: "记下的卡 %s" % n["name"]),
    Block("operated", "cards", "卡片", "刚才处理的卡", slots=[("filter", "只要其中这样的卡（可以空着）", "filter", 0)],
          hint="Duel.GetOperatedGroup()：「这个效果除外的「玄化」卡」"),
    Block("each", "cards", "卡片", "当前这张", hint="「对每一张」里正在处理的那张"),
    Block("chain_card", "cards", "卡片", "那个发动的卡", hint="re:GetHandler()（时机是「卡或效果发动」时）"),
    Block("event_cards", "cards", "卡片", "那些卡（事件里的卡）", slots=[("filter", "只要其中这样的卡（可以空着）", "filter", 0)],
          hint="eg：召唤的怪兽、送去墓地的卡……"),
    Block("attacker", "cards", "卡片", "攻击的怪兽", hint="Duel.GetAttacker()"),
    Block("attack_target", "cards", "卡片", "被攻击的怪兽", hint="Duel.GetAttackTarget()"),
    Block("battling", "cards", "卡片", "进行战斗的怪兽", [("who", "谁的", "choice", PLAYERS)],
          show=lambda n: "进行战斗的%s怪兽" % _opt(PLAYERS, n["who"]), hint="Duel.GetBattleMonster"),
    Block("battle_opp", "cards", "卡片", "和这张卡战斗的怪兽", hint="GetBattleTarget()"),
    Block("equip_target", "cards", "卡片", "装备怪兽（这张卡装备的）", hint="GetEquipTarget"),
    Block("carried", "cards", "卡片", "带过来的卡", hint="「之后再处理」带上的卡（还在原处的那些）"),
    Block("cost_cards", "cards", "卡片", "作为代价的卡", hint="代价里除外 / 送去墓地 / 解放……的卡（「上升除外的怪兽的攻击力数值」）"),
    Block("overlay", "cards", "卡片", "这张卡的超量素材", hint="GetOverlayGroup"),
    Block("column_group", "cards", "卡片", "和这张卡相同纵列的卡", hint="GetColumnGroup（不含这张卡）"),
    Block("equip_group", "cards", "卡片", "这张卡装备着的卡", hint="GetEquipGroup"),
    Block("prev_equip_target", "cards", "卡片", "这张卡离场前装备着的怪兽", hint="GetPreviousEquipTarget"),
    Block("card_target", "cards", "卡片", "这张卡的对象怪兽", hint="GetFirstCardTarget：先用「这张卡持续以那张卡为对象」"),
    Block("linked_group", "cards", "卡片", "这张卡所连接区的怪兽", hint="GetLinkedGroup"),
    Block("max_of", "cards", "卡片", "……里攻击力最高的",
          [("stat", "比什么", "choice", [("atk", "攻击力"), ("def", "守备力"), ("level", "等级")]),
           ("which", "最高 / 最低", "choice", [("max", "最高"), ("min", "最低")])],
          [("cards", "从哪些卡里", "cards", 1)],
          show=lambda n: "……里%s%s的" % ({"atk": "攻击力", "def": "守备力", "level": "等级"}[n["stat"]],
                                         "最高" if n["which"] == "max" else "最低"),
          hint="GetMaxGroup / GetMinGroup（一样高的都算）"),
    Block("random_pick", "cards", "卡片", "随机选几张",
          [("who", "谁的", "choice", WHO), ("where", "在哪", "multi", ZONES), ("count", "几张", "int", 1)],
          [("filter", "什么样的卡", "filter", 0)],
          show=lambda n: "随机选 %d 张：%s%s的卡" % (n["count"], _opt(WHO, n["who"]), _opt(ZONES, n["where"])),
          hint="RandomSelect：「对方手卡随机选1张」"),
    Block("deck_top", "cards", "卡片", "卡组最上面的卡", [("who", "谁的", "choice", PLAYERS), ("count", "几张", "int", 1)],
          [("count_n", "几张（算出来的，可以空着）", "number", 1)],
          show=lambda n: "%s卡组最上面 %d 张" % (_opt(PLAYERS, n["who"]), n["count"]), hint="Duel.GetDecktopGroup"),
)

# ---------------------------------------------------------------- 卡片条件
_add(
    Block("f_kind", "filter", "卡片条件", "卡种", [("kind", "卡种", "multi", KINDS)],
          show=lambda n: "是%s" % _opt(KINDS, n["kind"])),
    Block("f_subtype", "filter", "卡片条件", "种类", [("subtype", "种类", "multi", SUBTYPES)],
          show=lambda n: "是%s卡" % _opt(SUBTYPES, n["subtype"])),
    Block("f_race", "filter", "卡片条件", "种族", [("race", "种族", "multi", RACES)],
          show=lambda n: "是%s" % _opt(RACES, n["race"])),
    Block("f_attr", "filter", "卡片条件", "属性", [("attribute", "属性", "multi", ATTRIBUTES)],
          show=lambda n: "是%s属性" % _opt(ATTRIBUTES, n["attribute"])),
    Block("f_level", "filter", "卡片条件", "等级", [("op", "比较", "choice", CMPS), ("value", "等级", "int", 4)],
          [("value_n", "和这个数值比（可以空着）", "number", 1)],
          show=lambda n: "等级 %s %d" % (_opt(CMPS, n["op"]), n["value"])),
    Block("f_atk", "filter", "卡片条件", "攻击力", [("op", "比较", "choice", CMPS), ("value", "攻击力", "int", 1500)],
          [("value_n", "和这个数值比（可以空着）", "number", 1)],
          show=lambda n: "攻击力 %s %d" % (_opt(CMPS, n["op"]), n["value"])),
    Block("f_def", "filter", "卡片条件", "守备力", [("op", "比较", "choice", CMPS), ("value", "守备力", "int", 1500)],
          [("value_n", "和这个数值比（可以空着）", "number", 1)],
          show=lambda n: "守备力 %s %d" % (_opt(CMPS, n["op"]), n["value"])),
    Block("f_name", "filter", "卡片条件", "卡名", [("code", "卡号", "int", 0), ("name", "卡名（读句子用）", "text", "")],
          show=lambda n: "卡名是「%s」" % (n.get("name") or n["code"]),
          hint="code须是真实卡号；name只用于读回，0不代表按名查找。比较本卡原本卡名用f_same_code(card=[this_card])"),
    Block("f_set", "filter", "卡片条件", "字段", [("setcode", "字段编号（如 0x19e）", "text", "0x0"),
                                                ("name", "字段名", "text", "")],
          show=lambda n: "是「%s」卡" % (n.get("name") or n["setcode"])),
    Block("f_position", "filter", "卡片条件", "表示形式", [("position", "表示形式", "choice", POSITIONS)],
          show=lambda n: "是%s" % _opt(POSITIONS, n["position"])),
    Block("f_not_self", "filter", "卡片条件", "这张卡以外", hint="排除这张卡自己"),
    Block("f_controller", "filter", "卡片条件", "谁控制的", [("who", "谁的", "choice", PLAYERS)],
          show=lambda n: "是%s的卡" % _opt(PLAYERS, n["who"]), hint="IsControler"),
    Block("f_summon_type", "filter", "卡片条件", "召唤方法", [("method", "怎么出场的", "multi", SUMMON_METHODS)],
          show=lambda n: "是%s的" % _opt(SUMMON_METHODS, n["method"]), hint="IsSummonType"),
    Block("f_prev_location", "filter", "卡片条件", "之前在哪", [("where", "之前在", "multi", ZONES)],
          show=lambda n: "之前在%s" % _opt(ZONES, n["where"]), hint="IsPreviousLocation（离开那里以后）"),
    Block("f_prev_controller", "filter", "卡片条件", "之前谁控制的", [("who", "谁的", "choice", PLAYERS)],
          show=lambda n: "之前是%s的卡" % _opt(PLAYERS, n["who"]), hint="IsPreviousControler（离开场上以后）"),
    Block("f_prev_position", "filter", "卡片条件", "之前的表示形式", [("position", "之前是", "choice", POSITIONS)],
          show=lambda n: "之前是%s" % _opt(POSITIONS, n["position"]), hint="IsPreviousPosition（离开场上以后）"),
    Block("f_lists_code", "filter", "卡片条件", "记述了卡名", [("code", "卡号", "int", 0), ("name", "卡名（读句子用）", "text", "")],
          show=lambda n: "记述了「%s」" % (n.get("name") or n["code"]),
          hint="aux.IsCodeListed：卡的文字里写了这个卡名（DIY 卡用到的卡名会自动登记）"),
    Block("f_declared", "filter", "卡片条件", "和宣言的一样", [("what", "宣言的什么", "choice", ANNOUNCE)],
          show=lambda n: "是宣言的%s" % _opt(ANNOUNCE, n["what"]), hint="配合「让玩家宣言」"),
    Block("f_same_code", "filter", "卡片条件", "和那张卡原本卡名相同", slots=[("card", "哪张卡", "cards", 1)],
          hint="IsOriginalCodeRule；card=[this_card]比较效果持有卡的原本卡名，包含同名副本。套f_not排除这些同名卡；不同于仅排实体的f_not_self，也不同于比较现在卡名的f_name"),
    Block("f_same_column", "filter", "卡片条件", "和这张卡相同纵列", hint="GetColumnGroup():IsContains"),
    Block("f_zone_seq", "filter", "卡片条件", "在哪种格子",
          [("seq", "格子", "choice", [("main", "主要怪兽区域"), ("extra", "额外怪兽区域"), ("middle", "正中间的格子")])],
          hint="GetSequence"),
    Block("f_has_effect", "filter", "卡片条件", "正受到某种效果", [("code", "效果代码", "code", None)],
          show=lambda n: "适用着「%s」" % code_zh(n["code"]), hint="IsHasEffect"),
    Block("f_not_destroying", "filter", "卡片条件", "不是已经确定要被破坏的", hint="not IsStatus(STATUS_DESTROY_CONFIRMED)"),
    Block("f_chaining", "filter", "卡片条件", "正在发动中（连锁上）的", hint="IsStatus(STATUS_CHAINING)"),
    Block("f_battle_pair", "filter", "卡片条件", "正在和这张卡战斗",
          [("who", "哪些", "choice", [("opp", "和这张卡进行战斗的怪兽"), ("both", "这张卡和进行战斗的怪兽（那2只）")])],
          hint="GetBattleTarget：「这张卡和怪兽进行战斗的场合，那2只不会被那次战斗破坏」"),
    Block("f_battled_opp", "filter", "卡片条件", "和对方怪兽进行过战斗", hint="IsStatus(STATUS_OPPO_BATTLE)"),
    Block("f_can_attack", "filter", "卡片条件", "可以攻击", hint="IsAttackable"),
    Block("f_prev_name", "filter", "卡片条件", "离场前的卡名", [("code", "卡号", "int", 0), ("name", "卡名", "text", "")],
          show=lambda n: "原本在场上的「%s」" % (n.get("name") or n["code"]), hint="GetPreviousCodeOnField"),
    Block("f_activated_effect", "filter", "卡片条件", "发动的效果（只在抗性里用）",
          hint="不受「……发动的效果」影响：EFFECT_IMMUNE_EFFECT 的数值里加 te:IsActivated()"),
    Block("f_orig_race", "filter", "卡片条件", "原本的种族", [("race", "种族", "multi", RACES)], hint="GetOriginalRace"),
    Block("f_orig_attr", "filter", "卡片条件", "原本的属性", [("attribute", "属性", "multi", ATTRIBUTES)],
          hint="GetOriginalAttribute"),
    Block("f_prev_kind", "filter", "卡片条件", "离场前的卡种", [("kind", "卡种", "multi", KINDS)],
          hint="GetPreviousTypeOnField"),
    Block("f_by_this", "filter", "卡片条件", "因为这张卡", hint="GetReasonCard / GetReasonEffect 是这张卡：「被这张卡战斗破坏的」"),
    Block("f_prev_set", "filter", "卡片条件", "离场前是这个字段", [("setcode", "字段编号（如 0x19e）", "text", "0x0"),
                                                         ("name", "字段名", "text", "")],
          show=lambda n: "原本在场上的「%s」卡" % (n.get("name") or n["setcode"]), hint="IsPreviousSetCard"),
    Block("f_prev_race", "filter", "卡片条件", "离场前的种族", [("race", "种族", "multi", RACES)],
          hint="GetPreviousRaceOnField"),
    Block("f_prev_attr", "filter", "卡片条件", "离场前的属性", [("attribute", "属性", "multi", ATTRIBUTES)],
          hint="GetPreviousAttributeOnField"),
    Block("f_linked", "filter", "卡片条件", "在这张卡所连接区", hint="GetLinkedGroup():IsContains"),
    Block("f_link_state", "filter", "卡片条件", "连接状态", hint="IsLinkState：在连接怪兽所连接区，或者自己是连接着别的怪兽的连接怪兽"),
    Block("f_rank", "filter", "卡片条件", "阶级", [("op", "比较", "choice", CMPS), ("value", "阶级", "int", 4)],
          show=lambda n: "阶级 %s %d" % (_opt(CMPS, n["op"]), n["value"])),
    Block("f_link", "filter", "卡片条件", "连接值", [("op", "比较", "choice", CMPS), ("value", "连接值", "int", 2)],
          show=lambda n: "连接值 %s %d" % (_opt(CMPS, n["op"]), n["value"])),
    Block("f_same_attr", "filter", "卡片条件", "和那张卡相同属性", slots=[("card", "哪张卡", "cards", 1)]),
    Block("f_same_race", "filter", "卡片条件", "和那张卡相同种族", slots=[("card", "哪张卡", "cards", 1)]),
    Block("f_any", "filter", "卡片条件", "或者（满足其中一条）", slots=[("items", "以下满足一条（几条一起用「并且」包起来）", "filter", 0)],
          show=lambda n: "以下满足一条", hint="「「魔导书」卡或者魔法师族怪兽」"),
    Block("f_all", "filter", "卡片条件", "并且（这几条都满足）", slots=[("filter", "以下都满足", "filter", 0)],
          show=lambda n: "以下都满足", hint="放在「或者」里，把几条条件当成一条"),
    Block("f_by_proc", "filter", "卡片条件", "用这张卡的召唤手续出场的", hint="「这个方法召唤的场合」"),
    Block("f_by_player", "filter", "卡片条件", "被谁的效果", [("who", "谁的", "choice", PLAYERS)],
          show=lambda n: "是被%s移动的" % _opt(PLAYERS, n["who"]), hint="GetReasonPlayer：「被对方破坏的」"),
    Block("f_reason", "filter", "卡片条件", "原因", [("reason", "因为", "multi", REASONS)],
          show=lambda n: "原因是%s" % _opt(REASONS, n["reason"]), hint="IsReason"),
    Block("f_not", "filter", "卡片条件", "不是……", slots=[("filter", "这样的卡", "filter", 0)], show=lambda n: "不是以下的卡"),
)

# ---------------------------------------------------------------- 数值与条件
_add(
    Block("num", "number", "数值", "数字", [("value", "数值", "int", 1000)], show=lambda n: str(n["value"])),
    Block("atk_of", "number", "数值", "攻击力", slots=[("card", "哪张卡", "cards", 1)], show=lambda n: "攻击力（某张卡）"),
    Block("def_of", "number", "数值", "守备力", slots=[("card", "哪张卡", "cards", 1)], show=lambda n: "守备力（某张卡）"),
    Block("level_of", "number", "数值", "等级", slots=[("card", "哪张卡", "cards", 1)], show=lambda n: "等级（某张卡）"),
    Block("count_of", "number", "数值", "卡的数量", slots=[("cards", "哪些卡", "cards", 1)]),
    Block("flag_count", "number", "数值", "标记的个数", [("on", "标记在", "choice", FLAG_ON), ("name", "标记编号（0～9）", "int", 1)],
          show=lambda n: "%s的标记 %d 的个数" % (_opt(FLAG_ON, n["on"]), n["name"]),
          hint="GetFlagEffect：每次做标记都多1个（期限选「一直」就会累计）——「每次准备阶段下降200」「3回合后」"),
    Block("material_count", "number", "数值", "召唤用的素材数量", hint="GetMaterialCount"),
    Block("battle_damage", "number", "数值", "那次战斗伤害", [("player", "谁受到的", "choice", PLAYERS)],
          show=lambda n: "%s受到的战斗伤害" % _opt(PLAYERS, n["player"]), hint="Duel.GetBattleDamage"),
    Block("attacked_count", "number", "数值", "这个回合攻击的次数", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "攻击的次数（某张卡）", hint="GetAttackedCount"),
    Block("prev_overlay_count", "number", "数值", "离场前的超量素材数", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "离场前的超量素材数（某张卡）", hint="GetPreviousOverlayCountOnField"),
    Block("scale_of", "number", "数值", "灵摆刻度", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "灵摆刻度（某张卡）", hint="GetLeftScale"),
    Block("text_atk_of", "number", "数值", "卡上写的攻击力", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "卡上写的攻击力（某张卡）", hint="GetTextAttack"),
    Block("text_def_of", "number", "数值", "卡上写的守备力", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "卡上写的守备力（某张卡）", hint="GetTextDefense"),
    Block("prev_atk_of", "number", "数值", "离场前的攻击力", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "离场前的攻击力（某张卡）", hint="GetPreviousAttackOnField"),
    Block("rank_of", "number", "数值", "阶级", slots=[("card", "哪张卡", "cards", 1)], show=lambda n: "阶级（某张卡）"),
    Block("link_of", "number", "数值", "连接值", slots=[("card", "哪张卡", "cards", 1)], show=lambda n: "连接值（某张卡）"),
    Block("turn_count", "number", "数值", "这个回合的次数", [("player", "谁", "choice", PLAYERS), ("what", "什么", "choice", ACTIVITIES)],
          show=lambda n: "这个回合%s%s" % (_opt(PLAYERS, n["player"]), _opt(ACTIVITIES, n["what"])),
          hint="Duel.GetActivityCount；抽卡张数由这张卡自己记"),
    Block("turn_number", "number", "数值", "第几回合", hint="Duel.GetTurnCount"),
    Block("chain_count", "number", "数值", "现在的连锁数", hint="Duel.GetCurrentChain：「连锁3以上」"),
    Block("declared_num", "number", "数值", "宣言的等级", hint="配合「让玩家宣言」等级"),
    Block("dice_value", "number", "数值", "骰子的点数", hint="配合「掷骰子」"),
    Block("event_value", "number", "数值", "那次的数值", hint="ev：那次伤害 / 回复的数值（时机是受到伤害等）"),
    Block("counter_of", "number", "数值", "指示物的数量", [("counter", "种类", "choice", COUNTERS)],
          [("card", "哪张卡（几张时合计）", "cards", 1)], show=lambda n: "%s的数量" % _opt(COUNTERS, n["counter"]),
          hint="GetCounter"),
    Block("sum_of", "number", "数值", "合计", [("stat", "合计什么", "choice", STATS)], [("cards", "哪些卡", "cards", 1)],
          show=lambda n: "%s的合计" % _opt(STATS, n["stat"]), hint="Group.GetSum"),
    Block("name_kinds", "number", "数值", "卡名的种类数", slots=[("cards", "哪些卡", "cards", 1)],
          hint="GetClassCount(Card.GetCode)：「卡名不同的卡的数量」"),
    Block("base_atk_of", "number", "数值", "原本攻击力", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "原本攻击力（某张卡）", hint="GetBaseAttack"),
    Block("base_def_of", "number", "数值", "原本守备力", slots=[("card", "哪张卡", "cards", 1)],
          show=lambda n: "原本守备力（某张卡）", hint="GetBaseDefense"),
    Block("lp_of", "number", "数值", "基本分", [("player", "谁的", "choice", PLAYERS)],
          show=lambda n: "%s的基本分" % _opt(PLAYERS, n["player"])),
    Block("math", "number", "数值", "加减乘除", [("op", "运算", "choice", [("+", "+"), ("-", "−"), ("*", "×"), ("//", "÷（取整）")])],
          [("left", "左边", "number", 1), ("right", "右边", "number", 1)], show=lambda n: "计算：左边 %s 右边" % n["op"]),
    Block("compare", "cond", "条件", "比较", [("op", "比较", "choice", CMPS)],
          [("left", "左边", "number", 1), ("right", "右边", "number", 1)],
          show=lambda n: "比较：左边 %s 右边" % _opt(CMPS, n["op"])),
    Block("exists", "cond", "条件", "存在", slots=[("cards", "哪些卡", "cards", 1)], show=lambda n: "存在这样的卡"),
    Block("turn", "cond", "条件", "谁的回合", [("player", "谁的", "choice", PLAYERS)],
          show=lambda n: "%s回合" % _opt(PLAYERS, n["player"])),
    Block("phase", "cond", "条件", "阶段", [("phase", "现在是（可以勾几个）", "multi", PHASES)],
          show=lambda n: "现在是%s" % _opt(PHASES, n["phase"]), hint="Duel.GetCurrentPhase / IsMainPhase"),
    Block("coin_heads", "cond", "条件", "硬币是表", hint="配合「投掷硬币」"),
    Block("coin_right", "cond", "条件", "猜中了", hint="配合「投掷硬币」先猜里表"),
    Block("can_chain_attack", "cond", "条件", "这张卡还能继续攻击", hint="Duel.IsChainAttackable"),
    Block("not_sent_this_turn", "cond", "条件", "不是这张卡送去墓地的回合", hint="aux.exccon：「这个效果在这张卡送去墓地的回合不能发动」"),
    Block("player_affected", "cond", "条件", "玩家正受到某种效果",
          [("player", "谁", "choice", PLAYERS), ("code", "效果代码", "code", None)],
          show=lambda n: "%s受到「%s」" % (_opt(PLAYERS, n["player"]), code_zh(n["code"])), hint="Duel.IsPlayerAffectedByEffect"),
    Block("can_enter_bp", "cond", "条件", "这个回合还能进行战斗阶段", hint="Duel.IsAbleToEnterBP"),
    Block("can_normal_draw", "cond", "条件", "自己这个回合能进行通常抽卡", hint="aux.IsPlayerCanNormalDraw"),
    Block("this_battled", "cond", "条件", "这张卡这个回合进行过战斗", hint="GetBattledGroupCount()>0"),
    Block("this_attacked", "cond", "条件", "这张卡这个回合攻击过", hint="GetAttackAnnouncedCount()>0"),
    Block("gemini_state", "cond", "条件", "这张卡是再度召唤的状态", hint="aux.IsDualState：二重怪兽的效果都要放这个条件"),
    Block("union_state", "cond", "条件", "这张卡当作装备卡装备中", hint="aux.IsUnionState：同盟怪兽装备时的效果"),
    Block("chain_is", "cond", "条件", "那个发动的是……", [("what", "是", "choice", CHAIN_KINDS)],
          show=lambda n: "那个发动的是%s" % _opt(CHAIN_KINDS, n["what"]), hint="时机是卡或效果发动时：re / 连锁信息"),
    Block("chain_does", "cond", "条件", "那个发动的效果会……", [("what", "会", "choice", CHAIN_CATS)],
          show=lambda n: "那个发动的效果会%s" % _opt(CHAIN_CATS, n["what"]),
          hint="re:IsHasCategory：「要让卡破坏的效果发动时」（时机是卡或效果发动）"),
    Block("materials_are", "cond", "条件", "这张卡召唤用的素材……",
          [("mode", "怎样", "choice", [("any", "里有这样的卡"), ("all", "全部是这样的卡")])],
          [("filter", "素材（解放的怪兽）满足", "filter", 0)],
          show=lambda n: "这张卡召唤用的素材%s" % ("里有这样的卡" if n["mode"] == "any" else "全部是这样的卡"),
          hint="GetMaterial：「把「X」怪兽解放对这张卡的上级召唤成功时」「用X为素材同调召唤的场合」"),
    Block("has_flag", "cond", "条件", "有标记", [("on", "标记在", "choice", FLAG_ON), ("name", "标记编号（0～9）", "int", 1)],
          show=lambda n: "%s有标记 %d" % (_opt(FLAG_ON, n["on"]), n["name"]), hint="GetFlagEffect（配合「做标记」）"),
    Block("card_is", "cond", "条件", "卡是这样的卡", slots=[("cards", "哪张卡", "cards", 1), ("filter", "满足", "filter", 0)],
          show=lambda n: "卡满足以下条件", hint="「这张卡是同调召唤的」「那只怪兽是对方的」"),
    Block("all_of", "cond", "条件", "并且", slots=[("items", "以下都满足", "cond", 0)]),
    Block("any_of", "cond", "条件", "或者", slots=[("items", "以下满足一个", "cond", 0)]),
    Block("not_cond", "cond", "条件", "不是", slots=[("item", "这个条件", "cond", 1)]),
)

# 积木栏的分类顺序
CATEGORY_ORDER = ["效果", "动作", "登记效果", "控制", "卡片", "卡片条件", "数值", "条件"]
KIND_ZH = {"hat": "效果", "stmt": "语句", "cards": "卡片", "number": "数值", "cond": "条件", "filter": "卡片条件",
           "target": "取对象", "option": "●选项"}


def new(key, **values):
    """新建一块积木（JSON 节点），values 覆盖默认选项。"""
    node = BLOCKS[key].defaults()
    node.update(values)
    if key == "effect" and not node.get("modes"):
        node.pop("modes", None)      # 绝大多数效果用不到，空着就不进存档
    return node


def fits(slot, key):
    """积木 key 能不能放进这个槽（类型对、并且是槽收的那几种）。"""
    b = BLOCKS[key]
    return b.kind == slot[2] and (slot[4] is None or key in slot[4])
