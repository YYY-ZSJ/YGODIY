"""把样例卡生成的中文效果文本与离线卡库（百鸽）里的官方文本逐字比较。

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.check_text
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from effect_model import load, lint, zh  # noqa: E402

CARDS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),
                          "YGODIY_2.1.0", "离线卡库", "cards.json")


# 有意保留的差异：官方文本是旧译法或少数写法，生成器按全卡库的多数写法写
KNOWN = {
    27693363: "旧译法「特殊召唤成功的场合」，多数写「特殊召唤的场合」（874 对 486）",
    37742478: "①官方写「场上的表侧表示的这张卡回到手卡」，多数写「这张卡回到手卡」（70 对 2）",
    65681983: "官方写「这个回合中，」，效果无效化时多数写「这个回合，」（13 对 3）",
    91932350: "没有编号的旧式卡文",
}


def main():
    with open(CARDS_JSON, encoding="utf-8") as f:
        official = {v["id"]: v["text"] for v in json.load(f).values()}
    samples = sorted(glob.glob(os.path.join(os.path.dirname(HERE), "samples", "*.json")))
    same = known = bad = 0
    for path in samples:
        model = load(path)
        for level, where, msg in lint(model):
            print("  [%s] %s %s：%s" % (level, model["card"]["name"], where, msg))
        try:
            text = zh.render(model)
        except NotImplementedError as ex:
            print("出错  %s：%s" % (model["card"]["name"], ex))
            continue
        off = official[model["card"]["code"]]
        keys = ("desc", "pdesc")
        if "normal" in model["card"].get("subtypes", []):      # 通常怪兽的描述栏是怪兽描述，不由效果生成
            keys = ("pdesc",)
        diffs = [k for k in keys if text[k] != off[k].replace("\r", "")]
        if not diffs:
            same += 1
            print("一致  %s" % model["card"]["name"])
            continue
        code = model["card"]["code"]
        if code in KNOWN:
            known += 1
            print("已知  %s：%s" % (model["card"]["name"], KNOWN[code]))
            continue
        bad += 1
        print("不同  %s" % model["card"]["name"])
        for k in diffs:
            print("    生成：%s" % text[k].replace("\n", " / "))
            print("    官方：%s" % off[k].replace("\r", "").replace("\n", " / "))
    print("逐字一致：%d / %d，已知差异 %d，其他不同 %d" % (same, len(samples), known, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
