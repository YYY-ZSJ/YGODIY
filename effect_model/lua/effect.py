"""一个效果的注册代码与它的 condition / cost / target / operation 函数。"""

from ..model import ModelError, applies, is_ref, limits_of
from ..model.patterns import linked_count_times, same_original_name_ref
from .acts import ActsMixin, COUNTER_CODE, PHASE_CODE
from .common import CATEGORY, HINT, LANDED, LOC, SHORT, SUMMON_EVENTS, TYPE, able, cmp_lua, indent, sides, step_refs
from .cont import ContMixin, SUMMON_TYPE

LUA_OP = {"==": "==", "<=": "<=", ">=": ">=", "<": "<", ">": ">", "!=": "~="}
FORBID = {"summon": ("ACTIVITY_SUMMON", "EFFECT_CANNOT_SUMMON"),
          "flip_summon": ("ACTIVITY_FLIPSUMMON", "EFFECT_CANNOT_FLIP_SUMMON"),
          "special_summon": ("ACTIVITY_SPSUMMON", "EFFECT_CANNOT_SPECIAL_SUMMON")}
# 不是召唤类的玩家限制：(活动计数, 效果代码…)
FORBID_PLAYER = {"normal_summon": ("ACTIVITY_NORMALSUMMON", ("EFFECT_CANNOT_SUMMON", "EFFECT_CANNOT_MSET")),
                 "battle_phase": ("ACTIVITY_BATTLE_PHASE", ("EFFECT_CANNOT_BP",))}
SELF_FORBID = {"attack": "EFFECT_CANNOT_ATTACK", "direct_attack": "EFFECT_CANNOT_DIRECT_ATTACK"}
CHAINED_LINKS = ("and_if_you_do", "then", "and")      # 依赖前一步做成的连接
# 「那之后，可以……」问玩家时的提示
ASK_TEXT = {"destroy": "是否破坏？", "banish": "是否除外？", "send_to_gy": "是否送去墓地？", "add_to_hand": "是否加入手卡？",
            "special_summon": "是否特殊召唤？", "set_spell_trap": "是否盖放？", "draw": "是否抽卡？", "damage": "是否给与伤害？",
            "change_position": "是否改变表示形式？", "discard": "是否丢弃手卡？"}


def optional_part(steps):
    """可以选择不做的步骤（optional），连同依赖它们做成的后续步骤：下标的集合。"""
    out, inside = set(), False
    for i, st in enumerate(steps):
        if st.get("optional"):
            inside = True
        elif not (inside and st.get("link", "also") in CHAINED_LINKS):
            inside = False
        if inside:
            out.add(i)
    return out


def all_steps(steps):
    """连同分支里的步骤一起列出。"""
    for st in steps:
        yield st
        for case in st.get("cases", []):
            yield from all_steps(case["do"])


class EffectGen(ActsMixin, ContMixin):
    """一个效果的注册代码与它的 condition / cost / target / operation 函数。"""

    def __init__(self, gen, eff):
        self.g = gen
        self.card = gen.card
        self.eff = eff
        self.k = eff["index"]
        self.v = "e%d" % self.k
        self.targets = {t["as"]: t["sel"] for t in eff.get("target", []) if t.get("as")}
        for step in eff.get("do", []):
            what = step.get("what")
            if is_ref(what) and "." in what["ref"] and self.kept_is_self(what["ref"]):
                step["what"] = {"ref": "self"}

    def kept_is_self(self, ref):
        """别的效果留下的绑定指的是这张卡自己（星尘龙「为那个效果发动而解放的这张卡」）：同一张卡由「①适用过」的标记确认。"""
        eid, key = ref.split(".", 1)
        src = next((e for e in self.card["effects"] if e["id"] == eid), None)
        if src is None:                  # chain.card、battle.you 这类内置引用
            return False
        step = next(s for s in src["cost"] + src["do"] if s.get("as") == key)
        return is_ref(step.get("what"), "self")

    # ------------------------------------------------------------ 注册

    def register(self):
        if "rule" in self.eff:          # 卡片级的规则文字
            return self.rule()
        t = self.eff["type"]
        if t == "continuous":
            return self.continuous()
        if t == "procedure":
            return self.procedure()
        return self.activated()

    def count_limit(self, oath_ok=True):
        """SetCountLimit 的参数。引擎一个效果只能挂一个次数，几种额度同时有时取最少的次数（都是 1 时就是 1）。"""
        own = limits_of(self.card, self.eff, scope="card") + limits_of(self.card, self.eff, scope="face_up")
        names = limits_of(self.card, self.eff, scope="name")
        if names:
            key, lim = names[0]
            code = self.g.code_offset(self.g.limit_keys[key])
            if lim["unit"] in ("procedure", "activate_card") and oath_ok:
                code += "+EFFECT_COUNT_CODE_OATH"
            if lim["per"] == "duel":
                code += "+EFFECT_COUNT_CODE_DUEL"
            return "%d,%s" % (min(l["n"] for _, l in names + own), code)
        if own:
            return "%d" % min(l["n"] for _, l in own)
        return None

    def description(self):
        if self.eff["type"] == "procedure":
            text = "特殊召唤"
        else:
            first = self.eff["do"][0]["act"] if self.eff["do"] else "apply_continuous"
            text = SHORT.get(first, "效果")
        if self.eff["block"] == "pendulum":
            text = "灵摆效果：" + text
        return "aux.Stringid(id,%d)" % self.g.add_string(self.eff["label"] + text)

    def categories(self):
        cats = []
        for step in all_steps(self.eff["do"]):
            act = step["act"]
            if act == "apply_continuous" and "on" in applies(step)[0]:
                cats.extend(CATEGORY[s["act"]] for s in applies(step)[0]["do"] if s["act"] in CATEGORY)
                continue
            if act == "apply_continuous" and applies(step)[0].get("cont") == "atk_update":
                cats.append("CATEGORY_ATKCHANGE")
            if act in CATEGORY:
                cats.append(CATEGORY[act])
            what = step.get("what") or {}
            if act == "create_token":
                cats += ["CATEGORY_TOKEN", "CATEGORY_SPECIAL_SUMMON"]
            if act == "one_of":
                cats += ["CATEGORY_TOHAND", "CATEGORY_SPECIAL_SUMMON"]
                if "grave" in what.get("where", []):
                    cats += ["CATEGORY_GRAVE_ACTION", "CATEGORY_GRAVE_SPSUMMON"]
            if act == "perform_summon":
                cats.append("CATEGORY_SPECIAL_SUMMON")
                if "deck" in step["materials"].get("where", []):
                    cats.append("CATEGORY_DECKDES")
            if act == "banish" and self.eff.get("declare"):
                cats.append("CATEGORY_ANNOUNCE")
            if act == "add_to_hand" and not is_ref(what) and "deck" in what.get("where", []):
                cats.append("CATEGORY_SEARCH")
            if act == "send_to_gy" and not is_ref(what) and "deck" in what.get("where", []):
                cats.append("CATEGORY_DECKDES")
        return list(dict.fromkeys(cats))

    def event_code(self):
        on = self.eff.get("on")
        if not on:
            return "EVENT_FREE_CHAIN" if self.eff["type"] in ("activation", "quick") else None
        ev = on["event"]
        if isinstance(ev, list):
            ev = ev[0]          # 其余的事件在注册后克隆
        if ev == "summon_attempt":
            return {"special": "EVENT_SPSUMMON", "normal": "EVENT_SUMMON", "flip": "EVENT_FLIP_SUMMON"}[
                on.get("method", "special")]
        if ev == "phase_end" and self.eff["type"] in ("activation", "quick"):
            return "EVENT_FREE_CHAIN"   # 「战斗阶段结束时」的发动：自由时点 + 当前阶段的条件
        if ev == "effect_activated":
            return "EVENT_CHAINING"
        if ev == "attack_declared":
            return "EVENT_ATTACK_ANNOUNCE"
        if ev == "becomes_attack_target":
            return "EVENT_BE_BATTLE_TARGET"
        if ev == "sent_to_gy":
            return "EVENT_TO_GRAVE"
        if ev in SUMMON_EVENTS:
            return SUMMON_EVENTS[ev]
        if ev == "phase_window":
            return "EVENT_PHASE+" + {"end": "PHASE_END", "standby": "PHASE_STANDBY"}[on["phase"]]
        raise NotImplementedError("事件 %r 还没有 Lua 写法" % ev)

    def is_single_trigger(self):
        on = self.eff.get("on") or {}
        return is_ref(on.get("subject"), "self")

    def activated(self):
        eff, v = self.eff, self.v
        t = eff["type"]
        if eff.get("modes"):
            return self.modes()
        L = ["--" + (eff["label"] or "发动"), "local %s=Effect.CreateEffect(c)" % v]
        if t != "activation":
            L.append("%s:SetDescription(%s)" % (v, self.description()))
        cats = self.categories()
        if cats:
            L.append("%s:SetCategory(%s)" % (v, "+".join(cats)))
        if t == "activation":
            typ = "EFFECT_TYPE_ACTIVATE"
        elif t == "quick":
            typ = "EFFECT_TYPE_QUICK_O"
        elif t == "ignition":
            typ = "EFFECT_TYPE_IGNITION"
        else:
            trig = "EFFECT_TYPE_TRIGGER_O" if eff.get("optional", True) else "EFFECT_TYPE_TRIGGER_F"
            typ = ("EFFECT_TYPE_SINGLE+" if self.is_single_trigger() else "EFFECT_TYPE_FIELD+") + trig
        L.append("%s:SetType(%s)" % (v, typ))
        code = self.event_code()
        if code:
            L.append("%s:SetCode(%s)" % (v, code))
        props = []
        if eff["target"]:
            props.append("EFFECT_FLAG_CARD_TARGET")
        if t == "trigger" and eff.get("optional", True) and self.timing() == "if":
            props.append("EFFECT_FLAG_DELAY")
        if any(s["act"] == "negate_activation" for s in eff["do"]):
            props.append("EFFECT_FLAG_DAMAGE_STEP+EFFECT_FLAG_DAMAGE_CAL")
        if limits_of(self.card, eff, scope="face_up"):
            props.append("EFFECT_FLAG_NO_TURN_RESET")      # 「只在这张卡表侧表示存在才有1次」：次数不随回合恢复
        if (eff.get("window") or {}).get("phase") == "damage_step":
            props.append("EFFECT_FLAG_DAMAGE_STEP")
        if props:
            L.append("%s:SetProperty(%s)" % (v, "+".join(props)))
        if t in ("quick", "ignition") or (t == "trigger" and not self.is_single_trigger()):
            L.append("%s:SetRange(%s)" % (v, "+".join(LOC[w] for w in eff["range"])))
        if (eff.get("window") or {}).get("phase") == "damage_step":
            L.append("%s:SetHintTiming(TIMING_DAMAGE_STEP)" % v)
        elif (eff.get("on") or {}).get("event") == "phase_end" and code == "EVENT_FREE_CHAIN":
            L.append("%s:SetHintTiming(%s)" % (v, {"battle": "TIMING_BATTLE_END"}[eff["on"]["phase"]]))
        elif code == "EVENT_FREE_CHAIN" and t == "quick":
            L.append("%s:SetHintTiming(0,TIMINGS_CHECK_MONSTER)" % v)
        limit = self.count_limit()
        if not limit and code and code.startswith("EVENT_PHASE"):
            limit = "1"
        if limit:
            L.append("%s:SetCountLimit(%s)" % (v, limit))
        for kind, fn in (("Condition", self.condition_fn()), ("Cost", getattr(self, "shared_cost", None) or self.cost_fn()),
                         ("Target", self.target_fn()), ("Operation", self.operation_fn())):
            if fn:
                L.append("%s:Set%s(%s)" % (v, kind, fn))
        L.append("c:RegisterEffect(%s)" % v)
        ev = (eff.get("on") or {}).get("event")
        if isinstance(ev, list):
            for i, more in enumerate(ev[1:]):
                cv = "%s_%d" % (v, i + 2)
                L += ["local %s=%s:Clone()" % (cv, v), "%s:SetCode(%s)" % (cv, SUMMON_EVENTS[more]),
                      "c:RegisterEffect(%s)" % cv]
        return L

    def timing(self):
        return self.eff.get("timing") or "when"

    def modes(self):
        """「●」列表：每个选项注册成一个效果，共用同一个代价（神之通告的写法）。"""
        eff = self.eff
        cost = self.cost_fn()
        out = []
        for i, opt in enumerate(eff["modes"]["options"]):
            sub = dict(eff, on=opt.get("on"), timing=opt.get("timing"), condition=opt.get("condition", []),
                       target=opt.get("target", []), do=opt.get("do", []), modes=None, cost=[],
                       index=eff["index"] * 10 + i + 1)
            gen = EffectGen(self.g, sub)
            gen.shared_cost = cost
            out += gen.activated()
        return out

    def value_lua(self, v):
        """数值表达式 → Lua。数这张卡发动后所在的自己场上时，从手卡发动的要把它自己算进去。"""
        if isinstance(v, int):
            return str(v)
        if "count" in v:
            sel = v["count"]
            s_, o_ = sides(sel)
            if sel.get("filter"):
                expr = "Duel.GetMatchingGroupCount(%s,tp,%s,%s,nil,e,tp)" % (self.g.filter_fn(sel), s_, o_)
            else:
                expr = "Duel.GetFieldGroupCount(tp,%s,%s)" % (s_, o_)
            if self.eff.get("type") == "activation" and sel["who"] == "you" and set(sel["where"]) & {"field", "szone"}:
                expr = "(%s+(e:GetHandler():IsLocation(LOCATION_HAND) and 1 or 0))" % expr
            return expr
        raise NotImplementedError("数值 %r 还没有 Lua 写法" % v)

    # ------------------------------------------------------------ 条件

    def cond_exprs(self, conds, pre):
        """把条件列表译成表达式；需要的局部变量写进 pre。"""
        out = []
        for c in conds:
            kind = c.get("cond")
            if kind == "card_count":
                sel = c["sel"]
                s_, o_ = sides(sel)
                op, n = c["cmp"]
                if sel.get("filter"):
                    f = self.g.filter_fn(sel)
                    out.append("Duel.GetMatchingGroupCount(%s,tp,%s,%s,nil,e,tp)%s" % (f, s_, o_, cmp_lua(op, n)))
                else:
                    out.append("Duel.GetFieldGroupCount(tp,%s,%s)%s" % (s_, o_, cmp_lua(op, n)))
            elif kind == "material_possession" and is_ref(c.get("what"), "self"):
                op, n = c["cmp"]
                out.append("e:GetHandler():GetOverlayCount()%s" % cmp_lua(op, n))
            elif kind == "named_card_used":
                flag = self.g.code_offset(self.g.flags[c["effect"]])
                out.append("e:GetHandler():GetFlagEffect(%s)>0" % flag)
            elif kind in ("own_turn", "opponent_turn"):
                out.append("Duel.GetTurnPlayer()==%s" % ("tp" if kind == "own_turn" else "1-tp"))
            elif kind == "self_location" and c.get("activated_from") == "set":
                out.append("not e:GetHandler():IsStatus(STATUS_ACT_FROM_HAND) and e:GetHandler():IsLocation(LOCATION_SZONE)")
            elif kind == "raw":
                out.append(c["lua"])
            elif kind == "battle_participant":
                side = "tp" if c.get("side", "you") == "you" else "1-tp"
                preds = self.g.preds({"filter": c.get("filter", []), "where": ["mzone"]},
                                     ["$c:IsControler(%s)" % side, "$c:IsRelateToBattle()"])
                name = "s.battlefilter%d" % self.k
                self.g.add_func("function %s(c,tp)\n\treturn %s\nend" % (name, " and ".join(preds)))
                pre += ["local a=Duel.GetAttacker()", "local d=Duel.GetAttackTarget()"]
                out.append("d~=nil and d:IsFaceup() and (%s(a,tp) or %s(d,tp))" % (name, name))
            elif kind == "value_compare":
                out.append("%s%s%s" % (self.value_lua(c["left"]), LUA_OP[c["op"]], self.value_lua(c["right"])))
            elif kind == "summon_history" and is_ref(c.get("what"), "self"):
                out.append("e:GetHandler():IsSummonType(%s)" % SUMMON_TYPE[c["method"]])
            else:
                raise NotImplementedError("条件 %r 还没有 Lua 写法" % c)
        return out

    def event_exprs(self, pre):
        on = self.eff.get("on")
        if not on:
            return []
        out = []
        ev = on["event"]
        if self.eff.get("window", {}).get("phase") == "damage_step":
            out.append("Duel.GetCurrentPhase()==PHASE_DAMAGE and not Duel.IsDamageCalculated()")
        if isinstance(ev, list) or ev in SUMMON_EVENTS:
            if on.get("method") and is_ref(on.get("subject"), "self"):
                out.append("e:GetHandler():IsSummonType(%s)" % SUMMON_TYPE[on["method"]])
        if ev == "sent_to_gy":
            if "destroyed" in (on.get("reason") or []):
                out.append("e:GetHandler():IsReason(REASON_DESTROY)")
            if on.get("from"):
                out.append("e:GetHandler():IsPreviousLocation(%s)" % "+".join(
                    dict.fromkeys(LOC[w] for w in on["from"])))
                if "hand" in on["from"]:
                    out.append("e:GetHandler():IsPreviousControler(tp)")
            if on.get("turn"):
                out.append("Duel.GetTurnPlayer()==%s" % ("tp" if on["turn"] == "you" else "1-tp"))
        elif ev == "attack_declared":
            by = on.get("by", "any")
            if by != "any":
                out.append("Duel.GetAttacker():IsControler(%s)" % ("1-tp" if by == "opp" else "tp"))
        elif ev == "becomes_attack_target":
            out.append("Duel.GetAttackTarget()==e:GetHandler()")
        elif ev == "phase_window":
            if on.get("turn") in ("you", "opp"):
                out.append("Duel.GetTurnPlayer()==%s" % ("tp" if on["turn"] == "you" else "1-tp"))
        elif ev == "phase_end":
            out.append("Duel.GetCurrentPhase()==%s" % PHASE_CODE[on["phase"]])
        elif ev == "summon_attempt":
            out.append("aux.NegateSummonCondition()")
        elif ev == "effect_activated":
            if "mzone" in self.eff["range"]:
                out.append("not e:GetHandler():IsStatus(STATUS_BATTLE_DESTROYED)")
            if on.get("by") == "opp":
                out.append("rp==1-tp")
            if on.get("what") == "card":
                out.append("re:IsHasType(EFFECT_TYPE_ACTIVATE)")
            if (on.get("where") or {}).get("column_of") == {"ref": "self"}:
                out.append("e:GetHandler():GetColumnGroup():IsContains(re:GetHandler())")
            kinds = set(on.get("kinds", ["monster", "spell", "trap"]))
            if kinds != {"monster", "spell", "trap"}:
                out.append("re:IsActiveType(%s)" % "+".join(TYPE[k] for k in sorted(kinds)))
            inc = [x for x in on.get("includes", []) if x != "destroy_on_field"]
            if inc:
                alts = []
                if "ss_from_deck" in inc:
                    pre.append("local ex2,g2,gc2,dp2,dv2=Duel.GetOperationInfo(ev,CATEGORY_SPECIAL_SUMMON)")
                    alts.append("(ex2 and dv2&LOCATION_DECK==LOCATION_DECK)")
                if "send_from_deck_to_gy" in inc:
                    pre.append("local ex3,g3,gc3,dp3,dv3=Duel.GetOperationInfo(ev,CATEGORY_TOGRAVE)")
                    alts.append("(ex3 and dv3&LOCATION_DECK==LOCATION_DECK)")
                    alts.append("re:IsHasCategory(CATEGORY_DECKDES)")
                if "add_from_deck" in inc:
                    alts.append("re:IsHasCategory(CATEGORY_DRAW)")
                    alts.append("re:IsHasCategory(CATEGORY_SEARCH)")
                if "special_summon_from_gy" in inc:
                    pre.append("local ex4,g4,gc4,dp4,dv4=Duel.GetOperationInfo(ev,CATEGORY_SPECIAL_SUMMON)")
                    alts.append("(ex4 and (dv4&LOCATION_GRAVE==LOCATION_GRAVE"
                                " or g4 and g4:IsExists(Card.IsLocation,1,nil,LOCATION_GRAVE)))")
                    alts.append("re:IsHasCategory(CATEGORY_GRAVE_SPSUMMON)")
                out.append("(" + " or ".join(alts) + ")")
            if on.get("targets"):
                t = on["targets"]
                pre.append("local tg=re:IsHasProperty(EFFECT_FLAG_CARD_TARGET) and Duel.GetChainInfo(ev,CHAININFO_TARGET_CARDS)")
                cond = " and ".join(["c:IsLocation(%s)" % "+".join(LOC[w] for w in t["where"])] +
                                    (["c:IsControler(tp)"] if t["who"] == "you" else
                                     ["c:IsControler(1-tp)"] if t["who"] == "opp" else []) +
                                    self.g.preds(t))
                name = "s.chaintg%d" % self.k
                self.g.add_func("function %s(c,tp)\n\treturn %s\nend" % (name, cond))
                out.append("tg and tg:IsExists(%s,1,nil,tp)" % name)
            if "destroy_on_field" in on.get("includes", []):
                pre.append("local ex,tg,tc=Duel.GetOperationInfo(ev,CATEGORY_DESTROY)")
                out.append("ex and tg~=nil and tc+tg:FilterCount(Card.IsOnField,nil)-tg:GetCount()>0")
            acts = {s["act"] for s in self.eff["do"]}
            if "negate_activation" in acts:
                out.append("Duel.IsChainNegatable(ev)")
            elif "negate_effect" in acts:
                out.append("Duel.IsChainDisablable(ev)")
        return out

    def condition_fn(self):
        pre = []
        exprs = self.event_exprs(pre) + self.cond_exprs(self.eff["condition"], pre)
        if not self.eff.get("on") and (self.eff.get("window") or {}).get("phase") == "damage_step":
            exprs.insert(0, "Duel.GetCurrentPhase()==PHASE_DAMAGE and not Duel.IsDamageCalculated()")
        if not exprs:
            return None
        name = "s.condition%d" % self.k
        self.g.add_func("function %s(e,tp,eg,ep,ev,re,r,rp)\n%s\treturn %s\nend" % (
            name, "".join("\t%s\n" % p for p in pre), "\n\t\tand ".join(exprs)))
        return name

    # ------------------------------------------------------------ 代价

    def cost_parts(self, step):
        """返回 (检查表达式, 执行语句列表)。"""
        act = step["act"]
        what = step.get("what")
        if act == "discard":
            return "e:GetHandler():IsDiscardable()", ["Duel.SendtoGrave(e:GetHandler(),REASON_COST+REASON_DISCARD)"]
        if act == "send_to_gy" and is_ref(what, "self"):
            return "e:GetHandler():IsAbleToGraveAsCost()", ["Duel.SendtoGrave(e:GetHandler(),REASON_COST)"]
        if act == "release" and is_ref(what, "self"):
            return "e:GetHandler():IsReleasable()", ["Duel.Release(e:GetHandler(),REASON_COST)"]
        if act == "banish" and is_ref(what, "self"):
            return "e:GetHandler():IsAbleToRemoveAsCost()", ["Duel.Remove(e:GetHandler(),POS_FACEUP,REASON_COST)"]
        if act == "pay_lp":
            return "Duel.CheckLPCost(tp,%d)" % step["amount"], ["Duel.PayLPCost(tp,%d)" % step["amount"]]
        if act == "remove_counter" and is_ref(step.get("from"), "self"):
            code, n = COUNTER_CODE[step["counter"]], step.get("count", 1)
            return ("e:GetHandler():IsCanRemoveCounter(tp,%s,%d,REASON_COST)" % (code, n),
                    ["e:GetHandler():RemoveCounter(tp,%s,%d,REASON_COST)" % (code, n)])
        if act == "detach_xyz_material":
            n = step.get("count", 1)
            return ("e:GetHandler():CheckRemoveOverlayCard(tp,%d,REASON_COST)" % n,
                    ["e:GetHandler():RemoveOverlayCard(tp,%d,%d,REASON_COST)" % (n, n)])
        if act == "release":
            f = self.g.filter_fn(what)
            n = what.get("count", 1)
            return ("Duel.CheckReleaseGroup(tp,%s,%d,nil,e,tp)" % (f, n),
                    ["local g=Duel.SelectReleaseGroup(tp,%s,%d,%d,nil,e,tp)" % (f, n, n), "Duel.Release(g,REASON_COST)"])
        if act in ("send_to_gy", "banish"):
            able = "$c:IsAbleToGraveAsCost()" if act == "send_to_gy" else "$c:IsAbleToRemoveAsCost()"
            f = self.g.filter_fn(what, [able])
            s_, o_ = sides(what)
            n = what.get("count", 1)
            do = "Duel.SendtoGrave(g,REASON_COST)" if act == "send_to_gy" else "Duel.Remove(g,POS_FACEUP,REASON_COST)"
            body = ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % HINT[act],
                    "local g=Duel.SelectMatchingCard(tp,%s,tp,%s,%s,%d,%d,e:GetHandler(),e,tp)" % (f, s_, o_, n, n), do]
            if step.get("as"):          # 支付时的卡名，处理时引用（「和那只怪兽的原本的卡名……」）
                body.append("e:SetLabel(g:GetFirst():GetOriginalCode())")
            return ("Duel.IsExistingMatchingCard(%s,tp,%s,%s,%d,e:GetHandler(),e,tp)" % (f, s_, o_, n), body)
        raise NotImplementedError("代价 %r 还没有 Lua 写法" % act)

    def cost_fn(self):
        restricts = [r for r in self.eff.get("restrict", []) if r["span"] == "whole_turn"]
        if not self.eff["cost"] and not restricts:
            return None
        checks, body = [], []
        for step in self.eff["cost"]:
            chk, do = self.cost_parts(step)
            checks.append(chk)
            body.extend(do)
        for r in restricts:
            chk, do = self.oath_parts(r)
            checks.extend(chk)
            body.extend(do)
        name = "s.cost%d" % self.k
        self.g.add_func("function %s(e,tp,eg,ep,ev,re,r,rp,chk)\n\tif chk==0 then return %s end\n%s\nend" % (
            name, " and ".join(checks), "\n".join(indent(body))))
        return name

    def oath_parts(self, r):
        """整回合誓约（发动条件）：发动前这回合没做过，发动后到回合结束也不能做（「这张卡发动的回合，自己不能……」）。
        卡的发动被无效时誓约跟着解除，只是效果被无效时仍然留着（强欲而谦虚之壶的官方说明）——引擎的 OATH 正是这样。"""
        if r["who"] == "both":
            raise NotImplementedError("整回合的自肃目前只支持限制自己或这张卡")
        checks, body = [], []
        if r["who"] == "self":
            for i, f in enumerate(r["forbid"]):
                if f != "attack":
                    raise NotImplementedError("整回合的「这张卡不能直接攻击」还没有 Lua 写法（没有对应的活动记录）")
                checks.append("e:GetHandler():GetAttackAnnouncedCount()==0")
                le = "oe%d" % (i + 1)
                body += ["local %s=Effect.CreateEffect(e:GetHandler())" % le, "%s:SetType(EFFECT_TYPE_SINGLE)" % le,
                         "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_OATH)" % le,
                         "%s:SetCode(%s)" % (le, SELF_FORBID[f]),
                         "%s:SetReset(RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END)" % le,
                         "e:GetHandler():RegisterEffect(%s,true)" % le]
            return checks, body
        n = 0
        for f in r["forbid"]:
            n += 1
            le = "oe%d" % n
            if f == "attack":                # 「这张卡发动的回合，自己不用「X」怪兽不能攻击宣言」
                if (r.get("except") or {}).get("card"):
                    raise NotImplementedError("整回合的「这张卡 / 对象以外的怪兽不能攻击」还没有 Lua 写法")
                limit = self.monster_limit_fn(r)
                if limit:
                    counter = self.g.activity_counter("ACTIVITY_ATTACK", self.attack_counter_fn(r))
                    checks.append("Duel.GetCustomActivityCount(%s,tp,ACTIVITY_ATTACK)==0" % counter)
                else:
                    checks.append("Duel.GetActivityCount(tp,ACTIVITY_ATTACK)==0")
                body += ["local %s=Effect.CreateEffect(e:GetHandler())" % le, "%s:SetType(EFFECT_TYPE_FIELD)" % le,
                         "%s:SetProperty(EFFECT_FLAG_OATH)" % le, "%s:SetCode(EFFECT_CANNOT_ATTACK_ANNOUNCE)" % le,
                         "%s:SetTargetRange(LOCATION_MZONE,0)" % le]
                if limit:
                    body.append("%s:SetTarget(%s)" % (le, limit))
                body += ["%s:SetReset(RESET_PHASE+PHASE_END)" % le, "Duel.RegisterEffect(%s,tp)" % le]
                continue
            if f == "activate":              # 「这张卡发动的回合，自己不能把「X」卡以外的魔法卡发动」
                counter = self.g.activity_counter("ACTIVITY_CHAIN", self.chain_counter_fn(r))
                checks.append("Duel.GetCustomActivityCount(%s,tp,ACTIVITY_CHAIN)==0" % counter)
                body += ["local %s=Effect.CreateEffect(e:GetHandler())" % le, "%s:SetType(EFFECT_TYPE_FIELD)" % le,
                         "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET+EFFECT_FLAG_OATH)" % le,
                         "%s:SetCode(EFFECT_CANNOT_ACTIVATE)" % le, "%s:SetTargetRange(1,0)" % le,
                         "%s:SetValue(%s)" % (le, self.activate_limit_fn(r)),
                         "%s:SetReset(RESET_PHASE+PHASE_END)" % le, "Duel.RegisterEffect(%s,tp)" % le]
                continue
            if f not in FORBID_PLAYER and f not in FORBID:
                from ..model.vocab import RESTRICT_FORBID_ZH
                raise NotImplementedError("整回合的「%s」还没有 Lua 写法（引擎没有本回合做过没有的记录），"
                                          "请改用「这个效果的发动后」或「这个回合」" % RESTRICT_FORBID_ZH.get(f, f))
            if f in FORBID_PLAYER:
                activity, codes = FORBID_PLAYER[f]
                checks.append("Duel.GetActivityCount(tp,%s)==0" % activity)
                for j, code in enumerate(codes):
                    v = le if j == 0 else "%s_%d" % (le, j)
                    body += ["local %s=Effect.CreateEffect(e:GetHandler())" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v,
                             "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET+EFFECT_FLAG_OATH)" % v, "%s:SetCode(%s)" % (v, code),
                             "%s:SetReset(RESET_PHASE+PHASE_END)" % v, "%s:SetTargetRange(1,0)" % v,
                             "Duel.RegisterEffect(%s,tp)" % v]
                continue
            activity, code = FORBID[f]
            limit = self.summon_limit_fn(r, f)
            if limit and (r.get("only") or r.get("from")):
                counter = self.g.activity_counter(activity, self.counter_filter_fn(r))
                checks.append("Duel.GetCustomActivityCount(%s,tp,%s)==0" % (counter, activity))
            else:
                checks.append("Duel.GetActivityCount(tp,%s)==0" % activity)
            body += ["local %s=Effect.CreateEffect(e:GetHandler())" % le, "%s:SetType(EFFECT_TYPE_FIELD)" % le,
                     "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET+EFFECT_FLAG_OATH)" % le, "%s:SetCode(%s)" % (le, code),
                     "%s:SetReset(RESET_PHASE+PHASE_END)" % le, "%s:SetTargetRange(1,0)" % le]
            if (r.get("except") or {}).get("by_effect") == "this_card" and f == "special_summon":
                body.append("%s:SetLabelObject(e)" % le)
            if limit:
                body.append("%s:SetTarget(%s)" % (le, limit))
            body.append("Duel.RegisterEffect(%s,tp)" % le)
        return checks, body

    def _only_expr(self, r, var="c"):
        """「不是X怪兽」里的 X：选卡过滤条件 → Lua 表达式；没有 only 时为 None。"""
        if not r.get("only"):
            return None
        preds = self.g.preds({"where": ["mzone"], "filter": r["only"]}, var=var)
        return " and ".join(preds) if preds else "true"

    def summon_limit_fn(self, r, f):
        """召唤类限制的 SetTarget：返回 true 的怪兽不能召唤 / 特殊召唤。没有任何筛选时返回 None（全面禁止）。"""
        conds = []
        if r.get("from"):                    # 「不能从卡组·额外卡组把怪兽特殊召唤」
            conds.append("c:IsLocation(%s)" % "+".join(LOC[z] for z in r["from"]))
        only = self._only_expr(r)
        if only:
            conds.append("not (%s)" % only)
        if (r.get("except") or {}).get("by_effect") == "this_card" and f == "special_summon":
            conds.append("e:GetLabelObject()~=se")       # 「这张卡的效果以外」：通常召唤没有效果，不用写
        if not conds:
            return None
        body = "function %%s(e,c,sump,sumtype,sumpos,targetp,se)\n\treturn %s\nend" % " and ".join(conds)
        base = "s.%slimit%d" % ("sp" if f == "special_summon" else "sum", self.k)
        name, n = base, 1
        while any(fn.startswith("function %s(" % name) for fn in self.g.funcs):
            if body % name in self.g.funcs:          # 同一个效果的整回合与处理后用同一个限制：共用
                return name
            n += 1
            name = "%s_%d" % (base, n)
        self.g.add_func(body % name)
        return name

    def counter_filter_fn(self, r):
        """自定义活动计数的过滤：返回 true 的特殊召唤不算数（表侧的「X」怪兽，或者不是从额外卡组出来的）。"""
        only = self._only_expr(r)
        ok = "c:IsFaceup() and %s" % only if only else None
        if r.get("from"):
            ok = "not c:IsSummonLocation(%s)" % "+".join(LOC[z] for z in r["from"]) + (" or %s" % ok if ok else "")
        body = "function %%s(c)\n\treturn %s\nend" % (ok or "false")
        base = name = "s.counterfilter%d" % self.k
        n = 1
        while any(fn.startswith("function %s(" % name) for fn in self.g.funcs):
            if body % name in self.g.funcs:
                return name
            n += 1
            name = "%s_%d" % (base, n)
        self.g.add_func(body % name)
        return name

    def after_resolution_lines(self):
        """处理后建立的自肃（「这个效果的发动后，直到回合结束时……」）：写在处理的最后。效果被无效时不处理也就不建立；
        主要处理没成功仍然建立（卫星闪灵启辉器的官方说明）。"""
        out = []
        for r in self.eff["restrict"]:
            if r["span"] not in ("after_resolution", "this_turn"):     # 「这个回合，……」也在处理时登记
                continue
            if r["until"] == "end_of_turn":
                reset = "RESET_PHASE+PHASE_END"
            else:
                reset = "RESET_PHASE+PHASE_END+RESET_SELF_TURN,Duel.GetTurnPlayer()==tp and 2 or 1"
            if r["who"] == "self":
                out.append("if c:IsRelateToEffect(e) then")
                for i, f in enumerate(r["forbid"]):
                    v = "re%d" % (i + 1)
                    out += indent(["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                                   "%s:SetCode(%s)" % (v, SELF_FORBID[f]),
                                   "%s:SetReset(RESET_EVENT+RESETS_STANDARD+%s)" % (v, reset), "c:RegisterEffect(%s)" % v])
                out.append("end")
                continue
            rng = "1,1" if r["who"] == "both" else "1,0"
            for i, f in enumerate(r["forbid"]):
                if f not in FORBID_PLAYER and f not in FORBID:
                    out += self.lock_lines(r, f, "re%d_0" % (i + 1), reset)
                    continue
                if f in FORBID_PLAYER:
                    codes = FORBID_PLAYER[f][1]
                    limit = None
                else:
                    codes = (FORBID[f][1],)
                    limit = self.summon_limit_fn(r, f)
                for j, code in enumerate(codes):
                    v = "re%d_%d" % (i + 1, j)
                    out += ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v,
                            "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % v, "%s:SetCode(%s)" % (v, code),
                            "%s:SetTargetRange(%s)" % (v, rng)]
                    if (r.get("except") or {}).get("by_effect") == "this_card" and f == "special_summon":
                        out.append("%s:SetLabelObject(e)" % v)
                    if limit:
                        out.append("%s:SetTarget(%s)" % (v, limit))
                    out += ["%s:SetReset(%s)" % (v, reset), "Duel.RegisterEffect(%s,tp)" % v]
        return out

    def lock_lines(self, r, f, v, reset):
        """处理时登记的第二批限制（写法照官方卡：造反剧、共斗、大寒气、左腕的代偿、强欲而金满之壶、灵摆停顿、
        铁兽战线、No.72……）。"""
        both = r["who"] == "both"
        head = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v]
        tail = ["%s:SetReset(%s)" % (v, reset), "Duel.RegisterEffect(%s,tp)" % v]
        if f in ("attack", "direct_attack"):          # 「这张卡以外的自己怪兽不能攻击」「自己不用「X」怪兽不能直接攻击」
            code = {"attack": "EFFECT_CANNOT_ATTACK", "direct_attack": "EFFECT_CANNOT_DIRECT_ATTACK"}[f]
            out = head + ["%s:SetCode(%s)" % (v, code),
                          "%s:SetTargetRange(LOCATION_MZONE,%s)" % (v, "LOCATION_MZONE" if both else "0")]
            limit = self.monster_limit_fn(r)
            if limit:
                out.append("%s:SetTarget(%s)" % (v, limit))
            card = (r.get("except") or {}).get("card")
            if card == "self":
                out.append("%s:SetLabel(c:GetFieldID())" % v)
            elif card == "targets":
                out.append("%s:SetLabel(tc and tc:GetFieldID() or 0)" % v)
            return out + tail
        rng = "1,1" if both else "1,0"
        player = ["%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % v, "%s:SetTargetRange(%s)" % (v, rng)]
        if f == "activate":                            # 「自己不能把地属性以外的怪兽的效果发动」
            return head + player + ["%s:SetCode(EFFECT_CANNOT_ACTIVATE)" % v,
                                    "%s:SetValue(%s)" % (v, self.activate_limit_fn(r))] + tail
        if f == "set":                                 # 「自己不能把卡盖放」「自己不能把魔法·陷阱卡盖放」
            codes = ["EFFECT_CANNOT_SSET"] + (["EFFECT_CANNOT_MSET", "EFFECT_CANNOT_TURN_SET"]
                                               if r.get("kinds", "card") == "card" else [])
            out = []
            for j, code in enumerate(codes):
                w = "%s_%d" % (v, j)
                out += ["local %s=Effect.CreateEffect(c)" % w, "%s:SetType(EFFECT_TYPE_FIELD)" % w,
                        "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % w, "%s:SetTargetRange(%s)" % (w, rng),
                        "%s:SetCode(%s)" % (w, code), "%s:SetTarget(aux.TRUE)" % w,
                        "%s:SetReset(%s)" % (w, reset), "Duel.RegisterEffect(%s,tp)" % w]
            return out
        if f == "draw_by_effect":                      # 「自己不能用卡的效果抽卡」
            return head + player + ["%s:SetCode(EFFECT_CANNOT_DRAW)" % v] + tail
        if f == "search":                              # 「自己不能用抽卡以外的方法从卡组把卡加入手卡」
            return head + player + ["%s:SetCode(EFFECT_CANNOT_TO_HAND)" % v,
                                    "%s:SetTarget(aux.TargetBoolFunction(Card.IsLocation,LOCATION_DECK))" % v] + tail
        if f == "material":                            # 「自己不是兽族怪兽不能作为连接素材」
            code = "EFFECT_CANNOT_BE_%s_MATERIAL" % r["method"].upper()
            only = self._only_expr(r)
            val = self._fn("s.matval%d" % self.k, "function %s(e,c)\n\tif not c then return false end\n"
                                                    "\treturn c:IsControler(e:GetHandlerPlayer())\nend")
            out = head + ["%s:SetCode(%s)" % (v, code),
                          "%s:SetProperty(EFFECT_FLAG_SET_AVAILABLE+EFFECT_FLAG_IGNORE_IMMUNE)" % v,
                          "%s:SetTargetRange(0xff,0xff)" % v]
            if only:
                name = self._fn("s.matlimit%d" % self.k, "function %%s(e,c)\n\treturn not (%s)\nend" % only)
                out.append("%s:SetTarget(%s)" % (v, name))
            return out + ["%s:SetValue(%s)" % (v, val)] + tail
        if f == "half_battle_damage":                  # 「对方受到的战斗伤害变成一半」
            return head + ["%s:SetCode(EFFECT_CHANGE_BATTLE_DAMAGE)" % v,
                           "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % v, "%s:SetTargetRange(0,1)" % v,
                           "%s:SetValue(HALF_DAMAGE)" % v] + tail
        raise NotImplementedError("自肃「%s」还没有 Lua 写法" % f)

    def _fn(self, base, body):
        """按 body（里面的 %s 是函数名）登记一个函数；同样的函数已经有了就共用，不同的换个名字。"""
        name, n = base, 1
        while any(fn.startswith("function %s(" % name) for fn in self.g.funcs):
            if body % name in self.g.funcs:
                return name
            n += 1
            name = "%s_%d" % (base, n)
        self.g.add_func(body % name)
        return name

    def monster_limit_fn(self, r):
        """攻击类限制的 SetTarget：返回 true 的怪兽不能攻击（不是 X 的；这张卡 / 对象以外的，用 Label 里的 FieldID）。"""
        conds = []
        only = self._only_expr(r)
        if only:
            conds.append("not (%s)" % only)
        if (r.get("except") or {}).get("card"):
            conds.append("c:GetFieldID()~=e:GetLabel()")
        if not conds:
            return None
        return self._fn("s.atklimit%d" % self.k, "function %%s(e,c)\n\treturn %s\nend" % " and ".join(conds))

    def attack_counter_fn(self, r):
        """「攻击」的自定义活动计数：X 怪兽的攻击不算数。"""
        return self._fn("s.atkcounter%d" % self.k, "function %%s(c)\n\treturn %s\nend" % self._only_expr(r))

    def activate_match(self, r, re="re"):
        """「发动」限制针对的是哪些发动：怪兽的效果 / 魔法·陷阱卡的效果 / 卡的效果 / 魔法卡的发动，再除去 X。"""
        kind = {"monster": "%s:IsActiveType(TYPE_MONSTER)", "spell_trap": "%s:IsActiveType(TYPE_SPELL+TYPE_TRAP)",
                "card": None, "spell": "%s:IsHasType(EFFECT_TYPE_ACTIVATE) and %s:IsActiveType(TYPE_SPELL)"}[
                    r.get("kinds", "monster")]
        conds = [kind.replace("%s", re)] if kind else []
        only = self._only_expr(r, var="%s:GetHandler()" % re)
        if only:
            conds.append("not (%s)" % only)
        return " and ".join(conds) or "true"

    def activate_limit_fn(self, r):
        return self._fn("s.actlimit%d" % self.k, "function %%s(e,re,tp)\n\treturn %s\nend" % self.activate_match(r))

    def chain_counter_fn(self, r):
        """「发动」的自定义活动计数（ACTIVITY_CHAIN）：不受限制的发动不算数。"""
        return self._fn("s.chaincounter%d" % self.k, "function %%s(re,tp,cid)\n\treturn not (%s)\nend" % self.activate_match(r))

    # ------------------------------------------------------------ 对象与可行性

    def able_for_ref(self, ref):
        """作用在对象 ref 上的动作，各自要求对象满足什么（能否除外、能否特殊召唤……）。"""
        out = []
        for step in self.eff["do"]:
            if not is_ref(step.get("what"), ref):
                continue
            out.extend(able(step["act"]))
        return out

    def gating_steps(self):
        if self.eff["type"] == "trigger" and not self.eff.get("optional", True):
            return []
        out = []
        maybe = optional_part(self.eff["do"])
        for i, step in enumerate(self.eff["do"]):
            if step.get("when_exists") or step.get("if") or i in maybe:    # 可以选择不做的不影响能否发动
                continue
            if i > 0 and step.get("link", "also") == "also":
                continue
            out.append(step)
        return out

    def self_leaves(self):
        """处理中这张卡会先离开场上（回到额外卡组等）：后面特殊召唤可以用它腾出的格子。"""
        return any(is_ref(s.get("what"), "self") and s["act"] in ("return_to_extra", "banish", "send_to_gy", "add_to_hand")
                   for s in self.eff["do"])

    def feasible(self, step):
        special = self.special_feasible(step)
        if special is not None:
            return special
        act = step["act"]
        what = step.get("what")
        if act in ("negate_activation", "negate_effect", "negate_attack", "apply_continuous", "raw", "negate_card_effects"):
            return []
        if act == "draw":
            return ["Duel.IsPlayerCanDraw(%s,%d)" % ("tp" if step.get("player", "you") == "you" else "1-tp",
                                                  step.get("count", 1))]
        if is_ref(what):
            ref = what["ref"]
            if ref == "self":
                if act == "destroy":
                    return ["e:GetHandler():IsDestructable()"]
                if act == "special_summon":
                    return ["Duel.GetLocationCount(tp,LOCATION_MZONE)>0",
                            "e:GetHandler():IsCanBeSpecialSummoned(e,0,tp,false,false)"]
                return [x.replace("$c", "e:GetHandler()") for x in able(act)]
            if ref in self.targets and act == "special_summon":
                if self.self_leaves():
                    return ["Duel.GetMZoneCount(tp,e:GetHandler())>0"]
                return ["Duel.GetLocationCount(tp,LOCATION_MZONE)>0"]
            return []
        f = self.g.filter_fn(what, able(act))
        s_, o_ = sides(what)
        n = 1 if what.get("count") == "all" else what.get("count", 1)
        out = ["Duel.IsExistingMatchingCard(%s,tp,%s,%s,%d,nil,e,tp)" % (f, s_, o_, n)]
        if act == "special_summon":
            out.insert(0, "Duel.GetLocationCount(tp,LOCATION_MZONE)>0")
        return out

    def op_info(self, step, tvars):
        special = self.special_opinfo(step)
        if special is not None:
            return special
        act = step["act"]
        what = step.get("what")
        cat = CATEGORY.get(act)
        if not cat or act == "negate_card_effects":
            return []
        if act == "negate_activation":
            return ["Duel.SetOperationInfo(0,CATEGORY_NEGATE,eg,1,0,0)"]
        if act == "negate_effect":
            return ["Duel.SetOperationInfo(0,CATEGORY_DISABLE,eg,1,0,0)"]
        if act == "draw":
            return ["Duel.SetOperationInfo(0,CATEGORY_DRAW,nil,0,%s,%d)" % (
                "tp" if step.get("player", "you") == "you" else "1-tp", step.get("count", 1))]
        if act == "set_spell_trap":
            return []
        if is_ref(what, "chain") or is_ref(what, "chain.card"):
            return ["if re:GetHandler():IsDestructable() and re:GetHandler():IsRelateToEffect(re) then",
                    "\tDuel.SetOperationInfo(0,%s,eg,1,0,0)" % cat, "end"]
        if is_ref(what, "self"):
            return ["Duel.SetOperationInfo(0,%s,e:GetHandler(),1,0,0)" % cat]
        if is_ref(what):
            return ["Duel.SetOperationInfo(0,%s,%s,1,0,0)" % (cat, tvars[what["ref"]])]
        s_, o_ = sides(what)
        if what.get("count") == "all":
            f = self.g.filter_fn(what, able(act))
            return ["local og=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (f, s_, o_),
                    "Duel.SetOperationInfo(0,%s,og,#og,0,0)" % cat]
        loc = s_ if s_ != "0" else o_
        player = "tp" if what["who"] != "opp" else "1-tp"
        return ["Duel.SetOperationInfo(0,%s,nil,%d,%s,%s)" % (cat, what.get("count", 1), player, loc)]

    def target_fn(self):
        eff = self.eff
        lines, gates, tvars = [], [], {}
        prelude = []
        if self.uses_event_name():      # 「和那张发动的卡卡名不同的……」：先记下那张发动的卡
            prelude.append("e:SetLabelObject(re:GetHandler())")
        chkc = None
        for t in eff["target"]:
            sel = t["sel"]
            f = self.g.filter_fn(sel, self.able_for_ref(t["as"]))
            s_, o_ = sides(sel)
            n = sel.get("count", 1)
            locs = "+".join(LOC[w] for w in sel["where"])
            ctl = {"you": "chkc:IsControler(tp) and ", "opp": "chkc:IsControler(1-tp) and ", "both": ""}[sel["who"]]
            fcall = "aux.TRUE(chkc)" if f == "aux.TRUE" else "%s(chkc,e,tp)" % f
            # 放进这张卡的超量素材时，对象不能是这张卡自己
            onto_self = any(s["act"] == "attach_xyz_material" and is_ref(s.get("what"), t["as"]) for s in eff["do"])
            exclude = "e:GetHandler()" if onto_self else "nil"
            chkc = "chkc:IsLocation(%s) and %s%s%s" % (locs, ctl, fcall, " and chkc~=e:GetHandler()" if onto_self else "")
            gates.append("Duel.IsExistingTarget(%s,tp,%s,%s,%d,%s,e,tp)" % (f, s_, o_, n, exclude))
            act = next((s["act"] for s in eff["do"] if is_ref(s.get("what"), t["as"])), "destroy")
            lines.append("Duel.Hint(HINT_SELECTMSG,tp,%s)" % HINT.get(act, "HINTMSG_TARGET"))
            var = "g" if len(eff["target"]) == 1 else "g_%s" % t["as"]
            lines.append("local %s=Duel.SelectTarget(tp,%s,tp,%s,%s,%d,%d,%s,e,tp)" % (var, f, s_, o_, n, n, exclude))
            tvars[t["as"]] = var
        for d in eff.get("declare", []):
            lines += self.declare_lines(d)
        for step in self.gating_steps():
            gates.extend(self.feasible(step))
        maybe = optional_part(eff["do"])
        for i, step in enumerate(eff["do"]):
            if i not in maybe:              # 可以选择不做的处理不预告
                lines.extend(self.op_info(step, tvars))
        lines.extend(self.g.hooks.get(eff["id"], []))
        if not (lines or gates or chkc):
            return None
        name = "s.target%d" % self.k
        head = "function %s(e,tp,eg,ep,ev,re,r,rp,chk%s)" % (name, ",chkc" if chkc else "")
        body = list(prelude)
        if chkc:
            body.append("if chkc then return %s end" % chkc)
        body.append("if chk==0 then return %s end" % (" and ".join(dict.fromkeys(gates)) or "true"))
        body.extend(lines)
        self.g.add_func(head + "\n" + "\n".join(indent(body)) + "\nend")
        return name

    def uses_event_name(self):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("same_as") == {"ref": "event"} or node.get("same_as") == {"ref": "event", "snapshot": "event"}:
                    found.append(node)
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(self.eff["do"])
        return bool(found)

    def declare_lines(self, d):
        """「宣言1个卡名才能发动」：只能宣言自己卡组里有的卡名（抹杀之指名者的写法）。"""
        if d["kind"] != "card_name":
            raise NotImplementedError("宣言 %r 还没有 Lua 写法" % d["kind"])
        dom = d.get("domain") or {"who": "you", "where": ["deck"]}
        s_, o_ = sides(dom)
        return ["local dg=Duel.GetFieldGroup(tp,%s,%s)" % (s_, o_),
                "local ag=Group.CreateGroup()", "local codes={}",
                "for dc in aux.Next(dg) do", "\tlocal code=dc:GetCode()",
                "\tif not ag:IsExists(Card.IsCode,1,nil,code) then", "\t\tag:AddCard(dc)",
                "\t\ttable.insert(codes,code)", "\tend", "end",
                "table.sort(codes)", "local afilter={codes[1],OPCODE_ISCODE}",
                "for i=2,#codes do", "\ttable.insert(afilter,codes[i])", "\ttable.insert(afilter,OPCODE_ISCODE)",
                "\ttable.insert(afilter,OPCODE_OR)", "end",
                "Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_CODE)",
                "local ac=Duel.AnnounceCard(tp,table.unpack(afilter))",
                "Duel.SetTargetParam(ac)",
                "Duel.SetOperationInfo(0,CATEGORY_ANNOUNCE,nil,0,tp,0)"]

    # ------------------------------------------------------------ 效果处理

    def operation_fn(self):
        eff = self.eff
        self.vars = {}
        self.lingering = 0
        body = ["local c=e:GetHandler()"]
        if eff["target"]:
            body.append("local tc=Duel.GetFirstTarget()")
            for t in eff["target"]:
                self.vars[t["as"]] = ("tc", None)
        body.extend(self.steps(eff["do"], 0))
        if eff["id"] in self.g.flags:
            flag = self.g.code_offset(self.g.flags[eff["id"]])
            body.append("c:RegisterFlagEffect(%s,RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END,0,1)" % flag)
        tail = self.after_resolution_lines()
        if tail:
            # 处理中途 return 的写法（衍生物放不下等）也要登记自肃：把处理包进一个局部函数
            if any(line.lstrip().startswith("return") or " return " in line for line in body[1:]):
                body = body[:1] + ["local function main()"] + indent(body[1:]) + ["end", "main()"]
            body += tail
        name = "s.operation%d" % self.k
        self.g.add_func("function %s(e,tp,eg,ep,ev,re,r,rp)\n%s\nend" % (name, "\n".join(indent(body))))
        return name

    def optional_steps(self, steps, i):
        """玩家可以选择做不做的一步（「那之后，可以……」）：能做的时候问一次，选「是」才做，依赖它的后续步骤一起放在里面。
        「那之后」的 BreakEffect 照官方写在选了「是」之后。"""
        step = steps[i]
        j = i + 1
        while j < len(steps) and steps[j].get("link", "also") in CHAINED_LINKS:
            j += 1
        ask = "Duel.SelectYesNo(tp,aux.Stringid(id,%d))" % self.g.add_string(ASK_TEXT.get(step["act"], "是否继续处理？"))
        inner = (["Duel.BreakEffect()"] if step.get("link") == "then" else []) + \
            self.steps([dict(step, optional=False)] + steps[i + 1:j], 0)
        return ["if %s then" % " and ".join(self.feasible(step) + [ask])] + indent(inner) + ["end"] + self.steps(steps, j)

    def steps(self, steps, i):
        if i >= len(steps):
            return []
        step = steps[i]
        if step.get("optional"):
            return self.optional_steps(steps, i)
        nxt = steps[i + 1] if i + 1 < len(steps) else None
        # 「这个效果除外的怪兽……」引用了前一步的结果，前一步没做成就不适用，所以和「然后」一样嵌套
        chained = nxt is not None and (nxt.get("link", "also") in ("and_if_you_do", "then", "and")
                                       or (step.get("as") and step["as"] in step_refs(nxt)))
        pre, guard, call, post, success = self.step_code(step)
        if step.get("if"):
            guard = [" and ".join(self.cond_exprs(step["if"], pre))] + guard
        out = list(pre)
        if chained and success is None:
            from ..zh import consequence_ref
            if not consequence_ref(step):
                raise NotImplementedError("动作 %r 后面不能接「然后」" % step["act"])
            # 「后果」本身没有做成与否：它已经嵌在所属那一步「做成了」的分支里，后面的「那之后」照常接在它后面
            chained = False
            if nxt.get("link") == "then" and not nxt.get("optional"):
                post = post + ["Duel.BreakEffect()"]
        if chained:
            cond = " and ".join(guard + [success])
            inner = list(post)
            if nxt.get("link") == "then" and not nxt.get("optional"):     # 可以选择不做的：问过之后再 BreakEffect
                inner.append("Duel.BreakEffect()")
            inner += self.steps(steps, i + 1)
            out += ["if %s then" % cond] + indent(inner) + ["end"]
            return out
        stmts = call + post
        if guard:
            out += ["if %s then" % " and ".join(guard)] + indent(stmts) + ["end"]
        else:
            out += stmts
        return out + self.steps(steps, i + 1)

    def select(self, what, act, name):
        """从某处选卡（不取对象）。返回 (pre, 组变量)。"""
        f = self.g.filter_fn(what, able(act))
        s_, o_ = sides(what)
        if "grave" in what["where"]:
            f = "aux.NecroValleyFilter(%s)" % f
        if what.get("count") == "all":
            return ["local %s=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (name, f, s_, o_)], name
        n = what.get("count", 1)
        exclude = "c" if act == "send_to_gy" and "field" in what["where"] else "nil"
        return ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % HINT[act],
                "local %s=Duel.SelectMatchingCard(tp,%s,tp,%s,%s,%d,%d,%s,e,tp)" % (name, f, s_, o_, n, n, exclude)], name

    def subject(self, what, act):
        """动作的作用对象。返回 (pre, 变量, guard 列表)。"""
        if is_ref(what, "self"):
            guard = ["c:IsRelateToEffect(e)"]
            if act == "special_summon" and "grave" in self.eff["range"]:
                guard.append("aux.NecroValleyFilter()(c)")
            return [], "c", guard
        if is_ref(what, "chain") or is_ref(what, "chain.card"):
            return [], "eg", ["re:GetHandler():IsRelateToEffect(re)"]
        if is_ref(what, "event"):
            return [], "eg", []
        if is_ref(what):
            ref = what["ref"]
            if ref in self.targets:
                guard = ["tc:IsRelateToEffect(e)"]
                if act == "special_summon" and "grave" in self.targets[ref]["where"]:
                    guard.append("aux.NecroValleyFilter()(tc)")
                return [], "tc", guard
            var, _ = self.vars[ref]
            return [], var, []
        name = "g%d" % (len(self.vars) + 1)
        pre, var = self.select(what, act, name)
        self.vars["_" + name] = (var, act)
        if what.get("count") == "all":
            return pre, var, []
        return pre, var, ["#%s>0" % var]

    def step_code(self, step):
        """返回 (pre, guard, call 语句列表, post 语句列表, 成功表达式或 None)。"""
        special = self.special_step(step)
        if special is not None:
            return special
        act = step["act"]
        what = step.get("what")
        if act == "negate_activation":
            return [], [], ["Duel.NegateActivation(ev)"], [], "Duel.NegateActivation(ev)"
        if act == "negate_effect":
            return [], [], ["Duel.NegateEffect(ev)"], [], "Duel.NegateEffect(ev)"
        if act == "negate_attack":
            return [], [], ["Duel.NegateAttack()"], [], "Duel.NegateAttack()"
        if act == "draw":
            p = "tp" if step.get("player", "you") == "you" else "1-tp"
            call = "Duel.Draw(%s,%d,REASON_EFFECT)" % (p, step.get("count", 1))
            return [], [], [call], [], call + ">0"
        if act == "apply_continuous":
            special = self.special_apply(step)
            if special is not None:
                return special
            return self.apply(step)
        if act == "raw":
            if step.get("lua_functions"):
                self.g.add_func("\n".join(step["lua_functions"]))
            return [], [], list(step["lua"]), [], None
        pre, var, guard = self.subject(what, act)
        if step.get("as"):
            self.vars[step["as"]] = (var, act)
        if act == "negate_card_effects":
            # 「对方场上的全部表侧表示怪兽」是一组卡：过滤函数里已经有表侧和能否无效的条件，逐张处理
            group = isinstance(what, dict) and what.get("count") == "all" and not is_ref(what)
            if is_ref(what) and var not in ("c", "tc", "eg") and "," not in var:
                # 前一步的结果（「这个效果特殊召唤的怪兽的效果无效化」）：逐张，只处理表侧表示的
                pre = pre + ["local ng=%s:Filter(Card.IsFaceup,nil)" % var]
                var, group = "ng", True
            one = "tc" if group else var
            reset = "RESET_EVENT+RESETS_STANDARD"
            if step.get("until", "end_of_turn") != "permanent":
                reset += "+" + self.reset_of(step.get("until", "end_of_turn"))
            self.lingering += 2
            a, b = "le%d" % (self.lingering - 1), "le%d" % self.lingering
            call = ["Duel.NegateRelatedChain(%s,RESET_TURN_SET)" % one,
                    "local %s=Effect.CreateEffect(c)" % a, "%s:SetType(EFFECT_TYPE_SINGLE)" % a,
                    "%s:SetCode(EFFECT_DISABLE)" % a, "%s:SetReset(%s)" % (a, reset),
                    "%s:RegisterEffect(%s)" % (one, a),
                    "local %s=Effect.CreateEffect(c)" % b, "%s:SetType(EFFECT_TYPE_SINGLE)" % b,
                    "%s:SetCode(EFFECT_DISABLE_EFFECT)" % b, "%s:SetValue(RESET_TURN_SET)" % b,
                    "%s:SetReset(%s)" % (b, reset),
                    "%s:RegisterEffect(%s)" % (one, b)]
            if group:
                return pre, [], ["for tc in aux.Next(%s) do" % var] + indent(call) + ["end"], [], "#%s>0" % var
            guard = ["%s:IsFaceup()" % var] + guard + ["%s:IsCanBeDisabledByEffect(e)" % var]
            return pre, guard, call, [], "true"
        if act == "destroy":
            expr = "Duel.Destroy(%s,REASON_EFFECT)" % var
        elif act == "banish":
            expr = "Duel.Remove(%s,POS_FACEUP,REASON_EFFECT)" % var
        elif act == "send_to_gy":
            expr = "Duel.SendtoGrave(%s,REASON_EFFECT)" % var
        elif act == "add_to_hand":
            expr = "Duel.SendtoHand(%s,nil,REASON_EFFECT)" % var
        elif act == "special_summon":
            expr = "Duel.SpecialSummon(%s,0,tp,tp,false,false,POS_FACEUP)" % var
        elif act == "set_spell_trap":
            expr = "Duel.SSet(tp,%s)" % var
        elif act == "change_position":
            pos = {"faceup": "POS_FACEUP_ATTACK,POS_FACEUP_ATTACK,POS_FACEUP_DEFENSE,POS_FACEUP_DEFENSE",
                   "facedown": "POS_FACEDOWN_DEFENSE", "attack": "POS_FACEUP_ATTACK",
                   "defense": "POS_FACEUP_DEFENSE"}[step["to"]]
            expr = "Duel.ChangePosition(%s,%s)" % (var, pos)
            if step.get("when_exists"):
                guard = ["#%s>0" % var]
        else:
            raise NotImplementedError("动作 %r 还没有 Lua 写法" % act)
        post = []
        if act == "add_to_hand" and not is_ref(what) and "deck" in what["where"]:
            post.append("Duel.ConfirmCards(1-tp,%s)" % var)
        success = expr + ">0"
        if act in LANDED and var not in ("c", "tc", "eg"):
            success += " and %s:GetFirst():IsLocation(%s)" % (var, LANDED[act])
        elif act in LANDED:
            success += " and %s:IsLocation(%s)" % (var, LANDED[act])
        return pre, guard, [expr], post, success

    # ------------------------------------------------------------ 持续一段时间的效果

    def reset_of(self, until):
        return {"end_of_turn": "RESET_PHASE+PHASE_END", "end_of_next_turn": "RESET_PHASE+PHASE_END,2"}[until]

    def bound_card(self, ref):
        # 引用它的步骤已经嵌套在「那一步做成了」的分支里（见 steps），这里不用再检查位置
        var, act = self.vars[ref]
        if var in ("c", "tc"):
            return [], var, []
        return ["local %s_c=%s:GetFirst()" % (var, var)], "%s_c" % var, []

    def apply(self, step):
        ap = applies(step)[0]
        reset = self.reset_of(step["until"])
        k = self.k
        if "on" in ap:
            return [], [], self.listener(ap, reset), [], None
        cont = ap["cont"]
        if cont == "cannot_activate":
            pre, var, guard = self.bound_card(ap["which"]["same_name_as"]["ref"])
            self.lingering += 1
            le = "le%d" % self.lingering
            rng = "1,0" if ap.get("player", "you") == "you" else "0,1"
            self.g.add_func("function s.aclimit%d(e,re,tp)\n\treturn re:GetHandler():IsCode(e:GetLabel())\nend" % k)
            call = ["local %s=Effect.CreateEffect(c)" % le, "%s:SetType(EFFECT_TYPE_FIELD)" % le,
                    "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % le, "%s:SetCode(EFFECT_CANNOT_ACTIVATE)" % le,
                    "%s:SetTargetRange(%s)" % (le, rng), "%s:SetValue(s.aclimit%d)" % (le, k),
                    "%s:SetLabel(%s:GetCode())" % (le, var), "%s:SetReset(%s)" % (le, reset),
                    "Duel.RegisterEffect(%s,tp)" % le]
            return pre, guard, call, [], None
        if cont == "effects_disabled" and same_original_name_ref(ap):
            pre, var, guard = self.bound_card(same_original_name_ref(ap))
            self.lingering += 2
            a, b = "le%d" % (self.lingering - 1), "le%d" % self.lingering
            self.g.add_func("\n".join([
                "function s.distg%d(e,c)" % k,
                "\tlocal tc=e:GetLabelObject()",
                "\treturn c:IsOriginalCodeRule(tc:GetOriginalCodeRule()) and (c:IsType(TYPE_EFFECT) or c:GetOriginalType()&TYPE_EFFECT~=0)",
                "end",
                "function s.discon%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal tc=e:GetLabelObject()",
                "\treturn re:IsActiveType(TYPE_MONSTER) and re:GetHandler():IsOriginalCodeRule(tc:GetOriginalCodeRule())",
                "end",
                "function s.disop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tDuel.NegateEffect(ev)",
                "end"]))
            call = ["local %s=Effect.CreateEffect(c)" % a, "%s:SetType(EFFECT_TYPE_FIELD)" % a,
                    "%s:SetCode(EFFECT_DISABLE)" % a, "%s:SetTargetRange(LOCATION_MZONE,LOCATION_MZONE)" % a,
                    "%s:SetTarget(s.distg%d)" % (a, k), "%s:SetLabelObject(%s)" % (a, var),
                    "%s:SetReset(%s)" % (a, reset), "Duel.RegisterEffect(%s,tp)" % a,
                    "local %s=Effect.CreateEffect(c)" % b, "%s:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)" % b,
                    "%s:SetCode(EVENT_CHAIN_SOLVING)" % b, "%s:SetCondition(s.discon%d)" % (b, k),
                    "%s:SetOperation(s.disop%d)" % (b, k), "%s:SetLabelObject(%s)" % (b, var),
                    "%s:SetReset(%s)" % (b, reset), "Duel.RegisterEffect(%s,tp)" % b]
            return pre, guard, call, [], None
        raise NotImplementedError("持续效果 %r 还没有 Lua 写法" % cont)

    def listener(self, ap, reset):
        """「每次对方把怪兽特殊召唤，自己抽1张」：连锁处理中发生的要等连锁结束后合并处理（增殖的G 的写法）。"""
        on = ap["on"]
        if on["event"] != "special_summon_success" or on.get("subject") or [s["act"] for s in ap["do"]] != ["draw"]:
            raise NotImplementedError("目前只支持「每次……特殊召唤，抽卡」这一种监听")
        k = self.k
        sp = "1-tp" if on.get("by") == "opp" else "tp"
        n = ap["do"][0].get("count", 1)
        self.g.add_func("\n".join([
            "function s.lfilter%d(c,sp)" % k, "\treturn c:IsSummonPlayer(sp)", "end",
            "function s.lcon%d_1(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\treturn eg:IsExists(s.lfilter%d,1,nil,%s) and not Duel.IsChainSolving()" % (k, sp), "end",
            "function s.lop%d_1(e,tp,eg,ep,ev,re,r,rp)" % k, "\tDuel.Draw(tp,%d,REASON_EFFECT)" % n, "end",
            "function s.lcon%d_2(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\treturn eg:IsExists(s.lfilter%d,1,nil,%s) and Duel.IsChainSolving()" % (k, sp), "end",
            "function s.lop%d_2(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\tDuel.RegisterFlagEffect(tp,id,RESET_CHAIN,0,1)", "end",
            "function s.lcon%d_3(e,tp,eg,ep,ev,re,r,rp)" % k, "\treturn Duel.GetFlagEffect(tp,id)>0", "end",
            "function s.lop%d_3(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\tlocal n=Duel.GetFlagEffect(tp,id)", "\tDuel.ResetFlagEffect(tp,id)",
            "\tDuel.Draw(tp,n*%d,REASON_EFFECT)" % n, "end"]))
        out = []
        for i, (code, delay) in enumerate((("EVENT_SPSUMMON_SUCCESS", True), ("EVENT_SPSUMMON_SUCCESS", False),
                                           ("EVENT_CHAIN_SOLVED", False))):
            self.lingering += 1
            le = "le%d" % self.lingering
            out += ["local %s=Effect.CreateEffect(c)" % le,
                    "%s:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_FIELD)" % le]
            if delay:
                out.append("%s:SetProperty(EFFECT_FLAG_DELAY)" % le)
            out += ["%s:SetCode(%s)" % (le, code), "%s:SetCondition(s.lcon%d_%d)" % (le, k, i + 1),
                    "%s:SetOperation(s.lop%d_%d)" % (le, k, i + 1), "%s:SetReset(%s)" % (le, reset),
                    "Duel.RegisterEffect(%s,tp)" % le]
        return out

    # ------------------------------------------------------------ 永续效果、规则、召唤手续

    def continuous(self):
        special = self.special_continuous()
        if special is not None:
            return special
        eff, v, k = self.eff, self.v, self.k
        ap = applies(eff)[0]
        cont = ap["cont"]
        L = ["--" + eff["label"], "local %s=Effect.CreateEffect(c)" % v]
        rng = "+".join(LOC[w] for w in eff["range"])
        if cont == "cannot_attack" and ap.get("declare"):
            a = ap["affects"]
            s_, o_ = sides(a)
            L += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_CANNOT_ATTACK_ANNOUNCE)" % v,
                  "%s:SetRange(%s)" % (v, rng), "%s:SetTargetRange(%s,%s)" % (v, s_, o_)]
        elif cont == "atk_update":
            val = ap["value"]
            times = linked_count_times(val)
            if times is not None:
                self.g.add_func("function s.atkval%d(e,c)\n\treturn c:GetLinkedGroupCount()*%d\nend" % (k, times))
                value = "s.atkval%d" % k
            else:
                value = str(val)
            L += ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetCode(EFFECT_UPDATE_ATTACK)" % v,
                  "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v, "%s:SetRange(%s)" % (v, rng),
                  "%s:SetValue(%s)" % (v, value)]
        elif cont == "battle_damage_change" and ap.get("value") == {"mul": 2} and ap.get("against") == "opp_monster":
            self.g.add_func("function s.damcon%d(e)\n\treturn e:GetHandler():GetBattleTarget()~=nil\nend" % k)
            L += ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetCode(EFFECT_CHANGE_BATTLE_DAMAGE)" % v,
                  "%s:SetCondition(s.damcon%d)" % (v, k), "%s:SetValue(aux.ChangeBattleDamage(1,DOUBLE_DAMAGE))" % v]
        elif cont == "battle_damage_zero" and ap.get("optional"):
            inv = ap["involving"]
            preds = self.g.preds(inv, var="tc")
            names = limits_of(self.card, eff, scope="name")
            flag = None
            if names:
                flag = self.g.code_offset(self.g.limit_keys[names[0][0]])
            ask = self.g.add_string("是否把战斗伤害变成0？")
            L.insert(2, "%s:SetDescription(%s)" % (v, self.description()))
            cond = ["ep==tp", "tc"] + preds + (["Duel.GetFlagEffect(tp,%s)==0" % flag] if flag else [])
            self.g.add_func("\n".join([
                "function s.rdcon%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal tc=Duel.GetAttacker()",
                "\tif tc:IsControler(1-tp) then tc=Duel.GetAttackTarget() end",
                "\treturn " + " and ".join(cond), "end",
                "function s.rdop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tif Duel.SelectYesNo(tp,aux.Stringid(id,%d)) then" % ask,
                "\t\tDuel.Hint(HINT_CARD,0,id)",
                "\t\tDuel.ChangeBattleDamage(tp,0)"]
                + (["\t\tDuel.RegisterFlagEffect(tp,%s,RESET_PHASE+PHASE_END,0,1)" % flag] if flag else [])
                + ["\tend", "end"]))
            L += ["%s:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)" % v, "%s:SetCode(EVENT_PRE_BATTLE_DAMAGE)" % v,
                  "%s:SetRange(%s)" % (v, rng), "%s:SetCondition(s.rdcon%d)" % (v, k),
                  "%s:SetOperation(s.rdop%d)" % (v, k)]
        else:
            raise NotImplementedError("永续效果 %r 还没有 Lua 写法" % cont)
        L.append("c:RegisterEffect(%s)" % v)
        return L

    def rule(self):
        eff, v, k = self.eff, self.v, self.k
        r = eff["rule"]
        if r == "lasting":
            turns = eff["turns"]
            opp = eff.get("count_on", "opp") == "opp"
            act = next((e for e in self.card["effects"] if e["type"] == "activation"), None)
            if act is None:
                raise ModelError("「发动后继续留在场上」要和这张卡的「魔法·陷阱卡的发动」效果一起用")
            self.g.hooks.setdefault(act["id"], []).extend([
                "local hc=e:GetHandler()",
                "hc:SetTurnCounter(0)",
                "local le=Effect.CreateEffect(hc)",
                "le:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                "le:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)",
                "le:SetCode(EVENT_PHASE+PHASE_END)",
                "le:SetCountLimit(1)",
                "le:SetRange(LOCATION_SZONE)",
                "le:SetCondition(s.lastcon)",
                "le:SetOperation(s.lastop)",
                "le:SetReset(RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END+%s,%d)" % (
                    "RESET_OPPO_TURN" if opp else "RESET_SELF_TURN", turns),
                "hc:RegisterEffect(le)",
                "hc:RegisterFlagEffect(1082946,RESET_PHASE+PHASE_END+%s,0,%d)" % (
                    "RESET_OPPO_TURN" if opp else "RESET_SELF_TURN", turns),
            ])
            self.g.add_func("\n".join([
                "function s.lastcon(e,tp,eg,ep,ev,re,r,rp)",
                "\treturn Duel.GetTurnPlayer()==%s" % ("1-tp" if opp else "tp"), "end",
                "function s.lastop(e,tp,eg,ep,ev,re,r,rp)",
                "\tlocal c=e:GetHandler()",
                "\tlocal ct=c:GetTurnCounter()+1",
                "\tc:SetTurnCounter(ct)",
                "\tif ct==%d then" % turns,
                "\t\tDuel.Destroy(c,REASON_RULE)",
                "\t\tc:ResetFlagEffect(1082946)",
                "\tend", "end"]))
            return ["--留在场上", "local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                    "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                    "%s:SetCode(EFFECT_REMAIN_FIELD)" % v, "c:RegisterEffect(%s)" % v]
        if r == "activate_from_hand":
            pre = []
            exprs = self.cond_exprs(eff["condition"], pre)
            self.g.add_func("function s.handcon%d(e)\n\tlocal tp=e:GetHandlerPlayer()\n%s\treturn %s\nend" % (
                k, "".join("\t%s\n" % p for p in pre), " and ".join(exprs) or "true"))
            code = "EFFECT_TRAP_ACT_IN_HAND" if self.card["card"]["kind"] == "trap" else "EFFECT_QP_ACT_IN_NTPHAND"
            return ["--从手卡发动", "local %s=Effect.CreateEffect(c)" % v,
                    "%s:SetDescription(aux.Stringid(id,%d))" % (v, self.g.add_string("从手卡发动")),
                    "%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetCode(%s)" % (v, code),
                    "%s:SetCondition(s.handcon%d)" % (v, k), "c:RegisterEffect(%s)" % v]
        raise NotImplementedError("规则 %r 还没有 Lua 写法" % r)

    def procedure(self):
        eff, v, k = self.eff, self.v, self.k
        L = ["--" + eff["label"], "local %s=Effect.CreateEffect(c)" % v,
             "%s:SetDescription(%s)" % (v, self.description()),
             "%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(EFFECT_SPSUMMON_PROC)" % v,
             "%s:SetProperty(EFFECT_FLAG_UNCOPYABLE)" % v,
             "%s:SetRange(%s)" % (v, "+".join(LOC[w] for w in eff["range"]))]
        limit = self.count_limit()
        if limit:
            L.append("%s:SetCountLimit(%s)" % (v, limit))
        pre = []
        exprs = self.cond_exprs(eff["condition"], pre)
        if eff["cost"]:
            step = eff["cost"][0]
            if step["act"] != "send_to_gy":
                raise NotImplementedError("召唤手续的代价目前只支持送去墓地")
            what = step["what"]
            preds = self.g.preds(what, ["$c:IsAbleToGraveAsCost()", "Duel.GetMZoneCount(tp,$c)>0"])
            self.g.add_func("function s.sprfilter%d(c,tp)\n\treturn %s\nend" % (k, " and ".join(preds)))
            s_, o_ = sides(what)
            exprs.append("Duel.IsExistingMatchingCard(s.sprfilter%d,tp,%s,%s,1,c,tp)" % (k, s_, o_))
            self.g.add_func("\n".join([
                "function s.sprtg%d(e,tp,eg,ep,ev,re,r,rp,chk,c)" % k,
                "\tlocal g=Duel.GetMatchingGroup(s.sprfilter%d,tp,%s,%s,c,tp)" % (k, s_, o_),
                "\tDuel.Hint(HINT_SELECTMSG,tp,HINTMSG_TOGRAVE)",
                "\tlocal tc=g:SelectUnselect(nil,tp,false,true,1,1)",
                "\tif tc then",
                "\t\te:SetLabelObject(tc)",
                "\t\treturn true",
                "\telse return false end",
                "end",
                "function s.sprop%d(e,tp,eg,ep,ev,re,r,rp,c)" % k,
                "\tDuel.SendtoGrave(e:GetLabelObject(),REASON_SPSUMMON)",
                "end"]))
        else:
            exprs.append("Duel.GetLocationCount(tp,LOCATION_MZONE)>0")
        self.g.add_func("function s.sprcon%d(e,c)\n\tif c==nil then return true end\n\tlocal tp=c:GetControler()\n%s\treturn %s\nend" % (
            k, "".join("\t%s\n" % p for p in pre), "\n\t\tand ".join(exprs)))
        L.append("%s:SetCondition(s.sprcon%d)" % (v, k))
        if eff["cost"]:
            L += ["%s:SetTarget(s.sprtg%d)" % (v, k), "%s:SetOperation(s.sprop%d)" % (v, k)]
        L.append("c:RegisterEffect(%s)" % v)
        return L
