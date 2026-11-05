"""RD 卡框跟随 OCG 编辑器：把 OCG 的卡片数据同步到 RD 卡面，以及切到 RD 模式。

由补丁分片 p01、p06、p07、p08、p09、p10、p26、p38、p42 整理而来。
"""

import os
import sys
import traceback

from PIL import Image, ImageOps
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QGraphicsPixmapItem

from common import (
    _RD_IMAGE_RENDER_CACHE,
    _RD_RANK_RESOURCE_PREFIX,
    _app_dir,
    _bounded_cache_get,
    _bounded_cache_put,
    _combo_index_from,
    _combo_text_from,
    _freeze_cache_value,
    _pixmap_from_pillow,
    _plain_text_from,
    _replace_combo_items,
    _safe_call,
    _schedule_preview_update_restore,
    _set_combo_index_silent,
    _set_combo_text,
    _set_combo_text_silent,
    _set_graphics_text,
    _set_item_visible,
    _set_line_text_silent,
    _set_plain_text_silent,
    _set_slider_value_silent,
    _set_text_item_alignment,
    _set_text_item_outline,
    _set_text_item_pixel_size,
    _set_toggle_checked_silent,
    _slider_value_from,
    _tab_log,
    _text_from,
    _toggle_checked,
)
from utils import runtime_resource_exists


_RD_LINK_OVERLAY_CACHE = {}

_RD_PENDULUM_FONT_MAX_SIZE = 48
_RD_PENDULUM_FONT_MIN_SIZE = 28
_RD_HIDDEN_OCG_CALL_WAYS = ("暗黑同调", "巨神兵", "天空龙", "翼神龙")
_RD_HIDDEN_OCG_WIDGETS = ("LB_Zack_label", "LB_Zack_toggle")
_RD_ONLY_COMBO_OPTIONS = {
    "copyright_selector": ("样式一", "样式二", "样式三"),
    "rare_selector": ("N", "SR", "RR", "PSER"),
}

_RD_IMAGE_RENDER_CACHE_LIMIT = 24

_RD_FRAME_SYNC_DELAY_MS = 45


def _set_rd_only_combo_options(editor, enabled):
    state_name = "_rd_only_combo_states"
    if enabled:
        if hasattr(editor, state_name):
            return
        states = {}
        for name, rd_items in _RD_ONLY_COMBO_OPTIONS.items():
            widget = getattr(editor, name, None)
            if widget is None:
                continue
            try:
                original_items = tuple(
                    str(widget.itemText(index)) for index in range(widget.count())
                )
                # 选项上的附加数据（如 p17「自定义」项的动作标记）和图标也要保存，
                # 只恢复文字会让「自定义」退化成普通选项，再选它就会越界。
                original_extras = tuple(
                    (widget.itemData(index, Qt.UserRole), widget.itemIcon(index))
                    for index in range(widget.count())
                )
            except Exception:
                continue
            selected_index = _combo_index_from(widget)
            states[name] = (original_items, selected_index, original_extras)
            _replace_combo_items(widget, rd_items, selected_index)
        setattr(editor, state_name, states)
        return

    states = getattr(editor, state_name, None)
    if states is None:
        return
    for name, state in states.items():
        original_items = state[0]
        original_extras = state[2] if len(state) > 2 else ()
        widget = getattr(editor, name, None)
        _replace_combo_items(widget, original_items, _combo_index_from(widget))
        _restore_combo_item_extras(widget, original_extras)
    delattr(editor, state_name)


def _restore_combo_item_extras(widget, extras):
    if widget is None or not extras:
        return
    try:
        was_blocked = widget.blockSignals(True)
        try:
            for index, (data, icon) in enumerate(extras[: widget.count()]):
                if data is not None:
                    widget.setItemData(index, data, Qt.UserRole)
                if icon is not None and not icon.isNull():
                    widget.setItemIcon(index, icon)
        finally:
            widget.blockSignals(was_blocked)
    except Exception:
        pass


def _set_rd_only_editor_controls(app, enabled):
    editor = getattr(app, "otcg_widget", None)
    if editor is None:
        return

    selector = getattr(editor, "info_selector_left", None)
    if enabled:
        _set_rd_only_combo_options(editor, True)
        if not hasattr(editor, "_rd_hidden_call_way_items"):
            hidden_items = []
            previous_text = _combo_text_from(selector)
            try:
                for index in range(selector.count() - 1, -1, -1):
                    text = str(selector.itemText(index))
                    if text in _RD_HIDDEN_OCG_CALL_WAYS:
                        hidden_items.append((index, text))
                        selector.removeItem(index)
            except Exception:
                hidden_items = []
            editor._rd_hidden_call_way_items = sorted(hidden_items)
            editor._rd_hidden_previous_call_way = (
                previous_text if previous_text in _RD_HIDDEN_OCG_CALL_WAYS else ""
            )
            if editor._rd_hidden_previous_call_way:
                _set_combo_text(selector, "效果", 0)

        if not hasattr(editor, "_rd_hidden_widget_states"):
            states = {}
            for name in _RD_HIDDEN_OCG_WIDGETS:
                widget = getattr(editor, name, None)
                if widget is None:
                    continue
                try:
                    states[name] = not bool(widget.isHidden())
                except Exception:
                    states[name] = True
                try:
                    widget.setVisible(False)
                except Exception:
                    pass
            editor._rd_hidden_widget_states = states

        toggle = getattr(editor, "LB_Zack_toggle", None)
        if toggle is not None and not hasattr(editor, "_rd_hidden_zack_checked"):
            editor._rd_hidden_zack_checked = bool(getattr(toggle, "is_checked", False))
            try:
                toggle.is_checked = False
                _safe_call(getattr(toggle, "animate_circle", None))
                _safe_call(getattr(toggle, "update", None))
            except Exception:
                pass
        return

    _set_rd_only_combo_options(editor, False)
    hidden_items = getattr(editor, "_rd_hidden_call_way_items", None)
    if hidden_items is not None:
        try:
            existing = {
                str(selector.itemText(index)) for index in range(selector.count())
            }
            for index, text in hidden_items:
                if text not in existing:
                    selector.insertItem(min(index, selector.count()), text)
                    existing.add(text)
            previous_text = getattr(editor, "_rd_hidden_previous_call_way", "")
            if previous_text and _combo_text_from(selector) == "效果":
                _set_combo_text(selector, previous_text)
        except Exception:
            pass
        delattr(editor, "_rd_hidden_call_way_items")
        if hasattr(editor, "_rd_hidden_previous_call_way"):
            delattr(editor, "_rd_hidden_previous_call_way")

    states = getattr(editor, "_rd_hidden_widget_states", None)
    if states is not None:
        for name, visible in states.items():
            try:
                getattr(editor, name).setVisible(bool(visible))
            except Exception:
                pass
        delattr(editor, "_rd_hidden_widget_states")

    if hasattr(editor, "_rd_hidden_zack_checked"):
        toggle = getattr(editor, "LB_Zack_toggle", None)
        if toggle is not None:
            try:
                toggle.is_checked = bool(editor._rd_hidden_zack_checked)
                _safe_call(getattr(toggle, "animate_circle", None))
                _safe_call(getattr(toggle, "update", None))
            except Exception:
                pass
        delattr(editor, "_rd_hidden_zack_checked")


def _install_rd_only_editor_controls(editor, attempt=0):
    if editor is None or getattr(editor, "_rd_only_controls_installed", False):
        return
    app = getattr(editor, "parent_app", None)
    mode_selector = getattr(app, "combo_box", None)
    try:
        signal = mode_selector.currentIndexChanged
    except Exception:
        if attempt < 20:
            QTimer.singleShot(
                100,
                lambda: _install_rd_only_editor_controls(editor, attempt + 1),
            )
        return

    def update(index=None):
        if index is None:
            try:
                index = mode_selector.currentIndex()
            except Exception:
                index = getattr(app, "current_mode", 0)
        _set_rd_only_editor_controls(app, int(index) == 1)

    signal.connect(update)
    editor._rd_only_controls_installed = True
    update()
    control_output_path = os.environ.get("YGODIY_RD_CONTROL_DIAGNOSTIC")
    if not control_output_path and "--rd-control-diagnostic" in sys.argv:
        control_output_path = os.path.join(
            _app_dir(),
            "logs",
            "rd-control-diagnostic.json",
        )
    if control_output_path:
        QTimer.singleShot(
            2500,
            lambda: _export_rd_control_diagnostic(app, control_output_path),
        )


def _mapped_otcg_detail_value(otcg_editor, value):
    value = str(value or "")
    try:
        language = getattr(otcg_editor, "language", "简体中文")
        return str(otcg_editor.config.detail_map[language][value])
    except Exception:
        return value


def _mapped_otcg_race_value(otcg_editor, value):
    value = str(value or "")
    try:
        language = getattr(otcg_editor, "language", "简体中文")
        return str(otcg_editor.config.race_map[language][value])
    except Exception:
        return value


def _fallback_otcg_detail_text(otcg_editor):
    language = str(getattr(otcg_editor, "language", "简体中文") or "简体中文")
    if _toggle_checked(getattr(otcg_editor, "detail_custom_toggle", None)):
        parts_text = _text_from(getattr(otcg_editor, "detail_custom_edit", None))
        left, right = ("[", "]") if language == "英文" else ("【", "】")
        return left + parts_text + right

    race = _mapped_otcg_race_value(
        otcg_editor,
        _combo_text_from(getattr(otcg_editor, "race_selector", None), "怪兽"),
    )
    call_way = str(
        getattr(otcg_editor, "detail_call_way", "")
        or _combo_text_from(getattr(otcg_editor, "info_selector_left", None), "效果")
    )
    extra1 = str(
        getattr(otcg_editor, "detail_extra1", "")
        or _combo_text_from(getattr(otcg_editor, "info_selector_mid", None))
    )
    extra2 = str(
        getattr(otcg_editor, "detail_extra2", "")
        or _combo_text_from(getattr(otcg_editor, "info_selector_right", None))
    )
    mapped = lambda value: _mapped_otcg_detail_value(otcg_editor, value)

    parts = [race, mapped(call_way)]
    if call_way != "通常":
        parts.append(mapped("效果"))
    if call_way in {"衍生物", "效果"}:
        parts.pop(-2)

    if extra1 and extra1 != extra2:
        if extra1 == "通常":
            if len(parts) > 2:
                parts.pop(-1)
            if call_way == "衍生物":
                parts[-1] = mapped("通常")
        else:
            parts.insert(-1, mapped(extra1))

    if extra2 and extra2 != extra1:
        if extra2 == "通常":
            if len(parts) > 2 and parts[-1] == mapped("效果") and call_way != "效果":
                parts.pop(-1)
        elif parts[-1] in {mapped("效果"), mapped("通常")}:
            parts.insert(-1, mapped(extra2))
        else:
            parts.append(mapped(extra2))

    if extra1 == extra2 and extra1:
        if extra1 == "通常":
            parts.pop(-1)
        else:
            parts.insert(-1, mapped(extra1))

    special_summon = mapped("特殊召唤")
    if special_summon in parts:
        index = parts.index(special_summon)
        if index != 1:
            parts.pop(index)
            parts.insert(1, special_summon)

    left, right = ("[", "]") if language == "英文" else ("【", "】")
    separator = "／" if "日文" in language else "/"
    text = left + separator.join(parts) + right
    if bool(getattr(otcg_editor, "offical_cn", False)):
        text = text.replace("同调", "同步").replace("调整", "协调")
    return text


def _otcg_detail_text(otcg_editor):
    compressor = getattr(otcg_editor, "detail_compresstor", None)
    generated = getattr(compressor, "text", None)
    if isinstance(generated, str) and generated:
        return generated
    return _fallback_otcg_detail_text(otcg_editor)


def _rd_supported_call_way(value):
    text = str(value or "")
    supported = {
        "通常",
        "效果",
        "融合",
        "仪式",
        "同调",
        "连接",
        "衍生物",
        "超量",
        "灵摆",
        "通常灵摆",
        "效果灵摆",
        "融合灵摆",
        "仪式灵摆",
        "同调灵摆",
        "超量灵摆",
    }
    aliases = {
        "XYZ": "超量",
        "XYZ灵摆": "超量灵摆",
        "Link": "连接",
        "LINK": "连接",
        "Token": "衍生物",
    }
    text = aliases.get(text, text)
    if text in supported:
        return text
    return "效果"


def _rd_frame_call_way_from_otcg(call_way, *extra_values):
    base = _rd_supported_call_way(call_way)
    extras = {str(value or "") for value in extra_values}
    if "灵摆" not in extras:
        return base
    # 卡框仍按副类型细分（Pend_Normal / Pend_Effect / Pend_Fusion …），
    # 只是这些细分值不再出现在召唤方式下拉里。
    pendulum_map = {
        "通常": "通常灵摆",
        "效果": "效果灵摆",
        "融合": "融合灵摆",
        "仪式": "仪式灵摆",
        "同调": "同调灵摆",
        "超量": "超量灵摆",
    }
    return pendulum_map.get(base, "灵摆")


_LINK_ARROW_DIRECTIONS = ("UL", "U", "UR", "L", "R", "BL", "B", "BR")


def _link_arrow_states_from_otcg(otcg_editor):
    arrows = getattr(otcg_editor, "arrow_status_list", None)
    if isinstance(arrows, (list, tuple)):
        states = [bool(value) for value in arrows[:8]]
        states.extend([False] * (8 - len(states)))
        return tuple(states)
    return (False,) * 8


def _rd_link_overlay_pixmap(width, height, rating, arrow_states):
    arrow_states = tuple(bool(value) for value in arrow_states)
    arrow_mask = sum(1 << index for index, enabled in enumerate(arrow_states) if enabled)
    key = (int(width), int(height), int(rating), arrow_mask)
    cached = _RD_LINK_OVERLAY_CACHE.get(key)
    if cached is not None:
        return cached

    import RD_widget

    pixmap = RD_widget.decrypt_image_qpixmap(
        f"Rush_Duel/Link_Rating{max(0, min(8, int(rating)))}.enc"
    ).copy()
    painter = QPainter(pixmap)
    for direction, enabled in zip(_LINK_ARROW_DIRECTIONS, arrow_states):
        if enabled:
            painter.drawPixmap(
                0,
                0,
                RD_widget.decrypt_image_qpixmap(f"Rush_Duel/Link_Arrow_{direction}.enc"),
            )
    painter.end()
    _RD_LINK_OVERLAY_CACHE[key] = pixmap
    return pixmap


def _ensure_rd_link_overlay(rd_editor, rating, arrow_states):
    try:
        overlay = getattr(rd_editor, "_rd_link_overlay_item", None)
        if overlay is None:
            overlay = QGraphicsPixmapItem()
            overlay.setZValue(8)
            rd_editor.parent_app.rd_scene.addItem(overlay)
            rd_editor._rd_link_overlay_item = overlay
        config = getattr(rd_editor, "config", None)
        width = getattr(config, "card_w", 1626)
        height = getattr(config, "card_h", 2370)
        overlay.setPixmap(_rd_link_overlay_pixmap(width, height, rating, arrow_states))
        overlay.setVisible(True)
    except Exception:
        _tab_log("创建RD Link叠加层失败:\n" + traceback.format_exc())


def _apply_rd_link_visuals(rd_editor, is_link, rating=0, arrow_states=None):
    if arrow_states is None:
        arrow_states = (False,) * 8
    is_link = bool(is_link)
    rating = max(0, min(8, int(rating or 0)))
    arrow_states = tuple(bool(value) for value in arrow_states)
    signature = (is_link, rating, arrow_states)
    if getattr(rd_editor, "_rd_synced_link_visuals", None) == signature:
        return
    rd_editor._rd_synced_link_visuals = signature
    rd_editor._rd_link_mode = is_link
    rd_editor._rd_link_rating = rating
    rd_editor._rd_link_arrow_states = arrow_states
    overlay = getattr(rd_editor, "_rd_link_overlay_item", None)
    if not is_link:
        if overlay is not None:
            _set_item_visible(overlay, False)
        for name in ("level_item", "ATK_DEF_item", "DEF_number_item"):
            _set_item_visible(getattr(rd_editor, name, None), True)
        max_visible = bool(getattr(rd_editor, "Max_ATK_flag", False))
        for name in ("Max_ATK_item", "Max_number_item"):
            _set_item_visible(getattr(rd_editor, name, None), max_visible)
        return

    _ensure_rd_link_overlay(
        rd_editor,
        rd_editor._rd_link_rating,
        rd_editor._rd_link_arrow_states,
    )
    for name in ("level_item", "ATK_DEF_item", "DEF_number_item", "Max_ATK_item", "Max_number_item"):
        _set_item_visible(getattr(rd_editor, name, None), False)
    _set_item_visible(getattr(rd_editor, "ATK_number_item", None), True)
    for name in ("card_name_item", "ATK_number_item", "detail_text_item", "text_item", "card_pack_item", "attribute_item"):
        item = getattr(rd_editor, name, None)
        try:
            item.setZValue(12)
        except Exception:
            pass


def _apply_rd_pendulum_visuals(rd_editor, is_pendulum):
    is_pendulum = bool(is_pendulum)
    if getattr(rd_editor, "_rd_synced_pendulum_visuals", None) == is_pendulum:
        return
    rd_editor._rd_synced_pendulum_visuals = is_pendulum
    item_names = (
        "level_item",
        "ATK_DEF_item",
        "Max_ATK_item",
        "ATK_number_item",
        "DEF_number_item",
        "Max_number_item",
    )
    shift_y = 308
    positions = getattr(rd_editor, "_rd_pendulum_original_positions", None)
    if positions is None:
        positions = {}
        for name in item_names:
            item = getattr(rd_editor, name, None)
            if item is not None:
                try:
                    pos = item.pos()
                    positions[name] = (float(pos.x()), float(pos.y()))
                except Exception:
                    pass
        rd_editor._rd_pendulum_original_positions = positions

    for name, (x, y) in positions.items():
        item = getattr(rd_editor, name, None)
        if item is not None:
            try:
                item.setPos(x, y - shift_y if is_pendulum else y)
            except Exception:
                pass
    rd_editor._rd_pendulum_mode = bool(is_pendulum)


def _rd_sync_pendulum_text_inner(rd_editor, otcg_editor, is_pendulum):
    item = getattr(rd_editor, "_rd_pendulum_text_item", None)
    if not is_pendulum:
        if getattr(rd_editor, "_rd_synced_pendulum_text", None) is False:
            return
        rd_editor._rd_synced_pendulum_text = False
        if item is not None:
            _set_item_visible(item, False)
        return

    text = ""
    for name in ("LB_text_edit", "lb_text_edit", "lb_text_input"):
        text = _plain_text_from(getattr(otcg_editor, name, None))
        if text:
            break
    signature = (True, text)
    if getattr(rd_editor, "_rd_synced_pendulum_text", None) == signature:
        return
    rd_editor._rd_synced_pendulum_text = signature

    try:
        if item is None:
            from PyQt5.QtWidgets import QGraphicsTextItem

            item = QGraphicsTextItem()
            item.setDefaultTextColor(Qt.black)
            item.document().setDocumentMargin(0)
            item.setZValue(12)
            rd_editor.parent_app.rd_scene.addItem(item)
            rd_editor._rd_pendulum_text_item = item

        item.setVisible(True)
        item.setPos(245, 1435)
        item.setTextWidth(1135)
        item.setPlainText(text)

        source_item = getattr(rd_editor, "detail_text_item", None)
        if source_item is None:
            source_item = getattr(rd_editor, "text_item", None)
        font = source_item.font() if source_item is not None else item.font()
        try:
            font.setBold(True)
        except Exception:
            pass
        for pixel_size in range(
            _RD_PENDULUM_FONT_MAX_SIZE,
            _RD_PENDULUM_FONT_MIN_SIZE - 1,
            -1,
        ):
            font.setPixelSize(pixel_size)
            item.setFont(font)
            if item.boundingRect().height() <= 255:
                break
    except Exception:
        _tab_log("同步RD灵摆效果文本失败:\n" + traceback.format_exc())


# 官方灵摆卡把刻度数字放在菱形下方、与灵摆效果栏垂直居中（不是压在菱形里）。
# 实测：官方数字墨迹中心比菱形中心低约一个菱形高度，换算到本框即菱形下缘再往下 30px。
_RD_PENDULUM_SCALE_GAP = 30
_RD_PENDULUM_SCALE_FONT_SIZE = 62


def _rd_pendulum_scale_center_y(diamond_center_y, diamond_height):
    """刻度数字的中心：菱形下缘再往下 _RD_PENDULUM_SCALE_GAP。"""
    diamond_bottom = float(diamond_center_y) + float(diamond_height) / 2.0
    return diamond_bottom + _RD_PENDULUM_SCALE_GAP + _RD_PENDULUM_SCALE_FONT_SIZE / 2.0


# RD 灵摆框里菱形刻度箭头的位置与尺寸（刻度数字据此定位）。
# 数值由框资源实测：Pend / Pend_Normal / Pend_Effect 等各色框的位置一致，
# 箭头本身在框里就是实心饱和的 —— 之前看起来半透明，是因为超框前层
# （RD_front_item）的 z 值压在卡框之上把它糊住了，见 _RD_LAYER_Z。
_RD_PENDULUM_DIAMONDS = ((157, 1492, 98, 74), (1468, 1492, 97, 75))


def _rd_sync_pendulum_scales_inner(rd_editor, otcg_editor, is_pendulum):
    items = getattr(rd_editor, "_rd_pendulum_scale_items", None)
    if not is_pendulum:
        if getattr(rd_editor, "_rd_synced_pendulum_scales", None) is False:
            return
        rd_editor._rd_synced_pendulum_scales = False
        for item in items or ():
            _set_item_visible(item, False)
        return

    scale = _text_from(getattr(otcg_editor, "LB_level_edit", None), "")
    if not scale:
        scale = str(getattr(otcg_editor, "LB_level", "") or "")
    signature = (True, scale)
    if getattr(rd_editor, "_rd_synced_pendulum_scales", None) == signature:
        return
    rd_editor._rd_synced_pendulum_scales = signature

    try:
        if items is None:
            from PyQt5.QtWidgets import QGraphicsTextItem

            items = (QGraphicsTextItem(), QGraphicsTextItem())
            for item in items:
                item.setDefaultTextColor(Qt.black)
                item.document().setDocumentMargin(0)
                item.setZValue(13)
                rd_editor.parent_app.rd_scene.addItem(item)
            rd_editor._rd_pendulum_scale_items = items

        ocg_scale_items = (
            getattr(otcg_editor, "LB_level_left", None),
            getattr(otcg_editor, "LB_level_right", None),
        )
        for item, source_item, (center_x, center_y, _w, diamond_h) in zip(
            items,
            ocg_scale_items,
            _RD_PENDULUM_DIAMONDS,
        ):
            font = source_item.font() if source_item is not None else item.font()
            font.setPixelSize(_RD_PENDULUM_SCALE_FONT_SIZE)
            item.setVisible(True)
            item.setFont(font)
            item.setPlainText(scale)
            rect = item.boundingRect()
            item.setPos(
                center_x - rect.width() / 2,
                _rd_pendulum_scale_center_y(center_y, diamond_h) - rect.height() / 2,
            )
    except Exception:
        _tab_log("同步RD灵摆刻度失败:\n" + traceback.format_exc())


def _sync_rd_attribute(rd_editor, attribute):
    attribute = str(attribute or "")
    if attribute not in {"光", "暗", "风", "水", "炎", "地", "神"}:
        return
    if getattr(rd_editor, "_rd_synced_attribute", None) == attribute:
        return
    rd_editor._rd_synced_attribute = attribute
    try:
        rd_editor.current_attribute = attribute
        for name, button in getattr(rd_editor, "attribute_btn_dict", {}).items():
            colors = (
                getattr(rd_editor, "attribute_on_colors", {})
                if name == attribute
                else getattr(rd_editor, "attribute_off_colors", {})
            )
            _safe_call(getattr(button, "setColor", None), colors.get(name))
        attribute_item = getattr(rd_editor, "attribute_item", None)
        config = getattr(rd_editor, "config", None)
        if attribute_item is not None and config is not None:
            import RD_widget

            attribute_imgs = getattr(config, "attribute_imgs", {})
            if attribute in attribute_imgs:
                attribute_item.setPixmap(
                    RD_widget.decrypt_image_qpixmap(attribute_imgs[attribute])
                )
    except Exception:
        _tab_log("同步RD属性失败:\n" + traceback.format_exc())


def _sync_rd_name_color(rd_editor, otcg_editor):
    names = (
        "title_color",
        "shadow_vis_ratio",
        "outline_enabled",
        "outline_color",
        "outline_thickess",
        "shadow_flag",
        "shadow_color",
        "shadow_blur_size",
        "shadow_x_offset",
        "shadow_y_offset",
        "gradient_flag",
        "gradient_process",
        "single_color",
        "outline_enabled_c",
        "outline_color_c",
        "outline_thickess_c",
        "shadow_flag_c",
        "shadow_color_c",
        "shadow_blur_size_c",
        "shadow_x_offset_c",
        "shadow_y_offset_c",
        "gradient_flag_c",
        "gradient_process_c",
        "single_color_c",
        "mix_option",
    )
    signature = tuple(
        (name, _freeze_cache_value(getattr(otcg_editor, name, None)))
        for name in names
        if hasattr(otcg_editor, name)
    )
    mix_mode_flag = bool(getattr(otcg_editor, "mix_mode_flag", False))
    advanced_toggle = getattr(otcg_editor, "color_advanced_btn", None)
    if advanced_toggle is not None:
        mix_mode_flag = mix_mode_flag and _toggle_checked(advanced_toggle)
    signature += (("mix_mode_flag", mix_mode_flag),)
    if getattr(rd_editor, "_rd_synced_name_color", None) == signature:
        return False
    rd_editor._rd_synced_name_color = signature

    for name in names:
        if hasattr(otcg_editor, name):
            try:
                setattr(rd_editor, name, getattr(otcg_editor, name))
            except Exception:
                pass
    rd_editor.mix_mode_flag = mix_mode_flag
    _safe_call(getattr(rd_editor, "update_mix_param", None))
    inactive_item_names = (
        ("card_name_item", "card_name_list")
        if mix_mode_flag
        else ("mix_name_item", "mix_name_list")
    )
    for name in inactive_item_names:
        value = getattr(rd_editor, name, None)
        if isinstance(value, (list, tuple)):
            for item in value:
                _set_item_visible(item, False)
        else:
            _set_item_visible(value, False)
    return True


def _rd_apply_default_title_color(rd_editor, otcg_editor):
    """按当前卡种校正 RD 的卡名颜色，返回是否真的改了。

    超量（含超量灵摆）的卡框偏深，卡名若还是默认黑就看不清，改用白色；
    其余卡种用数据里原本的颜色。

    这里每次都按卡种算一遍，是因为 _sync_rd_name_color 带签名去重，切换卡种时
    数据那边没有变化、它不会重跑，RD 的 title_color 会残留上一张卡的颜色。
    """
    if rd_editor is None or otcg_editor is None:
        return False
    try:
        from PyQt5.QtGui import QColor

        source = getattr(otcg_editor, "title_color", None)
        if source is None:
            return False
        wanted = QColor(source)
        if str(getattr(rd_editor, "_rd_frame_call_way", "") or "").startswith("超量"):
            if (int(wanted.red()), int(wanted.green()), int(wanted.blue())) == (0, 0, 0):
                wanted = QColor(Qt.white)
        current = getattr(rd_editor, "title_color", None)
        if current is not None and (int(current.red()), int(current.green()), int(current.blue())) == (
            int(wanted.red()), int(wanted.green()), int(wanted.blue())
        ):
            return False
        rd_editor.title_color = wanted
    except Exception:
        return False
    return True


def _sync_rd_effect_layout(rd_editor, otcg_editor):
    if rd_editor is None or otcg_editor is None:
        return
    state = _effect_layout_state(otcg_editor)
    state["first_line_compress"] = False
    _apply_qtext_effect_layout(
        rd_editor,
        state,
        apply_alignment=int(state.get("h_align", 0) or 0) != 0,
    )


def _sync_rd_text_adjust_controls(rd_editor, otcg_editor):
    for slider_name, toggle_name, flag_name in _RD_TEXT_ADJUST_CONTROLS:
        slider = getattr(rd_editor, slider_name, None)
        toggle = getattr(rd_editor, toggle_name, None)
        if slider is None or toggle is None:
            continue
        source = getattr(otcg_editor, slider_name)
        checked = bool(getattr(otcg_editor, flag_name))
        setattr(rd_editor, flag_name, checked)
        if _toggle_checked(toggle) != checked:
            _set_toggle_checked_silent(toggle, checked)
        _set_slider_value_silent(slider, source.value())
        slider.setEnabled(source.isEnabled())
        getattr(rd_editor, "_rd_" + slider_name + "_label").setText(str(source.value()))


def _rd_ruby_previous_sync_text_adjustments(rd_editor, otcg_editor):
    _sync_rd_text_adjust_controls(rd_editor, otcg_editor)
    config = getattr(rd_editor, "config", None)
    base_size = int(getattr(config, "text_size", 45))
    if bool(getattr(otcg_editor, "text_sizeable", False)):
        base_size += _slider_value_from(getattr(otcg_editor, "text_size_slider", None))
    weight = _slider_value_from(getattr(otcg_editor, "text_weight_slider", None)) / 10
    outline_enabled = bool(getattr(otcg_editor, "text_weightable", False)) and weight != 0
    signature = (base_size, outline_enabled, weight)
    if getattr(rd_editor, "_rd_synced_text_adjustments", None) == signature:
        return
    rd_editor._rd_synced_text_adjustments = signature
    _set_text_item_pixel_size(getattr(rd_editor, "text_item", None), base_size)
    for name in ("text_item", "detail_text_item", "_rd_pendulum_text_item"):
        _set_text_item_outline(
            getattr(rd_editor, name, None),
            outline_enabled,
            weight,
        )


def _sync_rd_text_alignments(rd_editor, otcg_editor):
    name_alignments = (
        getattr(Qt, "AlignLeft", 0),
        getattr(Qt, "AlignCenter", 0),
        getattr(Qt, "AlignRight", 0),
    )
    name_index = max(
        0,
        min(
            len(name_alignments) - 1,
            _combo_index_from(getattr(otcg_editor, "name_align_selector", None)),
        ),
    )
    if getattr(rd_editor, "_rd_synced_name_alignment", None) != name_index:
        for name in ("card_name_item", "mix_name_item"):
            _set_text_item_alignment(getattr(rd_editor, name, None), name_alignments[name_index])
        for name in ("card_name_list", "mix_name_list"):
            for item in getattr(rd_editor, name, ()) or ():
                _set_text_item_alignment(item, name_alignments[name_index])
        rd_editor._rd_synced_name_alignment = name_index

    text_index = _combo_index_from(getattr(otcg_editor, "text_align_selector", None))
    text_alignment = (
        getattr(Qt, "AlignJustify", getattr(Qt, "AlignLeft", 0))
        if text_index == 0
        else getattr(Qt, "AlignCenter", 0)
    )
    if getattr(rd_editor, "_rd_synced_text_alignment", None) != text_index:
        _set_text_item_alignment(getattr(rd_editor, "text_item", None), text_alignment)
        rd_editor._rd_synced_text_alignment = text_index
    _set_text_item_alignment(getattr(rd_editor, "_rd_pendulum_text_item", None), text_alignment)


def _prev_custom_sync_rd_overlay_controls(rd_editor, otcg_editor):
    holo_index = max(
        0,
        min(
            len(getattr(getattr(rd_editor, "config", None), "holo_imgs", ())) - 1,
            _combo_index_from(getattr(otcg_editor, "holo_selector", None)),
        ),
    )
    if holo_index >= 0 and getattr(rd_editor, "_rd_synced_holo_index", None) != holo_index:
        _set_combo_index_silent(getattr(rd_editor, "holo_selector", None), holo_index)
        _safe_call(getattr(rd_editor, "holo_change", None), holo_index)
        rd_editor._rd_synced_holo_index = holo_index

    copyright_index = max(
        0,
        min(
            len(getattr(getattr(rd_editor, "config", None), "copyright_svgs", ())) - 1,
            _combo_index_from(getattr(otcg_editor, "copyright_selector", None)),
        ),
    )
    if (
        copyright_index >= 0
        and getattr(rd_editor, "_rd_synced_copyright_index", None) != copyright_index
    ):
        _set_combo_index_silent(
            getattr(rd_editor, "copyright_selector", None),
            copyright_index,
        )
        _safe_call(getattr(rd_editor, "copyright_change", None), copyright_index)
        rd_editor._rd_synced_copyright_index = copyright_index

    rare_options = _RD_ONLY_COMBO_OPTIONS["rare_selector"]
    rare_text = _combo_text_from(getattr(otcg_editor, "rare_selector", None), "N")
    if rare_text not in rare_options:
        rare_text = rare_options[
            max(
                0,
                min(
                    len(rare_options) - 1,
                    _combo_index_from(getattr(otcg_editor, "rare_selector", None)),
                ),
            )
        ]
    if getattr(rd_editor, "_rd_synced_rare_text", None) != rare_text:
        _set_combo_text_silent(getattr(rd_editor, "rare_selector", None), rare_text, 0)
        _safe_call(getattr(rd_editor, "rare_change", None))
        rd_editor._rd_synced_rare_text = rare_text

    holo_visible = _toggle_checked(getattr(otcg_editor, "toggle_holo", None), True)
    if getattr(rd_editor, "_rd_synced_holo_visible", None) != holo_visible:
        _safe_call(getattr(rd_editor, "on_toggle_holo", None), holo_visible)
        rd_editor._rd_synced_holo_visible = holo_visible
    copyright_visible = _toggle_checked(getattr(otcg_editor, "toggle_copy", None), True)
    if getattr(rd_editor, "_rd_synced_copyright_visible", None) != copyright_visible:
        _safe_call(getattr(rd_editor, "on_toggle_copy", None), copyright_visible)
        rd_editor._rd_synced_copyright_visible = copyright_visible


def _sync_rd_detail_color(rd_editor, otcg_editor, is_xyz):
    """按卡种切换详情栏文字颜色，并按等级/阶级换图标。

    超量怪兽（含超量灵摆）一律用阶级图标 —— 官方超量灵摆卡显示的也是 RANK。
    这里统一在这一处判定，_sync_rd_level() 直接复用结果，避免两处判据不一致。

    文字颜色则只有「普通超量」才用白色：超量灵摆的种类栏压在浅色灵摆区上，
    黑字本来就看得清；而普通超量的深色卡框（XYZ.enc）不用白字就完全看不见。
    """
    is_xyz = bool(is_xyz)
    # 保留原义：p15 的等级样式也读这个标志判断是不是超量。
    rd_editor._rd_synced_detail_is_xyz = is_xyz
    rd_editor._rd_detail_is_xyz = is_xyz
    # 与 p14 的 _apply_rd_text_colors 用同一套判据，否则两处谁后跑谁算数。
    white_text = str(getattr(rd_editor, "_rd_frame_call_way", "") or "") in ("连接", "超量")
    item = getattr(rd_editor, "detail_text_item", None)
    if item is not None and getattr(rd_editor, "_rd_synced_detail_white", None) != white_text:
        rd_editor._rd_synced_detail_white = white_text
        _safe_call(
            getattr(item, "setDefaultTextColor", None),
            Qt.white if white_text else Qt.black,
        )
    if is_xyz:
        try:
            import RD_widget

            rank = max(0, min(13, int(getattr(otcg_editor, "current_rank", 0) or 0)))
            level_item = getattr(rd_editor, "level_item", None)
            if level_item is not None:
                level_item.setPixmap(
                    RD_widget.decrypt_image_qpixmap(
                        f"{_RD_RANK_RESOURCE_PREFIX}{rank}.enc"
                    )
                )
        except Exception:
            _tab_log("同步RD阶级图标失败:\n" + traceback.format_exc())


def _sync_rd_level(rd_editor, otcg_editor):
    is_xyz = bool(getattr(rd_editor, "_rd_detail_is_xyz", False))
    level = getattr(otcg_editor, "current_rank" if is_xyz else "current_level", None)
    try:
        level = max(0, min(13, int(level or 0)))
    except Exception:
        level = 0
    signature = (level, is_xyz)
    if getattr(rd_editor, "_rd_synced_level_signature", None) == signature:
        return
    rd_editor._rd_synced_level_signature = signature
    rd_editor._rd_synced_level = level
    rd_editor.current_level = level
    _safe_call(getattr(rd_editor, "display_level_btn", None))
    _safe_call(getattr(rd_editor, "update_level_label", None))
    _safe_call(getattr(rd_editor, "update_level_img", None))
    if is_xyz:
        # update_level_img() 只会贴等级图标，超量必须再补一次阶级图标；
        # 序号可能与等级相同（签名没法反映），所以这里按当前阶级无条件覆盖。
        _sync_rd_detail_color(rd_editor, otcg_editor, True)


def _sync_rd_image(rd_editor, otcg_editor):
    image = getattr(otcg_editor, "card_img", None)
    if image is None:
        return
    cache_identity = getattr(otcg_editor, "_rd_image_cache_token", None)
    image_token = (
        cache_identity or id(image),
        getattr(image, "size", None),
        getattr(image, "mode", None),
        0 if cache_identity else int(getattr(otcg_editor, "_rd_image_generation", 0)),
    )
    if getattr(rd_editor, "_rd_synced_image_token", None) == image_token:
        return
    rd_editor._rd_synced_image_token = image_token
    try:
        config = getattr(rd_editor, "config", None)
        width = int(getattr(config, "card_img_w", 1463))
        height = int(getattr(config, "card_img_h", 1468))
        cache_key = (image_token, width, height)
        pixmap = _bounded_cache_get(_RD_IMAGE_RENDER_CACHE, cache_key)
        if pixmap is None:
            fitted = ImageOps.fit(
                image,
                (width, height),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.0),
            )
            pixmap = _pixmap_from_pillow(fitted)
            _bounded_cache_put(
                _RD_IMAGE_RENDER_CACHE,
                cache_key,
                pixmap,
                _RD_IMAGE_RENDER_CACHE_LIMIT,
            )
        rd_editor.card_img = image
        rd_editor.display_img = pixmap
        card_img_item = getattr(rd_editor, "card_img_item", None)
        if card_img_item is not None:
            card_img_item.setPixmap(pixmap)
            app = getattr(rd_editor, "parent_app", None)
            if getattr(app, "_rd_switch_in_progress", False):
                app._rd_switch_image_commits = int(
                    getattr(app, "_rd_switch_image_commits", 0)
                ) + 1
            card_img_item.setPos(
                int(getattr(config, "card_img_x", 81)),
                int(getattr(config, "card_img_y", 234)),
            )
    except Exception:
        _tab_log("等比裁切RD卡图失败，保留原始变换:\n" + traceback.format_exc())


def _sync_rd_frame_from_otcg(app):
    try:
        otcg_editor = getattr(app, "otcg_widget", None)
        rd_editor = getattr(app, "rd_widget", None)
        if otcg_editor is None or rd_editor is None:
            return
        if not getattr(app, "RD_init", False):
            return

        card_type = _combo_text_from(getattr(otcg_editor, "type_selector", None), "怪兽卡")
        if card_type not in {"怪兽卡", "魔法卡", "陷阱卡"}:
            card_type = "怪兽卡"
        call_way_text = _combo_text_from(getattr(otcg_editor, "info_selector_left", None))
        extra_mid = _combo_text_from(getattr(otcg_editor, "info_selector_mid", None))
        extra_right = _combo_text_from(getattr(otcg_editor, "info_selector_right", None))
        rd_frame_call_way = _rd_frame_call_way_from_otcg(call_way_text, extra_mid, extra_right)
        is_link = card_type == "怪兽卡" and rd_frame_call_way == "连接"
        is_pendulum = card_type == "怪兽卡" and "灵摆" in rd_frame_call_way
        link_arrow_states = (
            _link_arrow_states_from_otcg(otcg_editor) if is_link else (False,) * 8
        )
        link_rating = sum(link_arrow_states) if is_link else 0

        values = {
            "card_type": card_type,
            "race": _combo_text_from(getattr(otcg_editor, "race_selector", None)),
            "call_way": rd_frame_call_way,
            "extra": extra_mid or extra_right,
            "mt_type": _combo_text_from(
                getattr(otcg_editor, "MT_type_selector", None),
                "通常",
            ),
            "name": _text_from(getattr(otcg_editor, "card_name_edit", None)),
            "card_pass": _text_from(getattr(otcg_editor, "card_pass_edit", None)),
            "card_pack": _text_from(getattr(otcg_editor, "card_pack_edit", None)),
            "text": _plain_text_from(getattr(otcg_editor, "text_input", None)),
            "atk": _text_from(getattr(otcg_editor, "ATK_edit", None)),
            "def": _text_from(getattr(otcg_editor, "DEF_edit", None)),
        }
        previous = getattr(rd_editor, "_rd_sync_values", {})
        _sync_rd_custom_detail(rd_editor, otcg_editor)

        def changed(*names):
            return any(previous.get(name) != values[name] for name in names)

        if changed("card_type"):
            _set_combo_text_silent(getattr(rd_editor, "type_selector", None), card_type)
            _safe_call(getattr(rd_editor, "switch_card_type", None))

        _set_line_text_silent(getattr(rd_editor, "card_name_edit", None), values["name"])
        _set_line_text_silent(getattr(rd_editor, "card_pass_edit", None), values["card_pass"])
        _set_line_text_silent(getattr(rd_editor, "card_pack_edit", None), values["card_pack"])
        _set_plain_text_silent(getattr(rd_editor, "text_input", None), values["text"])

        if card_type == "怪兽卡":
            _set_combo_text_silent(getattr(rd_editor, "race_selector", None), values["race"])
            # 下拉里只列 OCG 那 8 项召唤方式；「效果灵摆」这类细分值只用于选卡框
            # （见 _install_rd_frame_key_bridge），不写进下拉的显示值。
            _set_combo_text_silent(
                getattr(rd_editor, "call_way_selector", None),
                call_way_text,
            )
            rd_editor._rd_frame_call_way = rd_frame_call_way
            _set_combo_text_silent(
                getattr(rd_editor, "extra_info_selector", None),
                values["extra"],
            )
            _sync_rd_attribute(rd_editor, getattr(otcg_editor, "current_attribute", "光"))
            # 先定下是不是超量（含超量灵摆），_sync_rd_level 据此在等级/阶级间选择。
            _sync_rd_detail_color(
                rd_editor,
                otcg_editor,
                rd_frame_call_way.startswith("超量"),
            )
            if is_link:
                link_level = max(0, min(8, int(link_rating or 0)))
                rd_editor._rd_synced_level_signature = None
                if getattr(rd_editor, "_rd_synced_level", None) != link_level:
                    rd_editor._rd_synced_level = link_level
                    rd_editor.current_level = link_level
                    _safe_call(getattr(rd_editor, "display_level_btn", None))
                    _safe_call(getattr(rd_editor, "update_level_label", None))
            else:
                _sync_rd_level(rd_editor, otcg_editor)
        else:
            _set_combo_text_silent(
                getattr(rd_editor, "MT_type_selector", None),
                values["mt_type"],
            )
            if changed("card_type", "mt_type"):
                _safe_call(getattr(rd_editor, "update_MT_type", None))

        _set_line_text_silent(getattr(rd_editor, "ATK_edit", None), values["atk"])
        _set_line_text_silent(getattr(rd_editor, "DEF_edit", None), values["def"])
        name_color_changed = _sync_rd_name_color(rd_editor, otcg_editor)
        # 超量的卡名默认用白色（深色卡框上黑字看不清）。
        if _rd_apply_default_title_color(rd_editor, otcg_editor):
            name_color_changed = True
        # 非灵摆卡不显示灵摆编辑区。放在这里而不是灵摆绘制链路里，
        # 是为了让魔法/陷阱卡（不进那段逻辑）也能正确隐藏。
        _sync_pendulum_panel = globals().get("_sync_rd_pendulum_editor_visibility")
        if _sync_pendulum_panel is not None:
            _sync_pendulum_panel(rd_editor, is_pendulum and not is_link)
        _sync_rd_text_adjustments(rd_editor, otcg_editor)
        _sync_rd_overlay_controls(rd_editor, otcg_editor)

        if changed("card_type", "race", "call_way", "extra", "mt_type"):
            _safe_call(getattr(rd_editor, "switch_info", None))
            _safe_call(getattr(rd_editor, "update_detail_info", None))
        if changed("name") or name_color_changed:
            _safe_call(getattr(rd_editor, "update_card_name", None))
        if changed("atk"):
            _safe_call(getattr(rd_editor, "update_ATK", None))
        if changed("def"):
            _safe_call(getattr(rd_editor, "update_DEF", None))
        if changed("text"):
            _safe_call(getattr(rd_editor, "update_text", None))
        if changed("card_pack"):
            _safe_call(getattr(rd_editor, "update_card_pack", None))
        if card_type == "怪兽卡":
            _set_graphics_text(
                getattr(rd_editor, "detail_text_item", None),
                _otcg_detail_text(otcg_editor),
            )
        _apply_rd_pendulum_visuals(rd_editor, is_pendulum and not is_link)
        _sync_rd_pendulum_text(rd_editor, otcg_editor, is_pendulum and not is_link)
        _sync_rd_pendulum_scales(rd_editor, otcg_editor, is_pendulum and not is_link)
        _sync_rd_text_alignments(rd_editor, otcg_editor)
        _sync_rd_effect_layout(rd_editor, otcg_editor)
        _apply_rd_link_visuals(rd_editor, is_link, link_rating, link_arrow_states)
        _sync_rd_image(rd_editor, otcg_editor)
        rd_editor._rd_sync_values = values
    except Exception:
        _tab_log("同步OCG数据到RD卡框失败:\n" + traceback.format_exc())


def _schedule_rd_frame_sync(app):
    try:
        if app is None or getattr(app, "current_mode", None) != 1:
            return
        if getattr(app, "_rd_sync_suspended", False):
            app._rd_sync_pending = True
            return
        timer = getattr(app, "_rd_frame_sync_timer", None)
        if timer is None:
            timer = QTimer(app)
            timer.setSingleShot(True)

            def run():
                try:
                    if getattr(app, "_rd_sync_suspended", False):
                        app._rd_sync_pending = True
                    elif getattr(app, "current_mode", None) == 1:
                        app._rd_sync_pending = False
                        _sync_rd_frame_from_otcg(app)
                except Exception:
                    _tab_log("计划同步RD卡框失败:\n" + traceback.format_exc())

            timer.timeout.connect(run)
            app._rd_frame_sync_timer = timer
            app._rd_frame_sync_callback = run
        timer.start(_RD_FRAME_SYNC_DELAY_MS)
    except Exception:
        pass


def _install_rd_frame_sync_on_editor(editor):
    if editor is None or getattr(editor, "_rd_frame_sync_installed", False):
        return
    editor._rd_frame_sync_installed = True

    def schedule(*args, **kwargs):
        _schedule_rd_frame_sync(getattr(editor, "parent_app", None))

    for signal_owner, signal_name in (
        ("card_name_edit", "textChanged"),
        ("type_selector", "currentIndexChanged"),
        ("race_selector", "currentIndexChanged"),
        ("info_selector_left", "currentIndexChanged"),
        ("info_selector_mid", "currentIndexChanged"),
        ("info_selector_right", "currentIndexChanged"),
        ("MT_type_selector", "currentIndexChanged"),
        ("ATK_edit", "textChanged"),
        ("DEF_edit", "textChanged"),
        ("card_pass_edit", "textChanged"),
        ("card_pack_edit", "textChanged"),
        ("text_input", "textChanged"),
        ("LB_text_edit", "textChanged"),
        ("LB_level_edit", "textChanged"),
        ("detail_custom_edit", "textChanged"),
        ("detail_custom_toggle", "clicked"),
        ("color_advanced_btn", "toggled"),
        ("text_size_slider", "valueChanged"),
        ("text_weight_slider", "valueChanged"),
        ("name_align_selector", "currentIndexChanged"),
        ("text_align_selector", "currentIndexChanged"),
        ("holo_selector", "currentIndexChanged"),
        ("copyright_selector", "currentIndexChanged"),
        ("rare_selector", "currentIndexChanged"),
        ("text_adjust_btn", "toggled"),
        ("text_weight_adjust_btn", "toggled"),
        ("toggle_holo", "toggled"),
        ("toggle_copy", "toggled"),
    ):
        try:
            signal = getattr(getattr(editor, signal_owner), signal_name)
            signal.connect(schedule)
        except Exception:
            pass

    for button_list_name in ("color_btn_list", "color_advanced_list"):
        for button in getattr(editor, button_list_name, ()) or ():
            try:
                button.toggled.connect(schedule)
            except Exception:
                pass

    try:
        getattr(getattr(editor, "parent_app", None).combo_box, "currentIndexChanged").connect(schedule)
    except Exception:
        pass

    for method_name in (
        "after_info_fetch",
        "on_cardpass_return",
        "random_card",
        "on_import_clicked",
        "set_card_img_nocrop",
        "set_card_img_crop",
        "transform_normal_img",
        "transform_LB_img",
        "switch_card_type",
        "switch_template",
        "switch_info",
        "update_detail_info",
        "update_detail_text_only",
        "detail_custom_cliked",
        "attribute_update",
        "display_level_btn",
        "display_rank_btn",
        "update_level_label",
        "update_rank_label",
        "link_btn_clicked",
        "update_link_number",
        "display_link_arrow",
        "hide_link_arrow",
        "update_card_name",
        "update_ATK",
        "update_DEF",
        "update_text",
        "update_lb_level",
        "update_card_pack",
        "color_btn_clicked",
        "advanced_btn_clicked",
        "change_color_mode",
        "text_sizeable_toggle",
        "text_weight_switch",
        "update_text_weight",
        "name_align_change",
        "text_align_change",
        "holo_change",
        "copyright_change",
        "rare_change",
        "on_toggle_holo",
        "on_toggle_copy",
    ):
        method = getattr(editor, method_name, None)
        if method is None or getattr(method, "_rd_frame_sync_wrapped", False):
            continue

        def wrapped(*args, _method=method, _method_name=method_name, **kwargs):
            result = _method(*args, **kwargs)
            if _method_name in {
                "after_info_fetch",
                "on_cardpass_return",
                "random_card",
                "on_import_clicked",
                "set_card_img_nocrop",
                "set_card_img_crop",
                "transform_normal_img",
                "transform_LB_img",
            }:
                rd_editor = getattr(getattr(editor, "parent_app", None), "rd_widget", None)
                if rd_editor is not None:
                    rd_editor._rd_synced_image_token = None
                editor._rd_image_cache_token = None
                editor._rd_image_generation = int(
                    getattr(editor, "_rd_image_generation", 0)
                ) + 1
            schedule()
            return result

        wrapped._rd_frame_sync_wrapped = True
        setattr(editor, method_name, wrapped)


def _patch_rd_resource_check(rd_editor):
    if rd_editor is None or getattr(rd_editor, "_runtime_resource_check_installed", False):
        return
    resources = getattr(getattr(rd_editor, "config", None), "resource", ()) or ()
    if resources and all(runtime_resource_exists(path) for path in resources):
        rd_editor.check_resource = lambda: True
        rd_editor._runtime_resource_check_installed = True


def _initialize_rd_without_demo_image(app):
    rd_editor = getattr(app, "rd_widget", None)
    if rd_editor is None or getattr(app, "RD_init", False):
        return
    original_load_demo = getattr(rd_editor, "load_demo", None)
    if original_load_demo is None:
        rd_editor.init_vis()
        return

    def skip_demo():
        app._rd_demo_image_suppressed = True

    rd_editor.load_demo = skip_demo
    try:
        rd_editor.init_vis()
    finally:
        rd_editor.load_demo = original_load_demo


def _finish_view_transition_cover(app, cover, generation):
    view = getattr(app, "view", None)
    viewport = _safe_call(getattr(view, "viewport", None))
    if cover is not None and viewport is not None:
        _safe_call(getattr(cover, "setGeometry", None), viewport.rect())
        _safe_call(getattr(cover, "raise_", None))
    if generation != getattr(app, "_view_transition_generation", 0):
        return
    _safe_call(getattr(cover, "hide", None))
    _safe_call(getattr(cover, "deleteLater", None))
    app._view_transition_cover = None
    full_update = getattr(view, "FullViewportUpdate", None)
    if full_update is not None:
        _safe_call(getattr(view, "setViewportUpdateMode", None), full_update)
        app._rd_transition_full_repaint = True
    _safe_call(getattr(view, "resetCachedContent", None))
    _safe_call(getattr(viewport, "update", None))

    def restore_optimized_updates():
        optimized_update = getattr(view, "BoundingRectViewportUpdate", None)
        if optimized_update is not None:
            _safe_call(getattr(view, "setViewportUpdateMode", None), optimized_update)
        _safe_call(getattr(view, "resetCachedContent", None))
        _safe_call(getattr(viewport, "update", None))

    QTimer.singleShot(50, restore_optimized_updates)


def _switch_to_rd_frame_only(app):
    view = getattr(app, "view", None)
    viewport = _safe_call(getattr(view, "viewport", None))
    app._view_transition_generation = int(
        getattr(app, "_view_transition_generation", 0)
    ) + 1
    transition_cover = None
    transition_generation = app._view_transition_generation
    app._rd_transition_cover_shown = False
    update_targets = tuple(target for target in (view, viewport) if target is not None)
    previous_update_states = []
    try:
        for target in update_targets:
            try:
                previous_update_states.append((target, bool(target.updatesEnabled())))
            except Exception:
                previous_update_states.append((target, True))
            _safe_call(getattr(target, "setUpdatesEnabled", None), False)
        app._rd_switch_in_progress = True
        app._rd_switch_image_commits = 0
        app._rd_demo_image_suppressed = False
        _patch_rd_resource_check(getattr(app, "rd_widget", None))
        _initialize_rd_without_demo_image(app)
        if not getattr(app, "RD_init", False):
            app.combo_box.setCurrentIndex(getattr(app, "current_mode", 0))
            return

        manager = getattr(app, "card_tab_manager", None)
        if manager is not None:
            _safe_call(
                getattr(manager, "_prepare_current_image_for_mode_switch", None)
            )
            _safe_call(getattr(manager, "_save_current_snapshot", None), full=False)

        _set_rd_only_editor_controls(app, True)
        app.rd_widget._rd_synced_image_token = None
        _sync_rd_frame_from_otcg(app)
        app.view.setScene(app.rd_scene)
        app.view.fitInView(
            app.rd_widget.base_item.boundingRect(),
            Qt.KeepAspectRatio,
        )
        app.stacked_widget.setCurrentIndex(1)
        app.current_mode = 1
    except Exception:
        _tab_log("切换到RD卡框失败:\n" + traceback.format_exc())
        try:
            app.combo_box.setCurrentIndex(getattr(app, "current_mode", 0))
        except Exception:
            pass
    finally:
        app._rd_switch_in_progress = False
        for target, enabled in previous_update_states:
            _safe_call(getattr(target, "setUpdatesEnabled", None), enabled)
        if view is not None:
            _safe_call(getattr(view, "update", None))
            _safe_call(getattr(viewport, "update", None))
        _finish_view_transition_cover(app, transition_cover, transition_generation)
        _schedule_preview_update_restore(app)


def _with_rd_frame_key(rd_widget, apply):
    """让 RD 卡框继续按细分后的召唤方式取值（RDWidget.switch_base_image 调用）。

    换卡框的代码拿召唤方式下拉的文本去 config.base_imgs 里取卡框；而「效果灵摆 / 融合灵摆 …」
    这些细分值已经从下拉里去掉了（只列 OCG 那 8 项）。这里在 apply() 前把细分值临时补进下拉、
    之后立刻撤掉，这样卡框照旧按副类型细分（Pend_Effect / Pend_Fusion …），下拉显示却与 OCG 一致。
    """
    combo = getattr(rd_widget, "call_way_selector", None)
    key = str(getattr(rd_widget, "_rd_frame_call_way", "") or "")
    if combo is None or not key or combo.findText(key) >= 0:
        return apply()
    saved = combo.currentIndex()
    combo.blockSignals(True)
    combo.addItem(key)
    combo.setCurrentIndex(combo.count() - 1)
    try:
        return apply()
    finally:
        combo.removeItem(combo.count() - 1)
        combo.setCurrentIndex(saved)
        combo.blockSignals(False)


def _rd_is_xyz(rd_widget):
    return bool(getattr(rd_widget, "_rd_synced_detail_is_xyz", False))


def _rd_clamped_level(rd_widget):
    try:
        return max(0, min(13, int(getattr(rd_widget, "current_level", 0) or 0)))
    except Exception:
        return 0


def _rd_push_rank_to_otcg(rd_widget):
    otcg_editor = getattr(getattr(rd_widget, "parent_app", None), "otcg_widget", None)
    if otcg_editor is None:
        return
    rank = _rd_clamped_level(rd_widget)
    # 先把签名对上，避免随后的同步把同一个阶级再走一遍等级链路。
    rd_widget._rd_synced_level_signature = (rank, True)
    rd_widget._rd_synced_level = rank
    if getattr(otcg_editor, "current_rank", None) == rank:
        return
    otcg_editor.current_rank = rank
    # 与 OTCGWidget.rank_clicked 的刷新顺序一致（星星按钮、标签、卡面阶级星）。
    _safe_call(getattr(otcg_editor, "display_rank_btn", None))
    _safe_call(getattr(otcg_editor, "update_rank_label", None))
    if rank == 13:
        _safe_call(getattr(otcg_editor, "hide_rank_star", None))
        _safe_call(getattr(otcg_editor, "display_thirdteen_rank", None))
    else:
        _safe_call(getattr(otcg_editor, "hide_thirdteen_rank", None))
        _safe_call(getattr(otcg_editor, "display_rank_star", None))


_RD_FIT_MIN_STRETCH = 60
_RD_FIT_HOST_MIN_STRETCH = 25
_RD_FIT_MIN_FONT_RATIO = 0.32


def _rd_effect_base_px(rd_widget):
    """用户设定的字号（配置字号 + 字号偏移），与 _sync_rd_text_adjustments 同一算法。"""
    config = getattr(rd_widget, "config", None)
    base = int(getattr(config, "text_size", 45) or 45)
    otcg_editor = getattr(getattr(rd_widget, "parent_app", None), "otcg_widget", None)
    if otcg_editor is not None and bool(getattr(otcg_editor, "text_sizeable", False)):
        base += _slider_value_from(getattr(otcg_editor, "text_size_slider", None))
    return max(1, base)


def _rd_effect_layout(rd_widget, text, px, stretch, line_height):
    item = rd_widget.text_item
    font = item.font()
    font.setPixelSize(max(1, int(px)))
    font.setStretch(max(1, int(stretch)))
    item.setFont(font)
    item.setPlainText(text)
    rd_widget.set_line_height(line_height)
    return float(item.boundingRect().height())


def _rd_fit_stretch(rd_widget, text, px, line_height, limit, low, high):
    """在 [low, high] 里二分找放得下的最大横向比例；放不下返回 None。"""
    if _rd_effect_layout(rd_widget, text, px, high, line_height) <= limit:
        return high
    if _rd_effect_layout(rd_widget, text, px, low, line_height) > limit:
        return None
    while high - low > 1:
        middle = (low + high) // 2
        if _rd_effect_layout(rd_widget, text, px, middle, line_height) <= limit:
            low = middle
        else:
            high = middle
    return low


def _rd_refit_effect_text(rd_widget):
    item = getattr(rd_widget, "text_item", None)
    rect = getattr(rd_widget, "text_display_rect", None)
    config = getattr(rd_widget, "config", None)
    text_input = getattr(rd_widget, "text_input", None)
    if item is None or rect is None or config is None or text_input is None:
        return
    text = str(text_input.toPlainText())
    limit = float(rect.height())
    reference_px = float(getattr(config, "text_size", 45) or 45)
    line_num = max(1, int(getattr(config, "text_line_num", 6) or 6))
    reference_line = (float(rd_widget.rect_height) - 2 * float(config.text_margin)) / line_num
    base_px = _rd_effect_base_px(rd_widget)
    min_px = max(4, int(round(base_px * _RD_FIT_MIN_FONT_RATIO)))

    def line_height_for(size):
        return reference_line * size / reference_px

    px = base_px
    for _ in range(40):
        line_height = line_height_for(px)
        stretch = _rd_fit_stretch(rd_widget, text, px, line_height, limit, _RD_FIT_MIN_STRETCH, 100)
        if stretch is not None:
            _rd_effect_layout(rd_widget, text, px, stretch, line_height)
            return
        if px <= min_px:
            break
        # 按压窄到下限时的超出比例估下一个字号（面积约与字号平方成正比），至少减 1
        height = _rd_effect_layout(rd_widget, text, px, _RD_FIT_MIN_STRETCH, line_height)
        ratio = (limit / height) ** 0.5 if height > 0 else 0.9
        px = max(min_px, min(px - 1, int(px * max(0.8, ratio * 0.99))))
    # 最小字号也放不下：退回宿主的做法，继续横向压窄
    line_height = line_height_for(px)
    stretch = _rd_fit_stretch(
        rd_widget, text, px, line_height, limit, _RD_FIT_HOST_MIN_STRETCH, _RD_FIT_MIN_STRETCH
    )
    _rd_effect_layout(rd_widget, text, px, stretch or _RD_FIT_HOST_MIN_STRETCH, line_height)


def _sync_rd_text_adjustments(rd_editor, otcg_editor):
    before = getattr(rd_editor, "_rd_synced_text_adjustments", None)
    result = _rd_effect_fit_previous_sync_text_adjustments(rd_editor, otcg_editor)
    after = getattr(rd_editor, "_rd_synced_text_adjustments", None)
    # 只在字号变化时重排（签名第一项是字号；字重只改描边，不影响排版）
    if after and (not before or after[0] != before[0]):
        _safe_call(getattr(rd_editor, "update_text", None))
    return result


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from effect_layout import _apply_qtext_effect_layout, _effect_layout_state
from rd_panel import (
    _RD_TEXT_ADJUST_CONTROLS,
    _sync_rd_custom_detail,
    _sync_rd_pendulum_editor_visibility,
    _sync_rd_pendulum_scales,
    _sync_rd_pendulum_text,
)
from rd_ruby import _rd_effect_fit_previous_sync_text_adjustments
from mode_styles import _sync_rd_overlay_controls
from diagnostics import _export_rd_control_diagnostic
