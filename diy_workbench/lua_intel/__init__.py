"""脚本页的接口资料：函数说明、常量和代码片段。资料来自开源项目 DataEditorY 的 resources/lua-intel。"""

import json
from pathlib import Path
import re

from diy_workbench.ai.lua_reference import parse_constants, parse_functions

FOLDER = Path(__file__).parent
MAX_ITEMS = 200
OBJECT_TYPES = ("Card", "Effect", "Group")
NAME_TYPES = {"c": "Card", "tc": "Card", "rc": "Card", "ec": "Card", "e": "Effect", "te": "Effect", "re": "Effect",
              "g": "Group", "sg": "Group", "eg": "Group", "mg": "Group", "tg": "Group"}
PLACEHOLDER = re.compile(r"\$\{?\d+(?::[^}]*)?\}?")


class Entry:
    def __init__(self, name, kind, detail, doc="", insert=None):
        self.name, self.kind, self.detail, self.doc = name, kind, detail, doc
        self.insert = insert if insert is not None else name


class LuaIntel:
    def __init__(self):
        functions = parse_functions((FOLDER / "_functions.txt").read_text(encoding="utf-8-sig"))
        constant_text = (FOLDER / "constant.lua").read_text(encoding="utf-8-sig", errors="replace")
        meanings = parse_constants(constant_text)
        self.functions = [Entry(name, "函数", row["signature"], row["doc"]) for name, row in sorted(functions.items())]
        self.constants = [Entry(name, "常量", value, meanings.get(name, ""))
                          for name, value in re.findall(r"^([A-Z][A-Z0-9_]+)\s*=\s*([^\s-]+)", constant_text, re.M)]
        snippets = json.loads((FOLDER / "snippets.json").read_text(encoding="utf-8"))
        self.snippets = [Entry(row["prefix"], "片段", row.get("description", ""), "\n".join(row["body"]), "\n".join(row["body"])) for row in snippets.values()]
        self.by_name = {entry.name: entry for entry in self.functions + self.constants}
        self.by_method = {}
        for entry in self.functions:
            self.by_method.setdefault(entry.name.split(".")[-1], []).append(entry)

    def object_type(self, code, name):
        """推断变量是 Card、Effect 还是 Group：看最近一次赋值的函数返回类型，再看常用变量名。"""
        for found in reversed(list(re.finditer(r"\b%s\s*=\s*([A-Za-z_][\w.:]*)\(" % re.escape(name), code))):
            for entry in self.lookup(found.group(1)):
                kind = re.match(r"\w+", entry.detail)
                if kind and kind.group() in OBJECT_TYPES:
                    return kind.group()
        return NAME_TYPES.get(name)

    def complete(self, prefix, owner=None):
        """prefix 是光标前的词：#片段、Duel.xxx、obj:xxx 或普通词；owner 是 obj 的类型，不知道就列出全部方法。"""
        if prefix.startswith("#"):
            return [entry for entry in self.snippets if entry.name.startswith(prefix)][:MAX_ITEMS]
        if ":" in prefix:
            word = prefix.rsplit(":", 1)[1].lower()
            owner_filter = (owner,) if owner else None
            seen, result = set(), []
            for entry in self.functions:
                entry_owner, _, short = entry.name.rpartition(".")
                if entry_owner in (owner_filter or OBJECT_TYPES) and short.lower().startswith(word) and short not in seen:
                    seen.add(short)
                    result.append(Entry(short, "方法", entry.detail, entry.doc))
            return result[:MAX_ITEMS]
        word = prefix.lower()
        return [entry for entry in self.functions + self.constants if entry.name.lower().startswith(word)][:MAX_ITEMS]

    def lookup(self, word):
        word = word.replace(":", ".")
        if word in self.by_name:
            return [self.by_name[word]]
        return self.by_method.get(word.split(".")[-1], [])

    def search(self, text):
        text = text.strip().lower()
        entries = self.functions + self.constants + self.snippets
        return [entry for entry in entries if not text or text in entry.name.lower() or text in entry.doc.lower() or text in entry.detail.lower()][:MAX_ITEMS]

    def unknown_calls(self, code):
        """Duel.Xxx 这种静态调用里，资料里没有的接口：(行号, 名字)。"""
        result = []
        for number, line in enumerate(code.splitlines(), 1):
            line = re.sub(r"--.*$", "", line)
            for owner, name in re.findall(r"\b(Duel|Effect|Group|Card|aux)\.(\w+)\s*\(", line):
                if "%s.%s" % (owner, name) not in self.by_name:
                    result.append((number, "%s.%s" % (owner, name)))
        return result


def expand(snippet):
    """去掉 $1 这类占位符，返回 (文字, 第一个占位符的位置)。"""
    first = PLACEHOLDER.search(snippet)
    position = first.start() if first else len(snippet)
    return PLACEHOLDER.sub(lambda m: m.group().split(":", 1)[1].rstrip("}") if ":" in m.group() else "", snippet), position


_intel = None


def intel():
    global _intel
    if _intel is None:
        _intel = LuaIntel()
    return _intel
