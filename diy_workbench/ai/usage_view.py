"""词元用量面板与逐次请求明细，数字格式全界面共用。"""

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                             QHeaderView, QPushButton, QTableView, QVBoxLayout)

from .appearance import apply_control_fonts, apply_font
from .usage import hit_rate, money, number, token_value, tooltip


class RequestTable(QAbstractTableModel):
    HEADERS = ("请求", "模型", "命中率", "未缓存输入", "缓存读取", "缓存写入", "输出", "约计费用")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.requests, self.style = [], "grouped"

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.requests)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        request = self.requests[index.row()]
        usage = request.get("usage", {})
        if role == Qt.ToolTipRole:
            rates = request.get("rates") or {}
            cost = request.get("cost") or {}
            totals = {cost["currency"]: cost["total"]} if cost.get("known") else {}
            prefix = request.get("prefix") or {}
            detail = "前次前缀：%d / %d 块保持一致" % (prefix.get("matched_units", 0), prefix.get("previous_units", 0))
            return tooltip(dict(usage, costs=totals), self.style) + "\n" + detail + "\n" + request.get("cache_debug", "") + "\n" + rates.get("tier", "") + "\n" + rates.get("source", "")
        if role != Qt.DisplayRole:
            return None
        cost = request.get("cost") or {}
        costs = {cost["currency"]: cost["total"]} if cost.get("known") else {}
        values = [str(index.row() + 1) + (" · 压缩" if request.get("purpose") == "compression" else ""),
                  request.get("model", ""), hit_rate(usage)]
        values += [number(usage.get(key), self.style) for key in ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens")]
        values.append(money(costs))
        return values[index.column()]

    def update(self, requests, style):
        self.beginResetModel()
        self.requests, self.style = requests, style
        self.endResetModel()


class UsageDialog(QDialog):
    format_changed = pyqtSignal(str)

    def __init__(self, record, style="grouped", parent=None):
        super().__init__(parent)
        apply_font(self)
        self.record, self.style = record, style
        self.setWindowTitle("词元用量")
        self.resize(740, 510)
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("词元用量"))
        self.total = QLabel()
        self.total.setStyleSheet("font-size:25px;font-weight:700;color:#263f65;padding:8px;")
        heading.addWidget(self.total, 1)
        self.format_button = QPushButton()
        self.format_button.clicked.connect(self._toggle_format)
        heading.addWidget(self.format_button)
        root.addLayout(heading)
        form = self.form = QFormLayout()
        self.values = {}
        for key, label in (("hit", "缓存命中率"), ("uncached_input_tokens", "未缓存输入"),
                           ("cache_read_tokens", "缓存读取"), ("cache_write_tokens", "缓存写入"),
                           ("output_tokens", "输出"), ("reasoning_tokens", "其中思考"), ("cost", "约计费用")):
            value = self.values[key] = QLabel()
            form.addRow(label, value)
        root.addLayout(form)
        self.notice = QLabel("费用按每次请求当时的单价分档相加；实际扣费以服务商账单为准。")
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        root.addWidget(QLabel("逐次请求（包括工具往返和压缩）"))
        self.table = QTableView()
        self.model = RequestTable(self.table)
        self.table.setModel(self.model)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(78)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 55)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(7, 135)
        self.table.verticalHeader().hide()
        root.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh()
        apply_control_fonts(self)

    def _toggle_format(self):
        self.style = "wan" if self.style == "grouped" else "grouped"
        self.refresh()
        self.format_changed.emit(self.style)

    def refresh(self):
        usage = self.record.get("usage", {})
        self.total.setText(("≥" if usage.get("unknown_calls") else "") + number(usage.get("input_tokens", 0) + usage.get("output_tokens", 0), self.style) + " 词元")
        self.total.setToolTip(tooltip(usage, self.style))
        self.format_button.setText("切换为万" if self.style == "grouped" else "每4位分组")
        self.values["hit"].setText(hit_rate(usage))
        for key in ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"):
            value = token_value(usage, key)
            suffix = "（已知部分）" if usage.get("cache_unknown_calls") and key != "output_tokens" else ""
            self.values[key].setText(number(value, self.style) + " 词元" + suffix)
        self.values["cost"].setText(money(usage.get("costs", {})) + ("（部分未计价）" if usage.get("unpriced_calls") else ""))
        partial = "已返回部分；" if usage.get("reasoning_reported_calls", 0) < usage.get("calls", 0) else ""
        self.values["reasoning_tokens"].setText(number(usage.get("reasoning_tokens"), self.style) + " 词元（" + partial + "已含在输出中）")
        has_reasoning = bool(usage.get("reasoning_reported_calls"))
        self.values["reasoning_tokens"].setVisible(has_reasoning)
        self.form.labelForField(self.values["reasoning_tokens"]).setVisible(has_reasoning)
        has_claude = any(request.get("protocol") == "claude" for request in self.record.get("requests", []))
        self.values["cache_write_tokens"].setVisible(has_claude)
        self.form.labelForField(self.values["cache_write_tokens"]).setVisible(has_claude)
        self.table.setColumnHidden(5, not has_claude)
        self.model.update(self.record.get("requests", []), self.style)
