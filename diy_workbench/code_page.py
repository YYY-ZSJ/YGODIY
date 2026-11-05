"""工作台的「脚本」页：直接写这张卡的完整 Lua。保存后导出和测试都用这份，积木不再生成脚本。"""

import re

from PyQt5.QtCore import QEvent, QRect, QSize, QStringListModel, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor, QTextDocument
from PyQt5.QtWidgets import (QCompleter, QFormLayout, QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QScrollArea, QSizePolicy, QSplitter, QTabWidget, QTextEdit, QToolTip, QVBoxLayout, QWidget)

from .lua_intel import expand, intel

KEYWORDS = ("and break do else elseif end false for function goto if in local nil not or repeat return then true until while").split()
RULES = ((r"\b(?:%s)\b" % "|".join(KEYWORDS), "#b5651d", True), (r"\b(?:Duel|Card|Effect|Group|aux)\b", "#1f6fb2", False),
         (r"\b[A-Z][A-Z0-9_]{2,}\b", "#7a4fb5", False), (r"\b\d+\b|\b0x[0-9a-fA-F]+\b", "#2c7a4b", False),
         (r"\"[^\"]*\"|'[^']*'", "#a33a3a", False), (r"--.*$", "#8a8f98", False))


class LuaHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        for pattern, color, bold in RULES:
            style = QTextCharFormat()
            style.setForeground(QColor(color))
            if bold:
                style.setFontWeight(QFont.Bold)
            self.rules.append((re.compile(pattern), style))

    def highlightBlock(self, text):
        for pattern, style in self.rules:
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), style)


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_numbers(event)


class CodeEditor(QPlainTextEdit):
    """带行号的代码框：行号画在左边距里，跟着滚动；输入时补全，悬停看接口说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.numbers = LineNumbers(self)
        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_area)
        self._update_width()
        self.entries = {}
        self.marks = {}
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setModel(QStringListModel(self.completer))
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.activated[str].connect(self.accept_completion)
        self.cursorPositionChanged.connect(self.refresh_selections)
        self.refresh_selections()

    def word_before_cursor(self):
        block = self.textCursor().block().text()[:self.textCursor().positionInBlock()]
        found = re.search(r"#?[A-Za-z_][\w]*(?:[.:]\w*)?$|#$", block)
        return found.group() if found else ""

    def update_completion(self, typed):
        prefix = self.word_before_cursor()
        popup = self.completer.popup()
        if not typed or not (typed[-1].isalnum() or typed[-1] in "_.:#") or (len(prefix) < 2 and prefix != "#"):
            popup.hide()
            return
        owner = None
        if ":" in prefix:
            before = self.toPlainText()[:self.textCursor().position() - len(prefix)]
            owner = intel().object_type(before, prefix.split(":")[0])
        entries = intel().complete(prefix, owner)
        if not entries:
            popup.hide()
            return
        labels = ["%s  ·  %s" % (entry.name, entry.detail[:60]) for entry in entries]
        self.entries = dict(zip(labels, entries))
        self.completer.model().setStringList(labels)
        rect = self.cursorRect()
        rect.setWidth(min(620, popup.sizeHintForColumn(0) + 30))
        rect.translate(self.viewportMargins().left(), 0)
        self.completer.complete(rect)
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))

    def accept_completion(self, label):
        entry = self.entries.get(label)
        if entry is None:
            return
        prefix = self.word_before_cursor()
        cursor = self.textCursor()
        keep = prefix.rsplit(":", 1)[0] + ":" if ":" in prefix and entry.kind == "方法" else ""
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix) - len(keep))
        text, position = expand(entry.insert)
        start = cursor.selectionStart()
        cursor.insertText(text)
        if entry.kind == "片段":
            cursor.setPosition(start + position)
        self.setTextCursor(cursor)

    def keyPressEvent(self, event):
        popup = self.completer.popup()
        if popup.isVisible() and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab, Qt.Key_Escape, Qt.Key_Backtab):
            event.ignore()
            return
        super().keyPressEvent(event)
        text = event.text()
        self.update_completion(text)
        if text == "(":           # 等补全列表关完再弹，否则窗口切换的事件会把提示一起关掉
            QTimer.singleShot(30, self.show_signature)

    def show_signature(self):
        block = self.textCursor().block().text()[:self.textCursor().positionInBlock()]
        found = re.search(r"([\w.:]+)\($", block)
        entries = intel().lookup(found.group(1)) if found else []
        if entries:
            QToolTip.showText(self.mapToGlobal(self.cursorRect().bottomLeft()), entries[0].detail, self)

    def viewportEvent(self, event):
        if event.type() == QEvent.ToolTip:
            cursor = self.cursorForPosition(event.pos())
            line = cursor.blockNumber() + 1
            lines = [self.marks[line]] if line in self.marks else []
            entry = self.entry_at(cursor)
            if entry:
                lines.append("%s\n%s" % (entry.detail, entry.doc))
            if lines:
                QToolTip.showText(event.globalPos(), "\n\n".join(lines), self)
            else:
                QToolTip.hideText()
            return True
        return super().viewportEvent(event)

    def entry_at(self, cursor):
        text, column = cursor.block().text(), cursor.positionInBlock()
        for found in re.finditer(r"[A-Za-z_][\w]*(?:[.:]\w+)*", text):
            if found.start() <= column <= found.end():
                entries = intel().lookup(found.group())
                return entries[0] if entries else None
        return None

    def set_marks(self, marks):
        """marks：{行号: 说明}。出问题的行画底色，悬停能看到说明。"""
        self.marks = marks
        self.refresh_selections()

    def _line_selection(self, block, color):
        selection = QTextEdit.ExtraSelection()
        selection.format.setBackground(QColor(color))
        selection.format.setProperty(QTextCharFormat.FullWidthSelection, True)
        selection.cursor = QTextCursor(block)
        return selection

    def refresh_selections(self):
        """光标所在行浅蓝，有问题的行浅红；两者重合时显示问题。"""
        selections = [self._line_selection(self.textCursor().block(), "#e6f0fb")]
        for line in self.marks:
            block = self.document().findBlockByNumber(line - 1)
            if block.isValid():
                selections.append(self._line_selection(block, "#fbe3e0"))
        self.setExtraSelections(selections)

    def go_to_line(self, line):
        block = self.document().findBlockByNumber(line - 1)
        if block.isValid():
            self.setTextCursor(QTextCursor(block))
            self.centerCursor()
            self.setFocus()

    def insert_entry(self, entry):
        text, position = expand(entry.insert)
        cursor = self.textCursor()
        start = cursor.selectionStart()
        cursor.insertText(text)
        if entry.kind == "片段":
            cursor.setPosition(start + position)
        self.setTextCursor(cursor)
        self.setFocus()

    def number_width(self):
        return 14 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def _update_width(self, _count=0):
        self.setViewportMargins(self.number_width(), 0, 0, 0)

    def _update_area(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self.numbers.setGeometry(QRect(area.left(), area.top(), self.number_width(), area.height()))

    def setFont(self, font):
        super().setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._update_width()

    def paint_numbers(self, event):
        painter = QPainter(self.numbers)
        painter.fillRect(event.rect(), QColor("#f0f1f3"))
        painter.setPen(QColor("#8a8f98"))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible():
                painter.drawText(0, top, self.numbers.width() - 6, height, Qt.AlignRight, str(block.blockNumber() + 1))
            top += round(self.blockBoundingRect(block).height())
            block = block.next()


class Handbook(QWidget):
    """可搜索的函数、常量和片段，双击插入到光标处。"""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜函数、常量、片段，中文说明也能搜")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)
        self.items = QListWidget()
        self.items.itemActivated.connect(self._insert)
        self.items.currentItemChanged.connect(self._show)
        layout.addWidget(self.items, 1)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(130)
        layout.addWidget(self.detail)

    def refresh(self, text=""):
        self.items.clear()
        for entry in intel().search(text):
            item = QListWidgetItem("%s  %s" % (entry.kind, entry.name))
            item.setData(Qt.UserRole, entry)
            self.items.addItem(item)

    def _show(self, item):
        if item is not None:
            entry = item.data(Qt.UserRole)
            self.detail.setPlainText("%s\n%s" % (entry.detail, entry.doc))

    def _insert(self, item):
        self.editor.insert_entry(item.data(Qt.UserRole))


class CodePage(QWidget):
    save_requested = pyqtSignal()
    export_image_requested = pyqtSignal()
    generate_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    check_requested = pyqtSignal()
    open_requested = pyqtSignal()
    reload_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel()
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        root.addWidget(self.title)
        self.toolbar = QGridLayout()
        self.toolbar.setSpacing(4)
        self.buttons = []
        for text, signal in (("让伊格尼斯写", self.generate_requested), ("重新载入", self.reload_requested), ("检查报错", self.check_requested), ("外部打开", self.open_requested),
                             ("导出代码图片", self.export_image_requested), ("改回积木生成", self.reset_requested), ("保存脚本", self.save_requested)):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            self.buttons.append(button)
        root.addLayout(self.toolbar)
        self._arrange_buttons()
        split = QSplitter()
        self.editor = CodeEditor()
        self.editor.setFont(QFont("Consolas", 10))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.highlighter = LuaHighlighter(self.editor.document())
        split.addWidget(self.editor)
        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        self.desc = QPlainTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setMaximumHeight(110)
        side_layout.addWidget(QLabel("效果 / 描述"))
        side_layout.addWidget(self.desc)
        side_layout.addWidget(QLabel("aux.Stringid 文本"))
        holder = QWidget()
        form = QFormLayout(holder)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.strings = []
        for index in range(16):
            edit = QLineEdit()
            self.strings.append(edit)
            form.addRow("Stringid %d" % index, edit)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        side_layout.addWidget(scroll, 1)
        tabs = QTabWidget()
        tabs.addTab(side, "卡片")
        self.handbook = Handbook(self.editor)
        tabs.addTab(self.handbook, "手册")
        tabs.currentChanged.connect(lambda index: self.handbook.refresh(self.handbook.search.text()) if index == 1 and not self.handbook.items.count() else None)
        split.addWidget(tabs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        split.setSizes([3000, 1000])
        root.addWidget(split, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.results = QListWidget()
        self.results.setMaximumHeight(90)
        self.results.itemActivated.connect(self._jump)
        self.results.itemClicked.connect(self._jump)
        root.addWidget(self.results)
        self.card_key = None

    def _arrange_buttons(self):
        """放不下时换行，按钮文字不能被裁掉。"""
        width = max(button.sizeHint().width() for button in self.buttons) + self.toolbar.spacing()
        columns = max(1, min(len(self.buttons), self.width() // width))
        for index, button in enumerate(self.buttons):
            self.toolbar.addWidget(button, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange_buttons()

    def show_card(self, key, title, code, desc, auto_strings, custom, handwritten):
        """换了卡才重新载入代码，正在写的内容不会被刷新冲掉。"""
        self.title.setText(title)
        self.desc.setPlainText(desc)
        for index, edit in enumerate(self.strings):
            edit.setPlaceholderText(auto_strings[index] if index < len(auto_strings) else "")
            if key != self.card_key:
                edit.setText(custom.get(str(index), ""))
        if key != self.card_key or not self.editor.document().isModified():
            self.editor.setPlainText(code)
            self.editor.document().setModified(False)
        self.card_key = key
        self.status.setText("这张卡用手写脚本：导出和测试都用这份，积木不再生成。" if handwritten else
                            "现在显示的是积木生成的脚本，保存后这张卡就改用手写脚本。")

    def text(self):
        return self.editor.toPlainText()

    def custom_strings(self):
        return {str(index): edit.text().strip() for index, edit in enumerate(self.strings) if edit.text().strip()}

    def set_text(self, text):
        self.editor.setPlainText(text)
        self.editor.document().setModified(True)

    def show_lines(self, lines):
        """检查结果：写了行号的可以点击跳过去，出错的行在代码里标出来。"""
        self.results.clear()
        marks = {}
        for mark, text in lines:
            item = QListWidgetItem("%s %s" % (mark, text))
            found = re.search(r"第(\d+)行|\]:(\d+):", text)
            if found:
                line = int(found.group(1) or found.group(2))
                item.setData(Qt.UserRole, line)
                if mark != "√":
                    marks.setdefault(line, text)
            self.results.addItem(item)
        self.editor.set_marks(marks)

    def _jump(self, item):
        line = item.data(Qt.UserRole)
        if line:
            self.editor.go_to_line(line)

    def diagnostics(self):
        from blocks.lua_guard import locate
        code = self.text()
        lines = [("×", "第%d行：%s" % row) for row in locate(code)]
        lines += [("!", "第%d行：资料里没有 %s，可能写错了" % row) for row in intel().unknown_calls(code)]
        return lines

    def render_image(self, width=1100):
        """整段代码画成图片，不受窗口大小限制。"""
        document = QTextDocument()
        document.setDefaultFont(self.editor.font())
        document.setPlainText(self.text())
        LuaHighlighter(document)
        document.setTextWidth(width)
        size = document.size().toSize()
        image = QImage(size.width() + 40, size.height() + 40, QImage.Format_RGB32)
        image.fill(QColor("#ffffff"))
        painter = QPainter(image)
        painter.translate(20, 20)
        document.drawContents(painter)
        painter.end()
        return image
