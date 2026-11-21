"""卡包的指示物名称、已有引用及改号。"""
import copy
from functools import lru_cache
from itertools import chain
import re

from effect_model.counters import counter_code
from . import store
from .lua_numbers import _LITERAL, _NUMBER, masked_code, rewrite

# 冒号方法省略卡片本身；Card.* 静态调用则多一个卡片参数。
_FIRST = r"(?:EnableCounterPermit|SetCounterLimit|AddCounter|IsCanAddCounter|GetCounter)"
_SECOND = r"(?:RemoveCounter|IsCanRemoveCounter)"
_ARG = r"[^,()\n]+,\s*"
_LUA_COUNTER = re.compile(
    r"(?::" + _FIRST + r"\s*\(\s*|\bCard\." + _FIRST + r"\s*\(\s*" + _ARG
    + r"|:" + _SECOND + r"\s*\(\s*" + _ARG + r"|\bCard\." + _SECOND + r"\s*\(\s*" + _ARG * 2
    + r"|\bDuel\.(?:RemoveCounter|IsCanRemoveCounter|GetCounter)\s*\(\s*" + _ARG * 3
    + r"|\bCard\.GetCounter\s*,\s*)(" + _NUMBER + r")(?=\s*[,\)])"
)


_COUNTER_LIST = re.compile(r"\b(?:counter_place_list|counter_list)\s*=\s*\{([^{}]*)\}")


def _positions(masked):
    spans = {m.span(1) for m in _LUA_COUNTER.finditer(masked)}
    for table in _COUNTER_LIST.finditer(masked):
        spans.update(m.span() for m in _LITERAL.finditer(masked, table.start(1), table.end(1)))
    return spans


def _mentions_counters(text):
    return "Counter" in text or "counter_" in text


def _script_codes(text):
    return _recognized_codes(text) if _mentions_counters(text) else ()


@lru_cache(maxsize=1024)
def _recognized_codes(text):
    masked = masked_code(text)
    return tuple(masked[a:b] for a, b in sorted(_positions(masked)))


def _nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _nodes(item)
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (list, dict)):
                yield from _nodes(child)


def _parts(diy):
    for key in ("blocks", "effect", "script"):
        if diy.get(key):
            yield diy[key]
    if diy.get("tests"):
        yield diy["tests"].get("scenarios", ())


def _number(value):
    try:
        return counter_code(value)
    except ValueError:
        return None


def _values(data):
    if isinstance(data, str):
        yield from _script_codes(data)
        return
    for node in _nodes(data):
        if "counter" in node:
            yield node["counter"]
        if isinstance(node.get("counters"), dict):
            yield from node["counters"]
        for key in ("lua", "helpers", "script"):
            if isinstance(node.get(key), str):
                yield from _script_codes(node[key])


def card_codes(tab):
    return {code for part in _parts(tab.get("diy") or {}) for value in _values(part) if (code := _number(value))}


def used_codes(pack):
    found = set()
    for tab in pack.get("tabs", ()):
        found.update(card_codes(tab))
    return found


def _migrate(diy, old, code):
    def replace(value):
        return code if _number(value) == old else value

    review = False
    if diy.get("script") and _mentions_counters(diy["script"]):
        diy["script"], review = rewrite(diy["script"], replace, _positions)
    for part in (diy.get("blocks"), diy.get("effect"), (diy.get("tests") or {}).get("scenarios")):
        for node in _nodes(part):
            if "counter" in node:
                node["counter"] = replace(node["counter"])
            if isinstance(node.get("counters"), dict):
                node["counters"] = {replace(k): v for k, v in node["counters"].items()}
            for key in ("lua", "helpers", "script"):
                if isinstance(node.get(key), str) and _mentions_counters(node[key]):
                    node[key], uncertain = rewrite(node[key], replace, _positions)
                    review |= uncertain
    return review


def change(pack, old, requested, name, external, used):
    settings = store.pack_diy(pack)
    names = settings["counters"]
    name = name.strip()
    if not name or len(name.splitlines()) != 1 or any(c in name for c in "\t\r\n\x00"):
        raise ValueError("请输入单行指示物名称。")
    if old and old not in names and old not in used:
        raise ValueError("所选指示物已变更，请重新选择。")
    if requested:
        code = counter_code(requested)
    else:
        taken = set(names) | set(external) | used
        # 从 0x100 开始，避开大部分官方常用的小编号。
        code = next((hex(i) for i in chain(range(0x100, 0x10000), range(1, 0x100)) if hex(i) not in taken), None)
        if code is None:
            raise ValueError("指示物编号已全部占用。")
    if code != old and (code in names or (old and code in used)):
        raise ValueError("本包已有指示物使用 %s。" % code)
    if code in external and (code != old or (external[code][1] == "官方" and external[code][0] != name)):
        raise ValueError("%s 属于%s的「%s」，可查找选用，或填写其他编号。" % (code, external[code][1], external[code][0]))
    reviews, updates = [], []
    if old and old != code:
        for tab in pack.get("tabs", ()):
            original = tab.get("diy") or {}
            if not original:
                continue
            updated = dict(original)
            for key in ("blocks", "effect"):
                if key in original:
                    updated[key] = copy.deepcopy(original[key])
            if original.get("tests"):
                tests = dict(original["tests"])
                tests["scenarios"] = copy.deepcopy(tests.get("scenarios", []))
                updated["tests"] = tests
            if _migrate(updated, old, code):
                reviews.append(tab.get("title", ""))
            if updated != original:
                updates.append((tab, updated))
        names.pop(old, None)
    names[code] = name
    store.set_pack_diy(pack, settings)
    for tab, updated in updates:
        store.set_card_diy(tab, updated)
    return code, reviews


def import_card_names(pack, incoming, tabs, external):
    """单卡导入已有包时，只合并这几张卡实际引用的名称。重号只调整被导入卡的引用。"""
    from effect_model.counters import clean_names
    settings = store.pack_diy(pack)
    used = used_codes({"tabs": tabs})
    incoming = {code: name for code, name in clean_names(incoming).items() if code in used}
    if not incoming:
        return []
    temporary = {"tabs": tabs, "diy": {"counters": incoming}}
    taken = used | used_codes(pack)
    reserved = dict(external)
    reserved.update({code: (name, "本包") for code, name in settings["counters"].items()})
    notes = []
    for code, name in incoming.items():
        if code in reserved and reserved[code][0] != name:
            new, review = change(temporary, code, "", name, reserved, taken)
            notes.append("导入的「%s」与%s重号，已在导入卡中将 %s 调整为 %s。" % (name, reserved[code][1], code, new))
            notes.extend(title + " 的手写 Lua 含同值数字，请核对。" for title in review)
    settings["counters"].update(store.pack_diy(temporary)["counters"])
    store.set_pack_diy(pack, settings)
    return notes
