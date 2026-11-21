"""当前卡包的字段改号，卡片、效果积木与测试布场使用同一映射。"""
import copy
import re

from . import store

from .lua_numbers import _LITERAL, _NUMBER, rewrite

_CALL = re.compile(r"\b(?:Is(?:Previous|Fusion|Link)?SetCard|IsSetCardExcept|AddSetcode)\s*[(,]\s*(" + _NUMBER + r")\b")
_LIST = re.compile(r"\blisted_series\s*=\s*\{([^{}]*)\}")


def field_number(value):
    text = str(value).strip()
    if re.fullmatch(_NUMBER, text):
        number = int(text, 16 if text.lower().startswith("0x") else 10)
        if 0 < number <= 0xffff and number & 0xfff:
            return number
    raise ValueError("字段编号须为 1～65535，基础编号不能为 0。可填十进制或 0x 开头的十六进制。")


def field_key(value):
    """将积木中手填的十进制或十六进制编号对应到卡包定义，允许输入尚未完成。"""
    try:
        return hex(field_number(value))
    except ValueError:
        return ""


def base_occupied(code, used):
    return any((number & 0xfff) == (code & 0xfff) for number in used)


def _field_positions(masked):
    spans = {m.span(1) for m in _CALL.finditer(masked)}
    for group in _LIST.finditer(masked):
        spans.update(m.span() for m in _LITERAL.finditer(masked, group.start(1), group.end(1)))
    return spans


def _migrate(node, replace, old, old_name, name):
    review = False
    if isinstance(node, list):
        for item in node:
            review |= _migrate(item, replace, old, old_name, name)
    elif isinstance(node, dict):
        if "setcode" in node and field_key(node["setcode"]) == old:
            if node.get("name") == old_name or (node.get("block") in ("f_set", "f_prev_set") and not node.get("name")):
                node["name"] = name
            if node.get("set") == old_name:
                node["set"] = name
        for attr, value in node.items():
            if attr == "setcode":
                node[attr] = replace(value)
            elif attr == "setcodes" and isinstance(value, list):
                node[attr] = [replace(v) for v in value]
            elif attr in ("script", "lua", "helpers") and isinstance(value, str):
                node[attr], uncertain = rewrite(value, replace, _field_positions)
                review |= uncertain
            elif attr != "results":
                review |= _migrate(value, replace, old, old_name, name)
    return review


def change(pack, old, requested, name, used):
    settings = store.pack_diy(pack)
    names = settings["setnames"]
    if not isinstance(name, str) or not name.strip() or len(name.splitlines()) != 1 or any(ch in name for ch in "\t\r\n\x00"):
        raise ValueError("请输入单行字段名称。")
    if old and old not in names:
        raise ValueError("所选字段已经发生变化，请重新选择。")
    code = field_number(requested or store.next_setcode(names, used))
    key = hex(code)
    previous = field_number(old) if old else None
    if key in names and key != old:
        raise ValueError("本包已定义编号 %s。" % key)
    if (previous is None or (previous & 0xfff) != (code & 0xfff)) and base_occupied(code, used):
        raise ValueError("编号 %s 的基础编号已被官方或其他卡包占用。" % key)

    def replace(value):
        try:
            current = field_number(value)
        except ValueError:
            return value
        if current == previous and current != code:
            return key
        if previous is not None and previous < 0x1000 and code < 0x1000 and current & 0xfff == previous and previous != code:
            return hex((current & 0xf000) | code)
        return value

    mappings = {}
    for original, title in names.items():
        mapped, label = (key, name) if original == old else (replace(original), title)
        if mapped in mappings:
            raise ValueError("调整后的子字段与本包另一项重号。")
        mappings[mapped] = label
    mappings[key] = name
    changes, reviews = [], []
    if previous is not None:
        for tab in pack.get("tabs", []):
            original = tab.get("diy") or {}
            updated = copy.deepcopy(original)
            if _migrate(updated, replace, hex(previous), names[old], name):
                reviews.append(tab.get("title", ""))
            if updated != original:
                changes.append((tab, updated))
    settings["setnames"] = mappings
    store.set_pack_diy(pack, settings)
    for tab, updated in changes:
        store.set_card_diy(tab, updated)
    return reviews
