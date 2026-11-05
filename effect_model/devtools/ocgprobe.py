"""冒烟测试：每张样例卡的生成脚本都能被引擎加载、注册效果、做发动检查，没有 Lua 错误。

把被测卡放进手卡 / 场上 / 墓地 / 灵摆区域 / 额外卡组，推进到先攻玩家的主要阶段 1。期间引擎会执行
initial_effect，并对可发动的效果调用 condition、cost(chk=0)、target(chk=0)。
效果处理（operation）、诱发效果和连锁由情景测试负责：python -m effect_model.devtools.run_scenarios

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.ocgprobe
    python -m effect_model.devtools.ocgprobe --dump 目录     # 顺便把生成的 Lua 写出来
"""

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import load, build  # noqa: E402
from sandbox.core import Core  # noqa: E402
from sandbox.probe import load_check as probe  # noqa: E402

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", help="把生成的 Lua 写到这个目录")
    args = ap.parse_args()
    core = Core()

    # 对照：故意写坏的脚本，确认错误真的能被收集到、主要阶段真的做了发动检查
    broken_init = b"local s,id,o=GetID()\nfunction s.initial_effect(c)\n\tc:NoSuchMethod()\nend\n"
    broken_target = (b"local s,id,o=GetID()\nfunction s.initial_effect(c)\n\tlocal e1=Effect.CreateEffect(c)\n"
                     b"\te1:SetType(EFFECT_TYPE_ACTIVATE)\n\te1:SetCode(EVENT_FREE_CHAIN)\n\te1:SetTarget(s.tg)\n"
                     b"\tc:RegisterEffect(e1)\nend\nfunction s.tg(e,tp,eg,ep,ev,re,r,rp,chk)\n"
                     b"\tif chk==0 then return Duel.NoSuchFunction() end\nend\n")
    for label, script in (("initial_effect 出错", broken_init), ("发动检查时出错", broken_target)):
        _, errs = probe(core, 12580477, script)
        print("[对照] %s：错误 %d 条 %s" % (label, len(errs), errs[:1]))
        if not errs:
            print("!! 收不到错误，测试本身不可信")
            return 2

    samples = sorted(glob.glob(os.path.join(os.path.dirname(HERE), "samples", "*.json")))
    bad = 0
    print("%-24s %-10s %-10s" % ("卡", "官方脚本", "生成脚本"))
    for path in samples:
        model = load(path)
        code = model["card"]["code"]
        lua = build(model)["lua"]
        if args.dump:
            os.makedirs(args.dump, exist_ok=True)
            with open(os.path.join(args.dump, "c%d.lua" % code), "w", encoding="utf-8", newline="\n") as f:
                f.write(lua)
        o_loaded, o_errs = probe(core, code)
        with core.as_exported(code):
            g_loaded, g_errs = probe(core, code, lua.encode("utf-8"))
        row = core.cdb.get(code)
        bad += not (g_loaded and not g_errs)
        print("%-24s %-10s %-10s" % (
            model["card"]["name"],
            # 本地引擎见到 alias 就去加载那张卡的脚本：鹰身女郎1 的官方脚本在这里跑不起来
            ("错误%d%s" % (len(o_errs), "(alias)" if row and row[1] else "")) if o_errs
            else ("通过" if o_loaded else "未加载"),
            ("错误%d" % len(g_errs)) if g_errs else ("通过" if g_loaded else "未加载")))
        for e in g_errs:
            print("    ", e)
    print("生成脚本未通过：%d / %d" % (bad, len(samples)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
