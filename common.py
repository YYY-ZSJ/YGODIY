"""补丁子系统共用的导入、常量与小工具（控件读写、日志、缓存、调用原方法等）。

由补丁分片 p01、p02、p03、p04、p05、p06、p07、p09、p10、p13、p14、p45 整理而来。
"""

import copy
import io
import os
import sys

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap


_RD_IMAGE_RENDER_CACHE = {}
_RD_RANK_RESOURCE_PREFIX = "Rush_Duel/rank"

_EFFECT_LAYOUT_DEFAULTS = {
    "effect_first_line_compress": False,
    "effect_h_align": 0,
    "effect_v_align": 0,
    "effect_line_height_mode": 0,
    "effect_line_height": 100,
    "effect_letter_spacing": 0,
}
_EDITOR_TEXT_DEBOUNCE_MS = 90

_RACES = {
    1: "战士族",
    2: "魔法师族",
    4: "天使族",
    8: "恶魔族",
    16: "不死族",
    32: "机械族",
    64: "水族",
    128: "炎族",
    256: "岩石族",
    512: "鸟兽族",
    1024: "植物族",
    2048: "昆虫族",
    4096: "雷族",
    8192: "龙族",
    16384: "兽族",
    32768: "兽战士族",
    65536: "恐龙族",
    131072: "鱼族",
    262144: "海龙族",
    524288: "爬虫类族",
    1048576: "念动力族",
    2097152: "幻神兽族",
    4194304: "创造神族",
    8388608: "幻龙族",
    16777216: "电子界族",
    33554432: "幻想魔族",
}
_ATTRIBUTES = {
    1: "地",
    2: "水",
    4: "炎",
    8: "风",
    16: "光",
    32: "暗",
    64: "神",
}
_MAIN_TYPES = ("通常", "融合", "仪式", "同调", "超量", "连接", "衍生物")
_LINK_MARKERS = (64, 128, 256, 8, 32, 1, 2, 4)
_CARD_TYPE_FILTERS = (
    ("通常", 0x10),
    ("效果", 0x20),
    ("融合", 0x40),
    ("仪式", 0x80),
    ("同调", 0x2000),
    ("超量", 0x800000),
    ("灵摆", 0x1000000),
    ("连接", 0x4000000),
    ("魔法", 0x2),
    ("陷阱", 0x4),
)
_SPELL_TRAP_FILTERS = (
    ("通常魔法", 0x2),
    ("场地魔法", 0x80000),
    ("装备魔法", 0x40000),
    ("永续魔法", 0x20000),
    ("速攻魔法", 0x10000),
    ("仪式魔法", 0x80),
    ("通常陷阱", 0x4),
    ("永续陷阱", 0x20000),
    ("反击陷阱", 0x100000),
)
_ABILITY_FILTERS = (
    ("卡通", 0x400000),
    ("二重", 0x800),
    ("同盟", 0x400),
    ("灵魂", 0x200),
    ("调整", 0x1000),
    ("反转", 0x200000),
    ("特殊召唤", 0x2000000),
    ("效果以外", 0),
)


def _app_dir():
    """程序目录（日志、标签页状态、设置文件都放在这里）。fast_launch 用 YGODIY_APP_DIR 告诉源码。"""
    return os.environ.get("YGODIY_APP_DIR") or os.path.dirname(os.path.abspath(sys.executable))


def _freeze_cache_value(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_cache_value(item)) for key, item in value.items()))
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(value))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_cache_value(item) for item in value)
    return value


def _tab_log(message):
    try:
        log_path = os.path.join(_app_dir(), "制卡器标签页.log")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(message + "\n")
    except Exception:
        pass


def _bounded_cache_put(cache, key, value, limit):
    try:
        cache.pop(key, None)
        cache[key] = value
        while len(cache) > limit:
            cache.pop(next(iter(cache)))
    except Exception:
        cache[key] = value


def _bounded_cache_get(cache, key):
    value = cache.get(key)
    if value is not None:
        try:
            cache.pop(key, None)
            cache[key] = value
        except Exception:
            pass
    return value


def _json_clone(data):
    return copy.deepcopy(data)


def _text_from(widget, default=""):
    try:
        return str(widget.text())
    except Exception:
        return default


def _plain_text_from(widget, default=""):
    try:
        return str(widget.toPlainText())
    except Exception:
        return default


def _combo_text_from(widget, default=""):
    try:
        return str(widget.currentText())
    except Exception:
        return default


def _combo_index_from(widget, default=0):
    try:
        return int(widget.currentIndex())
    except Exception:
        text = _combo_text_from(widget)
        try:
            for index in range(widget.count()):
                if str(widget.itemText(index)) == text:
                    return index
        except Exception:
            pass
        return int(default)


def _slider_value_from(widget, default=0):
    try:
        return int(widget.value())
    except Exception:
        return int(default)


def _set_line_text(widget, text):
    if widget is None:
        return
    value = str(text or "")
    try:
        if str(widget.text()) == value:
            return
    except Exception:
        pass
    try:
        widget.setText(value)
    except Exception:
        pass


def _set_plain_text(widget, text):
    if widget is None:
        return
    value = str(text or "")
    try:
        if str(widget.toPlainText()) == value:
            return
    except Exception:
        pass
    try:
        widget.setText(value)
    except Exception:
        try:
            widget.setPlainText(value)
        except Exception:
            pass


def _set_graphics_text(item, text):
    if item is None:
        return
    value = str(text or "")
    for getter_name in ("toPlainText", "text"):
        try:
            if str(getattr(item, getter_name)()) == value:
                return
        except Exception:
            pass
    for method_name in ("setPlainText", "setText"):
        try:
            getattr(item, method_name)(value)
            return
        except Exception:
            pass


def _set_combo_text(widget, text, fallback_index=None):
    if widget is None:
        return
    value = str(text or "")
    try:
        if value and str(widget.currentText()) == value:
            return
    except Exception:
        pass
    try:
        if value:
            widget.setCurrentText(value)
            return
    except Exception:
        pass
    if fallback_index is not None:
        try:
            widget.setCurrentIndex(int(fallback_index))
        except Exception:
            pass


def _call_with_blocked_signals(widget, callback, *args, **kwargs):
    if widget is None:
        return None
    previous = None
    blocked = False
    try:
        previous = widget.blockSignals(True)
        blocked = True
    except Exception:
        pass
    try:
        return callback(widget, *args, **kwargs)
    finally:
        if blocked:
            try:
                widget.blockSignals(previous)
            except Exception:
                pass


def _set_line_text_silent(widget, text):
    return _call_with_blocked_signals(widget, _set_line_text, text)


def _set_plain_text_silent(widget, text):
    return _call_with_blocked_signals(widget, _set_plain_text, text)


def _set_combo_text_silent(widget, text, fallback_index=None):
    return _call_with_blocked_signals(
        widget,
        _set_combo_text,
        text,
        fallback_index,
    )


def _set_combo_index_silent(widget, index):
    def set_index(target, value):
        return _safe_call(getattr(target, "setCurrentIndex", None), value)

    return _call_with_blocked_signals(widget, set_index, index)


def _set_slider_value_silent(widget, value):
    def set_value(target, slider_value):
        return _safe_call(getattr(target, "setValue", None), int(slider_value))

    return _call_with_blocked_signals(widget, set_value, value)


def _set_toggle_checked_silent(widget, checked):
    def set_checked(target, value):
        if hasattr(target, "is_checked"):
            target.is_checked = bool(value)
            _safe_call(getattr(target, "animate_circle", None))
            _safe_call(getattr(target, "update", None))
            return None
        return _safe_call(getattr(target, "setChecked", None), bool(value))

    return _call_with_blocked_signals(widget, set_checked, checked)


def _safe_call(method, *args, **kwargs):
    try:
        if method is not None:
            return method(*args, **kwargs)
    except Exception:
        pass
    return None


def _replace_combo_items(widget, items, selected_index=0):
    if widget is None:
        return
    previous_blocked = None
    try:
        previous_blocked = widget.blockSignals(True)
    except Exception:
        pass
    try:
        try:
            widget.clear()
            widget.addItems([str(item) for item in items])
        except Exception:
            try:
                for index in range(widget.count() - 1, -1, -1):
                    widget.removeItem(index)
                for index, item in enumerate(items):
                    widget.insertItem(index, str(item))
            except Exception:
                return
        if items:
            widget.setCurrentIndex(max(0, min(int(selected_index), len(items) - 1)))
    finally:
        if previous_blocked is not None:
            try:
                widget.blockSignals(previous_blocked)
            except Exception:
                pass


def _set_item_visible(item, visible):
    if item is None:
        return
    try:
        item.setVisible(bool(visible))
    except Exception:
        pass


def _toggle_checked(widget, default=False):
    if widget is None:
        return bool(default)
    if hasattr(widget, "is_checked"):
        return bool(widget.is_checked)
    try:
        return bool(widget.isChecked())
    except Exception:
        return bool(default)


def _pixmap_from_pillow(image):
    try:
        from PyQt5.QtGui import QImage

        rgba = image if image.mode == "RGBA" else image.convert("RGBA")
        width, height = rgba.size
        qimage = QImage(
            rgba.tobytes("raw", "RGBA"),
            width,
            height,
            width * 4,
            QImage.Format_RGBA8888,
        ).copy()
        return QPixmap.fromImage(qimage)
    except Exception:
        data = io.BytesIO()
        image.save(data, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(data.getvalue())
        return pixmap


def _set_text_item_alignment(item, alignment):
    if item is None:
        return
    try:
        document = item.document()
        option = document.defaultTextOption()
        option.setAlignment(alignment)
        document.setDefaultTextOption(option)
    except Exception:
        pass


def _set_text_item_pixel_size(item, pixel_size):
    if item is None:
        return
    try:
        font = item.font()
        font.setPixelSize(max(1, int(pixel_size)))
        font.setStretch(100)
        item.setFont(font)
    except Exception:
        pass


def _set_text_item_outline(item, enabled, thickness=0):
    if item is None:
        return
    _safe_call(getattr(item, "enableOutline", None), bool(enabled))
    if enabled:
        _safe_call(
            getattr(item, "setOutlineStyle", None),
            color=Qt.black,
            thickness=float(thickness),
        )


def _ensure_preview_updates_enabled(app):
    view = getattr(app, "view", None)
    viewport = _safe_call(getattr(view, "viewport", None))
    scene = _safe_call(getattr(view, "scene", None))
    for target in (view, viewport):
        if target is None:
            continue
        _safe_call(getattr(target, "setUpdatesEnabled", None), True)
        _safe_call(getattr(target, "update", None))
        _safe_call(getattr(target, "repaint", None))
    if view is not None:
        _safe_call(getattr(view, "resetCachedContent", None))
    if scene is not None:
        _safe_call(getattr(scene, "update", None))


def _schedule_preview_update_restore(app):
    _ensure_preview_updates_enabled(app)
    for delay in (0, 50, 200):
        try:
            QTimer.singleShot(
                delay,
                lambda app=app: _ensure_preview_updates_enabled(app),
            )
        except Exception:
            pass


def _attach_editor_button(editor, button, reference_names=()):
    """把按钮挂进编辑器布局：先参考已有按钮所在布局，再退回编辑器自身布局。

    返回是否成功进入布局。
    """
    try:
        from PyQt5.QtWidgets import QPushButton
    except Exception:
        return False

    references = []
    for name in reference_names:
        reference = getattr(editor, name, None)
        if reference is not None:
            references.append(reference)
    if not references:
        try:
            references = [
                child
                for child in editor.findChildren(QPushButton)
                if child is not button and child.text()
            ]
        except Exception:
            references = []

    for reference in references:
        parent = reference.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is None:
            continue
        try:
            layout.addWidget(button)
            button.show()
            return True
        except Exception:
            continue

    layout = editor.layout()
    if layout is not None:
        try:
            layout.addWidget(button)
            button.show()
            return True
        except Exception:
            pass

    try:
        button.setParent(editor)
        button.show()
    except Exception:
        return False
    return False


def _original_positional_limit(original):
    """返回原方法除 self 外可接受的位置参数个数；None 表示可变参数（不限）。"""
    try:
        import inspect

        parameters = list(inspect.signature(original).parameters.values())
    except (TypeError, ValueError):
        return 0
    count = 0
    for parameter in parameters:
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD):
            count += 1
        elif parameter.kind == parameter.VAR_POSITIONAL:
            return None
    return max(0, count - 1)


def _call_original(original, self, args, kwargs):
    """调用原方法，并按原签名裁剪多余的位置参数（Qt 信号常会多传参数）。"""
    limit = _original_positional_limit(original)
    if limit is None:
        return original(self, *args, **kwargs)
    return original(self, *args[:limit], **kwargs)


_RARE_FRONT_Z = 10000.0


def _widget_scene(editor):
    """Return the QGraphicsScene attached to an editor."""
    try:
        from PyQt5.QtWidgets import QGraphicsScene
    except Exception:
        return None
    candidates = [getattr(editor, "scene", None)]
    app = getattr(editor, "parent_app", None)
    if app is not None:
        name = type(editor).__name__.lower()
        if "rd" in name:
            candidates.extend((getattr(app, "rd_scene", None), getattr(app, "scene", None)))
        elif "past" in name:
            candidates.extend((getattr(app, "past_scene", None), getattr(app, "scene", None)))
        else:
            candidates.extend((getattr(app, "scene", None), getattr(app, "otcg_scene", None)))
    for candidate in candidates:
        if isinstance(candidate, QGraphicsScene):
            return candidate
    return None


def _symbol_layout_of(root, widget):
    """返回 (直接包含 widget 的布局, 下标)。"""
    if root is None:
        return None
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is None:
            continue
        if item.widget() is widget:
            return root, index
        if item.layout() is not None:
            found = _symbol_layout_of(item.layout(), widget)
            if found is not None:
                return found
    return None


def _install_symbol_bar(panel, effect_name, extra_names):
    from customComponents import make_symbol_bar

    if panel is None or getattr(panel, "_symbol_bar", None) is not None:
        return
    effect = getattr(panel, effect_name, None)
    found = _symbol_layout_of(panel.layout(), effect) if effect is not None else None
    if found is None:
        _tab_log("特殊符号按钮：找不到 %s 的效果文本框" % type(panel).__name__)
        return
    layout, index = found
    extras = [getattr(panel, n, None) for n in extra_names]
    bar, watcher = make_symbol_bar(panel, effect, extras)
    layout.insertWidget(index, bar)
    panel._symbol_bar = bar
    panel._symbol_watcher = watcher
