"""卡包与积木共享的指示物列表、选择框和查找框。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QToolButton, QToolTip, QVBoxLayout, QWidget)

from effect_model.counters import counter_code, counter_name


def _item(view, code, name, source):
    item = QListWidgetItem("%s　%s%s" % (code, name, "　〔%s〕" % source if source else ""))
    item.setData(Qt.UserRole, code)
    view.addItem(item)
    return item


class CounterList(QWidget):
    action = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setMaximumHeight(110)
        self.list.itemDoubleClicked.connect(lambda _: self.request("edit"))
        self.list.currentItemChanged.connect(self._buttons)
        layout.addWidget(self.list)
        row = QHBoxLayout()
        self.buttons = {}
        for action, text in (("new", "＋ 新建指示物"), ("edit", "修改"), ("remove", "删除"), ("find", "查找…")):
            button = QPushButton(text)
            button.clicked.connect(lambda _, op=action: self.request(op))
            row.addWidget(button)
            self.buttons[action] = button
        row.addStretch(1)
        layout.addLayout(row)
        self.buttons["remove"].setToolTip("删除本包的名称后，使用它的积木会按编号或已有来源名称显示。")
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addStretch(1)
        self.owned, self.editable, self.ready = set(), set(), False
        self._buttons()

    def selected(self):
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else ""

    def request(self, operation):
        if self.buttons[operation].isEnabled():
            self.action.emit(operation, self.selected())

    def _buttons(self, *_):
        code = self.selected()
        self.buttons["new"].setEnabled(self.ready)
        self.buttons["find"].setEnabled(self.ready)
        self.buttons["edit"].setEnabled(self.ready and code in self.editable)
        self.buttons["remove"].setEnabled(code in self.owned)

    def populate(self, rows, owned, editable, ready, select=""):
        select = select or self.selected()
        self.owned, self.editable, self.ready = owned, editable, ready
        self.list.clear()
        for code, (name, source) in rows.items():
            item = _item(self.list, code, name, source)
            if code == select:
                self.list.setCurrentItem(item)
        self.note.setText("双击可修改本包定义或给已有编号命名。" if ready else "正在读取已安装的指示物…")
        self._buttons()


class CounterSearch(QDialog):
    def __init__(self, entries, current, parent):
        super().__init__(parent)
        self.setWindowTitle("查找指示物")
        self.resize(480, 420)
        self.entries = entries
        self.current = current
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("输入名称、来源、十进制或 0x 编号")
        self.query.setClearButtonEnabled(True)
        layout.addWidget(self.query)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = buttons.button(QDialogButtonBox.Ok)
        self.ok.setText("选用")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.query.textChanged.connect(self.filter)
        self.filter("")

    def filter(self, text):
        key = text.strip().casefold()
        try:
            exact = counter_code(key)
        except ValueError:
            exact = None
        self.list.clear()
        exact_item = None
        for code, (name, source) in self.entries.items():
            matches_number = (code == exact or code.startswith(key) or code[2:].startswith(key)
                              or str(int(code, 16)).startswith(key))
            if key and not matches_number and key not in (name + source).casefold():
                continue
            item = _item(self.list, code, name, source)
            if code == exact:
                exact_item = item
            if code == self.current:
                self.list.setCurrentItem(item)
        if exact_item is not None:
            self.list.setCurrentItem(exact_item)
        elif self.list.count() and not self.list.currentItem():
            self.list.setCurrentRow(0)
        self.ok.setEnabled(self.list.currentItem() is not None)

    def selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else ""


class CounterPicker(QWidget):
    picked = pyqtSignal(str)
    action = pyqtSignal(str, str)

    def __init__(self, value, entries, owned, ready, parent=None):
        super().__init__(parent)
        self.code = counter_code(value)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.NoInsert)
        self.combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.combo.setToolTip("可从列表选择，也可直接输入十进制或 0x 编号。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(self.combo)
        row = QHBoxLayout()
        self.buttons = {}
        for op, text in (("new", "新建…"), ("edit", "修改…"), ("remove", "删除名称"), ("find", "查找…")):
            button = QToolButton()
            button.setText(text)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(lambda _, op=op: self.action.emit(op, self.code))
            row.addWidget(button)
            self.buttons[op] = button
        row.addStretch(1)
        layout.addLayout(row)
        self.populate(entries, owned, ready)
        self.combo.activated[int].connect(self._choose)
        self.combo.lineEdit().editingFinished.connect(self._commit)

    def populate(self, entries, owned, ready):
        draft = self.combo.currentText() if self.combo.lineEdit().hasFocus() and self.combo.currentText() != self.combo.itemText(self.combo.currentIndex()) else None
        self.owned, self.ready = owned, ready
        self.available = set(entries)
        self.combo.clear()
        for code, (name, source) in entries.items():
            self.combo.addItem("%s　%s" % (code, name), code)
            self.combo.setItemData(self.combo.count() - 1, source, Qt.ToolTipRole)
        self._display()
        if draft is not None:
            self.combo.setEditText(draft)
        for op in ("find", "new"):
            self.buttons[op].setEnabled(ready)

    def _display(self):
        i = self.combo.findData(self.code)
        if i < 0:
            self.combo.addItem("%s　%s" % (self.code, counter_name(self.code)), self.code)
            i = self.combo.count() - 1
        self.combo.setCurrentIndex(i)
        self.combo.setEditText(self.combo.itemText(i))
        self.buttons["edit"].setEnabled(self.ready and (self.code in self.owned or self.code not in self.available))
        self.buttons["remove"].setEnabled(self.code in self.owned)

    def mark_registered(self, code):
        self.owned.add(code)
        self._display()

    def _choose(self, index):
        code = self.combo.itemData(index)
        if code and code != self.code:
            self.code = code
            self._display()
            self.picked.emit(code)

    def _commit(self):
        text = self.combo.currentText().strip()
        i = self.combo.findText(text, Qt.MatchFixedString)
        if i >= 0:
            self._choose(i)
            return
        try:
            code = counter_code(text)
        except ValueError as error:
            QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), str(error), self)
            self._display()
            return
        if code != self.code:
            self.code = code
            self._display()
            self.picked.emit(code)
        else:
            self._display()
