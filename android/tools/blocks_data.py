"""只打包积木目录和中文读法；安卓端复用桌面的文字生成器。"""
import ast
import inspect
import json
import sys
from pathlib import Path

from lessons import block_help, lessons

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from blocks import card_queries, catalog, read
from blocks.compile import one
from effect_model.counters import counter_code, counter_name


def prepare(output):
    help_by_key = block_help()
    blocks = {}
    for key, block in catalog.BLOCKS.items():
        if key.startswith("ls_") or key in {"raw", "custom_effect"}:
            continue
        blocks[key] = dict(label=block.label, kind=block.kind, fields=block.fields,
                           slots=block.slots, initial=block.defaults(), help=help_by_key.get(key, []))
    data = dict(blocks=blocks, codes=[(c["name"], c["zh"]) for c in catalog.effect_codes()],
                chapters=lessons(output))
    (output / "library.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    source = (ROOT / "blocks/read.py").read_text("utf-8")
    tree = ast.parse(source)
    definitions = ["import os, re, json"]
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "catalog":
            for alias in node.names:
                obj = getattr(catalog, alias.name)
                if not callable(obj):
                    definitions.append(f"{alias.name} = {obj!r}")
        if isinstance(node, ast.ImportFrom) and node.module == "card_queries":
            for alias in node.names:
                labels = {k: (v[0],) for k, v in getattr(card_queries, alias.name).items()}
                definitions.append(f"{alias.name} = {labels!r}")
    functions = (catalog.multi_parts, catalog.MultiMap, catalog.events_of, one, counter_code, counter_name)
    definitions.extend(inspect.getsource(f) for f in functions)
    definitions += [f"CODE_NAMES = {dict(data['codes'])!r}", "def code_zh(name): return CODE_NAMES.get(name, name)"]
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)) or getattr(node, "name", "") in {
                "summon_text", "read_full", "read_card"}:
            continue
        definitions.append(ast.get_source_segment(source, node))
    definitions.append('''def render_text(payload):
    effects, name, counters = json.loads(payload)
    VAR_DONE.clear()
    return json.dumps([part_text([e for e in effects if e.get("part") != "pendulum"], name, counters),
                       part_text([e for e in effects if e.get("part") == "pendulum"], name, counters)],
                      ensure_ascii=False)
''')
    (output / "reader.py").write_text("\n\n".join(definitions), "utf-8")
    return len(blocks)
