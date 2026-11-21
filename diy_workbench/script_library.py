"""按卡号读取玩家选择的本机实卡脚本和对应提示文字，只打开选中的资源。"""

from contextlib import closing
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from ygopack import sqlite
from ygopack.expansion import copy_database


def name_matches(root, term):
    db = root / "Data/locales/zh-CN/cards.cdb"
    if not db.is_file():
        return []
    with closing(sqlite.connect(db, readonly=True)) as conn:
        return conn.query("select id,name from texts where instr(name,?)>0 order by (name=?) desc,name,id limit 100",
                          (term, term))


def versions(root, code):
    name = "c%d.lua" % code
    result = []
    expansions = root / "Expansions"
    paths = [root / "Data/script.zip"]
    if expansions.is_dir():
        paths.extend(sorted(p for p in expansions.rglob("*") if p.is_file() and
                            (p.name.lower() == name or p.suffix.lower() in (".zip", ".ypk", ".dey"))))
    for path in paths:
        if path.name.lower() == name:
            result.append((path, None))
        elif path.is_file() and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as arc:
                result.extend((path, m) for m in arc.namelist() if PurePosixPath(m.replace("\\", "/")).name.lower() == name)
    return result


def _texts(path, code):
    if not path.is_file():
        return None
    with closing(sqlite.connect(path, readonly=True)) as conn:
        row = conn.query("select * from texts where id=?", (code,))
    if not row:
        return None
    _, _, desc, *strings = row[0]
    desc = (desc or "").replace("\r\n", "\n")
    parts = re.split(r"【怪兽效果】|\[怪兽效果\]", desc, maxsplit=1)
    pdesc = ""
    if len(parts) == 2:
        pdesc = re.sub(r"^\s*(?:【灵摆效果】|\[灵摆效果\])\s*", "", parts[0]).strip()
    return parts[-1].strip(), pdesc, strings[:16]


def read_version(root, version, code):
    path, member = version
    texts = None
    if member is None:
        data = path.read_bytes()
    else:
        with zipfile.ZipFile(path) as arc:
            data = arc.read(member)
            if path != root / "Data/script.zip":
                with tempfile.TemporaryDirectory() as folder:
                    temp = Path(folder) / "cards.cdb"
                    for name in arc.namelist():
                        if name.lower().endswith(".cdb"):
                            copy_database(arc, name, temp)
                            texts = _texts(temp, code)
                            if texts is not None:
                                break
    return data.decode("utf-8-sig"), texts or _texts(root / "Data/locales/zh-CN/cards.cdb", code)
