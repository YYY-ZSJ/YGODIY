"""效果文本排版：首行压缩、对齐、行高、字距，以及「效果排版」对话框。

由补丁分片 p01、p05、p07、p08、p12 整理而来。
"""

import traceback

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QTextBlockFormat, QTextCursor
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from common import (
    _EDITOR_TEXT_DEBOUNCE_MS,
    _EFFECT_LAYOUT_DEFAULTS,
    _combo_index_from,
    _safe_call,
    _set_combo_index_silent,
    _set_slider_value_silent,
    _set_text_item_alignment,
    _set_toggle_checked_silent,
    _slider_value_from,
    _tab_log,
    _toggle_checked,
)


_EFFECT_LAYOUT_H_ALIGN_LABELS = ("默认", "居左", "居中", "居右", "两端")
_EFFECT_LAYOUT_V_ALIGN_LABELS = ("默认", "顶部", "居中", "底部")
_EFFECT_LAYOUT_LINE_HEIGHT_LABELS = ("自动", "自定义")

_EFFECT_LINE_HEIGHT_MIN = 40
_EFFECT_LINE_HEIGHT_MAX = 260
_EFFECT_LETTER_SPACING_MIN = -100
_EFFECT_LETTER_SPACING_MAX = 200


def _clamp_int(value, minimum, maximum, default):
    try:
        value = int(value)
    except Exception:
        value = int(default)
    return max(int(minimum), min(int(maximum), value))


def _effect_layout_state_from_data(data):
    source = data if isinstance(data, dict) else {}
    return {
        "first_line_compress": bool(
            source.get(
                "effect_first_line_compress",
                _EFFECT_LAYOUT_DEFAULTS["effect_first_line_compress"],
            )
        ),
        "h_align": _clamp_int(
            source.get("effect_h_align", _EFFECT_LAYOUT_DEFAULTS["effect_h_align"]),
            0,
            len(_EFFECT_LAYOUT_H_ALIGN_LABELS) - 1,
            _EFFECT_LAYOUT_DEFAULTS["effect_h_align"],
        ),
        "v_align": _clamp_int(
            source.get("effect_v_align", _EFFECT_LAYOUT_DEFAULTS["effect_v_align"]),
            0,
            len(_EFFECT_LAYOUT_V_ALIGN_LABELS) - 1,
            _EFFECT_LAYOUT_DEFAULTS["effect_v_align"],
        ),
        "line_height_mode": _clamp_int(
            source.get(
                "effect_line_height_mode",
                _EFFECT_LAYOUT_DEFAULTS["effect_line_height_mode"],
            ),
            0,
            len(_EFFECT_LAYOUT_LINE_HEIGHT_LABELS) - 1,
            _EFFECT_LAYOUT_DEFAULTS["effect_line_height_mode"],
        ),
        "line_height": _clamp_int(
            source.get(
                "effect_line_height",
                _EFFECT_LAYOUT_DEFAULTS["effect_line_height"],
            ),
            _EFFECT_LINE_HEIGHT_MIN,
            _EFFECT_LINE_HEIGHT_MAX,
            _EFFECT_LAYOUT_DEFAULTS["effect_line_height"],
        ),
        "letter_spacing": _clamp_int(
            source.get(
                "effect_letter_spacing",
                _EFFECT_LAYOUT_DEFAULTS["effect_letter_spacing"],
            ),
            _EFFECT_LETTER_SPACING_MIN,
            _EFFECT_LETTER_SPACING_MAX,
            _EFFECT_LAYOUT_DEFAULTS["effect_letter_spacing"],
        ),
    }


def _effect_layout_state(editor):
    return _effect_layout_state_from_data(
        {
            "effect_first_line_compress": getattr(
                editor,
                "effect_first_line_compress",
                _EFFECT_LAYOUT_DEFAULTS["effect_first_line_compress"],
            ),
            "effect_h_align": getattr(
                editor,
                "effect_h_align",
                _EFFECT_LAYOUT_DEFAULTS["effect_h_align"],
            ),
            "effect_v_align": getattr(
                editor,
                "effect_v_align",
                _EFFECT_LAYOUT_DEFAULTS["effect_v_align"],
            ),
            "effect_line_height_mode": getattr(
                editor,
                "effect_line_height_mode",
                _EFFECT_LAYOUT_DEFAULTS["effect_line_height_mode"],
            ),
            "effect_line_height": getattr(
                editor,
                "effect_line_height",
                _EFFECT_LAYOUT_DEFAULTS["effect_line_height"],
            ),
            "effect_letter_spacing": getattr(
                editor,
                "effect_letter_spacing",
                _EFFECT_LAYOUT_DEFAULTS["effect_letter_spacing"],
            ),
        }
    )


def _set_effect_layout_state(editor, state):
    if editor is None:
        return
    state = _effect_layout_state_from_data(
        {
            "effect_first_line_compress": state.get("first_line_compress", False),
            "effect_h_align": state.get("h_align", 0),
            "effect_v_align": state.get("v_align", 0),
            "effect_line_height_mode": state.get("line_height_mode", 0),
            "effect_line_height": state.get("line_height", 100),
            "effect_letter_spacing": state.get("letter_spacing", 0),
        }
        if isinstance(state, dict)
        else {}
    )
    editor.effect_first_line_compress = state["first_line_compress"]
    editor.effect_h_align = state["h_align"]
    editor.effect_v_align = state["v_align"]
    editor.effect_line_height_mode = state["line_height_mode"]
    editor.effect_line_height = state["line_height"]
    editor.effect_letter_spacing = state["letter_spacing"]


def _inject_effect_layout_data(editor, data):
    if not isinstance(data, dict):
        return data
    state = _effect_layout_state(editor)
    data.update(
        {
            "effect_first_line_compress": state["first_line_compress"],
            "effect_h_align": state["h_align"],
            "effect_v_align": state["v_align"],
            "effect_line_height_mode": state["line_height_mode"],
            "effect_line_height": state["line_height"],
            "effect_letter_spacing": state["letter_spacing"],
        }
    )
    return data


def _effect_default_h_align_index(editor):
    return _combo_index_from(getattr(editor, "text_align_selector", None), 0)


def _effect_layout_text_align(editor, state):
    index = int(state.get("h_align", 0) or 0)
    if index == 0:
        return "justify" if _effect_default_h_align_index(editor) == 0 else "center"
    return {
        1: "left",
        2: "center",
        3: "right",
        4: "justify",
    }.get(index, "justify")


def _effect_layout_qt_align(editor, state):
    index = int(state.get("h_align", 0) or 0)
    if index == 0:
        return (
            getattr(Qt, "AlignJustify", getattr(Qt, "AlignLeft", 0))
            if _effect_default_h_align_index(editor) == 0
            else getattr(Qt, "AlignCenter", 0)
        )
    return {
        1: getattr(Qt, "AlignLeft", 0),
        2: getattr(Qt, "AlignCenter", 0),
        3: getattr(Qt, "AlignRight", 0),
        4: getattr(Qt, "AlignJustify", getattr(Qt, "AlignLeft", 0)),
    }.get(index, getattr(Qt, "AlignJustify", getattr(Qt, "AlignLeft", 0)))


def _effect_line_height_ratio(state):
    if int(state.get("line_height_mode", 0) or 0) != 1:
        return 1.0
    return max(
        _EFFECT_LINE_HEIGHT_MIN / 100,
        min(_EFFECT_LINE_HEIGHT_MAX / 100, state.get("line_height", 100) / 100),
    )


def _effect_letter_spacing_value(state):
    return max(
        _EFFECT_LETTER_SPACING_MIN / 10,
        min(_EFFECT_LETTER_SPACING_MAX / 10, state.get("letter_spacing", 0) / 10),
    )


def _effect_layout_has_custom_render(state):
    return bool(
        state.get("first_line_compress", False)
        or int(state.get("h_align", 0) or 0) != 0
        or int(state.get("v_align", 0) or 0) != 0
        or int(state.get("line_height_mode", 0) or 0) != 0
        or int(state.get("letter_spacing", 0) or 0) != 0
    )


def _set_font_letter_spacing(item, spacing):
    if item is None:
        return
    try:
        font = QFont(item.font())
        font.setLetterSpacing(QFont.AbsoluteSpacing, float(spacing))
        item.setFont(font)
    except Exception:
        pass


def _set_text_item_line_height(item, state):
    if item is None or int(state.get("line_height_mode", 0) or 0) != 1:
        return
    try:
        cursor = item.textCursor()
        cursor.select(QTextCursor.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            int(round(_effect_line_height_ratio(state) * 100)),
            QTextBlockFormat.ProportionalHeight,
        )
        cursor.setBlockFormat(block_format)
    except Exception:
        pass


def _item_pos_xy(item):
    try:
        pos = item.pos()
        x = pos.x() if callable(getattr(pos, "x", None)) else getattr(pos, "x", 0)
        y = pos.y() if callable(getattr(pos, "y", None)) else getattr(pos, "y", 0)
        return float(x), float(y)
    except Exception:
        return 0.0, 0.0


def _capture_effect_auto_layout(editor):
    compresstor = getattr(editor, "compresstor", None)
    if compresstor is not None:
        try:
            editor._effect_auto_line_height = float(compresstor.lineHeight)
        except Exception:
            pass
    group = getattr(editor, "text_group", None)
    if group is not None:
        editor._effect_auto_group_pos = _item_pos_xy(group)


def _apply_model_letter_spacing(item_list, spacing):
    if not spacing:
        return
    per_line_offset = {}
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        text = str(getattr(ruby, "text", "") or "") if ruby is not None else ""
        if ruby is None:
            continue
        line = getattr(ruby, "line", 0)
        offset = per_line_offset.get(line, 0.0)
        try:
            ruby.x = float(getattr(ruby, "x", 0) or 0) + offset
        except Exception:
            pass
        if text and text != "\n":
            increment = float(spacing) * max(1, len(text))
            per_line_offset[line] = offset + increment


def _line_width_stats(item_list):
    stats = {}
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        if ruby is None or getattr(ruby, "line", -1) < 0:
            continue
        text = str(getattr(ruby, "text", "") or "")
        if not text or text == "\n":
            continue
        try:
            line = int(getattr(ruby, "line", 0))
            width = _model_text_width(ruby, 0)
            char_count = max(1, len(text))
        except Exception:
            continue
        line_width, line_chars = stats.get(line, (0.0, 0))
        stats[line] = (line_width + width, line_chars + char_count)
    return stats


def _fitted_letter_spacing(item_list, desired_spacing, compresstor):
    box_width = float(getattr(compresstor, "width", 0) or 0)
    if box_width <= 0:
        return desired_spacing
    spacing = float(desired_spacing)
    minimum = _EFFECT_LETTER_SPACING_MIN / 10
    for line_width, line_chars in _line_width_stats(item_list).values():
        if line_chars <= 0:
            continue
        max_spacing = (box_width - line_width) / line_chars
        spacing = min(spacing, max_spacing)
    return max(minimum, spacing)


def _line_y_positions(item_list):
    positions = {}
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        if ruby is None or getattr(ruby, "line", -1) < 0:
            continue
        if str(getattr(ruby, "text", "") or "") == "\n":
            continue
        try:
            line = int(getattr(ruby, "line", 0))
            y = float(getattr(ruby, "y", 0) or 0)
        except Exception:
            continue
        positions[line] = min(positions.get(line, y), y)
    return positions


def _median(values):
    values = sorted(values)
    if not values:
        return 0.0
    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (float(values[middle - 1]) + float(values[middle])) / 2


def _apply_model_line_height(item_list, state, compresstor):
    if int(state.get("line_height_mode", 0) or 0) != 1:
        return
    line_y = _line_y_positions(item_list)
    lines = sorted(line_y)
    if len(lines) <= 1:
        return
    diffs = [
        line_y[next_line] - line_y[line]
        for line, next_line in zip(lines, lines[1:])
        if line_y[next_line] > line_y[line]
    ]
    auto_step = _median(diffs)
    if auto_step <= 0:
        auto_step = float(getattr(compresstor, "fontSize", 45) or 45) * float(
            getattr(compresstor, "lineHeight", 1.0) or 1.0
        )
    target_step = max(1.0, auto_step * _effect_line_height_ratio(state))
    first_y = line_y[lines[0]]
    target_y_by_line = {
        line: first_y + index * target_step
        for index, line in enumerate(lines)
    }
    delta_by_line = {
        line: target_y_by_line[line] - line_y[line]
        for line in lines
    }
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        rt = getattr(item, "rt", None)
        if ruby is None:
            continue
        try:
            line = int(getattr(ruby, "line", -1))
        except Exception:
            continue
        if line not in delta_by_line:
            continue
        delta = delta_by_line[line]
        for text_part in (ruby, rt):
            if text_part is None:
                continue
            try:
                text_part.y = float(getattr(text_part, "y", 0) or 0) + delta
            except Exception:
                pass


def _model_text_width(ruby, spacing):
    try:
        text = str(getattr(ruby, "text", "") or "")
        width = float(getattr(ruby, "width", 0) or 0)
        scale = float(getattr(ruby, "scaleX", 1) or 1)
        try:
            original_width = float(getattr(ruby, "originalWidth", 0) or 0)
        except Exception:
            original_width = 0.0
        if original_width > 0:
            width = max(width, original_width * scale)
        spacing_width = max(0, len(text) - 1) * float(spacing)
        if spacing_width < 0 and scale < 1:
            spacing_width *= scale
        return max(0.0, width + spacing_width)
    except Exception:
        return 0.0


def _model_text_part_bounds(text_part, spacing=0, centered=False):
    try:
        text = str(getattr(text_part, "text", "") or "")
        if not text or text == "\n":
            return None
        x = float(getattr(text_part, "x", 0) or 0)
        y = float(getattr(text_part, "y", 0) or 0)
        height = float(getattr(text_part, "height", 0) or 0)
        part_spacing = float(getattr(text_part, "letterSpacing", spacing) or 0)
        width = _model_text_width(text_part, part_spacing if centered else spacing)
        if centered:
            left = x - part_spacing / 2 - width / 2
            right = left + width
            left = min(left, x)
            right = max(right, x + width)
        else:
            left = x
            right = x + width
        return (left, y, right, y + max(0.0, height))
    except Exception:
        return None


def _effect_model_bounds(item_list, spacing=0):
    left = None
    top = None
    right = None
    bottom = None
    for item in item_list or ():
        for text_part, centered in (
            (getattr(item, "ruby", None), False),
            (getattr(item, "rt", None), True),
        ):
            if text_part is None or getattr(text_part, "line", 0) < 0:
                continue
            part_bounds = _model_text_part_bounds(text_part, spacing, centered=centered)
            if part_bounds is None:
                continue
            part_left, part_top, part_right, part_bottom = part_bounds
            left = part_left if left is None else min(left, part_left)
            top = part_top if top is None else min(top, part_top)
            right = part_right if right is None else max(right, part_right)
            bottom = part_bottom if bottom is None else max(bottom, part_bottom)
    if left is None or top is None or right is None or bottom is None:
        return (0.0, 0.0, 0.0, 0.0)
    return (left, top, right, bottom)


def _effect_bounds_fit(item_list, compresstor, spacing):
    left, top, right, bottom = _effect_model_bounds(item_list, spacing)
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    box_width = float(getattr(compresstor, "width", 0) or 0)
    box_height = float(getattr(compresstor, "height", 0) or 0)
    width_ok = box_width <= 0 or width <= box_width + 0.5
    height_ok = box_height <= 0 or height <= box_height + 0.5
    return width_ok and height_ok


def _translate_effect_items(item_list, dx=0, dy=0):
    if not dx and not dy:
        return
    for item in item_list or ():
        for text_part in (getattr(item, "ruby", None), getattr(item, "rt", None)):
            if text_part is None:
                continue
            try:
                text_part.x = float(getattr(text_part, "x", 0) or 0) + float(dx)
            except Exception:
                pass
            try:
                text_part.y = float(getattr(text_part, "y", 0) or 0) + float(dy)
            except Exception:
                pass


def _normalize_effect_items_to_box(item_list, compresstor, spacing):
    box_width = float(getattr(compresstor, "width", 0) or 0)
    box_height = float(getattr(compresstor, "height", 0) or 0)
    if box_width <= 0 and box_height <= 0:
        return

    left, top, right, bottom = _effect_model_bounds(item_list, spacing)
    dx = 0.0
    dy = 0.0
    if box_width > 0:
        if left < 0:
            dx = -left
        if right + dx > box_width:
            dx -= right + dx - box_width
        if left + dx < 0 and right - left <= box_width:
            dx += -(left + dx)
    if box_height > 0:
        if top < 0:
            dy = -top
        if bottom + dy > box_height:
            dy -= bottom + dy - box_height
        if top + dy < 0 and bottom - top <= box_height:
            dy += -(top + dy)
    _translate_effect_items(item_list, dx, dy)


def _apply_model_horizontal_alignment(item_list, state, compresstor, spacing):
    align = _effect_layout_text_align(None, state)
    if align == "justify":
        return
    box_width = float(getattr(compresstor, "width", 0) or 0)
    if box_width <= 0:
        return
    line_bounds = {}
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        if ruby is None or getattr(ruby, "line", -1) < 0:
            continue
        text = str(getattr(ruby, "text", "") or "")
        if text == "\n":
            continue
        try:
            line = int(getattr(ruby, "line", 0))
        except Exception:
            continue
        for text_part, centered in ((ruby, False), (getattr(item, "rt", None), True)):
            if text_part is None:
                continue
            part_bounds = _model_text_part_bounds(
                text_part,
                spacing,
                centered=centered,
            )
            if part_bounds is None:
                continue
            part_left, top, part_right, bottom = part_bounds
            left, current_right = line_bounds.get(line, (part_left, part_right))
            line_bounds[line] = (
                min(left, part_left),
                max(current_right, part_right),
            )
    offsets = {}
    for line, (left, right) in line_bounds.items():
        line_width = max(0.0, right - left)
        remain = max(0.0, box_width - line_width)
        if align == "center":
            offsets[line] = remain / 2 - left
        elif align == "right":
            offsets[line] = remain - left
        else:
            offsets[line] = -left
    for item in item_list or ():
        ruby = getattr(item, "ruby", None)
        rt = getattr(item, "rt", None)
        if ruby is None:
            continue
        try:
            line = int(getattr(ruby, "line", -1))
        except Exception:
            continue
        if line not in offsets:
            continue
        offset = offsets[line]
        for text_part in (ruby, rt):
            if text_part is None:
                continue
            try:
                text_part.x = float(getattr(text_part, "x", 0) or 0) + offset
            except Exception:
                pass


def _apply_rendered_letter_spacing(group, spacing):
    for item in getattr(group, "ruby_items", ()) or ():
        _set_font_letter_spacing(item, spacing)


def _rect_value(rect, method_name, attr_name):
    value = getattr(rect, method_name, None)
    if callable(value):
        return float(value())
    value = getattr(rect, attr_name, None)
    return float(value() if callable(value) else value)


def _rect_to_bounds(rect):
    if rect is None:
        return None
    try:
        return (
            _rect_value(rect, "left", "x"),
            _rect_value(rect, "top", "y"),
            _rect_value(rect, "right", "right"),
            _rect_value(rect, "bottom", "bottom"),
        )
    except Exception:
        pass
    try:
        x = _rect_value(rect, "x", "x")
        y = _rect_value(rect, "y", "y")
        width = _rect_value(rect, "width", "width")
        height = _rect_value(rect, "height", "height")
        return (x, y, x + width, y + height)
    except Exception:
        return None


def _rendered_group_bounds(group):
    for method_name in ("childrenBoundingRect", "boundingRect"):
        rect_getter = getattr(group, method_name, None)
        if not callable(rect_getter):
            continue
        bounds = _rect_to_bounds(rect_getter())
        if bounds is not None:
            return bounds
    return None


def _offset_bounds_into_limit(start, end, limit):
    if limit <= 0:
        return 0.0
    offset = 0.0
    if start < 0:
        offset = -start
    if end + offset > limit:
        offset -= end + offset - limit
    if start + offset < 0 and end - start <= limit:
        offset += -(start + offset)
    return offset


def _apply_group_vertical_alignment(editor, compresstor, group, state, item_list, spacing=0):
    mode = int(state.get("v_align", 0) or 0)
    box_width = float(getattr(compresstor, "width", 0) or 0)
    box_height = float(getattr(compresstor, "height", 0) or 0)
    rendered_bounds = _rendered_group_bounds(group)
    if rendered_bounds is None:
        rendered_bounds = _effect_model_bounds(item_list, spacing)
    left, top, right, bottom = rendered_bounds
    dx = _offset_bounds_into_limit(left, right, box_width)
    content_height = max(0.0, bottom - top)
    if mode <= 1:
        dy = _offset_bounds_into_limit(top, bottom, box_height)
    else:
        free_space = max(0.0, box_height - content_height)
        dy = (free_space / 2 if mode == 2 else free_space) - top
    if box_height > 0:
        if top + dy < 0:
            dy += -(top + dy)
        if bottom + dy > box_height:
            dy -= bottom + dy - box_height
        if top + dy < 0 and content_height <= box_height:
            dy += -(top + dy)
    group_pos_attr = str(state.get("_group_pos_attr", "_effect_auto_group_pos"))
    base_x, base_y = getattr(editor, group_pos_attr, _item_pos_xy(group))
    try:
        group.setPos(base_x + dx, base_y + dy)
    except Exception:
        pass


def _editor_text_weight(editor):
    try:
        if bool(getattr(editor, "text_weightable", False)):
            return _slider_value_from(getattr(editor, "text_weight_slider", None)) / 10
    except Exception:
        pass
    return 0


def _set_effect_font_size(editor, compresstor, group, font_size):
    font_size = max(1, int(round(font_size)))
    if hasattr(compresstor, "setFontSize"):
        _safe_call(getattr(compresstor, "setFontSize", None), font_size)
    else:
        try:
            compresstor.fontSize = font_size
        except Exception:
            pass
    _safe_call(getattr(group, "setRubyFontSize", None), font_size)
    return font_size


def _layout_effect_items(editor, compresstor, group, state, font_size, desired_spacing):
    _set_effect_font_size(editor, compresstor, group, font_size)
    compresstor.compressText()
    item_list = compresstor.getItemList()
    _apply_model_line_height(item_list, state, compresstor)
    spacing = _fitted_letter_spacing(item_list, desired_spacing, compresstor)
    _apply_model_letter_spacing(item_list, spacing)
    _apply_model_horizontal_alignment(item_list, state, compresstor, spacing)
    return item_list, spacing


def _shrink_fit_effect_items(editor, compresstor, group, state, base_font_size, desired_spacing):
    box_width = float(getattr(compresstor, "width", 0) or 0)
    box_height = float(getattr(compresstor, "height", 0) or 0)
    minimum_font_size = max(4, int(round(float(base_font_size) * 0.32)))
    font_size = max(minimum_font_size, int(round(float(base_font_size))))
    best_item_list = None
    best_spacing = desired_spacing

    for _ in range(16):
        item_list, spacing = _layout_effect_items(
            editor,
            compresstor,
            group,
            state,
            font_size,
            desired_spacing,
        )
        best_item_list = item_list
        best_spacing = spacing
        if _effect_bounds_fit(item_list, compresstor, spacing):
            _normalize_effect_items_to_box(item_list, compresstor, spacing)
            break

        left, top, right, bottom = _effect_model_bounds(item_list, spacing)
        content_width = max(1.0, right - left)
        content_height = max(1.0, bottom - top)
        width_ratio = box_width / content_width if box_width > 0 else 1.0
        height_ratio = box_height / content_height if box_height > 0 else 1.0
        ratio = min(width_ratio, height_ratio, 0.94)
        next_font_size = max(minimum_font_size, int(font_size * max(0.65, ratio * 0.96)))
        if next_font_size >= font_size:
            next_font_size = font_size - 1
        if next_font_size < minimum_font_size or next_font_size == font_size:
            break
        font_size = next_font_size

    editor._effect_fitted_font_size = font_size
    editor._effect_fitted_letter_spacing = best_spacing
    if best_item_list:
        _normalize_effect_items_to_box(best_item_list, compresstor, best_spacing)
    return best_item_list or [], best_spacing


def _fit_effect_items(editor, compresstor, group, state, base_font_size, desired_spacing):
    return _shrink_fit_effect_items(
        editor,
        compresstor,
        group,
        state,
        base_font_size,
        desired_spacing,
    )


def _apply_otcg_effect_layout(editor, state):
    compresstor = getattr(editor, "compresstor", None)
    group = getattr(editor, "text_group", None)
    if compresstor is None or group is None:
        return False
    _capture_effect_auto_layout(editor)
    try:
        compresstor.firstLineCompress = bool(state.get("first_line_compress", False))
    except Exception:
        pass
    try:
        compresstor.textAlign = _effect_layout_text_align(editor, state)
    except Exception:
        pass
    try:
        base_line_height = float(
            getattr(editor, "_effect_auto_line_height", compresstor.lineHeight)
        )
        compresstor.lineHeight = base_line_height
    except Exception:
        pass
    try:
        base_font_size = int(getattr(compresstor, "fontSize", 45) or 45)
        desired_spacing = _effect_letter_spacing_value(state)
        item_list, spacing = _fit_effect_items(
            editor,
            compresstor,
            group,
            state,
            base_font_size,
            desired_spacing,
        )
        group.setTexts(item_list, _editor_text_weight(editor), compresstor.rtZoomRatio)
        _apply_rendered_letter_spacing(group, spacing)
        _apply_group_vertical_alignment(
            editor,
            compresstor,
            group,
            state,
            item_list,
            spacing,
        )
    except Exception:
        _tab_log("应用OCG效果排版失败:\n" + traceback.format_exc())
    return True


def _apply_qtext_effect_layout(editor, state, apply_alignment=True):
    items = [
        getattr(editor, "text_item", None),
        getattr(editor, "lb_text_item", None),
    ]
    spacing = _effect_letter_spacing_value(state)
    alignment = _effect_layout_qt_align(editor, state)
    for item in items:
        if item is None:
            continue
        if apply_alignment:
            _set_text_item_alignment(item, alignment)
        _set_text_item_line_height(item, state)
        _set_font_letter_spacing(item, spacing)
    return any(item is not None for item in items)


def _apply_effect_layout_to_editor(editor, schedule_rd=False):
    if editor is None:
        return
    state = _effect_layout_state(editor)
    if not _effect_layout_has_custom_render(state):
        return
    applied = _apply_otcg_effect_layout(editor, state)
    if not applied:
        applied = _apply_qtext_effect_layout(editor, state)
    if schedule_rd and applied:
        _schedule_rd_frame_sync(getattr(editor, "parent_app", None))


def _refresh_effect_text_layout(editor, schedule_rd=True):
    update_text = getattr(editor, "update_text", None)
    if update_text is None:
        _apply_effect_layout_to_editor(editor, schedule_rd=schedule_rd)
        return
    if getattr(editor, "_effect_layout_refreshing", False):
        _apply_effect_layout_to_editor(editor, schedule_rd=schedule_rd)
        return
    editor._effect_layout_refreshing = True
    try:
        update_text()
    finally:
        editor._effect_layout_refreshing = False
    _apply_effect_layout_to_editor(editor, schedule_rd=schedule_rd)


def _schedule_effect_layout_refresh(editor, delay=0, schedule_rd=True):
    try:
        QTimer.singleShot(
            int(delay),
            lambda editor=editor, schedule_rd=schedule_rd: _apply_effect_layout_to_editor(
                editor,
                schedule_rd=schedule_rd,
            ),
        )
    except Exception:
        _apply_effect_layout_to_editor(editor, schedule_rd=schedule_rd)


def _make_effect_layout_toggle(parent, checked):
    try:
        from customComponents import ToggleButton

        toggle = ToggleButton(parent)
        toggle.is_checked = bool(checked)
        _safe_call(getattr(toggle, "animate_circle", None))
        _safe_call(getattr(toggle, "update", None))
        return toggle
    except Exception:
        toggle = QCheckBox(parent)
        toggle.setChecked(bool(checked))
        return toggle


def _effect_toggle_signal(toggle):
    for name in ("toggled", "clicked", "stateChanged"):
        try:
            return getattr(toggle, name)
        except Exception:
            pass
    return None


def _install_effect_combo_items(combo, labels):
    try:
        combo.clear()
        combo.addItems(list(labels))
    except Exception:
        for label in labels:
            try:
                combo.addItem(label)
            except Exception:
                pass


class _EffectLayoutDialog(QDialog):
    def __init__(self, editor):
        super().__init__(getattr(editor, "parent_app", None) or editor)
        self.editor = editor
        self.setWindowTitle("效果排版")
        self.setMinimumWidth(350)
        state = _effect_layout_state(editor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(9)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("首行压缩", self))
        self.first_line_toggle = _make_effect_layout_toggle(
            self,
            state["first_line_compress"],
        )
        top_row.addWidget(self.first_line_toggle)
        top_row.addSpacing(14)
        top_row.addWidget(QLabel("水平对齐", self))
        self.h_align_combo = QComboBox(self)
        _install_effect_combo_items(self.h_align_combo, _EFFECT_LAYOUT_H_ALIGN_LABELS)
        self.h_align_combo.setCurrentIndex(state["h_align"])
        top_row.addWidget(self.h_align_combo, 1)
        top_row.addWidget(QLabel("垂直对齐", self))
        self.v_align_combo = QComboBox(self)
        _install_effect_combo_items(self.v_align_combo, _EFFECT_LAYOUT_V_ALIGN_LABELS)
        self.v_align_combo.setCurrentIndex(state["v_align"])
        top_row.addWidget(self.v_align_combo, 1)
        layout.addLayout(top_row)

        line_mode_row = QHBoxLayout()
        line_mode_row.addWidget(QLabel("文本行高", self))
        self.line_height_mode_combo = QComboBox(self)
        _install_effect_combo_items(
            self.line_height_mode_combo,
            _EFFECT_LAYOUT_LINE_HEIGHT_LABELS,
        )
        self.line_height_mode_combo.setCurrentIndex(state["line_height_mode"])
        line_mode_row.addWidget(self.line_height_mode_combo)
        layout.addLayout(line_mode_row)

        line_row = QHBoxLayout()
        self.line_height_label = QLabel("行高: 1.00", self)
        line_row.addWidget(self.line_height_label)
        self.line_height_slider = QSlider(Qt.Horizontal, self)
        self.line_height_slider.setRange(
            _EFFECT_LINE_HEIGHT_MIN,
            _EFFECT_LINE_HEIGHT_MAX,
        )
        self.line_height_slider.setValue(state["line_height"])
        line_row.addWidget(self.line_height_slider, 1)
        layout.addLayout(line_row)

        spacing_row = QHBoxLayout()
        self.letter_spacing_label = QLabel("间距: 0.0", self)
        spacing_row.addWidget(self.letter_spacing_label)
        self.letter_spacing_slider = QSlider(Qt.Horizontal, self)
        self.letter_spacing_slider.setRange(
            _EFFECT_LETTER_SPACING_MIN,
            _EFFECT_LETTER_SPACING_MAX,
        )
        self.letter_spacing_slider.setValue(state["letter_spacing"])
        spacing_row.addWidget(self.letter_spacing_slider, 1)
        layout.addLayout(spacing_row)

        self.close_button = QPushButton("关闭", self)
        layout.addWidget(self.close_button)

        self._connect_signals()
        self._sync_labels()

    def _connect_signals(self):
        signal = _effect_toggle_signal(self.first_line_toggle)
        if signal is not None:
            try:
                signal.connect(self._on_changed)
            except Exception:
                pass
        for widget in (
            self.h_align_combo,
            self.v_align_combo,
            self.line_height_mode_combo,
        ):
            try:
                widget.currentIndexChanged.connect(self._on_changed)
            except Exception:
                pass
        for widget in (
            self.line_height_slider,
            self.letter_spacing_slider,
        ):
            try:
                widget.valueChanged.connect(self._on_changed)
            except Exception:
                pass
        self.close_button.clicked.connect(self.close)

    def _sync_labels(self):
        try:
            self.line_height_label.setText(
                f"行高: {self.line_height_slider.value() / 100:.2f}"
            )
            self.line_height_slider.setEnabled(
                self.line_height_mode_combo.currentIndex() == 1
            )
            self.letter_spacing_label.setText(
                f"间距: {self.letter_spacing_slider.value() / 10:.1f}"
            )
        except Exception:
            pass

    def _on_changed(self, *args):
        state = {
            "first_line_compress": _toggle_checked(self.first_line_toggle),
            "h_align": self.h_align_combo.currentIndex(),
            "v_align": self.v_align_combo.currentIndex(),
            "line_height_mode": self.line_height_mode_combo.currentIndex(),
            "line_height": self.line_height_slider.value(),
            "letter_spacing": self.letter_spacing_slider.value(),
        }
        _set_effect_layout_state(self.editor, state)
        self._sync_labels()
        _refresh_effect_text_layout(self.editor, schedule_rd=True)


def _show_effect_layout_dialog(editor):
    try:
        dialog = getattr(editor, "_effect_layout_dialog", None)
        if dialog is None or not bool(dialog.isVisible()):
            dialog = _EffectLayoutDialog(editor)
            editor._effect_layout_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    except Exception:
        _tab_log("打开效果排版窗口失败:\n" + traceback.format_exc())


def _sync_effect_layout_controls(editor):
    state = _effect_layout_state(editor)
    _set_toggle_checked_silent(
        getattr(editor, "effect_first_line_toggle", None),
        state["first_line_compress"],
    )
    _set_combo_index_silent(
        getattr(editor, "effect_h_align_combo", None),
        state["h_align"],
    )
    _set_combo_index_silent(
        getattr(editor, "effect_v_align_combo", None),
        state["v_align"],
    )
    _set_combo_index_silent(
        getattr(editor, "effect_line_height_mode_combo", None),
        state["line_height_mode"],
    )
    _set_slider_value_silent(
        getattr(editor, "effect_line_height_slider", None),
        state["line_height"],
    )
    _set_slider_value_silent(
        getattr(editor, "effect_letter_spacing_slider", None),
        state["letter_spacing"],
    )
    dialog = getattr(editor, "_effect_layout_dialog", None)
    if dialog is not None:
        _set_toggle_checked_silent(
            getattr(dialog, "first_line_toggle", None),
            state["first_line_compress"],
        )
        _set_combo_index_silent(getattr(dialog, "h_align_combo", None), state["h_align"])
        _set_combo_index_silent(getattr(dialog, "v_align_combo", None), state["v_align"])
        _set_combo_index_silent(
            getattr(dialog, "line_height_mode_combo", None),
            state["line_height_mode"],
        )
        _set_slider_value_silent(
            getattr(dialog, "line_height_slider", None),
            state["line_height"],
        )
        _set_slider_value_silent(
            getattr(dialog, "letter_spacing_slider", None),
            state["letter_spacing"],
        )
        _safe_call(getattr(dialog, "_sync_labels", None))


def _install_effect_layout_controls(editor):
    if editor is None or getattr(editor, "_effect_layout_controls_installed", False):
        return
    _set_effect_layout_state(editor, _effect_layout_state(editor))
    try:
        button = QPushButton("效果排版", editor)
        button.setToolTip("设置效果文本的对齐、行高与文字间距")
        button.clicked.connect(lambda *args, editor=editor: _show_effect_layout_dialog(editor))
        editor.effect_layout_btn = button
        target_layout = getattr(editor, "align_box", None) or getattr(
            editor,
            "text_ctrl_hbox",
            None,
        )
        if target_layout is not None:
            target_layout.addWidget(button)
    except Exception:
        pass

    for method_name in ("update_text",):
        method = getattr(editor, method_name, None)
        if method is None or getattr(method, "_effect_layout_wrapped", False):
            continue

        def wrapped_update_text(*args, _method=method, **kwargs):
            result = _method(*args, **kwargs)
            if not getattr(editor, "_effect_layout_refreshing", False):
                _apply_effect_layout_to_editor(editor, schedule_rd=False)
            return result

        wrapped_update_text._effect_layout_wrapped = True
        setattr(editor, method_name, wrapped_update_text)

    def schedule(*args, editor=editor):
        _schedule_effect_layout_refresh(
            editor,
            _EDITOR_TEXT_DEBOUNCE_MS + 20,
            schedule_rd=True,
        )

    for signal_owner, signal_name in (
        ("text_input", "textChanged"),
        ("text_size_slider", "valueChanged"),
        ("text_weight_slider", "valueChanged"),
        ("text_align_selector", "currentIndexChanged"),
        ("full_effect_toggle", "toggled"),
        ("full_effect_toggle", "clicked"),
    ):
        try:
            getattr(getattr(editor, signal_owner), signal_name).connect(schedule)
        except Exception:
            pass

    editor._effect_layout_controls_installed = True
    _sync_effect_layout_controls(editor)
    _schedule_effect_layout_refresh(editor, 0, schedule_rd=False)


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_frame import _schedule_rd_frame_sync
