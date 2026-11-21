"""仅改写已确认参数位置的 Lua 编号，注释、字符串和其他数字原样保留。"""
import re

_NUMBER = r"(?:0[xX][0-9a-fA-F]+|\d+)"
_LUA_TEXT = re.compile(r"--\[(?P<c>=*)\[.*?\](?P=c)\]|--[^\n]*|\[(?P<s>=*)\[.*?\](?P=s)\]|"
                       r'"(?:\\.|[^"\\])*"' r"|'(?:\\.|[^'\\])*'", re.S)
_LITERAL = re.compile(r"(?<![\w.])" + _NUMBER + r"(?![\w.])")


def masked_code(text):
    return _LUA_TEXT.sub(lambda m: " " * len(m.group()), text)


def rewrite(text, replace, positions):
    masked = masked_code(text)
    spans = positions(masked)
    review = False
    edits = []
    for match in _LITERAL.finditer(masked):
        value = match.group()
        new = replace(value)
        if new != value:
            if match.span() in spans:
                edits.append((match.start(), match.end(), new))
            else:
                review = True
    for start, end, value in reversed(edits):
        text = text[:start] + value + text[end:]
    return text, review
