"""用测试沙盒验证导出的扩展包：像 MDPro3 一样加载它，逐张做加载检查，再跑情景；
另外模拟 MDPro3 读字段名的方式，确认包里用到的字段在 MDPro3 里有名字。"""

import os
import tempfile
import zipfile


def _parse_setnames(texts):
    """按 MDPro3 StringHelper.InitializeContent 的规则解析：「!」开头、按空格切开至少 3 段，同一编号只认第一个。"""
    names = {}
    for text in texts:
        for line in text.replace("\r", "").split("\n"):
            if len(line) > 1 and line[0] == "!":
                parts = [p for p in line[1:].split(" ") if p]
                if len(parts) > 2 and parts[0] == "setname":
                    try:
                        code = int(parts[1], 16) if parts[1][:2] == "0x" else int(parts[1])
                    except ValueError:
                        code = 0
                    names.setdefault(code, " ".join(parts[2:]).split("\t")[0])
    return names


def setname_check(ypk_path, base_strings=""):
    """模拟 MDPro3 读字段名的三种情况，返回 [(情况, 缺名字的字段编号列表)]，另加一条禁限卡表误判的检查。

    base_strings：MDPro3 自己的 strings.conf 内容（官方字段由它提供）。
    """
    with zipfile.ZipFile(ypk_path) as z:
        confs = {n: z.read(n).decode("utf-8-sig") for n in z.namelist() if n.lower().endswith(".conf")}
        used = set()
        with tempfile.TemporaryDirectory() as tmp:
            for n in z.namelist():
                if n.lower().endswith(".cdb"):
                    from ygopack import sqlite
                    con = sqlite.connect(z.extract(n, tmp), readonly=True)
                    for (setcode,) in con.query("select setcode from datas"):
                        while setcode:
                            if setcode & 0xffff:
                                used.add(setcode & 0xffff)
                            setcode >>= 16
                    con.close()
    out = []
    banlist_named = [n for n in confs if n.lower().endswith("lflist.conf")]
    out.append(("文件名以 lflist.conf 结尾的会被 MDPro3 当成禁限卡表", banlist_named))
    variants = [
        ("MDPro3 现在的版本（只收内容含 lflist 的 conf）", [t for t in confs.values() if "lflist" in t.lower()]),
        ("MDPro3 按内容排除修好以后", [t for t in confs.values() if "lflist" not in t.lower()]),
        ("MDPro3 按文件名排除修好以后", [t for n, t in confs.items() if "lflist" not in n.lower()]),
    ]
    for label, texts in variants:
        names = _parse_setnames([base_strings] + texts)
        out.append((label, sorted("0x%x" % c for c in used if c not in names)))
    return out


def verify(ypk_path, scenario_files=(), core=None, verbose=False, base_strings=None):
    """返回 (是否全部通过, 输出行)。"""
    from sandbox.core import Core
    from sandbox.probe import load_check
    from sandbox.scenario import run_file
    core = core or Core()
    lines, ok = [], True

    if base_strings is None:
        base_strings = _mdpro3_strings()
    for label, missing in setname_check(ypk_path, base_strings):
        ok &= not missing
        lines.append("%s  %s%s" % ("字段通过" if not missing else "字段失败", label,
                                   "" if not missing else "：" + "、".join(missing)))

    codes = core.add_expansion(ypk_path)
    with zipfile.ZipFile(ypk_path) as z:
        scripted = {int(os.path.basename(n)[1:-4]) for n in z.namelist()
                    if n.startswith("script/c") and n.endswith(".lua")}
    for code in codes:
        if code not in scripted:
            lines.append("—     %s（没有脚本）" % core.name(code))
            continue
        loaded, errs = load_check(core, code)
        good = loaded and not errs
        ok &= good
        lines.append("%s  %s%s" % ("加载通过" if good else "加载失败", core.name(code),
                                   "" if loaded else "（脚本没有被读到）"))
        lines.extend("      " + e for e in errs)
    for path in scenario_files:
        for name, passed, runner in run_file(core, path, {}, verbose):
            ok &= passed
            lines.append("%s  %s" % ("情景通过" if passed else "情景失败", name))
            if not passed:
                lines.extend("      ✗ " + f for f in runner.failures)
    return ok, lines


def _mdpro3_strings():
    from ygopack.mdpro3 import find_mdpro3
    path, _ = find_mdpro3()
    if not path:
        return ""
    try:
        with open(os.path.join(path, "Data", "locales", "zh-CN", "strings.conf"), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
