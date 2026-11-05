"""SQLite 读写的最小兼容层：有标准库 sqlite3 就用它，没有就用 ctypes 调 Windows 自带的 winsqlite3.dll。

YGODIY 打包的 Python 没有带 sqlite3 模块，导出卡包、测试沙盒读 cdb 都要经过这里。

    con = connect(path)            # 读写；readonly=True 只读
    rows = con.query("select id,name from texts where id=?", (code,))
    con.execute("insert into ...", params)
    con.commit(); con.close()
"""

import ctypes
import os

SQLITE_OK, SQLITE_ROW, SQLITE_DONE = 0, 100, 101
SQLITE_INTEGER, SQLITE_FLOAT, SQLITE_TEXT, SQLITE_BLOB, SQLITE_NULL = 1, 2, 3, 4, 5
OPEN_READONLY, OPEN_READWRITE, OPEN_CREATE = 0x1, 0x2, 0x4
TRANSIENT = ctypes.c_void_p(-1)

# 测试用：在有 sqlite3 的环境里也走 ctypes 这条路（环境变量 YGODIY_FORCE_WINSQLITE=1 等同于程序里的情况）
FORCE_CTYPES = bool(os.environ.get("YGODIY_FORCE_WINSQLITE"))


def available_backend():
    if not FORCE_CTYPES:
        try:
            import sqlite3  # noqa: F401
            return "sqlite3"
        except ImportError:
            pass
    return "winsqlite3"


def connect(path, readonly=False):
    if available_backend() == "sqlite3":
        return _StdConnection(path, readonly)
    return _CtypesConnection(path, readonly)


class _StdConnection:
    def __init__(self, path, readonly):
        import sqlite3
        uri = "file:%s?mode=ro" % path.replace("\\", "/") if readonly else path
        self._con = sqlite3.connect(uri, uri=readonly)

    def query(self, sql, params=()):
        return self._con.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        self._con.execute(sql, params)

    def commit(self):
        self._con.commit()

    def close(self):
        self._con.close()


_lib = None


def _load():
    global _lib
    if _lib is not None:
        return _lib
    last = None
    for name in ("winsqlite3.dll", "sqlite3.dll"):
        try:
            lib = ctypes.WinDLL(name)
            break
        except OSError as ex:
            last = ex
    else:
        raise OSError("找不到 SQLite（winsqlite3.dll）：%s" % last)
    P, I, L = ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong
    lib.sqlite3_open_v2.argtypes = [ctypes.c_char_p, ctypes.POINTER(P), I, ctypes.c_char_p]
    lib.sqlite3_prepare_v2.argtypes = [P, ctypes.c_char_p, I, ctypes.POINTER(P), P]
    lib.sqlite3_bind_text.argtypes = [P, I, ctypes.c_char_p, I, P]
    lib.sqlite3_bind_int64.argtypes = [P, I, L]
    lib.sqlite3_bind_double.argtypes = [P, I, ctypes.c_double]
    lib.sqlite3_bind_null.argtypes = [P, I]
    lib.sqlite3_step.argtypes = [P]
    lib.sqlite3_finalize.argtypes = [P]
    lib.sqlite3_close.argtypes = [P]
    lib.sqlite3_errmsg.argtypes = [P]
    lib.sqlite3_errmsg.restype = ctypes.c_char_p
    lib.sqlite3_column_count.argtypes = [P]
    lib.sqlite3_column_type.argtypes = [P, I]
    lib.sqlite3_column_int64.argtypes = [P, I]
    lib.sqlite3_column_int64.restype = L
    lib.sqlite3_column_double.argtypes = [P, I]
    lib.sqlite3_column_double.restype = ctypes.c_double
    lib.sqlite3_column_bytes.argtypes = [P, I]
    lib.sqlite3_column_blob.argtypes = [P, I]
    lib.sqlite3_column_blob.restype = P
    lib.sqlite3_column_text.argtypes = [P, I]
    lib.sqlite3_column_text.restype = P
    _lib = lib
    return lib


class _CtypesConnection:
    def __init__(self, path, readonly):
        self._lib = _load()
        self._db = ctypes.c_void_p()
        flags = OPEN_READONLY if readonly else OPEN_READWRITE | OPEN_CREATE
        if self._lib.sqlite3_open_v2(os.fsencode(path) if os.name != "nt" else path.encode("utf-8"),
                                     ctypes.byref(self._db), flags, None) != SQLITE_OK:
            raise OSError("SQLite 打不开 %s" % path)
        self._in_tx = False

    def _check(self, rc, want=SQLITE_OK):
        if rc != want:
            raise OSError("SQLite：%s" % self._lib.sqlite3_errmsg(self._db).decode("utf-8", "replace"))

    def _prepare(self, sql, params):
        lib = self._lib
        stmt = ctypes.c_void_p()
        self._check(lib.sqlite3_prepare_v2(self._db, sql.encode("utf-8"), -1, ctypes.byref(stmt), None))
        for i, p in enumerate(params, 1):
            if p is None:
                self._check(lib.sqlite3_bind_null(stmt, i))
            elif isinstance(p, str):
                data = p.encode("utf-8")
                self._check(lib.sqlite3_bind_text(stmt, i, data, len(data), TRANSIENT))
            elif isinstance(p, float):
                self._check(lib.sqlite3_bind_double(stmt, i, p))
            else:
                self._check(lib.sqlite3_bind_int64(stmt, i, int(p)))
        return stmt

    def query(self, sql, params=()):
        lib = self._lib
        stmt = self._prepare(sql, params)
        rows = []
        try:
            n = lib.sqlite3_column_count(stmt)
            while True:
                rc = lib.sqlite3_step(stmt)
                if rc == SQLITE_DONE:
                    break
                self._check(rc, SQLITE_ROW)
                row = []
                for i in range(n):
                    t = lib.sqlite3_column_type(stmt, i)
                    if t == SQLITE_INTEGER:
                        row.append(lib.sqlite3_column_int64(stmt, i))
                    elif t == SQLITE_FLOAT:
                        row.append(lib.sqlite3_column_double(stmt, i))
                    elif t == SQLITE_TEXT:
                        ptr = lib.sqlite3_column_text(stmt, i)
                        size = lib.sqlite3_column_bytes(stmt, i)
                        row.append(ctypes.string_at(ptr, size).decode("utf-8", "replace") if ptr else "")
                    elif t == SQLITE_BLOB:
                        ptr = lib.sqlite3_column_blob(stmt, i)
                        size = lib.sqlite3_column_bytes(stmt, i)
                        row.append(ctypes.string_at(ptr, size) if ptr else b"")
                    else:
                        row.append(None)
                rows.append(tuple(row))
        finally:
            lib.sqlite3_finalize(stmt)
        return rows

    def execute(self, sql, params=()):
        if not self._in_tx:
            self._run("BEGIN")
            self._in_tx = True
        self._run(sql, params)

    def _run(self, sql, params=()):
        stmt = self._prepare(sql, params)
        try:
            self._check(self._lib.sqlite3_step(stmt), SQLITE_DONE)
        finally:
            self._lib.sqlite3_finalize(stmt)

    def commit(self):
        if self._in_tx:
            self._run("COMMIT")
            self._in_tx = False

    def close(self):
        if self._db:
            self._lib.sqlite3_close(self._db)
            self._db = ctypes.c_void_p()
