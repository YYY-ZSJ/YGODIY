"""把卡片导出成文字信息：卡名、类型、数值，空一行后是效果。效果用卡面上的文字，卡面没写才用积木生成的。"""

from ygopack import cardinfo
from . import store

ARROWS = dict(zip(cardinfo.LINK_MARKERS, "↖↑↗←→↙↓↘"))
SUMMONS = ("融合", "仪式", "同调", "超量", "连接")
ABILITIES = ("调整", "二重", "灵魂", "反转", "特殊召唤", "同盟", "卡通", "灵摆")


def _stat(value):
    return "?" if value == -2 else str(value)


def _monster_lines(rec):
    kind = rec["type"]
    tags = ["怪兽", "效果" if kind & cardinfo.TYPE_EFFECT else "通常"]
    tags += [name for name in ABILITIES if kind & cardinfo.EXTRA_BITS[name]]
    tags += [name for name in SUMMONS if kind & cardinfo.CALL_WAY_BITS[name]]
    attribute = next((name for name, bit in cardinfo.ATTRIBUTE_BITS.items() if bit == rec["attribute"]), "?")
    race = cardinfo.RACES[cardinfo.RACE_BITS.index(rec["race"])].removesuffix("族") if rec["race"] in cardinfo.RACE_BITS else "?"
    level = rec["level"] & 0xff
    if kind & cardinfo.TYPE_LINK:
        stats = "[LINK-%d] %s %s" % (level, _stat(rec["atk"]), "".join(mark for bit, mark in ARROWS.items() if rec["def"] & bit))
    else:
        stats = "[%s%d] %s/%s" % ("☆" if kind & cardinfo.TYPE_XYZ else "★", level, _stat(rec["atk"]), _stat(rec["def"]))
    if kind & cardinfo.TYPE_PENDULUM:
        scale = rec["level"] >> 24 & 0xff
        stats += " ←%d %d→" % (scale, scale)
    return ["[%s] %s/%s" % ("|".join(tags), race, attribute), stats]


def _spell_line(rec):
    sub = next((name for name, bit in cardinfo.MT_TYPE_BITS.items() if bit and rec["type"] & bit), "通常")
    return "[%s|%s]" % ("魔法" if rec["type"] & cardinfo.TYPE_SPELL else "陷阱", sub)


def _compose(rec, name, effect, pendulum):
    lines = [name] + (_monster_lines(rec) if rec["type"] & cardinfo.TYPE_MONSTER else [_spell_line(rec)])
    if pendulum:
        effect = "【灵摆效果】\n%s\n【怪兽效果】\n%s" % (pendulum, effect)
    return "\n".join(lines) + ("\n\n" + effect if effect else "")


def _plain(name, effect):
    """不是 OCG/TCG 能导出的卡：没有类型资料，文字照样给。"""
    return "\n\n".join(part for part in (name, effect.strip()) if part)


def card_text(tab):
    data = tab.get("data") or {}
    result = store.generate(tab)
    name = data.get("name") or tab.get("title") or "未命名"
    if result.rec is None:
        return _plain(name, data.get("effect_text") or "")
    return _compose(result.rec, name, result.rec.get("desc") or result.desc, result.rec.get("pdesc") or result.pdesc)


def editor_text(fields):
    """OCG、RD 编辑器里的资料。没有积木，融合等怪兽有没有效果看文字里有没有完整的句子。"""
    effect = fields.get("effect_text") or ""
    has_effects = fields.get("call_way", 0) not in (0, "通常") and "。" in effect
    try:
        rec = cardinfo.from_ygodiy(fields, has_effects=has_effects)[0]
    except cardinfo.CardDataError:
        return _plain(fields.get("name") or "未命名", effect)
    return _compose(rec, rec["name"], rec.get("desc", ""), rec.get("pdesc", ""))


def write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")


def export(path, tabs):
    write(path, "\n\n\n".join(card_text(tab) for tab in tabs))
