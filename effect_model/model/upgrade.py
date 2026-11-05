"""把 v0.1 的 Effect Model 升级成 v0.2。

v0.1 的数据（15 张样例、工作台存档）读入时自动走这里，升级后生成的文本与 Lua 和升级前完全一样。
单个节点的升级函数也给工作台用：它在过渡期仍然编辑 v0.1 的节点，读句子前先升级。
"""

import copy

from .vocab import SCHEMA

# v0.1 的「时 / 场合」是按事件推断的，升级时补成显式的 timing
_IF_EVENTS = ("summoned", "sent_to_gy", "targeted_for_attack")
_SUMMON_EVENT = {"normal": "normal_summon_success", "special": "special_summon_success", "flip": "flip_summon_success"}
_LINK = {"then": "and_if_you_do", "after": "then", "and": "and_if_you_do", "also": "also"}
_UNTIL = {"this_turn": "end_of_turn", "until_end_of_turn": "end_of_turn", "until_end_of_next_turn": "end_of_next_turn"}
_TYPE = {"activate": "activation", "summon_rule": "procedure"}


def _self_ref(subject):
    return {"ref": "self"} if subject == "self" else subject


def upgrade_on(on):
    """事件。返回 (on, timing)；timing 为 None 表示这个事件不写「时 / 场合」（阶段）。"""
    if not on:
        return None, None
    on = copy.deepcopy(on)
    ev = on.pop("event")
    timing = "if" if ev in _IF_EVENTS else "when"
    if "subject" in on:
        on["subject"] = _self_ref(on["subject"])
    if ev == "activation":
        out = {"event": "effect_activated"}
        if on.pop("destroys_on_field", False):
            on["includes"] = ["destroy_on_field"]
    elif ev == "summoned":
        events = [_SUMMON_EVENT[h] for h in on.pop("how", ["normal"])]
        out = {"event": events[0] if len(events) == 1 else events}
    elif ev == "targeted_for_attack":
        out = {"event": "becomes_attack_target"}
    elif ev == "phase":
        out, timing = {"event": "phase_window"}, None
    elif ev == "special_summoned":
        out = {"event": "special_summon_success"}
    else:
        out = {"event": ev}
    out.update(on)
    return out, timing


def upgrade_cond(c):
    c = copy.deepcopy(c)
    if "count" in c:
        return {"cond": "card_count", "sel": c["count"], "cmp": c["cmp"]}
    if "turn" in c:
        return {"cond": "own_turn" if c["turn"] == "you" else "opponent_turn"}
    if "self_materials" in c:
        return {"cond": "material_possession", "what": {"ref": "self"}, "cmp": c["self_materials"]}
    if "applied_this_turn" in c:
        return {"cond": "named_card_used", "effect": c["applied_this_turn"], "what": "applied", "when": "this_turn"}
    if "activated_from" in c:
        return {"cond": "self_location", "where": ["szone"], "activated_from": c["activated_from"]}
    if "lua" in c or "zh" in c:
        return {"cond": "raw", "lua": c.get("lua", ""), "zh": c.get("zh", "")}
    return c


def upgrade_apply(ap):
    """持续适用的内容（v0.1 的 apply.effect / 永续效果的 apply）。"""
    ap = copy.deepcopy(ap)
    what = ap.pop("what")
    if what == "listener":
        on, _ = upgrade_on(ap["on"])
        return {"on": on, "do": upgrade_steps(ap["do"])}
    if what == "cannot_activate":
        return {"cont": "cannot_activate", "player": ap.get("player", "you"),
                "which": {"same_name_as": {"ref": ap["affects"]["same_name_as"]}}}
    if what == "negate_effects":
        x = {"ref": ap["affects"]["same_original_name_as"]}
        return {"cont": "effects_disabled", "scope": "dynamic",
                "affects": {"any": [x, {"who": "both", "where": ["mzone"],
                                        "filter": [{"card_type": "monster"}, {"original_name": {"same_as": x}}]}]}}
    if what == "cannot_attack_declare":
        return {"cont": "cannot_attack", "declare": True, "affects": ap["affects"]}
    if what == "atk_change":
        v = ap["value"]
        if isinstance(v, dict) and v.get("per") == "linked_monsters":
            v = {"mul": [{"count": {"who": "both", "where": ["linked"]}}, v["times"]]}
        return {"cont": "atk_update", "affects": ap["affects"], "value": v}
    if what == "double_battle_damage":
        return {"cont": "battle_damage_change", "affects": {"ref": "self"}, "against": "opp_monster", "value": {"mul": 2}}
    if what == "avoid_battle_damage":
        return {"cont": "battle_damage_zero", "optional": True, "player": ap["involving"]["who"],
                "involving": ap["involving"]}
    raise ValueError("v0.1 的持续效果 %r 不认识" % what)


def upgrade_step(step):
    step = copy.deepcopy(step)
    act = step["act"]
    if "link" in step:
        step["link"] = _LINK[step["link"]]
    if "if" in step:
        step["if"] = [upgrade_cond(c) for c in step["if"]]
    if act == "apply":
        out = {"act": "apply_continuous", "until": _UNTIL[step.pop("duration")], "apply": upgrade_apply(step.pop("effect"))}
        step.pop("act")
        out.update(step)
        return out
    if act == "detach":
        step["act"] = "detach_xyz_material"
        step["from"] = step.pop("what", {"ref": "self"})
    elif act == "set":
        step["act"] = "set_spell_trap"
    elif act == "negate_card_effects" and "duration" in step:
        step["until"] = _UNTIL[step.pop("duration")]
    elif act == "destroy" and step.get("what") == {"ref": "chain"}:
        step["what"] = {"ref": "chain.card"}
    elif act == "special_summon" and "to" in step:
        step["player"] = step.pop("to")
    return step


def upgrade_steps(steps):
    return [upgrade_step(s) for s in steps or []]


def upgrade_target(t):
    t = copy.deepcopy(t)
    out = {"as": t.pop("as")}
    out["sel"] = t
    return out


def _upgrade_limit(eff, eid, limits):
    lim = eff.get("limit")
    if not lim:
        return []
    if lim.get("scope") == "card":
        key = "l_" + eid
        limits[key] = {"scope": "card", "per": "turn", "n": 1}
        return [key]
    key = "l_" + lim.get("group", eid)
    limits.setdefault(key, {"scope": "name", "per": "turn", "n": 1})
    if lim.get("kind") == "activate":
        limits[key]["unit"] = "procedure"
    return [key]


def upgrade_effect(e, eid, limits):
    e = copy.deepcopy(e)
    out = {"id": eid, "type": _TYPE.get(e["type"], e["type"])}
    if e.get("box", "monster") != "monster":
        out["block"] = e["box"]
    if "from" in e:
        out["range"] = e["from"]
    if "optional" in e:
        out["optional"] = e["optional"]
    on, timing = upgrade_on(e.get("on"))
    if on:
        out["on"] = on
        timing = e.get("timing", timing)
        if timing:
            out["timing"] = timing
    if e.get("condition"):
        out["condition"] = [upgrade_cond(c) for c in e["condition"]]
    limit = _upgrade_limit(e, eid, limits)
    if limit:
        out["limit"] = limit
    if e.get("cost"):
        out["cost"] = upgrade_steps(e["cost"])
    if e.get("target"):
        out["target"] = [upgrade_target(t) for t in e["target"]]
    if e.get("do"):
        out["do"] = upgrade_steps(e["do"])
    if e.get("apply"):
        out["apply"] = upgrade_apply(e["apply"])
    return out


def upgrade_rule(e, eid):
    e = copy.deepcopy(e)
    out = {"id": eid, "rule": e["rule"]}
    for k in ("turns", "count_on"):
        if k in e:
            out[k] = e[k]
    if e.get("condition"):
        out["condition"] = [upgrade_cond(c) for c in e["condition"]]
    return out


def upgrade_summon(s):
    if not s or s.get("method") == "pendulum":     # 灵摆在 v0.2 由子类推出
        return {}
    m = s["method"]
    if m == "xyz":
        mat = {"method": "xyz", "level": s["level"], "count": s["count"]}
    elif m == "synchro":
        mat = {"method": "synchro", "tuner": {"count": 1}, "nontuner": {"min": s.get("min", 1)}}
    elif m == "link":
        mat = {"method": "link", "filter": s.get("filter", []), "min": s["min"]}
    else:
        raise ValueError("v0.1 的召唤手续 %r 不认识" % m)
    return {"materials": mat}


def upgrade(card):
    """v0.1 的整张卡 → v0.2（不改动传入的数据）。效果 id 保持不变（缺省的按 v0.1 规则补成 e1、e2……）。"""
    out = {"schema": SCHEMA, "card": copy.deepcopy(card["card"])}
    summon = upgrade_summon(card.get("summon"))
    if summon:
        out["summon"] = summon
    limits, rules, effects = {}, [], []
    for i, e in enumerate(card["effects"]):
        eid = e.get("id", "e%d" % (i + 1))
        if e.get("type") == "rule":
            rules.append(upgrade_rule(e, eid))
        else:
            effects.append(upgrade_effect(e, eid, limits))
    if rules:
        out["rules"] = rules
    if limits:
        out["limits"] = limits
    out["effects"] = effects
    return out
