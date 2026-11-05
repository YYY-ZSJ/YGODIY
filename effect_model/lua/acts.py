"""v0.2 新增的处理动作。写法照萌卡官方脚本（同一种处理在官方卡里怎么写，这里就怎么写）。

每个 act_xxx(step) 返回 (pre, guard, call, post, success)，含义同 EffectGen.step_code：
pre 是先执行的语句；guard 是执行前要满足的条件；call 是执行语句；post 是执行后的语句；
success 是「这一步做成了」的表达式（后面的步骤依赖它时用），None 表示不能被依赖。
"""

from ..model import applies, is_ref
from .common import LOC, RACE, ATTRIBUTE, indent, sides

PHASE_CODE = {"draw": "PHASE_DRAW", "standby": "PHASE_STANDBY", "main1": "PHASE_MAIN1", "battle": "PHASE_BATTLE",
              "main2": "PHASE_MAIN2", "end": "PHASE_END"}
SKIP_CODE = {"draw": "EFFECT_SKIP_DP", "standby": "EFFECT_SKIP_SP", "main1": "EFFECT_SKIP_M1",
             "battle": "EFFECT_SKIP_BP", "main2": "EFFECT_SKIP_M2"}
COUNTER_CODE = {"spell": "0x1"}


class ActsMixin:
    """EffectGen 的处理动作部分。用到 EffectGen 的 g、eff、k、vars、targets、steps()、lingering。"""

    # ------------------------------------------------------------ 分派

    def special_step(self, step):
        """v0.2 新增的写法；不是的话返回 None，交给原来的 step_code。"""
        act = step["act"]
        fn = getattr(self, "act_" + act, None)
        if fn:
            return fn(step)
        what = step.get("what") or {}
        if act == "draw" and step.get("player") == "both":
            return self.draw_both(step)
        if act == "banish" and (step.get("by") or step.get("face") == "down"):
            return self.banish_by_player(step)
        if act == "banish" and declared_name(what):
            return self.banish_declared(step)
        if act == "special_summon" and "name" in ((what.get("relation") or {}).get("same") or []):
            return self.ss_same_name(step)
        return None

    def special_feasible(self, step):
        act = step["act"]
        what = step.get("what") or {}
        if act == "return_to_extra" and is_ref(what, "self"):
            return ["e:GetHandler():IsAbleToExtra()"]
        if act == "draw" and step.get("player") == "both":
            n = step.get("count", 1)
            return ["Duel.IsPlayerCanDraw(tp,%d)" % n, "Duel.IsPlayerCanDraw(1-tp,%d)" % n]
        if act == "banish" and step.get("by") == "opp":
            return ["Duel.IsPlayerCanRemove(1-tp)", "s.diffct%d(e,tp)>0" % self.k,
                    "Duel.GetFieldGroup(tp,0,LOCATION_ONFIELD):IsExists(Card.IsAbleToRemove,1,nil,1-tp,POS_FACEDOWN,REASON_RULE)"]
        if act == "banish" and declared_name(what):
            return ["Duel.IsExistingMatchingCard(Card.IsAbleToRemove,tp,%s,%s,1,nil)" % sides(what)]
        if act == "select" and (step.get("for_each") or {}).get("players") == "both":
            f = self.g.filter_fn(what)
            return ["Duel.IsExistingMatchingCard(%s,tp,LOCATION_MZONE,0,1,nil,e,tp)" % f,
                    "Duel.IsExistingMatchingCard(%s,tp,0,LOCATION_MZONE,1,nil,e,tp)" % f]
        if act == "special_summon" and "name" in ((what.get("relation") or {}).get("same") or []):
            n = what.get("count", 2)
            return ["not Duel.IsPlayerAffectedByEffect(tp,59822133)",
                    "Duel.GetMZoneCount(tp,e:GetHandler())>%d" % (n - 1),
                    "s.samename%d(e,tp)" % self.k]
        if act == "attach_xyz_material":
            return ["e:GetHandler():IsType(TYPE_XYZ)"]
        if act == "activate_from_deck":
            return ["Duel.IsExistingMatchingCard(s.actfilter%d,tp,%s,%s,1,nil,tp)" % ((self.k,) + sides(what))]
        if act == "one_of":
            f = self.oneof_filter(step)
            return ["Duel.IsExistingMatchingCard(%s,tp,%s,%s,1,nil,e,tp,true)" % ((f,) + sides(what))]
        if act == "perform_summon" and step.get("method") == "ritual":
            return ["s.ritualcheck%d(e,tp)" % self.k]
        if act == "create_token":
            t = step["token"]
            n = step.get("count", 1)
            out = ["Duel.GetLocationCount(tp,LOCATION_MZONE)>%d" % (n - 1),
                   "Duel.IsPlayerCanSpecialSummonMonster(tp,%s,0,TYPES_TOKEN_MONSTER,%d,%d,%d,%s,%s,%s)" % (
                       token_code(t), t["atk"], t["def"], t["level"], RACE[t["race"]], ATTRIBUTE[t["attribute"]],
                       POS[step.get("position", "attack")])]
            if n > 1:
                out.insert(0, "not Duel.IsPlayerAffectedByEffect(tp,59822133)")
            return out
        if act == "apply_continuous" and applies(step)[0].get("cont") == "skip_phase":
            ap = applies(step)[0]
            return ["not Duel.IsPlayerAffectedByEffect(%s,%s)" % (PLAYER[ap["player"]], SKIP_CODE[ap["phase"]])]
        if act in ("negate_summon", "swap_control", "copy_effect", "toss_coin", "branch", "damage", "win_duel",
                   "schedule_operation", "discard", "apply_continuous"):
            return []
        return None

    def special_opinfo(self, step):
        act = step["act"]
        what = step.get("what") or {}
        if act == "return_to_extra":
            return ["Duel.SetOperationInfo(0,CATEGORY_TOEXTRA,e:GetHandler(),1,0,0)"]
        if act == "negate_summon":
            return ["Duel.SetOperationInfo(0,CATEGORY_DISABLE_SUMMON,eg,#eg,0,0)"]
        if act == "destroy" and is_ref(what, "event"):
            return ["Duel.SetOperationInfo(0,CATEGORY_DESTROY,eg,#eg,0,0)"]
        if act == "draw" and step.get("player") == "both":
            return ["Duel.SetOperationInfo(0,CATEGORY_DRAW,nil,0,PLAYER_ALL,%d)" % step.get("count", 1)]
        if act == "discard":
            who = "PLAYER_ALL" if (step.get("for_each") or {}).get("players_of") else "tp"
            return ["Duel.SetOperationInfo(0,CATEGORY_HANDES,nil,0,%s,%d)" % (who, what.get("count", 1))]
        if act == "banish" and step.get("by") == "opp":
            return ["Duel.SetOperationInfo(0,CATEGORY_REMOVE,nil,s.diffct%d(e,tp),1-tp,LOCATION_ONFIELD)" % self.k]
        if act == "banish" and declared_name(what):
            return ["Duel.SetOperationInfo(0,CATEGORY_REMOVE,nil,1,tp,%s)" % "+".join(LOC[w] for w in what["where"])]
        if act == "select" or act == "swap_control":
            return ["Duel.SetOperationInfo(0,CATEGORY_CONTROL,nil,0,0,0)"] if act == "swap_control" else []
        if act == "special_summon" and "name" in ((what.get("relation") or {}).get("same") or []):
            return ["Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,%d,tp,%s)" % (
                what.get("count", 2), "+".join(LOC[w] for w in what["where"]))]
        if act == "create_token":
            n = step.get("count", 1)
            return ["Duel.SetOperationInfo(0,CATEGORY_TOKEN,nil,%d,0,0)" % n,
                    "Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,%d,0,0)" % n]
        if act == "perform_summon":
            return ["Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,%s)" % "+".join(
                LOC[w] for w in step["monster"]["where"])]
        if act == "toss_coin":
            return ["Duel.SetOperationInfo(0,CATEGORY_COIN,nil,0,tp,%d)" % step.get("count", 1)]
        if act in ("attach_xyz_material", "activate_from_deck", "one_of", "copy_effect", "branch", "damage",
                   "win_duel", "schedule_operation", "apply_continuous"):
            return []
        return None

    # ------------------------------------------------------------ 移动卡片

    def act_return_to_extra(self, step):
        if not is_ref(step["what"], "self"):
            raise NotImplementedError("回到额外卡组目前只支持这张卡")
        expr = "Duel.SendtoDeck(c,nil,SEQ_DECKSHUFFLE,REASON_EFFECT)"
        return [], ["c:IsRelateToEffect(e)"], [expr], [], expr + "~=0 and c:IsLocation(LOCATION_EXTRA)"

    def draw_both(self, step):
        n = step.get("count", 1)
        call = ["local d1=Duel.Draw(tp,%d,REASON_EFFECT)" % n, "local d2=Duel.Draw(1-tp,%d,REASON_EFFECT)" % n]
        if step.get("as"):
            self.vars[step["as"]] = ("d1,d2", "draw_both")
        return call, [], [], [], "d1+d2>0"

    def act_discard(self, step):
        players = (step.get("for_each") or {}).get("players_of")
        what = step["what"]
        n = what.get("count", 1)
        if not players and what.get("who") == "you" and not what.get("filter"):
            # 「选2张手卡丢弃」（天使的施舍）：抽卡后先洗切手卡
            expr = "Duel.DiscardHand(tp,nil,%d,%d,REASON_EFFECT+REASON_DISCARD)" % (n, n)
            return ["Duel.ShuffleHand(tp)"], [], [expr], [], expr + ">0"
        if not players or self.vars.get(players["ref"], (None, None))[1] != "draw_both":
            raise NotImplementedError("丢弃目前只支持「自己选N张手卡丢弃」「抽卡的玩家各自丢弃」")
        call = []
        for var, p in (("d1", "tp"), ("d2", "1-tp")):
            call += ["if %s>0 then" % var, "\tDuel.ShuffleHand(%s)" % p,
                     "\tDuel.DiscardHand(%s,aux.TRUE,%d,%d,REASON_EFFECT+REASON_DISCARD)" % (p, n, n), "end"]
        return [], [], call, [], None

    def banish_by_player(self, step):
        """「直到变成和自己场上的卡数量相同为止，对方必须把自身场上的卡里侧除外」：玩家的行为，卡的抗性不挡。"""
        k = self.k
        self.g.add_func("\n".join([
            "function s.diffct%d(e,tp)" % k,
            "\tlocal ct=Duel.GetFieldGroupCount(tp,0,LOCATION_ONFIELD)-Duel.GetFieldGroupCount(tp,LOCATION_ONFIELD,0)",
            "\tif e:GetHandler():IsLocation(LOCATION_HAND) then ct=ct-1 end",
            "\treturn ct", "end"]))
        call = ["if not Duel.IsPlayerCanRemove(1-tp) then return end",
                "local rg=Duel.GetFieldGroup(tp,0,LOCATION_ONFIELD)",
                "local ct=rg:GetCount()-Duel.GetFieldGroupCount(tp,LOCATION_ONFIELD,0)",
                "if ct>0 then",
                "\tDuel.Hint(HINT_SELECTMSG,1-tp,HINTMSG_REMOVE)",
                "\tlocal sg=rg:FilterSelect(1-tp,Card.IsAbleToRemove,ct,ct,nil,1-tp,POS_FACEDOWN,REASON_RULE)",
                "\tDuel.Remove(sg,POS_FACEDOWN,REASON_RULE,1-tp)",
                "end"]
        return [], [], call, [], None

    def banish_declared(self, step):
        """「宣言的1张卡从卡组除外」：宣言的卡名在发动时用 SetTargetParam 存下。"""
        what = step["what"]
        k = self.k
        self.g.add_func("function s.declfilter%d(c,code)\n\treturn c:IsAbleToRemove() and c:IsCode(code)\nend" % k)
        s_, o_ = sides(what)
        pre = ["local ac=Duel.GetChainInfo(0,CHAININFO_TARGET_PARAM)",
               "Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_REMOVE)",
               "local xg=Duel.SelectMatchingCard(tp,s.declfilter%d,tp,%s,%s,1,1,nil,ac)" % (k, s_, o_)]
        if step.get("as"):
            self.vars[step["as"]] = ("xg", "banish")
        expr = "Duel.Remove(xg,POS_FACEUP,REASON_EFFECT)"
        return pre, ["#xg>0"], [expr], [], expr + "~=0 and xg:GetFirst():IsLocation(LOCATION_REMOVED)"

    def ss_same_name(self, step):
        """「从卡组把2只4星以下的同名通常怪兽特殊召唤」。"""
        what = step["what"]
        k = self.k
        f = self.g.filter_fn(what, ["$c:IsCanBeSpecialSummoned(e,0,tp,false,false)"])
        s_, o_ = sides(what)
        self.g.add_func("\n".join([
            "function s.samefilter%d(c,g)" % k, "\treturn g:IsExists(Card.IsCode,1,c,c:GetCode())", "end",
            "function s.samename%d(e,tp)" % k,
            "\tlocal g=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (f, s_, o_),
            "\treturn g:IsExists(s.samefilter%d,1,nil,g)" % k, "end"]))
        n = what.get("count", 2)
        pre = ["if Duel.IsPlayerAffectedByEffect(tp,59822133) or Duel.GetLocationCount(tp,LOCATION_MZONE)<%d then return end" % n,
               "local mg=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (f, s_, o_),
               "local dg=mg:Filter(s.samefilter%d,nil,mg)" % k,
               "if #dg==0 then return end",
               "Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)",
               "local sg=dg:Select(tp,1,1,nil)",
               "local tc1=sg:GetFirst()",
               "dg:RemoveCard(tc1)",
               "sg:Merge(dg:Filter(Card.IsCode,nil,tc1:GetCode()):Select(tp,%d,%d,nil))" % (n - 1, n - 1),
               "local ssn=Duel.SpecialSummon(sg,0,tp,tp,false,false,POS_FACEUP)"]
        if step.get("as"):
            self.vars[step["as"]] = ("sg", "special_summon")
        return pre, [], [], [], "ssn>0"

    # ------------------------------------------------------------ 无效、控制权

    def act_negate_summon(self, step):
        # NegateSummon 没有返回值：放在前面执行，后面的「那些怪兽破坏」照常接上
        return ["Duel.NegateSummon(eg)"], [], [], [], "true"

    def act_select(self, step):
        """「双方玩家各自选自身场上1只怪兽」。"""
        if (step.get("for_each") or {}).get("players") != "both":
            raise NotImplementedError("选卡目前只支持「双方各自选」")
        f = self.g.filter_fn(step["what"])
        pre = ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_CONTROL)",
               "local g1=Duel.SelectMatchingCard(tp,%s,tp,LOCATION_MZONE,0,1,1,nil,e,tp)" % f,
               "Duel.HintSelection(g1)",
               "Duel.Hint(HINT_SELECTMSG,1-tp,HINTMSG_CONTROL)",
               "local g2=Duel.SelectMatchingCard(1-tp,%s,1-tp,LOCATION_MZONE,0,1,1,nil,e,tp)" % f,
               "Duel.HintSelection(g2)",
               "local c1=g1:GetFirst()", "local c2=g2:GetFirst()"]
        if step.get("as"):
            self.vars[step["as"]] = ("c1,c2", "select")
        return pre, [], [], [], "c1 and c2"

    def act_swap_control(self, step):
        cards = self.vars[step["what"]["ref"]][0]
        expr = "Duel.SwapControl(%s,0,0)" % cards
        if step.get("as"):
            self.vars[step["as"]] = (cards, "swap")
        return [], [], [expr], [], expr

    def act_copy_effect(self, step):
        """「这张卡直到结束阶段得到和那只怪兽的原本的卡名·效果相同的卡名·效果」：卡名在支付代价时存进 label。"""
        k = self.k
        self.g.add_func("\n".join([
            "function s.rstop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\tlocal c=e:GetHandler()",
            "\tc:ResetEffect(e:GetLabel(),RESET_COPY)",
            "\tc:ResetEffect(RESET_DISABLE,RESET_EVENT)",
            "\te:GetLabelObject():Reset()",
            "end"]))
        reset = "RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END"
        call = ["local code=e:GetLabel()"]
        if "name" in step["fields"]:
            call += ["local ce=Effect.CreateEffect(c)", "ce:SetType(EFFECT_TYPE_SINGLE)",
                     "ce:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)", "ce:SetReset(%s)" % reset,
                     "ce:SetCode(EFFECT_CHANGE_CODE)", "ce:SetValue(code)", "c:RegisterEffect(ce)"]
        call += ["local cid=c:CopyEffect(code,%s,1)" % reset,
                 "local re2=Effect.CreateEffect(c)",
                 "re2:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                 "re2:SetCode(EVENT_PHASE+PHASE_END)",
                 "re2:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)",
                 "re2:SetCountLimit(1)", "re2:SetRange(LOCATION_MZONE)", "re2:SetReset(%s)" % reset,
                 "re2:SetLabelObject(ce)" if "name" in step["fields"] else "re2:SetLabelObject(re2)",
                 "re2:SetLabel(cid)", "re2:SetOperation(s.rstop%d)" % k, "c:RegisterEffect(re2)"]
        return [], ["c:IsRelateToEffect(e)", "c:IsFaceup()"], call, [], None

    def act_attach_xyz_material(self, step):
        what = step["what"]
        if not (is_ref(step.get("to"), "self") and is_ref(what) and what["ref"] in self.targets):
            raise NotImplementedError("放入超量素材目前只支持「对象作为这张卡的超量素材」")
        call = ["local og=tc:GetOverlayGroup()", "if #og>0 then Duel.SendtoGrave(og,REASON_RULE) end",
                "Duel.Overlay(c,Group.FromCards(tc))"]
        return [], ["c:IsRelateToEffect(e)", "tc:IsRelateToEffect(e)", "not tc:IsImmuneToEffect(e)"], call, [], None

    # ------------------------------------------------------------ 从卡组发动、二选一、仪式、衍生物

    def act_activate_from_deck(self, step):
        """「从卡组选1张「北极天熊北斗星」发动」：场地魔法放到场地区域并当作发动。"""
        what = step["what"]
        k = self.k
        preds = self.g.preds(what, ["$c:GetActivateEffect() and $c:GetActivateEffect():IsActivatable(tp,true,true)"])
        self.g.add_func("function s.actfilter%d(c,tp)\n\treturn %s\nend" % (k, " and ".join(preds)))
        s_, o_ = sides(what)
        call = ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_OPERATECARD)",
                "local ag=Duel.SelectMatchingCard(tp,s.actfilter%d,tp,%s,%s,1,1,nil,tp)" % (k, s_, o_),
                "local ac=ag:GetFirst()",
                "if ac then",
                "\tlocal te=ac:GetActivateEffect()",
                "\tif ac:IsType(TYPE_FIELD) then",
                "\t\tlocal fc=Duel.GetFieldCard(tp,LOCATION_FZONE,0)",
                "\t\tif fc then",
                "\t\t\tDuel.SendtoGrave(fc,REASON_RULE)",
                "\t\t\tDuel.BreakEffect()",
                "\t\tend",
                "\t\tDuel.MoveToField(ac,tp,tp,LOCATION_FZONE,POS_FACEUP,true)",
                "\telse",
                "\t\tDuel.MoveToField(ac,tp,tp,LOCATION_SZONE,POS_FACEUP,true)",
                "\tend",
                "\tte:UseCountLimit(tp,1,true)",
                "\tlocal cost=te:GetCost()",
                "\tif cost then cost(te,tp,eg,ep,ev,re,r,rp,1) end",
                "\tDuel.RaiseEvent(ac,4179255,te,0,tp,tp,Duel.GetCurrentChain())",
                "end"]
        return [], [], call, [], None

    def oneof_filter(self, step):
        """「加入手卡或特殊召唤」的过滤：能做其中一种就行（check 为假时只看能否加入手卡）。"""
        what = step["what"]
        name = "s.oneof%d" % self.k
        if name not in self.g.filter_names.values():
            preds = self.g.preds(what)
            self.g.filter_names["oneof%d" % self.k] = name
            self.g.add_func("function %s(c,e,tp,check)\n\treturn %s(c:IsAbleToHand() or check and c:IsCanBeSpecialSummoned(e,0,tp,false,false))\nend" % (
                name, "".join(p + " and " for p in preds)))
        return name

    def act_one_of(self, step):
        what = step["what"]
        if sorted(step["acts"]) != ["add_to_hand", "special_summon"]:
            raise NotImplementedError("二选一目前只支持「加入手卡或特殊召唤」")
        f = self.oneof_filter(step)
        if "grave" in what["where"]:
            f = "aux.NecroValleyFilter(%s)" % f
        s_, o_ = sides(what)
        call = ["local check=Duel.GetLocationCount(tp,LOCATION_MZONE)>0",
                "Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_OPERATECARD)",
                "local og=Duel.SelectMatchingCard(tp,%s,tp,%s,%s,1,1,nil,e,tp,check)" % (f, s_, o_),
                "local oc=og:GetFirst()",
                "if oc then",
                "\tif oc:IsAbleToHand() and (not oc:IsCanBeSpecialSummoned(e,0,tp,false,false) or not check",
                "\t\tor Duel.SelectOption(tp,1190,1152)==0) then",
                "\t\tDuel.SendtoHand(oc,nil,REASON_EFFECT)",
                "\t\tDuel.ConfirmCards(1-tp,oc)",
                "\telse",
                "\t\tDuel.SpecialSummon(oc,0,tp,tp,false,false,POS_FACEUP)",
                "\tend",
                "end"]
        return [], [], call, [], None

    def act_perform_summon(self, step):
        """仪式召唤：等级合计和仪式怪兽相同（「高等仪式术」的写法）。"""
        if step.get("method") != "ritual" or step["value"].get("op") != "==":
            raise NotImplementedError("进行召唤目前只支持「等级合计相同的仪式召唤」")
        k = self.k
        mat, mon = step["materials"], step["monster"]
        mpreds = self.g.preds(mat, ["$c:IsAbleToGrave()"] if mat.get("destination") == "grave" else [])
        self.g.add_func("\n".join([
            "function s.ritmat%d(c)" % k, "\treturn %s" % " and ".join(mpreds), "end",
            "function s.ritfilter%d(c,e,tp,m)" % k,
            "\tif bit.band(c:GetType(),0x81)~=0x81",
            "\t\tor not c:IsCanBeSpecialSummoned(e,SUMMON_TYPE_RITUAL,tp,false,true) then return false end",
            "\tif c.mat_filter then",
            "\t\tm=m:Filter(c.mat_filter,nil,tp)",
            "\tend",
            "\treturn m:CheckWithSumEqual(Card.GetRitualLevel,c:GetLevel(),1,99,c)",
            "end",
            "function s.ritualcheck%d(e,tp)" % k,
            "\tif Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return false end",
            "\tlocal mg=Duel.GetMatchingGroup(s.ritmat%d,tp,%s,%s,nil)" % ((k,) + sides(mat)),
            "\treturn Duel.IsExistingMatchingCard(s.ritfilter%d,tp,%s,%s,1,nil,e,tp,mg)" % ((k,) + sides(mon)),
            "end"]))
        call = ["if Duel.GetLocationCount(tp,LOCATION_MZONE)<=0 then return end",
                "::cancel::",
                "local mg=Duel.GetMatchingGroup(s.ritmat%d,tp,%s,%s,nil)" % ((k,) + sides(mat)),
                "Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)",
                "local tg=Duel.SelectMatchingCard(tp,s.ritfilter%d,tp,%s,%s,1,1,nil,e,tp,mg)" % ((k,) + sides(mon)),
                "if tg:GetCount()>0 then",
                "\tlocal rc=tg:GetFirst()",
                "\tif rc.mat_filter then",
                "\t\tmg=mg:Filter(rc.mat_filter,nil,tp)",
                "\tend",
                "\tlocal lv=rc:GetLevel()",
                "\tDuel.Hint(HINT_SELECTMSG,tp,HINTMSG_TOGRAVE)",
                "\taux.GCheckAdditional=function(sg) return sg:GetSum(Card.GetRitualLevel,rc)<=lv end",
                "\tlocal mat=mg:SelectSubGroup(tp,aux.RitualCheckEqual,true,1,99,rc,lv)",
                "\taux.GCheckAdditional=nil",
                "\tif not mat then goto cancel end",
                "\trc:SetMaterial(mat)",
                "\tDuel.SendtoGrave(mat,REASON_EFFECT+REASON_MATERIAL+REASON_RITUAL)",
                "\tDuel.BreakEffect()",
                "\tDuel.SpecialSummon(rc,SUMMON_TYPE_RITUAL,tp,tp,false,true,POS_FACEUP)",
                "\trc:CompleteProcedure()",
                "end"]
        return [], [], call, [], None

    def act_create_token(self, step):
        t = step["token"]
        n = step.get("count", 1)
        pos = POS[step.get("position", "attack")]
        check = "Duel.GetLocationCount(tp,LOCATION_MZONE)>%d and Duel.IsPlayerCanSpecialSummonMonster(tp,%s,0,TYPES_TOKEN_MONSTER,%d,%d,%d,%s,%s,%s)" % (
            n - 1, token_code(t), t["atk"], t["def"], t["level"], RACE[t["race"]], ATTRIBUTE[t["attribute"]], pos)
        if n > 1:
            check = "not Duel.IsPlayerAffectedByEffect(tp,59822133) and " + check
        # 生成衍生物的语句放在前面：后面「这衍生物不能……」依赖它时，只用 #tg>0 判断做成了没有
        pre = ["if not (%s) then return end" % check,
               "local tg=Group.CreateGroup()",
               "for i=1,%d do" % n,
               "\tlocal token=Duel.CreateToken(tp,%s)" % token_code(t),
               "\tDuel.SpecialSummonStep(token,0,tp,tp,false,false,%s)" % pos,
               "\ttg:AddCard(token)",
               "end",
               "Duel.SpecialSummonComplete()"]
        if step.get("as"):
            self.vars[step["as"]] = ("tg", "create_token")
        return pre, [], [], [], "#tg>0"

    # ------------------------------------------------------------ 预约、胜利、随机、伤害、指示物

    def act_win_duel(self, step):
        return [], [], ["Duel.Win(%s,0x11)" % PLAYER[step.get("player", "you")]], [], None

    def act_toss_coin(self, step):
        n = step.get("count", 1)
        pre = []
        if step.get("call"):
            pre = ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_COIN)", "local coin=Duel.AnnounceCoin(tp)"]
        if step.get("as"):
            self.vars[step["as"]] = ("res", "coin")
        return pre + ["local res=Duel.TossCoin(tp,%d)" % n], [], [], [], None

    def act_branch(self, step):
        cases = step["cases"]
        out = []
        for i, case in enumerate(cases):
            c = case["if"]
            if c.get("cond") != "die_coin_result":
                raise NotImplementedError("分支目前只支持投硬币的结果")
            cond = "coin~=res" if c.get("called_right") else "coin==res"     # 萌卡脚本：AnnounceCoin 与 TossCoin 不相等为猜中
            head = "if %s then" % cond if i == 0 else ("else" if i == len(cases) - 1 else "elseif %s then" % cond)
            out.append(head)
            out += indent(self.steps(case["do"], 0))
        out.append("end")
        return [], [], out, [], None

    def act_damage(self, step):
        player = PLAYER[step.get("player", "you")]
        amount = step["amount"]
        if isinstance(amount, int):
            expr = "Duel.Damage(%s,%d,REASON_EFFECT)" % (player, amount)
            return [], [], [expr], [], expr + ">0"
        half = amount.get("half") or {}
        if half.get("sum") == "atk" and is_ref(half.get("of")):
            face = {"previous": {"face": "up"}} in half["of"].get("filter", [])
            pre = ["local og=Duel.GetOperatedGroup()%s" % (":Filter(Card.IsPreviousPosition,nil,POS_FACEUP)" if face else ""),
                   "local sum=0",
                   "for oc in aux.Next(og) do sum=sum+math.max(oc:GetPreviousAttackOnField(),0) end"]
            return pre, ["sum>0"], ["Duel.Damage(%s,math.floor(sum/2),REASON_EFFECT)" % player], [], None
        raise NotImplementedError("伤害数值 %r 还没有 Lua 写法" % amount)

    def act_add_counter(self, step):
        if not is_ref(step.get("what"), "self"):
            raise NotImplementedError("放置指示物目前只支持这张卡")
        return [], [], ["e:GetHandler():AddCounter(%s,%d)" % (COUNTER_CODE[step["counter"]], step.get("count", 1))], [], None

    def act_schedule_operation(self, step):
        at = step["at"]
        k = self.k
        if "turn" in at:            # 「以发动的回合为第1回合来计算的第20回合的回合结束时……」
            n = at["turn"]
            body = self.scheduled_body(step["do"], None)
            self.g.add_func("\n".join([
                "function s.schop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal ct=e:GetLabel()+1",
                "\te:SetLabel(ct)",
                "\te:GetHandler():SetTurnCounter(ct)",
                "\tif ct==%d then" % n] + indent(body, 2) + ["\tend", "end"]))
            call = ["local se=Effect.CreateEffect(c)", "se:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                    "se:SetCode(EVENT_PHASE+PHASE_END)", "se:SetCountLimit(1)", "se:SetLabel(0)",
                    "se:SetOperation(s.schop%d)" % k, "se:SetReset(RESET_PHASE+PHASE_END,%d)" % n,
                    "Duel.RegisterEffect(se,tp)"]
            return [], [], call, [], None
        ref = self.scheduled_ref(step["do"])
        var = self.vars[ref][0] if ref else None
        if at.get("nth"):           # 「这张卡的发动后第2次的自己准备阶段，这个效果除外的卡加入手卡」
            n, phase = at["nth"], PHASE_CODE[at["phase"]]
            mine = at.get("player", "you") == "you"
            body = self.scheduled_body(step["do"], "tc")
            self.g.add_func("\n".join([
                "function s.schcon%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal fid=e:GetLabel()",
                "\treturn Duel.GetTurnPlayer()==%s and e:GetLabelObject():GetFlagEffectLabel(id)==fid" % ("tp" if mine else "1-tp"),
                "end",
                "function s.schop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal fid,ct=e:GetLabel()",
                "\tlocal tc=e:GetLabelObject()",
                "\tct=ct+1",
                "\te:GetHandler():SetTurnCounter(ct)",
                "\te:SetLabel(fid,ct)",
                "\tif ct~=%d then return end" % n,
                "\tif tc:GetFlagEffectLabel(id)==fid then"] + indent(body, 2) + ["\tend", "end"]))
            reset = "RESET_PHASE+%s+%s" % (phase, "RESET_SELF_TURN" if mine else "RESET_OPPO_TURN")
            call = ["local sc=%s:GetFirst()" % var if "," not in var and var not in ("c", "tc") else "local sc=%s" % var,
                    "local fid=c:GetFieldID()",
                    "sc:RegisterFlagEffect(id,RESET_EVENT+RESETS_STANDARD+%s,0,%d,fid)" % (reset, n),
                    "local se=Effect.CreateEffect(c)", "se:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                    "se:SetCode(EVENT_PHASE+%s)" % phase, "se:SetCountLimit(1)", "se:SetReset(%s,%d)" % (reset, n),
                    "se:SetLabel(fid,0)", "se:SetLabelObject(sc)",
                    "se:SetCondition(s.schcon%d)" % k, "se:SetOperation(s.schop%d)" % k, "Duel.RegisterEffect(se,tp)"]
            return [], [], call, [], None
        if at.get("which") == "this_turn":     # 「这个效果特殊召唤的怪兽在结束阶段破坏」
            phase = PHASE_CODE[at["phase"]]
            body = self.scheduled_body(step["do"], "tg")
            pre = []
            if var in ("c", "tc"):            # 单张卡（「这张卡特殊召唤。……在结束阶段除外」）：先放进一组
                pre, var = ["local sg=Group.FromCards(%s)" % var], "sg"
            self.g.add_func("\n".join([
                "function s.schfilter%d(c,fid)" % k, "\treturn c:GetFlagEffectLabel(id)==fid", "end",
                "function s.schcon%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal g=e:GetLabelObject()",
                "\tif not g:IsExists(s.schfilter%d,1,nil,e:GetLabel()) then" % k,
                "\t\tg:DeleteGroup()", "\t\te:Reset()", "\t\treturn false",
                "\tend",
                "\treturn true", "end",
                "function s.schop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
                "\tlocal tg=e:GetLabelObject():Filter(s.schfilter%d,nil,e:GetLabel())" % k] + indent(body, 1) + ["end"]))
            call = ["local fid=c:GetFieldID()",
                    "for sc in aux.Next(%s) do sc:RegisterFlagEffect(id,RESET_EVENT+RESETS_STANDARD,0,1,fid) end" % var,
                    "%s:KeepAlive()" % var,
                    "local se=Effect.CreateEffect(c)", "se:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                    "se:SetProperty(EFFECT_FLAG_IGNORE_IMMUNE)", "se:SetCode(EVENT_PHASE+%s)" % phase,
                    "se:SetCountLimit(1)", "se:SetLabel(fid)", "se:SetLabelObject(%s)" % var,
                    "se:SetCondition(s.schcon%d)" % k, "se:SetOperation(s.schop%d)" % k, "Duel.RegisterEffect(se,tp)"]
            return pre, [], call, [], None
        raise NotImplementedError("预约 %r 还没有 Lua 写法" % at)

    def scheduled_ref(self, steps):
        for s in steps:
            if is_ref(s.get("what")):
                return s["what"]["ref"]
        return None

    def scheduled_body(self, steps, var):
        """预约到期时执行的处理；引用的卡在 var 里（单张 tc 或一组 tg）。"""
        out = []
        for s in steps:
            act = s["act"]
            if act == "win_duel":
                out.append("Duel.Win(%s,0x11)" % PLAYER[s.get("player", "you")])
            elif act == "add_to_hand" and var:
                out += ["Duel.SendtoHand(%s,nil,REASON_EFFECT)" % var, "Duel.ConfirmCards(1-tp,%s)" % var]
            elif act == "destroy" and var:
                out.append("Duel.Destroy(%s,REASON_EFFECT)" % var)
            elif act == "banish" and var:
                out.append("Duel.Remove(%s,POS_FACEUP,REASON_EFFECT)" % var)
            else:
                raise NotImplementedError("预约的处理 %r 还没有 Lua 写法" % act)
        return out

    # ------------------------------------------------------------ 持续一段时间的效果（v0.2 新增的种类）

    def special_apply(self, step):
        ap = applies(step)[0]
        cont = ap.get("cont")
        until = step.get("until")
        from .cont import NEW_SIMPLE, SIMPLE
        aps = applies(step)
        if all(a.get("cont") in NEW_SIMPLE or (len(aps) > 1 and a.get("cont") == "atk_update") for a in aps):
            return self.apply_simple(aps, until)
        if cont == "atk_update":
            return self.apply_atk_update(ap, until)
        if cont == "cannot_change_position":
            ref = ap["affects"]["ref"]
            if "," in self.vars.get(ref, ("",))[0]:     # 「那2只怪兽」（强制转移）：照官方只到回合结束
                call = []
                for i, cv in enumerate(self.vars[ref][0].split(",")):
                    le = "pe%d" % (i + 1)
                    call += ["local %s=Effect.CreateEffect(c)" % le, "%s:SetType(EFFECT_TYPE_SINGLE)" % le,
                             "%s:SetCode(EFFECT_CANNOT_CHANGE_POSITION)" % le, "%s:SetReset(RESET_PHASE+PHASE_END)" % le,
                             "%s:RegisterEffect(%s)" % (cv, le)]
                return [], [], call, [], None
            guard, call = self.each_card(ref, lambda cv: [
                "local pe1=Effect.CreateEffect(c)", "pe1:SetType(EFFECT_TYPE_SINGLE)",
                "pe1:SetCode(EFFECT_CANNOT_CHANGE_POSITION)", "pe1:SetReset(RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END)",
                "%s:RegisterEffect(pe1)" % cv])
            return [], guard, call, [], None
        if cont == "skip_phase":
            player = ap["player"]
            code = SKIP_CODE[ap["phase"]]
            phase = PHASE_CODE[ap["phase"]]
            rng = "0,1" if player == "opp" else "1,0"
            turn = "RESET_OPPO_TURN" if player == "opp" else "RESET_SELF_TURN"
            who = "1-tp" if player == "opp" else "tp"
            call = ["local se=Effect.CreateEffect(c)", "se:SetType(EFFECT_TYPE_FIELD)",
                    "se:SetProperty(EFFECT_FLAG_PLAYER_TARGET)", "se:SetTargetRange(%s)" % rng, "se:SetCode(%s)" % code,
                    "if Duel.GetTurnPlayer()==%s and Duel.GetCurrentPhase()==%s then" % (who, phase),
                    "\tse:SetReset(RESET_PHASE+%s+%s,2)" % (phase, turn),
                    "else",
                    "\tse:SetReset(RESET_PHASE+%s+%s)" % (phase, turn),
                    "end",
                    "Duel.RegisterEffect(se,tp)"]
            return [], [], call, [], None
        if cont == "cannot_release" and ap.get("for") == ["tribute_summon"]:
            var = self.vars[ap["affects"]["ref"]][0]
            call = ["for rc in aux.Next(%s) do" % var,
                    "\tlocal re1=Effect.CreateEffect(c)", "\tre1:SetType(EFFECT_TYPE_SINGLE)",
                    "\tre1:SetCode(EFFECT_UNRELEASABLE_SUM)", "\tre1:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)",
                    "\tre1:SetValue(1)", "\tre1:SetReset(RESET_EVENT+RESETS_STANDARD)", "\trc:RegisterEffect(re1,true)",
                    "end"]
            return [], [], call, [], None
        if cont == "effects_disabled" and not _monsters_only(ap):     # 只限怪兽的（墓穴的指名者）走原来的写法
            return self.apply_negate_same_name(ap, until)
        # 处理的「后果」：作用在前一步的卡上（写法照沉默的死者、迷你番茄小子、再爆裂、妖魔 涂壁的官方脚本）
        aff = ap.get("affects") or {}
        if is_ref(aff) and cont in ("cannot_attack", "cannot_use_material", "cannot_release", "redirect_destination"):
            reset = "RESET_EVENT+RESETS_STANDARD" + ("+RESET_PHASE+PHASE_END" if until == "end_of_turn" else "")
            if cont == "redirect_destination":
                if (ap.get("from_dest"), ap.get("to_dest")) != ("leave_field", "banished"):
                    raise NotImplementedError("去向替代目前只支持「从场上离开的场合除外」")
                codes, value, reset = ["EFFECT_LEAVE_FIELD_REDIRECT"], "LOCATION_REMOVED", "RESET_EVENT+RESETS_REDIRECT"
            elif cont == "cannot_attack":
                codes, value = ["EFFECT_CANNOT_ATTACK"], None
            elif cont == "cannot_use_material":
                codes, value = ["EFFECT_CANNOT_BE_%s_MATERIAL" % ap["method"].upper()], "1"
            else:
                codes, value = ["EFFECT_UNRELEASABLE_SUM", "EFFECT_UNRELEASABLE_NONSUM"], "1"

            def lines(card):
                out = []
                for i, code in enumerate(codes):
                    v = "ce%d" % (i + 1)
                    out += ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                            "%s:SetCode(%s)" % (v, code)]
                    if value:
                        out.append("%s:SetValue(%s)" % (v, value))
                    out += ["%s:SetReset(%s)" % (v, reset), "%s:RegisterEffect(%s,true)" % (card, v)]
                return out
            guard, call = self.each_card(aff["ref"], lines)
            return [], guard, call, [], None
        return None

    def apply_simple(self, aps, until):
        """处理中给一张卡加上永续第一批的效果，到回合结束（「这个回合，那只怪兽不会被战斗·效果破坏」）。"""
        from .cont import SIMPLE
        aff = aps[0].get("affects") or {"ref": "self"}
        if not all((a.get("affects") or {"ref": "self"}) == aff for a in aps) or not is_ref(aff):
            raise NotImplementedError("处理中的这种持续适用还没有 Lua 写法")
        reset = "RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END" if until == "end_of_turn" else "RESET_EVENT+RESETS_STANDARD"

        def lines(target):
            call = []
            for i, ap in enumerate(aps):
                code, value, _ = SIMPLE[ap["cont"]]
                value = value(ap) if callable(value) else value
                code = code(ap) if callable(code) else code
                v = "ce%d" % (i + 1)
                call += ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                         "%s:SetCode(%s)" % (v, code)]
                if value is not None:
                    call.append("%s:SetValue(%s)" % (v, value))
                call += ["%s:SetReset(%s)" % (v, reset), "%s:RegisterEffect(%s)" % (target, v)]
            return call
        guard, call = self.each_card(aff["ref"], lines)
        return [], guard, call, [], None

    def each_card(self, ref, lines_for):
        """引用的卡逐张做 lines_for(卡的变量)，返回 (guard, 语句)。这张卡、对象是单张；「那2只怪兽」是几个变量；
        前一步的结果（「这个效果特殊召唤的怪兽」）是一组卡，逐张循环，只处理表侧表示的。"""
        if ref == "self":
            return ["c:IsRelateToEffect(e)", "c:IsFaceup()"], lines_for("c")
        if ref in self.targets:
            return ["tc:IsRelateToEffect(e)", "tc:IsFaceup()"], lines_for("tc")
        var = self.vars[ref][0]
        if var in ("c", "tc"):
            return [], lines_for(var)
        if "," in var:
            return [], [x for v in var.split(",") for x in lines_for(v)]
        return [], ["for bc in aux.Next(%s) do" % var] + indent(["if bc:IsFaceup() then"] + indent(lines_for("bc")) + ["end"]) + \
            ["end"]

    def apply_atk_update(self, ap, until):
        """「那只怪兽的攻击力直到回合结束时上升进行战斗的对方怪兽的攻击力数值」。"""
        aff, v = ap["affects"], ap["value"]
        if isinstance(v, int):
            value = str(v)
        elif v.get("stat") == "atk" and is_ref(v.get("of"), "battle.opp") and is_ref(aff, "battle.you"):
            value = "d:GetAttack()"
        else:
            raise NotImplementedError("攻击力变化的数值 %r 还没有 Lua 写法" % v)
        reset = "RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END" if until == "end_of_turn" else "RESET_EVENT+RESETS_STANDARD"

        def lines(target):
            return ["local ae=Effect.CreateEffect(c)", "ae:SetType(EFFECT_TYPE_SINGLE)", "ae:SetCode(EFFECT_UPDATE_ATTACK)",
                    "ae:SetValue(%s)" % value, "ae:SetReset(%s)" % reset, "%s:RegisterEffect(ae)" % target]
        if is_ref(aff, "battle.you"):
            pre = ["local a=Duel.GetAttacker()", "local d=Duel.GetAttackTarget()",
                   "if a:IsControler(1-tp) then a,d=d,a end"]
            return pre, ["a and d", "a:IsRelateToBattle()", "d:IsRelateToBattle()"], lines("a"), [], None
        if not is_ref(aff):
            raise NotImplementedError("攻击力变化的对象 %r 还没有 Lua 写法" % aff)
        # 这张卡 / 对象 / 前一步的结果（「这个效果特殊召唤的怪兽的攻击力上升500」）
        guard, call = self.each_card(aff["ref"], lines)
        return [], guard, call, [], None

    def apply_negate_same_name(self, ap, until):
        """「这个效果除外的卡以及原本卡名和那张卡相同的卡的效果无效化」（不限怪兽：魔法陷阱也一并无效）。"""
        from ..model.patterns import same_original_name_ref
        ref = same_original_name_ref(ap)
        if ref is None:
            raise NotImplementedError("效果无效化的这种范围还没有 Lua 写法")
        var = self.vars[ref][0]
        k = self.k
        reset = {"end_of_turn": "RESET_PHASE+PHASE_END", "end_of_next_turn": "RESET_PHASE+PHASE_END,2"}[until]
        self.g.add_func("\n".join([
            "function s.ndistg%d(e,c)" % k,
            "\tlocal tc=e:GetLabelObject()",
            "\tif c:IsType(TYPE_SPELL+TYPE_TRAP) then",
            "\t\treturn c:IsOriginalCodeRule(tc:GetOriginalCodeRule())",
            "\telse",
            "\t\treturn c:IsOriginalCodeRule(tc:GetOriginalCodeRule()) and (c:IsType(TYPE_EFFECT) or c:GetOriginalType()&TYPE_EFFECT~=0)",
            "\tend",
            "end",
            "function s.ndistg2_%d(e,c)" % k,
            "\treturn c:IsOriginalCodeRule(e:GetLabelObject():GetOriginalCodeRule())",
            "end",
            "function s.ndiscon%d(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\treturn re:GetHandler():IsOriginalCodeRule(e:GetLabelObject():GetOriginalCodeRule())",
            "end",
            "function s.ndisop%d(e,tp,eg,ep,ev,re,r,rp)" % k,
            "\tDuel.NegateEffect(ev)",
            "end"]))
        call = ["local xc=%s:GetFirst()" % var,
                "local ne1=Effect.CreateEffect(c)", "ne1:SetType(EFFECT_TYPE_FIELD)", "ne1:SetCode(EFFECT_DISABLE)",
                "ne1:SetTargetRange(LOCATION_ONFIELD,LOCATION_ONFIELD)", "ne1:SetTarget(s.ndistg%d)" % k,
                "ne1:SetLabelObject(xc)", "ne1:SetReset(%s)" % reset, "Duel.RegisterEffect(ne1,tp)",
                "local ne2=Effect.CreateEffect(c)", "ne2:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                "ne2:SetCode(EVENT_CHAIN_SOLVING)", "ne2:SetCondition(s.ndiscon%d)" % k,
                "ne2:SetOperation(s.ndisop%d)" % k, "ne2:SetLabelObject(xc)", "ne2:SetReset(%s)" % reset,
                "Duel.RegisterEffect(ne2,tp)",
                "local ne3=Effect.CreateEffect(c)", "ne3:SetType(EFFECT_TYPE_FIELD)",
                "ne3:SetCode(EFFECT_DISABLE_TRAPMONSTER)", "ne3:SetTargetRange(LOCATION_MZONE,LOCATION_MZONE)",
                "ne3:SetTarget(s.ndistg2_%d)" % k, "ne3:SetLabelObject(xc)", "ne3:SetReset(%s)" % reset,
                "Duel.RegisterEffect(ne3,tp)"]
        return [], [], call, [], None


PLAYER = {"you": "tp", "opp": "1-tp"}
POS = {"attack": "POS_FACEUP_ATTACK", "defense": "POS_FACEUP_DEFENSE"}


def token_code(t):
    """官方衍生物写卡号；DIY 衍生物是这张卡的卡号＋编号（normalize 给的 code_offset）。"""
    return str(t["code"]) if "code" in t else "id+%d" % t.get("code_offset", 1)


def _monsters_only(ap):
    anyof = (ap.get("affects") or {}).get("any") or []
    return any({"card_type": "monster"} in (x.get("filter") or []) for x in anyof if isinstance(x, dict))


def declared_name(sel):
    """选卡条件里有「宣言的卡名」。"""
    return not is_ref(sel) and any(isinstance(f.get("name"), dict) and "ref" in f["name"] for f in sel.get("filter", []))
