"""ygopro-core 的 Python 绑定（ctypes）。

目前直接用 MDPro3 自带的 ocgcore.dll、script.zip 和 cards.cdb——它们与导出卡包后实际对战的环境完全一致。
以后换成 YGODIY 自己 fork 的 ygopro-core，只需要改这里的路径。

引擎通过三个回调向宿主要数据：读脚本、读卡片资料、报告消息（脚本错误）。
这三个回调是 DLL 全局的，所以一个进程里只能有一个 Core。
"""

import contextlib
import ctypes
import os
import zipfile

def default_mdpro3():
    """本机 MDPro3 的安装目录（与导出卡包用同一套查找：环境变量、快捷方式、注册表、硬盘扫描）。"""
    from ygopack.mdpro3 import find_mdpro3
    path, _ = find_mdpro3()
    if not path:
        raise FileNotFoundError("没有找到 MDPro3；可以设环境变量 YGODIY_MDPRO3 指向它的安装目录")
    return path

TYPE_LINK = 0x4000000


class CardData(ctypes.Structure):
    _fields_ = [("code", ctypes.c_uint32), ("alias", ctypes.c_uint32), ("setcode", ctypes.c_uint16 * 16),
                ("type", ctypes.c_uint32), ("level", ctypes.c_uint32), ("attribute", ctypes.c_uint32),
                ("race", ctypes.c_uint32), ("attack", ctypes.c_int32), ("defense", ctypes.c_int32),
                ("lscale", ctypes.c_uint32), ("rscale", ctypes.c_uint32), ("link_marker", ctypes.c_uint32)]


SCRIPT_READER = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int))
CARD_READER = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(CardData))
MESSAGE_HANDLER = ctypes.CFUNCTYPE(ctypes.c_uint32, ctypes.c_ssize_t, ctypes.c_uint32)

_instance = None


class Core:
    def __init__(self, mdpro3=None):
        global _instance
        if _instance is not None:
            raise RuntimeError("一个进程里只能有一个 Core（引擎的回调是全局的）")
        mdpro3 = mdpro3 or default_mdpro3()
        self.dll = ctypes.CDLL(os.path.join(mdpro3, "MDPro3_Data", "Plugins", "x86_64", "ocgcore.dll"))
        d = self.dll
        P = ctypes.c_ssize_t
        d.create_duel.argtypes, d.create_duel.restype = [ctypes.c_uint32], P
        d.set_player_info.argtypes = [P] + [ctypes.c_int32] * 4
        d.start_duel.argtypes = [P, ctypes.c_uint32]
        d.end_duel.argtypes = [P]
        d.process.argtypes, d.process.restype = [P], ctypes.c_uint32
        d.get_message.argtypes, d.get_message.restype = [P, ctypes.c_char_p], ctypes.c_int32
        d.get_log_message.argtypes = [P, ctypes.c_char_p]
        d.set_responsei.argtypes = [P, ctypes.c_int32]
        d.set_responseb.argtypes = [P, ctypes.c_char_p]
        d.preload_script.argtypes, d.preload_script.restype = [P, ctypes.c_char_p], ctypes.c_int32
        d.query_field_card.argtypes = [P, ctypes.c_uint8, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_int32]
        d.query_field_card.restype = ctypes.c_int32

        self.zip = zipfile.ZipFile(os.path.join(mdpro3, "Data", "script.zip"))
        self.cdb, self.names = {}, {}
        from ygopack import sqlite
        con = sqlite.connect(os.path.join(mdpro3, "Data", "locales", "zh-CN", "cards.cdb"), readonly=True)
        for row in con.query("select id,alias,setcode,type,level,attribute,race,atk,def from datas"):
            self.cdb[row[0]] = row
        for code, name in con.query("select id,name from texts"):
            self.names[code] = name
        con.close()

        self.overrides = {}   # 卡号 → 脚本源码（bytes），优先于一切
        self.pack_scripts = {}  # 扩展包里的脚本：文件名 → 源码，优先于 script.zip（与 MDPro3 相同）
        self.virtual = {}     # 脚本名 → 源码（bytes），用于摆场脚本等
        self.requested = set()
        self.errors = []
        self._buffers = {}
        self._logbuf = ctypes.create_string_buffer(4096)
        self._cbs = (SCRIPT_READER(self._read_script), CARD_READER(self._read_card),
                     MESSAGE_HANDLER(self._handle_message))
        d.set_script_reader(self._cbs[0])
        d.set_card_reader(self._cbs[1])
        d.set_message_handler(self._cbs[2])
        _instance = self

    def add_expansion(self, path):
        """像 MDPro3 一样加载扩展：.ypk / .zip 里的 .cdb 与 script/，或单独的 .cdb。返回加载到的卡号。"""
        import tempfile
        codes = []

        def load_cdb(file):
            from ygopack import sqlite
            con = sqlite.connect(file, readonly=True)
            for row in con.query("select id,alias,setcode,type,level,attribute,race,atk,def from datas"):
                self.cdb[row[0]] = row
                codes.append(row[0])
            for code, name in con.query("select id,name from texts"):
                self.names[code] = name
            con.close()

        if path.lower().endswith(".cdb"):
            load_cdb(path)
            return codes
        with zipfile.ZipFile(path) as z:
            for entry in z.namelist():
                low = entry.lower()
                if low.endswith(".cdb"):
                    with tempfile.TemporaryDirectory() as tmp:
                        load_cdb(z.extract(entry, tmp))
                elif low.startswith("script/") and low.endswith(".lua"):
                    self.pack_scripts[os.path.basename(entry)] = z.read(entry)
        return codes

    def add_card(self, rec):
        """临时加入一张还没进任何 cdb 的卡（DIY 工作台检查单张卡时用）。rec 是 ygopack 的 cdb 记录。"""
        from ygopack.cdb import pack_setcode
        self.cdb[rec["code"]] = (rec["code"], rec.get("alias", 0), pack_setcode(rec.get("setcodes", [])), rec["type"],
                                 rec["level"], rec["attribute"], rec["race"], rec["atk"], rec["def"])
        self.names[rec["code"]] = rec["name"]

    @contextlib.contextmanager
    def as_exported(self, code):
        """照导出卡包后的样子去掉官方卡库里这张卡的 alias（ygopack 总写 0，规则同名写在脚本里）。

        MDPro3 带的引擎见到 alias 就去加载那张卡的脚本：鹰身女郎1（alias 鹰身女郎）的官方脚本在这里跑不起来，
        测生成脚本时必须先去掉。"""
        row = self.cdb.get(code)
        if row and row[1]:
            self.cdb[code] = row[:1] + (0,) + row[2:]
        try:
            yield
        finally:
            if row:
                self.cdb[code] = row

    def name(self, code):
        return self.names.get(code, str(code))

    def card_type(self, code):
        row = self.cdb.get(code)
        return row[3] if row else 0

    # ------------------------------------------------------------ 回调

    def _read_script(self, name, plen):
        name = name.decode()
        base = os.path.basename(name)
        data = self.virtual.get(base)
        if data is None and base.startswith("c") and base[1:-4].isdigit():
            code = int(base[1:-4])
            self.requested.add(code)
            data = self.overrides.get(code)
        if data is None:
            data = self.pack_scripts.get(base)
        if data is None:
            try:
                data = self.zip.read("script/" + base)
            except KeyError:
                plen[0] = 0
                return None
        buf = ctypes.create_string_buffer(data, len(data))
        self._buffers[name] = buf
        plen[0] = len(data)
        return ctypes.addressof(buf)

    def _read_card(self, code, pdata):
        ctypes.memset(pdata, 0, ctypes.sizeof(CardData))
        d = pdata.contents
        d.code = code
        row = self.cdb.get(code)
        if not row:
            return 0
        _, alias, setcode, typ, level, attr, race, atk, def_ = row
        d.alias, d.type, d.attribute, d.race, d.attack = alias, typ, attr, race, atk
        d.level = level & 0xff
        d.lscale, d.rscale = (level >> 24) & 0xff, (level >> 16) & 0xff
        if typ & TYPE_LINK:
            d.link_marker = def_
        else:
            d.defense = def_
        i = 0
        while setcode and i < 16:
            if setcode & 0xffff:
                d.setcode[i] = setcode & 0xffff
                i += 1
            setcode >>= 16
        return 0

    def _handle_message(self, pduel, msg_type):
        self.dll.get_log_message(pduel, self._logbuf)
        if msg_type == 1:
            self.errors.append(self._logbuf.value.decode("utf-8", "replace"))
        return 0
