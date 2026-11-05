"""v0.3 积木：贴近引擎的积木树 → 卡片脚本（Lua）与中文效果文字。

    from blocks import build
    result = build(model)   # {"lua", "desc", "pdesc", "strings", "issues"}，和 effect_model.build 一样

model 是 {"schema": "ygodiy-blocks/0.3", "card": {code, name, kind, subtypes}, "effects": [...], "summon": {...}}。
拼得不完整时 build 抛 compile.CompileError（说明缺什么）。设计见 effect_model/docs/v0.3-积木设计.md。
"""

SCHEMA = "ygodiy-blocks/0.3"


def is_blocks(model):
    return isinstance(model, dict) and model.get("schema") == SCHEMA


TYPE_SPSUMMON = 0x2000000      # 卡片数据里的「不能通常召唤」（引擎看 cdb 的 type，不看脚本）


def type_bits(model):
    """积木对卡片数据 type 的要求：「召唤条件：不能通常召唤」→ TYPE_SPSUMMON。"""
    if not is_blocks(model):
        return 0
    bits = TYPE_SPSUMMON if any(e.get("block") == "summon_rule" and e.get("normal") == "no"
                                for e in model.get("effects", [])) else 0
    for e in model.get("effects", []):          # 灵魂 / 同盟 / 二重：卡片种类上的标记
        if e.get("block") == "monster_trait":
            bits |= {"spirit": 0x200, "union": 0x400, "gemini": 0x800}[e["trait"]]
    return bits


def build(model):
    from .compile import check, compile_full, walk
    from .read import read_full
    issues = [("error", "积木", p) for p in check(model)]
    if any(b["block"] in ("raw", "custom_effect") for b in walk(model.get("effects", []))):
        issues.append(("warning", "积木", "AI 自定义 Lua · 未经积木校验：只做了安全检查，请在沙盒里测试"))
    lua, strings = compile_full(model)
    desc, pdesc = read_full(model)
    if (model.get("card") or {}).get("kind") in ("spell", "trap"):     # aux.IsTypeInText 查的是这个标记
        for word, constant in (("二重怪兽", "TYPE_DUAL"), ("灵魂怪兽", "TYPE_SPIRIT"), ("同盟怪兽", "TYPE_UNION")):
            if word in desc:
                lua += "s.has_text_type=%s\n" % constant
                break
    return {"lua": lua, "desc": desc, "pdesc": pdesc, "strings": strings, "issues": issues}
