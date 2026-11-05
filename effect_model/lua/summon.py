"""出场规则（效果外文本）：素材、出场手续、正规出场、出场限制、素材许可、指示物。写法照萌卡官方脚本。

summon_lines(g) 返回 initial_effect 开头的语句；没有 v0.2 新写法的卡，输出与 v0.1 完全一样。
"""

from .. import names
from .common import ATTRIBUTE, LOC, RACE, TYPE

COUNTER_CODE = {"spell": "0x1"}
# 「这张卡不能作为同调素材」等（粹蛙、安全守卫者……）
MATERIAL_CODE = {"fusion": "EFFECT_CANNOT_BE_FUSION_MATERIAL", "synchro": "EFFECT_CANNOT_BE_SYNCHRO_MATERIAL",
                 "xyz": "EFFECT_CANNOT_BE_XYZ_MATERIAL", "link": "EFFECT_CANNOT_BE_LINK_MATERIAL"}

# 只有一个条件时用公共函数：aux.FilterBoolFunction(Card.IsAttribute,ATTRIBUTE_DARK)
_SINGLE = {"race": ("Card.IsRace", RACE), "attribute": ("Card.IsAttribute", ATTRIBUTE), "subtype": ("Card.IsType", TYPE)}


def _single(f):
    for key, (fn, table) in _SINGLE.items():
        if key in f:
            return fn, table[f[key]]
    if "setcode" in f:
        return "Card.IsSetCard", f["setcode"]
    return None


class Summon:
    def __init__(self, g):
        self.g = g
        self.card = g.card
        self.n = 0

    def var(self):
        self.n += 1
        return "sp%d" % self.n

    def func(self, name, args, preds):
        self.g.add_func("function s.%s(%s)\n\treturn %s\nend" % (name, args, " and ".join(preds) or "true"))
        return "s." + name

    # ------------------------------------------------------------ 素材

    def materials(self, m, procs):
        method = m["method"]
        if method == "xyz":
            overlay = next((p for p in procs if p["kind"] == "xyz_overlay"), None)
            if not m.get("filter") and not overlay:
                return ["aux.AddXyzProcedure(c,nil,%d,%d)" % (m["level"], m["count"]), "c:EnableReviveLimit()"]
            f = self.func("xyzfilter", "c", self.g.preds({"filter": m.get("filter", []), "where": []})) \
                if m.get("filter") else "nil"
            if not overlay:
                return ["aux.AddXyzProcedure(c,%s,%d,%d)" % (f, m["level"], m["count"]), "c:EnableReviveLimit()"]
            on = overlay["on"]
            ov = self.func("ovfilter", "c", self.g.preds(on))    # 表侧（face: up）由 preds 写
            desc = self.g.add_string("在%s上面重叠来超量召唤" % "".join(
                "「%s」" % names.name_of(x["name"], self.card) for x in on.get("filter", []) if "name" in x))
            op = "nil"
            if overlay.get("limit"):
                op = "s.xyzop"
                n = self.card["limits"][overlay["limit"]]["n"]      # 「1回合最多2次也能……重叠」：记号数到 n 为止
                self.g.add_func("function s.xyzop(e,tp,chk)\n"
                                "\tif chk==0 then return Duel.GetFlagEffect(tp,id)%s end\n" % ("==0" if n == 1 else "<%d" % n) +
                                "\tDuel.RegisterFlagEffect(tp,id,RESET_PHASE+PHASE_END,EFFECT_FLAG_OATH,1)\nend")
            return ["aux.AddXyzProcedure(c,%s,%d,%d,%s,aux.Stringid(id,%d),%d,%s)" % (
                f, m["level"], m["count"], ov, desc, m["count"], op), "c:EnableReviveLimit()"]
        if method == "synchro":
            tuner, non = m["tuner"].get("filter", []), m["nontuner"].get("filter", [])
            if not tuner and not non:
                return ["aux.AddSynchroProcedure(c,nil,aux.NonTuner(nil),%d)" % m["nontuner"].get("min", 1),
                        "c:EnableReviveLimit()"]
            f1 = "nil"
            if tuner:
                one = _single(tuner[0]) if len(tuner) == 1 else None
                f1 = "aux.FilterBoolFunction(%s,%s)" % one if one else \
                    self.func("tunerfilter", "c", self.g.preds({"filter": tuner, "where": []}))
            f2 = "aux.NonTuner(nil)"
            if non:
                one = _single(non[0]) if len(non) == 1 else None
                f2 = "aux.NonTuner(%s,%s)" % one if one else \
                    "aux.NonTuner(%s)" % self.func("ntfilter", "c", self.g.preds({"filter": non, "where": []}))
            return ["aux.AddSynchroProcedure(c,%s,%s,%d)" % (f1, f2, m["nontuner"].get("min", 1)),
                    "c:EnableReviveLimit()"]
        if method == "link":
            subs = [f["subtype"] for f in m.get("filter", []) if "subtype" in f]
            f = "aux.FilterBoolFunction(Card.IsLinkType,%s)" % TYPE[subs[0]] if subs else "nil"
            return ["aux.AddLinkProcedure(c,%s,%d)" % (f, m["min"]), "c:EnableReviveLimit()"]
        if method == "fusion":
            items = m["list"]
            codes = [x["name"] for x in items if "name" in x]
            reps = [x for x in items if "filter" in x]
            if len(codes) == 1 and len(reps) == 1:
                rep = reps[0]
                f = self.func("fusfilter", "c", self.g.preds({"filter": rep["filter"], "where": []}) + ["c:IsType(TYPE_MONSTER)"])
                return ["c:EnableReviveLimit()",
                        "aux.AddFusionProcCodeFunRep(c,%d,%s,%d,%d,true,true)" % (
                            codes[0], f, rep.get("min", 1), rep.get("max", 127))]
            if len(codes) == 2 and not reps:
                return ["c:EnableReviveLimit()", "aux.AddFusionProcCode2(c,%d,%d,true,true)" % tuple(codes)]
            raise NotImplementedError("这种融合素材的写法还没有 Lua")
        raise NotImplementedError("召唤手续 %r 还没有 Lua 写法" % method)

    # ------------------------------------------------------------ 不编号的出场手续

    def procedure(self, p):
        if p["kind"] == "contact":
            where = p["materials"]["where"]
            locs = "+".join(LOC[w] for w in where["where"]) if where["where"] != ["mzone"] else "LOCATION_ONFIELD"
            self_loc = locs if where["who"] in ("you", "both") else "0"
            opp_loc = locs if where["who"] in ("opp", "both") else "0"
            cf = self.func("cfilter", "c,fc", ["c:IsAbleToGraveAsCost()", "(c:IsControler(fc:GetControler()) or c:IsFaceup())"])
            self.g.add_func("function s.contactop(g)\n\tDuel.SendtoGrave(g,REASON_COST)\nend")
            return ["aux.AddContactFusionProcedure(c,%s,%s,%s,s.contactop)" % (cf, self_loc, opp_loc)]
        if p["kind"] == "special" and p.get("from") == ["extra"]:
            return self.extra_procedure(p)
        raise NotImplementedError("出场手续 %r 还没有 Lua 写法" % p["kind"])

    def extra_procedure(self, p):
        """「等级差直到1为止从自己场上把调整1只和调整以外的怪兽1只送去墓地的场合才能特殊召唤」（北极天熊-勾陈一的写法）。"""
        cost = p["cost"][0]
        what = cost["what"]
        rel = what.get("relation") or {}
        if cost["act"] != "send_to_gy" or not (rel.get("roles") and rel.get("diff")):
            raise NotImplementedError("额外卡组的这种特殊召唤手续还没有 Lua 写法")
        n = rel["diff"]["value"]
        self.func("sprfilter", "c", ["c:IsFaceup()", "c:IsLevelAbove(1)", "c:IsAbleToGraveAsCost()"] + self.g.preds(what))
        self.g.add_func("\n".join([
            "function s.sprselect(g,tp,sc)",
            "\tif g:GetCount()~=2 then return false end",
            "\tlocal a=g:GetFirst()",
            "\tlocal b=g:GetNext()",
            "\treturn g:IsExists(Card.IsType,1,nil,TYPE_TUNER) and g:IsExists(aux.NOT(Card.IsType),1,nil,TYPE_TUNER)",
            "\t\tand math.abs(a:GetLevel()-b:GetLevel())==%d" % n,
            "\t\tand Duel.GetLocationCountFromEx(tp,tp,g,sc)>0",
            "end",
            "function s.sprcon(e,c)",
            "\tif c==nil then return true end",
            "\tlocal tp=c:GetControler()",
            "\tlocal g=Duel.GetMatchingGroup(s.sprfilter,tp,%s,0,nil)" % "+".join(LOC[w] for w in what["where"]),
            "\treturn g:CheckSubGroup(s.sprselect,2,2,tp,c)",
            "end",
            "function s.sprtg(e,tp,eg,ep,ev,re,r,rp,chk,c)",
            "\tlocal g=Duel.GetMatchingGroup(s.sprfilter,tp,%s,0,nil)" % "+".join(LOC[w] for w in what["where"]),
            "\tDuel.Hint(HINT_SELECTMSG,tp,HINTMSG_TOGRAVE)",
            "\tlocal sg=g:SelectSubGroup(tp,s.sprselect,true,2,2,tp,c)",
            "\tif sg then",
            "\t\tsg:KeepAlive()",
            "\t\te:SetLabelObject(sg)",
            "\t\treturn true",
            "\telse return false end",
            "end",
            "function s.sprop(e,tp,eg,ep,ev,re,r,rp,c)",
            "\tlocal tg=e:GetLabelObject()",
            "\tDuel.SendtoGrave(tg,REASON_SPSUMMON)",
            "\ttg:DeleteGroup()",
            "end"]))
        v = self.var()
        return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v,
                "%s:SetCode(EFFECT_SPSUMMON_PROC)" % v,
                "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                "%s:SetRange(LOCATION_EXTRA)" % v, "%s:SetCondition(s.sprcon)" % v,
                "%s:SetTarget(s.sprtg)" % v, "%s:SetOperation(s.sprop)" % v, "c:RegisterEffect(%s)" % v]

    # ------------------------------------------------------------ 正规出场、限制、许可、指示物

    def proper(self, s):
        """「只能用这个方法特殊召唤」：接触融合类（额外卡组以外的特殊召唤不受限）与额外卡组手续类（官方写法：一律不能）。"""
        if s.get("proper") != "only" and not s["cannot"]:
            return []
        v = self.var()
        out = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
               "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
               "%s:SetCode(EFFECT_SPSUMMON_CONDITION)" % v]
        if any(p["kind"] == "contact" for p in s["procedures"]):
            self.g.add_func("function s.splimit(e,se,sp,st)\n\treturn e:GetHandler():GetLocation()~=LOCATION_EXTRA\nend")
            out.append("%s:SetValue(s.splimit)" % v)
        return out + ["c:RegisterEffect(%s)" % v]

    def restriction(self, r):
        v = self.var()
        if r.get("special_summon_once") == "turn":      # 「自己对「X」1回合只能有1次特殊召唤」
            return ["c:SetSPSummonOnce(id)"]
        if "cannot_special_summon_from" in r:
            return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                    "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE+EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                    "%s:SetRange(%s)" % (v, "+".join(LOC[w] for w in r["cannot_special_summon_from"])),
                    "%s:SetCode(EFFECT_SPSUMMON_CONDITION)" % v, "c:RegisterEffect(%s)" % v]
        if r.get("cannot_be_material") in MATERIAL_CODE:
            return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                    "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                    "%s:SetCode(%s)" % (v, MATERIAL_CODE[r["cannot_be_material"]]), "%s:SetValue(1)" % v,
                    "c:RegisterEffect(%s)" % v]
        raise NotImplementedError("出场限制 %r 还没有 Lua 写法" % r)

    def permission(self, p):
        """「这张卡连接召唤的场合，对方场上1只怪兽也能作为连接素材」。"""
        if not (p.get("for") == "link" and p.get("who") == "opp" and p.get("count", 1) == 1):
            raise NotImplementedError("素材许可 %r 还没有 Lua 写法" % p)
        self.g.add_func("\n".join([
            "function s.matval(e,lc,mg,c,tp)",
            "\tif e:GetHandler()~=lc or not c:IsControler(1-tp) then return false,nil end",
            "\tif not mg then return true,true end",
            "\treturn true,not mg:IsExists(Card.IsControler,1,c,1-tp)",
            "end"]))
        v = self.var()
        return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v,
                "%s:SetProperty(EFFECT_FLAG_UNCOPYABLE+EFFECT_FLAG_IGNORE_IMMUNE)" % v,
                "%s:SetCode(EFFECT_EXTRA_LINK_MATERIAL)" % v, "%s:SetRange(LOCATION_EXTRA)" % v,
                "%s:SetTargetRange(0,%s)" % (v, "+".join(LOC[w] for w in p["where"])),
                "%s:SetValue(s.matval)" % v, "c:RegisterEffect(%s)" % v]

    def rule_name(self, code):
        """规则上当作另一张卡（官方靠 cdb 的 alias）。导出的卡包 alias 写 0——MDPro3 本地引擎见到 alias
        就去加载那张卡的脚本，整张卡就没有效果了——所以改成在任何区域都适用、不会被无效的改名效果。"""
        return ["--卡名当作「%s」使用" % names.name_of(code, self.card),
                "local e0=Effect.CreateEffect(c)", "e0:SetType(EFFECT_TYPE_SINGLE)",
                "e0:SetProperty(EFFECT_FLAG_SINGLE_RANGE+EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)",
                "e0:SetCode(EFFECT_CHANGE_CODE)",
                "e0:SetRange(LOCATION_DECK+LOCATION_HAND+LOCATION_ONFIELD+LOCATION_GRAVE+LOCATION_REMOVED+LOCATION_EXTRA)",
                "e0:SetValue(%d)" % code, "c:RegisterEffect(e0)"]

    def lines(self):
        card = self.card
        s = card["summon"]
        out = []
        codes = sorted({f["name"] for e in card["effects"] for f in _name_filters(e)
                        if isinstance(f.get("name"), int) and f["name"] != card["card"]["code"]})
        if codes:
            out.append("aux.AddCodeList(c,%s)" % ",".join(str(x) for x in codes))
        for code in card["card"]["rule_names"]:
            out += self.rule_name(code)
        if s.get("materials"):
            out += self.materials(s["materials"], s["procedures"])
        elif s.get("proper") == "only" or s["cannot"]:
            out.append("c:EnableReviveLimit()")
        for p in s["procedures"]:
            if p["kind"] != "xyz_overlay":
                out += self.procedure(p)
        out += self.proper(s)
        for r in s["restrictions"]:
            out += self.restriction(r)
        for p in s["material_permissions"]:
            out += self.permission(p)
        for name, spec in card["counters"].items():
            out.append("c:EnableCounterPermit(%s)" % COUNTER_CODE[name])
            if spec.get("max"):
                out.append("c:SetCounterLimit(%s,%d)" % (COUNTER_CODE[name], spec["max"]))
        if "pendulum" in card["card"]["subtypes"]:
            out.append("aux.EnablePendulumAttribute(c)")
        return out


def _name_filters(eff):
    """效果里「指定卡名」的过滤条件（用来写 aux.AddCodeList）。"""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if "filter" in node and isinstance(node["filter"], list):
                out.extend(f for f in node["filter"] if isinstance(f, dict))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(eff)
    return out


def summon_lines(g):
    return Summon(g).lines()

