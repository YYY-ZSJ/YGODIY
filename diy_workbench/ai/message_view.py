"""原生 Qt 气泡和 Markdown：文本交给 QTextDocument，围栏代码单独提供复制。"""

import math
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextOption
from PyQt5.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton,
    QLayout, QSizePolicy, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from .appearance import apply_control_fonts, apply_font
from .change_view import ChangeCard

FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")


def markdown_parts(text):
    result, buffer, fence, language = [], [], None, ""
    for line in text.splitlines(keepends=True):
        match = FENCE.match(line.rstrip("\r\n"))
        if fence is None and match:
            if buffer:
                result.append(("text", "", "".join(buffer)))
            buffer, fence, language = [], match[1], match[2].strip()
        elif fence is not None and match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
            result.append(("code", language, "".join(buffer)))
            buffer, fence = [], None
        else:
            buffer.append(line)
    if buffer or fence is not None:
        result.append(("code" if fence else "text", language if fence else "", "".join(buffer)))
    return result or [("text", "", "")]


MAX_EVENTS_HEIGHT = 320


class MarkdownText(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.NoContextMenu)       # 右键交给整条消息的菜单
        self.document().setDefaultFont(apply_font(self))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_link)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setStyleSheet("background:transparent;border:0;padding:0;")
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet("p{margin:5px 0;}h1,h2,h3{margin:6px 0;}code{font-family:Consolas;background:#eef1f6;}")
        self.document().documentLayout().documentSizeChanged.connect(self._fit)

    def loadResource(self, kind, url):
        if kind == QTextDocument.ImageResource:
            return None
        return super().loadResource(kind, url)

    def _open_link(self, url):
        if url.scheme() in ("https", "http"):
            QDesktopServices.openUrl(url)

    def set_text(self, text):
        flags = QTextDocument.MarkdownFeatures(QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML)
        self.document().setMarkdown(text, flags)
        block = self.document().begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if level:
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.BlockUnderCursor)
                style = QTextCharFormat(cursor.charFormat())
                style.clearProperty(QTextFormat.FontSizeAdjustment)
                style.clearProperty(QTextFormat.FontPixelSize)
                style.setFontPointSize(self.font().pointSizeF() + (2 * 72 / self.logicalDpiY() if level == 1 else 0))
                style.setFontWeight(QFont.Bold)
                cursor.setCharFormat(style)
            block = block.next()
        self._fit()

    def append_plain(self, text, previous=""):
        if text.startswith(previous):
            cursor = QTextCursor(self.document())
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(text[len(previous):])
        else:
            self.setPlainText(text)
        self._fit()

    def _fit(self, *_):
        height = max(20, math.ceil(self.document().size().height()) + 6)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = max(40, self.viewport().width())
        if self.document().textWidth() != width:
            self.document().setTextWidth(width)
        self._fit()


class CodeBlock(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ai_code")
        self.setStyleSheet("QFrame#ai_code{background:#f1f4f8;border:1px solid #e0e6ef;border-radius:8px;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 7, 10, 9)
        bar = QHBoxLayout()
        self.language = QLabel()
        self.language.setStyleSheet("color:#687589;font-size:11px;")
        bar.addWidget(self.language, 1)
        self.copy_button = QPushButton("复制")
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.setStyleSheet("border:0;color:#49678e;background:transparent;padding:3px 7px;")
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.code.toPlainText()))
        bar.addWidget(self.copy_button)
        root.addLayout(bar)
        self.code = QPlainTextEdit()
        self.code.setObjectName("ai_code_text")
        self.code.setReadOnly(True)
        font = QFont("Consolas", 10)
        font.setFamilies(["Consolas", "Microsoft YaHei"])
        font.setStyleHint(QFont.Monospace)
        self.code.setFont(font)
        self.code.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.code.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.code.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.code.setStyleSheet("background:transparent;border:0;padding:0;color:#28354a;"
                               "font-family:Consolas,'Microsoft YaHei';font-style:normal;font-weight:normal;")
        self.code.document().setDocumentMargin(0)
        self.code.document().documentLayout().documentSizeChanged.connect(self._fit_code)
        self.code.horizontalScrollBar().rangeChanged.connect(self._fit_code)
        root.addWidget(self.code)

    def set_text(self, text, language=""):
        self.language.setText(language or "代码")
        self.code.setPlainText(text.rstrip("\n"))
        self.code.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._fit_code()

    def _fit_code(self, *_):
        document = self.code.document()
        block, height = document.begin(), 0
        while block.isValid():
            height += document.documentLayout().blockBoundingRect(block).height()
            block = block.next()
        if self.code.horizontalScrollBar().maximum() > 0:
            height += self.code.horizontalScrollBar().sizeHint().height()
        height = math.ceil(height) + 8
        if self.code.height() != height:
            self.code.setFixedHeight(height)


class MarkdownBody(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(8)
        self.parts, self.views = [], []
        self.streaming_text = None

    def _clear(self):
        while self.root.count():
            old = self.root.takeAt(0).widget()
            old.hide()
            old.deleteLater()
        self.parts, self.views = [], []

    def set_streaming(self, text):
        if self.streaming_text is None:
            self._clear()
            view = MarkdownText(self)
            self.root.addWidget(view)
            self.views = [view]
            self.streaming_text = ""
        self.views[0].append_plain(text, self.streaming_text)
        self.streaming_text = text

    def set_text(self, text):
        if self.streaming_text is not None:
            self._clear()
            self.streaming_text = None
        parts = markdown_parts(text)
        if [p[0] for p in parts] != [p[0] for p in self.parts]:
            self._clear()
            for kind, _, _ in parts:
                view = CodeBlock(self) if kind == "code" else MarkdownText(self)
                self.root.addWidget(view)
                self.views.append(view)
            self.parts = []
        for view, part, previous in zip(self.views, parts, self.parts + [None] * len(parts)):
            if part != previous:
                if part[0] == "code":
                    view.set_text(part[2], part[1])
                else:
                    view.set_text(part[2])
        self.parts = parts


class MessageRow(QWidget):
    retry_requested = pyqtSignal(str)
    change_apply_requested = pyqtSignal(str)
    change_reject_requested = pyqtSignal(str)
    change_undo_requested = pyqtSignal(str)
    target_requested = pyqtSignal(str, str)
    tests_requested = pyqtSignal(str)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        apply_font(self)
        self.message_id = entry["id"]
        self.signature = None
        self.change_signature = None
        self.usage_text, self.text = "", ""
        player = self.player = entry.get("role") == "user"
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 3, 0, 9)
        root.setSizeConstraint(QLayout.SetMinimumSize)
        if player:
            root.addStretch(1)
        group = self.group = QWidget()
        body = self.body_layout = QVBoxLayout(group)
        self.reasoning = None
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(5)
        label = "你" if player else "伊格尼斯"
        role = QLabel(label + (" · " + entry["mode_label"] if entry.get("mode_label") else ""))
        role.setAlignment(Qt.AlignRight if player else Qt.AlignLeft)
        role.setStyleSheet("color:#758296;font-size:11px;padding:0 4px;")
        body.addWidget(role)
        self.bubble = QFrame()
        self.bubble.setObjectName("ai_bubble")
        color, border = ("#e9f1ff", "#dbe7fb") if player else ("#ffffff", "#e5eaf2")
        self.bubble.setStyleSheet("QFrame#ai_bubble{background:%s;border:1px solid %s;border-radius:12px;}" % (color, border))
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(13, 10, 13, 10)
        self.content = QLabel() if player else MarkdownBody()
        if player:
            self.content.setWordWrap(True)
            self.content.setTextFormat(Qt.PlainText)
            self.content.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self.content.setContextMenuPolicy(Qt.NoContextMenu)
        bubble_layout.addWidget(self.content)
        body.addWidget(self.bubble)
        self.events_button = QToolButton()
        self.events_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.events_button.setCheckable(True)
        self.events_button.setArrowType(Qt.RightArrow)
        self.events_button.setStyleSheet("color:#45566e;border:0;padding:3px;background:transparent;")
        self.events, self.event_text, self.body = None, "", body     # 展开时才创建，大多数消息用不到
        self.events_button.toggled.connect(self._expand)
        body.addWidget(self.events_button)
        self.changes = None
        self.change_slot = QVBoxLayout()
        self.change_slot.setContentsMargins(0, 0, 0, 0)
        body.addLayout(self.change_slot)
        self.test_reports = None
        self.test_slot = QVBoxLayout()
        self.test_slot.setContentsMargins(0, 0, 0, 0)
        body.addLayout(self.test_slot)
        note_row = QHBoxLayout()
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setAlignment(Qt.AlignCenter)
        note_row.addWidget(self.note, 1)
        self.retry_button = QPushButton("重试")
        self.retry_button.clicked.connect(lambda: self.retry_requested.emit(self.message_id))
        note_row.addWidget(self.retry_button)
        body.addLayout(note_row)
        root.addWidget(group)
        if not player:
            root.addStretch(1)
        self.update_entry(entry)
        apply_control_fonts(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = self.width()
        limit = max(80, int(available * 0.85))
        width = limit
        if self.player:
            text = self.content.text()
            width = min(limit, max(85, max((self.fontMetrics().horizontalAdvance(s) for s in text.splitlines()), default=0) + 30))
        if self.group.width() != width:
            self.group.setFixedWidth(width)
            self._fit_events()

    def _create_events(self):
        self.events = QPlainTextEdit()      # 工具参数是不换行的长 JSON，QLabel 算不准高度，会留下大片空白
        self.events.setReadOnly(True)
        self.events.setContextMenuPolicy(Qt.NoContextMenu)
        self.events.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.events.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.events.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.events.setStyleSheet("background:#edf1f7;color:#45566e;border:0;border-radius:7px;padding:4px;")
        self.events.setPlainText(self.event_text)
        self.body.insertWidget(self.body.indexOf(self.events_button) + 1, self.events)

    def _fit_events(self):
        if self.events is None or self.events.isHidden():
            return
        document = QTextDocument()
        document.setDefaultFont(self.events.font())
        document.setDocumentMargin(self.events.document().documentMargin())
        option = document.defaultTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(option)
        document.setPlainText(self.events.toPlainText())
        document.setTextWidth(max(40, self.group.width() - 24))
        self.events.setFixedHeight(min(MAX_EVENTS_HEIGHT, int(document.size().height()) + 16))

    def _expand(self, shown):
        if shown and self.events is None:
            self._create_events()
        if self.events is not None:
            self.events.setVisible(shown)
        self.events_button.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)
        self._fit_events()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("复制这条消息", lambda: QApplication.clipboard().setText(self.text))
        if self.usage_text:
            menu.addSeparator()
            for line in self.usage_text.splitlines():
                menu.addAction(line).setEnabled(False)
            menu.addAction("复制用量", lambda: QApplication.clipboard().setText(self.usage_text))
        menu.exec_(event.globalPos())

    def update_entry(self, entry):
        parts = entry.get("reasoning_parts", [])
        signature = (entry.get("text", ""), entry.get("status"), entry.get("note", ""), tuple(entry.get("events", [])),
                     entry.get("changes"), tuple((p.get("text"), p.get("seconds"), p.get("active")) for p in parts),
                     entry.get("test_reports"), entry.get("verification"))
        if signature == self.signature:
            return
        old = self.signature
        self.signature = signature
        text, status, note, events, _ = signature[:5]
        self.text = text
        if parts and not self.player:
            if self.reasoning is None:
                from .reasoning_view import ReasoningBlock
                self.reasoning = ReasoningBlock(self.group)
                self.body_layout.insertWidget(1, self.reasoning)
                apply_control_fonts(self.reasoning)
            self.reasoning.set_parts(parts)
        if isinstance(self.content, MarkdownBody):
            if status == "streaming":
                self.content.set_streaming(text)
            elif old is None or (text, status) != old[:2]:
                self.content.set_text(text)
        else:
            self.content.setText(text)
        self.bubble.setVisible(bool(text) or (status == "streaming" and not parts))
        self.note.setText(note)
        self.note.setVisible(bool(note))
        self.note.setStyleSheet("color:%s;font-size:11px;padding:5px;" % ("#b65353" if status == "failed" else "#8b96a5"))
        self.retry_button.setText("继续" if status == "paused" else "重试")
        self.retry_button.setVisible(status in ("failed", "interrupted", "cancelled", "paused"))
        self.events_button.setVisible(bool(events))
        requests = sum(event.startswith("请求 ") for event in events)
        steps = entry.get("tool_steps")
        self.events_button.setText("调用过程 · %d 次工具 · %d 次请求" % (steps, requests) if steps is not None else "调用过程 · %d 条" % len(events))
        if self.event_text != "\n".join(events):
            self.event_text = "\n".join(events)
            if self.events is not None:
                self.events.setPlainText(self.event_text)
                self._fit_events()
        reports, evidence = entry.get("test_reports", []), entry.get("verification")
        if reports or evidence:
            if self.test_reports is None:
                from .sandbox_view import TestReports
                self.test_reports = TestReports(self.group)
                self.test_reports.inspect_requested.connect(self.tests_requested.emit)
                self.test_slot.addWidget(self.test_reports)
            self.test_reports.set_reports(reports, evidence)
        if entry.get("changes"):
            if self.changes is None:
                self.changes = ChangeCard()
                self.changes.apply_requested.connect(self.change_apply_requested.emit)
                self.changes.reject_requested.connect(self.change_reject_requested.emit)
                self.changes.undo_requested.connect(self.change_undo_requested.emit)
                self.changes.target_requested.connect(self.target_requested.emit)
                self.change_slot.addWidget(self.changes)
                apply_control_fonts(self.changes)
            self.changes.show()
            if self.change_signature is not entry["changes"]:
                self.changes.set_report(entry["changes"])
                self.change_signature = entry["changes"]
        elif self.changes is not None:
            self.changes.hide()


# 保留原导入入口；窗口化显示独立于单条气泡。
from .chat_view import ChatView
