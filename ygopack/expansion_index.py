"""已安装卡号和字段。缓存每个扩展文件的解析结果，增删、替换后按当前目录重新汇总。"""
import os
import tempfile
import zipfile
from contextlib import closing
from functools import lru_cache

from . import cdb, sqlite
from .expansion import archive_names, copy_database
from .string_names import read_names


def _read_database(path, codes, fields):
    with closing(sqlite.connect(path, readonly=True)) as connection:
        codes.update(row[0] for row in connection.query("select id from datas"))
        if "setcode" not in {column[1].lower() for column in connection.query("pragma table_info(datas)")}:
            return
        for (value,) in connection.query("select distinct setcode from datas"):
            for code in cdb.unpack_setcode(value):
                fields.setdefault("0x%x" % code, "")


@lru_cache(maxsize=128)
def _file_index(path, size, modified):
    codes, fields, counters = set(), {}, {}
    ext = os.path.splitext(path)[1].lower()
    if ext == ".conf":
        with open(path, encoding="utf-8-sig", errors="replace") as stream:
            names = read_names([stream.read()])
            fields.update(names["setnames"])
            counters.update(names["counters"])
    elif ext == ".cdb":
        _read_database(path, codes, fields)
    else:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as tmp:
            names = archive_names(archive)
            fields.update(names["setnames"])
            counters.update(names["counters"])
            database = os.path.join(tmp, "pack.cdb")
            for member in archive.namelist():
                if member.lower().endswith(".cdb"):
                    copy_database(archive, member, database)
                    try:
                        _read_database(database, codes, fields)
                    except (OSError, sqlite.DatabaseError, ValueError):
                        continue
    return codes, fields, counters


def installed_index(md_dir, expansions=None, skip_file=None, *, include_counters=False):
    codes, fields, counters = {}, {}, {}
    files = []
    if md_dir:
        files.append((os.path.join(md_dir, "Data", "locales", "zh-CN", "cards.cdb"), "官方卡"))
        expansions = expansions or os.path.join(md_dir, "Expansions")
    if expansions and os.path.isdir(expansions):
        for name in sorted(os.listdir(expansions)):
            if name.lower().endswith((".conf", ".cdb", ".ypk", ".zip")) and os.path.normcase(name) != os.path.normcase(skip_file or ""):
                files.append((os.path.join(expansions, name), "扩展 " + name))
    for path, source in files:
        try:
            stat = os.stat(path)
            ids, names, counter_names = _file_index(os.path.abspath(path), stat.st_size, stat.st_mtime_ns)
        except (OSError, sqlite.DatabaseError, zipfile.BadZipFile, ValueError, RuntimeError):
            continue
        for code in ids:
            codes.setdefault(code, source)
        if source != "官方卡":
            for code, name in names.items():
                if code not in fields or (name and not fields[code][0]):
                    fields[code] = (name, source)
            for code, name in counter_names.items():
                counters.setdefault(code, (name, source))
    return (codes, fields, counters) if include_counters else (codes, fields)
