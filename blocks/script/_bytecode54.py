"""逐字节对照 Lua 5.4 输出，仅移除标准 strip 仍保留的函数定义起止行号。"""


def executable_chunk(chunk):
    # 字段次序对应 Lua 5.4 的 ldump.c。所有指令、常量、闭包及上值信息参与比较。
    if chunk[:6] != b"\x1bLua\x54\x00":
        raise ValueError("需要 Lua 5.4 的标准二进制块")
    instruction, integer, number = chunk[12:15]
    pos = 15 + integer + number + 1
    pieces = []
    start = 0

    def size():
        nonlocal pos
        n = 0
        while True:
            byte = chunk[pos]
            pos += 1
            n = (n << 7) | (byte & 0x7f)
            if byte & 0x80:
                return n

    def skip_string():
        nonlocal pos
        length = size()
        pos += max(0, length - 1)

    def function():
        nonlocal pos, start
        skip_string()
        pieces.append(chunk[start:pos])
        size()  # linedefined
        size()  # lastlinedefined
        start = pos
        pos += 3
        ncode = size()
        pos += ncode * instruction
        for _ in range(size()):
            tag = chunk[pos]
            pos += 1
            if tag in (4, 20):
                skip_string()
            elif tag == 3:
                pos += integer
            elif tag == 19:
                pos += number
            elif tag not in (0, 1, 17):
                raise ValueError("未知的 Lua 5.4 常量标签 %d" % tag)
        nup = size()
        pos += 3 * nup
        for _ in range(size()):
            function()
        if any(size() for _ in range(4)):
            raise ValueError("需要由 string.dump(f,true) 去除调试信息")

    function()
    if pos != len(chunk):
        raise ValueError("Lua 5.4 字节码长度不符")
    pieces.append(chunk[start:])
    return tuple(pieces)
