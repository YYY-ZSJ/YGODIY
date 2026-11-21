"""脚本积木中的常量、对局接口和方法查找，沿用脚本页的本地手册。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

from blocks.script.calls import ENGINE_TABLES
from .lua_intel import OBJECT_TYPES, intel


def symbol_field(block, field, value, change):
    if (block, field) not in (("ls_name", "value"), ("ls_method", "name"), ("ls_engine", "api")):
        return None
    constant = block == "ls_name"
    method = block == "ls_method"
    button_text = "查找常量…" if constant else "查找接口…"
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    edit = QLineEdit(value or "")
    edit.textChanged.connect(change)
    row.addWidget(edit, 1)
    button = QPushButton(button_text)
    row.addWidget(button)

    def choose():
        book = intel()
        tables = OBJECT_TYPES if method else ENGINE_TABLES
        pool = book.constants if constant else [e for e in book.functions if e.name.partition(".")[0] in tables]
        dlg = QDialog(box)
        dlg.setWindowTitle(button_text.rstrip("…"))
        dlg.resize(580, 390)
        layout = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("输入中文含义或 Lua 名称")
        listing = QListWidget()
        detail = QLabel()
        detail.setWordWrap(True)
        detail.setTextFormat(Qt.PlainText)
        actions = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        for w in (search, listing, detail, actions):
            layout.addWidget(w)

        def refresh(query):
            listing.clear()
            for entry in book.search(query, pool):
                it = QListWidgetItem(entry.name + ("  " + entry.doc.splitlines()[0] if entry.doc else ""))
                it.setData(Qt.UserRole, entry.name)
                listing.addItem(it)
            listing.setCurrentRow(0)
            actions.button(QDialogButtonBox.Ok).setEnabled(listing.count() > 0)

        def show(it, _old):
            entry = book.by_name.get(it.data(Qt.UserRole)) if it else None
            detail.setText(entry.detail + "\n" + entry.doc if entry else "")

        listing.currentItemChanged.connect(show)
        search.textChanged.connect(refresh)
        listing.itemDoubleClicked.connect(lambda *_: dlg.accept())
        actions.accepted.connect(dlg.accept)
        actions.rejected.connect(dlg.reject)
        refresh("")
        if dlg.exec_() == QDialog.Accepted and listing.currentItem():
            name = listing.currentItem().data(Qt.UserRole)
            edit.setText(name.split(".")[-1] if method else name)

    button.clicked.connect(choose)
    return box
