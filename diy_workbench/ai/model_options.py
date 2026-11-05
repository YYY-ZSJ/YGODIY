"""高级设置中的当前模型容量和分档单价，保存到当前服务配置。"""

import copy

from PyQt5.QtWidgets import QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox, QWidget

from .model_info import PRICE_FIELDS, builtin


class ModelOptions(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.overrides, self.current, self.config = {}, None, {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        self.context = QSpinBox()
        self.context.setRange(0, 2000000000)
        self.context.setSpecialValueText("自动获取 / 内置表")
        form.addRow("当前模型上下文上限", self.context)
        self.price_mode = QComboBox()
        self.price_mode.addItems(["使用内置单价", "手填当前模型单价"])
        form.addRow("费用估算", self.price_mode)
        self.currency = QComboBox()
        self.currency.setEditable(True)
        self.currency.addItems(["CNY", "USD"])
        form.addRow("币种", self.currency)
        self.rates = {}
        for field, label in zip(PRICE_FIELDS, ("未缓存输入", "缓存读取", "缓存写入", "输出")):
            box = self.rates[field] = QDoubleSpinBox()
            box.setDecimals(6)
            box.setRange(0, 1000000)
            box.setSuffix(" / 百万词元")
            form.addRow(label, box)
        self.source = QLabel()
        self.source.setWordWrap(True)
        form.addRow(self.source)
        self.price_mode.currentIndexChanged.connect(self._enabled)

    def _enabled(self):
        enabled = self.price_mode.currentIndex() == 1
        for widget in list(self.rates.values()) + [self.currency]:
            widget.setEnabled(enabled)

    def _remember(self):
        if self.current is None:
            return
        value = {"context_window": self.context.value()}
        if self.price_mode.currentIndex() == 1:
            value["prices"] = {key: widget.value() for key, widget in self.rates.items()}
            value["prices"]["currency"] = self.currency.currentText().strip() or "CNY"
        if value.get("context_window") or value.get("prices"):
            self.overrides[self.current] = value
        else:
            self.overrides.pop(self.current, None)

    def load_profile(self, config):
        self.current = None
        self.config = dict(config)
        self.overrides = copy.deepcopy(config.get("model_overrides", {}))
        self.select_model(config.get("model", ""))

    def select_model(self, model):
        self._remember()
        self.current = model
        value = self.overrides.get(model, {})
        preset = builtin(dict(self.config, model=model))
        rates = value.get("prices") or preset.get("prices") or {}
        self.context.setValue(value.get("context_window", 0))
        self.price_mode.setCurrentIndex(1 if value.get("prices") else 0)
        for key, box in self.rates.items():
            box.setValue(rates.get(key, 0))
        self.currency.setCurrentText(rates.get("currency", "CNY"))
        self.source.setText("手填价格会覆盖当前模型内置价格。" if value.get("prices") else
                            "内置表核实于 %s；按服务商、模型及时段估算。" % rates["verified"] if rates else
                            "尚无该模型的内置单价，可手填；费用始终标为约计。")
        self._enabled()

    def value(self):
        self._remember()
        return copy.deepcopy(self.overrides)
