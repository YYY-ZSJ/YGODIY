"""服务预设和可手填模型；测试连接交给控制器的同一套后台线程。"""

import copy

from PyQt5.QtCore import QSignalBlocker, QTimer, pyqtSignal
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from .appearance import apply_control_fonts, apply_font
from .providers import KEY_URLS, PRESETS
from .settings import DEFAULTS, validate
from .model_catalog import cache_key, cached_models
from .model_options import ModelOptions


class ModelCombo(QComboBox):
    opening = pyqtSignal()

    def showPopup(self):
        self.opening.emit()
        super().showPopup()


class ServiceDialog(QDialog):
    test_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()
    models_requested = pyqtSignal(dict)

    def __init__(self, data, notice="", parent=None):
        super().__init__(parent)
        apply_font(self)
        self.setStyleSheet("QWidget{font-family:'%s';}" % self.font().family())
        self.setWindowTitle("AI 服务设置")
        self.resize(570, 360)
        self.profiles = copy.deepcopy(data["profiles"])
        self.current = None
        self.ui_settings = copy.deepcopy(data.get("ui", {}))
        self.switching = False
        root = QVBoxLayout(self)
        intro = QLabel("使用你自己的 API 服务，费用由该服务商按你的账户计收。预设可修改，模型名也可直接输入。")
        intro.setWordWrap(True)
        root.addWidget(intro)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.preset = QComboBox()
        for key, values in PRESETS.items():
            self.preset.addItem(values[0], key)
        form.addRow("服务商预设", self.preset)
        self.protocol = QComboBox()
        self.protocol.addItem("OpenAI 兼容 · Chat Completions", "openai")
        self.protocol.addItem("Claude · Messages", "claude")
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("填写服务商提供的 base_url")
        form.addRow("服务地址", self.base_url)
        self.model = ModelCombo()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.NoInsert)
        self.model.lineEdit().setPlaceholderText("选择示例或手填实际模型名")
        self.model.opening.connect(self._models_popup)
        form.addRow("模型名", self.model)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("API Key（仅本机加密保存；本地 Ollama 可留空）")
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        self.key_button = QPushButton("获取 API Key")
        self.key_button.clicked.connect(self._open_key_page)
        key_row.addWidget(self.key_button)
        form.addRow("API Key", key_row)
        self.send_mode = QComboBox()
        self.send_mode.addItem("Enter 发送，Shift+Enter 换行", True)
        self.send_mode.addItem("Ctrl+Enter 发送，Enter 换行", False)
        self.send_mode.setCurrentIndex(0 if data.get("ui", {}).get("send_with_enter", True) else 1)
        form.addRow("发送按键", self.send_mode)
        root.addLayout(form)
        self._build_advanced(root)
        self.test_button = QPushButton("测试连接与工具调用")
        self.test_button.clicked.connect(self._test)
        root.addWidget(self.test_button)
        self.status = QLabel(notice)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("保存")
        self.buttons.button(QDialogButtonBox.Cancel).setText("取消")
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.preset.setCurrentIndex(max(0, self.preset.findData(data.get("active", "custom"))))
        self.preset.currentIndexChanged.connect(self._switch)
        self._switch()
        self.model.currentTextChanged.connect(self._model_changed)
        self.testing = False
        apply_control_fonts(self)
        QTimer.singleShot(0, self._fit_contents)

    def _build_advanced(self, root):
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("高级")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        root.addWidget(self.advanced_toggle)
        self.advanced = QScrollArea()
        self.advanced.setWidgetResizable(True)
        self.advanced.setFrameShape(QScrollArea.NoFrame)
        self.advanced.setFixedHeight(300)
        advanced_content = QWidget()
        self.advanced.setWidget(advanced_content)
        advanced_form = QFormLayout(advanced_content)
        advanced_form.setContentsMargins(0, 0, 0, 0)
        advanced_form.addRow("接口类型", self.protocol)
        self.read_timeout = QSpinBox()
        self.read_timeout.setRange(5, 600)
        self.read_timeout.setSuffix(" 秒")
        self.read_timeout.setToolTip("连续没有收到网络数据的等待时间。长思考时可提高，最长600秒。")
        advanced_form.addRow("网络读取超时", self.read_timeout)
        self.request_timeout = QSpinBox()
        self.request_timeout.setRange(30, 7200)
        self.request_timeout.setSuffix(" 秒")
        self.request_timeout.setToolTip("每次请求单独计时，默认10分钟；工具执行时间不计入。长思考可提高到最多2小时，超时可继续。")
        advanced_form.addRow("单次请求时限", self.request_timeout)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(0, 2000000)
        self.max_tokens.setSpecialValueText("不限制")
        self.max_tokens.setToolTip("默认不向 OpenAI 兼容接口传 max_tokens；Claude 自动查询该模型最大值。服务商仍有自己的模型上限。")
        self.max_tokens.setSingleStep(256)
        advanced_form.addRow("单次输出上限", self.max_tokens)
        self.tool_call_limit = QSpinBox()
        self.tool_call_limit.setRange(0, 10000)
        self.tool_call_limit.setSpecialValueText("不限制")
        self.tool_call_limit.setToolTip("默认60次；达到后保留进度，可点继续。没有整轮总时限，循环检测始终有效。")
        advanced_form.addRow("每次工具调用上限", self.tool_call_limit)
        self.task_cost_limit = QDoubleSpinBox()
        self.task_cost_limit.setDecimals(4)
        self.task_cost_limit.setRange(0, 1000000)
        self.task_cost_limit.setSingleStep(1)
        self.task_cost_limit.setSpecialValueText("关闭")
        self.task_cost_limit.setToolTip("按当前模型币种和单价估算，在请求之间检查，单次响应可能越过上限。未知单价或用量时暂停；继续可增加一份额度。")
        advanced_form.addRow("单次任务费用上限", self.task_cost_limit)
        self.model_options = ModelOptions()
        self.model_options.currency.currentTextChanged.connect(lambda code: self.task_cost_limit.setSuffix(" " + code.strip()))
        advanced_form.addRow(self.model_options)
        root.addWidget(self.advanced)
        self.advanced.hide()
        self.advanced_toggle.toggled.connect(self._advanced_toggled)

    def value(self):
        return {"service_type": "text", "preset": self.preset.currentData(), "protocol": self.protocol.currentData(),
                "base_url": self.base_url.text().strip().rstrip("/"), "model": self.model.currentText().strip(),
                "api_key": self.key.text().strip(), "read_timeout": self.read_timeout.value(),
                "request_timeout": self.request_timeout.value(), "task_cost_limit": self.task_cost_limit.value(),
                "max_tokens": self.max_tokens.value(), "tool_call_limit": self.tool_call_limit.value(), "model_overrides": self.model_options.value()}

    def _switch(self, *_):
        if self.current is not None:
            previous = self.value()
            previous["preset"] = self.current
            self.profiles[self.current] = previous
        self.current = self.preset.currentData()
        self.switching = True
        _, protocol, base_url, models = PRESETS[self.current]
        value = self.profiles.get(self.current) or dict(DEFAULTS, protocol=protocol, base_url=base_url,
                                                       model=models[0] if models else "")
        self.protocol.setCurrentIndex(max(0, self.protocol.findData(value["protocol"])))
        self.base_url.setText(value["base_url"])
        self.key.setText(value.get("api_key", ""))
        self.model.clear()
        self.model.addItems(models)
        self.model.setCurrentText(value["model"])
        self.read_timeout.setValue(value.get("read_timeout", DEFAULTS["read_timeout"]))
        self.request_timeout.setValue(value.get("request_timeout", DEFAULTS["request_timeout"]))
        self.task_cost_limit.setValue(value.get("task_cost_limit", 0))
        self.max_tokens.setValue(value.get("max_tokens", 0))
        self.tool_call_limit.setValue(value.get("tool_call_limit", 60))
        self.model_options.load_profile(value)
        self.task_cost_limit.setSuffix(" " + self.model_options.currency.currentText().strip())
        self.switching = False
        self.key_button.setEnabled(self.current in KEY_URLS)
        self.key_button.setToolTip(KEY_URLS.get(self.current, "自定义服务请到对应服务商的控制台创建 API Key。"))

    def _model_changed(self, model):
        if not self.switching:
            self.model_options.config["base_url"] = self.base_url.text().strip()
            self.model_options.select_model(model)

    def _replace_models(self, models):
        selected = self.model.currentText()
        with QSignalBlocker(self.model):
            self.model.clear()
            self.model.addItems(models)
            self.model.setCurrentText(selected)

    def _models_popup(self):
        config = self.value()
        models = cached_models(config) or list(PRESETS[self.current][3])
        self._replace_models(models)
        error = validate(dict(config, model="list-models"))
        if error:
            self.status.setText(error + " 模型名仍可手填。")
            return
        self.status.setText("正在获取可用模型……")
        self.models_requested.emit(config)

    def show_models(self, result):
        if result["key"] != cache_key(self.value()):
            return
        self._replace_models(result.get("models") or cached_models(self.value()) or list(PRESETS[self.current][3]))
        self.status.setText(result.get("error") or result.get("notice") or "可用模型已更新；也可手填模型名。")

    def _advanced_toggled(self, shown):
        if shown:
            available = self.screen().availableGeometry().height()
            self.advanced.setFixedHeight(max(100, min(300, available - self.height() - 80)))
        self.advanced.setVisible(shown)
        self.advanced_toggle.setArrowType(Qt.DownArrow if shown else Qt.RightArrow)
        QTimer.singleShot(0, self._fit_contents)

    def _fit_contents(self):
        self.layout().activate()
        self.resize(self.width(), self.layout().sizeHint().height())

    def _open_key_page(self):
        url = KEY_URLS.get(self.current)
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def ui_value(self):
        return dict(self.ui_settings, send_with_enter=self.send_mode.currentData())

    def _test(self):
        if self.testing:
            self.stop_requested.emit()
            self.test_button.setEnabled(False)
            self.status.setText("已请求停止，正在等待网络读取结束……")
            return
        error = validate(self.value())
        if error:
            self.status.setText(error)
        else:
            self.test_requested.emit(self.value())

    def set_testing(self, testing, text=""):
        self.testing = testing
        self.test_button.setEnabled(True)
        self.test_button.setText("停止测试" if testing else "测试连接与工具调用")
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not testing)
        for widget in (self.preset, self.protocol, self.base_url, self.model, self.key, self.key_button,
                       self.send_mode, self.read_timeout, self.request_timeout, self.max_tokens, self.tool_call_limit,
                       self.task_cost_limit, self.model_options):
            widget.setEnabled(not testing)
        if not testing:
            self.key_button.setEnabled(self.current in KEY_URLS)
        if text:
            self.status.setText(text)

    def _accept(self):
        error = validate(self.value())
        if error:
            self.status.setText(error)
            return
        self.profiles[self.current] = self.value()
        self.accept()
