"""自定义 Lua 的静态检查：挡住与对局无关的调用和明显的语法错误；是否真能运行由沙盒决定。"""

import re

FORBIDDEN = {"os", "io", "require", "load", "loadstring", "loadfile", "dofile", "debug", "package", "collectgarbage",
             "getfenv", "setfenv", "getmetatable", "setmetatable", "rawget", "rawset", "rawequal", "_G", "_ENV",
             "coroutine", "Debug", "LoadScript", "dump"}
OPENERS = {"function", "do", "if", "repeat"}
CLOSERS = {"end", "until"}
PAIRS = {")": "(", "]": "[", "}": "{"}
HELPER_PREFIX = "s.cl_"


def _skip_long(code, i):
    """code[i] 是 [ 时，若是长字符串 / 长注释的开头，返回结尾之后的位置。"""
    m = re.compile(r"\[(=*)\[").match(code, i)
    if not m:
        return None
    end = code.find("]" + m.group(1) + "]", m.end())
    return len(code) if end < 0 else end + len(m.group(1)) + 2


def tokens(code):
    """去掉注释和字符串后的词和符号；字符串只留一个占位，字符串里的文字不算调用。"""
    result, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if code.startswith("--", i):
            end = _skip_long(code, i + 2) if code.startswith("[", i + 2) else None
            if end is None:
                end = code.find("\n", i)
                end = n if end < 0 else end
            i = end
        elif c == "[" and _skip_long(code, i) is not None:
            i = _skip_long(code, i)
            result.append("<string>")
        elif c in "\"'":
            i += 1
            while i < n and code[i] != c:
                i += 2 if code[i] == "\\" else 1
            i += 1
            result.append("<string>")
        elif c.isalpha() or c == "_":
            m = re.compile(r"\w+").match(code, i)
            result.append(m.group())
            i = m.end()
        elif c.isspace():
            i += 1
        else:
            result.append(c)
            i += 1
    return result


def syntax_problems(code):
    depth, stack = 0, []
    words = tokens(code)
    for word in words:
        if word in OPENERS:
            # for / while 的 do 和它们本身算同一层，这里只数 do
            depth += 1
        elif word in CLOSERS:
            depth -= 1
            if depth < 0:
                return ["多了一个 %s" % word]
        elif word in PAIRS.values():
            stack.append(word)
        elif word in PAIRS:
            if not stack or stack.pop() != PAIRS[word]:
                return ["括号没有配对：%s" % word]
    if depth > 0:
        return ["缺少 end：有 %d 个代码块没有结束" % depth]
    if stack:
        return ["括号没有配对：%s" % stack[-1]]
    return []


def locate(code):
    """问题定位到行：(行号, 说明)。块和括号没配对时指向它开始的那一行。"""
    result, blocks, brackets = [], [], []
    for number, line in enumerate(str(code or "").splitlines(), 1):
        words = tokens(line)
        for index, word in enumerate(words):
            if word in FORBIDDEN and not (word == "Debug" and words[index + 1:index + 3] == [".", "Message"]):
                result.append((number, "不允许使用 %s：与对局无关" % word))
            elif word in OPENERS:
                blocks.append(number)
            elif word in CLOSERS:
                if blocks:
                    blocks.pop()
                else:
                    result.append((number, "多了一个 %s" % word))
            elif word in PAIRS.values():
                brackets.append((word, number))
            elif word in PAIRS:
                if brackets and brackets[-1][0] == PAIRS[word]:
                    brackets.pop()
                else:
                    result.append((number, "括号没有配对：%s" % word))
    result += [(number, "这里开始的代码块缺少 end") for number in blocks[-1:]]
    result += [(number, "括号没有配对：%s" % word) for word, number in brackets[-1:]]
    return sorted(result)


def reminders(code):
    """官方写法里容易漏的检测；不一定是错，提醒写的人核对。"""
    result = []
    if "LOCATION_GRAVE" in code and re.search(r"Duel\.Select(Matching|Group)", code) and "NecroValleyFilter" not in code:
        result.append("从墓地选卡的不取对象效果，过滤函数要包 aux.NecroValleyFilter（王家长眠之谷）")
    if "Duel.SpecialSummon" in code and "59822133" not in code and re.search(r"Select\w*\([^\n]*,\s*(?:\d+\s*,\s*)?(?:[2-9]|ft)\s*,", code):
        result.append("可能同时特殊召唤 2 只以上时，要查 Duel.IsPlayerAffectedByEffect(tp,59822133)（青眼精灵龙）")
    if re.search(r"SetType\(EFFECT_TYPE_(ACTIVATE|IGNITION|QUICK|TRIGGER)", code) and "SetCategory" not in code:
        result.append("发动的效果通常要写 SetCategory，别的卡要靠它判断")
    return result


def problems(code, helpers=False):
    """→ 问题列表（空表示通过）。helpers=True 时检查的是写在脚本顶层的辅助函数。"""
    code = str(code or "")
    words = tokens(code)
    found = sorted({word for index, word in enumerate(words) if word in FORBIDDEN and
                    not (word == "Debug" and words[index + 1:index + 3] == [".", "Message"])})
    result = ["不允许使用 %s：与对局无关" % word for word in found]
    result += syntax_problems(code)
    if helpers:
        stripped = re.sub(r"--[^\n]*", "", code)
        for m in re.finditer(r"(?<![\w.])(local\s+)?function\s+([A-Za-z_][\w.:]*)", stripped):
            if not m.group(1) and not m.group(2).startswith(HELPER_PREFIX):
                result.append("辅助函数 %s 要以 %s 开头，避免和积木生成的函数重名" % (m.group(2), HELPER_PREFIX))
    return result
