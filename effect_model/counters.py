"""OCG 引擎指示物的 16 位编号；旧积木用 spell 表示魔力指示物。"""
import re


def counter_code(value):
    if value == "spell":
        return "0x1"
    text = str(value).strip()
    if re.fullmatch(r"0[xX][0-9a-fA-F]{1,4}|[0-9]{1,5}", text):
        number = int(text, 16 if text.lower().startswith("0x") else 10)
        if 1 <= number <= 0xffff:
            return hex(number)
    raise ValueError("指示物编号须为 1～65535 的十进制数或 0x 开头的十六进制数。")


def counter_name(value, names=None):
    code = counter_code(value)
    if names and code in names:
        return names[code]
    return "魔力指示物" if code == "0x1" else "指示物（%s）" % code


def clean_names(names):
    result = {}
    if isinstance(names, dict):
        for key, name in names.items():
            if not isinstance(name, str) or not name.strip() or any(c in name for c in "\t\r\n\x00"):
                continue
            try:
                result[counter_code(key)] = name.strip()
            except ValueError:
                continue
    return result
