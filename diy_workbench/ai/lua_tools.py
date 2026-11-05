"""自定义 Lua 兜底：写入、官方脚本参考和积木缺口日志；安全检查在 blocks.lua_guard。"""

import copy
import json
import os
import re
import time
import zipfile

from blocks.catalog import new
from blocks.lua_guard import problems, reminders

MAX_MATCHES = 10
MAX_SCRIPT_CHARS = 6000
CONTEXT_LINES = 2


class LuaTools:
    def __init__(self, operations):
        self.operations = operations
        self.scripts = None
        self.manual = None

    def write(self, kind, description, code, reason, helpers=None, effect_index=None, card_uid=None):
        found = problems(code) + (problems(helpers, True) if helpers else [])
        if found:
            raise ValueError("Lua 没有通过安全检查：" + "；".join(found))
        tree = copy.deepcopy(self.operations._blocks(card_uid))
        effects = tree.setdefault("effects", [])
        if kind == "effect":
            node = new("custom_effect", zh=description, lua=code, helpers=helpers or "")
            if effect_index is None:
                effects.append(node)
            elif 0 <= effect_index < len(effects):
                effects[effect_index] = node
            else:
                raise ValueError("effect_index超出范围：这张卡有%d个效果。" % len(effects))
        else:
            if helpers:
                raise ValueError("statement只能写处理语句；需要辅助函数时用kind=effect。")
            if effect_index is None or not 0 <= effect_index < len(effects) or effects[effect_index].get("block") != "effect":
                raise ValueError("statement要用effect_index指定一个「会发动的效果」，从0开始。")
            node = new("raw", zh=description, lua=code)
            effects[effect_index].setdefault("operation", []).append(node)
        result = self.operations.changes.stage("blocks", model=tree, card_uid=card_uid, custom=[node])
        self.record_gap(description, reason, card_uid, "lua")
        return dict(result, custom_lua=True, tested=False, reminders=reminders(code + "\n" + (helpers or "")),
                    note=result.get("note", "") + " 只通过了安全检查，还没有证明能运行；请写情景并用run_sandbox_test测试。")

    def write_script(self, code, reason, card_uid=None):
        found = problems(code)
        if found:
            raise ValueError("Lua 没有通过安全检查：" + "；".join(found))
        result = self.operations.changes.stage("script", code=code, card_uid=card_uid)
        self.record_gap("整张卡改用手写脚本", reason, card_uid, "script")
        return dict(result, custom_lua=True, tested=False, reminders=reminders(code),
                    note=result.get("note", "") + " 只通过了安全检查，请写情景并用run_sandbox_test测试。")

    def gap(self, text, reason, card_uid=None):
        self.record_gap(text, reason, card_uid, "gap")
        return {"recorded": True}

    def record_gap(self, text, reason, card_uid, kind):
        from . import settings
        plan = self.operations.changes.current
        uid = card_uid or (plan.target if plan else None)
        path = settings.settings_path().parent / "AI会话" / "积木缺口日志.jsonl"
        os.makedirs(path.parent, exist_ok=True)
        row = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind, "card_uid": uid, "text": text, "reason": reason}
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _load(self):
        if self.scripts is None:
            from ygopack import mdpro3
            root, _ = mdpro3.find_mdpro3()
            path = os.path.join(root or "", "Data", "script.zip")
            if not root or not os.path.exists(path):
                raise ValueError("没有找到 MDPro3 的官方脚本，无法检索。")
            scripts = {}
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.endswith(".lua"):
                        scripts[os.path.basename(name)] = archive.read(name).decode("utf-8", "replace")
            self.scripts = scripts
        return self.scripts

    def _manual(self):
        if self.manual is None:
            from . import settings
            from .lua_reference import DATA_FILE, load
            self.manual = load(settings.settings_path().parent / "AI资料" / DATA_FILE)
        return self.manual

    def symbol(self, name, limit=3):
        """查一个接口或常量：手册说明、本机实际定义和官方用法。手册可能过时，以本机脚本为准。"""
        from diy_workbench.lua_intel import intel
        scripts, manual = self._load(), self._manual()
        method = re.split(r"[.:]", name)[-1]
        rows = [entry for entry in intel().lookup(name) if entry.kind == "函数"]
        result = {"symbol": name, "manual": [{"name": row.name, "signature": row.detail, "doc": row.doc} for row in rows[:3]]}
        for table in ("abilities", "events"):
            if name in manual.get(table, {}):
                result[table[:-1] if table == "events" else "ability"] = manual[table][name]
        constant = intel().by_name.get(name)
        if constant is not None and constant.kind == "常量" and constant.doc:
            result["meaning"] = constant.doc
        value = re.search(r"^%s\s*=\s*([^\s-]+)" % re.escape(name), scripts.get("constant.lua", ""), re.M)
        if value:
            result["value"] = value.group(1)
        for library in ("utility.lua", "procedure.lua"):
            found = re.search(r"^function\s+[\w.:]*\b%s\([^)]*\)" % re.escape(method), scripts.get(library, ""), re.M)
            if found:
                result["defined_in"] = {"file": library, "signature": found.group()}
        pattern = re.compile(r"\b%s\b" % re.escape(method))
        cards = [key for key in sorted(scripts) if re.fullmatch(r"c\d+\.lua", key) and pattern.search(scripts[key])]
        result["used_by_official_cards"] = len(cards)
        result["examples"] = []
        for key in cards[:limit]:
            found = pattern.search(scripts[key])
            start = scripts[key].rfind("\n", 0, found.start()) + 1
            end = scripts[key].find("\n", found.end())
            result["examples"].append({"file": key, "line": scripts[key][start:end].strip()})
        if not result["manual"] and "value" not in result and "defined_in" not in result and not cards:
            raise ValueError("手册和官方脚本里都没有 %s，这个接口可能不存在；不要使用，换一种写法。" % name)
        if not cards:
            result["note"] = "官方脚本没有用过，可能已经过时，要在沙盒里确认能用。"
        return result

    def reference(self, code=None, query=None, limit=5, symbol=None):
        """symbol 查接口说明，code 取官方脚本全文，query 搜用法；只读本机文件。"""
        if sum(value is not None for value in (code, query, symbol)) != 1:
            raise ValueError("symbol、code、query只能填一个：symbol查接口或常量的说明，code取一张官方卡的脚本，query搜任意文字的用法。")
        if symbol is not None:
            return self.symbol(symbol, min(limit, 3))
        scripts = self._load()
        if code is not None:
            text = scripts.get("c%d.lua" % code)
            if text is None:
                raise ValueError("本机官方脚本里没有卡号%d。" % code)
            return {"code": code, "script": text[:MAX_SCRIPT_CHARS], "truncated": len(text) > MAX_SCRIPT_CHARS}
        pattern = re.compile(re.escape(query))
        matches, total = [], 0
        for name in sorted(scripts):
            found = pattern.search(scripts[name])
            if found is None:
                continue
            total += 1
            if len(matches) < min(limit, MAX_MATCHES):
                lines = scripts[name].splitlines()
                index = scripts[name].count("\n", 0, found.start())
                matches.append({"file": name, "lines": lines[max(0, index - CONTEXT_LINES):index + CONTEXT_LINES + 1]})
        return {"total": total, "matches": matches}
