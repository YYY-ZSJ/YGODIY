"""工作台的「卡包」页：卡片一览（卡包就是数据库）、卡包设置、自己的字段、导出。"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

GREEN, RED, ORANGE, GREY = "#2c6e2f", "#b3261e", "#9a5a00", "#666666"


def _section(title):
    frame = QFrame()
    frame.setObjectName("diy_section")
    frame.setStyleSheet("QFrame#diy_section{background:#ffffff;border:1px solid #c9c9c9;}")
    box = QVBoxLayout(frame)
    box.setContentsMargins(10, 8, 10, 10)
    label = QLabel(title)
    label.setStyleSheet("font-weight:bold;font-size:15px;")
    box.addWidget(label)
    return frame, box


class PackPage(QWidget):
    card_selected = pyqtSignal(int)          # 点一行：切到那张卡的效果页
    settings_changed = pyqtSignal(dict)      # author / ot / code_start / code_step
    assign_codes = pyqtSignal()
    setname_added = pyqtSignal(str, str)     # 编号, 名字
    setname_removed = pyqtSignal(str)
    export_requested = pyqtSignal(bool)      # True：导出并装进；False：只导出 .ypk
    transfer_requested = pyqtSignal(str)     # import、export_card、export_pack、text_card、text_pack
    change_target = pyqtSignal()
    find_setcode = pyqtSignal()              # 查找字段（官方 + 已装扩展包里的自创字段）
    recheck = pyqtSignal()                   # 重新读一遍 MDPro3 里已有的卡号和字段
    reset_target = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        frame, box = _section("卡片一览")
        self.overview_note = QLabel()
        self.overview_note.setStyleSheet("color:%s;" % GREY)
        box.addWidget(self.overview_note)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["卡号", "卡名", "种类", "字段", "效果", "卡面文字", "检查"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda r, c: self.card_selected.emit(r))
        self.table.setMinimumHeight(170)
        box.addWidget(self.table, 1)
        tip = QLabel("双击一行：切到那张卡的效果页")
        tip.setStyleSheet("color:%s;" % GREY)
        box.addWidget(tip)
        root.addWidget(frame, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        frame, box = _section("卡包设置")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.pack_name = QLabel()
        grid.addWidget(QLabel("包名"), 0, 0)
        grid.addWidget(self.pack_name, 0, 1)
        grid.addWidget(QLabel("作者"), 1, 0)
        self.author = QLineEdit()
        self.author.setPlaceholderText("你的名字（写进卡包信息）")
        self.author.editingFinished.connect(self._emit_settings)
        grid.addWidget(self.author, 1, 1)
        grid.addWidget(QLabel("能用于"), 2, 0)
        self.ot = QComboBox()
        for v, text in ((3, "OCG 和 TCG 卡组都能用"), (1, "只能用于 OCG"), (2, "只能用于 TCG")):
            self.ot.addItem(text, v)
        self.ot.currentIndexChanged.connect(self._emit_settings)
        grid.addWidget(self.ot, 2, 1)
        grid.addWidget(QLabel("卡号"), 3, 0)
        codes = QHBoxLayout()
        codes.addWidget(QLabel("从"))
        self.code_start = QSpinBox()
        self.code_start.setRange(1, 268435455)
        self.code_start.setMinimumWidth(110)
        self.code_start.valueChanged.connect(self._emit_settings)
        codes.addWidget(self.code_start)
        codes.addWidget(QLabel("起，每张间隔"))
        self.code_step = QSpinBox()
        self.code_step.setRange(1, 10000)
        self.code_step.valueChanged.connect(self._emit_settings)
        codes.addWidget(self.code_step)
        assign = QPushButton("按顺序重新分配")
        assign.clicked.connect(self.assign_codes.emit)
        codes.addWidget(assign)
        recheck = QPushButton("重新核查")
        recheck.setToolTip("重新读一遍 MDPro3 里已有的卡号和字段（刚往扩展目录里放了别的卡包时用）")
        recheck.clicked.connect(self.recheck.emit)
        codes.addWidget(recheck)
        codes.addStretch(1)
        grid.addLayout(codes, 3, 1)
        # 核查：这个卡包要用的卡号在 MDPro3 里有没有被占用（官方卡、已装的别的扩展包）
        self.code_status = QLabel()
        self.code_status.setWordWrap(True)
        grid.addWidget(self.code_status, 4, 1)
        note = QLabel("卡号会写进卡面的卡密。隔开 100 是为了不让两张卡共用「1回合1次」的次数。")
        note.setWordWrap(True)
        note.setStyleSheet("color:%s;" % GREY)
        grid.addWidget(note, 5, 1)
        box.addLayout(grid)
        box.addStretch(1)
        row.addWidget(frame, 3)

        frame, box = _section("自己的字段")
        self.setnames = QListWidget()
        self.setnames.setMaximumHeight(110)
        box.addWidget(self.setnames)
        btns = QHBoxLayout()
        add = QPushButton("＋ 新建字段")
        add.clicked.connect(self._add_setname)
        remove = QPushButton("删除选中的")
        remove.clicked.connect(self._remove_setname)
        find = QPushButton("查找字段…")
        find.clicked.connect(self.find_setcode.emit)
        btns.addWidget(add)
        btns.addWidget(remove)
        btns.addWidget(find)
        btns.addStretch(1)
        box.addLayout(btns)
        hint = QLabel("官方字段（如「罪宝」）和已装扩展包里的字段不用在这里新建：点「查找字段」按名字找，双击就加到当前卡上。"
                      "新建的字段会自动避开已经被用掉的编号。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % GREY)
        box.addWidget(hint)
        box.addStretch(1)
        row.addWidget(frame, 2)
        root.addLayout(row)

        frame, box = _section("导出")
        top = QHBoxLayout()
        self.target = QLabel()
        self.target.setWordWrap(True)
        top.addWidget(self.target, 1)
        change = QPushButton("更改…")
        change.clicked.connect(self.change_target.emit)
        reset = QPushButton("恢复自动查找")
        reset.clicked.connect(self.reset_target.emit)
        top.addWidget(change)
        top.addWidget(reset)
        box.addLayout(top)
        actions = QHBoxLayout()
        for text, action in (("导入卡片或卡包…", "import"), ("导出这张卡…", "export_card"), ("导出这个卡包…", "export_pack")):
            button = QPushButton(text)
            button.clicked.connect(lambda _, a=action: self.transfer_requested.emit(a))
            actions.addWidget(button)
        text_button = QPushButton("导出文字")
        text_menu = QMenu(text_button)
        text_menu.addAction("这张卡…", lambda: self.transfer_requested.emit("text_card"))
        text_menu.addAction("这个卡包…", lambda: self.transfer_requested.emit("text_pack"))
        text_button.setMenu(text_menu)
        actions.addWidget(text_button)
        actions.addStretch(1)
        only = QPushButton("只导出 .ypk 文件…")
        only.clicked.connect(lambda: self.export_requested.emit(False))
        self.export_button = QPushButton("导出并装进 MDPro3")
        self.export_button.setStyleSheet("QPushButton{background:#2f7fc4;border:1px solid #23669f;border-radius:3px;"
                                         "color:#ffffff;padding:6px 16px;font-weight:bold;}"
                                         "QPushButton:disabled{background:#9dbfdc;}")
        self.export_button.clicked.connect(lambda: self.export_requested.emit(True))
        actions.addWidget(only)
        actions.addWidget(self.export_button)
        box.addLayout(actions)
        self.results = QListWidget()
        self.results.setMinimumHeight(110)
        box.addWidget(self.results)
        root.addWidget(frame)

    # ------------------------------------------------------------ 显示

    def show_pack(self, title, settings, rows, target_text, code_status=None, setname_conflicts=None):
        """rows：[(卡号, 卡名, 种类, 字段, 效果, 卡面文字, 检查, 是否当前卡, 卡号的问题)]；
        code_status：(说明, 颜色) 卡号核查的结果。"""
        self._loading = True
        try:
            self.pack_name.setText(title)
            self.author.setText(settings.get("author", ""))
            self.ot.setCurrentIndex(max(0, self.ot.findData(settings.get("ot", 3))))
            self.code_start.setValue(int(settings.get("code_start", 100001000)))
            self.code_step.setValue(int(settings.get("code_step", 100)))
            self.setnames.clear()
            for code, name in settings.get("setnames", {}).items():
                clash = (setname_conflicts or {}).get(code)
                item = QListWidgetItem("%s　%s%s" % (code, name, "　× %s" % clash if clash else ""))
                item.setData(Qt.UserRole, code)
                if clash:                                      # 编号和别的卡包的字段撞了
                    item.setForeground(QColor(RED))
                    item.setToolTip(clash)
                self.setnames.addItem(item)
            self.table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                for c, value in enumerate(row[:7]):
                    item = QTableWidgetItem(str(value))
                    if c == 5:
                        item.setForeground(QColor(GREEN if value == "一致" else ORANGE if value == "不同" else GREY))
                    if c == 6:
                        item.setForeground(QColor(RED if str(value).startswith("×") else
                                                  GREEN if str(value).startswith("√") else GREY))
                    if row[7]:
                        item.setBackground(QColor("#eaf2fa"))
                    if c == 0 and len(row) > 8 and row[8]:        # 卡号被占用：标红
                        item.setForeground(QColor(RED))
                        item.setBackground(QColor("#fde7e5"))
                        item.setToolTip(row[8])
                    self.table.setItem(r, c, item)
            self.overview_note.setText("卡包「%s」· %d 张" % (title, len(rows)))
            text, color = code_status or ("", GREY)
            self.code_status.setText(text)
            self.code_status.setStyleSheet("color:%s;%s" % (color, "font-weight:bold;" if color == RED else ""))
            self.target.setText(target_text)
        finally:
            self._loading = False

    def show_results(self, lines, summary=None, ok=True):
        self.results.clear()
        for mark, text in lines:
            item = QListWidgetItem("%s  %s" % (mark, text))
            item.setForeground(QColor({"√": GREEN, "×": RED}.get(mark, ORANGE)))
            self.results.addItem(item)
        if summary:
            item = QListWidgetItem(summary)
            item.setForeground(QColor(GREEN if ok else RED))
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self.results.addItem(item)
        self.results.scrollToBottom()

    def set_busy(self, busy):
        self.export_button.setEnabled(not busy)
        self.export_button.setText("正在导出…" if busy else "导出并装进 MDPro3")

    def _emit_settings(self, *args):
        if self._loading:
            return
        self.settings_changed.emit({"author": self.author.text().strip(), "ot": self.ot.currentData(),
                                    "code_start": self.code_start.value(), "code_step": self.code_step.value()})

    def _add_setname(self):
        name, ok = QInputDialog.getText(self, "新建字段", "字段名（如 星光）")
        if ok and name.strip():
            self.setname_added.emit("", name.strip())

    def _remove_setname(self):
        item = self.setnames.currentItem()
        if item is not None:
            self.setname_removed.emit(item.data(Qt.UserRole))
