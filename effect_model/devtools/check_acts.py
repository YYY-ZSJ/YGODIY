"""工作台第二批的检查：生成器原来只照某张样例卡支持、这次放宽了的写法（自己选N张手卡丢弃、处理中给对象加攻击力、
攻击力变成固定数值、不受其他卡的效果影响、DIY 衍生物……）。文字照官方的说法，生成的 Lua 在沙盒里效果对，改坏一处的对照能被查出。

用的是 DIY 测试卡（卡号 1000093xx）；DIY 衍生物的卡片数据照导出卡包时的做法（卡号＝这张卡＋1）加进沙盒。

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.check_acts
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import SCHEMA, build  # noqa: E402

SELF = {"ref": "self"}
MONSTER = {"type": 0x21, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 1000, "def": 1000}
SPELL = {"type": 0x2, "level": 0, "attribute": 0, "race": 0, "atk": 0, "def": 0}
DORON, LV4, RAIGEKI = 756652, 549481, 12580477     # 多隆（战士族 900/500）、硬毛鼠（4星）、雷击


def card(code, name, kind, effects, rec):
    sub = ["effect"] if kind == "monster" else ["normal"]
    model = {"schema": SCHEMA, "card": {"code": code, "name": name, "kind": kind, "subtypes": sub}, "effects": effects}
    return model, dict(rec, code=code, name=name, alias=0, setcodes=[])


def act(p, do, c=None, **kw):
    a = {"player": p, "do": do}
    if c is not None:
        a["card"] = c
    a.update(kw)
    return a


def chk(kind, **kw):
    return dict({"check": kind}, **kw)


CASES = []

m, r = card(100009301, "处理测试·施舍", "spell",
            [{"id": "e1", "type": "activation",
              "do": [{"act": "draw", "player": "you", "count": 3},
                     {"act": "discard", "link": "then", "what": {"who": "you", "where": ["hand"], "count": 2}}]}], SPELL)
CASES.append(("自己选2张手卡丢弃", m, r, "①：自己从卡组抽3张。那之后，选2张手卡丢弃。",
              [{"field": {"0": {"hand": [100009301, LV4, LV4]}, "1": {}},
                "actions": [act(0, "activate", 100009301), chk("count", player=0, **{"in": "hand"}, eq=3),
                            chk("count", player=0, **{"in": "grave"}, eq=3)]}],
              ("DiscardHand(tp,nil,2,2", "DiscardHand(tp,nil,1,1")))

m, r = card(100009302, "处理测试·鼓舞", "monster",
            [{"id": "e1", "type": "ignition", "target": [{"as": "t1", "sel": {"who": "you", "where": ["mzone"], "count": 1}}],
              "do": [{"act": "apply_continuous", "until": "end_of_turn",
                      "apply": {"cont": "atk_update", "affects": {"ref": "t1"}, "value": 500}}]}], MONSTER)
CASES.append(("处理中：那只怪兽的攻击力直到回合结束时上升", m, r,
              "①：以自己场上1只怪兽为对象才能发动。那只怪兽的攻击力直到回合结束时上升500。",
              [{"field": {"0": {"mzone": [100009302, DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009302), act(0, "select", cards=[DORON]),
                            chk("atk", player=0, card=DORON, eq=1400)]}],
              ("ae:SetValue(500)", "ae:SetValue(400)")))

m, r = card(100009303, "处理测试·定值", "monster",
            [{"id": "e1", "type": "continuous", "apply": {"cont": "atk_set", "affects": SELF, "value": 2000}}], MONSTER)
CASES.append(("攻击力变成固定数值", m, r, "①：这张卡的攻击力变成2000。",
              [{"field": {"0": {"mzone": [100009303]}, "1": {}}, "actions": [chk("atk", card=100009303, eq=2000)]}],
              ("SetCode(EFFECT_SET_ATTACK)", "SetCode(EFFECT_UPDATE_ATTACK)")))

m, r = card(100009304, "处理测试·原本", "monster",
            [{"id": "e1", "type": "continuous",
              "apply": {"cont": "atk_set", "affects": SELF, "value": 2500, "original": True}}], MONSTER)
CASES.append(("原本攻击力变成固定数值", m, r, "①：这张卡的原本攻击力变成2500。",
              [{"field": {"0": {"mzone": [100009304]}, "1": {}}, "actions": [chk("atk", card=100009304, eq=2500)]}],
              ("SetCode(EFFECT_SET_BASE_ATTACK)", "SetCode(EFFECT_UPDATE_ATTACK)")))

m, r = card(100009305, "处理测试·免疫", "monster",
            [{"id": "e1", "type": "continuous", "apply": {"cont": "immune_effect", "affects": SELF, "from": {}}}], MONSTER)
CASES.append(("不受其他卡的效果影响", m, r, "①：这张卡不受其他卡的效果影响。",
              [{"field": {"0": {"mzone": [100009305]}, "1": {"hand": [RAIGEKI]}},
                "actions": [act(0, "end_turn"), act(1, "activate", RAIGEKI),
                            chk("count", player=0, card=100009305, **{"in": "mzone"}, eq=1)]}],
              ("SetCode(EFFECT_IMMUNE_EFFECT)", "SetCode(EFFECT_PIERCE)")))

m, r = card(100009306, "处理测试·衍生", "spell",
            [{"id": "e1", "type": "activation",
              "do": [{"act": "create_token", "count": 2, "player": "you", "position": "defense",
                      "token": {"name": "测试衍生物", "race": "beast", "attribute": "earth", "level": 1, "atk": 0, "def": 0}}]}],
            SPELL)
CASES.append(("DIY 衍生物（卡号＝这张卡＋1）", m, r, "①：在自己场上把2只「测试衍生物」（兽族·地·1星·攻/守0）守备表示特殊召唤。",
              [{"field": {"0": {"hand": [100009306]}, "1": {}},
                "actions": [act(0, "activate", 100009306), chk("count", player=0, card=100009307, **{"in": "mzone"}, eq=2)]}],
              ("for i=1,2 do", "for i=1,1 do")))

m, r = card(100009307, "处理测试·可选", "monster",
            [{"id": "e1", "type": "ignition",
              "do": [{"act": "draw", "player": "you", "count": 1},
                     {"act": "damage", "player": "opp", "amount": 500, "link": "then", "optional": True}]}], MONSTER)
CASES.append(("那之后，可以……（问玩家；选是 / 选否）", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。那之后，可以给与对方500伤害。",
              [{"field": {"0": {"mzone": [100009307]}, "1": {}},
                "actions": [act(0, "activate", 100009307), act(0, "yes"), chk("lp", player=1, eq=7500)]},
               {"field": {"0": {"mzone": [100009307]}, "1": {}},
                "actions": [act(0, "activate", 100009307), act(0, "no"), chk("lp", player=1, eq=8000)]}],
              ("Duel.SelectYesNo(tp,aux.Stringid(id,1))", "true")))

m, r = card(100009308, "处理测试·跟进", "spell",
            [{"id": "e1", "type": "activation",
              "do": [{"act": "special_summon", "as": "b1",
                      "what": {"who": "you", "where": ["deck"], "count": 1, "filter": [{"card_type": "monster"}]}},
                     {"act": "apply_continuous", "link": "and_if_you_do", "until": "end_of_turn",
                      "apply": {"cont": "atk_update", "affects": {"ref": "b1"}, "value": 500}}]}], SPELL)
CASES.append(("这个效果特殊召唤的怪兽的攻击力上升（引用前一步的结果）", m, r,
              "①：从卡组把1只怪兽特殊召唤，这个效果特殊召唤的怪兽的攻击力直到回合结束时上升500。",
              [{"field": {"0": {"hand": [100009308], "deck": [DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009308), chk("atk", player=0, card=DORON, eq=1400)]}],
              ("ae:SetValue(500)", "ae:SetValue(400)")))

def from_deck(*consequences):
    """「从卡组把1只怪兽特殊召唤。这个效果特殊召唤的怪兽……」：处理的后果挂在特殊召唤那一步后面。"""
    steps = [{"act": "special_summon", "as": "b1",
              "what": {"who": "you", "where": ["deck"], "count": 1, "filter": [{"card_type": "monster"}]}}]
    return [{"id": "e1", "type": "activation", "do": steps + [dict({"link": "also"}, **c) for c in consequences]}]


def on_b1(cont, until="permanent", **kw):
    return {"act": "apply_continuous", "until": until, "apply": dict({"cont": cont, "affects": {"ref": "b1"}}, **kw)}


def at_end(act):
    return {"act": "schedule_operation", "activates": False, "at": {"phase": "end", "which": "this_turn"},
            "do": [{"act": act, "what": {"ref": "b1"}}]}


m, r = card(100009321, "后果测试·不能攻击", "spell", from_deck(on_b1("cannot_attack")), SPELL)
CASES.append(("后果：这个效果特殊召唤的怪兽不能攻击", m, r, "①：从卡组把1只怪兽特殊召唤。这个效果特殊召唤的怪兽不能攻击。",
              [{"field": {"0": {"hand": [100009321], "deck": [DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009321), act(0, "battle"),
                            chk("offered", card=DORON, **{"as": "attack"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_ATTACK)", "SetCode(EFFECT_CANNOT_TRIGGER)")))

m, r = card(100009322, "后果测试·离场除外", "spell",
            from_deck({"act": "negate_card_effects", "what": {"ref": "b1"}, "until": "permanent"},
                      on_b1("redirect_destination", from_dest="leave_field", to_dest="banished")), SPELL)
CASES.append(("后果：效果无效化，从场上离开的场合除外（并成一句）", m, r,
              "①：从卡组把1只怪兽特殊召唤。这个效果特殊召唤的怪兽的效果无效化，从场上离开的场合除外。",
              [{"field": {"0": {"hand": [100009322], "deck": [DORON]}, "1": {"hand": [RAIGEKI]}},
                "actions": [act(0, "activate", 100009322), act(0, "end_turn"), act(1, "activate", RAIGEKI),
                            chk("count", player=0, card=DORON, **{"in": "banished"}, eq=1)]}],
              ("SetCode(EFFECT_LEAVE_FIELD_REDIRECT)", "SetCode(EFFECT_CANNOT_TRIGGER)")))

m, r = card(100009323, "后果测试·结束除外", "spell", from_deck(at_end("banish")), SPELL)
CASES.append(("后果：在结束阶段除外", m, r, "①：从卡组把1只怪兽特殊召唤。这个效果特殊召唤的怪兽在结束阶段除外。",
              [{"field": {"0": {"hand": [100009323], "deck": [DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009323), act(0, "end_turn"),
                            chk("count", player=0, card=DORON, **{"in": "banished"}, eq=1)]}],
              ("Duel.Remove(tg,POS_FACEUP,REASON_EFFECT)", "Duel.Destroy(tg,REASON_EFFECT)")))

m, r = card(100009324, "后果测试·结束回手", "spell", from_deck(at_end("add_to_hand")), SPELL)
CASES.append(("后果：在结束阶段回到手卡", m, r, "①：从卡组把1只怪兽特殊召唤。这个效果特殊召唤的怪兽在结束阶段回到手卡。",
              [{"field": {"0": {"hand": [100009324], "deck": [DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009324), act(0, "end_turn"),
                            chk("count", player=0, card=DORON, **{"in": "hand"}, eq=1)]}],
              ("Duel.SendtoHand(tg,nil,REASON_EFFECT)", "Duel.Destroy(tg,REASON_EFFECT)")))

for code, name, cons, text in (
        (100009325, "后果测试·素材", [on_b1("cannot_use_material", until="end_of_turn", method="synchro")],
         "这个回合，这个效果特殊召唤的怪兽不能作为同调素材。"),
        (100009326, "后果测试·解放", [on_b1("cannot_release")], "这个效果特殊召唤的怪兽不能解放。"),
        (100009327, "后果测试·无效破坏", [{"act": "negate_card_effects", "what": {"ref": "b1"}, "until": "permanent"},
                                          at_end("destroy")],
         "这个效果特殊召唤的怪兽的效果无效化，在结束阶段破坏。"),
        (100009328, "后果测试·那之后", [at_end("destroy"), {"act": "draw", "player": "you", "count": 1, "link": "then"}],
         "这个效果特殊召唤的怪兽在结束阶段破坏。那之后，自己从卡组抽1张。")):
    m, r = card(code, name, "spell", from_deck(*cons), SPELL)
    CASES.append(("只查文字和加载：后果 " + text[:-1], m, r, "①：从卡组把1只怪兽特殊召唤。" + text, [], None))

MOONBOOK, POT = 14087893, 55144522         # 月之书（速攻魔法）、强欲之壶（通常魔法）
m, r = card(100009309, "处理测试·检索", "spell",
            [{"id": "e1", "type": "activation",
              "do": [{"act": "add_to_hand", "what": {"who": "you", "where": ["deck"], "count": 1,
                                                     "filter": [{"card_type": "spell"}, {"subtype": "normal"}]}}]}], SPELL)
CASES.append(("魔陷的种类：通常魔法卡（只有「魔法」这一位）", m, r, "①：从卡组把1张通常魔法卡加入手卡。",
              [{"field": {"0": {"hand": [100009309], "deck": [MOONBOOK, POT]}, "1": {}},
                "actions": [act(0, "activate", 100009309), chk("count", player=0, card=POT, **{"in": "hand"}, eq=1)]},
               {"field": {"0": {"hand": [100009309], "deck": [MOONBOOK]}, "1": {}},     # 只有速攻魔法：不能发动
                "actions": [chk("offered", card=100009309, **{"as": "activate"}, eq=False)]}],
              ("c:GetType()==TYPE_SPELL", "c:IsType(TYPE_SPELL)")))

for code, name, kind, effects, text in (
        (100009315, "处理测试·速攻", "spell",
         [{"id": "e1", "type": "activation", "do": [{"act": "add_to_hand", "what": {
             "who": "you", "where": ["deck"], "count": 1, "filter": [{"card_type": "spell"}, {"subtype": "quick"}]}}]}],
         "①：从卡组把1张速攻魔法卡加入手卡。"),
        (100009316, "处理测试·反击", "spell",
         [{"id": "e1", "type": "activation", "do": [{"act": "set_spell_trap", "what": {
             "who": "you", "where": ["grave"], "count": 1, "filter": [{"card_type": "trap"}, {"subtype": "counter"}]}}]}],
         "①：从自己墓地把1张反击陷阱卡在自己场上盖放。"),
        (100009311, "处理测试·定形", "monster",
         [{"id": "e1", "type": "ignition", "do": [{"act": "apply_continuous", "until": "end_of_turn",
                                                  "apply": {"cont": "cannot_change_position", "affects": SELF}}]}],
         "①：自己主要阶段才能发动。这个回合，这张卡不能把表示形式变更。"),
        (100009312, "处理测试·魔力", "monster",
         [{"id": "e1", "type": "ignition", "do": [{"act": "add_counter", "counter": "spell", "count": 1, "what": SELF,
                                                  "max": 2}]}],
         "①：自己主要阶段才能发动。给这张卡放置1个魔力指示物（最多2个）。"),
        (100009313, "处理测试·只能", "monster",
         [{"id": "e1", "type": "continuous",
           "apply": {"cont": "cannot_special_summon", "player": "you", "which": [{"not": {"race": "warrior"}}]}}],
         "①：只要这张卡在怪兽区域存在，自己不是战士族怪兽不能特殊召唤。"),
        (100009314, "处理测试·跳过", "spell",
         [{"id": "e1", "type": "activation", "do": [{"act": "apply_continuous", "until": {"next": "battle", "player": "opp"},
                                                    "apply": {"cont": "skip_phase", "player": "opp", "phase": "battle"}}]}],
         "①：下次的对方战斗阶段跳过。")):
    m, r = card(code, name, kind, effects, MONSTER if kind == "monster" else SPELL)
    CASES.append(("只查文字和加载：" + text.split("。")[-2], m, r, text, [], None))


def main():
    from effect_model import lint
    from sandbox.core import Core
    from sandbox.probe import load_check
    from sandbox.scenario import Runner
    from ygopack.cardinfo import token_records
    core = Core()
    bad = 0
    for label, model, rec, text, scenarios, mutation in CASES:
        built = build(model)
        errors = [m for lv, _, m in built["issues"] + lint(model) if lv == "error"]
        ok_text = built["desc"] == text
        core.add_card(rec)
        for token in token_records(model, rec["code"]):
            core.add_card(token)
        lua = built["lua"].encode("utf-8")
        loaded, errs = load_check(core, rec["code"], lua)
        notes = [] if loaded and not errs else ["引擎加载失败：%s" % ("；".join(errs) or "没有加载")]
        core.overrides = {rec["code"]: lua}
        for i, sc in enumerate(scenarios):
            runner = Runner(core, dict(sc, name="%s #%d" % (label, i + 1)))
            if not runner.run():
                notes.append("情景 %d 失败：%s" % (i + 1, "；".join(runner.failures)))
        if scenarios and mutation:
            old, new = mutation
            if old not in built["lua"]:
                notes.append("对照没找到要改的地方：%s" % old)
            else:
                core.overrides = {rec["code"]: built["lua"].replace(old, new, 1).encode("utf-8")}
                if all(Runner(core, dict(sc, name="对照")).run() for sc in scenarios):
                    notes.append("改坏的对照没有被查出")
        ok = ok_text and not errors and not notes
        bad += not ok
        print("%s  %s%s" % ("通过" if ok else "失败", label,
                           "（%d 个情景，改坏的对照被查出）" % len(scenarios) if ok and scenarios else ""))
        if not ok_text:
            print("      期望：%s\n      实际：%s" % (text.replace("\n", " / "), built["desc"].replace("\n", " / ")))
        for x in errors + notes:
            print("      " + x)
    print("工作台第二批：%s" % ("全部通过" if not bad else "%d 项失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
