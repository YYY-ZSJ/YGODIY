"""解析 ygopro-core 一次 get_message 取出的消息流。

引擎把多条消息首尾相接放在同一个缓冲区里，没有长度前缀，所以每种消息都必须知道自己的格式才能往下读。
格式按 ocgcore 源码里的 write_buffer 顺序整理（MDPro3 源码包中的 ocgcore 与 YGOSharp 的 GameAnalyser 互相印证）。
遇到不认识的消息直接报错，而不是猜着跳过——读错一个字节后面就全乱了。
"""

import struct

NAMES = {
    1: "retry", 2: "hint", 5: "win", 10: "select_battlecmd", 11: "select_idlecmd", 12: "select_effectyn",
    13: "select_yesno", 14: "select_option", 15: "select_card", 16: "select_chain", 18: "select_place",
    19: "select_position", 20: "select_tribute", 22: "select_counter", 23: "select_sum", 24: "select_disfield",
    25: "sort_card", 26: "select_unselect_card", 30: "confirm_decktop", 31: "confirm_cards", 32: "shuffle_deck",
    33: "shuffle_hand", 35: "swap_grave_deck", 36: "shuffle_set_card", 37: "reverse_deck", 38: "deck_top",
    39: "shuffle_extra", 40: "new_turn", 41: "new_phase", 42: "confirm_extratop", 50: "move", 53: "pos_change",
    54: "set", 55: "swap", 56: "field_disabled", 60: "summoning", 61: "summoned", 62: "spsummoning",
    63: "spsummoned", 64: "flipsummoning", 65: "flipsummoned", 70: "chaining", 71: "chained",
    72: "chain_solving", 73: "chain_solved", 74: "chain_end", 75: "chain_negated", 76: "chain_disabled",
    81: "random_selected", 83: "become_target", 90: "draw", 91: "damage", 92: "recover", 93: "equip",
    94: "lpupdate", 96: "card_target", 97: "cancel_target", 100: "pay_lpcost", 101: "add_counter",
    102: "remove_counter", 110: "attack", 111: "battle", 112: "attack_disabled", 113: "damage_step_start",
    114: "damage_step_end", 120: "missed_effect", 130: "toss_coin", 131: "toss_dice",
    132: "rock_paper_scissors", 133: "hand_res", 140: "announce_race", 141: "announce_attrib",
    142: "announce_card", 143: "announce_number", 160: "card_hint", 161: "tag_swap", 165: "player_hint",
    170: "match_kill",
}

SELECTS = {
    "select_battlecmd", "select_idlecmd", "select_effectyn", "select_yesno", "select_option", "select_card",
    "select_chain", "select_place", "select_position", "select_tribute", "select_counter", "select_sum",
    "select_disfield", "sort_card", "select_unselect_card", "rock_paper_scissors", "announce_race",
    "announce_attrib", "announce_card", "announce_number",
}

# 只有固定长度、内容用不到的消息：名字 → 消息体字节数
FIXED = {
    "retry": 0, "shuffle_deck": 1, "swap_grave_deck": 1, "reverse_deck": 0, "deck_top": 6, "swap": 16,
    "field_disabled": 4, "summoned": 0, "spsummoned": 0, "flipsummoned": 0, "chained": 1, "chain_solved": 1,
    "chain_end": 0, "equip": 8, "card_target": 8, "cancel_target": 8, "add_counter": 7, "remove_counter": 7,
    "battle": 26, "attack_disabled": 0, "damage_step_start": 0, "damage_step_end": 0, "missed_effect": 8,
    "hand_res": 1, "card_hint": 9, "player_hint": 6, "match_kill": 4, "rock_paper_scissors": 1,
}


class Reader:
    def __init__(self, data):
        self.data = data
        self.pos = 0

    def take(self, fmt):
        v = struct.unpack_from("<" + fmt, self.data, self.pos)
        self.pos += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]

    def u8(self):
        return self.take("B")

    def u16(self):
        return self.take("H")

    def u32(self):
        return self.take("I")

    def i32(self):
        return self.take("i")

    def skip(self, n):
        self.pos += n

    def loc(self):
        """get_info_location()：控制者、位置、序号、表示形式各 1 字节。"""
        c, l, s, p = self.take("BBBB")
        return {"controller": c, "location": l, "sequence": s, "position": p}

    def card7(self):
        code, c, l, s = self.take("IBBB")
        return {"code": code, "controller": c, "location": l, "sequence": s}

    def card8(self):
        code = self.u32()
        d = self.loc()
        d["code"] = code
        return d


def _cards(r, n, fn):
    return [fn() for _ in range(n)]


def parse_one(r):
    t = r.u8()
    name = NAMES.get(t)
    if name is None:
        raise ValueError("不认识的消息类型 %d（位置 %d）" % (t, r.pos - 1))
    m = {"type": name}
    if name in FIXED:
        if name == "chained" or name == "chain_solved":
            m["chain"] = r.u8()
        elif name == "rock_paper_scissors":
            m["player"] = r.u8()
        else:
            r.skip(FIXED[name])
        return m
    if name == "hint":
        m["hint"], m["player"], m["data"] = r.u8(), r.u8(), r.u32()
    elif name == "win":
        m["player"], m["reason"] = r.u8(), r.u8()
    elif name == "select_battlecmd":
        m["player"] = r.u8()
        m["activatable"] = [dict(r.card7(), desc=r.u32()) for _ in range(r.u8())]
        m["attackable"] = [dict(r.card7(), direct=r.u8()) for _ in range(r.u8())]
        m["can_m2"], m["can_ep"] = r.u8(), r.u8()
    elif name == "select_idlecmd":
        m["player"] = r.u8()
        for key in ("summonable", "spsummonable", "repositionable", "msetable", "ssetable"):
            m[key] = _cards(r, r.u8(), r.card7)
        m["activatable"] = [dict(r.card7(), desc=r.u32()) for _ in range(r.u8())]
        m["can_bp"], m["can_ep"], m["can_shuffle"] = r.u8(), r.u8(), r.u8()
    elif name == "select_effectyn":
        m["player"], m["code"] = r.u8(), r.u32()
        m.update(r.loc())
        m["desc"] = r.u32()
    elif name == "select_yesno":
        m["player"], m["desc"] = r.u8(), r.u32()
    elif name in ("select_option", "announce_card", "announce_number"):
        m["player"] = r.u8()
        m["options"] = [r.u32() for _ in range(r.u8())]
    elif name == "select_card":
        m["player"], m["cancelable"], m["min"], m["max"] = r.u8(), r.u8(), r.u8(), r.u8()
        m["cards"] = _cards(r, r.u8(), r.card8)
    elif name == "select_tribute":
        m["player"], m["cancelable"], m["min"], m["max"] = r.u8(), r.u8(), r.u8(), r.u8()
        m["cards"] = [dict(r.card7(), release=r.u8()) for _ in range(r.u8())]
    elif name == "select_unselect_card":
        m["player"], m["finishable"], m["cancelable"], m["min"], m["max"] = r.take("BBBBB")
        m["cards"] = _cards(r, r.u8(), r.card8)
        m["selected"] = _cards(r, r.u8(), r.card8)
    elif name == "select_chain":
        # 不同版本的布局不同。选择类消息总在缓冲区末尾，按剩余长度判断：
        #   MDPro3 带的 DLL：头部没有 forced，每个条目 14 字节（标志 + forced 各 1 字节）
        #   源码包里的版本：头部有 forced，每个条目 13 字节；更早的版本：都没有
        m["player"] = r.u8()
        n = r.u8()
        m["special"] = r.u8()
        rest = len(r.data) - r.pos
        wide = n and rest == 8 + 14 * n      # n == 1 时两种布局长度相同，以 MDPro3 的为准
        m["forced"] = r.u8() if not wide and rest == 9 + 13 * n else 0
        r.skip(8)
        m["chains"] = []
        for _ in range(n):
            flag = r.u8()
            if wide:
                m["forced"] |= r.u8()
            code = r.u32()
            d = r.loc()
            d.update(code=code, flag=flag, desc=r.u32())
            m["chains"].append(d)
    elif name in ("select_place", "select_disfield"):
        m["player"], m["count"], m["flag"] = r.u8(), r.u8(), r.u32()
    elif name == "select_position":
        m["player"], m["code"], m["positions"] = r.u8(), r.u32(), r.u8()
    elif name == "select_counter":
        m["player"], m["counter"], m["count"] = r.u8(), r.u16(), r.u16()
        m["cards"] = [dict(r.card7(), counters=r.u16()) for _ in range(r.u8())]
    elif name == "select_sum":
        m["mode"], m["player"], m["acc"], m["min"], m["max"] = r.u8(), r.u8(), r.u32(), r.u8(), r.u8()
        m["must"] = [dict(r.card7(), param=r.u32()) for _ in range(r.u8())]
        m["cards"] = [dict(r.card7(), param=r.u32()) for _ in range(r.u8())]
    elif name == "sort_card":
        m["player"] = r.u8()
        m["cards"] = _cards(r, r.u8(), r.card7)
    elif name == "confirm_cards":
        # MDPro3 带的 DLL 在玩家后面多 1 个字节（展示方式的标志）
        m["player"], m["flag"] = r.u8(), r.u8()
        m["cards"] = _cards(r, r.u8(), r.card7)
    elif name in ("confirm_decktop", "confirm_extratop"):
        m["player"] = r.u8()
        m["cards"] = _cards(r, r.u8(), r.card7)
    elif name in ("shuffle_hand", "shuffle_extra"):
        m["player"] = r.u8()
        r.skip(4 * r.u8())
    elif name == "shuffle_set_card":
        r.u8()
        r.skip(8 * r.u8())
    elif name == "new_turn":
        m["player"] = r.u8()
    elif name == "new_phase":
        m["phase"] = r.u16()
    elif name == "move":
        m["code"] = r.u32()
        m["from"], m["to"], m["reason"] = r.loc(), r.loc(), r.u32()
    elif name == "pos_change":
        m["code"] = r.u32()
        m["controller"], m["location"], m["sequence"], m["prev"], m["position"] = r.take("BBBBB")
    elif name == "set":
        m["code"] = r.u32()
        m.update(r.loc())
    elif name in ("summoning", "spsummoning", "flipsummoning"):
        m["code"] = r.u32()
        m.update(r.loc())
    elif name == "chaining":
        m["code"] = r.u32()
        m.update(r.loc())
        m["trigger_controller"], m["trigger_location"], m["trigger_sequence"] = r.take("BBB")
        m["desc"], m["chain"] = r.u32(), r.u8()
    elif name in ("chain_solving", "chain_negated", "chain_disabled"):
        m["chain"] = r.u8()
    elif name == "random_selected":
        r.u8()
        r.skip(4 * r.u8())
    elif name == "become_target":
        m["targets"] = [r.loc() for _ in range(r.u8())]
    elif name == "draw":
        m["player"] = r.u8()
        m["codes"] = [r.u32() & 0x7fffffff for _ in range(r.u8())]
    elif name in ("damage", "recover", "lpupdate", "pay_lpcost"):
        m["player"], m["value"] = r.u8(), r.u32()
    elif name == "attack":
        m["attacker"], m["target"] = r.loc(), r.loc()
    elif name in ("toss_coin", "toss_dice"):
        m["player"] = r.u8()
        m["results"] = [r.u8() for _ in range(r.u8())]
    elif name in ("announce_race", "announce_attrib"):
        m["player"], m["count"], m["available"] = r.u8(), r.u8(), r.u32()
    elif name == "tag_swap":
        m["player"] = r.u8()
        _, ecount, _, hcount = r.take("BBBB")
        r.skip(4 + 4 * (hcount + ecount))
    else:
        raise ValueError("消息 %s 还没有写解析" % name)
    return m


def parse(data):
    r = Reader(data)
    out = []
    try:
        while r.pos < len(data):
            out.append(parse_one(r))
        if r.pos != len(data):
            raise ValueError("消息流长度对不上：读到 %d，实际 %d" % (r.pos, len(data)))
    except (ValueError, struct.error) as ex:
        raise ValueError("%s\n已解析：%s\n原始字节：%s" % (ex, [m["type"] for m in out], data.hex(" "))) from None
    return out
