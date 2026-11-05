"""原生 Qt 聊天侧栏：服务栏、气泡、欢迎示例及框内发送/停止。"""

from PyQt5.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton, QSizePolicy,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .appearance import action_icon, apply_control_fonts, apply_font
from .message_view import ChatView
from .providers import PRESETS, REASONING_LEVELS
from .status_view import StatusBar, capacity
from .header_view import ModelButton


class SubmitEdit(QPlainTextEdit):
    submitted = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.send_with_enter = True
        self._composing = False

    def inputMethodEvent(self, event):
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def keyPressEvent(self, event):
        enter = event.key() in (Qt.Key_Return, Qt.Key_Enter)
        modifiers = event.modifiers()
        if enter and not self._composing and not modifiers & Qt.ShiftModifier:
            if self.send_with_enter or modifiers & Qt.ControlModifier:
                self.submitted.emit()
                event.accept()
                return
        super().keyPressEvent(event)


class AssistantPanel(QWidget):
    send_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    new_requested = pyqtSignal()
    restore_requested = pyqtSignal(str)
    retry_requested = pyqtSignal(str)
    input_changed = pyqtSignal(str)
    auto_apply_changed = pyqtSignal(bool)
    reasoning_changed = pyqtSignal(str)
    change_apply_requested = pyqtSignal(str)
    change_reject_requested = pyqtSignal(str)
    change_undo_requested = pyqtSignal(str)
    change_history_requested = pyqtSignal()
    history_requested = pyqtSignal()
    attachment_changed = pyqtSignal(bool)
    target_requested = pyqtSignal(str, str)
    tests_requested = pyqtSignal(str)
    usage_requested = pyqtSignal()
    compress_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    context_requested = pyqtSignal()
    stats_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        apply_font(self)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setObjectName("ai_panel")
        self.setMinimumWidth(320)
        self.setStyleSheet("QWidget{font-family:'%s';}" % self.font().family() +
                          "QWidget#ai_panel{background:#f7f9fc;color:#25334b;}"
                          "QToolButton{border:0;border-radius:6px;padding:5px;color:#536681;}"
                          "QToolButton:hover{background:#e9eef7;}")
        self._busy, self._balance_text, self._balance_notice, self._balance_pending = False, None, "", False
        self._usage, self._service_text = {}, "选择服务和模型"
        self._record = None
        self._attached, self.number_style = True, "grouped"
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 10, 8)
        root.setSpacing(9)
        self._build_header(root)
        self._build_body(root)
        self._build_input(root)
        self.set_send_mode(True)
        self.set_service(None)
        apply_control_fonts(self)

    def _build_header(self, root):
        heading = QHBoxLayout()
        heading.setSpacing(4)
        self.service_button = ModelButton()
        self.service_button.clicked.connect(self.settings_requested.emit)
        heading.addWidget(self.service_button, 1)
        self.balance = QLabel("")
        self.balance.setStyleSheet("color:#718198;font-size:11px;")
        heading.addWidget(self.balance)
        self.new_button = self._icon_button("new", "新对话")
        self.new_button.clicked.connect(self.new_requested.emit)
        heading.addWidget(self.new_button)
        self.history_button = self._icon_button("history", "历史")
        self.history_menu = QMenu(self.history_button)
        self.history_button.clicked.connect(self.history_requested.emit)
        heading.addWidget(self.history_button)
        self.settings_button = self._icon_button("settings", "设置")
        self.settings_button.clicked.connect(self.settings_requested.emit)
        heading.addWidget(self.settings_button)
        root.addLayout(heading)

    def _icon_button(self, name, title):
        button = QToolButton()
        button.setIcon(action_icon(name))
        button.setToolTip(title)
        button.setAccessibleName(title)
        button.setFixedSize(30, 30)
        return button

    def _build_body(self, root):
        self.stack = QStackedWidget()
        self.welcome = QWidget()
        welcome = QVBoxLayout(self.welcome)
        welcome.addStretch(1)
        title = QLabel("一起设计你的下一张卡")
        title.setWordWrap(True)
        title.setStyleSheet("font-size:17px;font-weight:600;color:#344967;")
        welcome.addWidget(title)
        hint = QLabel("聊聊创意，或者从已有的效果文字开始。\n也可以让我切换模式、查阅卡片资料。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#8995a7;")
        welcome.addWidget(hint)
        self.examples = []
        for text in ("帮我设计一张……", "把这段效果改成官方写法", "看看这张卡有没有规则歧义"):
            button = QPushButton(text)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("text-align:left;border:1px solid #e2e8f1;border-radius:10px;padding:12px;background:white;color:#61738d;")
            button.clicked.connect(lambda checked=False, text=text: self._example(text))
            self.examples.append(button)
            welcome.addWidget(button)
        welcome.addStretch(2)
        self.stack.addWidget(self.welcome)
        self.chat = ChatView()
        self.chat.setStyleSheet("QScrollArea{background:transparent;}QScrollArea>QWidget>QWidget{background:transparent;}")
        self.chat.retry_requested.connect(self.retry_requested.emit)
        self.chat.change_apply_requested.connect(self.change_apply_requested.emit)
        self.chat.change_reject_requested.connect(self.change_reject_requested.emit)
        self.chat.change_undo_requested.connect(self.change_undo_requested.emit)
        self.chat.target_requested.connect(self.target_requested.emit)
        self.chat.tests_requested.connect(self.tests_requested.emit)
        self.stack.addWidget(self.chat)
        root.addWidget(self.stack, 1)
        self.status = QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color:#8b96a5;font-size:11px;padding:3px;")
        root.addWidget(self.status)

    def _build_input(self, root):
        attachment = QHBoxLayout()
        self.card_label = QLabel()
        self.card_label.setWordWrap(True)
        self.card_label.setStyleSheet("color:#647994;padding:3px;")
        attachment.addWidget(self.card_label, 1)
        self.attachment_button = QToolButton()
        self.attachment_button.clicked.connect(lambda: self.attachment_changed.emit(not self._attached))
        attachment.addWidget(self.attachment_button)
        root.addLayout(attachment)
        box = QFrame()
        box.setObjectName("ai_input_box")
        box.setStyleSheet("QFrame#ai_input_box{background:white;border:1px solid #dce4ef;border-radius:13px;}")
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(10, 8, 8, 8)
        box_layout.setSpacing(3)
        self.input = SubmitEdit()
        self.input.setPlaceholderText("描述你想做的卡片……")
        self.input.setMinimumHeight(62)
        self.input.setMaximumHeight(120)
        self.input.setStyleSheet("QPlainTextEdit{background:transparent;border:0;color:#30405a;padding:0;}")
        self.input.textChanged.connect(lambda: self.input_changed.emit(self.input.toPlainText()))
        self.input.submitted.connect(self._primary_action)
        box_layout.addWidget(self.input)
        bar = QHBoxLayout()
        self.auto_apply = QToolButton()
        self.auto_apply.setCheckable(True)
        self.auto_apply.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.auto_apply.setCursor(Qt.PointingHandCursor)
        self.auto_apply.setToolTip("本次对话自动应用修改（可撤销）；删除、导出、安装和覆盖文件仍逐次确认。")
        self.auto_apply.setStyleSheet("QToolButton{border:1px solid #dce4ef;border-radius:7px;padding:4px 7px;color:#60728d;}"
                                     "QToolButton:checked{background:#e3efff;border-color:#6c93da;color:#2455a2;}")
        self.auto_apply.toggled.connect(self._auto_apply_toggled)
        self._auto_apply_toggled(False)
        bar.addWidget(self.auto_apply)
        self.batch_button = QToolButton()
        self.batch_button.setText("批次")
        self.batch_button.setToolTip("查看本次启动的 AI 修改记录，应用或整批撤销")
        self.batch_button.clicked.connect(self.change_history_requested.emit)
        bar.addWidget(self.batch_button)
        self.reasoning = QComboBox()
        self.reasoning.setToolTip("思考等级：越高越慢、越费词元；默认由服务商决定")
        for value, label in REASONING_LEVELS:
            self.reasoning.addItem("默认思考" if not value else label if value == "off" else "思考" + label, value)
        self.reasoning.activated.connect(lambda: self.reasoning_changed.emit(self.reasoning.currentData()))
        self.reasoning.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        bar.addWidget(self.reasoning)
        self.shortcut_label = QLabel()
        self.shortcut_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.shortcut_label.setStyleSheet("color:#a0aabd;font-size:10px;")
        bar.addWidget(self.shortcut_label, 1)
        self.send_button = QPushButton("发送")
        self.send_button.setCursor(Qt.PointingHandCursor)
        self.send_button.setStyleSheet("QPushButton{background:#4d76c9;color:white;border:0;border-radius:8px;padding:7px 13px;}"
                                      "QPushButton:disabled{background:#c3cfdf;}")
        self.send_button.clicked.connect(self._primary_action)
        bar.addWidget(self.send_button)
        box_layout.addLayout(bar)
        root.addWidget(box)
        self.footer = StatusBar()
        self.footer.usage_requested.connect(self.usage_requested.emit)
        self.footer.context_requested.connect(self.context_requested.emit)
        self.footer.stats_requested.connect(self.stats_requested.emit)
        self.usage_button = self.footer.tokens
        root.addWidget(self.footer)
        self.context_data = (0, {}, {}, False)

    def _auto_apply_toggled(self, enabled):
        self.auto_apply.setText("自动应用中" if enabled else "自动应用")
        self.auto_apply_changed.emit(enabled)

    def _primary_action(self):
        if self.send_button.isEnabled():
            (self.stop_requested if self._busy else self.send_requested).emit()

    def _example(self, text):
        self.input.setPlainText(text)
        self.input.setFocus()

    def set_send_mode(self, enter):
        self.input.send_with_enter = enter
        self.shortcut_label.setText("Enter 发送 · Shift+Enter 换行" if enter else "Ctrl+Enter 发送 · Enter 换行")

    def set_service(self, config):
        self.reasoning.setCurrentIndex(max(0, self.reasoning.findData((config or {}).get("reasoning_level", ""))))
        if config:
            label = PRESETS.get(config.get("preset"), ("自定义服务",))[0]
            self._service_text = config.get("model", "未选模型")
            self.service_button.setToolTip(label + " / " + self._service_text + "\n点击切换")
        else:
            self._service_text = "选择服务和模型"
            self.service_button.setToolTip(self._service_text + "\n点击切换")
        self._elide_service()

    def _elide_service(self):
        self.service_button.setText(self._service_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_service()

    def show_session(self, tab, record):
        self.show_card_name(tab)
        with QSignalBlocker(self.input):
            self.input.setPlainText(record.get("input", ""))
        self.input.setEnabled(True)
        if self._record is not record:
            self.chat.reset()
        self._record = record
        self.show_history(record)
        with QSignalBlocker(self.auto_apply):
            self.auto_apply.setChecked(record.get("auto_apply", False) is True)
            self.auto_apply.setText("自动应用中" if self.auto_apply.isChecked() else "自动应用")
        menu = self.history_menu
        menu.clear()
        for saved in reversed(record.get("archives", [])):
            action = menu.addAction("恢复：" + saved.get("title", "历史对话"))
            action.triggered.connect(lambda checked=False, uid=saved["id"]: self.restore_requested.emit(uid))
        if menu.isEmpty():
            menu.addAction("暂无历史对话").setEnabled(False)

    def show_card_name(self, tab):
        name = ((tab or {}).get("data") or {}).get("name") or (tab or {}).get("title") or "未选择卡片"
        self.card_label.setText("当前卡片 · " + name)

    def set_attachment(self, name, mode, enabled):
        self._attached = enabled
        self.card_label.setText("附带：%s（%s）" % (name, mode) if enabled else "不附带卡片资料")
        self.attachment_button.setText("×" if enabled else "+ 附带当前卡")
        self.attachment_button.setToolTip("本次会话不再自动附带卡片" if enabled else "附带当前选中的卡片")

    def show_history(self, record):
        messages = record.get("messages", [])
        self.stack.setCurrentWidget(self.chat if messages else self.welcome)
        self.chat.number_style, self.chat.busy = self.number_style, self._busy
        self.chat.show_messages(messages)
        self._usage = record.get("usage") or {}
        self._show_account()

    def set_balance(self, text=None, notice="", pending=False):
        self._balance_text, self._balance_notice, self._balance_pending = text, notice, pending
        self._show_account()

    def _show_account(self):
        from .usage import tooltip
        self.footer.set_record(self._record or {}, self.number_style)
        text = self._balance_text or ("余额待更新" if self._balance_pending else "")
        self.balance.setText(QFontMetrics(self.font()).elidedText(text, Qt.ElideRight, 115))
        self.balance.setVisible(bool(text))
        self.balance.setToolTip("\n".join(filter(None, [self._balance_text, self._balance_notice,
            tooltip(self._usage, self.number_style)])))

    def set_context(self, count, limits, has_summary=False, parts=None):
        maximum = limits.get("context_window", 0)
        ratio = count / maximum if maximum else 0
        self.context_data = (count, limits, parts or {}, has_summary)
        self.footer.context.set_ratio(ratio, bool(maximum))
        self.footer.context.setToolTip("上下文 约%s / %s\n包含系统提示、工具、摘要、历史和本轮附件。容量来源：" % (capacity(count), capacity(maximum)) + limits.get("source", "未知") +
                                     ("\n接近上限，建议压缩对话；发送前超限时会自动压缩。" if ratio > .7 else ""))

    def set_busy(self, busy, has_card=True):
        self._busy = busy
        self.chat.busy = busy
        self.send_button.setEnabled(busy or has_card)
        self.send_button.setText("停止" if busy else "发送")
        self.settings_button.setEnabled(not busy)
        self.service_button.setEnabled(not busy)
        self.new_button.setEnabled(True)
        self.history_button.setEnabled(True)
        self.auto_apply.setEnabled(not busy and has_card)
        for row in self.chat.rows.values():
            row.retry_button.setEnabled(not busy)
            if row.changes is not None:
                row.changes.set_busy(busy)
