"""独立会话列表；搜索、导出与加载均经后台文件队列。"""

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5 import sip
from PyQt5.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout)

from .appearance import apply_control_fonts, apply_font
from .session_store import snapshot
from .usage import money, number, tooltip


class SessionDialog(QDialog):
    delete_requested = pyqtSignal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        apply_font(self)
        self.store, self.search_generation = store, 0
        self.finished.connect(self._finished)
        self.setWindowTitle("AI 会话")
        self.resize(580, 520)
        root = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索会话标题或正文")
        root.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda *_: self._open())
        root.addWidget(self.list)
        bar = QHBoxLayout()
        for title, callback in (("新对话", self._new), ("打开", self._open), ("改名", self._rename),
                                ("置顶 / 取消", self._pin), ("导出 Markdown", self._export), ("删除", self._delete)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            bar.addWidget(button)
        root.addLayout(bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(200)
        self.search_timer.timeout.connect(self._search)
        self.search.textChanged.connect(lambda *_: self.search_timer.start())
        store.listed.connect(self._listed)
        self._listed(list(store.index.values()))
        apply_control_fonts(self)

    def _selected(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _listed(self, items):
        if self.search.text().strip():
            self.search_timer.start()
        else:
            self._populate(items)

    def _populate(self, items):
        selected = self._selected() or self.store.current_id
        self.list.clear()
        for entry in sorted(items, key=lambda m: (bool(m.get("pinned")), m.get("updated") or ""), reverse=True):
            usage = entry.get("usage") or {}
            total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            style = getattr(self.store, "number_style", "grouped")
            label = ("≥" if usage.get("unknown_calls") else "") + number(total, style) + " 词元"
            if usage.get("costs"):
                label += " · " + money(usage["costs"])
            item = QListWidgetItem(("★ " if entry.get("pinned") else "") + entry.get("title", "新对话") + "\n" + label)
            item.setToolTip(tooltip(usage, style))
            item.setData(Qt.UserRole, entry["id"])
            self.list.addItem(item)
            if entry["id"] == selected:
                self.list.setCurrentItem(item)

    def _search(self):
        self.search_generation += 1
        generation = self.search_generation
        def done(items, error):
            if generation != self.search_generation or sip.isdeleted(self) or not self.isVisible():
                return
            self.status.setText(error)
            self._populate(items or [])
        self.store.search(self.search.text().strip(), done)

    def _finished(self, *_):
        self.search_generation += 1
        self.search_timer.stop()
        self.store.listed.disconnect(self._listed)

    def _new(self):
        self.store.create()
        self.accept()

    def _open(self):
        uid = self._selected()
        if uid:
            self.store.open(uid)
            self.accept()

    def _rename(self):
        uid = self._selected()
        if uid:
            title, ok = QInputDialog.getText(self, "会话改名", "标题", text=self.store.index[uid].get("title", ""))
            if ok and title.strip():
                self.store.edit_metadata(uid, title=title.strip()[:160])

    def _pin(self):
        uid = self._selected()
        if uid:
            self.store.edit_metadata(uid, pinned=not self.store.index[uid].get("pinned"))

    def _delete(self):
        uid = self._selected()
        if uid and QMessageBox.question(self, "删除会话", "删除这份会话和本地原文？卡片和修改批次仍保留。",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self.delete_requested.emit(uid)

    def _export(self):
        uid = self._selected()
        if not uid:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出会话", "对话.md", "Markdown (*.md)", options=QFileDialog.DontConfirmOverwrite)
        if not path:
            return
        record = snapshot(self.store.records[uid]) if uid in self.store.records else None
        def done(result, error):
            if sip.isdeleted(self) or not self.isVisible():
                return
            if result == "exists":
                if QMessageBox.question(self, "覆盖文件", "目标文件已存在，是否覆盖？", QMessageBox.Yes | QMessageBox.No,
                                        QMessageBox.No) == QMessageBox.Yes:
                    self.store.io.submit(self.store.disk.export, uid, path, True, record, callback=done)
            else:
                self.status.setText(error or "会话已导出为 Markdown。")
        self.store.io.submit(self.store.disk.export, uid, path, False, record, callback=done)
