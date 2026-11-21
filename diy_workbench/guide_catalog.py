"""将手写讲解与编辑器真实的参数、槽位和默认值组合为离线图鉴。"""
from html import escape
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from blocks.catalog import BLOCKS, CATEGORY_ORDER, effect_codes, new
from .block_editor import KIND_STYLE, slot_fits
from .guide_art import GuideReader

FOLDER = Path(__file__).with_name("handbook")
START_SLOTS = {
    "stmt": ("effect", "operation"), "cond": ("effect", "condition"), "cards": ("destroy", "cards"),
    "number": ("recover", "amount"), "filter": ("all", "filter"), "target": ("effect", "target"),
    "ls_stmt": ("ls_function", "body"), "ls_expr": ("ls_local", "values"),
    "ls_branch": ("ls_if", "branches"), "ls_field": ("ls_table", "fields"), "ls_hint": ("ls_program", "hints"),
}
SPECIAL_SLOTS = {
    "pay_lp": ("effect", "cost"), "option": ("choose", "options"), "effect_mode": ("effect", "modes"),
    "ls_function": ("ls_program", "body"), "ls_break": ("ls_while", "body"),
}


def read_notes():
    notes = {}
    for file in sorted(FOLDER.glob("积木-*.txt")):
        for line in file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                key, purpose, example, recovery = line.split("|")
                notes[key] = (purpose, example, recovery)
    return notes


def slot_options(block, index):
    name, _, accepts, count, only = block.slots[index]
    return [key for key in BLOCKS if slot_fits((name, accepts, count, only), key)]


def block_link(key):
    return f'<a href="block:{key}">{escape(BLOCKS[key].label)}</a>'


def position(block):
    if block.kind == "hat":
        return "在中栏最外层放置。整卡脚本独占顶层，普通中文效果可在一张卡上放多条。"
    if block.key == "each":
        return "先放「对每一张」，再在它的「做」里放一个需要卡片的动作，把本块接进那个动作的卡片槽。"
    if block.key == "f_activated_effect":
        return "在永续抗性选「不受效果影响」的效果代码，将本块放进「数值：只对这样的卡成立」槽。"
    if block.category == "对局引擎调用":
        return "用它执行操作时，放进「执行函数或对局操作」的调用槽。要使用返回的结果时，放进变量的值、判断或其他调用的参数槽。"
    parent, name = SPECIAL_SLOTS.get(block.key) or START_SLOTS[block.kind]
    slot = next(s for s in BLOCKS[parent].slots if s[0] == name)
    return f'在{block_link(parent)}里点「{escape(slot[1])}」槽，再从左栏双击本块。'


def parameter(field, default, expanded):
    name, label, kind, options = field
    if kind == "code":
        options = [(r["name"], r["zh"]) for r in effect_codes()]
    if kind in ("choice", "multi", "code"):
        mapping = dict(options)
        initial = mapping.get(default, str(default))
        action = "勾选所需项目" if kind == "multi" else "从列表选择一项"
        labels = [v for _, v in options]
        shown = labels if expanded else labels[:6]
        more = f" 等{len(labels)}项" if len(shown) < len(labels) else ""
        detail = f"{action}。初始为「{initial}」。可选{'、'.join(shown)}{more}。"
    else:
        action = {"int": "输入整数", "text": "填写文字或编号", "counter": "选指示物或填写编号",
                  "lua": "填写多行文字或代码，按此栏名称操作"}[kind]
        initial = str(default) if default not in (None, "") else "空白"
        detail = f"{action}。初始为「{initial}」。"
    return f"<li><b>{escape(label)}</b>　{escape(detail)}</li>"


def article(key, notes, expanded=False):
    block = BLOCKS[key]
    purpose, example, recovery = notes[key]
    parts = [f"<h2>{escape(block.label)}</h2><p>{escape(purpose)}</p>",
             f'<p><img src="diagram:{key}" alt="本块及其槽或选项的缩进图"></p>',
             f"<p><b>从哪里放进去</b>　{position(block)}</p>",
             f"<h3>跟着搭一次</h3><p>{escape(example)}</p>"]
    if block.fields:
        defaults = new(key)
        parts.append("<h3>右栏怎么填</h3><ul>" + "".join(
            parameter(f, defaults[f[0]], expanded) for f in block.fields) + "</ul>")
    if block.slots:
        rows = []
        for i, (_, label, accepts, count, _) in enumerate(block.slots):
            limit = "最多一块" if count == 1 else "可放多块"
            rows.append(f'<li><b>{escape(label)}</b>　{KIND_STYLE[accepts][0]}，{limit}。'
                        f'<a href="slot:{key}/{i}">查看能放入此槽的积木</a></li>')
        parts.append("<h3>中栏可以接什么</h3><ul>" + "".join(rows) + "</ul>")
    parts.append(f"<h3>怎样知道做对了</h3><p>{escape(recovery)}</p>")
    if block.hint:
        parts.append(f"<p><b>引擎对照</b>　{escape(block.hint)}</p>")
    return "".join(parts)


class CatalogPage(QWidget):
    def __init__(self):
        super().__init__()
        self.notes = read_notes()
        self.slot_filter = None
        self.search_index = {}
        for key, block in BLOCKS.items():
            words = [block.label, key, block.category, block.hint, *self.notes[key]]
            words.extend(f[1] for f in block.fields)
            words.extend(s[1] for s in block.slots)
            self.search_index[key] = " ".join(words).casefold()

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("找积木，例如 抽卡、取对象、Duel.Draw")
        self.search.setAccessibleName("在积木图鉴中搜索")
        self.search.setClearButtonEnabled(True)
        self.category = QComboBox()
        self.category.setAccessibleName("积木类别")
        self.category.addItems(["全部类别", *CATEGORY_ORDER])
        row.addWidget(self.search, 1)
        row.addWidget(self.category)
        layout.addLayout(row)
        line = QHBoxLayout()
        self.count = QLabel()
        self.count.setWordWrap(True)
        self.back = QPushButton("返回上一个积木")
        self.back.hide()
        self.history = []
        self.back.clicked.connect(self._back)
        line.addWidget(self.count, 1)
        line.addWidget(self.back)
        layout.addLayout(line)

        self.list = QListWidget()
        self.list.setAccessibleName("积木搜索结果")
        self.reader = GuideReader()
        self.reader.setAccessibleName("逐块说明")
        self.reader.setOpenLinks(False)
        self.reader.setOpenExternalLinks(False)
        self.reader.anchorClicked.connect(self._link)
        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.list)
        self.split.addWidget(self.reader)
        self.split.setChildrenCollapsible(False)
        self.split.setStretchFactor(1, 1)
        self.split.setSizes([220, 590])
        layout.addWidget(self.split, 1)
        self.full = QCheckBox("显示右栏全部可选值")
        layout.addWidget(self.full)
        self.search.textChanged.connect(self._filter)
        self.category.currentIndexChanged.connect(self._filter)
        self.list.currentItemChanged.connect(self._display)
        self.full.toggled.connect(self._display)
        self._filter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        orientation = Qt.Vertical if self.width() < 620 else Qt.Horizontal
        if orientation != self.split.orientation():
            self.split.setOrientation(orientation)
            self.split.setSizes([105, 440] if orientation == Qt.Vertical else [220, 590])

    def _filter(self, *_):
        words = self.search.text().casefold().split()
        category = self.category.currentText() if self.category.currentIndex() > 0 else ""
        candidates = BLOCKS if not self.slot_filter else slot_options(BLOCKS[self.slot_filter[0]], self.slot_filter[1])
        matches = [key for key in candidates if (not category or BLOCKS[key].category == category)
                   and all(w in self.search_index[key] for w in words)]
        if words:
            matches.sort(key=lambda k: not all(w in (BLOCKS[k].label+" "+k+" "+BLOCKS[k].hint).casefold() for w in words))
        self.list.blockSignals(True)
        self.list.clear()
        for key in matches:
            b = BLOCKS[key]
            item = QListWidgetItem(f"{b.label}  ·  {b.category}")
            item.setData(Qt.UserRole, key)
            self.list.addItem(item)
        self.list.blockSignals(False)
        scope = ""
        if self.slot_filter:
            parent, i = self.slot_filter
            scope = BLOCKS[parent].label + " / " + BLOCKS[parent].slots[i][1] + "　"
        self.count.setText(f"{scope}找到 {len(matches)} 种积木")
        if matches:
            self.list.setCurrentRow(0)
        else:
            self.reader.lesson("没有找到匹配的积木。清空搜索词或切换到全部类别，再试「抽卡」「破坏」等动作。若正在查某个槽，可返回上一个积木。", FOLDER)

    def _display(self, *_):
        item = self.list.currentItem()
        if item:
            key = item.data(Qt.UserRole)
            self.reader.entry(article(key, self.notes, self.full.isChecked()), BLOCKS[key])

    def _reset(self, slot=None):
        self.slot_filter = slot
        self.search.blockSignals(True)
        self.category.blockSignals(True)
        self.search.clear()
        self.category.setCurrentIndex(0)
        self.search.blockSignals(False)
        self.category.blockSignals(False)
        self._filter()

    def show_block(self, key):
        self._reset()
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == key:
                self.list.setCurrentRow(row)
                break

    def _link(self, link):
        item = self.list.currentItem()
        if not item:
            return
        self.history.append(item.data(Qt.UserRole))
        self.back.show()
        if link.scheme() == "block":
            self.show_block(link.path())
        elif link.scheme() == "slot":
            key, number = link.path().split("/")
            self._reset((key, int(number)))

    def _back(self):
        if self.history:
            self.show_block(self.history.pop())
        self.back.setVisible(bool(self.history))
