"""修改候选的原生预览与按钮；完整差异只读显示，不解析 HTML。"""

import json
import html

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from .appearance import apply_control_fonts, apply_font
from .field_rules import FIELD_LABELS
STATE_LABELS = {"pending": "候选待应用", "applied": "已应用，可整批撤销", "undone": "已整批撤销", "rejected": "已放弃",
                "partially_undone": "已撤销其余字段，保留手改"}


def value_text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def full_text(report):
    parts = [STATE_LABELS.get(report["state"], report["state"])]
    for row in report["rows"]:
        modes = "、".join(row.get("affected_modes", []))
        parts += ["\n%s · %s" % (row["target"], FIELD_LABELS.get(row["field"], row["field"])),
                  "会同时影响的模式：" + modes, row.get("note", "")]
        if row.get("reading_after"):
            parts.append("积木读回文字：\n" + row["reading_after"])
        parts += ["修改前：\n" + value_text(row.get("before_display", row["before"])),
                  "修改后：\n" + value_text(row.get("after_display", row["after"]))]
    if report.get("error"):
        parts += ["\n本次处理：", report["error"]]
    if report.get("undo_restored"):
        parts += ["\n已撤销：", "\n".join(report["undo_restored"])]
    if report.get("undo_kept"):
        parts += ["\n保留手改：", "\n".join(report["undo_kept"])]
    return "\n".join(parts)


class ChangeDialog(QDialog):
    def __init__(self, report, parent=None):
        super().__init__(parent)
        apply_font(self)
        self.setWindowTitle("AI 整批修改预览")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        self.report, self.entries = report, []
        self.selector = QComboBox()
        root.addWidget(self.selector)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.selector.currentIndexChanged.connect(self._select)
        self.set_report(report)
        root.addWidget(self.text)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_control_fonts(self)

    def _add_entry(self, row):
        self.entries.append(row)
        self.selector.addItem(row["target"] + " · " + FIELD_LABELS.get(row["field"], row["field"]))

    def _select(self, index):
        rows = self.entries[index:index + 1] if index >= 0 else []
        self.text.setPlainText(full_text(dict(self.report, rows=rows)))

    def set_report(self, report):
        selected = self.selector.currentIndex()
        self.report, self.entries = report, []
        self.selector.blockSignals(True)
        self.selector.clear()
        for row in report["rows"]:
            after = row.get("after")
            if isinstance(after, dict) and isinstance(after.get("卡片"), list):
                self._add_entry(dict(row, after={"卡包": after["卡包"], "卡片数量": len(after["卡片"])}))
                for index, card in enumerate(after["卡片"]):
                    self._add_entry(dict(row, target=row["target"] + " · 第%d张" % (index + 1), after=card))
            else:
                self._add_entry(row)
        self.selector.setCurrentIndex(max(0, min(selected, len(self.entries) - 1)))
        self.selector.blockSignals(False)
        self._select(self.selector.currentIndex())


class ChangeCard(QFrame):
    apply_requested = pyqtSignal(str)
    reject_requested = pyqtSignal(str)
    undo_requested = pyqtSignal(str)
    target_requested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ai_change_card")
        self.setStyleSheet("QFrame#ai_change_card{background:#edf3fd;border:1px solid #d5e2f5;border-radius:9px;}"
                          "QPushButton{padding:5px 8px;border:1px solid #ccd9ee;border-radius:6px;background:white;color:#365985;}")
        root = QVBoxLayout(self)
        root.setContentsMargins(9, 8, 9, 8)
        self.heading, self.summary, self.notice = QLabel(), QLabel(), QLabel()
        for label in (self.heading, self.summary, self.notice):
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            root.addWidget(label)
        self.summary.setTextFormat(Qt.RichText)
        self.summary.linkActivated.connect(self._target)
        self.notice.setStyleSheet("color:#a34a42;")
        row = QHBoxLayout()
        self.details = QPushButton("完整预览")
        self.details.clicked.connect(self._details)
        row.addWidget(self.details)
        self.apply_button, self.reject_button, self.undo_button = QPushButton("应用整批"), QPushButton("放弃"), QPushButton("整批撤销")
        for button, signal in ((self.apply_button, self.apply_requested), (self.reject_button, self.reject_requested), (self.undo_button, self.undo_requested)):
            button.clicked.connect(lambda checked=False, signal=signal: signal.emit(self.report["id"]))
            row.addWidget(button)
        root.addLayout(row)
        self.report, self.busy = {}, False

    def _target(self, index):
        row = self.report["rows"][int(index)]
        if row.get("card_uid"):
            self.target_requested.emit(row["card_uid"], row.get("mode", "ocg"))

    def _details(self):
        dialog = ChangeDialog(self.report, self)
        dialog.exec_()

    def set_report(self, report):
        self.report = report
        state = report["state"]
        prefix = "自动应用 · " if report.get("auto") and state == "applied" else ""
        self.heading.setText(prefix + STATE_LABELS.get(state, state))
        rows = report["rows"]
        lines = [('<a href="%d">%s</a>' % (i, html.escape(r["target"])) if r.get("card_uid") else html.escape(r["target"]))
                 + " · " + html.escape(FIELD_LABELS.get(r["field"], r["field"])) for i, r in enumerate(rows[:4])]
        if len(rows) > 4:
            lines.append("另有 %d 项，点击完整预览查看全部。" % (len(rows) - 4))
        modes = list(dict.fromkeys(mode for r in rows for mode in r.get("affected_modes", [])))
        lines.append("会同时影响的模式：" + "、".join(modes))
        if any(r.get("note", "").startswith("该模式的设置") for r in rows):
            lines.append("该模式的设置不随卡片保存。")
        self.summary.setText("<br>".join(lines))
        self.notice.setText(report.get("error", "") if report.get("available", True) else "历史批次只保留记录，不能跨重启应用或撤销。")
        self.notice.setVisible(bool(self.notice.text()))
        self.apply_button.setVisible(state == "pending")
        self.reject_button.setVisible(state == "pending")
        self.undo_button.setVisible(state == "applied")
        self.set_busy(self.busy)

    def set_busy(self, busy):
        self.busy = busy
        enabled = not busy and self.report.get("finished", False) and self.report.get("available", True)
        for button in (self.apply_button, self.reject_button, self.undo_button):
            button.setEnabled(enabled)
