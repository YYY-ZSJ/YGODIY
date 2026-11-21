"""扩展包 strings.conf 中由编号引用的字段和指示物名称。"""


def read_names(texts):
    result = {"setnames": {}, "counters": {}}
    tables = {"!setname": result["setnames"], "!counter": result["counters"]}
    for text in texts:
        for line in text.splitlines():
            if not line.startswith(("!setname ", "!counter ")):
                continue
            parts = line.split(None, 2)
            if len(parts) != 3 or parts[0] not in tables:
                continue
            number = parts[1]
            try:
                code = int(number, 16 if number.lower().startswith("0x") else 10)
            except ValueError:
                continue
            name = parts[2].partition("\t")[0].strip()
            if 0 < code <= 0xffff and name:
                tables[parts[0]].setdefault(hex(code), name)
    return result
