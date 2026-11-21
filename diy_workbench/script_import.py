"""在效果页把手写脚本、实卡或 .lua 文件转换为积木，保留一次可还原的版本。"""

import copy
from pathlib import Path
import re
import zipfile

from PyQt5.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from blocks import SCRIPT_TYPES, build, type_bits
from blocks.compile import CompileError, tokens
from blocks.script import parse, render
from ygopack import mdpro3, sqlite
from . import script_library, store


def _choose_reference(parent):
    folder, _ = mdpro3.find_mdpro3()
    if not folder:
        raise ValueError("未找到 MDPro3，可从文件导入 .lua。")
    root = Path(folder)
    term, ok = QInputDialog.getText(parent, "选择 MDPro3 的实卡", "输入卡号或官方卡名（扩展卡可按卡号查找）")
    if not ok or not term.strip():
        return None
    term = term.strip()
    if term.isascii() and term.isdecimal():
        code = int(term)
    else:
        matches = script_library.name_matches(root, term)
        if not matches:
            raise ValueError("没有找到这个卡名。")
        if len(matches) == 1:
            code = matches[0][0]
        else:
            label, ok = QInputDialog.getItem(parent, "选择卡片", "卡名匹配结果",
                                             ["%d  %s" % pair for pair in matches], 0, False)
            if not ok:
                return None
            code = int(label.split()[0])
    versions = script_library.versions(root, code)
    if not versions:
        raise ValueError("本机没有 c%d.lua。有些通常怪兽没有独立效果脚本。" % code)
    picked = versions[0]
    if len(versions) > 1:
        labels = [str(p.relative_to(root)) + (" · " + m if m else "") for p, m in versions]
        label, ok = QInputDialog.getItem(parent, "选择脚本版本", "本机有多份同卡号脚本", labels, 0, False)
        if not ok:
            return None
        picked = versions[labels.index(label)]
    source, texts = script_library.read_version(root, picked, code)
    return source, code, texts


def _input(workbench, tab, action):
    if action == "reference":
        return _choose_reference(workbench.panel)
    if action == "file":
        path, _ = QFileDialog.getOpenFileName(workbench.panel, "将 Lua 文件拆成积木", "", "Lua 脚本 (*.lua)")
        if not path:
            return None
        file = Path(path)
        number = re.fullmatch(r"c(\d+)", file.stem, re.I)
        return file.read_text(encoding="utf-8-sig"), int(number[1]) if number else 0, None

    diy = store.card_diy(tab)
    code = store.card_code(tab.get("data") or {})
    if diy.get("script"):
        return diy["script"], code, None
    model, _, _ = store.full_model(tab)
    # 同名规则由卡片设置在导出时添加。转换只收入用户实际编辑的积木。
    model["effects"] = diy["blocks"]["effects"]
    model.pop("script_alias", None)
    result = build(model, workbench.counters.labels(workbench.current()[1]))
    return result["lua"], code, (result["desc"], result["pdesc"], result["strings"])


def make_program(source, code, texts, card_code):
    program = parse(source, code)
    render(program, card_code)      # 写入草稿前完成字段、编号绑定和接口检查
    desc, pdesc, strings = texts
    program.update(desc=desc, pdesc=pdesc, hints=[{"block": "ls_hint", "index": i, "text": s}
                                                  for i, s in enumerate(strings) if s])
    return program


def change(workbench, action):
    tab, _ = workbench.current()
    if tab is None:
        return
    parent, diy = workbench.panel, store.card_diy(tab)
    if action == "restore":
        previous = diy.get("before_script_blocks")
        if previous is None:
            return
        if QMessageBox.question(parent, "还原上次转换", "用上次转换前的积木和手写脚本替换当前版本？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        diy["blocks"] = previous["blocks"]
        if previous.get("script"):
            diy["script"] = previous["script"]
        else:
            diy.pop("script", None)
        diy.pop("before_script_blocks")
    else:
        try:
            selected = _input(workbench, tab, action)
            if selected is None:
                return
            source, code, texts = selected
            if not source.strip():
                raise ValueError("脚本是空的。")
            desc, pdesc = workbench._card_text(tab)
            if texts is None:
                texts = (desc, pdesc, [])
            elif action == "current":
                texts = (texts[0] or desc, texts[1] or pdesc, texts[2])
            program = make_program(source, code, texts, store.card_code(tab.get("data") or {}))
            bits = type_bits(diy["blocks"])
            if bits:
                program["card_types"] = "+".join(key for key, mask in SCRIPT_TYPES.items() if bits & mask)
            if action == "current":
                program["token_cards"] = [dict(token, count_n=[]) for _, token in tokens(diy["blocks"])]
        except (OSError, ValueError, RuntimeError, CompileError, sqlite.DatabaseError, zipfile.BadZipFile) as exc:
            QMessageBox.warning(parent, "转换未完成", str(exc))
            return
        if (diy["blocks"].get("effects") or diy.get("script")) and QMessageBox.question(
                parent, "转换为脚本积木", "用转换后的积木替换当前效果？可以在同一菜单还原上次转换。",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        diy["before_script_blocks"] = {"blocks": copy.deepcopy(diy["blocks"]), "script": diy.get("script")}
        diy["blocks"] = dict(diy["blocks"], effects=[program])
        diy.pop("script", None)
    workbench._last_check.pop(tab.get("_card_uid"), None)
    workbench.code_page.card_key = None
    workbench._save_state()
    workbench.refresh()
