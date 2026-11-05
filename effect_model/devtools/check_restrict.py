"""自肃（restrict）的检查：文字照全卡库的多数写法，生成的 Lua 在沙盒里限制得对，改坏一处的对照能被查出。

官方卡里能完整表达的只有休战增援（样例和情景在 samples / scenarios 里，和官方脚本对照）；别的写法用到的卡，
其余效果还超出现有词汇，所以这里用 DIY 测试卡（卡号 1000091xx），只跑生成脚本：
    A  处理后：「这个效果的发动后，直到回合结束时自己不是机械族怪兽不能从额外卡组特殊召唤」（天轮之双星道士等 53 张的句式）
    B  整回合：「这个效果发动的回合，自己不是战士族怪兽不能特殊召唤」（电子龙三型等 66 张），发动前特召过就不能发动
    C  整回合：「这个效果发动的回合，这张卡不能攻击」（混沌巫师等 30 张），攻击过就不能发动
    D  「自己对「X」1回合只能有1次特殊召唤」（灵兽使 蕾拉等）
    E  卡的发动的整回合：「这个卡名的卡在1回合只能发动1张，这张卡发动的回合，自己不能把怪兽特殊召唤」（强欲而谦虚之壶）
    F  卡的发动的处理后：「这张卡的发动后，直到回合结束时自己不能从额外卡组把怪兽特殊召唤」（极寒冰柱）
    G  只查文字和加载：双方、直到下次的自己回合的结束时、几种限制并成一句

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.check_restrict
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import SCHEMA, build  # noqa: E402

DRAW = [{"act": "draw", "player": "you", "count": 1}]
MONSTER = {"type": 0x21, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 1000, "def": 1000}
SPELL = {"type": 0x2, "level": 0, "attribute": 0, "race": 0, "atk": 0, "def": 0}
LV4 = 549481             # 硬毛鼠：4星通常怪兽（兽族）
HOPE, NO27 = 84013237, 8387138      # 4阶超量：霍普（战士族）、No.27（机械族），都是「4星怪兽×2」
CD, BE = 70095154, 89631139         # 电子龙（只有对方场上有怪兽时从手卡特召，机械族）、青眼白龙


def card(code, name, kind, rec, effects, **more):
    model = {"schema": SCHEMA, "card": {"code": code, "name": name, "kind": kind,
                                        "subtypes": ["effect"] if kind == "monster" else ["normal"]},
             "effects": effects}
    model.update(more)
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

m, r = card(100009101, "自肃测试兵A", "monster", MONSTER, [
    {"id": "e1", "type": "ignition", "do": DRAW,
     "restrict": [{"span": "after_resolution", "forbid": ["special_summon"], "from": ["extra"],
                   "only": [{"race": "machine"}]}]}])
CASES.append(("A 处理后：不是机械族不能从额外卡组特殊召唤", m, r,
               "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果的发动后，直到回合结束时自己不是机械族怪兽不能从额外卡组特殊召唤。",
               [{"field": {"0": {"mzone": [100009101, LV4, LV4], "extra": [HOPE, NO27]}, "1": {}},
                 "actions": [chk("offered", card=HOPE, **{"as": "spsummon"}, eq=True),
                             act(0, "activate", 100009101),
                             chk("offered", card=HOPE, **{"as": "spsummon"}, eq=False),
                             chk("offered", card=NO27, **{"as": "spsummon"}, eq=True)]}],
               ("c:IsLocation(LOCATION_EXTRA) and not (c:IsRace(RACE_MACHINE))", "c:IsLocation(LOCATION_EXTRA)")))

m, r = card(100009102, "自肃测试兵B", "monster", MONSTER, [
    {"id": "e1", "type": "ignition", "do": DRAW,
     "restrict": [{"span": "whole_turn", "forbid": ["special_summon"], "only": [{"race": "warrior"}]}]}])
CASES.append(("B 整回合：不是战士族不能特殊召唤（发动前特召过就不能发动）", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果发动的回合，自己不是战士族怪兽不能特殊召唤。",
              [{"field": {"0": {"mzone": [100009102], "hand": [CD]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "activate", 100009102),
                            chk("offered", card=CD, **{"as": "spsummon"}, eq=False)]},
               {"field": {"0": {"hand": [CD], "grave": []}, "1": {"mzone": [BE]}},
                "actions": [act(0, "spsummon", CD),
                            chk("offered", card=100009102, **{"as": "activate"}, eq=False)]}],
              ("Duel.GetCustomActivityCount(id,tp,ACTIVITY_SPSUMMON)==0", "true")))
# B 的第二个情景：测试兵要在场上才能发动。电子龙特召需要自己场上没有怪兽，所以测试兵放手卡、再通常召唤
CASES[-1][4][1] = {"field": {"0": {"hand": [CD, 100009102]}, "1": {"mzone": [BE]}},
                   "actions": [act(0, "spsummon", CD), act(0, "summon", 100009102),
                               chk("offered", card=100009102, **{"as": "activate"}, eq=False)]}

m, r = card(100009103, "自肃测试兵C", "monster", MONSTER, [
    {"id": "e1", "type": "ignition", "limit": ["l1"],
     "do": [{"act": "apply_continuous", "until": "end_of_turn",
             "apply": {"cont": "atk_update", "affects": {"ref": "self"}, "value": 500}}],
     "restrict": [{"span": "whole_turn", "who": "self", "forbid": ["attack"]}]}],
    limits={"l1": {"scope": "card", "per": "turn", "n": 1}})
CASES.append(("C 整回合：这张卡不能攻击（攻击过就不能发动）", m, r,
              "①：1回合1次，自己主要阶段才能发动。这张卡的攻击力直到回合结束时上升500。这个效果发动的回合，这张卡不能攻击。",
              [{"field": {"0": {"mzone": [100009103]}, "1": {}},
                "actions": [act(0, "activate", 100009103), chk("atk", player=0, card=100009103, eq=1500),
                            act(0, "battle"), chk("offered", card=100009103, **{"as": "attack"}, eq=False)]},
               {"field": {"0": {"mzone": [100009103]}, "1": {}},
                "actions": [act(0, "battle"), act(0, "attack", 100009103), act(0, "main2"),
                            chk("offered", card=100009103, **{"as": "activate"}, eq=False)]}],
              ("e:GetHandler():GetAttackAnnouncedCount()==0", "true")))

m, r = card(100009104, "自肃测试兵D", "monster", MONSTER,
            [{"id": "e1", "type": "procedure", "range": ["hand"]}],
            summon={"restrictions": [{"special_summon_once": "turn"}]})
CASES.append(("D 自己对「X」1回合只能有1次特殊召唤", m, r,
              "自己对「自肃测试兵D」1回合只能有1次特殊召唤。\n①：这张卡可以从手卡特殊召唤。",
              [{"field": {"0": {"hand": [100009104, 100009104]}, "1": {}},
                "actions": [act(0, "spsummon", 100009104),
                            chk("offered", card=100009104, **{"as": "spsummon"}, eq=False),
                            chk("count", player=0, **{"in": "mzone"}, card=100009104, eq=1)]}],
              ("c:SetSPSummonOnce(id)", "-- c:SetSPSummonOnce(id)")))

m, r = card(100009105, "自肃测试魔法E", "spell", SPELL, [
    {"id": "e1", "type": "activation", "limit": ["l1"], "do": [{"act": "draw", "player": "you", "count": 2}],
     "restrict": [{"span": "whole_turn", "forbid": ["special_summon"]}]}],
    limits={"l1": {"scope": "name", "per": "turn", "n": 1, "unit": "activate_card"}})
CASES.append(("E 卡的发动的整回合：不能把怪兽特殊召唤（并进卡名次数行）", m, r,
              "这个卡名的卡在1回合只能发动1张，这张卡发动的回合，自己不能把怪兽特殊召唤。\n①：自己从卡组抽2张。",
              [{"field": {"0": {"hand": [100009105, CD]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "activate", 100009105),
                            chk("offered", card=CD, **{"as": "spsummon"}, eq=False)]},
               {"field": {"0": {"hand": [100009105, CD]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "spsummon", CD),
                            chk("offered", card=100009105, **{"as": "activate"}, eq=False)]}],
              ("Duel.GetActivityCount(tp,ACTIVITY_SPSUMMON)==0", "true")))

m, r = card(100009106, "自肃测试魔法F", "spell", SPELL, [
    {"id": "e1", "type": "activation", "do": DRAW,
     "restrict": [{"span": "after_resolution", "forbid": ["special_summon"], "from": ["extra"]}]}])
CASES.append(("F 卡的发动的处理后：不能从额外卡组把怪兽特殊召唤", m, r,
              "①：自己从卡组抽1张。这张卡的发动后，直到回合结束时自己不能从额外卡组把怪兽特殊召唤。",
              [{"field": {"0": {"mzone": [LV4, LV4], "hand": [100009106], "extra": [HOPE]}, "1": {}},
                "actions": [chk("offered", card=HOPE, **{"as": "spsummon"}, eq=True),
                            act(0, "activate", 100009106),
                            chk("offered", card=HOPE, **{"as": "spsummon"}, eq=False)]}],
              ("return c:IsLocation(LOCATION_EXTRA)", "return false")))

m, r = card(100009107, "自肃测试兵G", "monster", MONSTER, [
    {"id": "e1", "type": "ignition", "do": DRAW,
     "restrict": [{"span": "whole_turn", "forbid": ["special_summon", "battle_phase"], "only": [{"race": "dragon"}]},
                  {"span": "after_resolution", "who": "both", "forbid": ["special_summon"], "from": ["extra"],
                   "only": [{"attribute": "dark"}], "until": "end_of_next_turn"}]}])
CASES.append(("G 几种限制并成一句、双方、直到下次的自己回合的结束时（只查文字和加载）", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果发动的回合，自己不是龙族怪兽不能特殊召唤，不能进行战斗阶段。"
              "这个效果的发动后，直到下次的自己回合的结束时双方不是暗属性怪兽不能从额外卡组特殊召唤。", [], None))

# ---- 第二批（2026-10-30）：写法照本机卡库里的官方中文（大寒气、造反剧、共斗、左腕的代偿、强欲而金满之壶、灵摆停顿、
# 铁兽战线、No.72……），Lua 照这些卡的官方脚本
POT, ROTA, DORON = 55144522, 32807846, 756652      # 强欲之壶、增援、多隆（3星战士族）


def mon(code, name, restrict, do=DRAW):
    return card(code, name, "monster", MONSTER, [{"id": "e1", "type": "ignition", "do": do, "restrict": [restrict]}])


m, r = mon(100009111, "自肃测试兵H", {"span": "this_turn", "forbid": ["activate"], "kinds": "monster",
                                    "only": [{"attribute": "earth"}]})
CASES.append(("H 这个回合：不能把地属性以外的怪兽的效果发动", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个回合，自己不能把地属性以外的怪兽的效果发动。",
              [{"field": {"0": {"mzone": [100009111]}, "1": {}},
                "actions": [act(0, "activate", 100009111),
                            chk("offered", card=100009111, **{"as": "activate"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_ACTIVATE)", "SetCode(EFFECT_CANNOT_SSET)")))

m, r = mon(100009112, "自肃测试兵I", {"span": "this_turn", "forbid": ["attack"], "except": {"card": "self"}})
CASES.append(("I 这个回合：这张卡以外的自己怪兽不能攻击", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个回合，这张卡以外的自己怪兽不能攻击。",
              [{"field": {"0": {"mzone": [100009112, DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009112), act(0, "battle"),
                            chk("offered", card=DORON, **{"as": "attack"}, eq=False),
                            chk("offered", card=100009112, **{"as": "attack"}, eq=True)]}],
              ("return c:GetFieldID()~=e:GetLabel()", "return false")))

m, r = mon(100009113, "自肃测试兵J", {"span": "whole_turn", "forbid": ["attack"]})
CASES.append(("J 整回合：自己怪兽不能攻击宣言（攻击过就不能发动）", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果发动的回合，自己怪兽不能攻击宣言。",
              [{"field": {"0": {"mzone": [100009113, DORON]}, "1": {}},
                "actions": [act(0, "activate", 100009113), act(0, "battle"),
                            chk("offered", card=DORON, **{"as": "attack"}, eq=False)]},
               {"field": {"0": {"mzone": [100009113, DORON]}, "1": {}},
                "actions": [act(0, "battle"), act(0, "attack", DORON), act(0, "main2"),
                            chk("offered", card=100009113, **{"as": "activate"}, eq=False)]}],
              ("Duel.GetActivityCount(tp,ACTIVITY_ATTACK)==0", "true")))

m, r = mon(100009114, "自肃测试兵K", {"span": "this_turn", "forbid": ["set"], "kinds": "card"})
CASES.append(("K 这个回合：不能把卡盖放", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个回合，自己不能把卡盖放。",
              [{"field": {"0": {"mzone": [100009114], "hand": [POT]}, "1": {}},
                "actions": [chk("offered", card=POT, **{"as": "sset"}, eq=True), act(0, "activate", 100009114),
                            chk("offered", card=POT, **{"as": "sset"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_SSET)", "SetCode(EFFECT_CANNOT_DRAW)")))

m, r = mon(100009115, "自肃测试兵L", {"span": "after_resolution", "forbid": ["draw_by_effect"]})
CASES.append(("L 发动后：不能用卡的效果抽卡", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果的发动后，直到回合结束时自己不能用卡的效果抽卡。",
              [{"field": {"0": {"mzone": [100009115], "hand": [POT]}, "1": {}},
                "actions": [act(0, "activate", 100009115), chk("offered", card=POT, **{"as": "activate"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_DRAW)", "SetCode(EFFECT_CANNOT_SSET)")))

m, r = mon(100009116, "自肃测试兵M", {"span": "after_resolution", "forbid": ["search"]})
CASES.append(("M 发动后：不能用抽卡以外的方法从卡组把卡加入手卡", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果的发动后，直到回合结束时自己不能用抽卡以外的方法从卡组把卡加入手卡。",
              [{"field": {"0": {"mzone": [100009116], "hand": [ROTA], "deck": [LV4, DORON]}, "1": {}},
                "actions": [chk("offered", card=ROTA, **{"as": "activate"}, eq=True), act(0, "activate", 100009116),
                            chk("offered", card=ROTA, **{"as": "activate"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_TO_HAND)", "SetCode(EFFECT_CANNOT_SSET)")))

m, r = mon(100009117, "自肃测试兵N", {"span": "this_turn", "forbid": ["half_battle_damage"]})
CASES.append(("N 这个回合：对方受到的战斗伤害变成一半", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个回合，对方受到的战斗伤害变成一半。",
              [{"field": {"0": {"mzone": [100009117]}, "1": {}},
                "actions": [act(0, "activate", 100009117), act(0, "battle"), act(0, "attack", 100009117),
                            chk("lp", player=1, eq=7500)]}],
              ("SetValue(HALF_DAMAGE)", "SetValue(DOUBLE_DAMAGE)")))

m, r = mon(100009118, "自肃测试兵O", {"span": "after_resolution", "forbid": ["special_summon"], "from": ["deck", "extra"]})
CASES.append(("O 发动后：不能从卡组·额外卡组把怪兽特殊召唤", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个效果的发动后，直到回合结束时自己不能从卡组·额外卡组把怪兽特殊召唤。",
              [{"field": {"0": {"mzone": [100009118, LV4, LV4], "extra": [HOPE]}, "1": {}},
                "actions": [chk("offered", card=HOPE, **{"as": "spsummon"}, eq=True), act(0, "activate", 100009118),
                            chk("offered", card=HOPE, **{"as": "spsummon"}, eq=False)]}],
              ("c:IsLocation(LOCATION_DECK+LOCATION_EXTRA)", "c:IsLocation(LOCATION_DECK)")))

m, r = card(100009119, "自肃测试魔法P", "spell", SPELL, [
    {"id": "e1", "type": "activation", "do": DRAW,
     "restrict": [{"span": "whole_turn", "forbid": ["activate"], "kinds": "spell"}]}])
CASES.append(("P 卡的发动的整回合：不能把魔法卡发动（之前发动过就不能发动）", m, r,
              "这张卡发动的回合，自己不能把魔法卡发动。\n①：自己从卡组抽1张。",
              [{"field": {"0": {"hand": [100009119, POT]}, "1": {}},
                "actions": [act(0, "activate", 100009119), chk("offered", card=POT, **{"as": "activate"}, eq=False)]},
               {"field": {"0": {"hand": [100009119, POT]}, "1": {}},
                "actions": [act(0, "activate", POT), chk("offered", card=100009119, **{"as": "activate"}, eq=False)]}],
              ("Duel.GetCustomActivityCount(id,tp,ACTIVITY_CHAIN)==0", "true")))

m, r = mon(100009120, "自肃测试兵Q", {"span": "this_turn", "forbid": ["activate", "set"], "kinds": "spell_trap"})
CASES.append(("Q 这个回合：不能把魔法·陷阱卡的效果发动，不能盖放（大寒气式）", m, r,
              "①：自己主要阶段才能发动。自己从卡组抽1张。这个回合，自己不能把魔法·陷阱卡的效果发动，不能把魔法·陷阱卡盖放。",
              [{"field": {"0": {"mzone": [100009120], "hand": [POT]}, "1": {}},
                "actions": [act(0, "activate", 100009120), chk("offered", card=POT, **{"as": "activate"}, eq=False),
                            chk("offered", card=POT, **{"as": "sset"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_SSET)", "SetCode(EFFECT_CANNOT_MSET)")))

for code, name, restrict, text in (
        (100009121, "自肃测试兵R", {"span": "this_turn", "forbid": ["material"], "method": "link", "only": [{"race": "beast"}]},
         "这个回合，自己不是兽族怪兽不能作为连接素材。"),
        (100009122, "自肃测试兵S", {"span": "after_resolution", "forbid": ["direct_attack"], "except": {"card": "self"}},
         "这个效果的发动后，直到回合结束时这张卡以外的自己怪兽不能直接攻击。"),
        (100009123, "自肃测试兵T", {"span": "this_turn", "forbid": ["attack"], "only": [{"set": "魔导", "setcode": "0x106e"}]},
         "这个回合，自己不用「魔导」怪兽不能攻击。")):
    m, r = mon(code, name, restrict)
    CASES.append(("%s 只查文字和加载：%s" % (name[-1], text[:-1]), m, r, "①：自己主要阶段才能发动。自己从卡组抽1张。" + text, [], None))


def main():
    from effect_model import lint
    from sandbox.core import Core
    from sandbox.probe import load_check
    from sandbox.scenario import Runner
    core = Core()
    bad = 0
    for label, model, rec, text, scenarios, mutation in CASES:
        built = build(model)
        errors = [m for lv, _, m in built["issues"] + lint(model) if lv == "error"]
        ok_text = built["desc"] == text
        core.add_card(rec)
        lua = built["lua"].encode("utf-8")
        loaded, errs = load_check(core, rec["code"], lua)
        notes = [] if loaded and not errs else ["引擎加载失败：%s" % "；".join(errs) or "没有加载"]
        core.overrides = {rec["code"]: lua}
        for i, sc in enumerate(scenarios):
            runner = Runner(core, dict(sc, name="%s #%d" % (label, i + 1)))
            if not runner.run():
                notes.append("情景 %d 失败：%s" % (i + 1, "；".join(runner.failures)))
        if scenarios and mutation:
            # 对照：改坏一处，至少一个情景要失败，否则这些情景查不出这条自肃
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
    print("自肃：%s" % ("全部通过" if not bad else "%d 项失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
