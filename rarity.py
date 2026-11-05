"""罕贵度：前景层、额外罕贵（PSER2 / ORR）、罕贵下拉的弹出位置。

由补丁分片 p14、p15、p16 整理而来。
"""

from PyQt5.QtCore import QEvent, QObject, QPoint, QTimer, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QMenu

from common import _RARE_FRONT_Z, _widget_scene
from utils import runtime_resource_path


def _add_extra_rarity_grades(editor, extras):
    """在罕贵下拉末尾补上额外的罕贵度（PSER2 / ORR，由各编辑器 __init__ 末尾调用）。

    rare_change() 按 config.json（rare_imgs / orare_imgs）和 rd_config.json（rare_imgs）取图。
    """
    selector = getattr(editor, "rare_selector", None)
    if selector is None:
        return
    for grade in extras:
        if selector.findText(grade) < 0:
            selector.addItem(grade)
    if extras and len(extras) == 1 and extras[0] == "ORR":
        try:
            selector.setMaxVisibleItems(5)
            view = selector.view()
            row_height = view.sizeHintForRow(0)
            if row_height > 0:
                view.setMinimumHeight(row_height * 5 + 4)
                view.setMaximumHeight(row_height * 5 + 4)
        except Exception:
            pass


_OTCG_RARE_FRONT_FALLBACK = {
    "PSER2": [
        "mold/rare/official/PSER2_front.png",
        "mold/rare/official/PSER2_front.png",
        "mold/rare/official/PSER2_P_front.png",
    ],
}
_PAST_RARE_FRONT_FALLBACK = dict(_OTCG_RARE_FRONT_FALLBACK)
_RD_RARE_FRONT_FALLBACK = {
    "SR": "Rush_Duel/rare/SR.enc",
    "RR": "Rush_Duel/rare/RR.enc",
    "PSER": "Rush_Duel/rare/PSER.enc",
    "ORR": "Rush_Duel/rare/ORR_front.enc",
}


def _ensure_rare_front_layer(editor):
    """Create the transparent front rarity layer used by YGOLD 4.1."""
    if editor is None:
        return None
    reference = getattr(editor, "rare_item", None)
    if reference is None:
        return None
    scene = reference.scene() or _widget_scene(editor)
    if scene is None:
        return None
    existing = getattr(editor, "rare_front_item", None)
    if existing is not None and existing.scene() is scene:
        try:
            existing.setZValue(_RARE_FRONT_Z)
        except Exception:
            pass
        return existing
    try:
        item_class = type(reference)
        try:
            front = item_class(QPixmap(), getattr(reference, "radius", 28))
        except TypeError:
            front = item_class(QPixmap())
        front.setVisible(False)
        front.setPos(reference.pos())
        front.setOpacity(reference.opacity())
        front.setZValue(_RARE_FRONT_Z)
        if hasattr(front, "set_rounded") and hasattr(reference, "rounded"):
            front.set_rounded(bool(reference.rounded))
        elif hasattr(front, "rounded") and hasattr(reference, "rounded"):
            front.rounded = bool(reference.rounded)
        scene.addItem(front)
        editor.rare_front_item = front
        return front
    except Exception:
        return None


def _set_rare_item_pixmap(item, path, index=0, module=None):
    if item is None:
        return False
    try:
        paths = path
        if isinstance(paths, str):
            paths = [paths]
        paths = list(paths or [])
        if not paths:
            return False
        selected = paths[min(max(0, int(index)), len(paths) - 1)]
        resolved = runtime_resource_path(selected)
        pixmap = None
        decrypt = getattr(module, "decrypt_image_qpixmap", None) if module is not None else None
        if decrypt is not None and str(selected).lower().endswith(".enc"):
            pixmap = decrypt(selected)
        else:
            pixmap = QPixmap(resolved)
        if pixmap is None or pixmap.isNull():
            return False
        item.setPixmap(pixmap)
        item.setVisible(True)
        return True
    except Exception:
        return False


def _prev_apply_rare_pair(editor, image_map, front_map, grade, index=0, module=None):
    _ensure_rare_front_layer(editor)
    item = getattr(editor, "rare_item", None)
    front = getattr(editor, "rare_front_item", None)
    if str(grade) == "N":
        if item is not None:
            item.setVisible(False)
        if front is not None:
            front.setVisible(False)
        return
    image_map = image_map if isinstance(image_map, dict) else {}
    front_map = front_map if isinstance(front_map, dict) else {}
    base_ok = _set_rare_item_pixmap(item, image_map.get(grade), index, module)
    if not base_ok and item is not None:
        item.setVisible(False)
    front_ok = _set_rare_item_pixmap(front, front_map.get(grade), index, module)
    if front is not None:
        front.setVisible(bool(front_ok))
        front.setZValue(_RARE_FRONT_Z)
    if item is not None and base_ok:
        item.setZValue(max(item.zValue(), -900.0))


def _apply_otcg_rarity(self):
    """OTCGWidget.rare_change 的实现：罕贵度底图 + 前景层。"""
    current_text = self.rare_selector.currentText()
    _ensure_rare_front_layer(self)
    if current_text == "N":
        return _apply_rare_pair(self, {}, {}, current_text, 0)
    index = 0
    if getattr(self, "card_type", "") == "怪兽卡":
        if getattr(self, "detail_extra1", "") == "灵摆":
            index = 2
        elif getattr(self, "detail_call_way", "") == "连接":
            index = 1
    official = int(getattr(self, "current_template", 0) or 0) == 0
    image_map = getattr(self.config, "orare_imgs" if official else "rare_imgs", {})
    front_map = getattr(self.config, "orare_front_imgs" if official else "rare_front_imgs", None) or _OTCG_RARE_FRONT_FALLBACK
    module = __import__("OTCG_widget")
    _apply_rare_pair(self, image_map, front_map, current_text, index, module)


def _apply_past_rarity(self):
    """PastWidget.rare_change 的实现：罕贵度底图 + 前景层。"""
    current_text = self.rare_selector.currentText()
    _ensure_rare_front_layer(self)
    if current_text == "N":
        return _apply_rare_pair(self, {}, {}, current_text, 0)
    index = 0
    if getattr(self, "card_type", "") == "怪兽卡":
        if getattr(self, "detail_extra1", "") == "灵摆":
            index = 2
        elif getattr(self, "detail_call_way", "") == "连接":
            index = 1
    image_map = getattr(self.config, "orare_imgs", {})
    front_map = getattr(self.config, "orare_front_imgs", None) or _PAST_RARE_FRONT_FALLBACK
    module = __import__("Past_widget")
    _apply_rare_pair(self, image_map, front_map, current_text, index, module)


def _apply_rd_rarity(self):
    """RDWidget.rare_change 的实现：罕贵度底图 + 前景层。"""
    current_text = self.rare_selector.currentText()
    _ensure_rare_front_layer(self)
    item = getattr(self, "rare_item", None)
    front = getattr(self, "rare_front_item", None)
    if current_text == "N":
        if item is not None:
            item.setVisible(False)
        if front is not None:
            front.setVisible(False)
        return
    module = __import__("RD_widget")
    image_map = getattr(self.config, "rare_imgs", {})
    front_map = getattr(self.config, "rare_front_imgs", None) or _RD_RARE_FRONT_FALLBACK
    base_ok = _set_rare_item_pixmap(item, image_map.get(current_text), 0, module)
    front_ok = _set_rare_item_pixmap(front, front_map.get(current_text), 0, module)
    if item is not None:
        item.setVisible(bool(base_ok))
        item.setZValue(-900.0 if base_ok else item.zValue())
    if front is not None:
        front.setVisible(bool(front_ok))
        front.setZValue(_RARE_FRONT_Z)


def _apply_rare_pair(editor, image_map, front_map, grade, index=0, module=None):
    result = _prev_apply_rare_pair(editor, image_map, front_map, grade, index, module)
    item = getattr(editor, "rare_item", None)
    front = getattr(editor, "rare_front_item", None)
    if item is not None:
        item.setZValue(-980.0)
    if front is not None:
        front.setZValue(_RARE_FRONT_Z)
    _configure_otcg_layer_stack(editor)
    return result


def _combo_popup_size(combo, view):
    row_height = view.sizeHintForRow(0)
    if row_height <= 0:
        row_height = 23
    width = max(combo.width(), view.sizeHintForColumn(0) + 24, 82)
    height = row_height * max(1, combo.count()) + 8
    return int(width), int(height)


def _move_combo_popup_into_screen(combo, popup, height):
    top_left = combo.mapToGlobal(QPoint(0, 0))
    below = combo.mapToGlobal(QPoint(0, combo.height())).y()
    app = QApplication.instance()
    screen = app.screenAt(top_left) if app is not None else None
    if screen is None and app is not None:
        screen = app.primaryScreen()
    available = screen.availableGeometry() if screen is not None else None
    y = below
    if available is not None and below + height > available.bottom():
        y = max(available.top(), top_left.y() - height)
    popup.move(int(top_left.x()), int(y))


class _RarityPopupPositionFilter(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Show:
            QTimer.singleShot(0, self.position_popup)
        return False

    def position_popup(self):
        try:
            combo = self.combo
            view = combo.view()
            popup = view.window()
            width, height = _combo_popup_size(combo, view)
            popup.resize(width, height)
            _move_combo_popup_into_screen(combo, popup, height)
        except Exception:
            pass


def _ensure_rarity_popup_geometry(combo):
    try:
        view = combo.view()
        popup = view.window()
        if popup is None or not popup.isVisible():
            return
        width, height = _combo_popup_size(combo, view)
        popup.setMinimumHeight(height)
        popup.setMaximumHeight(height)
        popup.resize(width, height)
        _move_combo_popup_into_screen(combo, popup, height)
    except Exception:
        pass


class _RarityMenuOverride(QObject):
    def __init__(self, combo):
        super().__init__(combo)
        self.combo = combo

    def eventFilter(self, watched, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.show_menu()
            return True
        return False

    def show_menu(self):
        menu = QMenu(self.combo)
        for index in range(self.combo.count()):
            action = menu.addAction(self.combo.itemText(index))
            action.setCheckable(True)
            action.setChecked(index == self.combo.currentIndex())
            action.triggered.connect(lambda _checked=False, idx=index: self.choose(idx))
        menu.setMinimumWidth(max(self.combo.width(), 82))
        anchor = self.combo.mapToGlobal(QPoint(0, self.combo.height()))
        app = QApplication.instance()
        screen = app.screenAt(anchor) if app is not None else None
        if screen is None and app is not None:
            screen = app.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            size = menu.sizeHint()
            if anchor.y() + size.height() > available.bottom():
                anchor.setY(max(available.top(), self.combo.mapToGlobal(QPoint(0, 0)).y() - size.height()))
        menu.exec_(anchor)

    def choose(self, index):
        self.combo.setCurrentIndex(index)
        widget = self.combo.parentWidget()
        while widget is not None and not hasattr(widget, "rare_change"):
            widget = widget.parentWidget()
        if widget is not None:
            try:
                widget.rare_change()
            except Exception:
                pass


def _install_rarity_popup_position(combo):
    if combo is None:
        return
    try:
        view = combo.view()
        if getattr(combo, "_rarity_popup_position_filter", None) is not None:
            return
        combo.setMaxVisibleItems(5)
        if not getattr(combo, "_rarity_menu_override", None):
            combo._rarity_menu_override = _RarityMenuOverride(combo)
            combo.installEventFilter(combo._rarity_menu_override)
        popup_filter = _RarityPopupPositionFilter(combo)
        combo._rarity_popup_position_filter = popup_filter
        view.installEventFilter(popup_filter)
        popup = view.window()
        if popup is not None and popup is not view:
            popup.installEventFilter(popup_filter)
        popup_timer = QTimer(combo)
        popup_timer.timeout.connect(lambda target=combo: _ensure_rarity_popup_geometry(target))
        popup_timer.start(100)
        combo._rarity_popup_position_timer = popup_timer
    except Exception:
        pass


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from overframe import _configure_otcg_layer_stack
