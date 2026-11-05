"""一局对局：摆场、推进、应答、查询场面。

摆场用引擎自带的 Debug.AddCard（残局模式用的那个函数）：生成一段 Lua，开局前预载执行。
它比 ocgapi 的 new_card 多两样本事：能把卡放进灵摆区域，能给超量怪兽挂素材。
"""

import ctypes
import struct

from .messages import parse, SELECTS

LOC = {"deck": 0x01, "hand": 0x02, "mzone": 0x04, "szone": 0x08, "grave": 0x10, "banished": 0x20,
       "extra": 0x40, "overlay": 0x80, "field": 0x0c, "pzone": 0x200}
LOC_NAME = {v: k for k, v in LOC.items()}
POS = {"attack": 0x1, "facedown_attack": 0x2, "defense": 0x4, "facedown_defense": 0x8, "set": 0xa,
       "faceup": 0x5, "facedown": 0xa}
POS_FACEUP = 0x5

DUEL_ATTACK_FIRST_TURN = 0x02
DUEL_PSEUDO_SHUFFLE = 0x10
PROCESSOR_WAITING, PROCESSOR_END = 0x10000000, 0x20000000

QUERY_CODE, QUERY_POSITION, QUERY_LEVEL, QUERY_ATTACK, QUERY_DEFENSE = 0x1, 0x2, 0x10, 0x100, 0x200
QUERY_OVERLAY_CARD, QUERY_STATUS = 0x10000, 0x80000
QUERY_FLAGS = QUERY_CODE | QUERY_POSITION | QUERY_LEVEL | QUERY_ATTACK | QUERY_DEFENSE | QUERY_OVERLAY_CARD | QUERY_STATUS
STATUS_DISABLED = 0x0001

FILLER = 89631139   # 青眼白龙：没有效果的通常怪兽，用来填卡组
SETUP_SCRIPT = "ygodiy_sandbox_setup.lua"


class Duel:
    def __init__(self, core, seed=20261022, lp=(8000, 8000), options=DUEL_ATTACK_FIRST_TURN | DUEL_PSEUDO_SHUFFLE):
        self.core = core
        self.seed = seed
        self.lp = list(lp)
        self.options = options
        self.ptr = core.dll.create_duel(seed)
        self.log = []          # 所有消息（解析后的 dict）
        self.ended = False
        self._msgbuf = ctypes.create_string_buffer(1 << 20)
        self._qbuf = ctypes.create_string_buffer(1 << 16)
        for p in (0, 1):
            core.dll.set_player_info(self.ptr, p, lp[p], 0, 1)

    # ------------------------------------------------------------ 摆场

    def setup(self, field):
        """field: {"0": {"hand": [...], "mzone": [...], ...}, "1": {...}}。每张卡可以是卡号，或
        {"code": 卡号, "seq": 格子, "pos": "attack"/"defense"/"set"/..., "materials": [卡号...]}。"""
        lines = []
        for p in (0, 1):
            zones = field.get(str(p), field.get(p, {})) or {}
            used = {"mzone": set(), "szone": set()}
            if zones.get("pzone"):
                used["szone"].update({0, 4})
            deck = list(zones.get("deck", []))
            deck += [FILLER] * max(0, 20 - len(deck))
            for code in reversed(deck):  # 列表第一张是卡组最上面
                lines.append(self._add(code, p, "deck", 0, "facedown_defense"))
            for zone in ("hand", "grave", "banished", "extra"):
                for item in zones.get(zone, []):
                    code, _, pos, _ = self._unpack(item)
                    lines.append(self._add(code, p, zone, 0, pos))
            for i, item in enumerate(zones.get("pzone", [])):
                code, seq, pos, _ = self._unpack(item)
                lines.append(self._add(code, p, "pzone", 0 if i == 0 else 1, "faceup"))
            for zone in ("mzone", "szone"):
                for item in zones.get(zone, []):
                    code, seq, pos, mats = self._unpack(item)
                    if seq is None:
                        seq = next(s for s in range(5) if s not in used[zone])
                    used[zone].add(seq)
                    pos = pos or ("attack" if zone == "mzone" else "set")
                    lines.append(self._add(code, p, zone, seq, pos))
                    for m in mats or []:
                        lines.append(self._add(m, p, "mzone", seq, "attack"))
        self.core.virtual[SETUP_SCRIPT] = ("\n".join(lines) + "\n").encode()
        self.core.dll.preload_script(self.ptr, ("./script/" + SETUP_SCRIPT).encode())

    @staticmethod
    def _unpack(item):
        if isinstance(item, dict):
            return item["code"], item.get("seq"), item.get("pos"), item.get("materials")
        return item, None, None, None

    def _add(self, code, p=0, zone="hand", seq=0, pos=None):
        position = POS[pos] if pos else (POS["facedown_defense"] if zone in ("deck", "extra") else POS["attack"])
        if zone in ("hand", "grave", "banished"):
            position = POS["attack"] if zone != "hand" else POS["facedown_defense"]
        return "Debug.AddCard(%d,%d,%d,%s,%d,%d,true)" % (code, p, p, {
            "deck": "LOCATION_DECK", "hand": "LOCATION_HAND", "mzone": "LOCATION_MZONE", "szone": "LOCATION_SZONE",
            "grave": "LOCATION_GRAVE", "banished": "LOCATION_REMOVED", "extra": "LOCATION_EXTRA",
            "pzone": "LOCATION_PZONE"}[zone], seq or 0, position)

    def start(self):
        self.core.dll.start_duel(self.ptr, self.options)

    # ------------------------------------------------------------ 推进与应答

    def advance(self, limit=10000):
        """推进到引擎要求应答或对局结束。返回 (这一段的消息列表, 要应答的消息或 None)。"""
        out = []
        for _ in range(limit):
            r = self.core.dll.process(self.ptr)
            n = self.core.dll.get_message(self.ptr, self._msgbuf)
            msgs = parse(self._msgbuf.raw[:n]) if n > 0 else []
            out.extend(msgs)
            self.log.extend(msgs)
            if r & PROCESSOR_END or any(m["type"] == "win" for m in msgs):
                self.ended = True
                return out, None
            if r & PROCESSOR_WAITING:
                # 确认卡片之类的消息后引擎也会暂停一次（让客户端展示），这种不需要应答，接着推进
                if msgs and msgs[-1]["type"] in SELECTS:
                    return out, msgs[-1]
        raise RuntimeError("推进 %d 次仍未停下" % limit)

    def respond_int(self, value):
        self.core.dll.set_responsei(self.ptr, value)

    def respond_bytes(self, values):
        data = bytes(v & 0xff for v in values)
        self.core.dll.set_responseb(self.ptr, data + b"\0" * (64 - len(data)))

    # ------------------------------------------------------------ 查询

    def query(self, player, zone):
        """返回某玩家某区域的卡：[{"code", "sequence", "position", "level", "atk", "def", "overlay", "disabled"}]。
        查询结果按标志位从低到高排列：卡号、位置、等级、攻击力、守备力、超量素材、状态。"""
        loc = LOC["szone"] if zone == "pzone" else LOC[zone]
        n = self.core.dll.query_field_card(self.ptr, player, loc, QUERY_FLAGS, self._qbuf, 0)
        data = self._qbuf.raw[:n]
        out, pos, idx = [], 0, 0
        while pos < n:
            length = struct.unpack_from("<i", data, pos)[0]
            if length <= 4:
                pos += 4
                idx += 1
                continue
            p = pos + 8
            code, = struct.unpack_from("<I", data, p)
            c, l, s, position = struct.unpack_from("<BBBB", data, p + 4)
            level, atk, def_ = struct.unpack_from("<iii", data, p + 8)
            nover, = struct.unpack_from("<i", data, p + 20)
            overlay = list(struct.unpack_from("<%dI" % nover, data, p + 24))
            status, = struct.unpack_from("<I", data, p + 24 + 4 * nover)
            out.append({"code": code, "sequence": s, "position": position, "level": level, "atk": atk, "def": def_,
                        "overlay": overlay, "disabled": bool(status & STATUS_DISABLED)})
            pos += length
            idx += 1
        if zone == "pzone":
            out = [c for c in out if c["sequence"] in (0, 4) and c["position"] & POS_FACEUP and
                   self.core.card_type(c["code"]) & 0x1000000]
        return out

    def end(self):
        self.core.dll.end_duel(self.ptr)
