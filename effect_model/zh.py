"""从 Effect Model 生成规范的简体中文效果文本（与 Lua 出自同一份数据，二者不会互相矛盾）。

措辞以百鸽（ygocdb）的官方中文文本为准；同一个意思有几种写法时，按全卡库里的多数写法来
（例如不带来源区域时写「这张卡被送去墓地」，297 张对 8 张）。
模型只存语义，连接词、「作为对象的怪兽 / 那只怪兽」这类措辞都在这里按语境选（设计见 docs/v0.2-骨架设计.md）。
"""

from . import names
from .model import applies, effect_by_id, is_numbered, is_ref, limits_of, normalize
from .model.patterns import linked_count_times, same_original_name_ref

ZONE = {
    "hand": "手卡", "mzone": "场上", "szone": "魔法与陷阱区域", "field": "场上", "pzone": "灵摆区域", "fzone": "场地区域",
    "grave": "墓地", "deck": "卡组", "banished": "除外状态", "extra": "额外卡组",
}
SELF_AT = {"grave": "墓地的", "mzone": "场上的", "field": "场上的", "szone": "场上的", "pzone": "场上的", "hand": "手卡的"}
OWNER = {"you": "自己", "opp": "对方"}
SUBTYPE = {
    "pendulum": "灵摆", "effect": "效果", "tuner": "调整", "normal": "通常", "ritual": "仪式",
    "fusion": "融合", "synchro": "同调", "xyz": "超量", "link": "连接",
    "quick": "速攻", "continuous": "永续", "equip": "装备", "field": "场地", "counter": "反击",   # 魔法·陷阱的种类
}
POSITION = {"attack": "攻击表示", "defense": "守备表示", "faceup": "表侧表示", "facedown": "里侧表示",
            "faceup_attack": "表侧攻击表示", "faceup_defense": "表侧守备表示"}
RACE = {
    "warrior": "战士", "spellcaster": "魔法师", "fairy": "天使", "fiend": "恶魔", "zombie": "不死",
    "machine": "机械", "aqua": "水", "pyro": "炎", "rock": "岩石", "winged_beast": "鸟兽",
    "plant": "植物", "insect": "昆虫", "thunder": "雷", "dragon": "龙", "beast": "兽",
    "beast_warrior": "兽战士", "dinosaur": "恐龙", "fish": "鱼", "sea_serpent": "海龙",
    "reptile": "爬虫类", "psychic": "念动力", "divine": "幻神兽", "wyrm": "幻龙",
    "cyberse": "电子界", "illusion": "幻想魔",
}
ATTRIBUTE = {"earth": "地", "water": "水", "fire": "炎", "wind": "风", "light": "光", "dark": "暗", "divine": "神"}
STAT = {"atk": "攻击力", "def": "守备力"}
CMP_WORD = {"<=": "以下", ">=": "以上"}
KIND_NOUN = {"monster": "怪兽", "spell": "魔法卡", "trap": "陷阱卡", "spell_trap": "魔法·陷阱卡", "card": "卡"}
ACTIVATION_KINDS = {
    ("monster", "spell", "trap"): "魔法·陷阱·怪兽",
    ("monster",): "怪兽",
    ("spell", "trap"): "魔法·陷阱卡",
    ("spell",): "魔法卡",
    ("trap",): "陷阱卡",
}
INCLUDES = {
    "add_from_deck": "从卡组把卡加入手卡的效果",
    "ss_from_deck": "从卡组把怪兽特殊召唤的效果",
    "send_from_deck_to_gy": "从卡组把卡送去墓地的效果",
}
INCLUDE_INLINE = {"special_summon_from_gy": "从墓地把怪兽特殊召唤效果"}
SUMMON_WORD = {"normal_summon_success": "召唤", "special_summon_success": "特殊召唤", "flip_summon_success": "反转召唤"}
METHOD_WORD = {"fusion": "融合召唤", "synchro": "同调召唤", "xyz": "超量召唤", "link": "连接召唤",
               "ritual": "仪式召唤", "pendulum": "灵摆召唤"}
MATERIAL_WORD = {"fusion": "融合素材", "synchro": "同调素材", "xyz": "超量素材", "link": "连接素材"}
PHASE_NAME = {"draw": "抽卡阶段", "standby": "准备阶段", "main1": "主要阶段1", "battle": "战斗阶段",
              "main2": "主要阶段2", "end": "结束阶段"}
UNTIL_HEAD = {"end_of_turn": "这个回合，", "end_of_next_turn": "直到下个回合的结束时，"}
BOUND_VERB = {"banish": "除外", "add_to_hand": "加入手卡", "send_to_gy": "送去墓地", "special_summon": "特殊召唤",
              "destroy": "破坏", "release": "解放"}
COUNTER_NAME = {"spell": "魔力指示物"}
FORBID_WORD = {"summon": "召唤", "flip_summon": "反转召唤", "special_summon": "特殊召唤"}
NEGATES = ("negate_activation", "negate_effect")


# ---------------------------------------------------------------- 名词短语

def zone_phrase(who, where):
    zones = "·".join(dict.fromkeys(ZONE[w] for w in where))
    if who == "both":
        return zones if zones == "场上" else "自己或对方的" + zones
    if who == "you" and set(where) <= {"hand", "deck", "extra"}:     # 「从手卡·卡组把……」不写「自己的」
        return zones
    owner = OWNER[who]
    return owner + "的" + zones if len(where) > 1 else owner + zones


def noun_kind(filters, where=()):
    for f in filters:
        if "card_type" in f:
            ct = f["card_type"]
            if isinstance(ct, list):
                return "spell_trap" if set(ct) == {"spell", "trap"} else ct[0]
            return ct
    subs = {f["subtype"] for f in filters if "subtype" in f}
    if subs & {"quick", "equip", "field"}:          # 只有魔法卡才有的种类
        return "spell"
    if "counter" in subs:
        return "trap"
    if subs or (where and set(where) <= {"mzone", "linked"}):
        return "monster"
    return "card"


def measure(kind):
    return "只" if kind == "monster" else "张"


def noun_parts(filters, where=(), sel=None, ctx=None, kind=None):
    """返回 (量词, 名词短语, 放在数量前面的修饰)，如 ("只", "攻击力1500以下的灵摆怪兽", "")。"""
    card = ctx.card if ctx else None
    kind = kind or noun_kind(filters, where)
    pre, pos, stats, tribes, sets, subs, named = [], [], [], [], [], [], []
    sel = sel or {}
    if sel.get("position"):
        pos.append(POSITION[sel["position"]])
    elif sel.get("face") == "up":
        pos.append("表侧表示")
    elif sel.get("face") == "down":
        pos.append("里侧表示")
    for f in filters:
        if "position" in f:
            pos.append(POSITION[f["position"]])
        elif "subtype" in f:
            subs.append(SUBTYPE[f["subtype"]])
        elif "level" in f:
            op, n = f["level"]
            stats.append("%d星%s" % (n, CMP_WORD[op] + "的" if op in CMP_WORD else ""))
        elif "atk" in f or "def" in f:
            key = "atk" if "atk" in f else "def"
            op, n = f[key]
            stats.append("%s%d%s的" % (STAT[key], n, CMP_WORD.get(op, "")))
        elif "race" in f:
            tribes.append(RACE[f["race"]] + "族")
        elif "attribute" in f:
            tribes.append(ATTRIBUTE[f["attribute"]] + "属性")
        elif "set" in f:
            sets.append("「%s」" % f["set"])
        elif isinstance(f.get("name"), int):
            named.append("「%s」" % names.name_of(f["name"], card))
            if kind == "card" and names.is_monster(f["name"], card):
                kind = "monster"
        elif "not" in f and isinstance(f["not"].get("name"), int):
            pre.append("「%s」以外的" % names.name_of(f["not"]["name"], card))
        elif "not" in f and isinstance(f["not"].get("name"), dict) and ctx is not None:
            pre.append("和%s卡名不同的" % ctx.ref_noun(f["not"]["name"]["same_as"]["ref"]))
        elif "zh" in f:
            stats.append(f["zh"])
    same = "同名" if "name" in ((sel.get("relation") or {}).get("same") or []) else ""
    tribe = "·".join(tribes)
    if named and not (stats or tribe or sets or subs or same):     # 指定卡名时不再写「表侧表示」等修饰
        return measure(kind), "".join(named), "".join(pre)
    text = "".join(pos) + "".join(stats) + tribe + ("的" if tribe and sets else "") + "".join(sets) + same + "".join(subs)
    return measure(kind), text + KIND_NOUN[kind], "".join(pre)


def noun(filters, where=(), sel=None, ctx=None):
    """返回 (量词, 名词短语)。"""
    m, n, pre = noun_parts(filters, where, sel, ctx)
    return m, pre + n


class Ctx:
    """渲染一个效果时的上下文：对象、已绑定的结果。规则文字没有效果，eff 传 None。"""

    def __init__(self, card, eff):
        self.card = card
        self.eff = eff
        eff = eff or {}
        self.targets = {t["as"]: t["sel"] for t in eff.get("target", []) if t.get("as")}
        self.bound = {s["as"]: s for s in eff.get("cost", []) if s.get("as")}
        self.paid = set(self.bound)
        self.bullets = []
        self.mentioned = []         # 已经提到过的对象（决定说「那只怪兽」还是「作为对象的怪兽」）
        self.in_listener = False

    def ref_noun(self, name):
        if name == "self":
            return "这张卡"
        if name == "event":
            ev = (self.eff or {}).get("on") or {}
            return "那张发动的卡" if ev.get("event") == "effect_activated" else "那些怪兽"
        if name == "battle.you":
            return "那只怪兽"
        if name == "battle.opp":
            return "进行战斗的对方怪兽"
        if "." in name:                      # 别的效果留下的绑定：「为那个效果发动而解放的这张卡」
            eid, key = name.split(".", 1)
            src = effect_by_id(self.card, eid)
            step = next(s for s in src["cost"] + src["do"] if s.get("as") == key)
            in_cost = step in src["cost"]
            return "为那个效果发动而%s的这张卡" % BOUND_VERB[step["act"]] if in_cost else "那张卡"
        if name in self.targets:
            t = self.targets[name]
            kind = noun_kind(t["filter"], t["where"])
            if any(m != name for m in self.mentioned):
                return "作为对象的" + KIND_NOUN[kind]
            if t["count"] != 1:
                return "那些怪兽" if kind == "monster" else "那些卡"
            return "那只怪兽" if kind == "monster" else "那张卡"
        if name in self.bound:
            step = self.bound[name]
            what = step.get("what") or {}
            if is_ref(what) and what["ref"] in self.targets:
                t = self.targets[what["ref"]]
                kind = noun_kind(t["filter"], t["where"])
            elif step["act"] in ("special_summon", "create_token"):     # 特殊召唤出来的总是怪兽
                kind = "monster"
            elif name in self.paid or step["act"] == "select":
                kind = noun_kind(what.get("filter", []), what.get("where", ()))
            else:                            # 「这个效果加入手卡的卡」：不论选的是什么，都叫「卡」
                kind = "card"
            if name in self.paid:            # 代价里的卡：「那只怪兽」
                return "那只怪兽" if kind == "monster" else "那张卡"
            if step["act"] == "select":
                return "那些怪兽" if kind == "monster" else "那些卡"
            if step["act"] == "create_token":
                return "这个效果特殊召唤的衍生物"
            return "这个效果%s的%s" % (BOUND_VERB[step["act"]], KIND_NOUN[kind])
        raise KeyError(name)


def obj(sel, ctx):
    """动作的宾语：这张卡 / 那只怪兽 / 对方场上的怪兽全部 / 对方场上1只怪兽。"""
    if is_ref(sel):
        return ctx.ref_noun(sel["ref"])
    m, n, pre = noun_parts(sel.get("filter", []), sel["where"], sel, ctx)
    zone = zone_phrase(sel["who"], sel["where"])
    if sel.get("count") == "all":
        return "%s的%s%s全部" % (zone, pre, n)
    return "%s%s%d%s%s" % (zone, pre, sel.get("count", 1), m, n)


def scope_noun(sel, ctx):
    """不计数的范围：「场上的表侧表示怪兽」「被送去墓地的怪兽」。"""
    if is_ref(sel):
        return ctx.ref_noun(sel["ref"])
    _, n = noun(sel.get("filter", []), sel.get("where", ()), sel, ctx)
    if not sel.get("where"):
        return n
    return "%s的%s" % (zone_phrase(sel["who"], sel["where"]), n)


def from_form(sel, verb, ctx=None, pick=False):
    """「从卡组把1只攻击力1500以下的怪兽加入手卡」的句式；pick 时写「从卡组选1张卡除外」。"""
    m, n, pre = noun_parts(sel.get("filter", []), sel["where"], sel, ctx)
    zone = zone_phrase(sel["who"], sel["where"])
    count = sel.get("count", 1)
    if pre.startswith("和"):           # 「和那张发动的卡卡名不同的1张「魔弹」卡从卡组加入手卡」：宾语在前
        return "%s%d%s%s从%s%s" % (pre, count, m, n, zone, verb)
    return "从%s%s%s%d%s%s%s" % (zone, "选" if pick else "把", pre, count, m, n, verb)


def ba_form(sel, verb, ctx):
    """代价的句式：「把这张卡解放」「把自己的手卡·场上1张卡送去墓地」「把这张卡所连接区1只自己怪兽解放」。"""
    if is_ref(sel):
        return "把%s%s" % (ctx.ref_noun(sel["ref"]), verb)
    m, n = noun(sel.get("filter", []), sel["where"], sel, ctx)
    if sel["where"] == ["linked"]:
        return "把这张卡所连接区%d%s%s%s%s" % (sel.get("count", 1), m, OWNER[sel["who"]], n, verb)
    return "把%s%d%s%s%s" % (zone_phrase(sel["who"], sel["where"]), sel.get("count", 1), m, n, verb)


def single_zone(sel):
    """只从一个非场上的区域选（墓地、卡组、手卡……）：代价写成「从自己墓地把……除外」。"""
    return not is_ref(sel) and len(sel["where"]) == 1 and sel["where"][0] not in ("field", "mzone", "szone", "linked")


def value_text(v, ctx):
    """数值表达式：300 / 这张卡的超量素材数量×200 / 表侧表示破坏的怪兽的攻击力合计数值一半。"""
    if isinstance(v, int):
        return str(abs(v))
    times = linked_count_times(v)
    if times is not None:
        return "这张卡所连接区的怪兽数量×%d" % times
    if "mul" in v and len(v["mul"]) == 2 and isinstance(v["mul"][1], int):
        return "%s×%d" % (value_text(v["mul"][0], ctx), v["mul"][1])
    if "count" in v:
        ref = (v["count"] or {}).get("ref")
        if ref == "overlay":
            return "这张卡的超量素材数量"
        if ref == "materials":
            method = (ctx.card["summon"].get("materials") or {}).get("method", "fusion")
            return "作为这张卡的%s的怪兽数量" % MATERIAL_WORD[method]
    if "half" in v:
        return value_text(v["half"], ctx) + "一半"
    if "sum" in v:
        return "%s的%s合计数值" % (group_noun(v["of"], ctx), STAT[v["sum"]])
    if "stat" in v:
        of = v["of"]
        if is_ref(of, "battle.opp"):
            return "进行战斗的对方怪兽的%s数值" % STAT[v["stat"]]
        return "%s的%s数值" % (obj(of, ctx), STAT[v["stat"]])
    raise NotImplementedError("数值 %r 还没有中文写法" % v)


def group_noun(sel, ctx):
    """「表侧表示破坏的怪兽」：前面步骤绑定的一组卡，可带移动前状态的过滤。"""
    step = ctx.bound[sel["ref"]]
    face = "表侧表示" if {"previous": {"face": "up"}} in sel.get("filter", []) else ""
    kind = noun_kind((step.get("what") or {}).get("filter", []), (step.get("what") or {}).get("where", ()))
    return "%s%s的%s" % (face, BOUND_VERB[step["act"]], KIND_NOUN[kind])


# ---------------------------------------------------------------- 条件

_ONLY_OPP_MONSTERS = [
    {"cond": "card_count", "sel": {"who": "you", "where": ["mzone"]}, "cmp": ["==", 0]},
    {"cond": "card_count", "sel": {"who": "opp", "where": ["mzone"]}, "cmp": [">=", 1]},
]


def count_noun(sel):
    """「对方场上的卡数量」。"""
    _, n = noun(sel.get("filter", []), sel["where"], sel)
    return "%s的%s数量" % (zone_phrase(sel["who"], sel["where"]), n)


def cond_text(conds, ctx):
    # 「只有对方场上才有怪兽存在」是一个固定说法
    if conds == _ONLY_OPP_MONSTERS:
        return "只有对方场上才有怪兽存在"
    parts = []
    for c in conds:
        kind = c.get("cond")
        if kind == "card_count":
            sel = c["sel"]
            _, n = noun(sel.get("filter", []), sel["where"], sel, ctx)
            op, k = c["cmp"]
            zone = zone_phrase(sel["who"], sel["where"])
            if (op, k) == ("==", 0):
                parts.append("%s没有%s存在" % (zone, n))
            elif (op, k) == (">=", 1):
                parts.append("%s有%s存在" % (zone, n))
            else:
                m, _ = noun(sel.get("filter", []), sel["where"], sel, ctx)
                parts.append("%s的%s有%d%s%s存在" % (zone, n, k, m, CMP_WORD.get(op, "")))
        elif kind in ("own_turn", "opponent_turn"):
            parts.append(("自己" if kind == "own_turn" else "对方") + "回合")
        elif kind == "self_location" and c.get("activated_from") == "set":
            parts.append("盖放的这张卡发动")
        elif kind == "battle_participant":       # 伤害步骤的时段里由 window_text 并进去；单独出现时
            _, n = noun(c.get("filter", []), ["mzone"], ctx=ctx)
            parts.append("%s的%s进行战斗" % (OWNER[c.get("side", "you")], n))
        elif kind == "value_compare" and c["op"] == ">" and "count" in c["left"] and "count" in c["right"]:
            parts.append("%s比%s多" % (count_noun(c["left"]["count"]), count_noun(c["right"]["count"])[:-2]))
        elif kind == "raw":
            parts.append(c["zh"])
        else:
            raise NotImplementedError("条件 %r 还没有中文写法" % c)
    return "，".join(parts)


# ---------------------------------------------------------------- 事件

def kinds_phrase(kinds):
    return ACTIVATION_KINDS[tuple(sorted(kinds, key=["monster", "spell", "trap"].index))]


def _turn_prefix(turn):
    return {"you": "自己", "opp": "对方", "any": "自己·对方的"}.get(turn, "")


def event_text(eff, ctx):
    """返回 (事件短语带后缀, 被事件吸收的条件下标集合)。"""
    on = eff.get("on")
    absorbed = set()
    if not on:
        if eff["type"] == "quick" and not eff.get("window"):
            return "自己·对方回合", absorbed
        return "", absorbed
    ev = on["event"]
    timing = eff.get("timing")
    suffix = {"when": "时", "if": "的场合"}.get(timing, "时")
    if ev == "effect_activated":
        kinds = on.get("kinds", ["monster", "spell", "trap"])
        includes = on.get("includes", [])
        by_phrase = {"both": "自己或者对方", "opp": "对方", "you": "自己"}.get(on.get("by"))
        if on.get("what") == "card":                 # 卡的发动
            noun_ = kinds_phrase(kinds)
            if (on.get("where") or {}).get("column_of") == {"ref": "self"}:
                text = "和这张卡相同纵列有%s发动" % noun_
            elif by_phrase:
                text = "%s把%s发动" % (by_phrase, noun_)
            else:
                text = noun_ + "发动"
        elif "destroy_on_field" in includes:
            text = "要让场上的卡破坏的%s的效果发动" % kinds_phrase(kinds)
        elif len(includes) == 1 and includes[0] in INCLUDE_INLINE:
            text = "包含%s的%s的效果%s发动" % (INCLUDE_INLINE[includes[0]], kinds_phrase(kinds),
                                         "由对方" if on.get("by") == "opp" else "")
        elif includes:
            text = "包含以下其中任意种效果的%s的效果发动" % kinds_phrase(kinds)
            ctx.bullets.extend("●" + INCLUDES[x] for x in includes)
        elif on.get("targets"):
            t = on["targets"]
            _, n = noun(t.get("filter", []), t["where"], t, ctx)
            text = "%s的%s为对象的%s的效果%s发动" % (
                zone_phrase(t["who"], t["where"]), n, kinds_phrase(kinds), "由对方" if on.get("by") == "opp" else "")
        else:
            text = ("对方把%s的效果发动" if on.get("by") == "opp" else "%s的效果发动") % kinds_phrase(kinds)
    elif isinstance(ev, list) or ev in SUMMON_WORD:
        events = ev if isinstance(ev, list) else [ev]
        words = METHOD_WORD[on["method"]] if on.get("method") else "·".join(SUMMON_WORD[e] for e in events)
        if is_ref(on.get("subject"), "self"):
            text = "这张卡" + words
        else:
            text = {"opp": "对方", "you": "自己"}.get(on.get("by"), "") + "把怪兽" + words
    elif ev == "sent_to_gy":
        if "destroyed" in (on.get("reason") or []):
            text = "这张卡被破坏送去墓地"
        elif on.get("from") or on.get("turn"):
            text = "这张卡"
            if on.get("turn"):
                text += "在%s回合" % OWNER[on["turn"]]
            if on.get("from"):
                text += "从" + "·".join(dict.fromkeys(ZONE[w] for w in on["from"]))
            text += "送去墓地"
        else:
            text = "这张卡被送去墓地"
    elif ev == "attack_declared":
        text = {"opp": "对方怪兽", "you": "自己怪兽", "any": "自己或对方的怪兽"}[on.get("by", "any")] + "的攻击宣言"
    elif ev == "becomes_attack_target":
        state = ""
        for i, c in enumerate(eff["condition"]):
            if c.get("cond") == "material_possession" and c.get("cmp") == ["==", 0]:
                state = "没有超量素材的状态"
                absorbed.add(i)
        text = "这张卡%s被选择作为攻击对象" % state
    elif ev == "phase_window":
        prefix = ""
        for i, c in enumerate(eff["condition"]):
            if c.get("cond") == "named_card_used":
                ref = effect_by_id(ctx.card, c["effect"])
                prefix = "这张卡的%s的效果适用的回合的" % ref["label"]
                absorbed.add(i)
        return prefix + _turn_prefix(on.get("turn")) + PHASE_NAME[on["phase"]], absorbed
    elif ev == "phase_end":
        return _turn_prefix(on.get("turn")) + PHASE_NAME[on["phase"]] + "结束时", absorbed
    elif ev == "summon_attempt":
        who = {"both": "自己或对方", "opp": "对方", "you": "自己"}.get(on.get("by"), "")
        how = dict(METHOD_WORD, special="特殊召唤", normal="召唤", flip="反转召唤").get(on.get("method"), "特殊召唤")
        return "%s把怪兽%s之际" % (who, how), absorbed
    else:
        raise NotImplementedError("事件 %r 还没有中文写法" % ev)
    return text + suffix, absorbed


def window_text(eff, ctx):
    """没有事件、只限定时段的诱发即时效果：「自己的光属性怪兽进行战斗的从伤害步骤开始时到伤害计算前」。"""
    w = eff.get("window") or {}
    if w.get("phase") != "damage_step":
        return "", set()
    absorbed, who = set(), ""
    for i, c in enumerate(eff["condition"]):
        if c.get("cond") == "battle_participant":
            _, n = noun(c.get("filter", []), ["mzone"], ctx=ctx)
            who = "%s的%s进行战斗的" % (OWNER[c.get("side", "you")], n)
            absorbed.add(i)
    span = {("start", "before_calc"): "从伤害步骤开始时到伤害计算前"}[(w.get("from"), w.get("to"))]
    return who + span, absorbed


# ---------------------------------------------------------------- 动作

def _player(p):
    return OWNER.get(p, "")


def step_text(step, ctx, infix=""):
    act = step["act"]
    what = step.get("what")
    if what is not None and is_ref(what):
        ctx.mentioned.append(what["ref"])
    if act == "destroy":
        if what and not is_ref(what) and what.get("count") != "all":
            m, n = noun(what.get("filter", []), what["where"], what, ctx)
            return "选%s%d%s%s%s破坏" % (zone_phrase(what["who"], what["where"]), what["count"], m, n, infix)
        return obj(what, ctx) + infix + "破坏"
    if act == "banish":
        return banish_text(step, ctx, infix)
    if act in ("add_to_hand", "send_to_gy"):
        verb = "加入手卡" if act == "add_to_hand" else "送去墓地"
        if act == "add_to_hand" and is_ref(what, "self") and set(ctx.eff["range"]) & {"mzone", "field", "szone"}:
            return "这张卡回到手卡"
        if act == "add_to_hand" and is_ref(what) and (ctx.bound.get(what["ref"]) or {}).get("act") in ON_FIELD_ACTS:
            return obj(what, ctx) + infix + "回到手卡"      # 「这个效果特殊召唤的怪兽在结束阶段回到手卡」
        if is_ref(what) or what.get("count") == "all":
            return obj(what, ctx) + infix + verb
        return from_form(what, verb, ctx)
    if act == "return_to_extra":
        return obj(what, ctx) + "回到额外卡组"
    if act == "special_summon":
        if is_ref(what):
            where = ""
            t = ctx.targets.get(what["ref"])
            if step.get("player") == "you" and t and t["who"] != "you":
                where = "在自己场上"
            if "." in what["ref"] and "grave" in ctx.eff["range"]:
                where = "从墓地"
            return obj(what, ctx) + where + "特殊召唤"
        return from_form(what, "特殊召唤", ctx)
    if act == "set_spell_trap":
        return from_form(what, "在自己场上盖放", ctx)
    if act == "change_position":
        to = {"faceup": "表侧表示", "facedown": "里侧守备表示", "attack": "表侧攻击表示", "defense": "表侧守备表示"}[step["to"]]
        if step.get("when_exists") and what.get("count") == "all":
            _, n = noun(what.get("filter", []), what["where"], what, ctx)
            return "%s有%s存在的场合，那些全部变成%s" % (zone_phrase(what["who"], what["where"]), n, to)
        return obj(what, ctx) + "变成" + to
    if act == "draw":
        n = step.get("count", 1)
        if step.get("player") == "both":
            return "双方各自从卡组抽%d张" % n
        if ctx.in_listener:
            return "%s抽%d张" % (_player(step.get("player", "you")), n)
        return "%s从卡组抽%d张" % (_player(step.get("player", "you")), n)
    if act == "discard":
        players = (step.get("for_each") or {}).get("players_of")
        if players and ctx.bound.get(players["ref"], {}).get("act") == "draw":
            return "抽卡的玩家选自身%d张手卡丢弃" % what.get("count", 1)
        if not players and what.get("who") == "you" and what.get("where") == ["hand"] and not what.get("filter"):
            return "选%d张手卡丢弃" % what.get("count", 1)        # 「天使的施舍」：自己从卡组抽3张，那之后选2张手卡丢弃
        raise NotImplementedError("丢弃的这种写法还没有中文")
    if act == "negate_activation":
        return "那个发动无效"
    if act == "negate_effect":
        return "那个效果无效"
    if act == "negate_attack":
        return "那次攻击无效"
    if act == "negate_summon":
        return "那次特殊召唤无效"
    if act == "negate_card_effects":
        if not is_ref(what) and what.get("count") == "all":
            _, n = noun(what.get("filter", []), what["where"], what, ctx)
            return "%s的全部%s的效果无效化" % (zone_phrase(what["who"], what["where"]), n)
        if step.get("until") == "permanent":         # 「这个效果特殊召唤的怪兽的效果无效化」
            return "%s的效果无效化" % obj(what, ctx)
        until = {"end_of_turn": "直到回合结束时"}.get(step.get("until"), "")
        return "%s的效果%s无效" % (obj(what, ctx), until)
    if act == "select":
        if (step.get("for_each") or {}).get("players") == "both":
            m, n = noun(what.get("filter", []), what["where"], what, ctx)
            return "双方玩家各自选自身%s%d%s%s" % (ZONE[what["where"][0]], what.get("count", 1), m, n)
        raise NotImplementedError("选卡的这种写法还没有中文")
    if act == "swap_control":
        chosen = ctx.bound[what["ref"]]
        return "那%d只怪兽的控制权交换" % (2 * chosen["what"].get("count", 1))
    if act == "copy_effect":
        fields = "·".join({"name": "卡名", "effects": "效果"}[f] for f in step["fields"])
        until = {"end_phase": "直到结束阶段"}.get(step.get("until"), "")
        return "%s%s得到和%s的%s%s相同的%s" % (obj(step["to"], ctx), until, ctx.ref_noun(step["from"]["ref"]),
                                       "原本的" if step.get("original") else "", fields, fields)
    if act == "attach_xyz_material":
        return "%s作为%s的超量素材" % (obj(what, ctx), obj(step["to"], ctx))
    if act == "activate_from_deck":
        m, n = noun(what.get("filter", []), what["where"], what, ctx)
        return "从%s选%d%s%s发动" % (zone_phrase(what["who"], what["where"]), what.get("count", 1), m, n)
    if act == "one_of":
        verbs = "或".join({"add_to_hand": "加入手卡", "special_summon": "特殊召唤"}[a] for a in step["acts"])
        m, n = noun(what.get("filter", []), what["where"], what, ctx)
        return "从%s选%d%s%s%s" % (zone_phrase(what["who"], what["where"]), what.get("count", 1), m, n, verbs)
    if act == "perform_summon" and step.get("method") == "ritual":
        mat, mon = step["materials"], step["monster"]
        _, mat_n = noun(mat.get("filter", []), mat["where"], mat, ctx)
        m, mon_n = noun(mon.get("filter", []), mon["where"], mon, ctx)
        rule = {"==": "等级合计直到变成和仪式召唤的怪兽相同为止"}[step["value"]["op"]]
        return "%s，把%s的%s%s，从%s把%d%s%s仪式召唤" % (
            rule, zone_phrase(mat["who"], mat["where"]), mat_n, {"grave": "送去墓地"}[mat["destination"]],
            zone_phrase(mon["who"], mon["where"]), mon.get("count", 1), m, mon_n)
    if act == "create_token":
        t = step["token"]
        stats = "攻/守%d" % t["atk"] if t["atk"] == t["def"] else "攻%d/守%d" % (t["atk"], t["def"])
        pos = {"defense": "守备表示", "attack": "攻击表示"}.get(step.get("position"), "")
        return "在%s场上把%d只「%s」（%s族·%s·%d星·%s）%s特殊召唤" % (
            _player(step.get("player", "you")), step.get("count", 1), t["name"], RACE[t["race"]],
            ATTRIBUTE[t["attribute"]], t["level"], stats, pos)
    if act == "schedule_operation":
        return schedule_text(step, ctx)
    if act == "win_duel":
        return "%s决斗胜利" % _player(step.get("player", "you"))
    if act == "toss_coin":
        return "进行%d次投掷硬币%s" % (step.get("count", 1), "，对里表作猜测" if step.get("call") else "")
    if act == "branch":
        parts = []
        for case in step["cases"]:
            c = case["if"]
            head = {True: "猜中的场合，", False: "猜错的场合，"}[c["called_right"]]
            parts.append(head + steps_text(case["do"], ctx))
        return "。".join(parts)
    if act == "damage":
        who = _player(step.get("player", "you"))
        if step.get("player", "you") == "you":
            return "%s受到%s的伤害" % (who, value_text(step["amount"], ctx))
        return "给与%s%s伤害" % (who, value_text(step["amount"], ctx))
    if act == "add_counter":
        cap = (ctx.card["counters"].get(step["counter"]) or {}).get("max")
        return "给%s放置%d个%s%s" % (obj(what, ctx), step.get("count", 1), COUNTER_NAME[step["counter"]],
                                 "（最多%d个）" % cap if cap else "")
    if act == "apply_continuous":
        return apply_text(step, ctx)
    if act == "raw":
        return step["zh"]
    raise NotImplementedError("动作 %r 还没有中文写法" % act)


def banish_text(step, ctx, infix=""):
    what = step["what"]
    if infix and is_ref(what):                       # 「这个效果特殊召唤的怪兽在结束阶段除外」
        return obj(what, ctx) + infix + "除外"
    if step.get("by") == "opp" and step.get("face") == "down":
        count = what.get("count") or {}
        head = ""
        if isinstance(count, dict) and "until_equal" in count:
            head = "直到变成和%s相同为止，" % count_noun(count["until_equal"]["count"])
        _, n = noun(what.get("filter", []), what["where"], what, ctx)
        return "%s对方必须把自身%s的%s里侧除外" % (head, ZONE[what["where"][0]], n)
    if not is_ref(what) and any(isinstance(f.get("name"), dict) and "ref" in f["name"] for f in what.get("filter", [])):
        return "宣言的%d张卡从%s除外" % (what.get("count", 1), zone_phrase(what["who"], what["where"]))
    if not is_ref(what) and what.get("count") != "all":
        return from_form(what, "除外", ctx, pick=not what.get("filter"))
    return obj(what, ctx) + "除外"


def schedule_text(step, ctx):
    at = step["at"]
    if "turn" in at:
        return "以发动的回合为第1回合来计算的第%d回合的回合结束时%s" % (at["turn"], steps_text(step["do"], ctx))
    if at.get("nth"):
        return "这张卡的发动后第%d次的%s%s，%s" % (at["nth"], _player(at.get("player", "you")), PHASE_NAME[at["phase"]],
                                          steps_text(step["do"], ctx))
    infix = "在%s" % PHASE_NAME[at["phase"]]
    return "。".join(step_text(s, ctx, infix) for s in step["do"])


def apply_text(step, ctx):
    ap = applies(step)[0]
    until = step.get("until")
    if "on" in ap:     # 「这个回合中，以下效果适用。●每次……，……。」
        inner = Ctx(ctx.card, {"target": [], "condition": []})
        inner.in_listener = True
        ev, _ = event_text({"type": "listener", "on": ap["on"], "timing": "when", "condition": []}, inner)
        body = steps_text(ap["do"], inner)
        ctx.bullets.append("●每次%s，%s。" % (ev[:-1] if ev.endswith("时") else ev, body))
        return {"end_of_turn": "这个回合中"}[until] + "，以下效果适用"
    cont = ap["cont"]
    head = UNTIL_HEAD.get(until, "") if isinstance(until, str) else ""
    if cont == "cannot_activate":
        name = ctx.ref_noun(ap["which"]["same_name_as"]["ref"])
        return head + "%s不能把%s以及那些同名卡的效果发动" % (OWNER[ap.get("player", "you")], name)
    if cont == "effects_disabled" and same_original_name_ref(ap):
        ref = same_original_name_ref(ap)
        name = ctx.ref_noun(ref)
        kind = "怪兽" if name.endswith("怪兽") else "卡"
        return head + "%s以及原本卡名和那%s%s相同的%s的效果无效化" % (name, "只" if kind == "怪兽" else "张", kind, kind)
    if cont == "cannot_change_position":
        return head + "%s不能把表示形式变更" % ctx.ref_noun(ap["affects"]["ref"])
    if cont == "skip_phase":
        return "下次的%s%s跳过" % (OWNER[ap["player"]], PHASE_NAME[ap["phase"]])
    if cont == "cannot_release" and ap.get("for") == ["tribute_summon"]:
        return "这衍生物不能为上级召唤而解放"
    # 处理的「后果」：作用在前一步的卡上（「这个效果特殊召唤的怪兽不能攻击」「……从场上离开的场合除外」）
    if cont == "cannot_release" and is_ref(ap.get("affects")):
        return head + "%s不能解放" % obj(ap["affects"], ctx)
    if cont == "cannot_attack" and is_ref(ap.get("affects")):
        return head + "%s不能攻击" % obj(ap["affects"], ctx)
    if cont == "cannot_use_material" and is_ref(ap.get("affects")):
        return head + "%s不能作为%s" % (obj(ap["affects"], ctx), MATERIAL_WORD[ap["method"]])
    if cont == "redirect_destination" and ap.get("from_dest") == "leave_field" and is_ref(ap.get("affects")):
        return "%s从场上离开的场合%s" % (obj(ap["affects"], ctx), {"banished": "除外"}[ap["to_dest"]])
    if cont == "atk_update" and len(applies(step)) == 1:
        v = ap["value"]
        span = {"end_of_turn": "直到回合结束时"}.get(until, "")
        return "%s的攻击力%s%s%s" % (obj(ap["affects"], ctx), span, "下降" if isinstance(v, int) and v < 0 else "上升",
                                 value_text(v, ctx))
    aps = applies(step)
    if all(a["cont"] in SIMPLE_CONT + ("atk_update",) for a in aps):
        # 「这个回合，那只怪兽不会被战斗·效果破坏」「这个回合，这张卡可以直接攻击」
        return head + (_merged_text(aps, ctx) or "，".join(simple_cont_text(a, ctx) for a in aps))
    raise NotImplementedError("持续效果 %r 还没有中文写法" % cont)


def _joins_as_bing(prev, step):
    """「那个发动无效并破坏」：无效之后把同一个发动的卡破坏，固定写成「并破坏」。"""
    return (prev["act"] in NEGATES and step["act"] == "destroy" and is_ref(step.get("what"), "chain.card")
            and step.get("link") in ("and_if_you_do", "and"))


MOVE_ACTS = ("destroy", "banish", "send_to_gy", "add_to_hand", "special_summon", "return_to_extra", "change_position",
             "set_spell_trap")
ON_FIELD_ACTS = ("special_summon", "create_token", "set_spell_trap")     # 做完以后卡在场上的动作


def consequence_ref(step):
    """处理的「后果」作用在哪一步的卡上：这一步引用的前一步结果的名字；不是后果时为 None。"""
    act = step.get("act")
    if act == "schedule_operation":
        what = (step.get("do") or [{}])[0].get("what")
    elif act == "apply_continuous":
        ap = applies(step)[0]
        what = ap.get("affects") or ((ap.get("which") or {}).get("same_name_as"))
    else:
        what = step.get("what")
    if is_ref(what) and what["ref"] not in ("self", "chain", "chain.card", "event") and "." not in what["ref"]:
        return what["ref"]
    return None


def optional_text(step, s):
    """玩家可以选择做不做的一步：「那之后，可以从自己墓地把1张陷阱卡在自己场上盖放」「可以把那只怪兽破坏」
    「自己可以从卡组抽1张」。"""
    if s.startswith("自己") and step["act"] == "draw":
        return "自己可以" + s[2:]
    if is_ref(step.get("what")) and step["act"] in MOVE_ACTS:
        return ("可以让" if "回到" in s else "可以把") + s       # 「可以让这张卡回到手卡」
    return "可以" + s


def steps_text(steps, ctx):
    out = ""
    for i, step in enumerate(steps):
        if i and _joins_as_bing(steps[i - 1], step):
            out += "并破坏"
            continue
        s = step_text(step, ctx)
        if step.get("optional"):
            s = optional_text(step, s)
        if step.get("if"):
            s = cond_text(step["if"], ctx) + "的场合，" + s
        if step.get("as"):
            ctx.bound[step["as"]] = step
        link = step.get("link", "also")
        ref = consequence_ref(step)
        if i and ref and ref == consequence_ref(steps[i - 1]) and link in ("also", "and_if_you_do") and not step.get("if"):
            subject = ctx.ref_noun(ref)
            if s.startswith(subject) and s != subject:
                # 同一些卡的几个后果并成一句：「这个效果特殊召唤的怪兽的效果无效化，在结束阶段破坏」
                rest = s[len(subject):]
                out += "，" + (rest[1:] if rest.startswith("的") else rest)
                continue
        if i == 0:
            out = s
        elif link == "and_if_you_do":
            out += "，" + s
        elif link in ("then", "also_after_that"):
            out += "。那之后，" + s
        elif link == "and":
            out += "并" + s
        else:
            out += "。" + s
    return out


# ---------------------------------------------------------------- 效果

def head_segments(eff, ctx):
    """发动部分的各段（不含「才能发动」）。"""
    ev, absorbed = event_text(eff, ctx)
    win, absorbed2 = window_text(eff, ctx)
    absorbed |= absorbed2
    conds = [c for i, c in enumerate(eff["condition"]) if i not in absorbed]
    segs = []
    for _, lim in limits_of(ctx.card, eff, scope="card"):
        segs.append(per_turn_head(lim["n"]))
    for _, lim in limits_of(ctx.card, eff, scope="face_up"):
        segs.append("只在这张卡表侧表示存在才有%d次" % lim["n"])
    lead = len(segs)
    if ev:
        segs.append(ev)
    if win:
        segs.append(win)
    if conds:
        segs.append(cond_text(conds, ctx) + "的场合")
    for d in eff.get("declare", []):
        segs.append({"card_name": "宣言1个卡名"}[d["kind"]])
    for step in eff["cost"]:
        segs.append(cost_text(step, ctx))
    for t_ in eff["target"]:
        segs.append("以%s为对象" % obj(t_["sel"], ctx))
    if len(segs) == lead and eff["type"] == "ignition":
        segs.append("自己主要阶段")
    return segs


def head_text(eff, ctx):
    """「……时，把……才能发动。」部分。"""
    segs = head_segments(eff, ctx)
    if not segs:
        return ""
    mandatory = eff["type"] in ("trigger", "quick") and not eff.get("optional", True)
    return "，".join(segs) + ("发动。" if mandatory else "才能发动。")


def cost_text(step, ctx):
    act = step["act"]
    what = step.get("what")
    if act == "discard":
        return "把这张卡从手卡丢弃"
    if act == "send_to_gy":
        if is_ref(what, "self"):
            return "把这张卡从手卡送去墓地" if ctx.eff["range"] == ["hand"] else "把这张卡送去墓地"
        if single_zone(what):
            return from_form(what, "送去墓地", ctx)
        return ba_form(what, "送去墓地", ctx)
    if act == "release":
        return ba_form(what, "解放", ctx)
    if act == "detach_xyz_material":
        return "把这张卡%d个超量素材取除" % step.get("count", 1)
    if act == "banish":
        if is_ref(what, "self"):
            return "把%s这张卡除外" % SELF_AT.get((ctx.eff.get("range") or [""])[0], "")
        if single_zone(what):
            return from_form(what, "除外", ctx)
        return ba_form(what, "除外", ctx)
    if act == "pay_lp":
        return "支付%d基本分" % step["amount"]
    if act == "remove_counter":
        return "把%s%d个%s取除" % (obj(step["from"], ctx), step.get("count", 1), COUNTER_NAME[step["counter"]])
    raise NotImplementedError("代价 %r 还没有中文写法" % act)


def continuous_text(eff, ctx):
    aps = applies(eff)
    prefix = ""
    if eff["block"] == "pendulum":
        prefix = ""
    elif ctx.card["card"]["kind"] != "monster" and eff["range"] == ["szone"]:
        prefix = "只要这张卡在魔法与陷阱区域存在，"
    elif eff.get("on") or any(not is_ref(ap.get("affects"), "self") for ap in aps):
        prefix = "只要这张卡在怪兽区域存在，"
    if eff.get("on"):          # 不入连锁的「每次……，……」
        inner = Ctx(ctx.card, eff)
        ev, _ = event_text(dict(eff, timing="when"), inner)
        return prefix + "每次%s，%s" % (ev[:-1], steps_text(eff["do"], inner))
    text = prefix + _continuous_body(aps, eff, ctx)
    if eff.get("cannot_be_negated"):
        text += "。这个效果不会被无效化"
    return text


# 永续第一批：只看效果内容的写法（主语由 _subject 给出）。键是调研细项 cont.* 去掉前缀
SIMPLE_CONT = ("def_update", "change_level", "indestructible_battle", "indestructible_effect",
               "indestructible_count", "cannot_be_targeted", "piercing", "direct_attack", "cannot_direct_attack",
               "extra_attack", "attack_all", "cannot_be_attack_target", "attack_target_restriction")
DESTROY_BY = {("battle",): "战斗", ("effect",): "效果", ("battle", "effect"): "战斗·效果"}


def _subject(ap, ctx, on_field=False):
    """「这张卡」「自己场上的战士族怪兽」。on_field：「场上的这张卡」（效果破坏抗性、不会成为效果的对象的多数写法）。"""
    aff = ap.get("affects") or {"ref": "self"}
    if is_ref(aff, "self") and on_field:
        return "场上的这张卡"
    return obj(aff, ctx) if is_ref(aff) else scope_noun(aff, ctx)


def _by_opp(ap):
    return "对方的" if ap.get("by") == "opp" else ""


def simple_cont_text(ap, ctx):
    cont = ap["cont"]
    if cont == "def_update":
        v = ap["value"]
        return "%s的守备力%s%s" % (_subject(ap, ctx), "下降" if isinstance(v, int) and v < 0 else "上升", value_text(v, ctx))
    if cont == "change_level" and "set" in ap:          # 「等级变成1星」
        return "%s的等级变成%d星" % (_subject(ap, ctx), ap["set"])
    if cont == "change_level":                          # 「等级上升2星」
        n = ap["value"]
        return "%s的等级%s%d星" % (_subject(ap, ctx), "下降" if n < 0 else "上升", abs(n))
    if cont == "indestructible_battle":
        return "%s不会被战斗破坏" % _subject(ap, ctx)
    if cont == "indestructible_effect":
        return "%s不会被%s效果破坏" % (_subject(ap, ctx, on_field=True), _by_opp(ap))
    if cont == "indestructible_count":
        n = ap.get("n", 1)
        times = "只有1次" if n == 1 else "最多%d次" % n
        return "%s1回合%s不会被%s破坏" % (_subject(ap, ctx), times, DESTROY_BY[tuple(ap.get("by", ["battle"]))])
    if cont == "cannot_be_targeted":
        opp = ap.get("by") == "opp"
        return "%s不会成为%s效果的对象" % (_subject(ap, ctx, on_field=not opp), _by_opp(ap))
    if cont == "piercing":
        return "%s向守备表示怪兽攻击的场合，给与攻击力超过那个守备力的数值的战斗伤害" % _subject(ap, ctx)
    if cont == "direct_attack":
        return "%s可以直接攻击" % _subject(ap, ctx)
    if cont == "cannot_direct_attack":
        return "%s不能直接攻击" % _subject(ap, ctx)
    if cont == "extra_attack":
        return "%s在同1次的战斗阶段中可以作%d次攻击" % (_subject(ap, ctx), ap.get("n", 2))
    if cont == "attack_all":
        return "%s可以向对方怪兽全部各作1次攻击" % _subject(ap, ctx)
    if cont == "cannot_be_attack_target":
        return "对方怪兽不能选择%s作为攻击对象" % _subject(ap, ctx)
    if cont == "attack_target_restriction" and is_ref(ap.get("only"), "self"):
        return "对方不能选择其他怪兽作为攻击对象"
    raise NotImplementedError("永续效果 %r 还没有中文写法" % cont)


def _merged_text(aps, ctx):
    """几条一起适用、官方并成一句的：「攻击力·守备力上升」「不会被战斗·效果破坏」「不会成为……的对象，不会被……破坏」。"""
    conts = [ap["cont"] for ap in aps]
    a, b = aps[0], aps[-1]
    same = len(aps) == 2 and a.get("affects", {"ref": "self"}) == b.get("affects", {"ref": "self"})
    if same and conts == ["atk_update", "def_update"] and a["value"] == b["value"]:
        v = a["value"]
        return "%s的攻击力·守备力%s%s" % (_subject(a, ctx), "下降" if isinstance(v, int) and v < 0 else "上升", value_text(v, ctx))
    if same and conts == ["indestructible_battle", "indestructible_effect"] and not b.get("by"):
        return "%s不会被战斗·效果破坏" % _subject(a, ctx)
    if same and conts == ["cannot_be_targeted", "indestructible_effect"] and a.get("by") == b.get("by"):
        return "%s不会成为%s效果的对象，不会被%s效果破坏" % (_subject(a, ctx, on_field=True), _by_opp(a), _by_opp(b))
    return None


def _continuous_body(aps, eff, ctx):
    conts = [ap["cont"] for ap in aps]
    if len(aps) > 1:
        merged = _merged_text(aps, ctx)
        if merged:
            return merged
        if all(c in SIMPLE_CONT for c in conts):
            return "，".join(simple_cont_text(ap, ctx) for ap in aps)
    if conts[0] in SIMPLE_CONT and len(aps) == 1:
        return simple_cont_text(aps[0], ctx)
    if sorted(conts) == ["quickplay_opponent_hand", "trap_from_hand"]:
        if any("set" not in f and "card_type" not in f for a in aps for f in a.get("which", [])):
            raise NotImplementedError("从手卡发动目前只能按字段限定")
        sets = "".join("「%s」" % f["set"] for f in aps[0].get("which", []) if "set" in f)
        return "自己·对方回合%s可以把%s魔法·陷阱卡从手卡发动" % (_player(aps[0].get("player", "you")), sets)
    ap = aps[0]
    cont = ap["cont"]
    if cont == "cannot_attack" and ap.get("declare"):
        return "%s怪兽不能攻击宣言" % OWNER[ap["affects"]["who"]]
    if cont == "atk_update":
        v = ap["value"]
        word = "下降" if isinstance(v, int) and v < 0 else "上升"
        target = obj(ap["affects"], ctx) if is_ref(ap["affects"]) else scope_noun(ap["affects"], ctx)
        return "%s的攻击力%s%s" % (target, word, value_text(v, ctx))
    if cont == "atk_set":
        return "%s的%s攻击力变成%s" % (obj(ap["affects"], ctx), "原本" if ap.get("original") else "",
                                  value_text(ap["value"], ctx))
    if cont == "battle_damage_change" and ap.get("value") == {"mul": 2} and ap.get("against") == "opp_monster":
        return "这张卡用和对方怪兽的战斗给与对方的战斗伤害变成2倍"
    if cont == "battle_damage_zero" and ap.get("optional"):
        inv = ap["involving"]
        _, n = noun(inv.get("filter", []), inv["where"], inv, ctx)
        return "可以把%s的%s的战斗发生的对%s的战斗伤害变成0" % (OWNER[inv["who"]], n, OWNER[inv["who"]])
    if cont == "immune_effect":
        subject = obj(ap["affects"], ctx)
        if any(c.get("cond") == "summon_history" for c in eff["condition"]):
            method = next(c["method"] for c in eff["condition"] if c.get("cond") == "summon_history")
            subject = METHOD_WORD[method] + "的" + subject
        src = ap["from"]
        # 「对方发动的效果」「其他卡的效果」「对方的效果」
        who = (OWNER[src["player"]] if src.get("player") else "其他卡") + ("发动的" if src.get("activated") else "的")
        if is_ref((src.get("except") or {}).get("targets"), "self"):
            return "%s不受除以这张卡为对象的效果以外的%s效果影响" % (subject, who)
        return "%s不受%s效果影响" % (subject, who)
    if cont == "effects_disabled":
        return "%s的效果无效化" % scope_noun(ap["affects"], ctx)
    if cont == "redirect_destination":
        _, n = noun(ap["affects"].get("filter", []), (), ap["affects"], ctx)
        return "被送去%s的%s不去%s而%s" % (ZONE[ap["from_dest"]], n, ZONE[ap["from_dest"]],
                                    {"banished": "除外"}[ap["to_dest"]])
    if cont == "cannot_special_summon":
        excepts = [f["not"] for f in ap.get("which", []) if "not" in f]
        if excepts:
            _, n = noun(excepts, ["mzone"], ctx=ctx)
            return "%s不是%s不能特殊召唤" % (OWNER[ap.get("player", "you")], n)
        return "%s不能特殊召唤" % OWNER[ap.get("player", "you")]
    raise NotImplementedError("永续效果 %r 还没有中文写法" % cont)


def procedure_text(eff, ctx):
    head = ""
    if eff["condition"]:
        head = cond_text(eff["condition"], ctx) + "的场合，"
    where = "·".join(ZONE[w] for w in eff["range"])
    if eff["cost"]:
        return head + "这张卡可以%s，从%s特殊召唤" % (cost_text(eff["cost"][0], ctx), where)
    return head + "这张卡可以从%s特殊召唤" % where


def rule_text(rule, ctx):
    r = rule["rule"]
    if r == "lasting":
        who = OWNER[rule.get("count_on", "opp")]
        return "这张卡发动后继续留在场上，用%s回合计算的%d回合后的%s结束阶段破坏。" % (who, rule["turns"], who)
    if r == "activate_from_hand":
        return cond_text(rule["condition"], ctx) + "的场合，这张卡的发动从手卡也能用。"
    raise NotImplementedError("规则 %r 还没有中文写法" % r)


def activation_line(eff, ctx):
    """不编号的卡的发动：「支付1000基本分才能把这张卡发动。」"""
    segs = []
    if eff["condition"]:
        segs.append(cond_text(eff["condition"], ctx) + "的场合")
    segs.extend(cost_text(step, ctx) for step in eff["cost"])
    return "，".join(segs) + "才能把这张卡发动。"


def modes_text(eff, ctx):
    """「●」列表：「可以支付1500基本分把以下效果发动。●……才能发动。……。」"""
    costs = "".join(cost_text(s, ctx) for s in eff["cost"])
    head = "可以%s把以下效果发动" % costs if costs else "可以从以下效果选择1个发动"
    for opt in eff["modes"]["options"]:
        sub = dict(eff, on=opt.get("on"), timing=opt.get("timing"), condition=opt.get("condition", []),
                   cost=[], target=opt.get("target", []), do=opt.get("do", []))
        sub_ctx = Ctx(ctx.card, sub)
        ctx.bullets.append("●" + head_text(sub, sub_ctx) + steps_text(sub["do"], sub_ctx) + "。")
    return head


def effect_text(eff, ctx):
    t = eff["type"]
    if t == "continuous":
        return continuous_text(eff, ctx) + "。"
    if t == "procedure":
        return procedure_text(eff, ctx) + "。"
    if eff.get("modes"):
        return modes_text(eff, ctx) + "。"
    body = steps_text(eff["do"], ctx)
    if t == "activation" and has_lasting(ctx.card) and eff["do"]:
        return "作为这张卡的发动时的效果处理，" + body + "。" + effect_restricts(eff, ctx)
    return head_text(eff, ctx) + body + "。" + effect_restricts(eff, ctx)


def has_lasting(card):
    return any(r["rule"] == "lasting" for r in card["rules"]) or \
        any(s in card["card"]["subtypes"] for s in ("continuous", "field", "equip"))


# ---------------------------------------------------------------- 素材行、出场规则、标题行

def materials_text(card):
    m = card["summon"].get("materials")
    if not m:
        return ""
    ctx = Ctx(card, None)
    method = m["method"]
    if method == "xyz":
        tribes = "·".join(noun([f], ["mzone"])[1][:-2] for f in m.get("filter", []))
        return "%s%d星怪兽×%d" % (tribes, m["level"], m["count"])
    if method == "synchro":
        tuner = noun(m["tuner"].get("filter", []), ["mzone"], ctx=ctx)[1][:-2] + "调整"
        _, non = noun(m["nontuner"].get("filter", []), ["mzone"], ctx=ctx)
        return "%s＋调整以外的%s%d只以上" % (tuner, non, m["nontuner"].get("min", 1))
    if method == "link":
        _, n = noun(m.get("filter", []), ["mzone"])
        return "%s%d只以上" % (n, m["min"])
    if method == "fusion":
        parts = []
        for item in m["list"]:
            if "name" in item:
                parts.append("「%s」" % names.name_of(item["name"], card))
            else:
                _, n = noun(item.get("filter", []), ["mzone"])
                parts.append(n + ("%d只以上" % item["min"] if item.get("min") else ""))
        return "＋".join(parts)
    return ""


def _procedure_line(card, p):
    ctx = Ctx(card, None)
    if p["kind"] == "contact":
        where = p["materials"]["where"]
        zone = "自己·对方场上" if where["who"] == "both" else zone_phrase(where["who"], where["where"])
        return "把%s的上记的卡%s的场合才能从额外卡组特殊召唤。" % (zone, {"grave": "送去墓地"}[p["materials"]["destination"]])
    if p["kind"] == "xyz_overlay":
        on = p["on"]
        lim = card["limits"].get(p.get("limit")) if p.get("limit") else None
        _, n = noun(on.get("filter", []), on["where"], on, ctx)
        return "「%s」%s也能在%s的%s上面重叠来超量召唤。" % (
            card["card"]["name"], per_turn_head(lim["n"]) if lim else "", zone_phrase(on["who"], on["where"]), n)
    if p["kind"] == "special":
        cost = p["cost"][0]
        what = cost["what"]
        rel = what.get("relation") or {}
        cannot = "".join("这张卡不能%s，" % METHOD_WORD[m] for m in card["summon"]["cannot"])
        if rel.get("diff") and rel.get("roles"):
            roles = "和".join("%s%d只" % ("调整" if {"subtype": "tuner"} in r["filter"] else "调整以外的怪兽", r["count"])
                             for r in rel["roles"])
            return "%s等级差直到%d为止从%s把%s送去墓地的场合才能特殊召唤。" % (
                cannot, rel["diff"]["value"], zone_phrase(what["who"], what["where"]), roles)
    raise NotImplementedError("出场手续 %r 还没有中文写法" % p["kind"])


def _restriction_line(r, card=None):
    if r.get("special_summon_once") == "turn":
        return "自己对「%s」1回合只能有1次特殊召唤。" % card["card"]["name"]
    if "cannot_special_summon_from" in r:
        return "这张卡不能从%s特殊召唤。" % "·".join(ZONE[w] for w in r["cannot_special_summon_from"])
    if "cannot_be_material" in r:
        return "这张卡不能作为%s。" % MATERIAL_WORD[r["cannot_be_material"]]
    raise NotImplementedError("出场限制 %r 还没有中文写法" % r)


def _permission_line(p):
    if p.get("for") == "link":
        return "这张卡连接召唤的场合，%s1只怪兽也能作为连接素材。" % zone_phrase(p["who"], p["where"])
    raise NotImplementedError("素材许可 %r 还没有中文写法" % p)


def labels(effs):
    return "".join(e["label"] for e in effs)


def per_turn_head(n):
    """效果开头的「1回合1次」；可以用多次时是「1回合最多2次」（No.15 机关傀儡-巨人杀手、蜂军风）。"""
    return "1回合1次" if n == 1 else "1回合最多%d次" % n


def _use_phrase(n, each=False):
    """「1回合只能使用1次」「1回合各能使用1次」；多次：「1回合可以使用最多2次」（No.80 狂装霸王 狂想战曲王）。"""
    if n == 1:
        return "1回合各能使用1次" if each else "1回合只能使用1次"
    return ("1回合各可以使用最多%d次" if each else "1回合可以使用最多%d次") % n


def limit_header(card, block):
    """「这个卡名的①的方法的特殊召唤1回合只能有1次，②③的效果1回合各能使用1次。」「这个卡名的卡在1回合只能发动1张。」
    额度的次数 n 大于 1 时按官方的多次写法：「1回合可以使用最多2次」「这个卡名的卡在1回合可以发动最多2张」。"""
    out = ""
    acts = [lim for e in card["effects"] if e["block"] == block
            for _, lim in limits_of(card, e, scope="name", unit="activate_card")]
    if acts:
        n = acts[0]["n"]
        out += "这个卡名的卡在1回合只能发动1张。" if n == 1 else "这个卡名的卡在1回合可以发动最多%d张。" % n
    effs = [e for e in card["effects"] if e["block"] == block and limits_of(card, e, scope="name", unit="use")
            or e["block"] == block and e["type"] == "procedure" and limits_of(card, e, scope="name")]
    if not effs:
        return out
    word = "灵摆效果" if block == "pendulum" else "效果"
    numbered = [e for e in card["effects"] if e["block"] == block and e["label"]]
    pieces = []
    procs = [e for e in effs if e["type"] == "procedure"]
    for n, group in _by_count(card, procs):
        pieces.append("%s的方法的特殊召唤%s" % (labels(group), "1回合只能有1次" if n == 1 else "1回合可以有最多%d次" % n))
    others = [e for e in effs if e["type"] != "procedure"]
    if others:
        groups = {}
        for e in others:
            groups.setdefault(limits_of(card, e, scope="name")[0][0], []).append(e)
        shared = [g for g in groups.values() if len(g) > 1]
        singles = [g[0] for g in groups.values() if len(g) == 1]
        if len(others) == 1 and len(numbered) == 1:
            pieces.append(word + _use_phrase(_name_n(card, others[0])))
        elif not shared:
            for n, group in _by_count(card, singles):
                pieces.append("%s的%s%s" % (labels(group), word, _use_phrase(n, each=len(group) > 1)))
        else:
            for g in shared:     # 几个效果共用一个额度：「①②的效果1回合只能有1次使用其中任意1个」
                n = _name_n(card, g[0])
                pieces.append("%s的%s%s" % (labels(g), word, "1回合只能有1次使用其中任意1个" if n == 1
                                           else "1回合合计可以使用最多%d次" % n))
            for n, group in _by_count(card, singles):
                pieces.append("%s的%s%s" % (labels(group), word, _use_phrase(n, each=len(group) > 1)))
    return out + "这个卡名的" + "，".join(pieces) + "。"


def _name_n(card, eff):
    return limits_of(card, eff, scope="name")[0][1]["n"]


def _by_count(card, effs):
    """按次数分组（保持卡面顺序）：[(n, [效果])]。次数都是 1 时就是原来的一组。"""
    out = {}
    for e in effs:
        out.setdefault(_name_n(card, e), []).append(e)
    return list(out.items())


# ---------------------------------------------------------------- 自肃（restrict）
# 位置照全卡库的多数：卡的发动的「这张卡发动的回合，……」单独一行（有「这个卡名的卡在1回合只能发动1张」时并进那一行），
# 其余的「这个效果发动的回合，……」「这个效果的发动后，直到回合结束时……」写在那个效果的最后。

PLAYER_WORD = {"you": "自己", "both": "双方"}


ACTIVATE_NOUN = {"monster": "怪兽的效果", "spell_trap": "魔法·陷阱卡的效果", "card": "卡的效果", "spell": "魔法卡"}
SET_NOUN = {"card": "卡", "spell_trap": "魔法·陷阱卡"}
FROM_ORDER = ("hand", "deck", "extra", "grave", "banished")


def _only_noun(only, kind, ctx):
    """「X以外的……」里的 X：只有属性 / 种族时不带「怪兽」（「地属性以外的怪兽的效果」），
    别的照名词写（「「X」怪兽以外的怪兽的效果」「「X」卡以外的卡的效果」）。"""
    _, n = noun_parts(only, ["mzone"], ctx=ctx, kind=kind)[:2]
    if kind == "monster" and all(set(f) <= {"attribute"} or set(f) <= {"race"} for f in only):
        return n[:-2]
    return n


def restrict_body(r, ctx):
    """「自己不是机械族怪兽不能从额外卡组特殊召唤，不能进行战斗阶段」「这张卡不能攻击」
    「自己不能把地属性以外的怪兽的效果发动」「这张卡以外的自己怪兽不能攻击」。"""
    forbid = r["forbid"]
    if r["who"] == "self":
        return "，".join({"attack": "这张卡不能攻击", "direct_attack": "这张卡不能直接攻击"}[f] for f in forbid)
    whole = r.get("span") == "whole_turn"
    pieces, monsters = [], []          # 玩家的限制（共用开头的「自己」）；怪兽的限制（自带主语）
    summons = [f for f in forbid if f in FORBID_WORD]
    if summons:
        verbs = "·".join(FORBID_WORD[f] for f in summons)
        zones = [z for z in FROM_ORDER if z in (r.get("from") or [])]
        src = "从" + "·".join(ZONE[z] for z in zones) if zones else ""
        if r.get("only"):
            _, n = noun(r["only"], ["mzone"], ctx=ctx)
            pieces.append("不是%s不能%s%s" % (n, src, verbs))
        elif (r.get("except") or {}).get("by_effect") == "this_card":
            pieces.append("不能用这张卡的效果以外%s把怪兽%s" % (src, verbs))
        else:
            pieces.append("不能%s把怪兽%s" % (src, verbs))
    if "normal_summon" in forbid:
        pieces.append("不能通常召唤")
    if "battle_phase" in forbid:
        pieces.append("不能进行战斗阶段")
    if "activate" in forbid:
        kinds = r.get("kinds", "monster")
        what = ACTIVATE_NOUN[kinds]
        if r.get("only"):
            what = "%s以外的%s" % (_only_noun(r["only"], "monster" if kinds == "monster" else "card", ctx), what)
        pieces.append("不能把%s发动" % what)
    if "set" in forbid:
        pieces.append("不能把%s盖放" % SET_NOUN[r.get("kinds", "card")])
    if "draw_by_effect" in forbid:
        pieces.append("不能用卡的效果抽卡")
    if "search" in forbid:
        pieces.append("不能用抽卡以外的方法从卡组把卡加入手卡")
    if "material" in forbid:
        if r.get("only"):
            pieces.append("不是%s不能作为%s" % (noun(r["only"], ["mzone"], ctx=ctx)[1], MATERIAL_WORD[r["method"]]))
        else:
            pieces.append("不能把怪兽作为%s" % MATERIAL_WORD[r["method"]])
    for f, verb in (("attack", "攻击宣言" if whole else "攻击"), ("direct_attack", "直接攻击")):
        if f not in forbid:
            continue
        card = (r.get("except") or {}).get("card")
        if r.get("only"):                                   # 「自己不用「X」怪兽不能攻击」
            pieces.append("不用%s不能%s" % (noun(r["only"], ["mzone"], ctx=ctx)[1], verb))
        elif card:
            head = {"self": "这张卡", "targets": "作为对象的怪兽"}[card]
            monsters.append("%s以外的%s怪兽不能%s" % (head, PLAYER_WORD[r["who"]], verb))
        else:
            monsters.append("%s怪兽不能%s" % (PLAYER_WORD[r["who"]], verb))
    if "half_battle_damage" in forbid:
        monsters.append("对方受到的战斗伤害变成一半")
    head = [PLAYER_WORD[r["who"]] + "，".join(pieces)] if pieces else []
    return "，".join(head + monsters)


def restrict_text(r, eff, ctx):
    """一条自肃的整句（不含句号）。卡的发动说「这张卡」，别的效果说「这个效果」。"""
    who = "这张卡" if eff["type"] == "activation" else "这个效果"
    if r["span"] == "whole_turn":
        return "%s发动的回合，%s" % (who, restrict_body(r, ctx))
    if r["span"] == "after_resolution":
        until = {"end_of_turn": "直到回合结束时", "end_of_next_turn": "直到下次的自己回合的结束时"}[r["until"]]
        return "%s的发动后，%s%s" % (who, until, restrict_body(r, ctx))
    if r["span"] == "this_turn":                       # 「这个回合，自己不能把地属性以外的怪兽的效果发动」
        head = {"end_of_turn": "这个回合，", "end_of_next_turn": "直到下次的自己回合的结束时，"}[r["until"]]
        return head + restrict_body(r, ctx)
    raise NotImplementedError("自肃 %r 还没有中文写法" % r["span"])


def _card_level(eff, r):
    """写在卡上（单独一行或并进卡名次数行）的：卡的发动的整回合自肃。"""
    return eff["type"] == "activation" and r["span"] == "whole_turn"


def restrict_lines(card, block="monster"):
    """卡的发动的整回合自肃：「这张卡发动的回合，自己不能用这张卡的效果以外把怪兽召唤·反转召唤·特殊召唤。」"""
    out = []
    for e in card["effects"]:
        if e["block"] != block:
            continue
        for r in e["restrict"]:
            if _card_level(e, r):
                out.append(restrict_text(r, e, Ctx(card, e)) + "。")
    return out


def effect_restricts(eff, ctx):
    """写在效果最后的自肃（「……。这个效果的发动后，直到回合结束时……。」）。"""
    return "".join(restrict_text(r, eff, ctx) + "。" for r in eff["restrict"] if not _card_level(eff, r))


def render(card):
    """返回 {"desc": 怪兽/魔陷效果, "pdesc": 灵摆效果}。通常怪兽的 desc 是怪兽描述，不由效果生成，返回空。"""
    card = normalize(card)
    out = {}
    for block, key in (("monster", "desc"), ("pendulum", "pdesc")):
        lines = []
        if block == "monster":
            if materials_text(card):
                lines.append(materials_text(card))
            for code in card["card"]["rule_names"]:
                lines.append("这张卡的卡名当作「%s」使用。" % names.name_of(code, card))
            for p in card["summon"]["procedures"]:
                if p["kind"] == "xyz_overlay":
                    lines.append(_procedure_line(card, p))
            for p in card["summon"]["material_permissions"]:
                lines.append(_permission_line(p))
            once = [r for r in card["summon"]["restrictions"] if r.get("special_summon_once")]
            for r in once:                   # 「自己对「X」1回合只能有1次特殊召唤。」多数单独一行
                lines.append(_restriction_line(r, card))
            line = "".join(_procedure_line(card, p) for p in card["summon"]["procedures"] if p["kind"] != "xyz_overlay")
            line += "".join(_restriction_line(r, card) for r in card["summon"]["restrictions"] if r not in once)
            header = limit_header(card, block)
            pending = restrict_lines(card, block)
            if pending and header.startswith("这个卡名的卡在1回合"):
                # 「这个卡名的卡在1回合只能发动1张，这张卡发动的回合，自己不能把怪兽特殊召唤。」并成一行
                first, rest = header.split("。", 1)
                header = first + "，" + pending[0] + rest
                pending = pending[1:]
            line += header
            if line:
                lines.append(line)
            for rule in card["rules"]:
                lines.append(rule_text(rule, Ctx(card, None)))
            lines.extend(pending)
        else:
            header = limit_header(card, block)
            if header:
                lines.append(header)
        for eff in card["effects"]:
            if eff["block"] != block:
                continue
            ctx = Ctx(card, eff)
            if not is_numbered(eff):
                lines.append(activation_line(eff, ctx))
                continue
            lines.append("%s：%s" % (eff["label"], effect_text(eff, ctx)))
            lines.extend(ctx.bullets)
        out[key] = "\n".join(lines)
    return out
