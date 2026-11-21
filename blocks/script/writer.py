"""把脚本积木生成 Lua。每个字段只接受它对应的标识符、字面量或运算符。"""

import re

from ..lua_guard import FORBIDDEN
from .calls import BY_BLOCK, ENGINE_TABLES, arguments
from .grammar import ATOMS, NUMBER, PRECEDENCE, RIGHT, UNARY, UNARY_LEVEL, ScriptError, is_name, name_list, tokens

CALLABLE = {"ls_call", "ls_method", "ls_engine"} | BY_BLOCK.keys()
PREFIX = {"ls_name", "ls_member", "ls_index", "ls_parens"} | CALLABLE
VARIABLES = {"ls_name", "ls_member", "ls_index"}


def only(node, slot):
    children = node.get(slot, [])
    if len(children) != 1:
        raise ScriptError("%s 的 %s 槽需要一块积木" % (node["block"], slot))
    return children[0]


def identifier(value):
    if not is_name(value):
        raise ScriptError("无效的标识符：%r" % value)
    return value


class Writer:
    def __init__(self, program, code):
        original = str(program.get("code") or "")
        self.original = original if code and original and original != str(code) else ""
        self.target = str(code)
        self.indent = 0
        self.loops = 0
        self.varargs = True   # Lua 顶层脚本可接收可变参数

    def name(self, value):
        identifier(value)
        if self.original and value == "c" + self.original:
            return "c" + self.target
        return value

    def names(self, text, **options):
        return ", ".join(n if n == "..." else self.name(n) for n in name_list(text, **options))

    def exprs(self, n, slot):
        return ", ".join(self.expr(v) for v in n.get(slot, []))

    def prefix(self, n):
        value = self.expr(n)
        return value if n["block"] in PREFIX else "(" + value + ")"

    def api(self, n):
        api = BY_BLOCK[n["block"]]
        callee = self.prefix(only(n, "receiver")) + api if api.startswith(":") else api
        slots = [n.get("arg%d" % i, []) for i in range(len(arguments(api)))]
        while slots and not slots[-1] and not n.get("more"):
            slots.pop()
        if any(len(slot) != 1 for slot in slots):
            raise ScriptError("%s 的参数中间有空槽，请填入数值或 nil" % api)
        args = [self.expr(slot[0]) for slot in slots] + [self.expr(arg) for arg in n.get("more", [])]
        return callee + "(" + ", ".join(args) + ")"

    def expr(self, n, minimum=0):
        k = n["block"]
        if k in BY_BLOCK:
            return self.api(n)
        if k == "ls_binary":
            op = n.get("op", "")
            if op not in PRECEDENCE:
                raise ScriptError("请选择二元运算")
            level = PRECEDENCE[op]
            left = self.expr(only(n, "left"), level + (op in RIGHT))
            right = self.expr(only(n, "right"), level + (op not in RIGHT))
            value = left + " " + op + " " + right
            return "(" + value + ")" if level < minimum else value
        if k == "ls_unary":
            op = n.get("op", "")
            if op not in UNARY:
                raise ScriptError("请选择一元运算")
            value = op + " " + self.expr(only(n, "value"), UNARY_LEVEL)
            return "(" + value + ")" if UNARY_LEVEL < minimum else value
        if k == "ls_name":
            return self.name(n["value"])
        if k == "ls_number":
            v = str(n["value"])
            if v.startswith("-") and NUMBER.fullmatch(v[1:]):
                return self.expr({"block": "ls_unary", "op": "-", "value": [{"block": "ls_number", "value": v[1:]}]}, minimum)
            if not NUMBER.fullmatch(v):
                raise ScriptError("无效的数值常量：%r" % v)
            return self.target if self.original and v == self.original else v
        if k == "ls_atom" and n["value"] in ATOMS:
            if n["value"] == "..." and not self.varargs:
                raise ScriptError("此函数需要在参数列表末尾声明 ... 才能使用可变参数")
            return n["value"]
        if k == "ls_string":
            v = n["value"]
            if not v.startswith(("'", '"', "[")) or list(tokens(v)) != [v] or v == "[":
                raise ScriptError("文本常量需要完整的一对引号或长字符串括号")
            return v
        if k == "ls_parens":
            return "(" + self.expr(only(n, "value")) + ")"
        if k in ("ls_member", "ls_method", "ls_index"):
            owner = self.prefix(only(n, "owner"))
            if k == "ls_index":
                return owner + "[" + self.expr(only(n, "key")) + "]"
            name = identifier(n["name"])
            return owner + "." + name if k == "ls_member" else owner + ":" + name + "(" + self.exprs(n, "args") + ")"
        if k == "ls_call":
            return self.prefix(only(n, "callee")) + "(" + self.exprs(n, "args") + ")"
        if k == "ls_engine":
            table, dot, name = n.get("api", "").partition(".")
            if not dot or table not in ENGINE_TABLES or not is_name(name):
                raise ScriptError("请选择有效的对局接口，例如 Duel.GetTurnPlayer")
            return table + "." + name + "(" + self.exprs(n, "args") + ")"
        if k == "ls_table":
            return "{" + ", ".join(self.field(v) for v in n.get("fields", [])) + "}"
        if k == "ls_lambda":
            return self.function("function", n)
        raise ScriptError("此处需要脚本表达式：%s" % k)

    def field(self, n):
        value = self.expr(only(n, "value"))
        if n["block"] == "ls_item":
            return value
        if n["block"] == "ls_named_field":
            return identifier(n["name"]) + " = " + value
        if n["block"] == "ls_key_field":
            return "[" + self.expr(only(n, "key")) + "] = " + value
        raise ScriptError("表中需要放入表项")

    def lines(self, statements):
        lines = []
        for i, n in enumerate(statements):
            if n["block"] == "ls_return" and i != len(statements) - 1:
                raise ScriptError("返回值必须放在所在语句块的最后")
            line = self.statement(n)
            # 避免下一条以左括号起头的语句，被 Lua 拼成上一条语句的函数调用。
            if line.startswith("(") and lines:
                line = ";" + line
            lines.append("\t" * self.indent + line)
        return "\n".join(lines)

    def body(self, n, head, tail="end", loop=False):
        self.indent += 1
        self.loops += loop
        try:
            body = self.lines(n.get("body", []))
        finally:
            self.indent -= 1
            self.loops -= loop
        return head + "\n" + (body + "\n" if body else "") + "\t" * self.indent + tail

    def function(self, head, n):
        params = self.names(n.get("params", ""), varargs=True, allow_empty=True)
        outer = self.loops, self.varargs
        self.loops, self.varargs = 0, params.endswith("...")
        try:
            return self.body(n, head + "(" + params + ")")
        finally:
            self.loops, self.varargs = outer

    def statement(self, n):
        k = n["block"]
        if k in ("ls_function", "ls_local_function"):
            parts = re.split(r"([.:])", n["name"])
            if k == "ls_local_function" and len(parts) != 1 or ":" in parts[:-2]:
                raise ScriptError("函数名的路径无效")
            parts[0] = self.name(parts[0])
            for part in parts[2::2]:
                identifier(part)
            head = "local function " if k == "ls_local_function" else "function "
            return self.function(head + "".join(parts), n)
        if k == "ls_local":
            lhs = self.names(n.get("names", ""))
            rhs = self.exprs(n, "values")
            return "local " + lhs + (" = " + rhs if rhs else "")
        if k == "ls_assign":
            targets = n.get("targets", [])
            if not targets or any(v["block"] not in VARIABLES for v in targets) or not n.get("values"):
                raise ScriptError("赋值需要可写的变量及右侧表达式")
            return self.exprs(n, "targets") + " = " + self.exprs(n, "values")
        if k == "ls_run":
            call = only(n, "call")
            if call["block"] not in CALLABLE:
                raise ScriptError("执行调用的槽中需要函数或引擎调用")
            return self.expr(call)
        if k == "ls_return":
            values = self.exprs(n, "values")
            return "return" + (" " + values if values else "")
        if k == "ls_if":
            out = self.body(n, "if " + self.expr(only(n, "test")) + " then", "")
            branches = n.get("branches", [])
            for i, branch in enumerate(branches):
                if branch["block"] == "ls_elseif":
                    head = "elseif " + self.expr(only(branch, "test")) + " then"
                elif branch["block"] == "ls_else" and i == len(branches) - 1:
                    head = "else"
                else:
                    raise ScriptError("否则分支只能出现在条件分支的最后")
                out += self.body(branch, head, "")
            return out + "end"
        if k == "ls_for_in":
            if not n.get("values"):
                raise ScriptError("遍历循环缺少迭代器")
            head = "for " + self.names(n["names"]) + " in " + self.exprs(n, "values") + " do"
            return self.body(n, head, loop=True)
        if k == "ls_for":
            bounds = [self.expr(only(n, key)) for key in ("start", "stop")]
            if n.get("step"):
                bounds.append(self.expr(only(n, "step")))
            return self.body(n, "for " + self.name(n["name"]) + " = " + ", ".join(bounds) + " do", loop=True)
        if k == "ls_while":
            return self.body(n, "while " + self.expr(only(n, "test")) + " do", loop=True)
        if k == "ls_repeat":
            return self.body(n, "repeat", "until " + self.expr(only(n, "test")), loop=True)
        if k == "ls_scope":
            return self.body(n, "do")
        if k == "ls_break":
            if not self.loops:
                raise ScriptError("退出循环只能放在当前函数的循环中")
            return "break"
        if k == "ls_goto":
            return "goto " + identifier(n["name"])
        if k == "ls_label":
            return "::" + identifier(n["name"]) + "::"
        raise ScriptError("语句槽中不能放 %s" % k)


def render(program, code=0):
    out = Writer(program, code).lines(program.get("body", [])) + "\n"
    words = list(tokens(out))
    bad = {w for i, w in enumerate(words) if w in FORBIDDEN and not (w == "Debug" and words[i + 1:i + 3] == [".", "Message"])}
    if bad:
        raise ScriptError("脚本中包含工作台限制的接口：" + "、".join(sorted(bad)))
    return out
