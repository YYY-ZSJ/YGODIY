"""自定义防伪与版权：下拉里可增删改名的自定义项。

由补丁分片 p16、p17、p18 整理而来。
"""

import base64
import copy
import inspect
import io
import os
import traceback

from PIL import Image
from PyQt5.QtCore import QEvent, QObject, QTimer, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QPixmap
from PyQt5.QtWidgets import QFileDialog, QGraphicsPixmapItem, QInputDialog, QLineEdit, QMenu, QMessageBox

from common import _safe_call, _tab_log, _toggle_checked, _widget_scene


_CUSTOM_OPTION_TEXT = "自定义"
_CUSTOM_HOLO_ATTR = "_ygodiy_custom_holo_image"
_CUSTOM_COPY_ATTR = "_ygodiy_custom_copyright_text"
_CUSTOM_HOLO_ITEMS_ATTR = "_ygodiy_custom_holo_items"
_CUSTOM_COPY_ITEMS_ATTR = "_ygodiy_custom_copyright_items"
_CUSTOM_HOLO_ACTIVE_ATTR = "_ygodiy_custom_holo_active"
_CUSTOM_COPY_ACTIVE_ATTR = "_ygodiy_custom_copyright_active"
_CUSTOM_ITEM_ROLE_PREFIX = "ygodiy-custom-item:"
_CUSTOM_ACTION_ROLE = "ygodiy-custom-action"

_CUSTOM_CONFIG = {
    "holo": {
        "selector": "holo_selector",
        "items_attr": _CUSTOM_HOLO_ITEMS_ATTR,
        "active_attr": _CUSTOM_HOLO_ACTIVE_ATTR,
        "value_attr": _CUSTOM_HOLO_ATTR,
        "value_key": "image",
        "legacy_value": "custom_holo_image",
        "legacy_name": "custom_holo_name",
        "last_index_attr": "_ygodiy_last_holo_combo_index",
        "toggle": "toggle_holo",
        "label": "防伪",
    },
    "copyright": {
        "selector": "copyright_selector",
        "items_attr": _CUSTOM_COPY_ITEMS_ATTR,
        "active_attr": _CUSTOM_COPY_ACTIVE_ATTR,
        "value_attr": _CUSTOM_COPY_ATTR,
        "value_key": "text",
        "legacy_value": "custom_copyright_text",
        "legacy_name": "custom_copyright_name",
        "last_index_attr": "_ygodiy_last_copyright_combo_index",
        "toggle": "toggle_copy",
        "label": "版权",
    },
}


def _customization_log(message):
    try:
        _tab_log(str(message))
    except Exception:
        pass


def _custom_config(kind):
    return _CUSTOM_CONFIG["holo" if kind == "holo" else "copyright"]


def _custom_selector(editor, kind):
    return getattr(editor, _custom_config(kind)["selector"], None)


def _combo_role(selector, index):
    if selector is None or index < 0:
        return ""
    try:
        value = selector.itemData(index, Qt.UserRole)
    except Exception:
        return ""
    return str(value or "")


def _custom_item_id_from_role(role):
    value = str(role or "")
    if value.startswith(_CUSTOM_ITEM_ROLE_PREFIX):
        return value[len(_CUSTOM_ITEM_ROLE_PREFIX) :]
    return ""


def _selected_custom_item_id(editor, kind):
    selector = _custom_selector(editor, kind)
    if selector is None:
        return ""
    return _custom_item_id_from_role(_combo_role(selector, selector.currentIndex()))


def _custom_items(editor, kind):
    config = _custom_config(kind)
    value = getattr(editor, config["items_attr"], None)
    return value if isinstance(value, list) else []


def _normalize_custom_items(editor, kind):
    config = _custom_config(kind)
    raw_items = getattr(editor, config["items_attr"], None)
    items = []
    seen_ids = set()
    seen_names = set()
    if isinstance(raw_items, list):
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            value_key = config["value_key"]
            value = str(raw.get(value_key, "") or "")
            if not value:
                continue
            item_id = str(raw.get("id", "") or os.urandom(8).hex())
            if item_id in seen_ids:
                item_id = os.urandom(8).hex()
            if kind == "holo":
                fallback_name = "防伪图片"
            else:
                fallback_name = value[:120] or "自定义项目"
            name = str(raw.get("name", "") or fallback_name).strip()
            if not name or name == _CUSTOM_OPTION_TEXT or name in seen_names:
                base = name or "自定义项目"
                candidate = base
                suffix = 2
                while (
                    candidate == _CUSTOM_OPTION_TEXT or candidate in seen_names
                ):
                    candidate = f"{base} ({suffix})"
                    suffix += 1
                name = candidate
            item = dict(raw)
            item["id"] = item_id
            item["name"] = name
            item[value_key] = value
            items.append(item)
            seen_ids.add(item_id)
            seen_names.add(name)
    setattr(editor, config["items_attr"], items)
    return items


def _custom_item_by_id(editor, kind, item_id):
    for item in _custom_items(editor, kind):
        if str(item.get("id", "")) == str(item_id):
            return item
    return None


def _selected_custom_item(editor, kind):
    return _custom_item_by_id(
        editor,
        kind,
        _selected_custom_item_id(editor, kind),
    )


def _unique_custom_name(editor, kind, desired_name, exclude_id=""):
    base = str(desired_name or "").strip() or "自定义项目"
    names = {
        str(item.get("name", ""))
        for item in _custom_items(editor, kind)
        if str(item.get("id", "")) != str(exclude_id or "")
    }
    candidate = base
    suffix = 2
    while candidate == _CUSTOM_OPTION_TEXT or candidate in names:
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def _set_combo_index_blocked(selector, index):
    if selector is None:
        return
    try:
        index = int(index)
    except Exception:
        return
    if index < 0 or index >= selector.count():
        return
    try:
        selector.blockSignals(True)
        selector.setCurrentIndex(index)
    finally:
        try:
            selector.blockSignals(False)
        except Exception:
            pass


def _standard_combo_entries(selector):
    entries = []
    if selector is None:
        return entries
    for index in range(selector.count()):
        role = _combo_role(selector, index)
        if role == _CUSTOM_ACTION_ROLE or _custom_item_id_from_role(role):
            continue
        entries.append(
            {
                "text": selector.itemText(index),
                "icon": selector.itemIcon(index),
                "data": selector.itemData(index, Qt.UserRole),
            }
        )
    return entries


def _custom_item_combo_index(selector, item_id):
    if selector is None:
        return -1
    wanted = _CUSTOM_ITEM_ROLE_PREFIX + str(item_id or "")
    for index in range(selector.count()):
        if _combo_role(selector, index) == wanted:
            return index
    return -1


def _rebuild_custom_combo(
    editor,
    kind,
    select_id="",
    fallback_index=0,
):
    selector = _custom_selector(editor, kind)
    if selector is None:
        return
    old_index = selector.currentIndex()
    old_id = _selected_custom_item_id(editor, kind)
    entries = _standard_combo_entries(selector)
    custom_items = _normalize_custom_items(editor, kind)
    try:
        selector.blockSignals(True)
        selector.clear()
        for entry in entries:
            icon = entry.get("icon")
            text = str(entry.get("text", "") or "")
            if icon is not None and not icon.isNull():
                selector.addItem(icon, text)
            else:
                selector.addItem(text)
            data = entry.get("data")
            if data is not None:
                selector.setItemData(selector.count() - 1, data, Qt.UserRole)
        for item in custom_items:
            selector.addItem(str(item.get("name", "") or "自定义项目"))
            selector.setItemData(
                selector.count() - 1,
                _CUSTOM_ITEM_ROLE_PREFIX + str(item.get("id", "")),
                Qt.UserRole,
            )
        selector.addItem(_CUSTOM_OPTION_TEXT)
        selector.setItemData(
            selector.count() - 1,
            _CUSTOM_ACTION_ROLE,
            Qt.UserRole,
        )
        target_index = -1
        if select_id:
            target_index = _custom_item_combo_index(selector, select_id)
        if target_index < 0 and old_id:
            target_index = _custom_item_combo_index(selector, old_id)
        if target_index < 0:
            try:
                target_index = int(fallback_index)
            except Exception:
                target_index = 0
        if target_index < 0 or target_index >= selector.count():
            target_index = max(0, min(old_index, selector.count() - 1))
        selector.setCurrentIndex(target_index)
    finally:
        try:
            selector.blockSignals(False)
        except Exception:
            pass


def _activate_combo_selection(editor, kind, notify=False):
    config = _custom_config(kind)
    selected_id = _selected_custom_item_id(editor, kind)
    item = _custom_item_by_id(editor, kind, selected_id)
    if item is None:
        setattr(editor, config["active_attr"], "")
        setattr(editor, config["value_attr"], "")
    else:
        setattr(editor, config["active_attr"], selected_id)
        setattr(
            editor,
            config["value_attr"],
            str(item.get(config["value_key"], "") or ""),
        )
    _apply_custom_overlays(editor)
    if notify:
        _mirror_customization_to_otcg(editor)
        _notify_customization_changed(editor)


def _select_custom_item(editor, kind, item_id, notify=True):
    selector = _custom_selector(editor, kind)
    index = _custom_item_combo_index(selector, item_id)
    if index < 0:
        return False
    _set_combo_index_blocked(selector, index)
    _activate_combo_selection(editor, kind, notify=notify)
    return True


def _restore_custom_selection(editor, kind, fallback_index=None):
    config = _custom_config(kind)
    selector = _custom_selector(editor, kind)
    if selector is None:
        return
    if fallback_index is None:
        fallback_index = getattr(editor, config["last_index_attr"], 0)
    try:
        fallback_index = int(fallback_index)
    except Exception:
        fallback_index = 0
    if fallback_index < 0 or fallback_index >= selector.count():
        active_index = _custom_item_combo_index(
            selector,
            getattr(editor, config["active_attr"], ""),
        )
        fallback_index = active_index if active_index >= 0 else 0
    _set_combo_index_blocked(selector, fallback_index)
    _activate_combo_selection(editor, kind, notify=False)


def _custom_item_scene(editor):
    for name in ("holo_item", "copyright_item", "base_item", "card_img_item"):
        item = getattr(editor, name, None)
        if item is None:
            continue
        try:
            scene = item.scene()
        except Exception:
            scene = None
        if scene is not None:
            return scene
    return _widget_scene(editor)


def _custom_toggle_enabled(editor, name):
    return _toggle_checked(getattr(editor, name, None), True)


def _ensure_custom_graphics(editor):
    if editor is None:
        return None, None
    holo_item = getattr(editor, "_ygodiy_custom_holo_item", None)
    copy_item = getattr(editor, "_ygodiy_custom_copyright_item", None)
    if holo_item is not None and copy_item is not None:
        try:
            if holo_item.scene() is not None and copy_item.scene() is not None:
                return holo_item, copy_item
        except Exception:
            pass
    scene = _custom_item_scene(editor)
    if scene is None:
        return None, None
    try:
        from PyQt5.QtWidgets import QGraphicsSimpleTextItem
    except Exception:
        return None, None

    def ensure(attr_name, factory):
        item = getattr(editor, attr_name, None)
        old_scene = None
        if item is not None:
            try:
                old_scene = item.scene()
            except Exception:
                old_scene = None
        if item is not None and old_scene is scene:
            return item
        if item is not None and old_scene is not None:
            try:
                old_scene.removeItem(item)
            except Exception:
                pass
        item = factory()
        try:
            item.setAcceptedMouseButtons(Qt.NoButton)
        except Exception:
            pass
        item.setVisible(False)
        scene.addItem(item)
        setattr(editor, attr_name, item)
        return item

    holo_item = ensure("_ygodiy_custom_holo_item", QGraphicsPixmapItem)
    copy_item = ensure("_ygodiy_custom_copyright_item", QGraphicsSimpleTextItem)
    if copy_item is not None:
        try:
            copy_item.setBrush(QBrush(QColor(0, 0, 0)))
            copy_item.setFont(QFont("Microsoft YaHei", 28))
        except Exception:
            pass
    return holo_item, copy_item


def _apply_custom_holo(editor):
    if editor is None:
        return
    selected = _selected_custom_item(editor, "holo")
    custom_item = getattr(editor, "_ygodiy_custom_holo_item", None)
    reference = getattr(editor, "holo_item", None)
    if selected is None:
        if custom_item is not None:
            try:
                custom_item.setVisible(False)
            except Exception:
                pass
        if reference is not None:
            try:
                reference.setVisible(
                    _toggle_checked(getattr(editor, "toggle_holo", None), True)
                )
            except Exception:
                pass
        return

    custom_item, _ = _ensure_custom_graphics(editor)
    if custom_item is None:
        return
    if reference is not None:
        try:
            reference.setVisible(False)
        except Exception:
            pass
    encoded = str(selected.get("image", "") or "")
    if not encoded or not _custom_toggle_enabled(editor, "toggle_holo"):
        custom_item.setVisible(False)
        return
    try:
        pixmap = QPixmap()
        if not pixmap.loadFromData(base64.b64decode(encoded), "PNG") or pixmap.isNull():
            custom_item.setVisible(False)
            return
        if reference is not None:
            target = max(24, int(round(reference.boundingRect().width() or 84)))
            target_height = max(
                24,
                int(round(reference.boundingRect().height() or target)),
            )
            fitted = pixmap.scaled(
                target,
                target_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            base_x = float(reference.pos().x())
            base_y = float(reference.pos().y())
            custom_item.setPos(
                base_x + (target - fitted.width()) / 2.0,
                base_y + (target_height - fitted.height()) / 2.0,
            )
            custom_item.setZValue(float(reference.zValue()) + 1.0)
        else:
            custom_item.setPos(0.0, 0.0)
            custom_item.setZValue(1000.0)
            fitted = pixmap
        custom_item.setPixmap(fitted)
        custom_item.setVisible(True)
    except Exception:
        custom_item.setVisible(False)


def _apply_custom_copyright(editor):
    if editor is None:
        return
    selected = _selected_custom_item(editor, "copyright")
    custom_item = getattr(editor, "_ygodiy_custom_copyright_item", None)
    reference = getattr(editor, "copyright_item", None)
    if selected is None:
        if custom_item is not None:
            try:
                custom_item.setVisible(False)
            except Exception:
                pass
        if reference is not None:
            try:
                reference.setVisible(
                    _toggle_checked(getattr(editor, "toggle_copy", None), True)
                )
            except Exception:
                pass
        return

    _, custom_item = _ensure_custom_graphics(editor)
    if custom_item is None:
        return
    if reference is not None:
        try:
            reference.setVisible(False)
        except Exception:
            pass
    text = str(selected.get("text", "") or "").strip()
    if not text or not _custom_toggle_enabled(editor, "toggle_copy"):
        custom_item.setVisible(False)
        return
    try:
        font_size = 28
        if reference is not None:
            font_size = max(
                18,
                min(42, int(round(reference.boundingRect().height() * 0.85))),
            )
        custom_item.setFont(QFont("Microsoft YaHei", font_size))
        custom_item.setText(text)
        custom_item.setBrush(QBrush(QColor(0, 0, 0)))
        custom_item.setScale(1.0)
        bounds = custom_item.boundingRect()
        if reference is not None:
            reference_width = max(
                1.0,
                float(reference.boundingRect().width())
                * max(0.01, float(reference.scale() or 1.0)),
            )
            base_item = getattr(editor, "base_item", None)
            base_width = (
                float(base_item.boundingRect().width())
                if base_item is not None
                else 1626.0
            )
            target_width = max(520.0, min(base_width - 140.0, reference_width * 1.18))
            scale = min(1.0, target_width / max(1.0, bounds.width()))
            custom_item.setScale(scale)
            center_x = (
                float(reference.pos().x())
                + float(reference.boundingRect().width())
                * max(0.01, float(reference.scale() or 1.0))
                / 2.0
            )
            center_y = (
                float(reference.pos().y())
                + float(reference.boundingRect().height())
                * max(0.01, float(reference.scale() or 1.0))
                / 2.0
            )
        else:
            custom_item.setScale(1.0)
            center_x = 813.0
            center_y = 2280.0
        custom_item.setPos(
            center_x - bounds.width() * custom_item.scale() / 2.0,
            center_y - bounds.height() * custom_item.scale() / 2.0,
        )
        if reference is not None:
            custom_item.setZValue(float(reference.zValue()) + 1.0)
        else:
            custom_item.setZValue(1000.0)
        custom_item.setVisible(True)
    except Exception:
        custom_item.setVisible(False)


def _apply_custom_overlays(editor):
    if editor is None:
        return
    try:
        _apply_custom_holo(editor)
    except Exception:
        pass
    try:
        _apply_custom_copyright(editor)
    except Exception:
        pass


def _notify_customization_changed(editor):
    def notify():
        try:
            app = getattr(editor, "parent_app", None)
            manager = getattr(app, "card_tab_manager", None)
            if manager is None:
                return
            _safe_call(getattr(manager, "_save_current_snapshot", None), full=False)
            _safe_call(getattr(manager, "_request_write_state", None))
        except Exception:
            pass

    QTimer.singleShot(0, notify)


def _add_custom_holo_item(editor, path):
    if editor is None or not path:
        return False
    try:
        with Image.open(path) as source:
            image = source.convert("RGBA")
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        name = _unique_custom_name(
            editor,
            "holo",
            os.path.basename(str(path)) or "防伪图片",
        )
        item_id = os.urandom(8).hex()
        item = {
            "id": item_id,
            "name": name,
            "image": encoded,
        }
        _custom_items(editor, "holo").append(item)
        _rebuild_custom_combo(editor, "holo", select_id=item_id)
        _select_custom_item(editor, "holo", item_id, notify=True)
        return True
    except Exception:
        _customization_log("读取自定义防伪图标失败:\n" + traceback.format_exc())
        return False


def _add_custom_copyright_item(editor, text):
    if editor is None:
        return False
    value = str(text or "").strip()
    if not value:
        return False
    name = _unique_custom_name(editor, "copyright", value)
    item_id = os.urandom(8).hex()
    item = {
        "id": item_id,
        "name": name,
        "text": value,
    }
    _custom_items(editor, "copyright").append(item)
    _rebuild_custom_combo(editor, "copyright", select_id=item_id)
    _select_custom_item(editor, "copyright", item_id, notify=True)
    return True


def _prompt_custom_holo(editor, fallback_index=None):
    if editor is None:
        return
    path, _selected = QFileDialog.getOpenFileName(
        editor,
        "选择防伪图标",
        "",
        "图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico)",
    )
    if path:
        if not _add_custom_holo_item(editor, path):
            QMessageBox.warning(editor, "自定义防伪", "无法读取该图片，请换一张图片重试。")
            _restore_custom_selection(editor, "holo", fallback_index)
        return
    _restore_custom_selection(editor, "holo", fallback_index)


def _prompt_custom_copyright(editor, fallback_index=None):
    if editor is None:
        return
    text, accepted = QInputDialog.getText(
        editor,
        "自定义版权文字",
        "版权文字（可包含 ©、作者或工作室名称）：",
        QLineEdit.Normal,
        "",
    )
    if accepted:
        if _add_custom_copyright_item(editor, text):
            return
        QMessageBox.information(editor, "自定义版权", "版权文字不能为空。")
    _restore_custom_selection(editor, "copyright", fallback_index)


def _rename_custom_item(editor, kind, item_id, new_name):
    item = _custom_item_by_id(editor, kind, item_id)
    if item is None:
        return False
    new_name = str(new_name or "").strip()
    if not new_name:
        return False
    duplicate = any(
        str(other.get("id", "")) != str(item_id)
        and str(other.get("name", "")) == new_name
        for other in _custom_items(editor, kind)
    )
    if new_name == _CUSTOM_OPTION_TEXT or duplicate:
        return False
    item["name"] = new_name
    if kind == "copyright":
        item["text"] = new_name
    _rebuild_custom_combo(editor, kind, select_id=item_id)
    _activate_combo_selection(editor, kind, notify=True)
    return True


def _delete_custom_item(editor, kind, item_id):
    config = _custom_config(kind)
    item = _custom_item_by_id(editor, kind, item_id)
    if item is None:
        return False
    was_active = str(getattr(editor, config["active_attr"], "")) == str(item_id)
    current_id = _selected_custom_item_id(editor, kind)
    try:
        _custom_items(editor, kind).remove(item)
    except ValueError:
        return False
    if was_active:
        setattr(editor, config["active_attr"], "")
        _rebuild_custom_combo(editor, kind, fallback_index=0)
        _activate_combo_selection(editor, kind, notify=True)
    else:
        _rebuild_custom_combo(editor, kind, select_id=current_id)
        _activate_combo_selection(editor, kind, notify=True)
    return True


def _show_custom_combo_menu(editor, kind, view, position):
    config = _custom_config(kind)
    selector = _custom_selector(editor, kind)
    if selector is None or view is None:
        return
    index = view.indexAt(position)
    item_id = _custom_item_id_from_role(_combo_role(selector, index.row()))
    item = _custom_item_by_id(editor, kind, item_id)
    if item is None:
        return
    menu = QMenu(view)
    rename_action = menu.addAction("改名")
    delete_action = menu.addAction("删除")
    chosen = menu.exec_(view.viewport().mapToGlobal(position))
    try:
        selector.hidePopup()
    except Exception:
        pass
    if chosen is rename_action:
        new_name, accepted = QInputDialog.getText(
            view,
            f"{config['label']}改名",
            "名称：",
            QLineEdit.Normal,
            str(item.get("name", "") or ""),
        )
        if not accepted:
            return
        if not _rename_custom_item(editor, kind, item_id, new_name):
            QMessageBox.warning(view, "改名", "名称不能为空或与已有项目重复。")
        return
    if chosen is not delete_action:
        return
    answer = QMessageBox.question(
        view,
        "删除自定义项目",
        f"确定删除“{item.get('name', '')}”吗？",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer != QMessageBox.Yes:
        return
    _delete_custom_item(editor, kind, item_id)


class _CustomComboContextFilter(QObject):
    """Intercept the full native right-click sequence on the popup viewport."""

    def __init__(self, editor, kind):
        super().__init__(editor)
        self.editor = editor
        self.kind = kind
        self.pending_menu = None

    def _viewport(self, watched):
        selector = _custom_selector(self.editor, self.kind)
        if selector is None:
            return None, None
        try:
            view = selector.view()
            if watched is not view.viewport():
                return None, None
            return selector, view
        except Exception:
            return None, None

    def eventFilter(self, watched, event):
        event_type = event.type()
        if event_type not in (
            QEvent.MouseButtonPress,
            QEvent.MouseButtonRelease,
            QEvent.ContextMenu,
        ):
            return False
        selector, view = self._viewport(watched)
        if selector is None or view is None:
            return False
        if event_type == QEvent.MouseButtonPress:
            try:
                if event.button() != Qt.RightButton:
                    return False
            except Exception:
                return False
            self.pending_menu = None
            try:
                position = event.pos()
                index = view.indexAt(position)
                item_id = _custom_item_id_from_role(
                    _combo_role(selector, index.row())
                )
                if _custom_item_by_id(
                    self.editor,
                    self.kind,
                    item_id,
                ) is not None:
                    self.pending_menu = (position, item_id)
            except Exception:
                self.pending_menu = None
            return True
        if event_type == QEvent.MouseButtonRelease:
            try:
                if event.button() != Qt.RightButton:
                    return False
            except Exception:
                return False
            pending = self.pending_menu
            self.pending_menu = None
            if pending is not None:
                position, item_id = pending
                try:
                    item = _custom_item_by_id(self.editor, self.kind, item_id)
                    if item is not None:
                        _show_custom_combo_menu(
                            self.editor,
                            self.kind,
                            view,
                            position,
                        )
                except Exception:
                    pass
            return True
        # Some Qt styles still emit ContextMenu after the native press/release.
        self.pending_menu = None
        return True


def _install_custom_combo_menu(editor, kind):
    if editor is None or getattr(editor, f"_ygodiy_{kind}_combo_menu", False):
        return
    selector = _custom_selector(editor, kind)
    if selector is None:
        return
    try:
        viewport = selector.view().viewport()
        context_filter = _CustomComboContextFilter(editor, kind)
        viewport.setContextMenuPolicy(Qt.DefaultContextMenu)
        viewport.installEventFilter(context_filter)
    except Exception:
        return
    setattr(editor, f"_ygodiy_{kind}_combo_context_filter", context_filter)
    setattr(editor, f"_ygodiy_{kind}_combo_menu", True)


def _schedule_custom_overlay_refresh(editor):
    QTimer.singleShot(0, lambda target=editor: _apply_custom_overlays(target))


def _handle_custom_combo_change(editor, kind, original, wants_index):
    try:
        selector = _custom_selector(editor, kind)
        if selector is None:
            return
        index = selector.currentIndex()
        role = _combo_role(selector, index)
        if role == _CUSTOM_ACTION_ROLE:
            fallback = getattr(editor, _custom_config(kind)["last_index_attr"], 0)
            if kind == "holo":
                _prompt_custom_holo(editor, fallback)
            else:
                _prompt_custom_copyright(editor, fallback)
            return
        if _custom_item_id_from_role(role):
            setattr(editor, _custom_config(kind)["last_index_attr"], index)
            _activate_combo_selection(editor, kind, notify=True)
            return
        setattr(editor, _custom_config(kind)["last_index_attr"], index)
        try:
            if wants_index:
                original(editor, index)
            else:
                original(editor)
        finally:
            _activate_combo_selection(editor, kind, notify=False)
    except Exception:
        _customization_log(
            "切换%s样式失败:" % ("防伪" if kind == "holo" else "版权")
            + "\n" + traceback.format_exc()
        )


def _method_wants_index(method):
    try:
        return len(inspect.signature(method).parameters) > 1
    except (TypeError, ValueError):
        return True


def _defer_custom_combo_change(editor, kind, standard):
    """防伪 / 版权下拉切换时调用：推迟到下一轮事件循环再由 _handle_custom_combo_change 处理。

    standard 是编辑器的标准样式切换方法（未绑定的 _standard_holo_change / _standard_copyright_change）。
    正在把卡片数据套回编辑器时（_ygodiy_custom_restoring）不处理。
    """
    if getattr(editor, "_ygodiy_custom_restoring", False):
        return None
    wants_index = _method_wants_index(standard)
    QTimer.singleShot(
        0,
        lambda target=editor, with_index=wants_index: _handle_custom_combo_change(target, kind, standard, with_index),
    )
    return None


def _install_customization_controls(editor):
    if editor is None or getattr(editor, "_ygodiy_custom_controls_installed", False):
        return
    for kind in ("holo", "copyright"):
        _normalize_custom_items(editor, kind)
        _rebuild_custom_combo(editor, kind)
        _install_custom_combo_menu(editor, kind)
        selector = _custom_selector(editor, kind)
        if selector is not None:
            setattr(
                editor,
                _custom_config(kind)["last_index_attr"],
                max(0, selector.currentIndex()),
            )
        _activate_combo_selection(editor, kind, notify=False)
    for toggle_name in ("toggle_holo", "toggle_copy"):
        toggle = getattr(editor, toggle_name, None)
        if toggle is not None:
            try:
                toggle.toggled.connect(
                    lambda _checked=False, target=editor: _schedule_custom_overlay_refresh(
                        target
                    )
                )
            except Exception:
                pass
    setattr(editor, "_ygodiy_custom_controls_installed", True)


def _inject_customization_data(manager, data):
    if not isinstance(data, dict):
        return data
    editor = getattr(manager, "editor", None)
    if editor is None:
        return data
    for kind, items_key, active_key in (
        ("holo", "custom_holo_items", "custom_holo_active"),
        ("copyright", "custom_copyright_items", "custom_copyright_active"),
    ):
        config = _custom_config(kind)
        data[items_key] = copy.deepcopy(_normalize_custom_items(editor, kind))
        data[active_key] = _selected_custom_item_id(editor, kind)
        data.pop(config["legacy_value"], None)
        data.pop(config["legacy_name"], None)
    return data


def _load_customization_data(editor, data):
    if editor is None or not isinstance(data, dict):
        return
    for kind, items_key, active_key in (
        ("holo", "custom_holo_items", "custom_holo_active"),
        ("copyright", "custom_copyright_items", "custom_copyright_active"),
    ):
        config = _custom_config(kind)
        raw_items = data.get(items_key)
        items = []
        if isinstance(raw_items, list):
            items = copy.deepcopy(raw_items)
        elif data.get(config["legacy_value"]):
            value = str(data.get(config["legacy_value"], "") or "")
            if value:
                items = [
                    {
                        "id": f"legacy-{kind}",
                        "name": str(
                            data.get(config["legacy_name"], "")
                            or ("防伪图片" if kind == "holo" else value)
                        ),
                        config["value_key"]: value,
                    }
                ]
        setattr(editor, config["items_attr"], items)
        normalized = _normalize_custom_items(editor, kind)
        active_id = str(data.get(active_key, "") or "")
        if not active_id and normalized and data.get(config["legacy_value"]):
            active_id = str(normalized[0].get("id", "") or "")
        setattr(editor, config["active_attr"], active_id)
        _rebuild_custom_combo(editor, kind, select_id=active_id, fallback_index=0)
        _activate_combo_selection(editor, kind, notify=False)


def _sync_customization_selection(editor):
    for kind in ("holo", "copyright"):
        _activate_combo_selection(editor, kind, notify=False)


def _copy_customization_state(source, target):
    if source is None or target is None or source is target:
        return
    for kind in ("holo", "copyright"):
        config = _custom_config(kind)
        items = copy.deepcopy(_normalize_custom_items(source, kind))
        setattr(target, config["items_attr"], items)
        _normalize_custom_items(target, kind)
        active_id = _selected_custom_item_id(source, kind)
        setattr(target, config["active_attr"], active_id)
        current_id = _selected_custom_item_id(target, kind)
        target_selector = _custom_selector(target, kind)
        # 没选自定义项时保留目标当前的标准样式；原先固定回到下标 0，
        # 每次 OCG→RD 同步都会把 RD 的防伪/版权悄悄重置成「样式一」。
        _rebuild_custom_combo(
            target,
            kind,
            select_id=active_id or current_id,
            fallback_index=max(0, target_selector.currentIndex()) if target_selector is not None else 0,
        )
        _activate_combo_selection(target, kind, notify=False)


def _mirror_customization_to_otcg(editor):
    if editor is None:
        return
    app = getattr(editor, "parent_app", None)
    target = getattr(app, "otcg_widget", None)
    _copy_customization_state(editor, target)


def _sync_rd_overlay_controls_with_customization(rd_editor, otcg_editor):
    result = _prev_custom_sync_rd_overlay_controls(rd_editor, otcg_editor)
    if rd_editor is None or otcg_editor is None:
        return result
    try:
        _copy_customization_state(otcg_editor, rd_editor)
    except Exception:
        pass
    return result


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_frame import _prev_custom_sync_rd_overlay_controls
