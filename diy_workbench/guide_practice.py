"""用真实积木编辑器做隔离练习，只在当前教程会话中保存各题的进度。"""
from copy import deepcopy
from html import escape

from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from blocks import SCHEMA, build
from blocks.catalog import BLOCKS, new
from blocks.compile import CompileError
from .block_editor import BlockEditor


def exercises():
    return [
        ("通常魔法 · 自己抽一张", "spell", "做一张通常魔法，处理时自己从卡组抽1张。",
         new("effect", operation=[new("draw")])),
        ("通常魔法 · 支付代价并选对象", "spell", "发动时支付500基本分并取对方场上一只怪兽为对象，处理时破坏它。",
         new("effect", cost=[new("pay_lp", amount=[new("num", value=500)])],
             target=[new("take_target", source=[new("all", who="opp", where="mzone")])],
             operation=[new("destroy", cards=[new("target")])])),
        ("起动效果 · 魔力指示物", "monster", "这张怪兽每回合只能使用一次起动效果，给自己放置1个魔力指示物。",
         new("effect", type="ignition", limit="card", operation=[new("add_counter", cards=[new("this_card")])])),
        ("发动条件 · 数自己的龙族", "spell", "自己场上至少有2只龙族怪兽才能发动，自己回复500基本分。",
         new("effect", condition=[new("compare", op=">=", left=[new("count_of", cards=[
             new("all", who="you", where="mzone", filter=[new("f_race", race="dragon")])])], right=[new("num", value=2)])],
             operation=[new("recover", amount=[new("num", value=500)])])),
    ]


def outline(node):
    b = BLOCKS[node["block"]]
    lines = [f"<b>{escape(b.show(node))}</b>"]
    for slot, label, *_ in b.slots:
        children = node.get(slot, [])
        if children:
            lines.append("<ul><li>" + escape(label) + "<ul>" +
                         "".join("<li>"+outline(child)+"</li>" for child in children) + "</ul></li></ul>")
    return "".join(lines)


def next_step(want, got):
    b = BLOCKS[want["block"]]
    if not got or got["block"] != b.key:
        return "双击「%s」放入这里。" % b.label
    for name, label, kind, opt in b.fields:
        value = want[name]
        if value != got.get(name, b.defaults()[name]):
            display = dict(opt).get(value, value) if kind in ("choice", "multi") else value
            return f"点「{b.label}」，将右栏「{label}」设为「{display}」。"
    for slot, label, *_ in b.slots:
        needed, existing = want.get(slot, []), got.get(slot, [])
        for i, child in enumerate(needed):
            hint = next_step(child, existing[i] if i < len(existing) else None)
            if hint:
                return f"「{b.label} → {label}」里，{hint}"
        if len(existing) > len(needed):
            return f"检查「{b.label} → {label}」中的额外步骤，本题参考搭法在这里用{len(needed)}块。"
    return ""


class PracticePage(QWidget):
    def __init__(self):
        super().__init__()
        self.tasks = exercises()
        self.drafts = {}
        self.active_task = None
        layout = QVBoxLayout(self)
        self.choose = QComboBox()
        self.choose.setAccessibleName("选择积木练习题")
        self.choose.addItems([task[0] for task in self.tasks])
        layout.addWidget(self.choose)
        self.prompt = QLabel()
        self.prompt.setWordWrap(True)
        layout.addWidget(self.prompt)
        bar = QHBoxLayout()
        check = QPushButton("核对练习")
        self.answer = QPushButton("看搭法")
        self.answer.setCheckable(True)
        reset = QPushButton("重新练本题")
        reset.setToolTip("清空这道练习，可在练习编辑器里点撤销")
        for button in (check, self.answer, reset):
            bar.addWidget(button)
        bar.addStretch()
        layout.addLayout(bar)
        self.solution = QTextBrowser()
        self.solution.setAccessibleName("参考搭法")
        self.solution.setMaximumHeight(170)
        layout.addWidget(self.solution)
        self.solution.hide()
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.editor = BlockEditor(embedded=False)
        layout.addWidget(self.editor, 1)
        self.choose.currentIndexChanged.connect(self._choose)
        self.answer.toggled.connect(self.solution.setVisible)
        check.clicked.connect(self.check)
        reset.clicked.connect(self._reset)
        self.editor.edited.connect(self.feedback.clear)
        self._choose(0)

    def _choose(self, index):
        if self.active_task is not None:
            self.drafts[self.active_task] = self.editor.card()
        self.active_task = index
        title, kind, goal, effect = self.tasks[index]
        self.blank = {"schema": SCHEMA, "card": {"code": 100098100+index, "name": title, "kind": kind}, "effects": []}
        self.editor.load(deepcopy(self.drafts.get(index, self.blank)))
        self.prompt.setText(goal + "　这里的练习仅保存在本次程序会话中。")
        self.feedback.clear()
        self.answer.setChecked(False)
        self.solution.setHtml(outline(effect))

    def _reset(self):
        self.editor.tree.load(deepcopy(self.blank))
        self.editor.refresh()
        self.feedback.setText("已清空本题。点练习编辑器的「撤销」可以取回上一步。")

    def check(self):
        model = self.editor.card()
        expected = self.tasks[self.active_task][3]
        try:
            result = build(model)
            reference = build(dict(self.blank, effects=[expected]))
            if not result["issues"] and result["lua"] == reference["lua"]:
                self.feedback.setText("与本题参考脚本一致。预计效果为　" + reference["desc"])
                return
        except (CompileError, ValueError):
            pass
        effects = model.get("effects", [])
        hint = next_step(expected, effects[0] if effects else None)
        self.feedback.setText(hint or "你的写法与参考脚本不同。点「看搭法」对照效果数量与顺序，其他等效写法可再用实际对局验证。")
