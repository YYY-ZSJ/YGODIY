"""DIY 工作台的数据：存在哪、怎么读写、怎么从卡片数据生成文本与脚本、怎么组装导出清单。

不依赖界面，可以单独测试。

存放位置（卡包就是数据库，不另建一套数据）：
    标签页里每张卡的记录 tab = {"title", "data", "_card_uid", "diy"}
        tab["diy"] = {"blocks": v0.3 积木树（不含 card 块）, "setcodes": ["0xa01", ...],
                      "convert_notes": [旧存档转换时没能完全转换的说明]}
      以前存的 v0.2（v0.1 先升级成 v0.2）效果 diy["effect"] 第一次读到时转换成积木树，旧的那份留在积木树的 legacy_v02 里。
      和 data 并列存放：OCG 编辑器保存卡片时只替换 data，不会冲掉它。
    卡包 pack = {"title", "current_index", "tabs", "diy"}
        pack["diy"] = {"author", "ot", "code_start", "code_step", "setnames": {"0xa01": "星光"}}
卡号就是卡面上的卡密（data["cardpass"]），卡名、种类、攻守等全部来自卡片数据。
"""

import copy
import re

from blocks import SCHEMA, build as build_blocks, type_bits
from blocks.catalog import new as new_block
from blocks.categories import categories
from blocks.compile import CompileError
from blocks.convert import convert
from effect_model import SCHEMA_V01, upgrade
from ygopack import cardinfo

DEFAULT_PACK = {"author": "", "ot": 3, "code_start": 100001000, "code_step": 100, "setnames": {}}


class NotSupported(ValueError):
    """这张卡不是工作台能处理的（目前只支持 OCG/TCG 卡）。"""


# ---------------------------------------------------------------- 读写

def card_diy(tab):
    diy = tab.get("diy")
    if not isinstance(diy, dict):
        diy = tab["diy"] = {}
    if not isinstance(diy.get("blocks"), dict):
        old = diy.pop("effect", None)
        if isinstance(old, dict) and (old.get("effects") or old.get("rules") or old.get("summon")):
            diy["blocks"], notes = convert(upgrade_v01(old), _kind_of(tab))
            if notes:
                diy["convert_notes"] = notes
        else:
            diy["blocks"] = {"schema": SCHEMA, "effects": []}
    diy["blocks"].setdefault("effects", [])
    diy.setdefault("setcodes", [])
    return diy


def _kind_of(tab):
    try:
        rec, _ = card_record(tab.get("data") or {}, has_effects=True)
        return card_kind(rec)
    except Exception:
        return "monster"


def upgrade_v01(effect):
    """v0.1 的存档（不含 card 块）→ v0.2（召唤手续一并改成 v0.2 的 materials）；已经是 v0.2 的原样返回。"""
    if effect.get("schema", SCHEMA_V01) != SCHEMA_V01:
        return effect
    old = dict(effect, card={}, effects=effect.get("effects", []))
    s = old.get("summon")
    if isinstance(s, dict) and s.get("method") in ("xyz", "link"):    # 以前的界面只存了素材数，阶级等由卡片资料补
        old["summon"] = dict({"level": 0, "count": 2, "min": 2}, **s)
    new = upgrade(old)
    new.pop("card")
    return new


def rule_same_name(diy):
    return bool(diy.get("alias")) and diy.get("alias_mode", "rule") == "rule"


def auto_category(tab):
    try:
        return categories(full_model(tab)[0])
    except (CompileError, NotSupported):
        return 0


def item_count(model):
    return len(model.get("effects", []))


def set_card_diy(tab, diy):
    tab["diy"] = diy


def pack_diy(pack):
    diy = pack.get("diy")
    out = copy.deepcopy(DEFAULT_PACK)
    if isinstance(diy, dict):
        out.update({k: v for k, v in diy.items() if k in DEFAULT_PACK})
    return out


def set_pack_diy(pack, diy):
    pack["diy"] = diy


def card_code(data):
    text = str(data.get("cardpass") or "").strip()
    return int(text) if text.isdigit() else 0


# ---------------------------------------------------------------- 卡片资料

def card_record(data, has_effects):
    """卡片数据 → cdb 字段；不是 OCG/TCG 能导出的卡时抛 NotSupported。"""
    try:
        rec, notes = cardinfo.from_ygodiy(data, has_effects=has_effects)
    except cardinfo.CardDataError as ex:
        raise NotSupported(str(ex))
    rec["code"] = card_code(data)
    return rec, notes


def describe(rec):
    """摘要行：效果怪兽 · 4星 · 光 · 魔法师族 · 1600/1200。"""
    t = rec["type"]
    if not t & cardinfo.TYPE_MONSTER:
        kind = "魔法" if t & cardinfo.TYPE_SPELL else "陷阱"
        sub = next((name for name, bit in cardinfo.MT_TYPE_BITS.items() if bit and t & bit), "通常")
        return "%s%s卡" % (sub, kind)
    parts = []
    for bit, name in ((cardinfo.TYPE_FUSION, "融合"), (cardinfo.TYPE_SYNCHRO, "同调"), (cardinfo.TYPE_XYZ, "超量"),
                      (cardinfo.TYPE_LINK, "连接"), (cardinfo.TYPE_RITUAL, "仪式"), (cardinfo.TYPE_PENDULUM, "灵摆"),
                      (cardinfo.TYPE_TUNER, "调整"), (cardinfo.TYPE_EFFECT, "效果"), (cardinfo.TYPE_NORMAL, "通常")):
        if t & bit:
            parts.append(name)
    kind = "·".join(parts) + "怪兽"
    level = rec["level"] & 0xff
    if t & cardinfo.TYPE_LINK:
        lv = "LINK-%d" % level
        stats = "%s/-" % _stat(rec["atk"])
    else:
        lv = ("%d阶" if t & cardinfo.TYPE_XYZ else "%d星") % level
        stats = "%s/%s" % (_stat(rec["atk"]), _stat(rec["def"]))
    attr = next((k for k, v in cardinfo.ATTRIBUTE_BITS.items() if v == rec["attribute"]), "?")
    race = cardinfo.RACES[cardinfo.RACE_BITS.index(rec["race"])] if rec["race"] in cardinfo.RACE_BITS else "?"
    return " · ".join([kind, lv, attr, race, stats])


def _stat(v):
    return "?" if v == -2 else str(v)


def card_kind(rec):
    t = rec["type"]
    return "monster" if t & cardinfo.TYPE_MONSTER else "spell" if t & cardinfo.TYPE_SPELL else "trap"


def default_materials(rec, current=None):
    """额外卡组怪兽的素材（v0.2 的 summon.materials），按卡片资料推出来；已有的设置（素材数等）保留。
    灵摆怪兽不用写：v0.2 由子类推出灵摆召唤与灵摆区域的规则。不是这几种时返回 None。"""
    t = rec["type"]
    cur = current if isinstance(current, dict) else {}
    if t & cardinfo.TYPE_XYZ:
        out = dict(cur) if cur.get("method") == "xyz" else {}
        out.update({"method": "xyz", "level": rec["level"] & 0xff, "count": int(cur.get("count", 2) or 2)})
        return out
    if t & cardinfo.TYPE_SYNCHRO:
        out = dict(cur) if cur.get("method") == "synchro" else {}
        out.setdefault("tuner", {"count": 1})
        out.setdefault("nontuner", {"min": 1})
        out["method"] = "synchro"
        return out
    if t & cardinfo.TYPE_LINK:
        out = dict(cur) if cur.get("method") == "link" else {}
        out.update({"method": "link", "min": int(cur.get("min", 2) or 2)})
        out.setdefault("filter", [])
        return out
    if t & cardinfo.TYPE_FUSION and cur.get("method") == "fusion":
        return dict(cur)
    return None


def default_summon(rec, current=None):
    """整个 summon 块：素材按卡片资料重算，出场手续、限制等原样保留。"""
    out = copy.deepcopy(current) if isinstance(current, dict) else {}
    mat = default_materials(rec, out.get("materials"))
    if mat:
        out["materials"] = mat
    else:
        out.pop("materials", None)
    return out


def full_model(tab):
    """这张卡完整的积木树（补上 card 块与召唤手续），以及它的 cdb 记录。"""
    diy = card_diy(tab)
    data = tab.get("data") or {}
    model = copy.deepcopy(diy["blocks"])
    if rule_same_name(diy):      # 规则上同名、效果不同：引擎见到 alias 就读原卡脚本，所以 alias 写 0，用改名效果
        model["effects"].insert(0, new_block("name_as", code=diy["alias"], name=diy.get("alias_name", ""), where="all"))
    rec, notes = card_record(data, has_effects=bool(model.get("effects")) or bool(diy.get("script")))
    rec["setcodes"] = [int(s, 16) for s in diy.get("setcodes", []) if re.fullmatch(r"0x[0-9a-fA-F]+", str(s))]
    model["schema"] = SCHEMA
    rec["type"] |= type_bits(model)          # 「不能通常召唤」写在卡片数据的 type 里
    model["card"] = cardinfo.model_card(rec)
    model["summon"] = default_summon(rec, model.get("summon"))
    if not model["summon"]:
        model.pop("summon")
    return model, rec, notes


# ---------------------------------------------------------------- 生成

class Result:
    def __init__(self):
        self.desc = ""
        self.pdesc = ""
        self.lua = ""
        self.strings = []
        self.issues = []        # [(级别, 说明)]
        self.error = None       # 整张卡生成失败的原因（积木还没拼完整等）
        self.rec = None
        self.model = None       # 补上 card 块的积木树（沙盒检查时取 DIY 衍生物的卡片数据）


def generate(tab):
    """为一张卡生成规范文本、Lua 和检查结果；积木还没拼完整时记在 error 里，不抛异常。"""
    res = Result()
    try:
        model, rec, notes = full_model(tab)
    except NotSupported as ex:
        res.error = str(ex)
        return res
    res.rec, res.model = rec, model
    for n in notes:
        res.issues.append(("提示", n))
    for n in card_diy(tab).get("convert_notes", []):
        res.issues.append(("提示", "旧存档转换：" + n))
    script = card_diy(tab).get("script")
    try:
        built = build_blocks(model)
    except CompileError as ex:
        if script:
            return _use_script(res, tab, script)
        res.error = "还没拼完整：%s" % ex
        return res
    except Exception as ex:          # 翻译器不认识的组合：报出来，不让界面崩
        res.error = "生成失败：%r" % ex
        return res
    res.desc, res.pdesc, res.lua, res.strings = built["desc"], built["pdesc"], built["lua"], built["strings"]
    for level, where, msg in built["issues"]:
        res.issues.append(("错误" if level == "error" else "提示", "%s：%s" % (where, msg)))
    if len(res.strings) > 16:
        res.issues.append(("错误", "提示文字超过 16 条（aux.Stringid 最多 16 条），请减少效果或选项"))
    return _use_script(res, tab, script) if script else res


def _use_script(res, tab, script):
    """手写脚本：导出和测试都用这份；积木能读出文字就留着，否则用卡面文字。"""
    from blocks.lua_guard import problems
    res.lua = script
    res.desc = res.desc or (tab.get("data") or {}).get("effect_text", "")
    res.issues.append(("提示", "这张卡用手写脚本，积木不生成脚本"))
    found = problems(script)
    if found:
        res.error = "手写脚本没有通过安全检查：%s" % "；".join(found)
    return res


def text_matches(card_text, generated):
    def norm(s):
        return re.sub(r"\s+", "", (s or "").replace("\r", ""))
    return norm(card_text) == norm(generated)


# ---------------------------------------------------------------- 导出

def manifest(pack, tabs):
    """把一个卡包组装成 ygopack 的清单（内存里的 dict）。"""
    diy = pack_diy(pack)
    cards = []
    for tab in tabs:
        data = tab.get("data") or {}
        cdiy = card_diy(tab)
        entry = {"card": data, "setcodes": list(cdiy.get("setcodes", []))}
        code = card_code(data)
        if code:
            entry["code"] = code
        if cdiy.get("media"):
            entry["media"] = dict(cdiy["media"])
        if cdiy.get("strings"):
            entry["strings"] = dict(cdiy["strings"])
        if cdiy.get("script"):
            entry["script"] = cdiy["script"]
        entry["category"] = cdiy["category"] if "category" in cdiy else auto_category(tab)
        if cdiy.get("alias") and not rule_same_name(cdiy):
            entry["alias"] = cdiy["alias"]      # 异画：效果和原卡一样，引擎直接读原卡脚本
        elif item_count(cdiy["blocks"]) or rule_same_name(cdiy):
            model, rec, _ = full_model(tab)
            entry["effect"] = model
        cards.append(entry)
    return {"name": pack.get("title") or "DIY", "author": diy.get("author", ""), "ot": diy.get("ot", 3),
            "setnames": dict(diy.get("setnames") or {}), "cards": cards}


def assign_codes(tabs, start, step):
    """按卡片顺序分配卡号：返回 [(tab, 新卡号)]，由调用方写进卡片（当前卡要经过编辑器）。"""
    return [(tab, start + i * step) for i, tab in enumerate(tabs)]


def free_code_start(start, step, count, known):
    """卡号段和已有的卡（官方卡、别的扩展包）冲突时，往后按 1000 找第一个整段都没被占用的起点。"""
    s = start
    while any(s + i * step in known for i in range(count)):
        s += 1000
    return s


def next_setcode(setnames, used=()):
    """新字段的编号：从 0xa01 起找第一个没用过的（官方字段目前到 0x2xx，DIY 用高位段）。"""
    taken = {int(k, 16) & 0xfff for k in setnames} | {c & 0xfff for c in used}
    code = 0xa01
    while code in taken:
        code += 1
    return "0x%x" % code
