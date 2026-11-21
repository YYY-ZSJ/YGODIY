"""核对整套卡片脚本。--bytecode 使用测试机的 lupa.lua54，无需在制卡器安装。"""

import argparse
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

from .. import SCHEMA, build
from ..compile import CompileError
from . import ScriptError, parse, render


CARD_FILE = re.compile(r"c(\d+)\.lua", re.I)


def sources(root):
    """主包和扩展中的每一份卡片脚本，保留重复卡号的不同版本。"""
    main = root / "Data" / "script.zip"
    if not main.is_file():
        raise FileNotFoundError(main)
    paths = (p for p in (root / "Expansions").rglob("*") if p.is_file())
    for path in [main, *sorted(paths)]:
        match = CARD_FILE.fullmatch(path.name)
        if match:
            yield path.relative_to(root).as_posix(), int(match[1]), path.read_bytes()
        elif path.suffix.lower() in {".zip", ".ypk", ".dey"} and zipfile.is_zipfile(path):
            label = path.relative_to(root).as_posix()
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    match = CARD_FILE.fullmatch(PurePosixPath(info.filename.replace("\\", "/")).name)
                    if match:
                        yield label, int(match[1]), archive.read(info)


def bytecode_checker():
    from lupa.lua54 import LuaRuntime
    from ._bytecode54 import executable_chunk
    lua = LuaRuntime(encoding=None)
    dump = lua.eval(b"function(s) local f,e=load(s,'=card','t',{}); if not f then error(e) end; return string.dump(f,true) end")
    return lambda source: executable_chunk(dump(source))


def verify(root, bytecode=False):
    dump = bytecode_checker() if bytecode else None
    seen, passed, failed = {}, set(), set()
    totals, errors = collections.Counter(), []
    for path, code, raw in sources(root):
        totals[path] += 1
        key = code, hashlib.sha256(raw).digest()
        if key in seen:
            continue
        try:
            source = raw.decode("utf-8-sig")
            tree = json.loads(json.dumps(parse(source, code), ensure_ascii=False))
            model = {"schema": SCHEMA, "card": {"code": code}, "effects": [tree]}
            built = build(model)
            if built["issues"]:
                raise ScriptError(str(built["issues"]))
            result = built["lua"]
            if dump:
                if dump(source.encode()) != dump(result.encode()):
                    raise ScriptError("Lua 指令、常量、闭包或上值不同")
            elif render(parse(result, code), code) != result:
                raise ScriptError("重新导入后生成结果不同")
        except (ValueError, RuntimeError, CompileError) as e:
            failed.add(code)
            errors.append((code, path, str(e)))
        else:
            passed.add(code)
        seen[key] = True
    return totals, len(seen), passed - failed, failed, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mdpro3", type=Path)
    ap.add_argument("--bytecode", action="store_true")
    args = ap.parse_args()
    totals, variants, passed, failed, errors = verify(args.mdpro3, args.bytecode)
    print("来源", dict(totals))
    print("脚本 %d 份，卡号及内容互异的版本 %d 份；全部版本通过的卡号 %d / %d；未通过 %d" %
          (sum(totals.values()), variants, len(passed), len(passed) + len(failed), len(failed)))
    print("核对项目", "去调试信息后的 Lua 5.4 可执行字节码" if args.bytecode else "重新导入与生成的稳定性")
    for code, path, err in errors:
        print(code, path, err)


if __name__ == "__main__":
    main()
