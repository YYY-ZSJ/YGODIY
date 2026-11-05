"""玩家本机的 Lua 接口资料：社区手册的内容不随程序发布，由 _tools/ai_reference_import.py 导入到设置目录。"""

import json
import re
import zipfile

DATA_FILE = "lua_reference.json"
FUNCTION_LINE = re.compile(r"^●.*?\b((?:Duel|Card|Effect|Group|Debug|aux|Auxiliary)[.:]\w+)\s*\(")
CONSTANT_LINE = re.compile(r"^(\w+)\s*=\s*[^\s-]+[^-]*--\s*(.*\S)")
MAX_DOC_CHARS = 600


def parse_functions(text):
    """手册里 ● 开头的是函数，#● 是已经不存在的，不收。"""
    result, name = {}, None
    for line in text.splitlines():
        m = FUNCTION_LINE.match(line)
        if m:
            name = m.group(1).replace(":", ".").replace("Auxiliary.", "aux.")
            result[name] = {"signature": line[1:].strip(), "doc": ""}
        elif line.startswith(("●", "#")) or not line.strip():
            if line.startswith("●"):
                name = None
        elif name:
            result[name]["doc"] = (result[name]["doc"] + "\n" + line.strip()).strip()[:MAX_DOC_CHARS]
    return result


def parse_constants(text):
    return {m.group(1): m.group(2) for m in map(CONSTANT_LINE.match, text.splitlines()) if m and re.search(r"[一-鿿]", m.group(2))}


def _sheet_rows(archive, index, strings):
    xml = archive.read("xl/worksheets/sheet%d.xml" % index).decode("utf-8")
    for row in re.findall(r"<row [^>]*>(.*?)</row>", xml, re.S):
        yield [strings[int(value)] for value in re.findall(r't="s"[^>]*><v>(\d+)</v>', row)]


def parse_tables(path):
    """教程表格的附录：能力表（代码、意思、Value 的意思）和时点表（时点、中文）。"""
    with zipfile.ZipFile(path) as archive:
        names = re.findall(r'<sheet [^>]*name="([^"]+)"', archive.read("xl/workbook.xml").decode("utf-8"))
        shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
        strings = [re.sub(r"<[^>]+>", "", item).replace("&#10;", " ").replace("&amp;", "&").strip() for item in re.findall(r"<si>(.*?)</si>", shared, re.S)]
        abilities, events = {}, {}
        for row in _sheet_rows(archive, names.index("附录·能力表") + 1, strings):
            if len(row) >= 3 and row[0].startswith("EFFECT_"):
                abilities[row[0]] = {"meaning": row[1], "value": row[2]}
        for row in _sheet_rows(archive, names.index("附录·时点表") + 1, strings):
            for key, meaning in zip(row[0::2], row[1::2]):
                if key.startswith("EVENT_"):
                    events[key] = meaning
    return abilities, events


def build(functions_text, constants_text, tables_path):
    abilities, events = parse_tables(tables_path)
    return {"functions": parse_functions(functions_text), "constants": parse_constants(constants_text), "abilities": abilities, "events": events}


def load(path):
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError):
        return {}
