"""模型名完整显示；过长时在按钮内换行，避免把停靠面板撑宽。"""

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QLabel, QSizePolicy, QToolButton, QVBoxLayout


class ModelButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value, self._width = "", 0
        self.label = QLabel()
        self.label.setTextFormat(Qt.PlainText)
        self.label.setWordWrap(True)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setText(self, text):
        if self.value != text:
            self.value = text
            self.setAccessibleName(text)
            # 仅显示文本加入换行机会；原始模型名和API参数保持原样。
            self.label.setText("\u200b".join(text))
            self._fit()

    def text(self):
        return self.value

    def sizeHint(self):
        return QSize(170, 30)

    def minimumSizeHint(self):
        return QSize(60, 30)

    def _fit(self):
        self.setFixedHeight(max(30, self.label.heightForWidth(max(20, self.width() - 10)) + 6))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._width != self.width():
            self._width = self.width()
            self._fit()
