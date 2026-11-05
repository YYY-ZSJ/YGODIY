"""上下文浮层：来源分段、用量明细和压缩入口。"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .appearance import apply_control_fonts, apply_font
from .status_view import capacity
from .usage import number

PARTS = (("system", "系统提示词", "#729de1"), ("tools", "工具定义", "#9e88d1"), ("messages", "对话消息（含摘要）", "#63aa99"))


class ContextSegments(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parts, self.maximum = {}, 0
        self.setFixedHeight(9)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#e6ebf2"))
        maximum = self.maximum or max(1, self.parts.get("total", 0))
        position = 0
        for key, label, color in PARTS:
            width = self.width() * self.parts.get(key, 0) / maximum
            painter.fillRect(int(position), 0, int(width + 1), self.height(), QColor(color))
            position += width


class ContextDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        apply_font(self)
        self.setFixedWidth(370)
        root = QVBoxLayout(self)
        self.title = QLabel("上下文占用")
        self.title.setStyleSheet("font-size:17px;font-weight:600;padding:5px;")
        root.addWidget(self.title)
        self.bar = ContextSegments()
        root.addWidget(self.bar)
        form = QFormLayout()
        self.values = {}
        for key, label, color in PARTS:
            name = QLabel("● " + label)
            name.setStyleSheet("color:%s;" % color)
            self.values[key] = QLabel()
            form.addRow(name, self.values[key])
        root.addLayout(form)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        row = QHBoxLayout()
        self.originals = QPushButton("摘要 / 原文")
        self.compress = QPushButton("压缩对话")
        row.addWidget(self.originals)
        row.addWidget(self.compress)
        root.addLayout(row)
        apply_control_fonts(self)

    def set_data(self, count, limits, parts, busy=False, has_summary=False):
        self.title.setText("上下文 约%s / %s" % (number(count), capacity(limits.get("context_window"))))
        self.bar.parts, self.bar.maximum = parts, limits.get("context_window", 0)
        self.bar.update()
        for key, _, _ in PARTS:
            self.values[key].setText("约 " + number(parts.get(key, 0)) + " 词元")
        self.notice.setText("容量来源：" + limits.get("source", "未知") + "\n统计含当前输入与附件；缓存命中不减少上下文占用。")
        self.compress.setEnabled(not busy)
        self.originals.setEnabled(has_summary)


def position_popup(dialog, anchor, fit=True):
    if fit:
        dialog.adjustSize()
    point = anchor.mapToGlobal(anchor.rect().topLeft())
    screen = anchor.screen().availableGeometry()
    x = min(max(screen.left(), point.x()), max(screen.left(), screen.right() - dialog.width()))
    y = max(screen.top(), point.y() - dialog.height() - 6)
    dialog.move(x, y)
