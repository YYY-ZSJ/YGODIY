"""只为可见区及上下缓冲区创建气泡；消息原文与高度缓存独立保存。"""

from bisect import bisect_right
import math

from PyQt5.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget


def _view_messages(messages):
    result, cache_notice = [], False
    for message in messages:
        events = []
        for event in message.get("events", []):
            if event == message.get("note"):
                continue
            if event.startswith("DeepSeek：缓存构建"):
                if cache_notice:
                    continue
                cache_notice = True
            events.append(event)
        result.append(dict(message, events=tuple(events), reasoning_parts=[dict(part) for part in message.get("reasoning_parts", [])]))
    return result


class ChatView(QScrollArea):
    retry_requested = pyqtSignal(str)
    change_apply_requested = pyqtSignal(str)
    change_reject_requested = pyqtSignal(str)
    change_undo_requested = pyqtSignal(str)
    target_requested = pyqtSignal(str, str)
    tests_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.root = QVBoxLayout(self.container)
        self.root.setContentsMargins(4, 8, 8, 4)
        self.root.setSpacing(0)
        self.top_gap, self.bottom_gap = QWidget(), QWidget()
        self.top_gap.setFixedHeight(0)
        self.bottom_gap.setFixedHeight(0)
        self.root.addWidget(self.top_gap)
        self.root.addWidget(self.bottom_gap)
        self.root.addStretch(1)
        self.setWidget(self.container)
        self.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical{background:#f0f3f8;width:9px;margin:0;}"
            "QScrollBar::handle:vertical{background:#c0cada;border-radius:4px;min-height:28px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
            "QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}")
        self.rows, self.messages, self.heights, self.expanded = {}, [], {}, {}
        self.offsets, self.indices = [0], {}
        self._follow, self._moving, self._updating = True, False, False
        self._width = 0
        self.number_style = "grouped"
        self.busy = False
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self._refresh)
        self.verticalScrollBar().valueChanged.connect(self._scrolled)
        self.verticalScrollBar().rangeChanged.connect(self._range_changed)

    def _schedule(self, delay=16):
        if not self.refresh_timer.isActive():
            self.refresh_timer.start(delay)

    def _scrolled(self, value):
        if not self._moving:
            self._follow = value >= self.verticalScrollBar().maximum() - 20
            self._schedule()

    def _range_changed(self, *_):
        if self._follow:
            QTimer.singleShot(0, self.scroll_to_bottom)

    def scroll_to_bottom(self):
        if self._follow:
            self._moving = True
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
            self._moving = False

    def _estimate(self, message):
        columns = max(12, int(self.viewport().width() * 0.85 / 12))
        lines = sum(max(1, math.ceil(len(s) / columns)) for s in message.get("text", "").splitlines())
        return max(64, 64 + lines * 20 + (32 if message.get("events") else 0))

    def _index_heights(self):
        self.offsets = [0]
        for message in self.messages:
            height = self.heights.get(message["id"])
            if height is None:
                height = self.heights[message["id"]] = self._estimate(message)
            self.offsets.append(self.offsets[-1] + height)

    def _anchor(self):
        if not self.messages:
            return None
        value = self.verticalScrollBar().value()
        index = min(len(self.messages) - 1, max(0, bisect_right(self.offsets, value) - 1))
        return self.messages[index]["id"], value - self.offsets[index]

    def _remove(self, key):
        row = self.rows.pop(key)
        self.expanded[key] = (row.events_button.isChecked(), row.reasoning.button.isChecked() if row.reasoning is not None else False)
        self.root.removeWidget(row)
        row.hide()
        row.deleteLater()

    def _window(self):
        height = max(200, self.viewport().height())
        value = max(0, self.offsets[-1] - height) if self._follow else self.verticalScrollBar().value()
        start = max(0, bisect_right(self.offsets, max(0, value - height)) - 1)
        end = min(len(self.messages), bisect_right(self.offsets, value + 2 * height))
        return start, end

    def _refresh(self):
        if self._updating:
            return
        from .message_view import MessageRow
        self._updating = True
        anchor = self._anchor()
        try:
            start, end = self._window()
            wanted = {m["id"] for m in self.messages[start:end]}
            for key in list(self.rows):
                if key not in wanted:
                    self._remove(key)
            for index, entry in enumerate(self.messages[start:end], 1):
                key = entry["id"]
                if key not in self.rows:
                    row = self.rows[key] = MessageRow(entry, self.container)
                    for name in ("retry_requested", "change_apply_requested", "change_reject_requested", "change_undo_requested", "target_requested", "tests_requested"):
                        if hasattr(row, name):
                            getattr(row, name).connect(getattr(self, name).emit)
                    events_open, reasoning_open = self.expanded.get(key, (False, False))
                    row.events_button.setChecked(events_open)
                    if row.reasoning is not None:
                        row.reasoning.button.setChecked(reasoning_open)
                    row.installEventFilter(self)
                    self.root.insertWidget(index, row)
                else:
                    row = self.rows[key]
                    row.update_entry(entry)
                from .usage import tooltip
                row.usage_text = tooltip(entry["usage"], self.number_style) if entry.get("usage") else ""
                row.retry_button.setEnabled(not self.busy)
                if row.changes is not None:
                    row.changes.set_busy(self.busy)
                row.setFixedWidth(max(80, self.viewport().width() - 12))
                row.layout().activate()
                row.group.layout().activate()
                row.bubble.layout().activate()
                height = max(48, row.sizeHint().height(), row.minimumSizeHint().height())
                if row.height() != height:
                    row.setFixedHeight(height)
                self.heights[key] = height
            self._index_heights()
            self.top_gap.setFixedHeight(self.offsets[start])
            self.bottom_gap.setFixedHeight(self.offsets[-1] - self.offsets[end])
            self.root.activate()
            if anchor and not self._follow and anchor[0] in self.indices:
                self._moving = True
                self.verticalScrollBar().setValue(self.offsets[self.indices[anchor[0]]] + anchor[1])
                self._moving = False
            self.scroll_to_bottom()
        finally:
            self._updating = False

    def eventFilter(self, watched, event):
        if event.type() == QEvent.LayoutRequest and not self._updating:
            self._schedule()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._width != self.viewport().width():
            self._width = self.viewport().width()
            self.heights.clear()
            self._index_heights()
            self._schedule()

    def show_messages(self, messages):
        # 绘制只使用本次合并刷新的视图值，布局事件不能偷读尚未刷新的一小段流式文字。
        self.messages = _view_messages(messages)
        self.indices = {m["id"]: i for i, m in enumerate(self.messages)}
        self._index_heights()
        self._refresh()

    def reset(self):
        for key in list(self.rows):
            self._remove(key)
        self.messages, self.indices, self.heights, self.expanded = [], {}, {}, {}
        self.offsets, self._follow = [0], True
        self.top_gap.setFixedHeight(0)
        self.bottom_gap.setFixedHeight(0)

    def toPlainText(self):
        return "\n\n".join(m.get("text", "") for m in self.messages)
