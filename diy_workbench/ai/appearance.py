"""AI 区域的字体；不修改应用或其他模式的字体。"""

import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget


def apply_font(widget):
    families = QFontDatabase().families()
    if "Microsoft YaHei" not in families:
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/msyh.ttc"
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase().families()
    family = next((f for f in ("Microsoft YaHei", "微软雅黑", "Noto Sans CJK SC", "Segoe UI") if f in families), "sans-serif")
    font = QFont(family, 10)
    widget.setFont(font)
    return font


def action_icon(name):
    pixmap = QPixmap(22, 22)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#526681"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if name == "new":
        painter.drawRoundedRect(3, 3, 16, 14, 4, 4)
        painter.drawLine(6, 17, 6, 20)
        painter.drawLine(6, 20, 10, 17)
        painter.drawLine(11, 7, 11, 13)
        painter.drawLine(8, 10, 14, 10)
    elif name == "history":
        painter.drawEllipse(3, 3, 16, 16)
        painter.drawLine(11, 6, 11, 11)
        painter.drawLine(11, 11, 15, 13)
    elif name == "settings":
        painter.drawEllipse(5, 5, 12, 12)
        painter.drawEllipse(8, 8, 6, 6)
        painter.translate(11, 11)
        for _ in range(8):
            painter.drawLine(0, -7, 0, -9)
            painter.rotate(45)
    painter.end()
    return QIcon(pixmap)


def apply_control_fonts(widget):
    """宿主为新控件指定卡面字体，AI 子控件需显式指定，代码区保留等宽字体。"""
    font = widget.font()
    for child in widget.findChildren(QWidget):
        parent = child
        while parent is not None and parent is not widget and parent.objectName() != "ai_code_text":
            parent = parent.parentWidget()
        if parent is not None and parent.objectName() == "ai_code_text":
            continue
        child.setFont(font)
