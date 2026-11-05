"""输入区下方的三项会话状态；环形占用以原生绘制显示。"""

import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from .usage import hit_rate, number, tooltip


def capacity(value):
    if not value:
        return "未知"
    if value >= 1000000:
        return ("%.2f" % (value / (1000000 if value % 1000 == 0 else 1048576))).rstrip("0").rstrip(".") + "M"
    if value >= 1024:
        return ("%.1f" % (value / (1000 if value % 1000 == 0 else 1024))).rstrip("0").rstrip(".") + "K"
    return str(value)


def turn_stats(record):
    messages = record.get("messages", [])
    turns = sum(message.get("role") == "user" for message in messages)
    steps = sum(message["tool_steps"] if "tool_steps" in message else sum(bool(re.match(r"^[a-z_]+(?:\(| ·)", line)) for line in message.get("events", []))
                for message in messages if message.get("role") == "assistant")
    return turns, steps


class ContextButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ratio, self.color = 0, "#6b94cb"
        self.setFixedWidth(61)
        self.setToolTip("查看上下文占用")

    def set_ratio(self, ratio, known):
        self.ratio = max(0, min(1, ratio))
        self.color = "#cf5656" if ratio > .9 else "#d6a436" if ratio > .7 else "#6b94cb"
        self.setText("    %.0f%%" % (ratio * 100) if known else "    —")
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#dfe5ee"), 2))
        painter.drawEllipse(4, self.height() // 2 - 6, 12, 12)
        painter.setPen(QPen(QColor(self.color), 2))
        painter.drawArc(4, self.height() // 2 - 6, 12, 12, 90 * 16, -int(360 * 16 * self.ratio))


class StatusBar(QWidget):
    stats_requested = pyqtSignal()
    usage_requested = pyqtSignal()
    context_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QToolButton{font-size:11px;padding:4px 2px;color:#65728a;}")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.stats, self.tokens, self.context = QToolButton(), QToolButton(), ContextButton()
        self.texts = {}
        self.cache_suffix = ""
        for button, signal in ((self.stats, self.stats_requested), (self.tokens, self.usage_requested), (self.context, self.context_requested)):
            button.clicked.connect(signal.emit)
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button, 0 if button is self.context else 1)
        self.stats.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.tokens.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_record(self, record, style):
        turns, steps = turn_stats(record)
        speed = (record.get("last_request") or {}).get("output_speed")
        self.texts[self.stats] = "%d轮 %d步 · %s" % (turns, steps, "%.0f词元/秒" % speed if speed is not None else "速度待统计")
        usage = record.get("usage") or {}
        total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        rate = hit_rate(usage)
        self.cache_suffix = " · 缓存" + rate.replace("（已知部分）", "*")
        self.texts[self.tokens] = ("≥" if usage.get("unknown_calls") else "") + number(total, style) + "词元" + self.cache_suffix
        self.stats.setToolTip(self.texts[self.stats] + "\n速度按最近一次输出词元（含思考）÷输出阶段用时计算。点击查看请求详情。")
        self.tokens.setToolTip(tooltip(usage, style) + "\n点击查看词元用量")
        self._fit()

    def _fit(self):
        for button, text in self.texts.items():
            metrics, width = button.fontMetrics(), max(20, button.width() - 4)
            if button is self.tokens and self.cache_suffix:
                prefix = text[:-len(self.cache_suffix)]
                prefix_width = max(0, width - metrics.horizontalAdvance(self.cache_suffix))
                button.setText(metrics.elidedText(prefix, Qt.ElideRight, prefix_width) + self.cache_suffix)
            else:
                button.setText(metrics.elidedText(text, Qt.ElideRight, width))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()


class StatsDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent, Qt.Popup)
        from .appearance import apply_control_fonts, apply_font
        apply_font(self)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("会话与最近一次请求"))
        form = QFormLayout()
        turns, steps = turn_stats(record)
        request = record.get("last_request") or {}
        values = [("会话轮数 / 工具步数", "%d / %d" % (turns, steps)), ("模型", request.get("model", "尚无请求"))]
        for key, title, suffix in (("output_speed", "输出速度（含思考）", "词元/秒"), ("generation_seconds", "输出阶段", "秒"),
                                   ("reasoning_seconds", "其中思考阶段", "秒"), ("elapsed_seconds", "请求总用时", "秒")):
            value = request.get(key)
            values.append((title, "%.1f %s" % (value, suffix) if value is not None else "待统计"))
        for title, value in values:
            form.addRow(title, QLabel(value))
        root.addLayout(form)
        hint = QLabel("速度采用服务返回的输出词元数；用时从首段输出计到本次输出结束，含思考，不含此前等待。")
        hint.setWordWrap(True)
        hint.setMaximumWidth(330)
        root.addWidget(hint)
        apply_control_fonts(self)
