"""工作台的对话框：这张卡的字段（SetcodeDialog）、查找官方字段（OfficialSetcodeDialog）、勾选若干项（MultiChoiceDialog）。

效果本身用积木编辑（block_editor），不再用对话框填模板。
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)


class OfficialSetcodeSearch(QWidget):
    """按名字（中文 / 日文）或编号查字段：官方字段，加上已装扩展包里玩家自创的字段（第 4 项是来源）。
    双击一行发出 picked(编号, 名字)。"""

    picked = pyqtSignal(str, str)

    def __init__(self, official, parent=None):
        super().__init__(parent)
        self.official = official
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入字段名或编号查找，如 罪宝、星杯、0x19e")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setMinimumHeight(220)
        self.list.itemDoubleClicked.connect(lambda it: self.picked.emit(it.data(Qt.UserRole), it.data(Qt.UserRole + 1)))
        lay.addWidget(self.list)
        self.count = QLabel()
        self.count.setStyleSheet("color:#666666;")
        lay.addWidget(self.count)
        self.filter("")

    def filter(self, text):
        key = text.strip().lower()
        hexkey = key[2:] if key.startswith("0x") else key
        self.list.clear()
        for entry in self.official:
            code, zh, jp = entry[:3]
            source = entry[3] if len(entry) > 3 else ""
            if key and key not in zh.lower() and key not in jp.lower() and key not in source.lower() \
                    and hexkey != code[2:] and key != code:
                continue
            item = QListWidgetItem("%s　%s%s%s" % (code, zh, ("　" + jp) if jp and jp != zh else "",
                                                 "　〔%s〕" % source if source else ""))
            if source:
                item.setForeground(QColor("#1f4e8c"))
                item.setToolTip("玩家自创的字段，来自%s" % source)
            item.setData(Qt.UserRole, code)
            item.setData(Qt.UserRole + 1, zh)
            self.list.addItem(item)
        if not self.official:
            self.count.setText("没有找到 MDPro3 的官方字段表（strings.conf）")
        else:
            diy = sum(1 for e in self.official if len(e) > 3 and e[3])
            self.count.setText("找到 %d 个（官方字段 %d 个，已装扩展包里的自创字段 %d 个）；双击加上"
                               % (self.list.count(), len(self.official) - diy, diy))


class OfficialSetcodeDialog(QDialog):
    """卡包页的「查找官方字段」：查到以后双击，加到当前卡上（added(编号, 名字) 由工作台处理）。"""

    added = pyqtSignal(str, str)

    def __init__(self, official, card_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查找字段")
        self.resize(520, 480)
        root = QVBoxLayout(self)
        tip = QLabel("双击一行：把这个字段加到当前卡「%s」上（一张卡最多 4 个字段）" % card_name if card_name else
                     "双击一行：把这个字段加到当前卡上")
        tip.setWordWrap(True)
        root.addWidget(tip)
        self.search = OfficialSetcodeSearch(official)
        self.search.picked.connect(self._picked)
        root.addWidget(self.search, 1)
        self.status = QLabel()
        self.status.setStyleSheet("color:#2c6e2f;")
        root.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _picked(self, code, name):
        self.added.emit(code, name)

    def show_status(self, text, ok=True):
        self.status.setStyleSheet("color:%s;" % ("#2c6e2f" if ok else "#b3261e"))
        self.status.setText(text)


class SetcodeDialog(QDialog):
    """这张卡属于哪些字段：卡包里自己的字段勾选，官方字段填编号。"""

    def __init__(self, setnames, chosen, parent=None, official=None):
        super().__init__(parent)
        self.setWindowTitle("这张卡的字段")
        root = QVBoxLayout(self)
        self.boxes = {}
        if setnames:
            root.addWidget(QLabel("卡包里自己的字段"))
            for code, name in setnames.items():
                box = QCheckBox("%s（%s）" % (name, code))
                box.setChecked(code in chosen)
                self.boxes[code] = box
                root.addWidget(box)
        else:
            root.addWidget(QLabel("卡包里还没有自己的字段，可以到「卡包」页新建。"))
        root.addWidget(QLabel("官方字段的编号（多个用逗号隔开，如 0x19e）"))
        self.extra = QLineEdit(", ".join(c for c in chosen if c not in setnames))
        root.addWidget(self.extra)
        if official:                                  # 不记得编号：按名字查，双击填进上面
            root.addWidget(QLabel("查找官方字段（双击填进上面）"))
            search = OfficialSetcodeSearch(official)
            search.picked.connect(self._add_official)
            root.addWidget(search, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_official(self, code, _name):
        parts = [p.strip().lower() for p in self.extra.text().replace("，", ",").split(",") if p.strip()]
        if code not in parts:
            parts.append(code)
        self.extra.setText(", ".join(parts))

    def value(self):
        out = [c for c, b in self.boxes.items() if b.isChecked()]
        for part in self.extra.text().replace("，", ",").split(","):
            part = part.strip().lower()
            if part.startswith("0x") and part not in out:
                try:
                    int(part, 16)
                    out.append(part)
                except ValueError:
                    pass
        return out[:4]


class MultiChoiceDialog(QDialog):
    """勾选若干项（发动 / 适用的位置）。"""

    def __init__(self, title, options, chosen, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        root = QVBoxLayout(self)
        self.boxes = {}
        self.initial = list(chosen or [])   # 原来的顺序
        for v, label in options:
            box = QCheckBox(label)
            box.setChecked(v in self.initial)
            self.boxes[v] = box
            root.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def value(self):
        checked = [v for v, b in self.boxes.items() if b.isChecked()]
        return [v for v in self.initial if v in checked] + [v for v in checked if v not in self.initial]
