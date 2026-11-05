"""按选中的摘要或消息展开原文，长会话不一次创建全部正文控件。"""

from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QLabel, QListView,
                             QPlainTextEdit, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from .appearance import apply_control_fonts, apply_font


class MessageIndex(QAbstractListModel):
    def __init__(self, messages, parent):
        super().__init__(parent)
        self.messages = messages

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.messages)

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and index.isValid():
            message = self.messages[index.row()]
            name = "玩家" if message.get("role") == "user" else "AI"
            return "%d · %s · %s" % (index.row() + 1, name, message.get("text", "")[:48].replace("\n", " "))


class TranscriptDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        apply_font(self)
        self.setWindowTitle("摘要与完整原文")
        self.resize(740, 580)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)
        summary_page = QWidget()
        summary_layout = QVBoxLayout(summary_page)
        versions = QComboBox()
        summaries = record.get("summaries", [])
        versions.addItems(["摘要版本 %d" % (i + 1) for i in range(len(summaries))])
        summary_layout.addWidget(versions)
        summary = QPlainTextEdit()
        summary.setReadOnly(True)
        summary_layout.addWidget(summary)
        versions.currentIndexChanged.connect(lambda i: summary.setPlainText(summaries[i]["text"]) if i >= 0 else None)
        if summaries:
            versions.setCurrentIndex(len(summaries) - 1)
            summary.setPlainText(summaries[-1]["text"])
        tabs.addTab(summary_page, "摘要")
        originals = QWidget()
        original_layout = QVBoxLayout(originals)
        original_layout.addWidget(QLabel("选择一条消息展开完整原文；压缩不会删除这里的记录。"))
        split = QSplitter()
        index = QListView()
        messages = list(record.get("messages", []))
        index.setModel(MessageIndex(messages, index))
        split.addWidget(index)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        split.addWidget(text)
        split.setStretchFactor(1, 2)
        original_layout.addWidget(split)
        index.selectionModel().currentChanged.connect(lambda current, previous:
            text.setPlainText(messages[current.row()].get("text", "")) if current.isValid() else None)
        tabs.addTab(originals, "完整原文")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_control_fonts(self)
