"""玩家看到测试目的和原文依据，JSON与引擎提问默认收起。"""

import json

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget

from .appearance import apply_control_fonts, apply_font


def expectation_text(check):
    from sandbox.scenario import Runner
    player = "自己" if check.get("player", 0) == 0 else "对方"
    card = "本卡" if check.get("card") == "self" else str(check.get("card", ""))
    kind = check["check"]
    if kind == "count":
        subject = player + Runner.ZONE_ZH.get(check.get("in"), "") + "中" + card + "的数量"
    elif kind == "offered":
        return player + card + ("可以发动" if check.get("eq") else "不能发动")
    else:
        subject = player + card + {"lp": "基本分", "atk": "攻击力", "def": "守备力", "faceup": "是否表侧", "event": "事件次数"}.get(kind, kind)
    key = next(k for k in ("eq", "ge", "le") if k in check)
    return subject + {"eq": "＝", "ge": "至少", "le": "至多"}[key] + str(check[key])


class TestReports(QWidget):
    inspect_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(4, 4, 4, 4)
        self.reports = None
        self.evidence = None

    def set_reports(self, reports, evidence=None):
        if self.reports is reports and self.evidence == evidence:
            return
        self.reports = reports
        self.evidence = evidence
        while self.root.count():
            item = self.root.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        latest = {r["scenario_id"]: r for r in reports}
        if reports:
            self.root.addWidget(QLabel("本次测试记录；当前是否过期可在下方查看。"))
        for report in latest.values():
            state = report["status"]
            label = QLabel(report["name"] + " · " + state)
            label.setWordWrap(True)
            label.setStyleSheet("color:%s;" % ("#327657" if state == "通过" else "#a34a4a"))
            self.root.addWidget(label)
            basis = QLabel("原文：" + report.get("basis", ""))
            basis.setWordWrap(True)
            self.root.addWidget(basis)
        if evidence:
            missing = ["效果%d %s（%s）" % (r["effect"], r["label"], r["status"]) for r in evidence.get("requirements", []) if r["status"] != "通过"]
            missing.extend(r["name"] + "（" + r["status"] + "）" for r in evidence.get("unverified_scenarios", []))
            label = QLabel("未验证：" + "；".join(missing) if missing else "最低清单已通过；未列出的边界仍未验证。")
            label.setWordWrap(True)
            self.root.addWidget(label)
        for uid in dict.fromkeys(r.get("card_uid") for r in reports if r.get("card_uid")):
            button = QPushButton("查看卡片当前测试与未验证项")
            button.clicked.connect(lambda _, target=uid: self.inspect_requested.emit(target))
            self.root.addWidget(button)
        apply_control_fonts(self)


class TestDialog(QDialog):
    def __init__(self, document, pending=False, parent=None):
        super().__init__(parent)
        from sandbox.test_data import coverage, digest, revision, suite
        self.setWindowTitle("候选测试 · 尚未应用" if pending else "卡片测试结果")
        self.resize(680, 580)
        apply_font(self)
        root = QVBoxLayout(self)
        scroll, content = QScrollArea(), QWidget()
        scroll.setWidgetResizable(True)
        body = QVBoxLayout(content)
        tests = suite(document)
        needs = coverage(document, tests)
        summary = QLabel("最低反向清单：%d / %d 已验证。其余均未验证；此清单不保证覆盖所有规则。" % (needs["passed"], needs["total"]))
        summary.setWordWrap(True)
        body.addWidget(summary)
        for item in needs["requirements"]:
            label = QLabel("效果%d · %s · %s" % (item["effect"], item["label"], item["status"]))
            body.addWidget(label)
        latest = {r["scenario_id"]: r for r in tests["results"]}
        for scene in tests["scenarios"]:
            result = latest.get(scene["id"], {})
            stale = bool(result) and (result.get("revision") != revision(document) or result.get("scenario_revision") != digest(scene))
            status = "过期，请重测" if stale else result.get("status", "未验证")
            label = QLabel(scene["name"] + " · " + status + "\n原文：" + scene["basis"])
            label.setWordWrap(True)
            body.addWidget(label)
            button = QToolButton()
            button.setText("查看情景和执行详情")
            button.setCheckable(True)
            detail = QPlainTextEdit()
            detail.setReadOnly(True)
            detail.setMaximumHeight(180)
            detail.hide()
            def show(checked, editor=detail, source=scene, outcome=result):
                if checked and not editor.toPlainText():
                    editor.setPlainText(json.dumps({"scenario": source, "result": outcome}, ensure_ascii=False, indent=2))
                editor.setVisible(checked)
            button.toggled.connect(show)
            body.addWidget(button)
            body.addWidget(detail)
        body.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        apply_control_fonts(self)
