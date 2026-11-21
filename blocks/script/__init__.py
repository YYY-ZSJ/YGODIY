"""工作台的整卡脚本积木，与已有的卡片效果积木共用编辑与导出入口。"""

from .grammar import ScriptError
from .parser import parse
from .writer import render


def program_of(model):
    effects = model.get("effects") or []
    programs = [e for e in effects if e.get("block") == "ls_program"]
    if programs and len(effects) != 1:
        raise ScriptError("整卡脚本包含自己的初始化函数，必须单独放在最外层。可将当前效果转换成脚本积木后继续编辑。")
    return programs[0] if programs else None


def prompt_strings(program):
    hints = {}
    for node in program.get("hints", []):
        index = node["index"]
        if type(index) is not int or not 0 <= index < 16 or index in hints:
            raise ScriptError("卡片提示编号必须在 0～15 之间，每个编号只用一次")
        hints[index] = node.get("text", "")
    return [hints.get(i, "") for i in range(max(hints, default=-1) + 1)]
