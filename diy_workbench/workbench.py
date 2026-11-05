"""DIY 工作台总控：接进主窗口的模式下拉，跟随当前卡片，保存效果、写回卡面、导出。

和漫画卡模式一样是独立的一个模式：进入时先按 OCG/TCG 切换（卡面、数据、显示设置都按 OCG），
再把右栏换成工作台面板；app.current_mode 设为工作台自己的序号。
OCG 编辑器只在两件事上被动到，而且都是用户点了按钮：「写回卡面」（效果文字）和「按顺序重新分配」（卡密）。
"""

import os
import shutil
import threading
import traceback
import uuid
import zipfile

from PyQt5.QtCore import QTimer, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QResizeEvent
from PyQt5.QtWidgets import QDialog, QFileDialog, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from . import dialogs, store
from .code_page import CodePage
from .effect_page import EffectPage
from .installed_page import InstalledPage
from .pack_page import PackPage

MODE_LABEL = "DIY 工作台"
# 工作台模式下卡图和右栏的宽度比例（别的模式是 1:1）：卡图小一些，积木多些地方
VIEW_SHARE, PANEL_SHARE = 2, 3


def _log(message):
    try:
        from common import _tab_log
        _tab_log(message)
    except Exception:
        pass


def _verify_lines(vlines):
    """把测试沙盒的验证输出换成卡包页上的说法：字段名的几种读法合成一行，加载结果逐张列出。"""
    out, setname_bad, setname_seen = [], [], False
    for line in vlines:
        if line.startswith("      "):              # 上一行的细节（脚本报错、情景失败原因）
            out.append(("×", "    " + line.strip().lstrip("×").strip()))
            continue
        head, _, rest = line.partition("  ")
        rest = rest.strip()
        if head.startswith("字段"):
            setname_seen = True
            if head == "字段失败":
                setname_bad.append(rest)
        elif head == "加载通过":
            out.append(("√", "%s：脚本能被引擎加载，效果注册正常" % rest))
        elif head == "加载失败":
            out.append(("×", "%s：脚本加载出错" % rest))
        elif head == "情景通过":
            out.append(("√", "情景：%s" % rest))
        elif head == "情景失败":
            out.append(("×", "情景：%s" % rest))
        else:                                       # 「—     某卡（没有脚本）」
            name = line.lstrip("— ").strip().replace("（没有脚本）", "")
            out.append(("·", "%s：没有脚本（没有效果的卡不需要）" % name))
    head = [("×", "字段名：%s" % bad) for bad in setname_bad]
    if setname_seen and not setname_bad:
        head = [("√", "字段名在 MDPro3 里能显示（现在的版本和修好以后的版本都检查过）")]
    return head + out


class Workbench:
    def __init__(self, app):
        self.app = app
        self._connected = False
        self._busy = False
        self._core = None
        self._core_lock = threading.Lock()
        self._last_check = {}            # 卡片 uid → 沙盒检查结果文字
        self._script_findings = []       # 脚本页的静态检查结果，和沙盒结果一起显示
        self.focus = False               # 专注模式：隐藏卡图，地方都给积木
        self._known = {}                 # 卡包装进去的文件名 → MDPro3 里已有的卡号 {卡号: 谁占用}
        self._setcodes = {}              # 卡包装进去的文件名 → 别的扩展包用掉的字段 {编号: (名字, 来源)}
        self._known_busy = set()
        self._official = None            # 官方字段 [(编号, 中文名, 日文名)]
        self.panel = QWidget()
        self.panel.setObjectName("diy_workbench_panel")
        editor = getattr(app, "otcg_widget", None)
        if editor is not None and editor.styleSheet():
            self.panel.setStyleSheet(editor.styleSheet())
        root = QVBoxLayout(self.panel)
        root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.effect_page = EffectPage()
        self.pack_page = PackPage()
        self.tabs.addTab(self.effect_page, "效果")
        self.tabs.addTab(self.pack_page, "卡包")
        self.code_page = CodePage()
        self.installed_page = InstalledPage()
        self.tabs.addTab(self.code_page, "脚本")
        self.tabs.addTab(self.installed_page, "已安装")
        self.tabs.currentChanged.connect(self._tab_changed)
        root.addWidget(self.tabs)
        app.stacked_widget.addWidget(self.panel)

        ep, pp = self.effect_page, self.pack_page
        ep.changed.connect(self._effect_changed)
        ep.setcodes_requested.connect(self._edit_setcodes)
        ep.write_back.connect(self._write_back)
        ep.check_requested.connect(self._check_current)
        ep.media_requested.connect(self._edit_media)
        ep.card_data_requested.connect(self._edit_card_data)
        ep.export_requested.connect(lambda: (self.tabs.setCurrentIndex(1), self._export(True)))
        ep.edit_card_requested.connect(lambda: app.combo_box.setCurrentIndex(0))
        ep.focus_toggled.connect(self._set_focus)
        pp.card_selected.connect(self._select_card)
        pp.settings_changed.connect(self._settings_changed)
        pp.assign_codes.connect(self._assign_codes)
        pp.setname_added.connect(self._add_setname)
        pp.setname_removed.connect(self._remove_setname)
        pp.export_requested.connect(self._export)
        pp.transfer_requested.connect(self._transfer)
        cp, ip = self.code_page, self.installed_page
        cp.save_requested.connect(self._save_script)
        cp.reset_requested.connect(self._reset_script)
        cp.check_requested.connect(self._check_script)
        cp.open_requested.connect(self._open_script)
        cp.reload_requested.connect(self._reload_script)
        cp.export_image_requested.connect(self._export_code_image)
        cp.generate_requested.connect(self._generate_script)
        ip.refresh_requested.connect(self._refresh_installed)
        ip.open_requested.connect(self._open_expansions)
        ip.import_requested.connect(self._import_path)
        ip.uninstall_requested.connect(self._uninstall)
        ip.restore_requested.connect(self._restore_pack)
        ip.purge_requested.connect(self._purge_pack)
        pp.change_target.connect(self._change_target)
        pp.find_setcode.connect(self._find_setcode)
        pp.recheck.connect(self._recheck)
        pp.reset_target.connect(self._reset_target)

    # ------------------------------------------------------------ 模式

    def active(self):
        return getattr(self.app, "current_mode", None) == getattr(self.app, "_workbench_mode_index", -2)

    def enter(self, switch_to_ocg):
        switch_to_ocg(self.app, 0)
        self.app.current_mode = self.app._workbench_mode_index
        self.app.stacked_widget.setCurrentWidget(self.panel)
        self._set_shares(VIEW_SHARE, PANEL_SHARE)
        self._connect_manager()
        self.refresh()
        self._tab_changed(self.tabs.currentIndex())

    def leave(self):
        self.app.view.setVisible(True)
        self._set_shares(1, 1)                   # 别的模式还是原来的 1:1

    def _set_focus(self, on):
        """专注模式：隐藏卡图（左边的卡包、卡片列表还在，可以切卡）；关掉时卡面重新适配。"""
        self.focus = on
        self.effect_page.editor.set_wide(on)     # 地方够了：积木栏、积木列表、选项三栏并排
        if self.active():
            self.app.view.setVisible(not on and self.tabs.currentIndex() == 0)
            if not on:
                QTimer.singleShot(0, self._refit)

    def _set_shares(self, view, panel):
        """卡图和右栏分宽度的比例；改完按新的大小重新适配卡面。"""
        hbox = getattr(self.app, "hbox", None)
        if hbox is None:
            return
        hbox.setStretchFactor(self.app.view, view)
        hbox.setStretchFactor(self.app.right_widget, panel)
        QTimer.singleShot(0, self._refit)

    def _refit(self):
        app = self.app
        try:
            app.resizeEvent(QResizeEvent(app.size(), app.size()))   # 主窗口按当前模式重新适配卡面
        except Exception:
            _log("重新适配卡面失败:\n" + traceback.format_exc())

    def _tab_changed(self, index):
        if self.active():
            # 只有效果页显示卡面，其余页和专注模式把宽度让给右栏
            self.app.view.setVisible(index == 0 and not self.focus)
            self.refresh()

    def _connect_manager(self):
        manager = self.manager()
        if manager is None or self._connected:
            return
        for signal in (manager.tab_list.currentRowChanged, manager.pack_list.currentRowChanged):
            signal.connect(lambda *_: QTimer.singleShot(0, self._refresh_if_active))
        self._connected = True

    def _refresh_if_active(self):
        if self.active():
            self.refresh()

    # ------------------------------------------------------------ 数据

    def manager(self):
        return getattr(self.app, "card_tab_manager", None)

    def current(self):
        m = self.manager()
        if m is None or not (0 <= m.current_index < len(m.tabs)):
            return None, None
        pack = m.packs[m.current_pack_index] if 0 <= m.current_pack_index < len(m.packs) else None
        return m.tabs[m.current_index], pack

    def _save_state(self):
        m = self.manager()
        if m is None:
            return
        for name in ("_write_state_in_background", "_write_state"):
            fn = getattr(m, name, None)
            if fn is not None:
                try:
                    fn()
                    return
                except Exception:
                    _log("工作台保存标签页失败:\n" + traceback.format_exc())

    def _card_text(self, tab):
        """当前卡读编辑器里正在显示的文字，其他卡读存下来的数据。"""
        tab_now, _ = self.current()
        editor = getattr(self.app, "otcg_widget", None)
        if tab is tab_now and editor is not None:
            desc = editor.text_input.toPlainText() if hasattr(editor, "text_input") else ""
            pdesc = editor.LB_text_edit.toPlainText() if hasattr(editor, "LB_text_edit") else ""
            return desc, pdesc
        data = tab.get("data") or {}
        return data.get("effect_text", ""), data.get("lb_text", "")

    def _text_same(self, tab, result):
        if result.error or not result.desc and not result.pdesc:
            return True
        desc, pdesc = self._card_text(tab)
        return store.text_matches(desc, result.desc) and store.text_matches(pdesc, result.pdesc)

    # ------------------------------------------------------------ 刷新

    def refresh(self):
        tab, pack = self.current()
        if tab is None:
            return
        try:
            self._refresh_effect(tab, pack)
            if self.tabs.currentIndex() == 1:
                self._refresh_pack(pack)
            elif self.tabs.currentWidget() is self.code_page:
                self._refresh_code(tab)
            elif self.tabs.currentWidget() is self.installed_page:
                self._refresh_installed()
        except Exception:
            _log("刷新 DIY 工作台失败:\n" + traceback.format_exc())

    def _refresh_effect(self, tab, pack):
        diy = store.card_diy(tab)
        settings = store.pack_diy(pack or {})
        result = store.generate(tab)
        problem = None
        summary = ""
        setcode_text = "无"
        if result.rec is None:
            problem = result.error or "卡片资料不完整"
        else:
            rec = result.rec
            code = ("卡号 %d" % rec["code"]) if rec["code"] else "<span style='color:#9a5a00'>还没有卡号</span>"
            summary = "<b style='font-size:15px'>%s</b>　%s　%s" % (rec["name"], store.describe(rec), code)
            names = [self._setname(c, settings) for c in diy.get("setcodes", [])]
            setcode_text = "、".join(names) or "无"
        note = "卡包「%s」· %d 张 · %s" % ((pack or {}).get("title", ""), len((pack or {}).get("tabs", [])),
                                       self._target_text(short=True))
        self.effect_page.show_card(diy["blocks"], result.rec, summary, result, settings["setnames"],
                                   self._text_same(tab, result), note, problem, setcode_text)
        self.effect_page.show_design(diy.get("design_text") or "", store.text_matches(diy.get("design_text"), result.desc))
        uid = tab.get("_card_uid")
        if uid in self._last_check and not result.error:
            self.effect_page.add_check_lines(self._last_check[uid])
            self.effect_page.tabs.setCurrentIndex(0)

    def _refresh_pack(self, pack):
        if pack is None:
            return
        settings = store.pack_diy(pack)
        tab_now, _ = self.current()
        known = self.known_codes(pack)               # None：还在后台读
        codes = [store.card_code(t.get("data") or {}) for t in pack.get("tabs", [])]
        rows = []
        for tab in pack.get("tabs", []):
            res = store.generate(tab)
            diy = store.card_diy(tab)
            n = store.item_count(diy["blocks"])
            if res.rec is None:
                rows.append(("", tab.get("title", ""), "（不支持）", "", "", "", "× " + (res.error or ""), tab is tab_now))
                continue
            rec = res.rec
            kind = store.describe(rec).split(" · ")[0]
            names = "、".join(self._setname(c, settings) for c in diy.get("setcodes", []))
            effects = "%d 个效果" % n if n else ("（通常怪兽）" if rec["type"] & 0x10 else "没有效果")
            if not n:
                text = "—"
            else:
                text = "一致" if self._text_same(tab, res) else "不同"
            check = ("× " + res.error) if res.error else ("× " + res.issues[0][1] if any(
                lv == "错误" for lv, _ in res.issues) else ("√ 通过" if n else "—"))
            code_problem = ""
            if rec["code"] and known is not None and rec["code"] in known:
                code_problem = "卡号 %d 已被%s占用，不能用" % (rec["code"], known[rec["code"]])
            elif rec["code"] and codes.count(rec["code"]) > 1:
                code_problem = "卡号 %d 和这个卡包里别的卡重复，不能用" % rec["code"]
            if code_problem:
                check = "× " + code_problem
            rows.append((rec["code"] or "（无）", rec["name"], kind, names, effects, text, check, tab is tab_now,
                         code_problem))
        self.pack_page.show_pack(pack.get("title", ""), settings, rows, self._target_text(),
                                 self._code_status(settings, len(rows), known), self._setname_conflicts(pack, settings))

    def _code_status(self, settings, count, known):
        """卡号段核查：按「从……起，每张间隔……」分配的卡号，在 MDPro3 里有没有被占用。"""
        from .pack_page import GREEN, GREY, RED
        if known is None:
            return "正在核查 MDPro3 里已有的卡号……", GREY
        if not known:
            return "没有找到 MDPro3 的卡片数据，没法核查卡号有没有被占用", GREY
        start, step, n = settings["code_start"], settings["code_step"], max(count, 1)
        taken = [start + i * step for i in range(n) if start + i * step in known]
        if taken:
            free = store.free_code_start(start, step, n, known)
            return ("× 卡号 %s 已被%s占用，不能用。可以改成从 %d 起，再点「按顺序重新分配」"
                    % ("、".join(str(c) for c in taken[:3]) + ("等" if len(taken) > 3 else ""), known[taken[0]], free), RED)
        return "√ 从 %d 起的 %d 个卡号在 MDPro3 里都没有被占用，可以用" % (start, n), GREEN

    def known_codes(self, pack):
        """MDPro3 里已有的卡号（官方卡 + 已装的别的扩展包）；第一次在后台读，读完刷新。没读完时返回 None。"""
        from ygopack import build as ypbuild
        stem = "ygodiy-" + ypbuild.slug(pack.get("title") or "DIY") + ".ypk"   # 这个卡包自己装过的旧版本不算
        if stem in self._known:
            return self._known[stem]
        if stem not in self._known_busy:
            self._known_busy.add(stem)

            def work():
                from ygopack import mdpro3
                md_dir, _ = mdpro3.find_mdpro3()
                target, _ = mdpro3.expansions_dir()
                return (ypbuild.known_codes(md_dir, skip_file=stem, expansions=target),
                        ypbuild.known_setcodes(target, skip_file=stem))

            def done(value, error):
                self._known_busy.discard(stem)
                codes, setcodes = value if value and not error else ({}, {})
                self._known[stem] = codes
                self._setcodes[stem] = setcodes
                if error:
                    _log("读 MDPro3 已有卡号失败:\n" + error)
                self.refresh()
            self._run_async(work, done)
        return None

    def _stem(self, pack):
        from ygopack import build as ypbuild
        return "ygodiy-" + ypbuild.slug(pack.get("title") or "DIY") + ".ypk"

    def diy_setnames(self, pack):
        """已装扩展包里玩家自创的字段（去掉官方字段）：{编号: (名字, 来源)}；还没读完时是空的。"""
        official = {c for c, _, _ in self.official()}
        return {c: v for c, v in self._setcodes.get(self._stem(pack), {}).items() if c not in official}

    def _setname_conflicts(self, pack, settings):
        """自己的字段编号和官方字段、别的扩展包的字段撞了：{编号: 说明}。"""
        others = {}
        for c, (name, source) in self.diy_setnames(pack).items():
            if not others.get(int(c, 16) & 0xfff, ("",))[0]:
                others[int(c, 16) & 0xfff] = (name, source)
        official = {int(c, 16) & 0xfff: zh for c, zh, _ in self.official()}
        out = {}
        for code in settings.get("setnames", {}):
            base = int(code, 16) & 0xfff
            if base in official:
                out[code] = "编号和官方字段「%s」撞了，换一个" % official[base]
            elif base in others:
                name, source = others[base]
                out[code] = "编号和%s的%s撞了，换一个" % (source, "字段「%s」" % name if name else "字段")
        return out

    def _taken_setcodes(self, pack):
        """新建字段要避开的编号：官方字段 + 别的扩展包用掉的。"""
        return [int(c, 16) for c, _, _ in self.official()] + [int(c, 16) for c in self.diy_setnames(pack)]

    def _recheck(self):
        """重新读一遍 MDPro3 里已有的卡号和字段（刚往扩展目录里放了别的卡包时用）。"""
        self._known.clear()
        self._setcodes.clear()
        self._official = None
        self.refresh()

    def official(self):
        if self._official is None:
            from ygopack import mdpro3
            try:
                self._official = mdpro3.official_setnames()
            except Exception:
                _log("读官方字段失败:\n" + traceback.format_exc())
                self._official = []
        return self._official

    def searchable_setnames(self):
        """「查找字段」列出的：官方字段 + 已装扩展包里有名字的自创字段（带来源）。"""
        _, pack = self.current()
        diy = sorted((c, name, "", source) for c, (name, source) in self.diy_setnames(pack or {}).items() if name)
        return list(self.official()) + diy

    def _setname(self, code, settings):
        """字段编号 → 名字：自己的字段，或者官方字段的中文名。"""
        if code in settings["setnames"]:
            return settings["setnames"][code]
        name = next((zh for c, zh, _ in self.official() if c == code.lower()), None)
        return "%s（官方）" % name if name else code

    def _find_setcode(self):
        tab, _ = self.current()
        name = (store.generate(tab).rec or {}).get("name", "") if tab is not None else ""
        dlg = dialogs.OfficialSetcodeDialog(self.searchable_setnames(), name, self.panel)

        def add(code, zh):
            tab_now, _ = self.current()
            if tab_now is None:
                dlg.show_status("先在左边选一张卡", ok=False)
                return
            diy = store.card_diy(tab_now)
            codes = list(diy.get("setcodes", []))
            if code in codes:
                dlg.show_status("这张卡已经有「%s」字段了" % zh)
                return
            if len(codes) >= 4:
                dlg.show_status("一张卡最多 4 个字段，先在效果页「字段」里去掉一个", ok=False)
                return
            diy["setcodes"] = codes + [code]
            store.set_card_diy(tab_now, diy)
            self._save_state()
            self.refresh()
            dlg.show_status("已经把「%s」（%s）加到这张卡上" % (zh, code))
        dlg.added.connect(add)
        dlg.exec_()

    def _target_text(self, short=False):
        from ygopack import mdpro3
        try:
            path, note = mdpro3.expansions_dir()
        except Exception as ex:
            path, note = None, str(ex)
        if short:
            return ("装到 %s" % path) if path else "没有找到 MDPro3"
        return ("装到 %s（%s）" % (path, note)) if path else note

    # ------------------------------------------------------------ 效果页操作

    def _effect_changed(self):
        tab, _ = self.current()
        if tab is None:
            return
        diy = store.card_diy(tab)
        diy["blocks"] = self.effect_page.model
        store.set_card_diy(tab, diy)
        self._last_check.pop(tab.get("_card_uid"), None)
        self._save_state()
        QTimer.singleShot(0, self.refresh)

    def _edit_setcodes(self):
        tab, pack = self.current()
        if tab is None:
            return
        diy = store.card_diy(tab)
        settings = store.pack_diy(pack or {})
        dlg = dialogs.SetcodeDialog(settings["setnames"], diy.get("setcodes", []), self.panel, self.searchable_setnames())
        if dlg.exec_() == QDialog.Accepted:
            diy["setcodes"] = dlg.value()
            store.set_card_diy(tab, diy)
            self._save_state()
            self.refresh()

    def _write_back(self):
        tab, _ = self.current()
        editor = getattr(self.app, "otcg_widget", None)
        if tab is None or editor is None:
            return
        result = store.generate(tab)
        if result.error:
            return
        editor.text_input.setPlainText(result.desc)
        if result.pdesc and hasattr(editor, "LB_text_edit"):
            editor.LB_text_edit.setPlainText(result.pdesc)
        QTimer.singleShot(0, self.refresh)

    # ------------------------------------------------------------ 卡包页操作

    def _select_card(self, row):
        m = self.manager()
        if m is not None and 0 <= row < m.tab_list.count():
            self.tabs.setCurrentIndex(0)
            m.tab_list.setCurrentRow(row)

    def _settings_changed(self, values):
        _, pack = self.current()
        if pack is None:
            return
        settings = store.pack_diy(pack)
        settings.update(values)
        store.set_pack_diy(pack, settings)
        self._save_state()
        QTimer.singleShot(0, self.refresh)       # 卡号段改了：重新核查

    def _assign_codes(self):
        m = self.manager()
        _, pack = self.current()
        if m is None or pack is None:
            return
        settings = store.pack_diy(pack)
        tabs = pack.get("tabs", [])
        answer = QMessageBox.question(
            self.panel, "重新分配卡号",
            "按卡片顺序，从 %d 起每张间隔 %d，改写这个卡包里 %d 张卡的卡密？"
            % (settings["code_start"], settings["code_step"], len(tabs)))
        if answer != QMessageBox.Yes:
            return
        tab_now, _ = self.current()
        editor = getattr(self.app, "otcg_widget", None)
        for tab, code in store.assign_codes(tabs, settings["code_start"], settings["code_step"]):
            if tab is tab_now and editor is not None:
                editor.card_pass_edit.setText(str(code))   # 当前卡走编辑器，保存快照时不会被冲掉
            else:
                tab.setdefault("data", {})["cardpass"] = str(code)
        self._save_state()
        QTimer.singleShot(0, self.refresh)

    def _add_setname(self, code, name):
        _, pack = self.current()
        if pack is None:
            return
        settings = store.pack_diy(pack)
        code = code or store.next_setcode(settings["setnames"], self._taken_setcodes(pack))   # 避开已经被用掉的编号
        settings["setnames"][code] = name
        store.set_pack_diy(pack, settings)
        self._save_state()
        self.refresh()

    def _remove_setname(self, code):
        _, pack = self.current()
        if pack is None:
            return
        settings = store.pack_diy(pack)
        settings["setnames"].pop(code, None)
        store.set_pack_diy(pack, settings)
        self._save_state()
        self.refresh()

    def _change_target(self):
        from ygopack import mdpro3
        path = QFileDialog.getExistingDirectory(self.panel, "选 MDPro3 的安装目录，或任意扩展卡包目录")
        if path:
            mdpro3.set_custom_dir(path)
            self.refresh()

    def _reset_target(self):
        from ygopack import mdpro3
        mdpro3.set_custom_dir(None)
        self.refresh()

    # ------------------------------------------------------------ 后台任务

    def _run_async(self, work, done):
        box = {}

        def run():
            try:
                box["result"] = work()
            except Exception:
                box["error"] = traceback.format_exc()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        timer = QTimer(self.panel)
        timer.setInterval(100)

        def poll():
            if thread.is_alive():
                return
            timer.stop()
            timer.deleteLater()
            if "error" in box:
                _log("DIY 工作台后台任务失败:\n" + box["error"])
            done(box.get("result"), box.get("error"))

        timer.timeout.connect(poll)
        timer.start()

    def core(self):
        """测试沙盒的引擎（进程里只能有一个，建一次一直用）。"""
        if self._core is None:
            from sandbox.core import Core
            self._core = Core()
        return self._core

    def _check_current(self):
        tab, _ = self.current()
        if tab is None or self._busy:
            return
        result = store.generate(tab)
        if result.error or not result.lua:
            self.effect_page.add_check_lines([("×", result.error or "这张卡没有脚本")])
            return
        rec = dict(result.rec)
        rec["code"] = rec["code"] or 100000000    # 还没卡号也能检查
        lua = result.lua.encode("utf-8")
        uid = tab.get("_card_uid")
        self._busy = True

        def work():
            from sandbox.probe import load_check
            from ygopack.cardinfo import token_records
            with self._core_lock:
                core = self.core()
                core.add_card(rec)
                for token in token_records(result.model, rec["code"]):    # DIY 衍生物
                    core.add_card(token)
                return load_check(core, rec["code"], lua)

        def done(value, error):
            self._busy = False
            if error:
                lines = [("×", "沙盒检查没能运行：%s" % error.strip().splitlines()[-1])]
            else:
                loaded, errs = value
                lines = [("√", "脚本能被引擎加载、注册效果，发动检查没有出错（测试沙盒）")] if loaded and not errs else \
                    [("×", "脚本没有被读到")] if not loaded else [("×", e) for e in errs]
            self._last_check[uid] = lines
            self.effect_page.add_check_lines(lines)
            self.code_page.show_lines(self._script_findings + lines)
            self._script_findings = []

        self.effect_page.add_check_lines([("…", "正在测试沙盒里检查……")])
        self._run_async(work, done)

    def _edit_media(self):
        from .media_dialog import MediaDialog
        from card_tabs import _card_tabs_asset_dir
        tab, _ = self.current()
        if tab is not None and MediaDialog(tab, _card_tabs_asset_dir(), self.panel).exec_():
            self.manager()._request_write_state()
            self.refresh()

    # ------------------------------------------------------------ 脚本页

    def _refresh_code(self, tab):
        diy = store.card_diy(tab)
        result = store.generate(tab)
        data = tab.get("data") or {}
        code = str(data.get("cardpass") or "")
        title = "c%s.lua  ·  %s" % (code or "（还没有卡号）", data.get("name", ""))
        self.code_page.show_card(tab.get("_card_uid"), title, diy.get("script") or result.lua, result.desc or data.get("effect_text", ""),
                                 result.strings or [], diy.get("strings") or {}, bool(diy.get("script")))

    def _save_script(self):
        tab, _ = self.current()
        if tab is None:
            return
        diy = store.card_diy(tab)
        text = self.code_page.text()
        if text.strip():
            diy["script"] = text
        strings = self.code_page.custom_strings()
        if strings:
            diy["strings"] = strings
        else:
            diy.pop("strings", None)
        self.code_page.editor.document().setModified(False)
        self.manager()._request_write_state()
        self._refresh_code(tab)
        self.code_page.show_lines(self.code_page.diagnostics() or [("√", "已保存，静态检查通过；能不能运行请点「检查报错」")])

    def _reset_script(self):
        tab, _ = self.current()
        if tab is None or not store.card_diy(tab).get("script"):
            return
        if QMessageBox.question(self.panel, "改回积木生成", "手写的脚本会被删除，改用积木生成。确定吗？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        store.card_diy(tab).pop("script", None)
        self.code_page.editor.document().setModified(False)
        self.code_page.card_key = None
        self.manager()._request_write_state()
        self._refresh_code(tab)

    def _check_script(self):
        self._save_script()
        found = self.code_page.diagnostics()
        if any(mark == "×" for mark, _ in found):
            return
        self._script_findings = found
        self._check_current()

    def _generate_script(self):
        """把请求发给伊格尼斯；写好的脚本走候选，玩家应用后才生效。"""
        dock = getattr(self.app, "_ai_dock", None)
        if dock is None:
            return
        dock.toggle.setChecked(True)
        controller = dock.controller
        if controller is not None and controller.worker is None:
            controller.panel.input.setPlainText("按这张卡的效果文字写完整的 Lua 脚本，写好后测试。")
            controller.send()

    def _export_code_image(self):
        tab, _ = self.current()
        if tab is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.panel, "导出代码图片", "c%s.png" % ((tab.get("data") or {}).get("cardpass") or "script"), "PNG 图片 (*.png)")
        if path and self.code_page.render_image().save(path):
            self.code_page.show_lines([("√", "代码图片已保存到 %s" % path)])

    def _script_path(self, tab):
        from ygopack import mdpro3
        folder = os.path.join(mdpro3.app_dir(), "DIY脚本")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "c%s.lua" % ((tab.get("data") or {}).get("cardpass") or tab.get("_card_uid")))

    def _open_script(self):
        tab, _ = self.current()
        if tab is None:
            return
        path = self._script_path(tab)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(self.code_page.text())
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        self.code_page.show_lines([("…", "已用外部编辑器打开，改完保存后点「重新载入」")])

    def _reload_script(self):
        tab, _ = self.current()
        if tab is None:
            return
        path = self._script_path(tab)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as stream:
                self.code_page.set_text(stream.read())
            self.code_page.show_lines([("√", "已从外部文件载入，点「保存脚本」后才生效")])
        else:
            self.code_page.card_key = None
            self._refresh_code(tab)

    # ------------------------------------------------------------ 导入导出

    def _assets(self):
        from card_tabs import _card_tabs_asset_dir
        return _card_tabs_asset_dir()

    def _transfer(self, action):
        from . import transfer
        m = self.manager()
        tab, pack = self.current()
        if m is None or pack is None:
            return
        if action == "import":
            path, _ = QFileDialog.getOpenFileName(self.panel, "导入卡片或卡包", "", "卡片或卡包 (*.ydiy *.ypk)")
            if path:
                self._import_path(path)
            return
        m._save_current_snapshot(full=True)
        single = action in ("export_card", "text_card")
        title = (tab if single else pack).get("title") or "DIY"
        if action.startswith("text_"):
            self._export_text(title, [tab] if single else pack.get("tabs", []))
            return
        filters = "YGODIY 文件 (*.ydiy);;MDPro3 卡包 (*.ypk)" if single else "YGODIY 文件 (*.ydiy)"
        path, chosen = QFileDialog.getSaveFileName(self.panel, "导出这张卡" if single else "导出这个卡包", title + transfer.EXTENSION, filters)
        if not path:
            return
        if "ypk" in chosen:
            self._export(False, {"title": title, "tabs": [tab], "diy": pack.get("diy") or {}}, path)
            return
        transfer.export_file(path, "card" if single else "pack", title, [tab] if single else pack.get("tabs", []), pack.get("diy"), self._assets())
        self.pack_page.show_results([("√", "已导出到 %s" % path)], "导出完成", True)

    def _export_text(self, title, tabs):
        from . import card_text
        path, _ = QFileDialog.getSaveFileName(self.panel, "导出卡片文字", title + ".txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            card_text.export(path, tabs)
        except OSError as error:
            QMessageBox.warning(self.panel, "导出失败", "文件写不进去：%s" % error)
            return
        self.pack_page.show_results([("√", "已导出到 %s" % path)], "导出完成", True)

    def _import_path(self, path):
        from . import transfer
        from diy_workbench.ai.project_access import ProjectAccess
        m = self.manager()
        try:
            result = transfer.read_file(path, self._assets(), m._default_data)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
            QMessageBox.warning(self.panel, "导入失败", "这个文件读不出来：%s" % error)
            return
        self.import_result(ProjectAccess(self.app), result)

    def import_result(self, project, result):
        """卡片加进当前卡包，卡包文件新建一个卡包；导入后切到导入的第一张卡。"""
        project.flush()
        tabs = result["tabs"]
        if result["kind"] == "card":
            pack = self.current()[1]
            for tab in tabs:
                project.insert({"kind": "card", "pack_id": project.pack_id(pack), "document": tab, "images": {}})
        else:
            pack = {"title": result["title"], "current_index": 0, "tabs": tabs}
            if result["diy"]:
                pack["diy"] = result["diy"]
            project.insert({"kind": "pack", "id": uuid.uuid4().hex, "document": pack, "images": {}})
        project.refresh(pack, tabs[0])
        self.pack_page.show_results([("√", "导入了 %d 张卡" % len(tabs))], "导入完成", True)
        self.refresh()

    # ------------------------------------------------------------ 已安装

    def _recycle_folder(self):
        from ygopack import mdpro3
        return os.path.join(mdpro3.app_dir(), "DIY卡包导出", "回收站")

    def _refresh_installed(self):
        from . import transfer
        from ygopack import expansion, mdpro3
        target, note = mdpro3.expansions_dir()

        def done(value, error):
            rows, recycled = value or ([], [])
            self.installed_page.show_packs(target or note, rows)
            self.installed_page.show_bin(recycled)

        self._run_async(lambda: (expansion.list_packs(target), transfer.recycled(self._recycle_folder())), done)

    def _open_expansions(self):
        from ygopack import mdpro3
        target, _ = mdpro3.expansions_dir()
        if target and os.path.isdir(target):
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _uninstall(self, path):
        from . import transfer
        from ygopack import expansion, mdpro3
        if not os.path.basename(path).startswith(expansion.YGODIY_PREFIX):
            QMessageBox.information(self.panel, "不能卸载", "这个卡包不是 YGODIY 导出的，请自己在目录里管理。")
            return
        if QMessageBox.question(self.panel, "卸载卡包", "要从 MDPro3 卸载 %s 吗？\n卡包会进回收站，它解压出来的动态卡图也会清除，恢复后 MDPro3 会重新解压。" % os.path.basename(path),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            _, removed = transfer.uninstall(path, self._recycle_folder(), mdpro3.expansions_dir()[0])
            self.installed_page.notice = "已卸载，清除了 %d 个动态卡图。" % removed
            self._known.clear()
            self._refresh_installed()

    def _restore_pack(self, path):
        from . import transfer
        from ygopack import mdpro3
        target, note = mdpro3.expansions_dir()
        try:
            if not target:
                raise ValueError(note)
            transfer.restore(path, target)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self.panel, "恢复失败", str(error))
            return
        self._known.clear()
        self._refresh_installed()

    def _purge_pack(self, path):
        from . import transfer
        if QMessageBox.question(self.panel, "彻底删除", "彻底删除 %s 吗？删除后不能恢复。" % os.path.basename(path),
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            transfer.purge(path)
            self._refresh_installed()

    def _edit_card_data(self):
        from .card_data_dialog import CardDataDialog
        tab, _ = self.current()
        if tab is not None and CardDataDialog(tab, self.panel).exec_():
            self.manager()._request_write_state()
            self.refresh()

    def _export(self, install, pack=None, save_to=None, marks=(), finished=None):
        """finished 给 AI 用：(成功, 结果行, 总结, 沙盒验证没过)。marks 非空表示玩家已同意强制导出。"""
        if self._busy:
            if finished:
                finished(False, [], "工作台正在导出，请稍后再试。", False)
            return
        m = self.manager()
        pack = pack or self.current()[1]
        if m is None or pack is None:
            return
        try:
            m._save_current_snapshot(full=True)   # 当前卡的最新数据（含卡图）
        except Exception:
            _log("导出前保存当前卡失败:\n" + traceback.format_exc())
        if not install and not save_to:
            save_to, _ = QFileDialog.getSaveFileName(self.panel, "导出卡包",
                                                     "ygodiy-%s.ypk" % pack.get("title", "DIY"), "卡包 (*.ypk)")
            if not save_to:
                return
        from ygopack import build as ypbuild, mdpro3
        manifest = store.manifest(pack, pack.get("tabs", []))
        try:
            from card_tabs import _card_tabs_asset_dir
            assets = _card_tabs_asset_dir()
        except Exception:
            assets = os.path.join(mdpro3.app_dir(), "制卡器标签页资源")
        out_dir = os.path.join(mdpro3.app_dir(), "DIY卡包导出")
        self._busy = True
        self.pack_page.set_busy(True)
        self.pack_page.show_results([("…", "正在导出并在测试沙盒里验证……")])

        def work():
            lines = []
            md_dir, _ = mdpro3.find_mdpro3()
            target, note = mdpro3.expansions_dir()
            stem = "ygodiy-" + ypbuild.slug(manifest["name"]) + ".ypk"
            known = ypbuild.known_codes(md_dir, skip_file=stem, expansions=target)
            out, report = ypbuild.build_manifest(manifest, out_dir, out_dir, assets, known)
            for level, card, text in report.items:
                lines.append(("×" if level == "错误" else "!", ("%s：%s" % (card, text)) if card else text))
            if not out:
                if any("已被" in text for _, _, text in report.items):
                    diy = store.pack_diy(pack)
                    free = store.free_code_start(diy["code_start"], diy["code_step"], len(manifest["cards"]), known)
                    lines.append(("!", "卡号和已有的卡冲突：可以在「卡包设置」把卡号起点改成 %d，再点「按顺序重新分配」" % free))
                return False, lines, "有错误，没有导出。改好后再点一次。", False
            from ygopack.verify import verify
            with self._core_lock:
                ok, vlines = verify(out, (), self.core())
            lines.extend(_verify_lines(vlines))
            if not ok and not marks:
                return False, lines, "测试沙盒验证没有通过，没有安装。", True
            if marks:
                ypbuild.mark_unverified(out, marks)
                lines.append(("!", "卡包已标记「未通过验证」"))
            if save_to:
                shutil.copyfile(out, save_to)
                return True, lines, "已导出到 %s" % save_to, False
            if not target:
                return False, lines, "导出了，但不能安装：%s（卡包在 %s）" % (note, out), False
            os.makedirs(target, exist_ok=True)
            dest = os.path.join(target, os.path.basename(out))
            shutil.copyfile(out, dest)
            return True, lines, "已装进 %s · 重启 MDPro3 后生效" % dest, False

        def done(value, error):
            self._busy = False
            self.pack_page.set_busy(False)
            if error:
                self.pack_page.show_results([("×", error.strip().splitlines()[-1])], "导出时出错了", ok=False)
                if finished:
                    finished(False, [], "导出时出错了", False)
                return
            ok, lines, summary, verify_failed = value
            self.pack_page.show_results(lines, summary, ok)
            self._known.clear()                  # 装进去以后 MDPro3 里的卡号变了，重新核查
            self.refresh()
            if finished:
                finished(ok, lines, summary, verify_failed)
            elif verify_failed and QMessageBox.question(self.panel, "沙盒验证没有通过",
                    "这个卡包没有通过测试沙盒的验证。仍然继续的话，卡包里会标记「未通过验证」。",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                self._export(install, pack, save_to, ["沙盒加载检查没有通过"])

        self._run_async(work, done)


# ---------------------------------------------------------------- 主窗口调用的入口

def install(app):
    app._workbench_mode_index = app.combo_box.count()
    app.combo_box.addItem(MODE_LABEL)
    app._workbench = Workbench(app)


def enter(app, switch_to_ocg):
    wb = getattr(app, "_workbench", None)
    if wb is not None:
        wb.enter(switch_to_ocg)


def leave(app):
    wb = getattr(app, "_workbench", None)
    if wb is not None:
        wb.leave()
