"""整张卡：过滤函数、提示文字、次数额度、出场规则，以及 generate()。"""

from ..model import limits_of, normalize
from .common import ATTRIBUTE, POSITION, RACE, STAT_FN, TYPE, indent
from .effect import EffectGen
from .summon import summon_lines

SEL_POSITION = {"faceup_attack": "POS_FACEUP_ATTACK", "faceup_defense": "POS_FACEUP_DEFENSE",
                "attack": "POS_ATTACK", "defense": "POS_DEFENSE"}
CAN = {"change_control": "$c:IsAbleToChangeControler() and "
                         "Duel.GetMZoneCount($c:GetControler(),$c,$c:GetControler(),LOCATION_REASON_CONTROL)>0"}


class Gen:
    def __init__(self, card):
        self.card = normalize(card)
        self.funcs = []            # 生成的辅助函数（源码文本）
        self.filter_names = {}     # 过滤函数体 → 名字，用来去重
        self.strings = []          # aux.Stringid(id, n) 对应的提示文字
        self.limit_keys = {}       # 卡名次数限制的分组 → id 偏移
        self.flags = {}            # 效果 id → 标识用的 flag 编号（「①的效果适用的回合」）
        self.hooks = {}            # 效果 id → 追加到 target 函数里的语句（光之护封剑的回合计数）
        self.counters = {}         # (活动, 过滤函数名) → 自定义活动计数的编号（整回合自肃「不是X怪兽不能特殊召唤」）
        self.init_lines = []       # 写在 initial_effect 最后的语句（Duel.AddCustomActivityCounter）
        for eff in self.card["effects"]:
            for key, _ in limits_of(self.card, eff, scope="name"):
                self.limit_keys.setdefault(key, len(self.limit_keys))
        for eff in self.card["effects"]:
            for c in eff["condition"]:
                if c.get("cond") == "named_card_used":
                    self.flags.setdefault(c["effect"], len(self.flags))

    # ------------------------------------------------------------ 小工具

    def code_offset(self, k):
        return "id" if k == 0 else ("id+o" if k == 1 else "id+o*%d" % k)

    def add_string(self, text):
        self.strings.append(text)
        return len(self.strings) - 1

    def add_func(self, text):
        self.funcs.append(text)

    def pred(self, f, where, var):
        """单个过滤条件 → Lua 表达式；没有对应写法（由别处处理）时返回 None。"""
        if "card_type" in f:
            ct = f["card_type"]
            if ct == "monster" and set(where) <= {"mzone", "linked"}:
                return None
            if isinstance(ct, list):
                return "%s:IsType(%s)" % (var, "+".join(TYPE[x] for x in ct))
            return "%s:IsType(%s)" % (var, TYPE[ct])
        if "subtype" in f:
            return "%s:IsType(%s)" % (var, TYPE[f["subtype"]])
        if any(k in f for k in ("atk", "def", "level")):
            key = next(k for k in ("atk", "def", "level") if k in f)
            op, n = f[key]
            return "%s:%s(%d)" % (var, STAT_FN[(key, op)], n)
        if "race" in f:
            return "%s:IsRace(%s)" % (var, RACE[f["race"]])
        if "attribute" in f:
            return "%s:IsAttribute(%s)" % (var, ATTRIBUTE[f["attribute"]])
        if "setcode" in f:
            return "%s:IsSetCard(%s)" % (var, f["setcode"])
        if "position" in f:
            return "%s:%s()" % (var, POSITION[f["position"]])
        if "name" in f:
            if isinstance(f["name"], int):
                return "%s:IsCode(%d)" % (var, f["name"])
            same = f["name"].get("same_as") if isinstance(f["name"], dict) else None
            if same and same.get("ref") == "event":    # 「和那张发动的卡卡名不同的」：发动的卡在 target 里存进 LabelObject
                return "%s:IsCode(e:GetLabelObject():GetCode())" % var
            return None                                # 宣言的卡名：由处理动作自己取
        if "not" in f:
            inner = self.pred(f["not"], where, var)
            return "not %s" % inner if inner else None
        if "can" in f:
            return CAN[f["can"]].replace("$c", var)
        if "lua" in f:
            return f["lua"].replace("$c", var)
        if "previous" in f:
            return None
        raise NotImplementedError("过滤条件 %r 还没有 Lua 写法" % f)

    def preds(self, sel, extra=(), var="c"):
        out = []
        where = sel.get("where", [])
        if sel.get("position") in SEL_POSITION:
            out.append("%s:IsPosition(%s)" % (var, SEL_POSITION[sel["position"]]))
        elif sel.get("face") == "up":
            out.append("%s:IsFaceup()" % var)
        elif sel.get("face") == "down":
            out.append("%s:IsFacedown()" % var)
        kinds = [f["card_type"] for f in sel.get("filter", []) if f.get("card_type") in ("spell", "trap")]
        for f in sel.get("filter", []):
            if f.get("subtype") == "normal" and kinds:      # 通常魔法 / 通常陷阱：类型只有「魔法」「陷阱」这一位
                out.append("%s:GetType()==%s" % (var, TYPE[kinds[0]]))
                continue
            p = self.pred(f, where, var)
            if p:
                out.append(p)
        if "linked" in where:
            out.append("e:GetHandler():GetLinkedGroup():IsContains(%s)" % var)
        out.extend(x.replace("$c", var) for x in extra)
        return out

    def filter_fn(self, sel, extra=()):
        """生成 function s.fN(c,e,tp)，返回函数名；没有条件时返回 aux.TRUE。"""
        preds = self.preds(sel, extra)
        if not preds:
            return "aux.TRUE"
        body = " and ".join(preds)
        if body not in self.filter_names:
            name = "s.filter%d" % (len(self.filter_names) + 1)
            self.filter_names[body] = name
            self.add_func("function %s(c,e,tp)\n\treturn %s\nend" % (name, body))
        return self.filter_names[body]

    # ------------------------------------------------------------ 出场规则

    def summon_procedure(self):
        return summon_lines(self)

    def activity_counter(self, activity, filter_name):
        """登记一个自定义活动计数，返回它的编号（同一张卡里不同的过滤各用一个编号）。"""
        key = (activity, filter_name)
        if key not in self.counters:
            code = self.code_offset(len(self.counters)) if self.counters else "id"
            self.counters[key] = code
            self.init_lines.append("Duel.AddCustomActivityCounter(%s,%s,%s)" % (code, activity, filter_name))
        return self.counters[key]

    def implicit_activation(self):
        """永续 / 场地 / 装备魔法陷阱没有单独写「卡的发动」时，补一个普通的发动（不然在场上放不出来）。"""
        info = self.card["card"]
        if info["kind"] == "monster" or any(e["type"] == "activation" for e in self.card["effects"]):
            return []
        if not set(info["subtypes"]) & {"continuous", "field"}:
            return []
        return ["--发动", "local e0=Effect.CreateEffect(c)", "e0:SetType(EFFECT_TYPE_ACTIVATE)",
                "e0:SetCode(EVENT_FREE_CHAIN)", "c:RegisterEffect(e0)"]


def generate(card):
    """返回 (Lua 源码, 提示文字列表)。提示文字按 aux.Stringid(id, n) 的 n 排列，导出卡包时写进 cdb 的 str1..str16。"""
    g = Gen(card)
    # 规则文字可能往别的效果的 target 里插语句（留在场上的回合计数），所以先注册规则
    body = g.summon_procedure() + g.implicit_activation()
    for item in g.card["rules"] + g.card["effects"]:
        body.extend(EffectGen(g, item).register())
    body.extend(g.init_lines)
    info = g.card["card"]
    out = ["--" + info["name"], "local s,id,o=GetID()", "function s.initial_effect(c)"]
    out.extend(indent(body))
    out.append("end")
    out.extend(g.funcs)
    return "\n".join(out) + "\n", g.strings
