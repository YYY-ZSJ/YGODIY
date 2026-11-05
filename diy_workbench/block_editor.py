"""v0.3 积木编辑器：缩进列表 + 拖拽。

左边是积木栏（按类别）；中间是积木列表：每块积木一行，积木的槽（发动条件、处理、哪些卡……）是灰色的子行，
放进槽里的积木缩进在下面。从积木栏拖进来、在列表里拖来拖去，只有类型对得上的槽才放得进；
右边改选中积木的选项；下面实时显示读出来的中文、生成的 Lua 和问题（嵌进工作台时这部分由工作台显示）。
"""

import copy
import json

from PyQt5.QtCore import QEvent, QMimeData, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush, QColor, QDrag, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QStandardItem, QStandardItemModel,
)
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHeaderView, QCompleter, QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QShortcut, QSpinBox, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from blocks import catalog
from blocks.compile import CompileError, check, compile_card
from blocks.read import read_full

ROLE = Qt.UserRole               # "block" / "slot"
ROLE_NODE = Qt.UserRole + 1      # 积木：自己的选项（不含槽）；槽：(槽名, 接受的类型, 能放几块, 只收哪些积木)
MIME_NEW = "application/x-ygodiy-block"
MIME_MOVE = "application/x-ygodiy-move"
# 每种积木一个颜色（按积木的种类，也就是槽收的那种）：(名字, 浅底, 深字, 色块)。
# 积木前面是实心色块；槽前面是空心色块，颜色就是它收的那种积木——同色的才放得进去。
KIND_STYLE = {"hat": ("效果", "#EEEDFE", "#3C3489", "#7F77DD"),
              "stmt": ("动作·控制", "#E1F5EE", "#085041", "#1D9E75"),
              "target": ("取对象", "#FCEBEB", "#791F1F", "#E24B4A"),
              "option": ("●选项", "#F1EFE8", "#444441", "#888780"),
              "cards": ("卡片", "#FAECE7", "#712B13", "#D85A30"),
              "filter": ("卡片条件", "#FBEAF0", "#72243E", "#D4537E"),
              "number": ("数值", "#FAEEDA", "#633806", "#BA7517"),
              "cond": ("条件", "#E6F1FB", "#0C447C", "#378ADD")}
CATEGORY_KIND = {"效果": "hat", "动作": "stmt", "登记效果": "stmt", "控制": "stmt", "卡片": "cards", "卡片条件": "filter",
                 "数值": "number", "条件": "cond"}
HOVER_BG = "#CFE3F7"
_ICONS = {}


def kind_icon(kind, hollow=False):
    """积木前面的实心色块 / 槽前面的空心色块。"""
    key = (kind, hollow)
    if key not in _ICONS:
        color = QColor(KIND_STYLE[kind][3])
        pix = QPixmap(14, 14)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(color, 2))
        p.setBrush(Qt.NoBrush if hollow else color)
        p.drawRoundedRect(2, 2, 10, 10, 3, 3)
        p.end()
        _ICONS[key] = QIcon(pix)
    return _ICONS[key]


def shrinkable(combo):
    """下拉框按最少几个字算宽度，长选项在弹出的列表里看全，不把面板撑宽。"""
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(8)
    return combo


def fit_popup(combo):
    """弹出的列表按最长那项展开、不省略（下拉框本身可以窄）。"""
    fm = combo.view().fontMetrics()
    widest = max([fm.horizontalAdvance(combo.itemText(i)) for i in range(combo.count())] or [0])
    combo.view().setTextElideMode(Qt.ElideNone)
    combo.view().setMinimumWidth(widest + 56)           # 留出勾选框、滚动条的地方


def captioned(combo, text_of, long_only=False):
    """框太窄看不全时：框里从开头显示，下面一行灰字完整写出选中的是什么（会折行）。
    long_only：短的不另写（「下拉里打勾」只勾一两项时）。返回 (外框, 刷新函数)。"""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(2)
    lay.addWidget(combo)
    cap = QLabel()
    cap.setWordWrap(True)
    cap.setStyleSheet("color:#666666;")
    lay.addWidget(cap)

    def update():
        text = text_of() or ""
        cap.setText(text)
        cap.setVisible(bool(text) and (not long_only or len(text) > 12))
        combo.setToolTip(text)
        if combo.isEditable():
            combo.lineEdit().setCursorPosition(0)          # 从开头显示（先看到分类和中文名）
    update()
    return box, update


def wide_tree(tree):
    """列表里的长文字不截成省略号：列宽跟着内容，太长时出现横向滚动条。"""
    tree.setTextElideMode(Qt.ElideNone)
    tree.header().setStretchLastSection(False)
    tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)


def legend_html():
    return "　".join('<span style="color:%s">■</span>&nbsp;%s' % (st[3], st[0]) for st in KIND_STYLE.values()) + \
        '　<span style="color:#888780">（空心□是槽：放同色的积木）</span>'


KIND_HINT = {"stmt": "放动作、控制", "cards": "放一块卡片", "number": "放一块数值", "cond": "放一块条件",
             "filter": "放卡片条件（几条同时满足）", "target": "放一块「取对象」", "option": "放「●选项」"}


def slot_hint(accepts, only):
    if only:
        return "放：" + "、".join(catalog.BLOCKS[k].label for k in only)
    return KIND_HINT[accepts]


def slot_fits(slot_data, key):
    """槽（ROLE_NODE 里的 4 元组）收不收积木 key。"""
    _, accepts, _, only = slot_data
    return catalog.BLOCKS[key].kind == accepts and (not only or key in only)


def _fields_of(node):
    b = catalog.BLOCKS[node["block"]]
    slots = {s[0] for s in b.slots}
    return {k: v for k, v in node.items() if k not in slots}


class Palette(QTreeWidget):
    """积木栏：拖出去就是一块新积木；双击放进选中的槽。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabel("全部积木")       # 顶上写着现在显示的是哪些（选中槽时只显示放得进去的）
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setMinimumWidth(170)           # 不让分隔条把积木栏挤成一个字宽
        wide_tree(self)
        for cat in catalog.CATEGORY_ORDER:
            top = QTreeWidgetItem([cat])
            top.setFlags(Qt.ItemIsEnabled)
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            top.setForeground(0, QBrush(QColor(KIND_STYLE[CATEGORY_KIND[cat]][2])))
            self.addTopLevelItem(top)
            for b in catalog.BLOCKS.values():
                if b.category == cat:
                    it = QTreeWidgetItem([b.label])
                    it.setData(0, ROLE_NODE, b.key)
                    _, bg, fg, _ = KIND_STYLE[b.kind]
                    it.setToolTip(0, "%s（%s）" % (b.hint or b.label, KIND_STYLE[b.kind][0]))
                    it.setIcon(0, kind_icon(b.kind))
                    it.setBackground(0, QBrush(QColor(bg)))
                    it.setForeground(0, QBrush(QColor(fg)))
                    top.addChild(it)
            top.setExpanded(True)

    def blocks(self):
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            for j in range(top.childCount()):
                yield top, top.child(j)

    def show_all(self, title="全部积木"):
        self.setHeaderLabel(title)
        for top, it in self.blocks():
            it.setHidden(False)
            top.setHidden(False)
            top.setExpanded(True)

    def focus_slot(self, slot_data, slot_label):
        """右边选中一个槽：只显示放得进去的积木，滚到第一块。"""
        first = None
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            any_fit = False
            for j in range(top.childCount()):
                it = top.child(j)
                fit = slot_fits(slot_data, it.data(0, ROLE_NODE))
                it.setHidden(not fit)
                any_fit = any_fit or fit
                if fit and first is None:
                    first = it
            top.setHidden(not any_fit)
            top.setExpanded(any_fit)
        accepts = slot_data[1]
        self.setHeaderLabel("能放进「%s」的：%s（双击放进去）" % (slot_label, KIND_STYLE[accepts][0]))
        if first is not None:
            self.setCurrentItem(first)
            self.scrollToItem(first, QAbstractItemView.PositionAtTop)
            self.horizontalScrollBar().setValue(0)        # 只竖着跳，不横着滚

    def focus_block(self, key):
        """右边选中一块积木：显示全部，跳到这块积木在积木栏里的位置。"""
        self.show_all("全部积木（选中的是「%s」）" % catalog.BLOCKS[key].label)
        for _, it in self.blocks():
            if it.data(0, ROLE_NODE) == key:
                self.setCurrentItem(it)
                self.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                self.horizontalScrollBar().setValue(0)        # 只竖着跳，不横着滚
                return

    def startDrag(self, actions):
        it = self.currentItem()
        key = it.data(0, ROLE_NODE) if it else None
        if not key:
            return
        mime = QMimeData()
        mime.setData(MIME_NEW, key.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


class BlockTree(QTreeWidget):
    """积木列表。树就是正在编辑的积木树：to_card() 读出 JSON，load() 从 JSON 重建。"""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(22)
        wide_tree(self)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.card = {"code": 100009999, "name": "新卡", "kind": "monster"}
        self.extra = {}                 # 积木以外、原样保存的部分（召唤手续 summon 等）
        self._moving = None
        self._hover = None

    # ------------------------------------------------------------ 积木树 ↔ 列表
    def load(self, card):
        self.clear()
        self.card = dict(card["card"])
        self.extra = {k: copy.deepcopy(v) for k, v in card.items() if k not in ("schema", "card", "effects")}
        for node in card.get("effects", []):
            self.addTopLevelItem(self.make_block(node))
        self.expandAll()

    def make_block(self, node):
        b = catalog.BLOCKS[node["block"]]
        it = QTreeWidgetItem()
        it.setData(0, ROLE, "block")
        it.setData(0, ROLE_NODE, _fields_of(node))
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        self.paint(it)
        for name, label, accepts, count, only in b.slots:
            slot = QTreeWidgetItem(["%s（%s）" % (label, slot_hint(accepts, only))])
            slot.setData(0, ROLE, "slot")
            slot.setData(0, ROLE_NODE, (name, accepts, count, tuple(only or ())))
            slot.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            f = slot.font(0)
            f.setItalic(True)
            slot.setFont(0, f)
            self.paint_slot(slot)
            it.addChild(slot)
            for child in node.get(name, []):
                slot.addChild(self.make_block(child))
        return it

    def paint(self, it):
        node = it.data(0, ROLE_NODE)
        b = catalog.BLOCKS[node["block"]]
        it.setText(0, b.show(node))
        _, bg, fg, _ = KIND_STYLE[b.kind]
        it.setIcon(0, kind_icon(b.kind))
        it.setBackground(0, QBrush(QColor(bg)))
        it.setForeground(0, QBrush(QColor(fg)))
        it.setToolTip(0, "%s（%s）" % (b.hint or b.label, KIND_STYLE[b.kind][0]))

    def paint_slot(self, slot):
        """槽：空心色块 + 它收的那种积木的颜色。"""
        accepts = slot.data(0, ROLE_NODE)[1]
        slot.setIcon(0, kind_icon(accepts, hollow=True))
        slot.setBackground(0, QBrush())
        slot.setForeground(0, QBrush(QColor(KIND_STYLE[accepts][3])))
        slot.setToolTip(0, "这里放「%s」积木：和这个空心色块同色的那种" % KIND_STYLE[accepts][0])

    def restyle(self, it):
        if it.data(0, ROLE) == "slot":
            self.paint_slot(it)
        else:
            self.paint(it)

    def to_node(self, it):
        node = dict(it.data(0, ROLE_NODE))
        for i in range(it.childCount()):
            slot = it.child(i)
            name = slot.data(0, ROLE_NODE)[0]
            node[name] = [self.to_node(slot.child(j)) for j in range(slot.childCount())]
        if node.get("block") == "effect" and not node.get("modes"):
            node.pop("modes", None)
        return node

    def to_card(self):
        card = {"schema": "ygodiy-blocks/0.3", "card": dict(self.card),
                "effects": [self.to_node(self.topLevelItem(i)) for i in range(self.topLevelItemCount())]}
        card.update(copy.deepcopy(self.extra))
        return card

    # ------------------------------------------------------------ 放到哪里
    def drop_place(self, pos, key, moving=None):
        """积木 key 拖到 pos 时落在哪：(槽 item 或 None=最外层, 下标)；放不进返回 None。"""
        kind = catalog.BLOCKS[key].kind
        it = self.itemAt(pos)
        if it is None:                                   # 空白处：放到最外层末尾（只有效果能放）
            return (None, self.topLevelItemCount()) if kind == "hat" else None
        if it.data(0, ROLE) == "slot":
            parent, index = it, it.childCount()
        else:
            parent = it.parent()
            rect = self.visualItemRect(it)
            index = (parent.indexOfChild(it) if parent else self.indexOfTopLevelItem(it)) + \
                (1 if pos.y() > rect.center().y() else 0)
        if parent is None:
            return (None, index) if kind == "hat" else None
        count = parent.data(0, ROLE_NODE)[2]
        if not slot_fits(parent.data(0, ROLE_NODE), key):
            return None
        others = [parent.child(i) for i in range(parent.childCount()) if parent.child(i) is not moving]
        if count == 1 and others:
            return None
        p = parent                                         # 不能拖进自己里面
        while p is not None:
            if p is moving:
                return None
            p = p.parent()
        return parent, index

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None or it.data(0, ROLE) != "block":
            return
        self._moving = it
        mime = QMimeData()
        mime.setData(MIME_MOVE, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.MoveAction)
        self._moving = None
        self._mark(None)

    def _key_of(self, event):
        mime = event.mimeData()
        if mime.hasFormat(MIME_NEW):
            return bytes(mime.data(MIME_NEW)).decode("utf-8"), None
        if mime.hasFormat(MIME_MOVE) and self._moving is not None:
            return self._moving.data(0, ROLE_NODE)["block"], self._moving
        return None, None

    def _mark(self, it):
        """拖动时标出会落进哪里（浅蓝底）。"""
        if self._hover is not None:
            try:
                self.restyle(self._hover)
            except RuntimeError:                         # 已经被删掉的行
                pass
        self._hover = it
        if it is not None:
            it.setBackground(0, QBrush(QColor(HOVER_BG)))

    def dragEnterEvent(self, event):
        key, _ = self._key_of(event)
        event.acceptProposedAction() if key else event.ignore()

    def dragMoveEvent(self, event):
        key, moving = self._key_of(event)
        place = self.drop_place(event.pos(), key, moving) if key else None
        if place is None:
            self._mark(None)
            event.ignore()
            return
        self._mark(place[0] or self.itemAt(event.pos()))
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._mark(None)

    def dropEvent(self, event):
        key, moving = self._key_of(event)
        place = self.drop_place(event.pos(), key, moving) if key else None
        self._mark(None)
        if place is None:
            event.ignore()
            return
        parent, index = place
        if moving is not None:
            old = moving.parent()
            old_index = old.indexOfChild(moving) if old else self.indexOfTopLevelItem(moving)
            if old is parent and old_index < index:
                index -= 1
            (old.takeChild(old_index) if old else self.takeTopLevelItem(old_index))
            item = moving
        else:
            item = self.make_block(catalog.new(bytes(event.mimeData().data(MIME_NEW)).decode("utf-8")))
        if parent is None:
            self.insertTopLevelItem(index, item)
        else:
            parent.insertChild(index, item)
            parent.setExpanded(True)
        item.setExpanded(True)
        self._expand(item)
        self.setCurrentItem(item)
        event.acceptProposedAction()
        self.changed.emit()

    def _expand(self, it):
        it.setExpanded(True)
        for i in range(it.childCount()):
            self._expand(it.child(i))

    def insert_new(self, key):
        """双击积木栏：放进选中的槽（选中的是积木时放在它后面）。"""
        kind = catalog.BLOCKS[key].kind
        it = self.currentItem()
        if kind == "hat" or it is None:
            if kind != "hat":
                return False
            self.addTopLevelItem(self.make_block(catalog.new(key)))
        else:
            parent = it if it.data(0, ROLE) == "slot" else it.parent()
            index = parent.childCount() if it.data(0, ROLE) == "slot" else parent.indexOfChild(it) + 1
            if parent is None or not slot_fits(parent.data(0, ROLE_NODE), key):
                return False
            count = parent.data(0, ROLE_NODE)[2]
            if count == 1 and parent.childCount():
                return False
            new = self.make_block(catalog.new(key))
            parent.insertChild(index, new)
            parent.setExpanded(True)
        self.expandAll()
        self.changed.emit()
        return True

    def remove_current(self):
        it = self.currentItem()
        if it is None or it.data(0, ROLE) != "block":
            return
        parent = it.parent()
        (parent.removeChild(it) if parent else self.takeTopLevelItem(self.indexOfTopLevelItem(it)))
        self.changed.emit()


class CheckCombo(QComboBox):
    """下拉里打勾：选项多的多选字段（时机、种族……）。点选项只切换勾选，下拉不收起；框里显示勾了哪些。"""

    picked = pyqtSignal(list)

    def __init__(self, opt, chosen, parent=None):
        super().__init__(parent)
        shrinkable(self)
        model = QStandardItemModel(self)
        for v, text in opt:
            it = QStandardItem(text)
            it.setData(v, Qt.UserRole)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setData(Qt.Checked if v in chosen else Qt.Unchecked, Qt.CheckStateRole)
            model.appendRow(it)
        self.setModel(model)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)
        self.setMaxVisibleItems(20)
        fit_popup(self)
        self.summary()

    def items(self):
        return [self.model().item(i) for i in range(self.model().rowCount())]

    def keys(self):
        return [it.data(Qt.UserRole) for it in self.items() if it.checkState() == Qt.Checked]

    def summary(self):
        text = "、".join(it.text() for it in self.items() if it.checkState() == Qt.Checked) or "（没选）"
        self.lineEdit().setText(text)
        self.lineEdit().setCursorPosition(0)
        self.setToolTip(text)

    def toggle(self, row):
        it = self.model().item(row)
        it.setCheckState(Qt.Unchecked if it.checkState() == Qt.Checked else Qt.Checked)
        if not self.keys():                      # 至少留一个
            it.setCheckState(Qt.Checked)
            return
        self.summary()
        self.picked.emit(self.keys())

    def eventFilter(self, obj, ev):
        if obj is self.lineEdit() and ev.type() == QEvent.MouseButtonPress:
            self.showPopup()
            return True
        if obj is self.view().viewport() and ev.type() == QEvent.MouseButtonRelease:
            idx = self.view().indexAt(ev.pos())
            if idx.isValid():
                self.toggle(idx.row())
            return True
        return super().eventFilter(obj, ev)

    def hidePopup(self):
        super().hidePopup()
        self.summary()


class FieldPanel(QWidget):
    """选中积木的选项。"""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.form = QFormLayout(self)
        # 窄的时候长标签放到选项上面一行，不和下拉框挤在一起
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.item = None

    def show_item(self, tree, it):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.item = it if it is not None and it.data(0, ROLE) == "block" else None
        if self.item is None:
            self.form.addRow(QLabel("选中一块积木，在这里改它的选项。"))
            return
        node = self.item.data(0, ROLE_NODE)
        b = catalog.BLOCKS[node["block"]]
        title = QLabel("<b>%s</b>" % b.label)
        self.form.addRow(title)
        if b.hint:
            hint = QLabel(b.hint)
            hint.setWordWrap(True)
            hint.setStyleSheet("color:#666666;")
            self.form.addRow(hint)
        for name, label, ftype, opt in b.fields:
            lab = QLabel(label)
            if len(label) > 8:                           # 长标签折行，不把选项挤没；短的不拆（「效果代码」）
                lab.setWordWrap(True)
                lab.setMaximumWidth(220)
            self.form.addRow(lab, self.widget(tree, name, ftype, opt, node.get(name)))

    def widget(self, tree, name, ftype, opt, value):
        if ftype == "choice":
            w = shrinkable(QComboBox())
            for v, text in opt:
                w.addItem(text, v)
            w.setCurrentIndex(max(0, w.findData(value)))
            fit_popup(w)
            w.currentIndexChanged.connect(lambda _=0, w=w: self.set(tree, name, w.currentData()))
            return w
        if ftype == "multi" and len(opt) > 12:        # 选项多（时机、种族……）：下拉里打勾
            w = CheckCombo(opt, set(catalog.multi_parts(value, dict(opt))))
            w.picked.connect(lambda keys: self.set(tree, name, "+".join(keys)))
            box, update = captioned(w, lambda: w.lineEdit().text(), long_only=True)
            w.picked.connect(lambda _keys: update())
            return box
        if ftype == "multi":                          # 可以勾几个（「手卡·墓地」「兽族·兽战士族」）
            box = QWidget()
            grid = QGridLayout(box)
            grid.setContentsMargins(0, 0, 0, 0)
            keys = dict(opt)
            chosen = set(catalog.multi_parts(value, keys))
            checks = []
            for i, (v, text) in enumerate(opt):
                cb = QCheckBox(text)
                cb.setChecked(v in chosen)
                grid.addWidget(cb, i // 4, i % 4)
                checks.append((v, cb))

            def toggled(_=False, checks=checks):
                picked = [v for v, cb in checks if cb.isChecked()]
                if not picked:                        # 至少留一个
                    checks[0][1].setChecked(True)
                    return
                self.set(tree, name, "+".join(picked))
            for _, cb in checks:
                cb.toggled.connect(toggled)
            return box
        if ftype == "code":                           # 引擎的 259 种效果代码，可以输入中文或代码名搜索
            w = shrinkable(QComboBox())
            w.setEditable(True)
            w.setMaxVisibleItems(25)
            for c in catalog.effect_codes():
                w.addItem("%s〔%s〕%s" % ("★ " if c["common"] else "", c["category"], c["zh"]) + "  " + c["name"],
                          c["name"])
            w.setCurrentIndex(max(0, w.findData(value)))
            fit_popup(w)
            comp = QCompleter(w.model(), w)
            comp.setFilterMode(Qt.MatchContains)
            comp.setCaseSensitivity(Qt.CaseInsensitive)
            w.setCompleter(comp)
            w.currentIndexChanged.connect(lambda _=0, w=w: w.currentData() and self.set(tree, name, w.currentData()))
            box, update = captioned(w, w.currentText)
            w.currentIndexChanged.connect(lambda _=0: update())
            return box
        if ftype == "lua":                            # 自定义 Lua：多行
            w = QPlainTextEdit(str(value or ""))
            w.setFont(QFont("Consolas", 10))
            w.setFixedHeight(120)
            w.textChanged.connect(lambda w=w: self.set(tree, name, w.toPlainText()))
            return w
        if ftype == "int":
            w = QSpinBox()
            w.setRange(-99999, 99999)
            w.setValue(int(value or 0))
            w.valueChanged.connect(lambda v: self.set(tree, name, v))
            return w
        w = QLineEdit(str(value or ""))
        w.textChanged.connect(lambda v: self.set(tree, name, v.strip()))
        return w

    def set(self, tree, name, value):
        node = dict(self.item.data(0, ROLE_NODE))
        node[name] = value
        self.item.setData(0, ROLE_NODE, node)
        tree.paint(self.item)
        self.changed.emit()


class BlockEditor(QWidget):
    """embedded=True：嵌进工作台，不显示自己的中文 / Lua / 问题（工作台有）；改动时发 edited。"""

    edited = pyqtSignal()

    def __init__(self, parent=None, embedded=False):
        super().__init__(parent)
        self.embedded = embedded
        self.history = []
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        for text, slot in (("删除选中的积木", lambda: self.tree.remove_current()), ("撤销", self.undo)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        self.status = QLabel()
        bar.addWidget(self.status)
        root.addLayout(bar)
        self.legend = QLabel(legend_html())          # 颜色图例：每种积木一个颜色，槽是空心的同色块
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.RichText)
        root.addWidget(self.legend)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)          # 分隔条拖不没任何一栏
        self.palette = Palette()
        self.tree = BlockTree()
        self.tree.setMinimumWidth(260)
        self.fields = FieldPanel()
        # 选项多的时候滚动，而不是把每一行压扁叠在一起
        self.field_scroll = QScrollArea()
        self.field_scroll.setWidgetResizable(True)
        self.field_scroll.setWidget(self.fields)
        self.field_scroll.setMinimumHeight(140)
        self.field_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.right = None
        self.hsplit = split
        self.wide = False
        split.addWidget(self.palette)
        if embedded:                       # 工作台右栏窄：选项放在积木列表下面
            right = QSplitter(Qt.Vertical)
            right.setChildrenCollapsible(False)
            right.addWidget(self.tree)
            right.addWidget(self.field_scroll)
            right.setSizes([300, 340])
            self.right = right
            split.addWidget(right)
            split.setSizes([180, 420])
        else:
            split.addWidget(self.tree)
            split.addWidget(self.field_scroll)
            split.setSizes([200, 520, 320])
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(split)
        self.tabs = QTabWidget()
        self.zh = QPlainTextEdit()
        self.zh.setReadOnly(True)
        self.lua = QPlainTextEdit()
        self.lua.setReadOnly(True)
        self.lua.setFont(QFont("Consolas", 10))
        self.problems = QPlainTextEdit()
        self.problems.setReadOnly(True)
        self.tabs.addTab(self.zh, "读出来的中文")
        self.tabs.addTab(self.lua, "Lua（只读）")
        self.tabs.addTab(self.problems, "问题")
        vsplit.addWidget(self.tabs)
        vsplit.setSizes([520, 200])
        if embedded:
            self.tabs.hide()
            root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(vsplit, 1)
        self.palette.itemDoubleClicked.connect(self._palette_double)
        self.tree.currentItemChanged.connect(lambda it, _: self.fields.show_item(self.tree, it))
        self.tree.currentItemChanged.connect(lambda *_: QTimer.singleShot(0, self.fit_fields))
        self.tree.currentItemChanged.connect(lambda it, _: self.sync_palette(it))
        self.tree.changed.connect(self.refresh)
        self.fields.changed.connect(self.refresh)
        QShortcut(QKeySequence.Undo, self, self.undo)
        QShortcut(QKeySequence.Delete, self.tree, self.tree.remove_current)
        self.fields.show_item(self.tree, None)

    def sync_palette(self, it):
        """右边选中什么，左边积木栏就跳到对应的积木：选中槽 → 只显示放得进去的；选中积木 → 跳到它自己。"""
        if it is None:
            self.palette.show_all()
        elif it.data(0, ROLE) == "slot":
            data = it.data(0, ROLE_NODE)
            owner = catalog.BLOCKS[it.parent().data(0, ROLE_NODE)["block"]]
            label = next((sl[1] for sl in owner.slots if sl[0] == data[0]), data[0]).split("（")[0]
            self.palette.focus_slot(data, label)
        else:
            self.palette.focus_block(it.data(0, ROLE_NODE)["block"])

    def set_wide(self, wide):
        """嵌进工作台时切换布局：宽（专注模式）= 积木栏 | 积木列表 | 选项 三栏并排；窄 = 列表在上、选项在下。"""
        if self.right is None or wide == self.wide:
            return
        self.wide = wide
        total = max(sum(self.hsplit.sizes()), 900)
        if wide:
            self.hsplit.addWidget(self.tree)            # 从上下分栏里搬出来，变成并排的第二、第三栏
            self.hsplit.addWidget(self.field_scroll)
            self.right.hide()
            self.field_scroll.setMinimumWidth(320)
            QTimer.singleShot(0, self._wide_sizes)       # 等卡图让出地方、布局刷新完再按比例分
        else:
            self.field_scroll.setMinimumWidth(0)
            self.right.addWidget(self.tree)
            self.right.addWidget(self.field_scroll)
            self.right.show()
            self.hsplit.setSizes([180, max(total - 180, 420), 0])
            QTimer.singleShot(0, self.fit_fields)

    def _wide_sizes(self):
        if not self.wide:
            return
        total = sum(self.hsplit.sizes())
        sizes = [int(total * 0.2), int(total * 0.45), int(total * 0.35)]
        self.hsplit.setSizes([sizes[0], 0, sizes[1], sizes[2]])   # 第二个是藏起来的上下分栏

    def fit_fields(self):
        """嵌进工作台时：选项面板按选项要的高度尽量完整展开，积木列表至少留一段。"""
        if self.right is None or self.wide:            # 三栏并排时选项本来就占满一栏高
            return
        total = sum(self.right.sizes())
        if total <= 0:
            return
        self.fields.adjustSize()
        need = self.fields.sizeHint().height() + 2 * self.field_scroll.frameWidth() + 4
        tree_min = 150
        f = max(self.field_scroll.minimumHeight(), min(need, total - tree_min))
        self.right.setSizes([total - f, f])
        if self.tree.currentItem() is not None:          # 列表变矮了：选中的积木留在看得见的地方
            self.tree.scrollToItem(self.tree.currentItem(), QAbstractItemView.PositionAtTop)

    def _palette_double(self, it, _col):
        key = it.data(0, ROLE_NODE)
        if key and not self.tree.insert_new(key):
            self.status.setText("放不进去：先选中一个类型对得上的槽")

    def load(self, card):
        self.tree.load(card)
        self.history = [json.dumps(card, ensure_ascii=False)]
        self.refresh(record=False)

    def undo(self):
        if len(self.history) > 1:
            self.history.pop()
            self.tree.load(json.loads(self.history[-1]))
            self.refresh(record=False)
            self.edited.emit()

    def card(self):
        return self.tree.to_card()

    def refresh(self, record=True):
        card = self.card()
        if record:
            self.history.append(json.dumps(card, ensure_ascii=False))
            self.edited.emit()
        if self.embedded:
            return
        desc, pdesc = read_full(card)
        self.zh.setPlainText(desc + ("\n\n【灵摆效果】\n" + pdesc if pdesc else ""))
        problems = check(card)
        try:
            self.lua.setPlainText(compile_card(copy.deepcopy(card)))
        except CompileError as ex:
            self.lua.setPlainText("-- 还拼不完整：%s" % ex)
            problems.append(str(ex))
        except Exception as ex:                      # 原型：翻译器还不认识的组合
            self.lua.setPlainText("-- 翻译失败：%r" % ex)
            problems.append("翻译失败：%r" % ex)
        self.problems.setPlainText("\n".join(problems) or "没有问题")
        self.status.setText("√ 能生成 Lua" if not problems else "还有 %d 个问题（见「问题」）" % len(problems))
