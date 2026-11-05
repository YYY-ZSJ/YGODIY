"""从实际目录生成全局不变的参数参考；枚举表共用，避免重复占用上下文。"""

import json
from pathlib import Path

from blocks.catalog import BLOCKS, effect_codes

SAMPLES = (100009702, 100009704, 100009708, 100009711, 100009716, 100009742, 100009770, 100009773)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def full_catalog():
    enums, lines = {}, []
    for block in sorted(BLOCKS.values(), key=lambda item: item.key):
        if block.key in ("raw", "custom_effect"):
            continue
        fields, defaults = {}, block.defaults()
        for name, label, kind, option in block.fields:
            value = [label, kind, defaults[name]]
            if kind in ("choice", "multi", "code"):
                options = option if kind != "code" else [(row["name"], row["zh"]) for row in effect_codes()]
                key = encoded(options)
                if key not in enums:
                    enums[key] = "E%d" % (len(enums) + 1)
                value.append(enums[key])
            fields[name] = value
        slots = {name: [label, accepts, count, only] for name, label, accepts, count, only in block.slots}
        row = {"name": block.label, "kind": block.kind, "category": block.category, "fields": fields, "slots": slots}
        if block.hint:
            row["hint"] = block.hint
        lines.append(block.key + " | " + encoded(row))
    header = ["YGODIY_BLOCK_REFERENCE_V2 · 积木完整目录", "字段=[中文说明,类型,省略时默认值,可选值表编号(若有)]；枚举表项=[实际值,中文名]。",
              "每个块必填block；标量参数可省略用默认值。槽一律数组，槽项=[说明,接收类型,最多块数(0不限),限定块ID或null]。",
              "目录没有声明每个槽的最少数量；空槽在结构上可保留，编译可能要求补齐，见格式规范。不要把最多1块误解为必须1块。",
              "可选值表：" + encoded({value: json.loads(key) for key, value in enums.items()})]
    return "\n".join(header + lines)


def examples():
    rows = json.loads(Path(__file__).with_name("block_examples.json").read_text(encoding="utf-8"))
    lines = ["完整效果树样例（来自blocks/samples；只提交schema和effects，card元数据不可提交；未删子树）。"]
    for row in rows:
        lines += [row["name"] + "：" + row["text"], encoded(row["model"])]
    return "\n".join(lines)


def reference():
    rules = Path(__file__).with_name("block_guide.md").read_text(encoding="utf-8")
    return "\n\n".join((rules, full_catalog(), examples()))
