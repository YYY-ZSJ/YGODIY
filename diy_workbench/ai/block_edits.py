"""复用积木目录校验 JSON；自定义 Lua 只能经 write_custom_lua 写入，这里只允许原样保留。"""

import copy
import re

from blocks import SCHEMA
from blocks.catalog import BLOCKS, effect_codes, fits, multi_parts
from blocks.compile import walk

MAX_BLOCKS = 200
MAX_DEPTH = 20
CUSTOM_BLOCKS = ("raw", "custom_effect")


def custom_nodes(model):
    return [node for node in walk((model or {}).get("effects", [])) if node.get("block") in CUSTOM_BLOCKS]


def _custom_key(node):
    return node.get("block"), str(node.get("lua") or ""), str(node.get("helpers") or "")


def _detail(block):
    return {"id": block.key, "name": block.label, "kind": block.kind,
            "fields": block.fields, "slots": block.slots, "defaults": block.defaults(), "hint": block.hint}


def catalog(query="", limit=20, ids=None):
    if ids is not None:
        wanted = list(dict.fromkeys(ids))
        return {"blocks": [_detail(BLOCKS[key]) for key in wanted if key in BLOCKS and key not in CUSTOM_BLOCKS],
                "unknown": [key for key in wanted if key not in BLOCKS or key in CUSTOM_BLOCKS]}
    exact = BLOCKS.get(query)
    found = ([exact] if exact and exact.key not in CUSTOM_BLOCKS else
             [block for block in BLOCKS.values() if block.key not in CUSTOM_BLOCKS and query and
              query.casefold() in (block.key + block.label).casefold()])
    if len(found) != 1:
        return {"matches": [{"id": block.key, "name": block.label} for block in found[:limit]],
                "hint": "固定前缀有完整参数；遗漏的细节用ids一次查询多个id，query兼容单块查询。"}
    return _detail(found[0])


def compact_catalog():
    from .block_reference import full_catalog
    return full_catalog()


def _parameter(block, name, kind, option, value, path):
    if kind == "choice" and isinstance(value, (str, int, bool)) and value in dict(option):
        return value
    if kind == "multi" and isinstance(value, str) and all(v in dict(option) for v in multi_parts(value, dict(option))):
        return value
    if kind == "int" and type(value) is int and -99999999 <= value <= 99999999:
        return value
    if kind == "code" and isinstance(value, str) and value in {row["name"] for row in effect_codes()}:
        return value
    if kind == "lua" and isinstance(value, str) and len(value) <= 20000 and "\x00" not in value:
        return value
    if kind == "text" and isinstance(value, str) and len(value) <= 500 and "\x00" not in value:
        if name == "as" or (block.key in ("target", "var") and name == "name"):
            if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,31}", value):
                raise ValueError(path + '：变量名须匹配[A-Za-z_][A-Za-z_0-9]{0,31}，例如"A"。')
        if name == "setcode" and not re.fullmatch(r"0x[0-9a-fA-F]{1,4}", value):
            raise ValueError(path + '：字段编号须为0x开头的十六进制字符串，例如"0xa01"；名字不能代替编号。')
        return value
    expected = {"int": "整数(-99999999～99999999)", "text": "不含空字符、最多500字的字符串"}.get(kind, kind)
    if kind in ("choice", "multi"):
        expected = "可选值=" + ",".join(repr(key) for key, _ in option)
        if kind == "multi":
            expected += '；多选用+连接为字符串，例如"' + "+".join(str(key) for key, _ in option[:2]) + '"'
    elif kind == "code":
        expected = "目录中effect code可选值，例如EFFECT_UPDATE_ATTACK"
    raise ValueError("%s：积木%s的参数%s无效（%r）；%s。" % (path, block.label, name, value, expected))


def validate_tree(model, previous=None, custom=()):
    if not isinstance(model, dict) or model.get("schema") != SCHEMA or not isinstance(model.get("effects"), list):
        raise ValueError('model：必填schema="ygodiy-blocks/0.3"与effects数组，例如{"schema":"ygodiy-blocks/0.3","effects":[]}。')
    retained = {key: copy.deepcopy(value) for key, value in (previous or {}).items() if key not in ("schema", "effects")}
    for key, value in model.items():
        if key not in ("schema", "effects") and (key not in retained or retained[key] != value):
            raise ValueError("model.%s：只允许修改effects，不能在积木树内写入卡片资料或改旧元数据。" % key)
    count = [0]
    allowed = {_custom_key(node) for node in custom}

    def visit(node, depth, path, slot=None):
        count[0] += 1
        if depth > MAX_DEPTH or count[0] > MAX_BLOCKS:
            raise ValueError(path + "：积木树超过20层或200块，请拆分修改。")
        if not isinstance(node, dict) or not isinstance(node.get("block"), str) or node["block"] not in BLOCKS:
            raise ValueError(path + '.block：须为目录中已开放的积木ID，例如"effect"；不接受以type代替block。')
        if node["block"] in CUSTOM_BLOCKS and _custom_key(node) not in allowed:
            raise ValueError(path + "：自定义 Lua 只能用write_custom_lua写入，这里只能原样保留已有的。")
        block = BLOCKS[node["block"]]
        if (slot is None and block.kind != "hat") or (slot is not None and not fits(slot, block.key)):
            expected = slot[2] if slot else "hat"
            if slot and slot[4]:
                expected += "，限定积木=" + ",".join(slot[4])
            raise ValueError("%s：积木%s的类型是%s；此处接收%s。" % (path, block.key, block.kind, expected))
        names = {name for name, *_ in block.fields} | {part[0] for part in block.slots} | {"block"}
        if set(node) - names:
            bad = sorted(set(node) - names)[0]
            raise ValueError("%s.%s：积木%s没有此字段；可用键=%s。" % (path, bad, block.key, ",".join(sorted(names))))
        result = block.defaults()
        for name, _, kind, option in block.fields:
            result[name] = _parameter(block, name, kind, option, node.get(name, result[name]), path + "." + name)
        for child_slot in block.slots:
            children = node.get(child_slot[0], [])
            if not isinstance(children, list) or (child_slot[3] == 1 and len(children) > 1):
                examples = {"cards": "this_card", "cond": "phase", "number": "num", "filter": "f_kind", "stmt": "draw", "target": "take_target", "option": "option"}
                example = examples[child_slot[2]]
                if not fits(child_slot, example):
                    example = next(key for key in sorted(BLOCKS) if key not in CUSTOM_BLOCKS and fits(child_slot, key))
                raise ValueError(path + "." + child_slot[0] + "：槽必须是" + child_slot[2] + "积木的数组" +
                                 ("，最多1块" if child_slot[3] == 1 else "") + '；数组格式例如[{"block":"' + example + '"}]，按目录补其参数和槽。')
            result[child_slot[0]] = [visit(child, depth + 1, "%s.%s[%d]" % (path, child_slot[0], index), child_slot)
                                   for index, child in enumerate(children)]
        return result

    return dict(retained, schema=SCHEMA, effects=[visit(node, 1, "effects[%d]" % index) for index, node in enumerate(model["effects"])])
