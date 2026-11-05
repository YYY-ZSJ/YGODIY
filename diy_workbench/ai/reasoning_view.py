"""服务返回思考内容的折叠显示。使用有界纯文本视口，不参与协议历史生成。"""

import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QFrame, QPlainTextEdit, QToolButton, QVBoxLayout

MAX_HEIGHT = 180
MIN_HEIGHT = 44


class ReasoningBlock(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame{background:#f0f3f7;border-radius:7px;}"
                          "QToolButton{font-size:11px;color:#6b7687;padding:5px;border:0;text-align:left;}"
                          "QPlainTextEdit{font-size:11px;color:#738092;background:transparent;border:0;padding:4px;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 3, 4, 4)
        root.setSpacing(1)
        self.button = QToolButton()
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.RightArrow)
        self.button.toggled.connect(self._toggle)
        root.addWidget(self.button)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text.setMinimumWidth(0)
        self.text.hide()
        root.addWidget(self.text)
        self.value = ""

    def _toggle(self, shown):
        self.text.setVisible(shown)
        self.button.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)

    def set_parts(self, parts):
        active = any(part.get("active") for part in parts)
        seconds = sum(part.get("seconds") or 0 for part in parts)
        known = all(part.get("seconds") is not None for part in parts)
        title = "思考过程 · 用时 %.1f 秒" % seconds if known else "思考过程 · 用时未记录"
        self.button.setText("思考中…" if active else title)
        self.button.setToolTip("服务返回的思考内容；用时为客户端收到思考至该阶段结束的累计时间。")
        value = "\n\n".join(("压缩对话：\n" if part.get("purpose") == "compression" else "") + part.get("text", "") for part in parts)
        if value != self.value:
            bar = self.text.verticalScrollBar()
            follow, old_scroll = bar.value() >= bar.maximum() - 6, bar.value()
            if value.startswith(self.value):
                cursor = QTextCursor(self.text.document())
                cursor.movePosition(QTextCursor.End)
                cursor.insertText(value[len(self.value):])
            else:
                self.text.setPlainText(value)
            self.value = value
            columns = max(12, self.width() // max(1, self.fontMetrics().averageCharWidth()))
            lines = max(1, sum(math.ceil(max(1, len(line)) / columns) for line in value.splitlines()))
            self.text.setFixedHeight(min(MAX_HEIGHT, max(MIN_HEIGHT, lines * self.fontMetrics().lineSpacing() + 10)))
            bar.setValue(bar.maximum() if follow else old_scroll)
