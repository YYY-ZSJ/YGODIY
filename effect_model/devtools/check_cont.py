"""永续效果第一批的检查：文字照全卡库的多数写法，生成的 Lua 在沙盒里效果对，改坏一处的对照能被查出。

能完整表达的官方卡（隼骑士、枪兵龙人、暗黑共鸣者、朱罗纪单脊龙）的样例和情景在 samples / scenarios 里，和官方脚本对照；
其余各项用到的官方卡还有别的效果超出现有词汇，所以这里用 DIY 测试卡（卡号 1000092xx），只跑生成脚本。

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.check_cont
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import SCHEMA, build  # noqa: E402

SELF = {"ref": "self"}
MONSTER = {"type": 0x21, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 1000, "def": 1000}
NORMAL = {"type": 0x11, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 1000, "def": 1000}
DORON, LV4, BE, RAIGEKI = 756652, 549481, 89631139, 12580477   # 多隆（战士族 900/500）、硬毛鼠（4星）
HOPE, IMPERM, VAULT = 84013237, 10045474, 75500286              # 霍普（4阶）、无限泡影、封印之黄金柜


def cont(code, name, aps, label_rec=MONSTER, **more):
    eff = {"id": "e1", "type": "continuous", "apply": aps if len(aps) > 1 else aps[0]}
    model = {"schema": SCHEMA, "card": {"code": code, "name": name, "kind": "monster", "subtypes": ["effect"]},
             "effects": [eff]}
    model.update(more)
    return model, dict(label_rec, code=code, name=name, alias=0, setcodes=[])


def act(p, do, c=None, **kw):
    a = {"player": p, "do": do}
    if c is not None:
        a["card"] = c
    a.update(kw)
    return a


def chk(kind, **kw):
    return dict({"check": kind}, **kw)


def mz(n=1):
    return {"in": "mzone"}


CASES = []

m, r = cont(100009201, "永续测试兵P", [{"cont": "atk_update", "affects": SELF, "value": 500},
                                     {"cont": "def_update", "affects": SELF, "value": 500}])
CASES.append(("攻击力·守备力上升（这张卡）", m, r, "①：这张卡的攻击力·守备力上升500。",
              [{"field": {"0": {"mzone": [100009201]}, "1": {}},
                "actions": [chk("atk", card=100009201, eq=1500), chk("def", card=100009201, eq=1500)]}],
              ("SetCode(EFFECT_UPDATE_DEFENSE)", "SetCode(EFFECT_UPDATE_ATTACK)")))

warriors = {"who": "you", "where": ["mzone"], "filter": [{"race": "warrior"}]}
m, r = cont(100009202, "永续测试兵P2", [{"cont": "atk_update", "affects": warriors, "value": 300},
                                      {"cont": "def_update", "affects": warriors, "value": 300}])
CASES.append(("攻击力·守备力上升（自己场上的战士族怪兽）", m, r,
              "①：只要这张卡在怪兽区域存在，自己场上的战士族怪兽的攻击力·守备力上升300。",
              [{"field": {"0": {"mzone": [100009202, DORON]}, "1": {"mzone": [DORON]}},
                "actions": [chk("atk", player=0, card=DORON, eq=1200), chk("def", player=0, card=DORON, eq=800),
                            chk("atk", player=1, card=DORON, eq=900)]}],
              ("SetTargetRange(LOCATION_MZONE,0)", "SetTargetRange(0,LOCATION_MZONE)")))

m, r = cont(100009203, "永续测试兵Q", [{"cont": "change_level", "affects": SELF, "value": 2}])
CASES.append(("等级上升", m, r, "①：这张卡的等级上升2星。",
              [{"field": {"0": {"mzone": [100009203]}, "1": {}}, "actions": [chk("level", card=100009203, eq=6)]}],
              ("SetValue(2)", "SetValue(1)")))

m, r = cont(100009204, "永续测试兵R", [{"cont": "indestructible_battle", "affects": SELF},
                                     {"cont": "indestructible_effect", "affects": SELF}])
CASES.append(("不会被战斗·效果破坏", m, r, "①：这张卡不会被战斗·效果破坏。",
              [{"field": {"0": {"mzone": [100009204]}, "1": {"mzone": [BE], "hand": [RAIGEKI]}},
                "actions": [act(0, "end_turn"), act(1, "activate", RAIGEKI),
                            chk("count", player=0, card=100009204, **mz(), eq=1),
                            act(1, "battle"), act(1, "attack", BE, target=100009204),
                            chk("count", player=0, card=100009204, **mz(), eq=1),
                            chk("lp", player=0, eq=6000)]}],      # 不会被战斗破坏不等于不受战斗伤害
              ("SetCode(EFFECT_INDESTRUCTABLE_EFFECT)", "SetCode(EFFECT_DIRECT_ATTACK)")))

m, r = cont(100009205, "永续测试兵S", [{"cont": "cannot_be_targeted", "affects": SELF, "by": "opp"},
                                     {"cont": "indestructible_effect", "affects": SELF, "by": "opp"}])
CASES.append(("不会成为对方的效果的对象，不会被对方的效果破坏", m, r,
              "①：场上的这张卡不会成为对方的效果的对象，不会被对方的效果破坏。",
              [{"field": {"0": {"mzone": [100009205], "hand": [VAULT]}, "1": {"szone": [IMPERM]}},
                "actions": [act(0, "activate", VAULT),
                            chk("offered", player=1, card=IMPERM, **{"as": "chain"}, eq=False)]},
               {"field": {"0": {"mzone": [100009205]}, "1": {"hand": [RAIGEKI]}},
                "actions": [act(0, "end_turn"), act(1, "activate", RAIGEKI),
                            chk("count", player=0, card=100009205, **mz(), eq=1)]}],
              ("SetCode(EFFECT_CANNOT_BE_EFFECT_TARGET)", "SetCode(EFFECT_PIERCE)")))

m, r = cont(100009206, "永续测试兵U", [{"cont": "direct_attack", "affects": SELF}])
CASES.append(("可以直接攻击", m, r, "①：这张卡可以直接攻击。",
              [{"field": {"0": {"mzone": [100009206]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "battle"), act(0, "attack", 100009206), chk("lp", player=1, eq=7000)]}],
              ("SetCode(EFFECT_DIRECT_ATTACK)", "SetCode(EFFECT_PIERCE)")))

m, r = cont(100009207, "永续测试兵V", [{"cont": "cannot_direct_attack", "affects": SELF}])
CASES.append(("不能直接攻击", m, r, "①：这张卡不能直接攻击。",
              [{"field": {"0": {"mzone": [100009207]}, "1": {}},
                "actions": [act(0, "battle"), chk("offered", card=100009207, **{"as": "attack"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_DIRECT_ATTACK)", "SetCode(EFFECT_PIERCE)")))

m, r = cont(100009208, "永续测试兵W", [{"cont": "cannot_be_attack_target", "affects": SELF}])
CASES.append(("对方怪兽不能选择这张卡作为攻击对象", m, r, "①：对方怪兽不能选择这张卡作为攻击对象。",
              [{"field": {"0": {"mzone": [100009208, DORON]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "end_turn"), act(1, "battle"), act(1, "attack", BE),
                            chk("count", player=0, card=100009208, **mz(), eq=1),
                            chk("count", player=0, card=DORON, **{"in": "grave"}, eq=1)]}],
              ("SetCode(EFFECT_CANNOT_BE_BATTLE_TARGET)", "SetCode(EFFECT_PIERCE)")))

m, r = cont(100009209, "永续测试兵X", [{"cont": "attack_target_restriction", "only": SELF}])
CASES.append(("对方不能选择其他怪兽作为攻击对象", m, r, "①：只要这张卡在怪兽区域存在，对方不能选择其他怪兽作为攻击对象。",
              [{"field": {"0": {"mzone": [DORON, 100009209]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "end_turn"), act(1, "battle"), act(1, "attack", BE),
                            chk("count", player=0, card=DORON, **mz(), eq=1),
                            chk("count", player=0, card=100009209, **{"in": "grave"}, eq=1)]}],
              ("SetCode(EFFECT_CANNOT_SELECT_BATTLE_TARGET)", "SetCode(EFFECT_PIERCE)")))

m = {"schema": SCHEMA, "card": {"code": 100009210, "name": "永续测试兵Y", "kind": "monster", "subtypes": ["effect"]},
     "summon": {"restrictions": [{"cannot_be_material": "xyz"}]}, "effects": []}
r = dict(MONSTER, code=100009210, name="永续测试兵Y", alias=0, setcodes=[])
CASES.append(("不能作为超量素材", m, r, "这张卡不能作为超量素材。",
              [{"field": {"0": {"mzone": [100009210, LV4], "extra": [HOPE]}, "1": {}},
                "actions": [chk("offered", card=HOPE, **{"as": "spsummon"}, eq=False)]}],
              ("SetCode(EFFECT_CANNOT_BE_XYZ_MATERIAL)", "SetCode(EFFECT_PIERCE)")))

m = {"schema": SCHEMA, "card": {"code": 100009211, "name": "永续测试兵Z", "kind": "monster", "subtypes": ["effect"]},
     "effects": [{"id": "e1", "type": "ignition",
                  "target": [{"as": "t1", "sel": {"who": "you", "where": ["mzone"], "count": 1}}],
                  "do": [{"act": "apply_continuous", "until": "end_of_turn",
                          "apply": [{"cont": "indestructible_battle", "affects": {"ref": "t1"}},
                                    {"cont": "indestructible_effect", "affects": {"ref": "t1"}}]}]}]}
r = dict(MONSTER, code=100009211, name="永续测试兵Z", alias=0, setcodes=[])
CASES.append(("处理中：这个回合，那只怪兽不会被战斗·效果破坏", m, r,
              "①：以自己场上1只怪兽为对象才能发动。这个回合，那只怪兽不会被战斗·效果破坏。",
              [{"field": {"0": {"mzone": [100009211, DORON]}, "1": {"mzone": [BE]}},
                "actions": [act(0, "activate", 100009211), act(0, "select", cards=[DORON]),
                            act(0, "battle"), act(0, "attack", DORON, target=BE),
                            chk("count", player=0, card=DORON, **mz(), eq=1), chk("lp", player=0, eq=5900)]}],
              ("SetCode(EFFECT_INDESTRUCTABLE_BATTLE)", "SetCode(EFFECT_PIERCE)")))

for code, name, aps, text in (
        (100009212, "永续测试兵T1", [{"cont": "change_level", "affects": SELF, "set": 1}], "①：这张卡的等级变成1星。"),
        (100009213, "永续测试兵T2", [{"cont": "indestructible_count", "affects": SELF, "by": ["battle"], "n": 2}],
         "①：这张卡1回合最多2次不会被战斗破坏。"),
        (100009214, "永续测试兵T3", [{"cont": "def_update", "affects": SELF, "value": -300}], "①：这张卡的守备力下降300。"),
        (100009215, "永续测试兵T4", [{"cont": "extra_attack", "affects": SELF, "n": 3}],
         "①：这张卡在同1次的战斗阶段中可以作3次攻击。"),
        (100009216, "永续测试兵T5", [{"cont": "indestructible_battle", "affects": SELF}], "①：这张卡不会被战斗破坏。"),
        (100009217, "永续测试兵T6", [{"cont": "indestructible_effect", "affects": SELF}], "①：场上的这张卡不会被效果破坏。"),
        (100009218, "永续测试兵T7", [{"cont": "cannot_be_targeted", "affects": SELF}], "①：场上的这张卡不会成为效果的对象。"),
        (100009219, "永续测试兵T8", [{"cont": "piercing", "affects": SELF}, {"cont": "direct_attack", "affects": SELF}],
         "①：这张卡向守备表示怪兽攻击的场合，给与攻击力超过那个守备力的数值的战斗伤害，这张卡可以直接攻击。")):
    m, r = cont(code, name, aps)
    CASES.append(("只查文字和加载：" + text[2:-1], m, r, text, [], None))


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
    print("永续第一批：%s" % ("全部通过" if not bad else "%d 项失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
