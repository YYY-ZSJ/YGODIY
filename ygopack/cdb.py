"""写 ygopro 的 cards.cdb（SQLite）。

经过 ygopack.sqlite：开发环境用标准库 sqlite3；YGODIY 打包的 Python 没有带 sqlite3 模块，
那时改用 Windows 10 起系统自带的 winsqlite3.dll，两条路写出的文件内容相同（自检里比对）。
"""

import os
import tempfile
from contextlib import closing

from . import sqlite

SCHEMA = [
    "CREATE TABLE datas(id integer primary key,ot integer,alias integer,setcode integer,type integer,atk integer,"
    "def integer,level integer,race integer,attribute integer,category integer)",
    "CREATE TABLE texts(id integer primary key,name text,desc text," + ",".join("str%d text" % i for i in range(1, 17)) + ")",
]
INSERT_DATA = "INSERT INTO datas VALUES(?,?,?,?,?,?,?,?,?,?,?)"
INSERT_TEXT = "INSERT INTO texts VALUES(" + ",".join(["?"] * 19) + ")"


def pack_setcode(codes):
    """最多 4 个字段，每个 16 位，拼成 cdb 的 setcode。"""
    value = 0
    for i, c in enumerate(codes[:4]):
        value |= (c & 0xffff) << (16 * i)
    # SQLite 的 INTEGER 是有符号 64 位，第四个字段可以占用符号位。
    return value - (1 << 64) if value >= 1 << 63 else value


def unpack_setcode(value):
    value = int(value or 0)
    return [part for shift in (0, 16, 32, 48) if (part := (value >> shift) & 0xffff)]


def rows(records):
    for r in records:
        strings = list(r.get("strings", []))[:16]
        strings += [""] * (16 - len(strings))
        yield (INSERT_DATA, (r["code"], r.get("ot", 3), r.get("alias", 0), pack_setcode(r.get("setcodes", [])),
                             r["type"], r["atk"], r["def"], r["level"], r["race"], r["attribute"], r.get("category", 0)))
        yield (INSERT_TEXT, (r["code"], r["name"], r["cdb_desc"], *strings))


def write(path, records, backend=None):
    """写 cdb，返回用的是哪条路（sqlite3 / winsqlite3）。backend 只在测试里用来指定。"""
    if os.path.exists(path):
        os.remove(path)
    old = sqlite.FORCE_CTYPES
    if backend:
        sqlite.FORCE_CTYPES = backend == "winsqlite3"
    try:
        used = sqlite.available_backend()
        con = sqlite.connect(path)
        try:
            for sql in SCHEMA:
                con.execute(sql)
            for sql, params in rows(records):
                con.execute(sql, params)
            con.commit()
        finally:
            con.close()
    finally:
        sqlite.FORCE_CTYPES = old
    return used


def read_cards(path):
    """标准 datas/texts 联表，读取全部卡片数据库字段。"""
    names = ("code", "ot", "alias", "setcode", "type", "atk", "def", "level", "race", "attribute", "category", "name", "desc")
    columns = ",".join("t.str%d" % n for n in range(1, 17))
    query = ("select d.id,d.ot,d.alias,d.setcode,d.type,d.atk,d.def,d.level,d.race,d.attribute,d.category,t.name,t.desc,"
             + columns + " from datas d join texts t on t.id=d.id order by d.id")
    with closing(sqlite.connect(path, readonly=True)) as connection:
        rows = connection.query(query)
    for row in rows:
        yield {"record": dict(zip(names, row)), "strings": {str(i): text for i, text in enumerate(row[len(names):]) if text},
               "script": "", "art": None, "media": {}}


def write_atomic(path, records):
    folder = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(dir=folder, suffix=".cdb", delete=False) as temp:
        name = temp.name
    try:
        write(name, records)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.remove(name)
