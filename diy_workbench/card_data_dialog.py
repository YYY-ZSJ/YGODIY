"""卡片数据：提示文本 str1～str16 和效果分类。留空的提示文本、「自动」的分类都跟随积木生成。"""

from PyQt5.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLineEdit, QScrollArea,
                             QVBoxLayout, QWidget)

from blocks.categories import NAMES
from . import store

MAX_STRINGS = 16


class CardDataDialog(QDialog):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.setWindowTitle("卡片数据")
        self.tab = tab
        diy = store.card_diy(tab)
        generated = store.generate(tab)
        auto_strings = generated.strings or []
        saved = diy.get("strings") or {}
        self.auto_category = store.auto_category(tab)
        layout = QVBoxLayout(self)
        columns = QHBoxLayout()
        layout.addLayout(columns, 1)

        hints = QWidget()
        form = QFormLayout(hints)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.strings = []
        for index in range(MAX_STRINGS):
            edit = QLineEdit(saved.get(str(index), ""))
            edit.setPlaceholderText(auto_strings[index] if index < len(auto_strings) else "")
            self.strings.append(edit)
            form.addRow("str%d" % (index + 1), edit)
        scroll = QScrollArea()
        scroll.setWidget(hints)
        scroll.setWidgetResizable(True)
        box = QGroupBox("提示文本（灰字是积木生成的，填了就替换它）")
        QVBoxLayout(box).addWidget(scroll)
        columns.addWidget(box, 1)

        group = QGroupBox("效果分类")
        grid = QGridLayout(group)
        self.auto = QCheckBox("按积木自动判断")
        self.auto.setChecked("category" not in diy)
        self.auto.toggled.connect(self._auto_toggled)
        grid.addWidget(self.auto, 0, 0, 1, 4)
        self.boxes = []
        for index, name in enumerate(NAMES):
            check = QCheckBox(name)
            self.boxes.append(check)
            grid.addWidget(check, index // 4 + 1, index % 4)
        columns.addWidget(group, 1)
        self._show_category(diy.get("category", self.auto_category))
        self._auto_toggled(self.auto.isChecked())

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_category(self, value):
        for index, check in enumerate(self.boxes):
            check.setChecked(bool(value >> index & 1))

    def _auto_toggled(self, automatic):
        if automatic:
            self._show_category(self.auto_category)
        for check in self.boxes:
            check.setEnabled(not automatic)

    def accept(self):
        diy = self.tab.setdefault("diy", {})
        strings = {str(index): edit.text().strip() for index, edit in enumerate(self.strings) if edit.text().strip()}
        if strings:
            diy["strings"] = strings
        else:
            diy.pop("strings", None)
        if self.auto.isChecked():
            diy.pop("category", None)
        else:
            diy["category"] = sum(1 << index for index, check in enumerate(self.boxes) if check.isChecked())
        super().accept()
