"""YGODIY 的卡片数据（标签页 / 「导出数据」的 JSON）→ ygopro cdb 的一行。

YGODIY 里卡种、种族、召唤方式等存的是下拉框的序号，这里按编辑器里的选项顺序翻译成 ygopro 的常量。
选项顺序来自 OTCG_widget.py（卡种、魔陷类型、召唤方式、两个附加栏）与 config.json（种族、连接箭头）。
"""

import base64
import os

# ---------------------------------------------------------------- ygopro 常量

TYPE_MONSTER, TYPE_SPELL, TYPE_TRAP = 0x1, 0x2, 0x4
TYPE_NORMAL, TYPE_EFFECT, TYPE_FUSION, TYPE_RITUAL = 0x10, 0x20, 0x40, 0x80
TYPE_SPIRIT, TYPE_UNION, TYPE_DUAL, TYPE_TUNER, TYPE_SYNCHRO, TYPE_TOKEN = 0x200, 0x400, 0x800, 0x1000, 0x2000, 0x4000
TYPE_QUICKPLAY, TYPE_CONTINUOUS, TYPE_EQUIP, TYPE_FIELD, TYPE_COUNTER = 0x10000, 0x20000, 0x40000, 0x80000, 0x100000
TYPE_FLIP, TYPE_TOON, TYPE_XYZ, TYPE_PENDULUM, TYPE_SPSUMMON, TYPE_LINK = \
    0x200000, 0x400000, 0x800000, 0x1000000, 0x2000000, 0x4000000
TYPE_EXTRA = TYPE_FUSION | TYPE_SYNCHRO | TYPE_XYZ | TYPE_LINK

# 编辑器下拉框的选项顺序
CARD_TYPES = ["怪兽卡", "魔法卡", "陷阱卡"]
MT_TYPES = ["通常", "永续", "装备", "仪式", "场地", "反击", "速攻"]
CALL_WAYS = ["通常", "效果", "融合", "仪式", "同调", "超量", "衍生物", "连接", "暗黑同调", "巨神兵", "天空龙", "翼神龙"]
EXTRAS = ["", "通常", "调整", "二重", "灵魂", "反转", "特殊召唤", "同盟", "卡通", "灵摆"]
RACES = ["龙族", "战士族", "恶魔族", "魔法师族", "天使族", "不死族", "岩石族", "植物族", "昆虫族", "水族", "炎族", "雷族",
         "鱼族", "海龙族", "幻龙族", "恐龙族", "爬虫类族", "机械族", "兽族", "鸟兽族", "兽战士族", "念动力族", "电子界族",
         "幻想魔族", "幻神兽族", "创造神族"]
# 连接箭头在 link_status 里的顺序：左上、上、右上、左、右、左下、下、右下

MT_TYPE_BITS = {"通常": 0, "永续": TYPE_CONTINUOUS, "装备": TYPE_EQUIP, "仪式": TYPE_RITUAL, "场地": TYPE_FIELD,
                "反击": TYPE_COUNTER, "速攻": TYPE_QUICKPLAY}
SPELL_ONLY = {"装备", "仪式", "场地", "速攻"}
TRAP_ONLY = {"反击"}
CALL_WAY_BITS = {"通常": TYPE_NORMAL, "效果": TYPE_EFFECT, "融合": TYPE_FUSION, "仪式": TYPE_RITUAL,
                 "同调": TYPE_SYNCHRO, "超量": TYPE_XYZ, "衍生物": TYPE_TOKEN | TYPE_NORMAL, "连接": TYPE_LINK,
                 "暗黑同调": TYPE_SYNCHRO, "巨神兵": TYPE_EFFECT, "天空龙": TYPE_EFFECT, "翼神龙": TYPE_EFFECT}
EXTRA_BITS = {"": 0, "通常": TYPE_NORMAL, "调整": TYPE_TUNER, "二重": TYPE_DUAL, "灵魂": TYPE_SPIRIT, "反转": TYPE_FLIP,
              "特殊召唤": TYPE_SPSUMMON, "同盟": TYPE_UNION, "卡通": TYPE_TOON, "灵摆": TYPE_PENDULUM}
RACE_BITS = [0x2000, 0x1, 0x8, 0x2, 0x4, 0x10, 0x100, 0x400, 0x800, 0x40, 0x80, 0x1000, 0x20000, 0x40000, 0x800000,
             0x10000, 0x80000, 0x20, 0x4000, 0x200, 0x8000, 0x100000, 0x1000000, 0x2000000, 0x200000, 0x400000]
ATTRIBUTE_BITS = {"地": 0x01, "水": 0x02, "炎": 0x04, "风": 0x08, "光": 0x10, "暗": 0x20, "神": 0x40}
LINK_MARKERS = [0x40, 0x80, 0x100, 0x8, 0x20, 0x1, 0x2, 0x4]   # 按 link_status 的顺序

# 生成器（effect_model）用的 subtype 名字
SUBTYPE_OF_BIT = {TYPE_EFFECT: "effect", TYPE_TUNER: "tuner", TYPE_NORMAL: "normal", TYPE_RITUAL: "ritual",
                  TYPE_FUSION: "fusion", TYPE_SYNCHRO: "synchro", TYPE_XYZ: "xyz", TYPE_LINK: "link",
                  TYPE_PENDULUM: "pendulum", TYPE_QUICKPLAY: "quick", TYPE_CONTINUOUS: "continuous",
                  TYPE_EQUIP: "equip", TYPE_FIELD: "field", TYPE_COUNTER: "counter"}


class CardDataError(ValueError):
    pass


def _pick(options, index, what):
    try:
        return options[int(index)]
    except (IndexError, TypeError, ValueError):
        raise CardDataError("%s的序号 %r 超出范围" % (what, index))


def _stat(text, what):
    text = str(text or "").strip()
    if text in ("", "-"):
        return 0
    if text == "?":
        return -2
    try:
        return int(text)
    except ValueError:
        raise CardDataError("%s「%s」不是数字或 ?" % (what, text))


def from_ygodiy(data, has_effects=False):
    """把一张卡的 YGODIY 数据翻译成 cdb 字段。返回 (record, 提示列表)。

    has_effects：这张卡挂了 Effect Model 并且有效果。融合 / 同调 / 超量 / 连接 / 仪式怪兽在编辑器里不区分
    「有没有效果」，由它决定要不要加 TYPE_EFFECT。
    """
    notes = []
    kind = _pick(CARD_TYPES, data.get("card_type", 0), "卡种")
    rec = {"name": (data.get("name") or "").strip(), "alias": 0, "setcodes": [], "atk": 0, "def": 0,
           "level": 0, "race": 0, "attribute": 0, "category": 0}
    if not rec["name"]:
        raise CardDataError("卡名是空的")
    if kind != "怪兽卡":
        sub = _pick(MT_TYPES, data.get("mt_type", 0), "魔陷类型")
        if kind == "魔法卡" and sub in TRAP_ONLY or kind == "陷阱卡" and sub in SPELL_ONLY:
            raise CardDataError("%s没有「%s」这种类型" % (kind, sub))
        rec["type"] = (TYPE_SPELL if kind == "魔法卡" else TYPE_TRAP) | MT_TYPE_BITS[sub]
        rec["desc"] = (data.get("effect_text") or "").strip()
        return rec, notes

    call_way = _pick(CALL_WAYS, data.get("call_way", 1), "召唤方式")
    extra1 = _pick(EXTRAS, data.get("extra1", 0), "附加栏1")
    extra2 = _pick(EXTRAS[:-1], data.get("extra2", 0), "附加栏2")
    typ = TYPE_MONSTER | CALL_WAY_BITS[call_way] | EXTRA_BITS[extra1] | EXTRA_BITS[extra2]
    if call_way in ("融合", "仪式", "同调", "超量", "连接", "暗黑同调") and has_effects:
        typ |= TYPE_EFFECT
    if typ & TYPE_EFFECT and typ & TYPE_NORMAL and call_way != "通常":
        typ &= ~TYPE_NORMAL
    if call_way == "通常" and (typ & ~(TYPE_MONSTER | TYPE_NORMAL | TYPE_PENDULUM)):
        # 「通常 / 调整」之类不存在；带调整、反转等能力的怪兽一定是效果怪兽
        typ = (typ & ~TYPE_NORMAL) | TYPE_EFFECT
        notes.append("召唤方式是「通常」但附加栏带了能力，按效果怪兽导出")
    if call_way == "通常" and has_effects:
        typ = (typ & ~TYPE_NORMAL) | TYPE_EFFECT
        notes.append("召唤方式是「通常」但挂了效果，按效果怪兽导出")
    rec["type"] = typ
    rec["attribute"] = ATTRIBUTE_BITS.get(str(data.get("attribute") or "").strip(), 0)
    if not rec["attribute"]:
        notes.append("属性「%s」认不出来" % data.get("attribute"))
    rec["race"] = RACE_BITS[RACES.index(_pick(RACES, data.get("race", 0), "种族"))]
    rec["atk"] = _stat(data.get("ATK"), "攻击力")
    if typ & TYPE_LINK:
        arrows = list(data.get("link_status") or [False] * 8)
        rec["def"] = sum(bit for bit, on in zip(LINK_MARKERS, arrows) if on)
        rec["level"] = sum(1 for on in arrows if on)
        if not rec["level"]:
            notes.append("连接怪兽没有连接箭头")
    else:
        rec["def"] = _stat(data.get("DEF"), "守备力")
        rec["level"] = int(data.get("rank") if typ & TYPE_XYZ else data.get("level") or 0)
    pdesc = ""
    if typ & TYPE_PENDULUM:
        scale_text = str(data.get("lb_level") or "").strip()
        scale = int(scale_text) if scale_text.isdigit() else 0
        if not scale_text.isdigit():
            notes.append("灵摆刻度「%s」不是数字，按 0 导出" % scale_text)
        rec["level"] |= (scale << 24) | (scale << 16)
        rec["scale"] = scale
        pdesc = (data.get("lb_text") or "").strip()
    rec["desc"] = (data.get("effect_text") or "").strip()
    rec["pdesc"] = pdesc
    return rec, notes


def _stat_text(value):
    return "?" if value == -2 else str(value)


def to_ygodiy(rec):
    """cdb 记录 → 编辑器的卡片数据（from_ygodiy 的反方向），用于导入扩展包。"""
    typ = rec["type"]
    text = (rec.get("desc") or "").replace("\r\n", "\n")
    data = {"name": rec["name"], "cardpass": str(rec["code"]), "effect_text": text}
    if not typ & TYPE_MONSTER:
        data["card_type"] = 1 if typ & TYPE_SPELL else 2
        data["mt_type"] = next((MT_TYPES.index(name) for name, bit in MT_TYPE_BITS.items() if bit and typ & bit), 0)
        return data
    data["card_type"] = 0
    order = ("连接", "超量", "同调", "融合", "仪式", "衍生物")
    data["call_way"] = next((CALL_WAYS.index(name) for name in order if typ & CALL_WAY_BITS[name] == CALL_WAY_BITS[name]),
                            CALL_WAYS.index("效果" if typ & TYPE_EFFECT else "通常"))
    extras = [name for name in ("灵摆", "调整", "二重", "灵魂", "反转", "特殊召唤", "同盟", "卡通") if typ & EXTRA_BITS[name]]
    data["extra1"] = EXTRAS.index(extras[0]) if extras else 0
    data["extra2"] = EXTRAS.index(extras[1]) if len(extras) > 1 else 0
    data["attribute"] = next((name for name, bit in ATTRIBUTE_BITS.items() if rec["attribute"] & bit), "")
    data["race"] = RACE_BITS.index(rec["race"]) if rec["race"] in RACE_BITS else 0
    data["ATK"] = _stat_text(rec["atk"])
    level = rec["level"] & 0xff
    if typ & TYPE_LINK:
        data["link_status"] = [bool(rec["def"] & bit) for bit in LINK_MARKERS]
    else:
        data["DEF"] = _stat_text(rec["def"])
        data["rank" if typ & TYPE_XYZ else "level"] = level
    if typ & TYPE_PENDULUM:
        data["lb_level"] = str(rec["level"] >> 24 & 0xff)
        head, mark, tail = text.partition("【怪兽效果】")
        if mark:
            data["lb_text"] = head.split("\n", 1)[-1].strip()
            data["effect_text"] = tail.strip()
    return data


def model_card(rec):
    """effect_model 需要的 card 块（kind、subtypes），从 cdb 字段推出来，保证两边一致。"""
    t = rec["type"]
    kind = "monster" if t & TYPE_MONSTER else "spell" if t & TYPE_SPELL else "trap"
    subs = [name for bit, name in SUBTYPE_OF_BIT.items() if t & bit]
    if kind != "monster":
        subs = [s for s in subs if s in ("quick", "continuous", "equip", "field", "counter", "ritual")] or ["normal"]
    return {"code": rec["code"], "name": rec["name"], "kind": kind, "subtypes": subs}


def token_records(model, code, ot=3):
    """Effect Model 里「特殊召唤衍生物」用到的 DIY 衍生物的 cdb 记录：卡号＝这张卡的卡号＋编号（见 normalize.diy_tokens）。
    官方衍生物写了卡号，不在这里。"""
    from effect_model.model.normalize import diy_tokens
    from effect_model.zh import ATTRIBUTE, RACE
    from blocks import is_blocks
    if is_blocks(model):               # v0.3 积木树：衍生物的数据就在「特殊召唤衍生物」积木上
        from blocks.compile import tokens
        found = [(n, dict(name=b["name"], atk=b["atk"], level=b["level"], race=b["race"], attribute=b["attribute"],
                          **{"def": b["def"]})) for n, b in tokens(model)]
    else:
        found = diy_tokens(model or {})
    out = []
    for n, t in found:
        out.append({"code": code + n, "ot": ot, "alias": 0, "setcodes": [],
                    "type": TYPE_MONSTER | TYPE_NORMAL | TYPE_TOKEN, "atk": t["atk"], "def": t["def"],
                    "level": t["level"], "race": RACE_BITS[RACES.index(RACE[t["race"]] + "族")],
                    "attribute": ATTRIBUTE_BITS[ATTRIBUTE[t["attribute"]]], "name": t["name"], "desc": "",
                    "cdb_desc": "", "strings": []})
    return out


def ygopro_desc(rec, desc, pdesc):
    """拼成 cdb 的 desc：灵摆卡是「←刻度 【灵摆】 刻度→ / 灵摆效果 / 【怪兽效果】 / 怪兽效果」，换行用 \\r\\n。"""
    if rec["type"] & TYPE_PENDULUM:
        s = rec.get("scale", 0)
        text = "←%d 【灵摆】 %d→\n%s\n【怪兽效果】\n%s" % (s, s, pdesc, desc)
    else:
        text = desc
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def card_image_bytes(data, assets_dir=None):
    """卡图原画（PNG 字节）：「导出数据」的 JSON 里是 base64 的 image；标签页里是 _image_ref 指向资源文件。"""
    if data.get("image"):
        return base64.b64decode(data["image"])
    ref = data.get("_image_ref")
    if ref and assets_dir:
        path = os.path.join(assets_dir, ref + ".img")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
    return None
