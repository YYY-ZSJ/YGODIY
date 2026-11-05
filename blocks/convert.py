"""旧存档（Effect Model v0.2，工作台模板编辑器存的）→ v0.3 积木树。

尽量逐项换成积木：效果类型、时机、次数、发动条件、代价、对象、常用处理、常用永续效果。
换不了的部分变成「自定义 Lua」积木（中文写明原来是什么）并列进 notes，原存档整份留在 legacy_v02 里，什么都不丢。
"""

import copy

from .catalog import new

SCHEMA = "ygodiy-blocks/0.3"
WHERE = {"mzone": "mzone", "field": "field", "szone": "szone", "hand": "hand", "deck": "deck", "grave": "grave",
         "banished": "banished", "extra": "extra", "fzone": "field", "pzone": "szone"}
RANGE = {"mzone": "mzone", "szone": "szone", "fzone": "fzone", "pzone": "pzone", "hand": "hand", "grave": "grave",
         "banished": "banished", "field": "mzone"}
MOVES = {"destroy": "destroy", "banish": "banish", "send_to_gy": "send_to_gy", "add_to_hand": "to_hand",
         "special_summon": "special_summon", "set_spell_trap": "set_card", "release": "release", "discard": "discard",
         "return_to_extra": "to_deck"}
COST_MOVES = {"discard": "discard", "send_to_gy": "send_to_gy", "release": "release", "banish": "banish"}
# 一段时间内适用（apply_continuous）的 cont → (效果代码, 默认数值)
TEMP_CODES = {"atk_update": ("EFFECT_UPDATE_ATTACK", None), "def_update": ("EFFECT_UPDATE_DEFENSE", None),
              "change_level": ("EFFECT_UPDATE_LEVEL", None),
              "indestructible_battle": ("EFFECT_INDESTRUCTABLE_BATTLE", 1),
              "indestructible_effect": ("EFFECT_INDESTRUCTABLE_EFFECT", 1),
              "cannot_be_targeted": ("EFFECT_CANNOT_BE_EFFECT_TARGET", 1), "piercing": ("EFFECT_PIERCE", None),
              "direct_attack": ("EFFECT_DIRECT_ATTACK", None), "cannot_direct_attack": ("EFFECT_CANNOT_DIRECT_ATTACK", None),
              "extra_attack": ("EFFECT_EXTRA_ATTACK", None), "attack_all": ("EFFECT_ATTACK_ALL", 1),
              "cannot_be_attack_target": ("EFFECT_CANNOT_BE_BATTLE_TARGET", 1),
              "cannot_change_position": ("EFFECT_CANNOT_CHANGE_POSITION", None)}
ACT_ZH = {"one_of": "加入手卡或特殊召唤（二选一）", "activate_from_deck": "从卡组选1张发动", "perform_summon": "仪式召唤",
          "attach_xyz_material": "作为超量素材", "negate_summon": "那次召唤无效", "select": "双方各自选怪兽",
          "swap_control": "控制权交换", "copy_effect": "得到卡名·效果", "schedule_operation": "之后再处理",
          "apply_continuous": "一段时间内适用的效果"}


# 几个位置一起的发动位置（积木 RANGES 里的组合）
COMBO_RANGE = {frozenset(k.split("_")): k for k in ("hand_grave", "grave_banished", "hand_grave_banished", "hand_szone")}
COMBO_RANGE.update({frozenset(("mzone", "grave")): "mzone_grave", frozenset(("hand", "mzone")): "hand_mzone",
                    frozenset(("hand", "mzone", "grave")): "hand_mzone_grave", frozenset(("szone", "grave")): "szone_grave"})

class Converter:
    def __init__(self, model, kind):
        self.model = model
        self.kind = kind
        self.notes = []
        self.targets = set()        # 当前效果取对象的名字
        self.where = ""             # 当前在转换哪个效果（写 notes 用）

    def note(self, text):
        self.notes.append("%s：%s" % (self.where, text) if self.where else text)

    def raw(self, what, node=None):
        """换不了的一步：变成「自定义 Lua」积木（原来的 Lua 有就带上）。"""
        self.note("「%s」没能换成积木，暂时放了自定义积木，请改用积木重拼" % what)
        lua = "\n".join((node or {}).get("lua") or []) if isinstance((node or {}).get("lua"), list) else ""
        return new("raw", zh="（旧存档：%s）" % what, lua=lua)

    # ------------------------------------------------------------ 卡片
    def where_of(self, sel):
        places = sel.get("where") or ["mzone"]
        places = places if isinstance(places, list) else [places]
        if len(places) > 1:
            combo = {frozenset(["hand", "deck"]): "hand_deck", frozenset(["hand", "grave"]): "hand_grave",
                     frozenset(["deck", "grave"]): "deck_grave", frozenset(["hand", "deck", "grave"]): "hand_deck_grave",
                     frozenset(["hand", "field"]): "hand_field", frozenset(["hand", "mzone"]): "hand_field",
                     frozenset(["grave", "banished"]): "grave_banished"}.get(frozenset(places))
            if combo:
                return combo
            self.note("「%s」几个区域一起选，积木只能选一处，先用了第一个" % "·".join(places))
        return WHERE.get(places[0], "field")

    def filters(self, items):
        out = []
        for f in items or []:
            if not isinstance(f, dict) or not f:
                continue
            k, v = next(iter(f.items()))
            if k == "card_type":
                if v == "spell_trap":
                    out.append(new("f_not", filter=[new("f_kind", kind="monster")]))
                else:
                    out.append(new("f_kind", kind=v))
            elif k == "subtype":
                out.append(new("f_subtype", subtype=v))
            elif k == "race":
                out.append(new("f_race", race=v))
            elif k == "attribute":
                out.append(new("f_attr", attribute=v))
            elif k in ("atk", "def", "level") and isinstance(v, list) and len(v) == 2:
                out.append(new({"atk": "f_atk", "def": "f_def", "level": "f_level"}[k], op=v[0], value=int(v[1])))
            elif k == "set":
                out.append(new("f_set", setcode=f.get("setcode", "0x0"), name=v))
            elif k == "position":
                out.append(new("f_position", position=v))
            elif k == "name" and isinstance(v, int):
                out.append(new("f_name", code=v, name=str(v)))
            elif k == "not":
                inner = self.filters([v])
                if inner:
                    out.append(new("f_not", filter=inner))
            else:
                self.note("选卡条件 %s 没有对应的积木，去掉了" % k)
        return out

    def cards(self, sel, cost=False):
        """v0.2 的选卡（或引用）→ 卡片积木。"""
        if not isinstance(sel, dict):
            return new("this_card")
        if "ref" in sel:
            ref = sel["ref"]
            if ref == "self":
                return new("this_card")
            if ref in self.targets:
                return new("target", name=ref)
            if ref in ("chain", "chain.card"):
                return new("chain_card")
            if ref == "event":
                return new("event_cards")
            if ref == "battle.opp":
                return new("attacker")
            if getattr(self, "in_delay", False):
                return new("carried")
            self.note("引用「%s」换成了「刚才处理的卡」，请确认" % ref)
            return new("operated")
        who = sel.get("who", "you")
        who = who if who in ("you", "opp", "both") else "you"
        count = sel.get("count", "all")
        base = {"who": who, "where": self.where_of(sel), "filter": self.filters(sel.get("filter"))}
        if count == "all" or count is None or (isinstance(count, int) and not cost and sel.get("all")):
            return new("all", **base)
        n = count if isinstance(count, int) else (count.get("min", 1) if isinstance(count, dict) else 1)
        return new("pick", count=max(1, int(n)), **base)

    # ------------------------------------------------------------ 条件
    def cond(self, c):
        k = c.get("cond")
        if k == "card_count":
            src = self.cards(dict(c.get("sel") or {}, count="all"))
            op, n = (c.get("cmp") or ["==", 0])
            if op == "==" and n == 0:
                return new("not_cond", item=[new("exists", cards=[src])])
            if op == ">=" and n == 1:
                return new("exists", cards=[src])
            return new("compare", op=op, left=[new("count_of", cards=[src])], right=[new("num", value=int(n))])
        if k in ("own_turn", "opponent_turn"):
            return new("turn", player="you" if k == "own_turn" else "opp")
        if k == "value_compare":
            l = self.cards(dict((c.get("left") or {}).get("count") or {}, count="all"))
            r = self.cards(dict((c.get("right") or {}).get("count") or {}, count="all"))
            return new("compare", op=c.get("op", ">"), left=[new("count_of", cards=[l])], right=[new("count_of", cards=[r])])
        self.note("条件「%s」没有对应的积木，去掉了" % (c.get("zh") or k))
        return None

    def conds(self, items):
        out = [x for x in (self.cond(c) for c in items or []) if x]
        if not out:
            return []
        return [out[0]] if len(out) == 1 else [new("all_of", items=out)]

    # ------------------------------------------------------------ 处理
    def step(self, st, cost=False):
        """v0.2 的一步 → [积木]。"""
        act = st.get("act")
        if act in MOVES and not st.get("for_each"):
            key = (COST_MOVES if cost else MOVES).get(act)
            if key:
                return [new(key, cards=[self.cards(st.get("what"), cost)])]
        if act == "change_position":
            to = {"faceup": "attack"}.get(st.get("to"), st.get("to", "attack"))
            if st.get("to") == "faceup":
                self.note("「变成表侧表示」换成了「表侧攻击表示」")
            return [new("change_position", to=to if to in ("attack", "defense", "facedown") else "swap",
                        cards=[self.cards(st.get("what"))])]
        if act == "draw":
            p = st.get("player", "you")
            players = ["you", "opp"] if p == "both" else [p]
            return [new("draw", player=x, count=int(st.get("count", 1))) for x in players]
        if act in ("damage", "recover"):
            amount = st.get("amount", 1000)
            if not isinstance(amount, int):
                return [self.raw("%s（数值不是固定的）" % act, st)]
            return [new(act, player=st.get("player", "opp"), amount=[new("num", value=amount)])]
        if act == "pay_lp":
            return [new("pay_lp", amount=[new("num", value=int(st.get("amount", 1000)))])]
        if act == "detach_xyz_material":
            return [new("detach", count=int(st.get("count", 1)))]
        if act == "remove_counter":
            return [new("remove_counter", count=int(st.get("count", 1)))]
        if act == "add_counter":
            if st.get("max"):
                self.note("「最多%d个」的上限没有对应的积木，去掉了" % st["max"])
            return [new("add_counter", count=int(st.get("count", 1)), cards=[self.cards(st.get("what"))])]
        if act in ("negate_activation", "negate_effect", "negate_attack", "negate_summon"):
            return [new(act)]
        if act == "win_duel":
            return [new("win", player=st.get("player", "you"))]
        if act == "create_token":
            t = st.get("token") or {}
            if "code" in t:
                self.note("官方衍生物（卡号 %s）换成了 DIY 衍生物" % t["code"])
            return [new("create_token", name=t.get("name", "衍生物"), count=int(st.get("count", 1)),
                        race=t.get("race", "warrior"), attribute=t.get("attribute", "earth"), level=int(t.get("level", 1)),
                        atk=int(t.get("atk", 0)), def_=int(t.get("def", 0)), position=st.get("position", "defense"))]
        if act == "negate_card_effects":
            reset = "permanent" if st.get("until") == "permanent" else "end_of_turn"
            cards = self.cards(st.get("what"))
            return [new("register", code=code, reset=reset, cards=[copy.deepcopy(cards)])
                    for code in ("EFFECT_DISABLE", "EFFECT_DISABLE_EFFECT")]
        if act == "apply_continuous":
            return self.temp(st)
        if act == "schedule_operation":
            return self.schedule(st)
        if act == "perform_summon" and st.get("method") == "ritual":
            places = (st.get("monster") or {}).get("where") or ["hand"]
            frm = "hand_grave" if "grave" in places else "hand_deck" if "deck" in places else "hand"
            mats = (st.get("materials") or {}).get("where") or []
            if mats and set(mats) - {"hand", "mzone", "field"}:
                self.note("仪式召唤的解放素材从「%s」，积木只用手卡·场上" % "·".join(mats))
            equal = ((st.get("value") or {}).get("op") or "==") == "=="
            filters = [f for f in self.filters((st.get("monster") or {}).get("filter"))
                       if not (f["block"] == "f_subtype" and f["subtype"] == "ritual") and f["block"] != "f_kind"]
            return [new("ritual_summon", level="equal" if equal else "greater", filter=filters, **{"from": frm})]
        if act == "raw":
            if st.get("lua_functions"):
                return [self.raw(st.get("zh") or "自定义处理（带辅助函数）", st)]
            return [new("raw", zh=st.get("zh", ""), lua="\n".join(st.get("lua") or []))]
        return [self.raw(ACT_ZH.get(act, act), st)]

    def temp(self, st):
        aps = st.get("apply") or []
        aps = aps if isinstance(aps, list) else [aps]
        until = st.get("until")
        reset = {"end_of_turn": "end_of_turn", "end_phase": "end_of_turn", "end_of_next_turn": "end_of_next_turn",
                 "permanent": "permanent"}.get(until if isinstance(until, str) else "", None)
        out = []
        for ap in aps:
            c = ap.get("cont") if isinstance(ap, dict) else None
            if c not in TEMP_CODES or reset is None or "affects" not in ap:
                return [self.raw("一段时间内适用的效果（%s）" % (c or "每次……"), st)]
            if ap.get("by"):
                self.note("「只对对方的效果」没有对应的积木，现在对所有效果适用")
            code, default = TEMP_CODES[c]
            value = ap.get("n", ap.get("value", default))
            if c == "extra_attack":
                value = int(value or 2) - 1
            if value is not None and not isinstance(value, int):
                return [self.raw("一段时间内适用的效果（数值不是固定的）", st)]
            node = new("register", code=code, reset=reset, cards=[self.cards(ap["affects"])])
            if value is not None:
                node["value"] = [new("num", value=value)]
            out.append(node)
        return out

    def schedule(self, st):
        """「之后的某个时候再处理」→「之后再处理」；用到前一步结果的换成「带过来的卡」。"""
        at = st.get("at") or {}
        if at.get("phase") == "end" and at.get("which") == "this_turn":
            when = "this_end"
        elif at.get("phase") == "standby" and at.get("nth", 1) == 1:
            when = "next_standby"
        else:
            when = "next_standby" if at.get("phase") == "standby" else "next_end"
            self.note("「之后再处理」的时间（第几次 / 第几回合）换成了「%s」" % {"next_standby": "下次的自己准备阶段",
                                                                       "next_end": "下个回合的结束阶段"}[when])
        uses = any(isinstance((x.get("what") or {}), dict) and "ref" in (x.get("what") or {}) for x in st.get("do") or [])
        self.in_delay = True
        body = self.steps(st.get("do"))
        self.in_delay = False
        return [new("delay", when=when, carry="yes" if uses else "", body=body)]

    def steps(self, items, cost=False):
        """一串处理 → 积木；「那之后」把后面的步骤包进去，条件、可以选择不做也各自包起来。"""
        out = []
        items = list(items or [])
        for i, st in enumerate(items):
            if st.get("link") in ("then", "also_after_that") and out and not cost:
                out.append(new("after", body=self.steps([dict(items[i], link="also")] + items[i + 1:])))
                return out
            if st.get("link") == "and_if_you_do" and out and not cost:
                out.append(new("after", how="and", body=self.steps([dict(items[i], link="also")] + items[i + 1:])))
                return out
            blocks = self.step(st, cost)
            if st.get("if"):
                c = self.conds(st["if"])
                blocks = [new("if", cond=c, then=blocks)] if c else blocks
            if st.get("optional"):
                blocks = [new("may", ask=st.get("ask") or "是否继续处理？", body=blocks)]
            out += blocks
        return out

    # ------------------------------------------------------------ 效果
    def limit(self, eff):
        keys = eff.get("limit") or []
        keys = keys if isinstance(keys, list) else [keys]
        limits = self.model.get("limits") or {}
        for k in keys:
            spec = limits.get(k, k) if isinstance(k, str) else k
            if not isinstance(spec, dict):
                continue
            shared = sum(1 for e in self.model.get("effects", []) if k in (e.get("limit") or [])) > 1
            if shared:
                self.note("几个效果共用的次数限制换成了各自的「1回合1次」")
            if spec.get("scope") == "card":
                return "card"
            if spec.get("scope") == "name":
                if spec.get("unit") == "activate_card":
                    return "activate_card"
                if spec.get("per") == "duel":
                    return "duel"
                if spec.get("unit") not in (None, "use"):
                    self.note("「这个卡名的方法1回合1次」换成了「这个卡名的效果1回合1次」")
                return "name"
            self.note("次数限制（%s）没有对应的积木，去掉了" % spec.get("scope"))
        return ""

    def event(self, eff, node):
        on = eff.get("on")
        if not on:
            if (eff.get("window") or {}).get("phase") == "damage_step":
                node["damage_step"] = "yes"
            return
        ev = on.get("event")
        events = ev if isinstance(ev, list) else [ev]
        summon = {"normal_summon_success": "summon", "special_summon_success": "spsummon",
                  "flip_summon_success": "flip_summon"}
        if set(events) == {"normal_summon_success", "special_summon_success"}:
            node["event"] = "summon_both"
        elif all(e in summon for e in events):
            node["event"] = summon[events[0]]
            if len(events) > 1:
                self.note("「召唤·特殊召唤」两个时机，积木只能选一个，先用了「%s」" % ("召唤" if node["event"] == "summon" else "特殊召唤"))
        elif ev == "sent_to_gy":
            node["event"] = "field_to_grave" if on.get("from") == ["field"] else "to_grave"
            if on.get("from") and on.get("from") != ["field"] or on.get("turn"):
                self.note("「从哪里送去墓地」「谁的回合」没有对应的积木，去掉了")
        elif ev == "destroyed":
            by = on.get("by") or on.get("reason")
            node["event"] = {"battle": "battle_destroyed", "effect": "effect_destroyed"}.get(by, "destroyed")
        elif ev == "summon_attempt":
            node["event"] = "summon_attempt" if on.get("method") == "normal" else "spsummon_attempt"
            node["event_player"] = "opp" if on.get("by") == "opp" else "any"
            if on.get("method") == "flip":
                self.note("「反转召唤之际」换成了「召唤之际」")
        elif ev == "attack_declared":
            node["event"], node["event_player"] = "attack", on.get("by", "any") if on.get("by") in ("you", "opp") else "any"
        elif ev == "effect_activated":
            node["event"], node["event_player"] = "chaining", "opp" if on.get("by") == "opp" else "any"
            if on.get("kinds") and set(on["kinds"]) != {"monster", "spell", "trap"} or on.get("targets") or on.get("includes"):
                self.note("「发动的是哪种卡 / 限定」没有对应的积木，现在对所有发动都能回应")
        elif ev == "becomes_attack_target":
            node["event"] = "be_attacked"
        elif ev == "phase_end" and on.get("phase") == "battle":
            node["event"] = "battle_end"
            node["event_player"] = on.get("turn") if on.get("turn") in ("you", "opp") else "any"
        elif ev == "phase_window":
            node["event"] = on.get("phase", "end") if on.get("phase") in ("end", "standby") else "end"
            node["event_player"] = on.get("turn") if on.get("turn") in ("you", "opp") else "any"
        else:
            self.note("时机「%s」没有对应的积木，换成了自由时点" % ev)

    def effect(self, eff):
        t = eff.get("type")
        if t == "continuous" and eff.get("on") and eff.get("do"):
            return self.listener(eff)
        if t == "continuous":
            return self.continuous(eff)
        if t == "procedure":            # 编号的特殊召唤手续「这张卡可以从手卡特殊召唤」
            places = eff.get("range") or ["hand"]
            places = places if isinstance(places, list) else [places]
            rng = "hand_grave" if set(places) == {"hand", "grave"} else places[0]
            if rng not in ("hand", "grave", "banished", "hand_grave"):
                self.note("特殊召唤手续的位置「%s」换成了手卡" % "·".join(places))
                rng = "hand"
            return [new("sp_proc", range=rng, limit="once" if self.limit(eff) else "",
                        condition=self.conds(eff.get("condition")), cost=self.steps(eff.get("cost"), cost=True))]
        if t not in ("activation", "ignition", "quick", "trigger", "flip"):
            self.note("「%s」类的效果没有对应的积木，没有转换" % {"flip": "反转效果", "procedure": "特殊召唤手续"}.get(t, t))
            return []
        typ = {"activation": "activate", "ignition": "ignition", "quick": "quick_o", "flip": "flip",
               "trigger": "trigger_o" if eff.get("optional", True) else "trigger_f"}[t]
        rng = eff.get("range") or []
        places = [RANGE.get(x) for x in (rng if isinstance(rng, list) else [rng])]
        default = "szone" if self.kind != "monster" else "mzone"
        combo = COMBO_RANGE.get(frozenset(x for x in places if x))
        if combo:
            node_range = combo
        else:
            node_range = next((x for x in places if x), default)
            if len([x for x in places if x]) > 1:
                self.note("效果的位置「%s」没有对应的组合，只用了第一个" % "·".join(map(str, rng)))
        node = new("effect", type=typ, range=node_range,
                   limit=self.limit(eff), part="pendulum" if eff.get("block") == "pendulum" else "monster")
        self.event(eff, node)
        if typ.startswith("trigger") and node["event"] == "free":
            node["type"] = "quick_o"
            self.note("诱发效果的时机换不过来，暂时改成了诱发即时效果，请重新选时机")
        targets = eff.get("target") or []
        self.targets = {t.get("as") for t in targets if t.get("as")}
        if targets:
            t0 = targets[0]
            sel = dict(t0.get("sel") or {})
            n = sel.get("count", 1)
            n = n if isinstance(n, int) else 1
            node["target"] = [new("take_target", count=n, source=[self.cards(dict(sel, count="all"))],
                                  **{"as": t0.get("as") or "T"})]
            if len(targets) > 1:
                self.note("取了几组对象，积木只放得下一组，后面的去掉了")
        node["condition"] = self.conds(eff.get("condition"))
        node["cost"] = self.steps(eff.get("cost"), cost=True)
        node["operation"] = self.steps(eff.get("do"))
        self.targets = set()
        return [node]

    def listener(self, eff):
        """「每次……，……」（不入连锁的永续）。"""
        rng = {"monster": "mzone", "spell": "szone", "trap": "szone"}[self.kind]
        node = new("effect", type="listener", range=rng, limit=self.limit(eff),
                   part="pendulum" if eff.get("block") == "pendulum" else "monster")
        self.event(eff, node)
        if node["event"] == "free":
            self.note("「每次……」的时机换不过来，没有转换")
            return []
        node["condition"] = self.conds(eff.get("condition"))
        node["operation"] = self.steps(eff.get("do"))
        return [node]

    def continuous(self, eff):
        if eff.get("on"):
            self.note("「每次……」（不进连锁）的效果没有对应的积木，没有转换")
            return []
        aps = eff.get("apply") or []
        aps = aps if isinstance(aps, list) else [aps]
        out = []
        rng = {"monster": "mzone", "spell": "szone", "trap": "szone"}[self.kind]
        part = "pendulum" if eff.get("block") == "pendulum" else "monster"
        if part == "pendulum":
            rng = "pzone"
        for ap in aps:
            c = ap.get("cont")
            aff = ap.get("affects") or {"ref": "self"}
            value = ap.get("value")
            if isinstance(value, dict) and isinstance(value.get("mul"), list) and isinstance(value["mul"][-1], int):
                self.note("「×……的数量」没有对应的积木，先只用了数值本身")
                value = value["mul"][-1]
            if c in ("atk_update", "def_update") and isinstance(value, int):
                code = "EFFECT_UPDATE_ATTACK" if c == "atk_update" else "EFFECT_UPDATE_DEFENSE"
            elif c == "cannot_attack":
                code, value = "EFFECT_CANNOT_ATTACK_ANNOUNCE", None
            elif c == "immune_effect":
                code, value = "EFFECT_IMMUNE_EFFECT", None
                if ap.get("by") not in (None, "opp", "others"):
                    self.note("「不受……的效果影响」的范围换成了「其他卡的效果」")
            elif c == "atk_set" and isinstance(value, int):
                code = "EFFECT_SET_ATTACK"
            elif c in TEMP_CODES:
                code, value = TEMP_CODES[c][0], TEMP_CODES[c][1]
                if c == "extra_attack":
                    value = int(ap.get("n", 2)) - 1
                elif value is None and isinstance(ap.get("value"), int):
                    value = ap["value"]
            else:
                self.note("永续效果「%s」没有对应的积木，没有转换" % c)
                continue
            node = new("continuous", code=code, range=rng, part=part,
                       against="opp" if ap.get("by") == "opp" else "any")
            if aff.get("ref") == "self":
                node["mode"] = "self"
            else:
                who = aff.get("who", "you")
                node.update(mode="zone", who=who if who in ("you", "opp", "both") else "you",
                            where={"field": "field", "szone": "szone"}.get(self.where_of(aff), "mzone"),
                            filter=self.filters(aff.get("filter")))
            if value is not None:
                node["value"] = [new("num", value=value)]
            node["condition"] = self.conds(eff.get("condition"))
            out.append(node)
        return out

    def convert(self):
        effects = []
        for i, eff in enumerate(self.model.get("effects", [])):
            self.where = "效果%d" % (i + 1)
            try:
                effects += self.effect(eff)
            except Exception as ex:      # 结构和工作台存的不一样（手写的存档）：这个效果不转，说明原因
                self.note("没能转换（%s），没有转换" % ex)
        self.where = ""
        for r in self.model.get("rules", []):
            self.note("规则文字「%s」没有对应的积木，没有转换" % r.get("rule"))
        out = {"schema": SCHEMA, "effects": effects}
        if self.model.get("summon"):
            out["summon"] = copy.deepcopy(self.model["summon"])
            if self.model.get("limits"):          # 出场限制里的次数额度
                out["limits"] = copy.deepcopy(self.model["limits"])
        if self.notes or self.model.get("rules"):
            out["legacy_v02"] = copy.deepcopy(self.model)
        return out


def convert(model, kind="monster"):
    """v0.2 的存档（不含 card 块也行）→ (v0.3 积木树（不含 card 块）, 没能完全转换的说明列表)。"""
    c = Converter(model, kind)
    out = c.convert()
    for n in walk_tokens(out):
        n["def"] = n.pop("def_", n.get("def", 0))
    return out, c.notes


def walk_tokens(node):
    if isinstance(node, dict):
        if node.get("block") == "create_token":
            yield node
        for v in node.values():
            yield from walk_tokens(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_tokens(v)
