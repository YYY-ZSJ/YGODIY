"""v0.2 新增的永续效果写法（照萌卡官方脚本）。每个方法返回注册这个效果的语句列表。"""

from ..model import applies, is_ref
from .common import LOC, sides

COUNTER_CODE = {"spell": "0x1"}


def _value(ap):
    return str(ap["value"])


def _opp_or_1(helper):
    return lambda ap: helper if ap.get("by") == "opp" else "1"


# 一个效果代码就能写的永续效果：cont → (效果代码, 数值或算数值的函数或 None, 是否只在所在区域适用)
SIMPLE = {
    "atk_update": ("EFFECT_UPDATE_ATTACK", _value, True),
    "def_update": ("EFFECT_UPDATE_DEFENSE", _value, True),
    "change_level": (lambda ap: "EFFECT_CHANGE_LEVEL" if "set" in ap else "EFFECT_UPDATE_LEVEL",
                     lambda ap: str(ap["set"] if "set" in ap else ap["value"]), True),
    "indestructible_battle": ("EFFECT_INDESTRUCTABLE_BATTLE", "1", True),
    "indestructible_effect": ("EFFECT_INDESTRUCTABLE_EFFECT", _opp_or_1("aux.indoval"), True),
    "cannot_be_targeted": ("EFFECT_CANNOT_BE_EFFECT_TARGET", _opp_or_1("aux.tgoval"), True),
    "cannot_be_attack_target": ("EFFECT_CANNOT_BE_BATTLE_TARGET", "aux.imval1", True),
    "piercing": ("EFFECT_PIERCE", None, False),
    "direct_attack": ("EFFECT_DIRECT_ATTACK", None, False),
    "cannot_direct_attack": ("EFFECT_CANNOT_DIRECT_ATTACK", None, False),
    "attack_all": ("EFFECT_ATTACK_ALL", "1", False),
    "extra_attack": ("EFFECT_EXTRA_ATTACK", lambda ap: str(ap.get("n", 2) - 1), False),
}
# 只在原来就有写法的单独一条之外才走 SIMPLE 的（不改变已有样例的输出）
NEW_SIMPLE = set(SIMPLE) - {"atk_update"}
REASON = {"battle": "REASON_BATTLE", "effect": "REASON_EFFECT"}
SUMMON_TYPE = {"fusion": "SUMMON_TYPE_FUSION", "synchro": "SUMMON_TYPE_SYNCHRO", "xyz": "SUMMON_TYPE_XYZ",
               "link": "SUMMON_TYPE_LINK", "ritual": "SUMMON_TYPE_RITUAL", "pendulum": "SUMMON_TYPE_PENDULUM"}


class ContMixin:
    """EffectGen 的永续效果部分。"""

    def special_continuous(self):
        """v0.2 新增的写法；不是的话返回 None，交给原来的 continuous。"""
        eff = self.eff
        if eff.get("on"):
            return self.cont_listener()
        aps = applies(eff)
        if sorted(ap["cont"] for ap in aps) == ["quickplay_opponent_hand", "trap_from_hand"]:
            return self.cont_hand_activation(aps)
        ap = aps[0]
        cont = ap["cont"]
        if len(aps) > 1 or cont in NEW_SIMPLE or cont in ("indestructible_count", "attack_target_restriction"):
            return self.cont_simple(aps)
        if cont == "atk_update" and not is_ref(ap["affects"]):
            return self.cont_atk_field(ap)
        if cont == "atk_update" and isinstance(ap["value"], dict) and self.count_ref(ap["value"]) == "overlay":
            return self.cont_atk_self(ap, "c:GetOverlayCount()*%d" % ap["value"]["mul"][1])
        if cont == "atk_set":
            return self.cont_atk_set(ap)
        if cont == "immune_effect":
            return self.cont_immune(ap)
        if cont == "effects_disabled":
            return self.cont_disable_field(ap)
        if cont == "redirect_destination":
            return self.cont_redirect(ap)
        if cont == "cannot_special_summon":
            return self.cont_cannot_special_summon(ap)
        return None

    @staticmethod
    def count_ref(value):
        mul = value.get("mul") or []
        if len(mul) == 2 and isinstance(mul[0], dict) and "count" in mul[0]:
            return (mul[0]["count"] or {}).get("ref")
        return None

    def head(self):
        return ["--" + self.eff["label"], "local %s=Effect.CreateEffect(c)" % self.v]

    def rng(self):
        return "+".join(LOC[w] for w in self.eff["range"])

    def cont_condition(self):
        """永续效果的适用条件（「连接召唤的这张卡……」）。没有条件返回 None。"""
        if not self.eff["condition"]:
            return None
        pre = []
        exprs = self.cond_exprs(self.eff["condition"], pre)
        name = "s.contcon%d" % self.k
        self.g.add_func("function %s(e)\n\tlocal tp=e:GetHandlerPlayer()\n%s\treturn %s\nend" % (
            name, "".join("\t%s\n" % p for p in pre), " and ".join(exprs)))
        return name

    def finish(self, L):
        cond = self.cont_condition()
        if cond:
            L.append("%s:SetCondition(%s)" % (self.v, cond))
        L.append("c:RegisterEffect(%s)" % self.v)
        return L

    # ------------------------------------------------------------ 攻守

    def cont_atk_field(self, ap):
        """「场上的风属性怪兽的攻击力上升300」。"""
        v, k = self.v, self.k
        aff = ap["affects"]
        s_, o_ = sides(aff)
        preds = self.g.preds(aff, var="c")
        L = self.head() + ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_UPDATE_ATTACK)" % v,
                           "%s:SetRange(%s)" % (v, self.rng()), "%s:SetTargetRange(%s,%s)" % (v, s_, o_)]
        if preds:
            self.g.add_func("function s.atktg%d(e,c)\n\treturn %s\nend" % (k, " and ".join(preds)))
            L.append("%s:SetTarget(s.atktg%d)" % (v, k))
        L.append("%s:SetValue(%d)" % (v, ap["value"]))
        return self.finish(L)

    def cont_atk_self(self, ap, expr):
        """「这张卡的攻击力上升这张卡的超量素材数量×200」。"""
        v, k = self.v, self.k
        self.g.add_func("function s.atkval%d(e,c)\n\treturn %s\nend" % (k, expr))
        L = self.head() + ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetCode(EFFECT_UPDATE_ATTACK)" % v,
                           "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v, "%s:SetRange(%s)" % (v, self.rng()),
                           "%s:SetValue(s.atkval%d)" % (v, k)]
        return self.finish(L)

    def cont_atk_set(self, ap):
        """「这张卡的原本攻击力变成作为这张卡的融合素材的怪兽数量×1000」：素材数在出场时由手续记下（SetMaterial）。"""
        v, k = self.v, self.k
        value = ap["value"]
        if not is_ref(ap["affects"], "self"):
            raise NotImplementedError("攻击力变成目前只支持这张卡")
        code = "EFFECT_SET_BASE_ATTACK" if ap.get("original") else "EFFECT_SET_ATTACK"
        if isinstance(value, int):          # 「这张卡的（原本）攻击力变成2000」
            val = str(value)
        elif ap.get("original") and self.count_ref(value) == "materials":
            self.g.add_func("function s.atkval%d(e,c)\n\treturn c:GetMaterialCount()*%d\nend" % (k, value["mul"][1]))
            val = "s.atkval%d" % k
        else:
            raise NotImplementedError("攻击力变成的这种写法还没有 Lua")
        L = self.head() + ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetCode(%s)" % (v, code),
                           "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v, "%s:SetRange(%s)" % (v, self.rng()),
                           "%s:SetValue(%s)" % (v, val)]
        return self.finish(L)

    # ------------------------------------------------------------ 第一批：一个代码一条

    def cont_simple(self, aps):
        """几条一起适用的各写一个效果（攻击力·守备力上升、不会被战斗·效果破坏……）。"""
        out = []
        for i, ap in enumerate(aps):
            v = self.v if i == 0 else "%s_%d" % (self.v, i + 1)
            out += self.simple_one(ap, v, first=i == 0)
        return out

    def simple_one(self, ap, v, first=True):
        cont, k = ap["cont"], self.k
        L = (["--" + self.eff["label"]] if first else []) + ["local %s=Effect.CreateEffect(c)" % v]
        aff = ap.get("affects") or {"ref": "self"}
        if cont == "attack_target_restriction":
            if not is_ref(ap.get("only"), "self"):
                raise NotImplementedError("攻击对象限制目前只支持「对方不能选择其他怪兽作为攻击对象」")
            self.g.add_func("function s.atlimit%d(e,c)\n\treturn c~=e:GetHandler()\nend" % k)
            L += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_CANNOT_SELECT_BATTLE_TARGET)" % v,
                  "%s:SetRange(%s)" % (v, self.rng()), "%s:SetTargetRange(0,LOCATION_MZONE)" % v,
                  "%s:SetValue(s.atlimit%d)" % (v, k)]
            return self._finish_one(L, v)
        if cont == "indestructible_count":
            by = ap.get("by", ["battle"])
            self.g.add_func("function s.indct%d(e,re,r,rp)\n\treturn r&(%s)~=0\nend" % (k, "+".join(REASON[b] for b in by)))
            L += ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v,
                  "%s:SetRange(%s)" % (v, self.rng()), "%s:SetCode(EFFECT_INDESTRUCTABLE_COUNT)" % v,
                  "%s:SetCountLimit(%d)" % (v, ap.get("n", 1)), "%s:SetValue(s.indct%d)" % (v, k)]
            return self._finish_one(L, v)
        code, value, ranged = SIMPLE[cont]
        value = value(ap) if callable(value) else value
        code = code(ap) if callable(code) else code
        if is_ref(aff, "self"):
            L += ["%s:SetType(EFFECT_TYPE_SINGLE)" % v]
            if ranged:
                L += ["%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v, "%s:SetRange(%s)" % (v, self.rng())]
        elif not is_ref(aff):
            s_, o_ = sides(aff)
            L += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetRange(%s)" % (v, self.rng()),
                  "%s:SetTargetRange(%s,%s)" % (v, s_, o_)]
            preds = self.g.preds(aff, var="c")
            if preds:                        # 永续效果的 SetTarget 是 (e,c)，和选卡过滤函数 (c,e,tp) 不一样
                name = "s.conttg%d_%s" % (k, v.split("_")[-1] if "_" in v else "1")
                self.g.add_func("function %s(e,c)\n\treturn %s\nend" % (name, " and ".join(preds)))
                L.append("%s:SetTarget(%s)" % (v, name))
        else:
            raise NotImplementedError("永续效果的适用对象 %r 还没有 Lua 写法" % aff)
        L.append("%s:SetCode(%s)" % (v, code))
        if value is not None:
            L.append("%s:SetValue(%s)" % (v, value))
        return self._finish_one(L, v)

    def _finish_one(self, L, v):
        cond = self.cont_condition()
        if cond:
            L.append("%s:SetCondition(%s)" % (v, cond))
        L.append("c:RegisterEffect(%s)" % v)
        return L

    # ------------------------------------------------------------ 抗性、无效、去向、限制

    def cont_immune(self, ap):
        """「不受除以这张卡为对象的效果以外的对方发动的效果影响」。"""
        v, k = self.v, self.k
        src = ap["from"]
        lines = ["function s.efilter%d(e,te)" % k]
        if src.get("player") == "opp":
            lines.append("\tif te:GetOwnerPlayer()==e:GetHandlerPlayer() then return false end")
        elif not src.get("player"):           # 「不受其他卡的效果影响」
            lines.append("\tif te:GetOwner()==e:GetOwner() then return false end")
        if src.get("activated"):
            lines.append("\tif not te:IsActivated() then return false end")
        if is_ref((src.get("except") or {}).get("targets"), "self"):
            lines += ["\tif not te:IsHasProperty(EFFECT_FLAG_CARD_TARGET) then return true end",
                      "\tlocal g=Duel.GetChainInfo(0,CHAININFO_TARGET_CARDS)",
                      "\treturn not g or not g:IsContains(e:GetHandler())"]
        else:
            lines.append("\treturn true")
        self.g.add_func("\n".join(lines + ["end"]))
        L = self.head() + ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v,
                           "%s:SetRange(%s)" % (v, self.rng()), "%s:SetCode(EFFECT_IMMUNE_EFFECT)" % v,
                           "%s:SetValue(s.efilter%d)" % (v, k)]
        return self.finish(L)

    def cont_disable_field(self, ap):
        """「场上的表侧表示怪兽的效果无效化」（技能抽取）。"""
        v, k = self.v, self.k
        aff = ap["affects"]
        s_, o_ = sides(aff)
        self.g.add_func("function s.distg%d(e,c)\n\treturn c:IsType(TYPE_EFFECT) or c:GetOriginalType()&TYPE_EFFECT~=0\nend" % k)
        L = self.head() + ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetRange(%s)" % (v, self.rng()),
                           "%s:SetTargetRange(%s,%s)" % (v, s_, o_), "%s:SetTarget(s.distg%d)" % (v, k),
                           "%s:SetCode(EFFECT_DISABLE)" % v]
        return self.finish(L)

    def cont_redirect(self, ap):
        """「被送去墓地的怪兽不去墓地而除外」（次元的裂缝）。"""
        v = self.v
        if (ap["from_dest"], ap["to_dest"]) != ("grave", "banished"):
            raise NotImplementedError("去向替代目前只支持「不去墓地而除外」")
        monsters = {"card_type": "monster"} in ap["affects"].get("filter", [])
        L = self.head() + ["%s:SetType(EFFECT_TYPE_FIELD)" % v,
                           "%s:SetProperty(EFFECT_FLAG_SET_AVAILABLE+EFFECT_FLAG_IGNORE_RANGE+EFFECT_FLAG_IGNORE_IMMUNE)" % v,
                           "%s:SetCode(EFFECT_TO_GRAVE_REDIRECT)" % v, "%s:SetRange(%s)" % (v, self.rng())]
        if monsters:
            L.append("%s:SetTarget(aux.DimensionalFissureTarget)" % v)
        L += ["%s:SetTargetRange(LOCATION_DECK,LOCATION_DECK)" % v if monsters else "%s:SetTargetRange(0xff,0xff)" % v,
              "%s:SetValue(LOCATION_REMOVED)" % v]
        return self.finish(L)

    def cont_cannot_special_summon(self, ap):
        """「自己不是「机壳」怪兽不能特殊召唤」。"""
        v, k = self.v, self.k
        excepts = [f["not"] for f in ap.get("which", []) if "not" in f]
        props = "EFFECT_FLAG_PLAYER_TARGET"
        if self.eff.get("cannot_be_negated"):
            props += "+EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_CAN_FORBIDDEN"
        L = self.head() + ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_CANNOT_SPECIAL_SUMMON)" % v,
                           "%s:SetProperty(%s)" % (v, props), "%s:SetRange(%s)" % (v, self.rng()),
                           "%s:SetTargetRange(%s)" % (v, "1,0" if ap.get("player", "you") == "you" else "0,1")]
        if excepts:
            preds = self.g.preds({"filter": excepts, "where": []})
            self.g.add_func("function s.splimit%d(e,c,tp,sumtp,sumpos)\n\treturn not (%s)\nend" % (k, " and ".join(preds)))
            L.append("%s:SetTarget(s.splimit%d)" % (v, k))
        return self.finish(L)

    def cont_hand_activation(self, aps):
        """「自己·对方回合自己可以把「魔弹」魔法·陷阱卡从手卡发动」：速攻魔法与陷阱各一个许可。"""
        v, k = self.v, self.k
        which = [f for f in aps[0].get("which", []) if "card_type" not in f]
        preds = self.g.preds({"filter": which, "where": []})
        self.g.add_func("function s.handtg%d(e,c)\n\treturn %s\nend" % (k, " and ".join(preds) or "true"))
        L = self.head() + ["%s:SetDescription(aux.Stringid(id,%d))" % (v, self.g.add_string("从手卡发动")),
                           "%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_QP_ACT_IN_NTPHAND)" % v,
                           "%s:SetRange(%s)" % (v, self.rng()), "%s:SetTarget(s.handtg%d)" % (v, k),
                           "%s:SetTargetRange(LOCATION_HAND,0)" % v, "%s:SetValue(id)" % v,
                           "c:RegisterEffect(%s)" % v,
                           "local %s_2=%s:Clone()" % (v, v), "%s_2:SetCode(EFFECT_TRAP_ACT_IN_HAND)" % v,
                           "c:RegisterEffect(%s_2)" % v]
        return L

    # ------------------------------------------------------------ 「每次……，……」

    def cont_listener(self):
        """「每次自己或者对方把魔法卡发动，给这张卡放置1个魔力指示物」：发动时记下，连锁处理后放置（萌卡 aux.chainreg）。"""
        eff, v, k = self.eff, self.v, self.k
        on = eff["on"]
        if not (on.get("event") == "effect_activated" and on.get("what") == "card"):
            raise NotImplementedError("「每次……」目前只支持「每次……把卡发动」")
        from .common import TYPE
        conds = ["re:IsHasType(EFFECT_TYPE_ACTIVATE)",
                 "re:IsActiveType(%s)" % "+".join(TYPE[x] for x in on.get("kinds", ["spell"])),
                 "e:GetHandler():GetFlagEffect(FLAG_ID_CHAINING)>0"]
        if on.get("by") in ("you", "opp"):
            conds.append("rp==%s" % ("tp" if on["by"] == "you" else "1-tp"))
        body = []
        for s in eff["do"]:
            if s["act"] == "add_counter" and is_ref(s.get("what"), "self"):
                body.append("e:GetHandler():AddCounter(%s,%d)" % (COUNTER_CODE[s["counter"]], s.get("count", 1)))
            else:
                raise NotImplementedError("「每次……」的处理 %r 还没有 Lua 写法" % s["act"])
        self.g.add_func("function s.lsop%d(e,tp,eg,ep,ev,re,r,rp)\n\tif %s then\n%s\n\tend\nend" % (
            k, " and ".join(conds), "\n".join("\t\t" + b for b in body)))
        return self.head() + [
            "%s:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_FIELD)" % v, "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)" % v,
            "%s:SetCode(EVENT_CHAINING)" % v, "%s:SetRange(%s)" % (v, self.rng()), "%s:SetOperation(aux.chainreg)" % v,
            "c:RegisterEffect(%s)" % v,
            "local %s_2=Effect.CreateEffect(c)" % v, "%s_2:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_FIELD)" % v,
            "%s_2:SetCode(EVENT_CHAIN_SOLVED)" % v, "%s_2:SetRange(%s)" % (v, self.rng()),
            "%s_2:SetOperation(s.lsop%d)" % (v, k), "c:RegisterEffect(%s_2)" % v]

