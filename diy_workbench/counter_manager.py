"""协调卡包页和效果积木对同一份指示物目录的操作。"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QMessageBox

from effect_model.counters import clean_names, counter_code, counter_name
from ygopack import mdpro3
from . import counter_catalog, store
from .block_editor import ROLE, ROLE_NODE
from .counter_widgets import CounterPicker, CounterSearch
from .dialogs import NameCodeDialog


SCAN_BATCH = 128  # 大卡包每批归集的卡片数，批次之间让界面处理输入。


class CounterManager:
    def __init__(self, workbench):
        self.wb = workbench
        self.official = None
        self.installed = {}
        self.scan_revision = 0
        self.editor = workbench.effect_page.editor
        self.editor.fields.counters = self
        page = workbench.pack_page
        page.counter_list.action.connect(self.action)
        page.name_tabs.currentChanged.connect(lambda _: self.show_pack())

    def external(self, pack):
        if self.official is None:
            rows = mdpro3.official_counters()
            names = clean_names({code: name for code, name, _ in rows})
            self.official = {code: (name, "官方") for code, name in names.items()}
            self.official.setdefault("0x1", ("魔力指示物", "官方"))
        result = dict(self.official)
        for code, entry in self.installed.get(self.wb._stem(pack), {}).items():
            result.setdefault(code, entry)
        manager = self.wb.manager()
        for other in (manager.packs if manager else ()):
            if other is not pack:
                for code, name in store.pack_diy(other)["counters"].items():
                    result.setdefault(code, (name, "卡包「%s」" % other.get("title", "")))
        return result

    def entries(self, pack):
        result = self.external(pack)
        for code, name in store.pack_diy(pack)["counters"].items():
            result[code] = (name, "本包")
        return result

    def labels(self, pack):
        return {code: value[0] for code, value in self.entries(pack).items()}

    def show_pack(self, select=""):
        page, pack = self.wb.pack_page, self.wb.current()[1]
        self.scan_revision += 1
        revision = self.scan_revision
        if pack is None or page.name_tabs.currentWidget() is not page.counter_list:
            return
        ready = self.wb.known_codes(pack) is not None
        tabs = tuple(pack.get("tabs", ()))
        if len(tabs) <= SCAN_BATCH:
            self._show_rows(pack, counter_catalog.used_codes(pack), ready, select)
            return
        self._show_rows(pack, set(), False, select)
        page.counter_list.note.setText("正在整理本包卡片使用的指示物…")
        used = set()

        def scan(start):
            if revision != self.scan_revision or self.wb.current()[1] is not pack or self.wb.tabs.currentWidget() is not page:
                return
            for tab in tabs[start:start + SCAN_BATCH]:
                used.update(counter_catalog.card_codes(tab))
            if start + SCAN_BATCH < len(tabs):
                QTimer.singleShot(0, lambda: scan(start + SCAN_BATCH))
            else:
                self._show_rows(pack, used, ready, select)
        QTimer.singleShot(0, lambda: scan(0))

    def _show_rows(self, pack, used, ready, select):
        external = self.external(pack)
        own = store.pack_diy(pack)["counters"]
        rows = {}
        for code in sorted(used | own.keys(), key=lambda c: int(c, 16)):
            origin = external.get(code)
            name = own.get(code) or (origin[0] if origin else "未命名")
            source = origin[1] if origin else ("本包" if code in own else "已使用")
            if code in own and origin and name != origin[0]:
                source = "与%s的「%s」重号" % (origin[1], origin[0])
            rows[code] = (name, source)
        self.wb.pack_page.counter_list.populate(rows, set(own), own.keys() | (used - external.keys()), ready, select)

    def sync_labels(self, pack, tab):
        if counter_catalog.card_codes(tab):
            self.wb.known_codes(pack)
        tree = self.editor.tree
        names = self.labels(pack)
        if names != tree.counter_names:
            tree.counter_names = names
            for it in tree.findItems("", Qt.MatchContains | Qt.MatchRecursive):
                if it.data(0, ROLE) == "block" and "counter" in it.data(0, ROLE_NODE):
                    tree.paint(it)
        return names

    def picker(self, value):
        _, pack = self.wb.current()
        entries = self.entries(pack)
        owned = set(store.pack_diy(pack)["counters"])
        picker = CounterPicker(value, entries, owned, self.wb.known_codes(pack) is not None)
        picker.action.connect(lambda op, code: self.action(op, code, for_block=True))
        return picker

    def index_ready(self, pack):
        self.wb._refresh_effect(self.wb.current()[0], pack)
        picker = self.editor.fields.findChild(CounterPicker)
        if picker:
            entries = self.entries(pack)
            picker.populate(entries, set(store.pack_diy(pack)["counters"]), True)

    def remember_choice(self, code):
        pack = self.wb.current()[1]
        if pack is not None:
            settings = store.pack_diy(pack)
            external = self.external(pack)
            if code not in settings["counters"] and code in external:
                settings["counters"][code] = external[code][0]
                store.set_pack_diy(pack, settings)
                return True
        return False

    def _edit(self, pack, old, external, used):
        own = store.pack_diy(pack)["counters"]
        name = own.get(old, "")
        dlg = NameCodeDialog("指示物", bool(old), name, old, self.wb.panel)
        while dlg.exec_() == dlg.Accepted:
            try:
                return counter_catalog.change(pack, old, dlg.number_edit.text().strip(), dlg.title_edit.text(), external, used)
            except ValueError as error:
                QMessageBox.warning(dlg, "指示物设置", str(error))
        return "", []

    def action(self, operation, current, for_block=False):
        tab, pack = self.wb.current()
        if pack is None:
            return
        settings = store.pack_diy(pack)
        code, reviews = current, []
        if operation == "remove":
            settings["counters"].pop(current, None)
            store.set_pack_diy(pack, settings)
        else:
            used = counter_catalog.used_codes(pack)
            external = self.external(pack)
            if operation == "find":
                choices = self.entries(pack)
                for key in used - choices.keys():
                    choices[key] = (counter_name(key), "本包已使用")
                dlg = CounterSearch(choices, current, self.wb.panel)
                if dlg.exec_() != dlg.Accepted or not dlg.selected():
                    return
                code = dlg.selected()
                self.remember_choice(code)
            else:
                code, reviews = self._edit(pack, current if operation == "edit" else "", external, used)
                if not code:
                    return
                if operation == "edit" and current != code:
                    for card in pack.get("tabs", ()):
                        uid = card.get("_card_uid")
                        if uid in self.wb._last_check and code in counter_catalog.card_codes(card):
                            self.wb._last_check.pop(uid)
        if for_block:
            self._refresh_block(tab, code)
        else:
            self.wb._refresh_pack(pack, selected_counter=code)
        self.wb._save_state()
        if reviews:
            QMessageBox.information(self.wb.panel, "请核对手写 Lua", "以下卡片还有用途不明确的同值数字，请核对：\n" + "、".join(reviews))

    def _refresh_block(self, tab, code):
        if tab is not self.wb.current()[0]:
            return
        tree = self.editor.tree
        it = tree.refresh_selection(self.wb.refresh)
        if it is not None and it.data(0, ROLE) == "block" and "counter" in it.data(0, ROLE_NODE):
            field = self.editor.fields
            if counter_code(it.data(0, ROLE_NODE)["counter"]) != code:
                field.set(tree, "counter", code)
            field.show_item(tree, it)
