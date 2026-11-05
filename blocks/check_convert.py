"""旧存档转换的检查：effect_model/samples 里的 v0.2 样例卡逐张转换成 v0.3 积木树，
要能读成中文、翻译成 Lua、被引擎加载（测试沙盒），积木都放在对的槽里；没能完全转换的地方按次数汇总列出来。

用法（在 YGODIY_src 下）：python -m blocks.check_convert
"""

import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from blocks.compile import check, compile_card  # noqa: E402
from blocks.convert import convert  # noqa: E402
from blocks.read import read_full  # noqa: E402


def main():
    from sandbox.core import Core
    from sandbox.probe import load_check
    core = Core()
    bad, notes_by_kind = [], collections.Counter()
    paths = sorted(glob.glob(os.path.join(os.path.dirname(HERE), "effect_model", "samples", "*.json")))
    for i, p in enumerate(paths):
        name = os.path.basename(p)
        with open(p, encoding="utf-8") as f:
            model = json.load(f)
        out, notes = convert(model, model["card"]["kind"])
        # 用 DIY 卡号加载，免得和官方卡（同名卡、别名）的脚本混在一起
        card = dict(out, card=dict(model["card"], code=100000000 + i * 10))
        problems = check(card)
        try:
            lua = compile_card(card)
            desc, pdesc = read_full(card)
            loaded, errs = load_check(core, card["card"]["code"], lua.encode("utf-8"))
            if not loaded or errs:
                problems.append("引擎加载失败：%s" % ("；".join(errs) or "没有加载"))
            if card["effects"] and not (desc or pdesc):
                problems.append("读不出中文")
        except Exception as ex:
            problems.append("转换后生成失败：%r" % ex)
        if problems:
            bad.append(name)
        print("%s  %s（%d 个效果，%d 处没能完全转换）" % ("通过" if not problems else "失败", name, len(out["effects"]),
                                               len(notes)))
        for x in problems:
            print("      " + x)
        for n in notes:
            notes_by_kind[n.split("：", 1)[-1]] += 1
    print("没能完全转换的地方（按次数）：")
    for text, n in notes_by_kind.most_common():
        print("  %2d  %s" % (n, text))
    print("旧存档转换：%s" % ("全部通过（%d 张）" % len(paths) if not bad else "%d 张失败" % len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
