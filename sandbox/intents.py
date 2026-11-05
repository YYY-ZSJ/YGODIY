"""按引擎实际提问兑现选择意图；模型无需枚举select/yes/no。"""

import copy

from .scenario import Runner, ScenarioError, STABLE, IDLE_LISTS


def expand_intents(intents, ref):
    actions = []
    for source in intents:
        intent = copy.deepcopy(source)
        for key in ("card", "by", "target"):
            if key in intent:
                intent[key] = ref(intent[key])
        intent["choose"] = [dict(c, code=ref(c["ref"])) if isinstance(c, dict) else ref(c)
                            for c in intent.get("choose", [])]
        if intent["do"] != "flip":
            intent["do"] = "decline" if intent.get("decline") else intent["do"]
            actions.append(intent)
            continue
        card, player, method = intent["card"], intent.get("player", 0), intent["method"]
        policy = dict(intent, do="activate")
        trigger = {"_trigger": policy}
        if method == "summon":
            actions.append(dict(do="reposition", card=card, player=player, **trigger))
        elif method == "effect":
            actions.append(dict(do="activate", card=intent["by"], player=player, choose=[card], **trigger))
        elif method == "battle":
            attacker = 1 - player
            if attacker == 1:
                actions.append({"do": "end_turn", "player": 0})
            actions.extend([{"do": "battle", "player": attacker},
                            dict(do="attack", player=attacker, card=intent["by"], target=card, **trigger)])
        else:
            raise ValueError("flip.method须为summon/battle/effect。")
    return actions


class IntentRunner(Runner):
    def __init__(self, core, scene):
        super().__init__(core, scene)
        self.intent, self.trigger = {}, None
        self.choices, self.opportunities = [], set()
        self.check_results, self.questions = [], []
        self.executed_intents, self.declined = [], []
        self.last_request = None

    def take(self):
        action = super().take()
        self.intent = action
        self.choices = list(action.get("choose", []))
        self.trigger = action.get("_trigger")
        self.executed_intents.append({k: v for k, v in action.items() if not k.startswith("_")})
        return action

    @staticmethod
    def effect_number(entry):
        desc, code = entry.get("description", entry.get("desc", 0)), entry.get("code", 0)
        return (desc & 15) + 1 if desc and desc >> 4 == code else None

    def find(self, entries, action, key="card"):
        hits = [i for i, entry in enumerate(entries) if self.matches(entry, {
            "code": action.get(key), **({"in": action["from"]} if "from" in action else {})})]
        if "effect" in action:
            exact = [i for i in hits if self.effect_number(entries[i]) == action["effect"]]
            if exact:
                return exact[0]
            if any(self.effect_number(entries[i]) is not None for i in hits):
                return None
        if len(hits) > 1:
            raise ScenarioError("同一张卡有多个可用效果，请在意图中明确effect编号。")
        return hits[0] if hits else None

    def finished(self, request):
        self.last_request = copy.deepcopy(request)
        if request["type"] == "select_effectyn":
            self.opportunities.add((request["player"], request["code"], self.effect_number(request)))
        if request["type"] == "select_chain":
            self.opportunities.update((request["player"], e["code"], self.effect_number(e)) for e in request["chains"])
        while self.actions and self.actions[0].get("do") == "decline" and request["type"] in STABLE:
            action = self.take()
            if self.find(request.get("activatable", []), action) is not None:
                self.declined.append(action["card"])
            self.say("→ 选择不发动 " + self.core.name(action["card"]))
        return super().finished(request)

    def respond(self, request):
        self.questions.append(copy.deepcopy(request))
        return super().respond(request)

    def _trigger_action(self, request):
        policy = self.trigger
        if policy is None:
            return None
        if request["type"] == "select_effectyn" and policy["card"] == request["code"]:
            return policy
        if request["type"] == "select_chain" and self.find(request["chains"], policy) is not None:
            return policy
        return None

    def on_select_effectyn(self, request, action):
        policy = self._trigger_action(request)
        if policy is not None:
            self.intent, self.choices = policy, list(policy.get("choose", []))
            self.say("→ %s%s的效果" % ("不发动" if policy.get("decline") else "发动", self.core.name(request["code"])))
            self.duel.respond_int(0 if policy.get("decline") else 1)
            if policy.get("decline"):
                self.declined.append(request["code"])
        elif action and action.get("do") == "decline" and action.get("card") == request["code"]:
            self.take()
            self.say("→ 选择不发动 " + self.core.name(request["code"]))
            self.declined.append(request["code"])
            self.duel.respond_int(0)
        else:
            super().on_select_effectyn(request, action)

    def on_select_chain(self, request, action):
        policy = self._trigger_action(request)
        if policy is not None:
            self.intent, self.choices = policy, list(policy.get("choose", []))
            if policy.get("decline"):
                if request["forced"]:
                    raise ScenarioError("意图要求不发动，但引擎提示必须发动。")
                self.duel.respond_int(-1)
                self.declined.append(policy["card"])
            else:
                self.duel.respond_int(self.find(request["chains"], policy))
            return
        if action and action.get("do") == "decline" and self.find(request["chains"], action) is not None:
            self.take()
            if request["forced"]:
                raise ScenarioError("意图要求不发动，但引擎提示必须发动。")
            self.duel.respond_int(-1)
            self.declined.append(action["card"])
            return
        super().on_select_chain(request, action)

    def pick(self, entries, action, lo, hi):
        selected, consumed = [], []
        for position, wanted in enumerate(self.choices):
            index = next((i for i, entry in enumerate(entries) if i not in selected and self.matches(entry, wanted)), None)
            if index is not None and len(selected) < hi:
                selected.append(index)
                consumed.append(position)
        if len(selected) < lo:
            if not self.choices and len(entries) == lo:
                selected = list(range(lo))
            else:
                raise ScenarioError("当前选卡提问无法兑现意图；想选：%s；可选：%s；需选%d～%d张。" % (
                    self.choices, self.listing(entries), lo, hi))
        self.choices = [c for i, c in enumerate(self.choices) if i not in consumed]
        return selected

    def on_select_battlecmd(self, request, action):
        if action and action["do"] == "attack":
            index = self.find(request["attackable"], action)
            if index is None:
                raise ScenarioError("指定的攻击者当前不能攻击。")
            action = self.take()
            self.choices = [action["target"]] if action.get("target") else []
            self.say("→ 攻击 " + self.core.name(action.get("target", 0)))
            self.duel.respond_int((index << 16) | 1)
        else:
            super().on_select_battlecmd(request, action)

    def on_select_option(self, request, action):
        index = self.intent.get("option")
        if index is None and len(request.get("options", [])) > 1:
            raise ScenarioError("当前需要选择效果分支，请在发动意图中指定option（从1起）。")
        if index is not None and not 1 <= index <= len(request["options"]):
            raise ScenarioError("指定分支不在当前可选范围中。")
        self.duel.respond_int((index or 1) - 1)

    def on_select_unselect_card(self, request, action):
        for position, wanted in enumerate(self.choices):
            index = next((i for i, entry in enumerate(request["cards"]) if self.matches(entry, wanted)), None)
            if index is not None:
                self.choices.pop(position)
                self.duel.respond_bytes([1, index])
                return
        if request["finishable"]:
            self.duel.respond_int(-1)
        elif not self.choices and len(request["cards"]) == 1:
            self.duel.respond_bytes([1, 0])
        else:
            raise ScenarioError("素材选择无法兑现意图；请查看当前已选、可选素材。")

    def on_select_sum(self, request, action):
        if not self.choices:
            return super().on_select_sum(request, action)
        chosen, consumed = [], []
        for position, wanted in enumerate(self.choices):
            index = next((i for i, entry in enumerate(request["cards"]) if i not in chosen and self.matches(entry, wanted)), None)
            if index is not None:
                chosen.append(index)
                consumed.append(position)
        if not chosen:
            raise ScenarioError("数值合计提问中没有指定素材；请查看可选项。")
        self.choices = [c for i, c in enumerate(self.choices) if i not in consumed]
        must = len(request["must"])
        self.duel.respond_bytes([must + len(chosen)] + [0] * must + chosen)

    def check(self, spec, request):
        before = len(self.failures)
        completed = False
        try:
            if spec.get("check") == "offered" and spec.get("as") == "chain":
                spec["_seen"] = any(p == spec.get("player", 0) and code == spec["card"] and
                    ("effect" not in spec or effect in (None, spec["effect"])) for p, code, effect in self.opportunities)
            elif spec.get("check") == "offered" and spec.get("as") in IDLE_LISTS:
                key = IDLE_LISTS[spec["as"]][0]
                entries = request.get(key, [])
                index = self.find(entries, spec)
                request = dict(request, **{key: [entries[index]] if index is not None else []})
            super().check(spec, request)
            completed = True
        finally:
            self.check_results.append({"spec": {k: v for k, v in spec.items() if not k.startswith("_")},
                "completed": completed, "passed": completed and len(self.failures) == before,
                "errors": self.failures[before:]})

    def report(self):
        failed = any(c["completed"] and not c["passed"] for c in self.check_results)
        pending = [a for a in self.actions if "check" in a]
        return {"status": "失败" if failed else "执行受阻" if self.failures or pending else "通过",
            "checks": self.check_results, "errors": list(self.failures), "log": list(self.lines),
            "current_question": self.last_request if self.failures or pending else None,
            "unreached_assertions": pending, "questions": self.questions,
            "executed_intents": self.executed_intents,
            "evidence": "断言实际失败" if failed else "实际执行" if not pending and not self.failures else "尚未走完断言"}
