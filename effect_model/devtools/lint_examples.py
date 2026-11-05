"""结构检查：15 张样例（v0.1，读入时升级）和 27 张 v0.2 压力卡样例都要没有错误；
再把样例故意改坏几处，确认 lint 能查出来。

    python -m effect_model.devtools.lint_examples
"""

import copy
import glob
import json
import os
import sys

from effect_model import lint

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def errors(card):
    return [(w, m) for level, w, m in lint(card) if level == "error"]


def stress_cards():
    with open(os.path.join(HERE, "docs", "v0.2-压力卡样例.json"), encoding="utf-8") as f:
        data = json.load(f)
    return [{k: v for k, v in c.items() if k != "difficulty"} for c in data["cards"]]


# (说明, 改坏的方法, 应该出现在报错里的字)
MUTATIONS = [
    ("星尘龙：去掉 keep，②引用不到「为①发动而解放的这张卡」", "星尘龙",
     lambda c: c["effects"][0]["cost"][0].pop("keep"), "e1.released"),
    ("暗道化师 彼得：去掉 timing", "暗道化师 彼得", lambda c: c["effects"][0].pop("timing"), "timing"),
    ("电子龙·无限：引用不存在的额度", "电子龙·无限", lambda c: c["effects"][1].__setitem__("limit", "l9"), "l9"),
    ("救援兔：动作写错", "救援兔", lambda c: c["effects"][0]["do"][0].__setitem__("act", "special_sumon"), "special_sumon"),
    ("技能抽取：持续内容写错", "技能抽取", lambda c: c["effects"][1]["apply"].__setitem__("cont", "negate_all"), "negate_all"),
    ("颉颃胜负：规则里的条件写错", "颉颃胜负", lambda c: c["rules"][0]["condition"][0].__setitem__("cond", "count"), "count"),
    ("暗黑界的取引：连接写错", "暗黑界的取引", lambda c: c["effects"][0]["do"][1].__setitem__("link", "after"), "after"),
    ("嵌合要塞龙：去掉素材后仍引用 materials", "嵌合要塞龙", lambda c: c.pop("summon"), "materials"),
    ("电子龙·无限：次数写成 0", "电子龙·无限", lambda c: next(iter(c["limits"].values())).__setitem__("n", 0), "次数"),
    ("替罪羊：自肃的动作写错", "替罪羊", lambda c: c["effects"][0]["restrict"][0]["forbid"].append("summmon"), "forbid"),
    ("替罪羊：「这张卡」不能特殊召唤", "替罪羊", lambda c: c["effects"][0]["restrict"][0].__setitem__("who", "self"), "who: self"),
]


def main():
    bad = 0
    # samples/ 是 v0.2；samples/v01/ 是升级前的 v0.1 原件，lint 时自动升级
    samples = sorted(glob.glob(os.path.join(HERE, "samples", "*.json")))
    v01 = sorted(glob.glob(os.path.join(HERE, "samples", "v01", "*.json")))
    for path in samples + v01:
        with open(path, encoding="utf-8") as f:
            errs = errors(json.load(f))
        if errs:
            bad += 1
            print("错误  %s：%s" % (os.path.basename(path), errs))
    cards = {c["card"]["name"]: c for c in stress_cards()}
    for name, card in cards.items():
        errs = errors(card)
        if errs:
            bad += 1
            print("错误  %s：%s" % (name, errs))
    print("样例 %d 张（另有 v0.1 原件 %d 张）、压力卡 %d 张：%s" % (
        len(samples), len(v01), len(cards), "没有错误" if not bad else "%d 张有错误" % bad))
    missed = 0
    for label, name, mutate, word in MUTATIONS:
        card = copy.deepcopy(cards[name])
        mutate(card)
        errs = errors(card)
        caught = any(word in w or word in m for w, m in errs)
        missed += not caught
        print("%s  %s" % ("检出" if caught else "漏检", label))
    print("变异漏检 %d / %d" % (missed, len(MUTATIONS)))
    return 1 if bad or missed else 0


if __name__ == "__main__":
    sys.exit(main())
