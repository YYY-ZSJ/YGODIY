"""工作台的「已安装」页：看 MDPro3 扩展目录里的卡包，卸载 YGODIY 导出的那些；卸载的进回收站。"""

import os
import time

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

COLUMNS = ("文件", "卡包", "卡数", "大小", "安装时间", "状态")
BIN_COLUMNS = ("文件", "卡包", "卡数", "卸载时间")


class InstalledPage(QWidget):
    refresh_requested = pyqtSignal()
    open_requested = pyqtSignal()
    import_requested = pyqtSignal(str)
    uninstall_requested = pyqtSignal(str)
    restore_requested = pyqtSignal(str)
    purge_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.target = QLabel()
        self.target.setWordWrap(True)
        root.addWidget(self.target)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        root.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.status = QLabel()
        actions.addWidget(self.status, 1)
        for text, handler in (("刷新", self.refresh_requested.emit), ("打开目录", self.open_requested.emit),
                              ("导入到工作台", self._import), ("卸载", self._uninstall)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            actions.addWidget(button)
        root.addLayout(actions)
        self.rows = []
        self.notice = ""
        root.addWidget(QLabel("回收站"))
        self.bin_table = QTableWidget(0, len(BIN_COLUMNS))
        self.bin_table.setHorizontalHeaderLabels(BIN_COLUMNS)
        self.bin_table.verticalHeader().setVisible(False)
        self.bin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.bin_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.bin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.bin_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.bin_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.bin_table.setMaximumHeight(170)
        root.addWidget(self.bin_table)
        bin_actions = QHBoxLayout()
        bin_actions.addStretch(1)
        for text, signal in (("恢复", self.restore_requested), ("彻底删除", self.purge_requested)):
            button = QPushButton(text)
            button.clicked.connect(lambda _, s=signal: self._bin_action(s))
            bin_actions.addWidget(button)
        root.addLayout(bin_actions)
        self.bin_rows = []

    def show_packs(self, target, rows):
        self.target.setText("扩展目录：%s" % (target or "没有找到 MDPro3"))
        self.rows = rows
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            state = "未通过验证" if row["unverified"] else "YGODIY 导出" if row["ours"] else "其他来源"
            values = (row["file"], row["title"], str(row["cards"]), "%.1f MB" % (row["size"] / 1048576),
                      time.strftime("%Y-%m-%d %H:%M", time.localtime(row["time"])), state)
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        self.status.setText(self.notice or "共 %d 个卡包" % len(rows))
        self.notice = ""

    def show_bin(self, rows):
        self.bin_rows = rows
        self.bin_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["file"], row["title"], str(row["cards"]), time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.dirname(row["path"])))))
            for column, value in enumerate(values):
                self.bin_table.setItem(index, column, QTableWidgetItem(value))

    def _bin_action(self, signal):
        index = self.bin_table.currentRow()
        if 0 <= index < len(self.bin_rows):
            signal.emit(self.bin_rows[index]["path"])
        else:
            self.status.setText("先在回收站里选中一个卡包。")

    def selected(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.rows):
            return self.rows[index]
        self.status.setText("先选中一个卡包。")
        return None

    def _import(self):
        row = self.selected()
        if row:
            self.import_requested.emit(row["path"])

    def _uninstall(self):
        row = self.selected()
        if row:
            self.uninstall_requested.emit(row["path"])
