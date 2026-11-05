"""全卡库回归：官方中文文本 → 模型（zh_parse）→ 文本（zh），和原文一致才算覆盖。

对象是离线卡库（百鸽）里全部有效果的卡的编号效果（「①：……」连同后面的 ● 行）。通常怪兽的风味文字、衍生物不算。
每个效果的结果是三种之一：
    一致      解析成功，渲染回去和原文逐字一致（另记「规范化后一致」：只差旧译法，见 EQUIV）
    读不出    解析失败：报告按片段种类（发动部分 / 条件 / 代价 / 对象 / 处理 / 永续……）和句式归类
    不一致    解析成功但渲染出来不同（解析器或渲染器有一边的措辞还没对上）
句式归类时把「」里的内容换成 X、数字换成 N，按出现的效果数排序——这就是补词汇的先后顺序。

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.regress_corpus                      # 统计并写报告 docs/全卡库回归.md
    python -m effect_model.devtools.regress_corpus --show 处理 30        # 另外打印某类读不出的前 30 种句式和例子
"""

import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import zh_parse  # noqa: E402
from ygopack import cardinfo, mdpro3  # noqa: E402

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
REPORT = os.path.join(os.path.dirname(HERE), "docs", "全卡库回归.md")

# 旧译法 → 现行写法：意思相同，只是年代不同。规范化后一致的单独计数，不和逐字一致混在一起。
EQUIV = [
    (re.compile(r"(召唤|反转)成功(的场合|时)"), r"\1\2"),
]


def abstract(s):
    s = re.sub(r"「[^「」]*(「[^「」]*」[^「」]*)*」", "「X」", s)
    return re.sub(r"\d+", "N", s)


def load_cards():
    path = os.path.join(mdpro3.app_dir(), "离线卡库", "cards.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for c in data.values():
        if not isinstance(c, dict) or "data" not in c or "text" not in c:
            continue
        t = c["data"]["type"]
        if (t & 0x10 and not t & 0x1000000) or t & 0x4000:      # 通常怪兽（非灵摆）、衍生物
            continue
        rec = {"code": c["id"], "name": c.get("cn_name") or c.get("sc_name") or "", "type": t}
        out.append(({"card": cardinfo.model_card(rec)}, c["text"]))
    return out


def effects_of(text):
    """一段卡文里的编号效果：[(编号后的文字, [● 行])]。"""
    out = []
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line[0] in CIRCLED and line[1:2] == "：":
            out.append([line[2:], []])
        elif line[0] == "●" and out:
            out[-1][1].append(line)
        elif out and out[-1][1]:
            out[-1][1].append(line)
    return out


def check(card, block, body, bullets):
    """返回 (结果, 片段种类, 片段, 详情)。"""
    norm = body
    for pat, rep in EQUIV:
        norm = pat.sub(rep, norm)
    try:
        eff, limits = zh_parse.parse_effect(norm, card, block, bullets)
    except zh_parse.ParseError as ex:
        return "读不出", ex.part, ex.fragment, None
    except Exception as ex:             # 解析器自己的毛病也要报出来，不让统计中断
        return "读不出", "解析器异常", "%s: %s" % (type(ex).__name__, ex), None
    try:
        text, bl = zh_parse.render_effect(eff, limits, card)
    except Exception as ex:
        return "不一致", "渲染失败", "%s: %s" % (type(ex).__name__, ex), eff
    if text == body and bl == list(bullets):
        return "一致", None, None, eff
    if text == norm and bl == list(bullets):
        return "规范化后一致", None, None, eff
    return "不一致", "渲染不同", text, eff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", nargs=2, metavar=("种类", "条数"))
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args()
    cards = load_cards()
    status = collections.Counter()
    fails = collections.defaultdict(collections.Counter)        # 种类 → 句式 → 效果数
    examples = collections.defaultdict(dict)                    # 种类 → 句式 → 例子
    mismatches = []
    card_ok = 0
    n_cards = 0
    for card, text in cards:
        effs = [(b, body, bl) for b, key in (("pendulum", "pdesc"), ("monster", "desc"))
                for body, bl in effects_of(text.get(key) or "")]
        if not effs:
            continue
        n_cards += 1
        all_ok = True
        for block, body, bullets in effs:
            result, part, frag, _ = check(card, block, body, bullets)
            status[result] += 1
            if result == "读不出":
                key = abstract(frag)
                fails[part][key] += 1
                examples[part].setdefault(key, "%s：%s" % (card["card"]["name"], body))
                all_ok = False
            elif result == "不一致":
                all_ok = False
                if len(mismatches) < 400:
                    mismatches.append((card["card"]["name"], body, frag))
        card_ok += all_ok
    total = sum(status.values())
    lines = ["# 全卡库回归（官方中文文本 → 模型 → 文本）", "",
             "由 `python -m effect_model.devtools.regress_corpus` 生成。对象：离线卡库（百鸽）里 %d 张有编号效果的卡，"
             "共 %d 个编号效果（连同 ● 行）。" % (n_cards, total), "",
             "| 结果 | 效果数 | 占比 |", "| --- | --- | --- |"]
    for k in ("一致", "规范化后一致", "不一致", "读不出"):
        lines.append("| %s | %d | %.1f%% |" % (k, status[k], 100.0 * status[k] / total))
    lines += ["", "整张卡的编号效果全部一致（含规范化后一致）：%d / %d 张（%.1f%%）。" % (card_ok, n_cards, 100.0 * card_ok / n_cards),
              "", "「规范化后一致」只差旧译法：%s。" % "；".join("「%s」→「%s」" % (p.pattern, r) for p, r in EQUIV), ""]
    lines += ["## 读不出的片段（按种类）", "", "| 种类 | 效果数 | 句式种数 |", "| --- | --- | --- |"]
    for part, ctr in sorted(fails.items(), key=lambda x: -sum(x[1].values())):
        lines.append("| %s | %d | %d |" % (part, sum(ctr.values()), len(ctr)))
    for part, ctr in sorted(fails.items(), key=lambda x: -sum(x[1].values())):
        lines += ["", "### %s：最常见的 40 种" % part, "", "| 效果数 | 句式 | 例子 |", "| --- | --- | --- |"]
        for key, n in ctr.most_common(40):
            ex = examples[part][key]
            lines.append("| %d | %s | %s |" % (n, key.replace("|", "｜"), ex[:80].replace("|", "｜")))
    lines += ["", "## 解析了但渲染不同（前 30 个）", "", "| 卡 | 原文 | 渲染 |", "| --- | --- | --- |"]
    for name, body, got in mismatches[:30]:
        lines.append("| %s | %s | %s |" % (name, body.replace("|", "｜"), (got or "").replace("|", "｜")))
    report = "\n".join(lines) + "\n"
    if not args.no_report:
        with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
    for k in ("一致", "规范化后一致", "不一致", "读不出"):
        print("%-8s %6d  %5.1f%%" % (k, status[k], 100.0 * status[k] / total))
    print("整张卡全部一致：%d / %d" % (card_ok, n_cards))
    for part, ctr in sorted(fails.items(), key=lambda x: -sum(x[1].values())):
        print("  读不出·%s：%d（%d 种句式）" % (part, sum(ctr.values()), len(ctr)))
    if args.show:
        part, n = args.show[0], int(args.show[1])
        if part == "不一致":
            for name, body, got in mismatches[:n]:
                print("\n%s\n  原文：%s\n  渲染：%s" % (name, body, got))
        else:
            for key, cnt in fails[part].most_common(n):
                print("%5d  %s\n       例：%s" % (cnt, key, examples[part][key][:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
