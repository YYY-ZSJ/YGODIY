"""在 MDPro3 内核中分别加载原版及生成版，检查效果注册和发动条件。"""

import argparse
from collections import Counter
from pathlib import Path
import re
import zipfile

from sandbox.core import Core
from sandbox.probe import load_check
from .. import SCHEMA, build
from ..compile import CompileError
from . import parse
from .audit import sources


def diagnostic(result):
    loaded, messages = result
    return loaded, [re.sub(r"(?<=\]):\d+(?=:)", ":行", msg) for msg in messages]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mdpro3", type=Path)
    ap.add_argument("--start", type=int, default=0, help="从第几份脚本开始")
    ap.add_argument("--limit", type=int, help="本次核对多少份")
    args = ap.parse_args()
    root = args.mdpro3
    core = Core(str(root))
    for p in sorted((root / "Expansions").glob("*")):
        if p.is_file() and (p.suffix.lower() == ".cdb" or p.suffix.lower() in (".ypk", ".zip") and zipfile.is_zipfile(p)):
            core.add_expansion(str(p))
    counts = Counter()
    for index, (path, code, raw) in enumerate(sources(root)):
        if index < args.start:
            continue
        if args.limit is not None and index >= args.start + args.limit:
            break
        if code not in core.cdb:
            counts["本机卡库无卡片资料"] += 1
            continue
        try:
            model = {"schema": SCHEMA, "card": {"code": code}, "effects": [parse(raw.decode("utf-8-sig"), code)]}
            result = build(model)["lua"].encode()
        except (ValueError, CompileError) as ex:
            counts["未生成"] += 1
            print("未生成", path, code, str(ex), flush=True)
            continue
        with core.as_exported(code):
            before = load_check(core, code, raw)
            after = load_check(core, code, result)
        if before == (True, []) and after == (True, []):
            counts["两版加载通过"] += 1
        elif diagnostic(before) == diagnostic(after):
            counts["两版均未正常加载"] += 1
            print("两版均未正常加载", path, code, before, after, flush=True)
        else:
            counts["加载结果不同"] += 1
            print("加载结果不同", path, code, before, after, flush=True)
        if (index + 1) % 500 == 0:
            print("进度", index + 1, flush=True)
    print("合计", dict(counts), flush=True)
    return int(counts["加载结果不同"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
