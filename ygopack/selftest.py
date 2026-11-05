"""导出器自检：

1. YGODIY 卡片数据 → cdb 字段：用官方卡构造编辑器里的数据，转换结果逐字段对照 MDPro3 的官方 cdb；
2. 两种 cdb 写法（标准库 sqlite3 / 系统的 winsqlite3.dll）写出的内容完全相同；
3. 标签页里保存的真实卡片能转换，卡图能从「制卡器标签页资源」里找到。

    python -m ygopack.selftest
"""

import json
import os
import sqlite3
import sys
import tempfile

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ygopack import cardinfo, cdb, mdpro3  # noqa: E402

N8 = [False] * 8

# 编辑器里的写法：卡种、魔陷类型、种族、召唤方式、附加栏都是下拉框序号
CASES = {
    72270339: dict(name="黑魔女 迪亚贝尔斯塔尔", card_type=0, call_way=1, race=3, level=7, attribute="暗", ATK="2500", DEF="2000"),
    14558127: dict(name="灰流丽", card_type=0, call_way=1, extra1=2, race=5, level=3, attribute="炎", ATK="0", DEF="1800"),
    89631139: dict(name="青眼白龙", card_type=0, call_way=0, race=0, level=8, attribute="光", ATK="3000", DEF="2500"),
    84013237: dict(name="No.39 希望皇 霍普", card_type=0, call_way=5, race=1, rank=4, level=0, attribute="光", ATK="2500", DEF="2000"),
    44508094: dict(name="星尘龙", card_type=0, call_way=4, race=0, level=8, attribute="风", ATK="2500", DEF="2000"),
    1861629: dict(name="解码语者", card_type=0, call_way=7, race=22, attribute="暗", ATK="2300",
                  link_status=[False, True, False, False, False, True, False, True]),
    16178681: dict(name="异色眼灵摆龙", card_type=0, call_way=1, extra1=9, race=0, level=7, attribute="暗",
                   ATK="2500", DEF="2000", lb_level="4"),
    94415058: dict(name="星读之魔术师", card_type=0, call_way=1, extra1=9, race=3, level=5, attribute="暗",
                   ATK="1200", DEF="2400", lb_level="1"),
    12580477: dict(name="雷击", card_type=1, mt_type=0),
    24224830: dict(name="墓穴的指名者", card_type=1, mt_type=6),
    4542651: dict(name="混沌护盾", card_type=1, mt_type=1),
    10045474: dict(name="无限泡影", card_type=2, mt_type=0),
    41420027: dict(name="神之宣告", card_type=2, mt_type=5),
}
EFFECTFUL = {84013237, 44508094, 1861629}   # 额外卡组的效果怪兽：挂了 Effect Model 才会加 TYPE_EFFECT


def check_convert(mdpro3_dir):
    con = sqlite3.connect(os.path.join(mdpro3_dir, "Data", "locales", "zh-CN", "cards.cdb"))
    bad = 0
    for code, fields in CASES.items():
        data = {"extra1": 0, "extra2": 0, "link_status": N8, "effect_text": "", "lb_text": "", **fields}
        rec, _ = cardinfo.from_ygodiy(data, has_effects=code in EFFECTFUL)
        row = con.execute("select type,atk,def,level,race,attribute from datas where id=?", (code,)).fetchone()
        if row is None:
            print("跳过  %s（cdb 里没有）" % fields["name"])
            continue
        got = (rec["type"], rec["atk"], rec["def"], rec["level"], rec["race"], rec["attribute"])
        if rec["type"] & cardinfo.TYPE_SPELL or rec["type"] & cardinfo.TYPE_TRAP:
            got, row = got[:1], row[:1]
        ok = got == tuple(row)
        bad += not ok
        print("%s  %s%s" % ("一致" if ok else "不同", fields["name"], "" if ok else "：生成 %s，官方 %s" % (got, tuple(row))))
    con.close()
    return bad


def check_backends():
    recs = []
    for code, fields in list(CASES.items())[:4]:
        data = {"extra1": 0, "extra2": 0, "link_status": N8, "effect_text": "效果\n第二行", "lb_text": "", **fields}
        rec, _ = cardinfo.from_ygodiy(data)
        rec.update(code=code, setcodes=[0xa01, 0x19e], strings=["提示", "", "第三条"],
                   cdb_desc=cardinfo.ygopro_desc(rec, rec["desc"], rec.get("pdesc", "")))
        recs.append(rec)
    with tempfile.TemporaryDirectory() as tmp:
        dumps = []
        for backend in ("sqlite3", "winsqlite3"):
            path = os.path.join(tmp, backend + ".cdb")
            cdb.write(path, recs, backend=backend)
            con = sqlite3.connect(path)
            dumps.append(list(con.iterdump()))
            con.close()
    same = dumps[0] == dumps[1]
    print("%s  sqlite3 与 winsqlite3 写出的 cdb%s" % ("一致" if same else "不同", "" if same else "内容不同"))
    return not same


def check_real_tab():
    path = os.path.join(mdpro3.app_dir(), "制卡器标签页.json")
    if not os.path.exists(path):
        print("跳过  标签页（没有 %s）" % path)
        return 0
    with open(path, encoding="utf-8") as f:
        packs = json.load(f).get("packs", [])
    bad = 0
    for pack in packs:
        for tab in pack.get("tabs", []):
            data = tab.get("data") or {}
            try:
                rec, notes = cardinfo.from_ygodiy(data)
                img = cardinfo.card_image_bytes(data, os.path.join(mdpro3.app_dir(), "制卡器标签页资源"))
                print("通过  标签页里的「%s」：type=0x%x atk=%d def=%d level=%d，卡图 %s%s" % (
                    rec["name"], rec["type"], rec["atk"], rec["def"], rec["level"],
                    "%d 字节" % len(img) if img else "没找到", ("；" + "；".join(notes)) if notes else ""))
            except cardinfo.CardDataError as ex:
                bad += 1
                print("失败  标签页里的「%s」：%s" % (data.get("name"), ex))
    return bad


def check_pack_errors(known):
    """故意写坏的清单，导出器应该拦下来（错误）或提醒（提示）。"""
    from ygopack import build
    demo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo")
    with open(os.path.join(demo, "清单.json"), encoding="utf-8") as f:
        base = json.load(f)
    explorer = dict(base["cards"][0], card=os.path.join(demo, base["cards"][0]["card"]),
                    effect=os.path.join(demo, base["cards"][0]["effect"]), art=os.path.join(demo, base["cards"][0]["art"]))
    guard = dict(base["cards"][1], card=os.path.join(demo, base["cards"][1]["card"]))
    two_limits = {"schema": "ygodiy-effect/0.1", "effects": [
        {"type": "ignition", "limit": {"scope": "name"}, "do": [{"act": "draw", "count": 1}]},
        {"type": "ignition", "limit": {"scope": "name"}, "do": [{"act": "draw", "count": 1}]}]}
    cases = [
        ("卡号和官方卡冲突", [dict(explorer, code=12580477)], "错误", "已被"),
        ("卡号太大", [dict(explorer, code=300000000)], "错误", "太大"),
        ("包内卡号重复", [explorer, dict(guard, code=100001000)], "错误", "重复"),
        ("两个效果的计数代码撞上另一张卡", [dict(explorer, code=100002000, effect=two_limits),
                                          dict(guard, code=100002100)], "提示", "撞车"),
        ("字段没有起名字", [dict(explorer, setcodes=["0xa02"])], "提示", "没有在 setnames"),
    ]
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for title, cards, level, needle in cases:
            manifest = dict(base, cards=cards, scenarios=[])
            path = os.path.join(tmp, "清单.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False)
            out, report = build.build(path, tmp, None, known)
            hit = any(lv == level and needle in text for lv, _, text in report.items)
            if level == "错误":
                hit = hit and out is None
            bad += not hit
            print("%s  %s（应当%s）" % ("拦下" if hit else "漏掉", title, level))
    return bad


def check_setnames():
    """字段名在 MDPro3 里要有名字：示例包在三种读法下都通过；只带标准 conf 的旧式包在现在的 MDPro3 里应当被认出读不到。"""
    import zipfile
    from ygopack import build
    from ygopack.verify import setname_check
    demo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo", "清单.json")
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        out, report = build.build(demo, tmp, None, None)
        results = setname_check(out)
        ok = out is not None and not any(missing for _, missing in results)
        bad += not ok
        print("%s  示例包的字段名在 MDPro3 的各种读法下都有名字" % ("通过" if ok else "失败"))
        old = os.path.join(tmp, "old.ypk")
        with zipfile.ZipFile(out) as src, zipfile.ZipFile(old, "w") as dst:
            for n in src.namelist():
                if not n.endswith("-mdpro3.conf"):
                    dst.writestr(n, src.read(n))
        current = dict(setname_check(old))
        hit = bool(current["MDPro3 现在的版本（只收内容含 lflist 的 conf）"])
        bad += not hit
        print("%s  旧式包（只有标准 conf）在现在的 MDPro3 里读不到字段名" % ("认出" if hit else "漏掉"))
    return bad


def main():
    md, _ = mdpro3.find_mdpro3()
    bad = 0
    if md:
        bad += check_convert(md)
        from ygopack.build import known_codes
        bad += check_pack_errors(known_codes(md))
    else:
        print("跳过  对照官方 cdb（没有找到 MDPro3）")
    bad += check_backends()
    bad += check_setnames()
    bad += check_real_tab()
    print("自检%s" % ("通过" if not bad else "有 %d 项不通过" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
