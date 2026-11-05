"""导出卡包。

    python -m ygopack 清单.json                      # 导出到清单旁边，并用测试沙盒验证
    python -m ygopack 清单.json --install            # 验证通过后放进 MDPro3 的扩展目录（自动查找或自定义的）
    python -m ygopack 清单.json --out 目录 --no-verify
"""

import argparse
import os
import shutil
import sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from ygopack import build, mdpro3  # noqa: E402


def main():
    ap = argparse.ArgumentParser(prog="python -m ygopack", description="把 DIY 卡导出成 MDPro3 / ygopro 的扩展包")
    ap.add_argument("manifest", help="卡包清单（JSON）")
    ap.add_argument("--out", help="输出目录（默认：清单所在目录）")
    ap.add_argument("--assets", help="卡片数据用 _image_ref 引用卡图时的资源目录（默认：YGODIY 的「制卡器标签页资源」）")
    ap.add_argument("--no-verify", action="store_true", help="不用测试沙盒验证")
    ap.add_argument("--install", action="store_true", help="放进 MDPro3 的扩展目录")
    args = ap.parse_args()

    assets = args.assets or os.path.join(mdpro3.app_dir(), "制卡器标签页资源")
    md_dir, source = mdpro3.find_mdpro3()
    known = {}
    if md_dir:
        import json
        with open(args.manifest, encoding="utf-8") as f:
            stem = "ygodiy-" + build.slug(json.load(f).get("name") or "DIY") + ".ypk"
        known = build.known_codes(md_dir, skip_file=stem, expansions=mdpro3.expansions_dir()[0])
        print("对照的 MDPro3：%s（%s），已有卡号 %d 个" % (md_dir, source, len(known)))
    else:
        print("没有找到 MDPro3：不检查卡号是否和官方卡 / 其他扩展冲突")

    out, report = build.build(args.manifest, args.out, assets, known)
    for line in report.lines():
        print(line)
    if not out:
        print("有错误，没有导出")
        return 1
    print("已导出：%s" % out)

    if not args.no_verify:
        from ygopack.verify import verify
        manifest_dir = os.path.dirname(os.path.abspath(args.manifest))
        import json
        with open(args.manifest, encoding="utf-8") as f:
            scenarios = [os.path.join(manifest_dir, p) for p in json.load(f).get("scenarios", [])]
        ok, lines = verify(out, scenarios)
        print("—— 测试沙盒验证")
        for line in lines:
            print(line)
        if not ok:
            print("验证没有通过，没有安装")
            return 1

    if args.install:
        target, note = mdpro3.expansions_dir()
        if not target:
            print("不能安装：%s" % note)
            return 1
        os.makedirs(target, exist_ok=True)
        dest = os.path.join(target, os.path.basename(out))
        shutil.copyfile(out, dest)
        print("已放进 %s（%s）。MDPro3 要重启后才会读到新卡。" % (dest, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
