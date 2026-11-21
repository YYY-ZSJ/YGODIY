"""整卡脚本的语句、表达式和引擎调用目录，供现有拖放编辑器使用。"""

from .calls import CALLS, arguments, block_id
from .grammar import ATOMS, PRECEDENCE, UNARY


FLOWS = "脚本流程"
VALUES = "脚本表达式"
PARTS = "脚本分支与表项"
ENGINE = "对局引擎调用"
KINDS = {"ls_stmt": "脚本语句", "ls_expr": "脚本表达式", "ls_branch": "条件分支",
         "ls_field": "表项", "ls_hint": "提示文字"}
CATEGORIES = {FLOWS: "ls_stmt", VALUES: "ls_expr", PARTS: "ls_field", ENGINE: "ls_expr"}

BODY = ("body", "依次执行", "ls_stmt", 0)
TEST = ("test", "条件", "ls_expr", 1)
VALUE = ("value", "值", "ls_expr", 1)
VALUES_SLOT = ("values", "值（按顺序）", "ls_expr", 0)
ARGS = ("args", "参数（按顺序）", "ls_expr", 0)
OWNER = ("owner", "从哪个对象读取", "ls_expr", 1)
PARAMS = ("params", "参数名（逗号分隔）", "text", "")
NAME = ("name", "名称", "text", "v")
NAMES = ("names", "变量名（逗号分隔）", "text", "v")
OPS_ZH = {"and": "并且", "or": "或者", "not": "不满足", "#": "取长度", "..": "连接文本", "//": "整除",
          "~=": "不等于", "&": "按位与", "|": "按位或", "~": "按位异或", "<<": "左移", ">>": "右移", "^": "乘方"}


def definitions(Block):
    def spec(key, kind, category, label, fields=(), slots=(), summary=None, hint=""):
        show = (lambda n: label + " " + str(n.get(summary, ""))) if summary else None
        return Block("ls_" + key, kind, category, label, fields, slots, show, hint)

    def stmt(key, label, fields=(), slots=(), summary=None):
        return spec(key, "ls_stmt", FLOWS, label, fields, slots, summary)

    def expr(key, label, fields=(), slots=(), summary=None):
        return spec(key, "ls_expr", VALUES, label, fields, slots, summary)

    def choices(items):
        return [(k, k + " " + OPS_ZH[k] if k in OPS_ZH else k) for k in items]

    yield spec("program", "hat", "效果", "整卡脚本积木",
               [("code", "原脚本卡号", "int", 0), ("desc", "效果文字", "lua", ""), ("pdesc", "灵摆效果文字", "lua", ""),
                ("card_types", "附加卡片数据种类", "multi", [("none", "无"), ("spsummon", "不能通常召唤"),
                                                    ("spirit", "灵魂"), ("union", "同盟"), ("gemini", "二重")])],
               [BODY, ("hints", "卡片提示文字", "ls_hint", 0),
                ("token_cards", "随卡包导出的衍生物资料（按卡号顺序）", "stmt", 0, ["create_token"])],
               hint="独立编辑整卡的函数与流程。导出到新卡号时会替换原卡的脚本表名和相同的十进制卡号。填 0 可保留原引用。")
    yield stmt("function", "定义函数", [("name", "函数名", "text", "s.initial_effect"), PARAMS], [BODY], "name")
    yield stmt("local_function", "定义局部函数", [NAME, PARAMS], [BODY], "name")
    yield stmt("local", "声明局部变量", [NAMES], [VALUES_SLOT], "names")
    yield stmt("assign", "赋值", slots=[("targets", "写入哪些变量或表项", "ls_expr", 0), VALUES_SLOT])
    yield stmt("run", "执行函数或对局操作", slots=[("call", "要执行的调用", "ls_expr", 1)])
    yield stmt("if", "如果条件成立", slots=[TEST, BODY, ("branches", "其他分支", "ls_branch", 0)])
    yield spec("elseif", "ls_branch", PARTS, "否则如果", slots=[TEST, BODY])
    yield spec("else", "ls_branch", PARTS, "否则", slots=[BODY])
    yield stmt("for", "按数值循环", [NAME], [("start", "起点", "ls_expr", 1), ("stop", "终点", "ls_expr", 1),
                                      ("step", "步长（可省）", "ls_expr", 1), BODY], "name")
    yield stmt("for_in", "遍历卡片组或表", [NAMES], [("values", "迭代器及其参数", "ls_expr", 0), BODY], "names")
    yield stmt("while", "条件成立时重复", slots=[TEST, BODY])
    yield stmt("repeat", "重复直到条件成立", slots=[BODY, TEST])
    yield stmt("scope", "局部作用域", slots=[BODY])
    yield stmt("break", "退出当前循环")
    yield stmt("return", "返回值", slots=[VALUES_SLOT])
    yield stmt("label", "标记跳转位置", [NAME], summary="name")
    yield stmt("goto", "跳转到标记", [NAME], summary="name")
    yield expr("name", "变量或引擎常量", [("value", "标识符", "text", "c")], summary="value")
    yield expr("number", "数字常量", [("value", "数值（可用十六进制）", "text", "0")], summary="value")
    yield expr("string", "文本常量", [("value", "带引号的文本", "lua", '""')], summary="value")
    yield expr("atom", "布尔值、空值或可变参数", [("value", "值", "choice", choices(ATOMS))], summary="value")
    yield expr("binary", "两项运算或比较", [("op", "运算", "choice", choices(PRECEDENCE))],
               [("left", "左边", "ls_expr", 1), ("right", "右边", "ls_expr", 1)], "op")
    yield expr("unary", "单项运算", [("op", "运算", "choice", [(k, "按位取反" if k == "~" else OPS_ZH.get(k, k)) for k in UNARY])],
               [VALUE], "op")
    yield expr("parens", "括号（只取第一个返回值）", slots=[VALUE])
    yield expr("member", "按名称读取成员", [NAME], [OWNER], "name")
    yield expr("index", "按索引读取表项", slots=[OWNER, ("key", "索引", "ls_expr", 1)])
    yield expr("call", "调用函数", slots=[("callee", "函数", "ls_expr", 1), ARGS])
    yield expr("method", "调用对象的方法", [NAME], [OWNER, ARGS], "name")
    yield expr("lambda", "匿名回调函数", [PARAMS], [BODY])
    yield expr("table", "建立一张表", slots=[("fields", "表项（按顺序）", "ls_field", 0)])
    yield spec("item", "ls_field", PARTS, "列表元素", slots=[VALUE])
    yield spec("named_field", "ls_field", PARTS, "按名称写入表项", [NAME], [VALUE], "name")
    yield spec("key_field", "ls_field", PARTS, "按键写入表项", slots=[("key", "键", "ls_expr", 1), VALUE])
    yield spec("hint", "ls_hint", PARTS, "卡片提示文字", [("index", "提示编号（0～15）", "int", 0),
               ("text", "提示内容", "text", "")], summary="text")
    yield spec("engine", "ls_expr", ENGINE, "从手册选择对局接口",
               [("api", "接口", "text", "Duel.GetTurnPlayer")], [ARGS], "api")
    for api, (label, _) in CALLS.items():
        slots = [("receiver", "调用方法的卡片、效果或卡片组", "ls_expr", 1)] if api.startswith(":") else []
        slots += [("arg%d" % i, name, "ls_expr", 1) for i, name in enumerate(arguments(api))]
        slots.append(("more", "额外参数（可省）", "ls_expr", 0))
        yield Block(block_id(api), "ls_expr", ENGINE, label, slots=slots, hint=api)
