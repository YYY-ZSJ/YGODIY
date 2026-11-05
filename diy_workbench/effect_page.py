"""工作台的「效果」页：当前这张卡的效果用积木拼（v0.3 积木编辑器嵌在中间），下面是规范文本、Lua 和检查。"""

import copy

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from . import dialogs
from .block_editor import BlockEditor

CHIP = ("QPushButton{background:#f3f8fd;border:1px solid #8fb3d6;border-radius:12px;padding:4px 10px;}"
        "QPushButton:hover{background:#e1edf9;}")
# 出场限制（卡上的 summon.restrictions，不编号的一行）
SUMMON_RESTRICT_LABELS = [("once", "自己对这张卡1回合只能有1次特殊召唤"), ("fusion", "不能作为融合素材"),
                          ("synchro", "不能作为同调素材"), ("xyz", "不能作为超量素材"), ("link", "不能作为连接素材")]


def _button(text, style, parent=None):
    b = QPushButton(text, parent)
    b.setStyleSheet(style)
    b.setCursor(Qt.PointingHandCursor)
    return b


def _flow(*widgets):
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for w in widgets:
        if isinstance(w, str):
            row.addWidget(QLabel(w))
        else:
            row.addWidget(w)
    row.addStretch(1)
    return row


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class EffectPage(QWidget):
    """效果页本体。workbench 负责读写卡片、生成文本与 Lua；这里只管显示与编辑。"""

    changed = pyqtSignal()          # 效果或素材改了（self.model 已经是新的）
    setcodes_requested = pyqtSignal()
    media_requested = pyqtSignal()
    card_data_requested = pyqtSignal()
    write_back = pyqtSignal()
    check_requested = pyqtSignal()
    export_requested = pyqtSignal()
    edit_card_requested = pyqtSignal()
    focus_toggled = pyqtSignal(bool)  # 专注模式：隐藏卡图，地方都给积木

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None           # 存进卡片的那份积木树（不含 card 块），直接修改
        self.kind = "monster"
        self.setnames = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        edit_card = QPushButton("在 OCG/TCG 模式里改卡片资料")
        edit_card.clicked.connect(self.edit_card_requested.emit)
        self.setcode_button = _button("字段：无", CHIP)
        self.setcode_button.clicked.connect(self.setcodes_requested.emit)
        top = QFrame()
        top.setObjectName("diy_summary")
        top.setStyleSheet("QFrame#diy_summary{background:#ffffff;border:1px solid #c9c9c9;}")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.addWidget(self.summary, 1)
        tl.addWidget(self.setcode_button)
        tl.addWidget(edit_card)
        self.focus_button = QPushButton("专注模式")
        self.focus_button.setCheckable(True)
        self.focus_button.setToolTip("隐藏卡图，整块地方都给积木编程（再点一次恢复）")
        self.focus_button.toggled.connect(self._focus_toggled)
        tl.addWidget(self.focus_button)
        root.addWidget(top)

        self.material_box = QWidget()
        self.material_row = QHBoxLayout(self.material_box)
        self.material_row.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.material_box)

        # 积木区和下面的规范文本 / Lua / 检查之间有分隔条，可以拖；默认大部分给积木区
        self.split = QSplitter(Qt.Vertical)
        self.split.setChildrenCollapsible(False)
        upper = QWidget()
        ul = QVBoxLayout(upper)
        ul.setContentsMargins(0, 0, 0, 0)
        self.editor = BlockEditor(embedded=True)
        self.editor.setMinimumHeight(300)
        self.editor.edited.connect(self._edited)
        ul.addWidget(self.editor, 1)
        self.problem_label = QLabel()
        self.problem_label.setWordWrap(True)
        self.problem_label.setStyleSheet("color:#666666;padding:12px;")
        self.problem_label.hide()
        ul.addWidget(self.problem_label, 1)
        self.split.addWidget(upper)
        root.addWidget(self.split, 1)

        self.tabs = QTabWidget()
        self.text_view = QPlainTextEdit()
        self.text_view.setReadOnly(True)
        self.text_status = QLabel()
        self.write_button = QPushButton("写回卡面")
        self.write_button.clicked.connect(self.write_back.emit)
        text_page = QWidget()
        tp = QVBoxLayout(text_page)
        tp.addWidget(self.text_view, 1)
        tp.addLayout(_flow(self.text_status, self.write_button))
        self.tabs.addTab(text_page, "规范文本")
        self.design_view = QPlainTextEdit()
        self.design_view.setReadOnly(True)
        self.design_status = QLabel()
        design_page = QWidget()
        dp = QVBoxLayout(design_page)
        dp.addWidget(self.design_view, 1)
        dp.addLayout(_flow(self.design_status))
        self.tabs.addTab(design_page, "设计稿")
        self.lua_view = QPlainTextEdit()
        self.lua_view.setReadOnly(True)
        self.lua_view.setFont(QFont("Consolas", 10))
        self.lua_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.tabs.addTab(self.lua_view, "Lua（只读）")
        check_page = QWidget()
        cp = QVBoxLayout(check_page)
        self.check_list = QListWidget()
        cp.addWidget(self.check_list, 1)
        sandbox = QPushButton("在测试沙盒里检查这张卡")
        sandbox.clicked.connect(self.check_requested.emit)
        cp.addLayout(_flow(sandbox))
        self.tabs.addTab(check_page, "检查")
        self.tabs.setMinimumHeight(110)
        self.split.addWidget(self.tabs)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 0)
        self.split.setSizes([700, 150])

        bar = QFrame()
        bar.setObjectName("diy_export_bar")
        bar.setStyleSheet("QFrame#diy_export_bar{background:#f4f4f4;border:1px solid #c9c9c9;}")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 10, 6)
        self.export_label = QLabel()
        bl.addWidget(self.export_label, 1)
        media = QPushButton("MDPro3 资源…")
        media.setToolTip("立绘、超框卡图、动态卡图和同名卡")
        media.clicked.connect(self.media_requested.emit)
        bl.addWidget(media)
        card_data = QPushButton("卡片数据…")
        card_data.setToolTip("提示文本和效果分类")
        card_data.clicked.connect(self.card_data_requested.emit)
        bl.addWidget(card_data)
        export = QPushButton("导出并装进 MDPro3")
        export.setStyleSheet("QPushButton{background:#2f7fc4;border:1px solid #23669f;border-radius:3px;color:#ffffff;"
                             "padding:6px 16px;font-weight:bold;}")
        export.clicked.connect(self.export_requested.emit)
        bl.addWidget(export)
        root.addWidget(bar)

    def _focus_toggled(self, on):
        self.focus_button.setText("退出专注模式" if on else "专注模式")
        self.focus_toggled.emit(on)

    # ------------------------------------------------------------ 显示

    def show_card(self, model, rec, summary, result, setnames, card_text_same, export_note, problem=None,
                  setcode_text="无"):
        """model：存进卡片的那份积木树（不含 card 块，会被直接修改）；result：store.generate 的结果。"""
        self.setnames = setnames
        self.setcode_button.setText("字段：%s" % setcode_text)
        self.setcode_button.setEnabled(not problem)
        self.export_label.setText(export_note)
        if problem:
            self.model = model
            self.summary.setText("<b>这张卡不能在工作台里编辑</b>：%s" % problem)
            self.material_box.hide()
            self.editor.hide()
            self.problem_label.setText("这张卡不能用积木编辑。")
            self.problem_label.show()
            self.text_view.setPlainText("")
            self.lua_view.setPlainText("")
            self.check_list.clear()
            return
        self.editor.show()
        self.problem_label.hide()
        self.summary.setText(summary)
        from diy_workbench import store
        from ygopack import cardinfo
        self.kind = store.card_kind(rec)
        card = dict(cardinfo.model_card(rec))
        # 同一张卡刷新时不重建积木列表（保留选中、展开、撤销记录）；换了卡或内容变了才重新载入
        same = model is self.model and self.editor.card()["effects"] == model.get("effects", []) and \
            self.editor.tree.card == card
        self.model = model
        if not same:
            self.editor.load(dict(copy.deepcopy(model), card=card))
        self._materials(rec)
        self._preview(result, card_text_same)

    def _edited(self):
        """积木改了：效果写回存档的那份（召唤手续等由素材一栏管，不从编辑器取）。"""
        if self.model is None:
            return
        self.model["effects"] = self.editor.card()["effects"]
        self.changed.emit()

    def _preview(self, result, card_text_same):
        if result.error:
            self.text_view.setPlainText(result.error)
            self.lua_view.setPlainText("-- " + result.error)
            self.text_status.setText("")
            self.write_button.setEnabled(False)
        else:
            text = result.desc if not result.pdesc else "【灵摆效果】\n%s\n【怪兽效果】\n%s" % (result.pdesc, result.desc)
            self.text_view.setPlainText(text)
            self.lua_view.setPlainText(result.lua)
            if card_text_same:
                self.text_status.setText("√ 卡面上的效果文字就是这段")
                self.text_status.setStyleSheet("color:#2c6e2f;")
                self.write_button.setEnabled(False)
            else:
                self.text_status.setText("卡面上的效果文字和这里不同")
                self.text_status.setStyleSheet("color:#9a5a00;")
                from diy_workbench import store
                self.write_button.setEnabled(bool(store.item_count(self.model)))
        self.check_list.clear()
        if result.error:
            self._check_line("×", result.error, "#b3261e")
        for level, msg in result.issues:
            self._check_line("×" if level == "错误" else "!", msg, "#b3261e" if level == "错误" else "#9a5a00")
        if not result.error and not result.issues:
            self._check_line("√", "语义检查：没有问题", "#2c6e2f")

    def _check_line(self, mark, text, color):
        item = QListWidgetItem("%s  %s" % (mark, text))
        item.setForeground(QColor(color))
        self.check_list.addItem(item)

    def add_check_lines(self, lines):
        for mark, text in lines:
            self._check_line(mark, text, {"√": "#2c6e2f", "×": "#b3261e"}.get(mark, "#9a5a00"))
        self.tabs.setCurrentIndex(2)

    # ------------------------------------------------------------ 素材与出场限制（summon，不在积木里）

    def _materials(self, rec):
        _clear(self.material_row)
        from ygopack import cardinfo
        t = rec["type"]
        summon = self.model.get("summon") or {}
        mat = summon.get("materials") or {}
        if t & cardinfo.TYPE_XYZ:
            spin = QSpinBox()
            spin.setRange(2, 9)
            spin.setValue(int(mat.get("count", 2)))
            spin.valueChanged.connect(lambda v: self._set_materials(dict(mat, method="xyz", count=v)))
            widgets = ["素材：%d阶怪兽 ×" % (rec["level"] & 0xff), spin]
        elif t & cardinfo.TYPE_SYNCHRO:
            spin = QSpinBox()
            spin.setRange(1, 9)
            spin.setValue(int((mat.get("nontuner") or {}).get("min", 1)))
            spin.valueChanged.connect(lambda v: self._set_materials(
                dict(mat, method="synchro", tuner=mat.get("tuner") or {"count": 1},
                     nontuner=dict(mat.get("nontuner") or {}, min=v))))
            widgets = ["素材：调整＋调整以外的怪兽", spin, "只以上"]
        elif t & cardinfo.TYPE_LINK:
            spin = QSpinBox()
            spin.setRange(1, 9)
            spin.setValue(int(mat.get("min", 2)))
            effect_only = QCheckBox("只能用效果怪兽")
            effect_only.setChecked({"subtype": "effect"} in (mat.get("filter") or []))

            def save(_=None):
                filt = [f for f in mat.get("filter") or [] if f != {"subtype": "effect"}]
                if effect_only.isChecked():
                    filt.insert(0, {"subtype": "effect"})
                self._set_materials(dict(mat, method="link", min=spin.value(), filter=filt))
            spin.valueChanged.connect(save)
            effect_only.toggled.connect(save)
            widgets = ["素材：", effect_only, "怪兽", spin, "只以上"]
        elif t & cardinfo.TYPE_PENDULUM:
            widgets = ["灵摆怪兽：灵摆召唤与灵摆区域的规则自动加上（灵摆效果放在效果的「灵摆卡：写在哪一栏」）"]
        else:
            widgets = []
        if self.kind == "monster":
            chip = _button("出场限制：%s ▼" % ("、".join(self._restriction_labels()) or "无"), CHIP)
            chip.clicked.connect(self._edit_restrictions)
            widgets.append(chip)
        if not widgets:
            self.material_box.hide()
            return
        self.material_box.show()
        for w in widgets:
            self.material_row.addWidget(QLabel(w) if isinstance(w, str) else w)
        self.material_row.addStretch(1)

    def _restriction_choices(self):
        rs = (self.model.get("summon") or {}).get("restrictions", [])
        out = ["once"] if any(r.get("special_summon_once") for r in rs) else []
        return out + [r["cannot_be_material"] for r in rs if r.get("cannot_be_material")]

    def _restriction_labels(self):
        names = dict(SUMMON_RESTRICT_LABELS)
        return [names[c].replace("自己对这张卡", "") for c in self._restriction_choices() if c in names]

    def _edit_restrictions(self):
        """「自己对「X」1回合只能有1次特殊召唤」「这张卡不能作为同调素材」：卡上不编号的一行。别的出场限制原样保留。"""
        dlg = dialogs.MultiChoiceDialog("出场限制", SUMMON_RESTRICT_LABELS, self._restriction_choices(), self)
        if dlg.exec_() != QDialog.Accepted:
            return
        self.set_restrictions(dlg.value())

    def show_design(self, text, same):
        self.design_view.setPlainText(text)
        self.design_status.setText("" if not text else "√ 积木读出来的文字和设计稿相同" if same else "积木读出来的文字和设计稿不同")

    def set_restrictions(self, choices):
        summon = self.model.get("summon")
        if not isinstance(summon, dict):
            summon = self.model["summon"] = {}
        keep = [r for r in summon.get("restrictions", []) if not (r.get("special_summon_once") or r.get("cannot_be_material"))]
        new = [{"special_summon_once": "turn"} if c == "once" else {"cannot_be_material": c} for c in choices]
        if keep + new:
            summon["restrictions"] = keep + new
        else:
            summon.pop("restrictions", None)
        self.changed.emit()

    def _set_materials(self, node):
        summon = self.model.get("summon")
        if not isinstance(summon, dict):
            summon = self.model["summon"] = {}
        summon["materials"] = node
        self.changed.emit()
