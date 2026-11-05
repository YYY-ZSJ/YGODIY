"""多次额度的检查：次数改成 2 时，中文写成官方的多次写法，生成的 Lua 在沙盒里正好能用 2 次、第 3 次不行。

官方卡里这几种多次写法都有，但用到它们的卡效果都超出现有词汇，所以这里用 DIY 测试卡（卡号 1000090xx），
只跑生成脚本：
    「1回合最多2次，」                       这张卡（No.15 机关傀儡-巨人杀手、蜂军风）
    「这个卡名的效果1回合可以使用最多2次。」   这个卡名（No.80 狂装霸王 狂想战曲王）
    「这个卡名的卡在1回合可以发动最多2张。」   卡的发动（杀手级调整曲同调）
    「……的方法的特殊召唤1回合可以有最多2次。」 特殊召唤手续（官方没有先例，按同一句式类推）

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.check_limits
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import SCHEMA, build  # noqa: E402

DRAW = [{"act": "draw", "player": "you", "count": 1}]
MONSTER = {"type": 0x21, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 1000, "def": 1000}
SPELL = {"type": 0x2, "level": 0, "attribute": 0, "race": 0, "atk": 0, "def": 0}


def card(code, name, kind, rec, effects, limits):
    model = {"schema": SCHEMA, "card": {"code": code, "name": name, "kind": kind,
                                        "subtypes": ["effect"] if kind == "monster" else ["normal"]},
             "effects": effects, "limits": limits}
    return model, dict(rec, code=code, name=name, alias=0, setcodes=[])


CASES = [
    # (说明, 模型, cdb 记录, 期望的中文, 情景)
    ("这张卡 1回合最多2次",) + card(
        100009001, "多次测试兵A", "monster", MONSTER,
        [{"id": "e1", "type": "ignition", "limit": ["l1"], "do": DRAW}],
        {"l1": {"scope": "card", "per": "turn", "n": 2}}) + (
        "①：1回合最多2次，自己主要阶段才能发动。自己从卡组抽1张。",
        {"field": {"0": {"mzone": [100009001]}, "1": {}},
         "actions": [{"mark": True}, {"player": 0, "do": "activate", "card": 100009001},
                     {"player": 0, "do": "activate", "card": 100009001},
                     {"check": "offered", "card": 100009001, "as": "activate", "eq": False},
                     {"check": "drawn", "player": 0, "eq": 2}]}),
    ("这个卡名 1回合可以使用最多2次（两张同名卡合计）",) + card(
        100009002, "多次测试兵B", "monster", MONSTER,
        [{"id": "e1", "type": "ignition", "limit": ["l1"], "do": DRAW}],
        {"l1": {"scope": "name", "per": "turn", "n": 2}}) + (
        "这个卡名的效果1回合可以使用最多2次。\n①：自己主要阶段才能发动。自己从卡组抽1张。",
        {"field": {"0": {"mzone": [100009002, 100009002]}, "1": {}},
         "actions": [{"mark": True}, {"player": 0, "do": "activate", "card": 100009002},
                     {"player": 0, "do": "activate", "card": 100009002, "nth": 1},
                     {"check": "offered", "card": 100009002, "as": "activate", "eq": False},
                     {"check": "drawn", "player": 0, "eq": 2}]}),
    ("这个卡名的卡 1回合可以发动最多2张",) + card(
        100009003, "多次测试魔法C", "spell", SPELL,
        [{"id": "e1", "type": "activation", "limit": ["l1"], "do": DRAW}],
        {"l1": {"scope": "name", "per": "turn", "n": 2, "unit": "activate_card"}}) + (
        "这个卡名的卡在1回合可以发动最多2张。\n①：自己从卡组抽1张。",
        {"field": {"0": {"hand": [100009003, 100009003, 100009003]}, "1": {}},
         "actions": [{"mark": True}, {"player": 0, "do": "activate", "card": 100009003},
                     {"player": 0, "do": "activate", "card": 100009003},
                     {"check": "offered", "card": 100009003, "as": "activate", "eq": False},
                     {"check": "drawn", "player": 0, "eq": 2}]}),
    ("特殊召唤手续 1回合可以有最多2次",) + card(
        100009004, "多次测试兵D", "monster", MONSTER,
        [{"id": "e1", "type": "procedure", "range": ["hand"], "limit": ["l1"]}],
        {"l1": {"scope": "name", "per": "turn", "n": 2, "unit": "procedure"}}) + (
        "这个卡名的①的方法的特殊召唤1回合可以有最多2次。\n①：这张卡可以从手卡特殊召唤。",
        {"field": {"0": {"hand": [100009004, 100009004, 100009004]}, "1": {}},
         "actions": [{"player": 0, "do": "spsummon", "card": 100009004},
                     {"player": 0, "do": "spsummon", "card": 100009004},
                     {"check": "offered", "card": 100009004, "as": "spsummon", "eq": False},
                     {"check": "count", "player": 0, "in": "mzone", "card": 100009004, "eq": 2}]}),
    ("两个效果次数不同",) + card(
        100009005, "多次测试兵E", "monster", MONSTER,
        [{"id": "e1", "type": "ignition", "limit": ["l1"], "do": DRAW},
         {"id": "e2", "type": "ignition", "limit": ["l2"], "cost": [{"act": "release", "what": {"ref": "self"}}],
          "do": DRAW}],
        {"l1": {"scope": "name", "per": "turn", "n": 2}, "l2": {"scope": "name", "per": "turn", "n": 1}}) + (
        "这个卡名的①的效果1回合可以使用最多2次，②的效果1回合只能使用1次。\n"
        "①：自己主要阶段才能发动。自己从卡组抽1张。\n②：把这张卡解放才能发动。自己从卡组抽1张。", None),
]


def main():
    from sandbox.core import Core
    from sandbox.scenario import Runner
    core = Core()
    bad = 0
    for label, model, rec, text, scenario in CASES:
        built = build(model)
        errors = [m for lv, _, m in built["issues"] if lv == "error"]
        ok_text = built["desc"] == text
        result = "（只查文字）"
        ok_run = True
        if scenario:
            core.add_card(rec)
            core.overrides = {rec["code"]: built["lua"].encode("utf-8")}
            runner = Runner(core, dict(scenario, name=label))
            ok_run = runner.run()
            result = "沙盒通过" if ok_run else "沙盒失败：" + "；".join(runner.failures)
            # 对照：脚本改回只能用 1 次，同一个情景必须失败，否则这个情景查不出次数
            one = built["lua"].replace("SetCountLimit(2", "SetCountLimit(1")
            core.overrides = {rec["code"]: one.encode("utf-8")}
            if one == built["lua"] or Runner(core, dict(scenario, name=label)).run():
                ok_run = False
                result += "；对照没有失败，情景查不出次数"
            else:
                result += "（改回 1 次的对照被查出）"
        ok = ok_text and ok_run and not errors
        bad += not ok
        print("%s  %s  %s" % ("通过" if ok else "失败", label, result))
        if not ok_text:
            print("      期望：%s\n      实际：%s" % (text.replace("\n", " / "), built["desc"].replace("\n", " / ")))
        for e in errors:
            print("      检查：%s" % e)
    print("多次额度：%s" % ("全部通过" if not bad else "%d 项失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
