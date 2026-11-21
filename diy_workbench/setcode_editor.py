"""卡包字段定义的编辑，以及在当前字段积木中选用定义。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QMessageBox, QToolButton, QWidget

from . import dialogs, setnames, store
from .block_editor import ROLE_NODE


class SetcodeButtons(QWidget):
    requested = pyqtSignal(str)

    def __init__(self, number_edit, names, ready):
        super().__init__()
        self.number_edit = number_edit
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.buttons = {}
        for action, label in (("new", "新建字段…"), ("edit", "修改…"), ("remove", "删除名称"), ("find", "查找字段…")):
            button = QToolButton()
            button.setText(label)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _, op=action: self.requested.emit(op))
            row.addWidget(button)
            self.buttons[action] = button
        row.addStretch(1)
        self.buttons["edit"].setToolTip("修改本包定义的字段编号或名称")
        self.buttons["remove"].setToolTip("移除本包的字段名称，保留卡片和积木对编号的引用")
        self.number_edit.textChanged.connect(self._update)
        self.configure(names, ready)

    def configure(self, names, ready):
        self.names, self.ready = names, ready
        self._update()

    def _update(self):
        owned = setnames.field_key(self.number_edit.text()) in self.names
        self.buttons["new"].setEnabled(self.ready)
        self.buttons["edit"].setEnabled(self.ready and owned)
        self.buttons["remove"].setEnabled(owned)
        self.buttons["find"].setEnabled(self.ready)


class SetcodeEditor:
    def __init__(self, workbench):
        self.wb = workbench
        self.editor = workbench.effect_page.editor
        self.editor.fields.setcode_actions = self.block_buttons
        workbench.pack_page.setname_requested.connect(self.edit_definition)
        workbench.pack_page.setname_removed.connect(self.remove_definition)

    def block_buttons(self, number_edit):
        _, pack = self.wb.current()
        names = store.pack_diy(pack or {})["setnames"]
        ready = pack is not None and self.wb.known_codes(pack) is not None
        buttons = SetcodeButtons(number_edit, names, ready)
        buttons.requested.connect(self._block_action)
        return buttons

    def index_ready(self, pack):
        buttons = self.editor.fields.findChild(SetcodeButtons)
        if buttons:
            buttons.configure(store.pack_diy(pack)["setnames"], True)

    def edit_definition(self, old, suggested_code="", suggested_name=""):
        _, pack = self.wb.current()
        if pack is None:
            return None
        names = store.pack_diy(pack)["setnames"]
        used = self.wb._taken_setcodes(pack)
        if old:
            if old not in names:
                return None
            suggested_code, suggested_name = old, names[old]
        elif suggested_code and (suggested_code in names or setnames.base_occupied(int(suggested_code, 16), used)):
            suggested_code, suggested_name = "", ""
        dlg = dialogs.NameCodeDialog("字段", bool(old), suggested_name, suggested_code, self.wb.panel)
        while dlg.exec_() == dlg.Accepted:
            if self.wb.current()[1] is not pack:
                return None
            name = dlg.title_edit.text().strip()
            try:
                code = dlg.number_edit.text().strip() or store.next_setcode(names, used)
                reviews = self._change(pack, old, code, name, used)
            except ValueError as error:
                QMessageBox.warning(dlg, "字段设置", str(error))
                continue
            self.wb._save_state()
            if self.wb.tabs.currentWidget() is self.wb.effect_page:
                self.editor.tree.refresh_selection(self.wb.refresh)
                if reviews:
                    QMessageBox.information(self.wb.panel, "请核对手写 Lua",
                                            "以下卡片有用途不明确的同值数字，请核对：\n" + "、".join(reviews))
            else:
                self.wb.refresh()
                if reviews:
                    self.wb.pack_page.show_results([("!", title + " 的 Lua 含同值常量，请核对其用途。") for title in reviews],
                                                   "字段已调整，以下脚本需核对")
            return setnames.field_key(code), name
        return None

    def _change(self, pack, old, code, name, used):
        # 改号会替换实际受影响卡片的 DIY 数据，这些卡的旧沙盒结果须重新验证。
        checked = self.wb._last_check
        tracked = []
        if old and checked:
            tracked = [(card, card.get("diy")) for card in pack.get("tabs", ()) if card.get("_card_uid") in checked]
        reviews = setnames.change(pack, old, code, name, used)
        for card, previous in tracked:
            if card.get("diy") is not previous:
                checked.pop(card["_card_uid"], None)
        return reviews

    def remove_definition(self, code):
        _, pack = self.wb.current()
        if pack is None:
            return
        settings = store.pack_diy(pack)
        if code in settings["setnames"]:
            del settings["setnames"][code]
            store.set_pack_diy(pack, settings)
            self.wb._save_state()
            self.wb.refresh()

    def _find(self, pack):
        entries = [(code, name, "", "本包") for code, name in store.pack_diy(pack)["setnames"].items()]
        dlg = dialogs.BlockSetcodeDialog(entries + self.wb.searchable_setnames(), self.wb.panel)
        return dlg.selected() if dlg.exec_() == dlg.Accepted else None

    def _block_action(self, action):
        tab, pack = self.wb.current()
        tree, fields = self.editor.tree, self.editor.fields
        if pack is None or fields.item is None:
            return
        path = tree.selection_path()
        node = fields.item.data(0, ROLE_NODE)
        code = setnames.field_key(node.get("setcode"))
        if action == "remove":
            self.remove_definition(code)
        else:
            if action == "find":
                choice = self._find(pack)
            elif action == "new":
                choice = self.edit_definition("", code, node.get("name") or "")
            else:
                choice = self.edit_definition(code)
            if not choice or self.wb.current()[0] is not tab or tree.selection_path() != path or fields.item is None:
                return
            fields.set_values(tree, {"setcode": choice[0], "name": choice[1]})
        fields.show_item(tree, tree.currentItem())
