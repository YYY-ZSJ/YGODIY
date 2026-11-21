"""把卡片 Lua 还原成目录中真实可编辑的积木。遇到不支持的语法报告行号。"""

from .calls import CALLS, ENGINE_TABLES, call_node
from .grammar import ATOMS, NUMBER, PRECEDENCE, RIGHT, UNARY, UNARY_LEVEL, ScriptError, is_name, tokens


def node(kind, **values):
    return {"block": "ls_" + kind, **values}


class Parser:
    def __init__(self, source):
        self.source = source
        self.offsets = []
        self.words = list(tokens(source, self.offsets)) + ["", ""]
        self.i = 0

    @property
    def word(self):
        return self.words[self.i]

    def take(self):
        word = self.word
        if not word:
            self.fail("脚本提前结束")
        self.i += 1
        return word

    def accept(self, word):
        if self.word == word:
            self.i += 1
            return True
        return False

    def expect(self, word):
        if not self.accept(word):
            self.fail("需要 %s，读到 %r" % (word, self.word))

    def fail(self, message):
        offset = self.offsets[self.i] if self.i < len(self.offsets) else len(self.source)
        raise ScriptError("第 %d 行：%s" % (1 + self.source.count("\n", 0, offset), message))

    def name(self):
        if not is_name(self.word):
            self.fail("需要变量或函数名，读到 %r" % self.word)
        return self.take()

    def names(self):
        names = [self.name()]
        while self.accept(","):
            names.append(self.name())
        return ", ".join(names)

    def function_body(self):
        self.expect("(")
        params = []
        if self.word != ")":
            while True:
                if self.accept("..."):
                    params.append("...")
                    break
                params.append(self.name())
                if not self.accept(","):
                    break
        self.expect(")")
        return {"params": ", ".join(params), "body": self.body_end()}

    def exprs(self, first=None):
        values = [self.expr() if first is None else first]
        while self.accept(","):
            values.append(self.expr())
        return values

    def expr(self, minimum=1):
        w = self.word
        if w in UNARY:
            self.take()
            left = node("unary", op=w, value=[self.expr(UNARY_LEVEL)])
        elif w == "function":
            self.take()
            left = node("lambda", **self.function_body())
        elif w == "{":
            left = self.table()
        elif w in ATOMS:
            left = node("atom", value=self.take())
        elif NUMBER.fullmatch(w):
            left = node("number", value=self.take())
        elif w.startswith(("'", '"', "[")):
            left = node("string", value=self.take())
        else:
            left = self.prefix()
        while PRECEDENCE.get(self.word, 0) >= minimum:
            op = self.take()
            right = self.expr(PRECEDENCE[op] + (op not in RIGHT))
            left = node("binary", op=op, left=[left], right=[right])
        return left

    def prefix(self):
        if self.accept("("):
            left = node("parens", value=[self.expr()])
            self.expect(")")
        else:
            left = node("name", value=self.name())
        while True:
            if self.accept("."):
                left = node("member", owner=[left], name=self.name())
            elif self.accept("["):
                left = node("index", owner=[left], key=[self.expr()])
                self.expect("]")
            elif self.accept(":"):
                method = self.name()
                args = self.args()
                left = (call_node(":" + method, left, args) if ":" + method in CALLS
                        else node("method", owner=[left], name=method, args=args))
            elif self.word in ("(", "{") or self.word.startswith(("'", '"', "[")):
                args = self.args()
                api = ""
                if left["block"] == "ls_member" and left["owner"][0]["block"] == "ls_name":
                    api = left["owner"][0]["value"] + "." + left["name"]
                if api in CALLS:
                    left = call_node(api, None, args)
                elif api.partition(".")[0] in ENGINE_TABLES:
                    left = node("engine", api=api, args=args)
                else:
                    left = node("call", callee=[left], args=args)
            else:
                return left

    def args(self):
        if self.accept("("):
            args = [] if self.word == ")" else self.exprs()
            self.expect(")")
            return args
        if self.word == "{":
            return [self.table()]
        if self.word.startswith(("'", '"', "[")):
            return [node("string", value=self.take())]
        self.fail("函数调用缺少参数括号")

    def table(self):
        self.expect("{")
        fields = []
        while not self.accept("}"):
            if self.accept("["):
                key = self.expr()
                self.expect("]")
                self.expect("=")
                fields.append(node("key_field", key=[key], value=[self.expr()]))
            elif is_name(self.word) and self.words[self.i + 1] == "=":
                name = self.take()
                self.take()
                fields.append(node("named_field", name=name, value=[self.expr()]))
            else:
                fields.append(node("item", value=[self.expr()]))
            if self.word in (",", ";"):
                self.take()
            elif self.word != "}":
                self.fail("表的条目之间需要逗号")
        return node("table", fields=fields)

    def body(self):
        statements = []
        while self.word not in ("", "else", "elseif", "end", "until"):
            if self.accept(";"):
                continue
            statements.append(self.statement())
        return statements

    def body_end(self):
        body = self.body()
        self.expect("end")
        return body

    def if_statement(self):
        test = self.expr()
        self.expect("then")
        body, branches = self.body(), []
        while self.accept("elseif"):
            other = self.expr()
            self.expect("then")
            branches.append(node("elseif", test=[other], body=self.body()))
        if self.accept("else"):
            branches.append(node("else", body=self.body()))
        self.expect("end")
        return node("if", test=[test], body=body, branches=branches)

    def for_statement(self):
        names = self.names()
        if self.accept("in"):
            values = self.exprs()
            self.expect("do")
            return node("for_in", names=names, values=values, body=self.body_end())
        self.expect("=")
        bounds = self.exprs()
        if "," in names or len(bounds) not in (2, 3):
            self.fail("计数循环需要一个变量、起点、终点以及可选的步长")
        self.expect("do")
        return node("for", name=names, start=bounds[:1], stop=bounds[1:2], step=bounds[2:], body=self.body_end())

    def statement(self):
        w = self.word
        if self.accept("local"):
            if self.accept("function"):
                return node("local_function", name=self.name(), **self.function_body())
            names = self.names()
            return node("local", names=names, values=self.exprs() if self.accept("=") else [])
        if self.accept("function"):
            name = self.name()
            while self.accept("."):
                name += "." + self.name()
            if self.accept(":"):
                name += ":" + self.name()
            return node("function", name=name, **self.function_body())
        if self.accept("if"):
            return self.if_statement()
        if self.accept("for"):
            return self.for_statement()
        if self.accept("while"):
            test = self.expr()
            self.expect("do")
            return node("while", test=[test], body=self.body_end())
        if self.accept("repeat"):
            body = self.body()
            self.expect("until")
            return node("repeat", body=body, test=[self.expr()])
        if self.accept("do"):
            return node("scope", body=self.body_end())
        if self.accept("return"):
            values = [] if self.word in (";", "", "else", "elseif", "end", "until") else self.exprs()
            return node("return", values=values)
        if self.accept("break"):
            return node("break")
        if self.accept("goto"):
            return node("goto", name=self.name())
        if self.accept("::"):
            name = self.name()
            self.expect("::")
            return node("label", name=name)
        left = self.prefix()
        if self.word in (",", "="):
            targets = self.exprs(left)
            self.expect("=")
            return node("assign", targets=targets, values=self.exprs())
        if left["block"] not in ("ls_call", "ls_method", "ls_engine") and not left["block"].startswith("ls_api_"):
            self.fail("需要赋值或调用函数，语句起始为 %r" % w)
        return node("run", call=[left])


def parse(source, code=0):
    p = Parser(source.lstrip("\ufeff"))
    body = p.body()
    if p.word:
        p.fail("多余的 %r" % p.word)
    if not code:
        for st in body:
            if st["block"] == "ls_function" and st["name"].endswith(".initial_effect"):
                table = st["name"].split(".")[0]
                if table.startswith("c") and table[1:].isdigit():
                    code = int(table[1:])
                    break
    return node("program", code=code, body=body)
