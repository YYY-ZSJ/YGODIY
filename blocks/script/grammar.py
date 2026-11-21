"""实卡使用的 Lua 词法与运算符优先级（Lua 5.3/5.4）。"""

import re


class ScriptError(ValueError):
    pass


KEYWORDS = set("and break do else elseif end false for function goto if in local nil not or repeat return then true until while".split())
NAME = re.compile(r"[a-zA-Z_]\w*", re.ASCII)
NUMBER = re.compile(r"(?:0[xX](?:[\da-fA-F]+(?:\.[\da-fA-F]*)?|\.[\da-fA-F]+)(?:[pP][+-]?\d+)?|(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", re.ASCII)
SHORT_STRING = r"""'(?:\\z\s*|\\(?:\r\n|[\s\S])|[^'\\\r\n])*'|"(?:\\z\s*|\\(?:\r\n|[\s\S])|[^"\\\r\n])*" """
LEX = re.compile(
    r"(?P<long>(?P<comment>--)?\[(?P<equals>=*)\[)|(?P<skip>--[^\r\n]*|\s+)|"
    + "(?P<string>" + SHORT_STRING.strip() + ")|(?P<number>" + NUMBER.pattern + ")|"
    + r"(?P<name>[a-zA-Z_]\w*)|(?P<symbol>\.\.\.|//|<<|>>|\.\.|==|~=|<=|>=|::|[+\-*/%^#&~|<>=(){}\[\];:,.])",
    re.ASCII)
PRECEDENCE = {op: level for level, ops in enumerate(
    (("or",), ("and",), ("==", "~=", "<", ">", "<=", ">="), ("|",), ("~",), ("&",),
     ("<<", ">>"), ("..",), ("+", "-"), ("*", "/", "//", "%")), 1) for op in ops}
UNARY_LEVEL = 11
PRECEDENCE["^"] = 12
RIGHT = {"^", ".."}
UNARY = ("not", "#", "-", "~")
ATOMS = ("true", "false", "nil", "...")


def is_name(word):
    return isinstance(word, str) and NAME.fullmatch(word) and word not in KEYWORDS


def tokens(source, positions=None):
    i, end = 0, len(source)
    while i < end:
        m = LEX.match(source, i)
        if not m:
            raise ScriptError("第 %d 行有无法识别的符号 %r" % (1 + source.count("\n", 0, i), source[i:i + 1]))
        start, i = i, m.end()
        if m.group("long"):
            close = "]" + m.group("equals") + "]"
            i = source.find(close, i)
            if i < 0:
                raise ScriptError("第 %d 行的长字符串或注释没有结束" % (1 + source.count("\n", 0, start)))
            i += len(close)
            if m.group("comment"):
                continue
        elif m.group("skip"):
            continue
        if positions is not None:
            positions.append(start)
        yield source[start:i]


def name_list(text, varargs=False, allow_empty=False):
    parts = [s.strip() for s in text.split(",")] if text.strip() else []
    if not parts and not allow_empty:
        raise ScriptError("请填写变量名")
    for i, name in enumerate(parts):
        if not is_name(name) and not (varargs and name == "..." and i == len(parts) - 1):
            raise ScriptError("变量名或参数无效：%r" % name)
    return parts
