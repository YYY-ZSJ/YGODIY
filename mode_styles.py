"""OCG/TCG、RD、漫画卡三模式各自的显示设置（随卡保存在 _mode_styles）与 RD 语言下拉。

由补丁分片 p34 整理而来。
"""

import copy

from common import _call_original, _safe_call


_MODE_STYLES_KEY = "_mode_styles"
_MODE_STYLE_KEYS = (
    "language", "translation", "template", "tc_type",
    "color_flag", "color_option", "title_color", "color_advanced_activated",
    "mix_mode_flag", "mix_option",
    "text_sizeable", "text_size_change", "text_weightable", "text_weight_change",
    "effect_first_line_compress", "effect_h_align", "effect_v_align",
    "effect_line_height_mode", "effect_line_height", "effect_letter_spacing",
    "holo", "copyright", "rare", "watermark",
    "cardpass_vis", "cardpack_vis", "holo_vis", "copyright_vis", "round_corner",
    "attr_hide", "full_effect", "name_align", "text_align", "cn_atk_def_flag",
)
_MODE_STYLE_PREFIXES = ("outline_", "shadow_", "gradient_", "single_color")
_RD_PANEL_STYLE_WIDGETS = (
    "holo_selector", "copyright_selector", "rare_selector", "water_selector",
    "name_align_selector", "text_align_selector",
)
_RD_PANEL_KEY = "rd_panel"


def _mode_style_key_of(app, index=None):
    """OCG 编辑器参与的三个模式的名字；FC / 卡背 / 旧版卡返回 None。"""
    if index is None:
        index = getattr(app, "current_mode", 0)
    if index == 0:
        return "ocg"
    if index == 1:
        return "rd"
    if index == getattr(app, "_manga_mode_index", -2):
        return "manga"
    if index == getattr(app, "_workbench_mode_index", -2):
        return "ocg"   # DIY 工作台显示和编辑的就是 OCG/TCG 卡
    return None


def _active_style_key(app):
    # 在 FC/卡背/旧版卡模式下，OCG 编辑器里留着的是最后一个 OCG 系模式的设置
    return getattr(app, "_style_mode_key", None) or "ocg"


def _is_style_key(key):
    return key in _MODE_STYLE_KEYS or key.startswith(_MODE_STYLE_PREFIXES)


def _extract_style(data):
    return {key: copy.deepcopy(value) for key, value in data.items() if _is_style_key(key)}


def _rd_panel_style(app):
    rd_widget = getattr(app, "rd_widget", None)
    style = {}
    for name in _RD_PANEL_STYLE_WIDGETS:
        widget = getattr(rd_widget, name, None)
        if widget is not None:
            try:
                style[name] = str(widget.currentText())
            except Exception:
                pass
    return style


def _apply_rd_panel_style(app, style):
    rd_widget = getattr(app, "rd_widget", None)
    if rd_widget is None or not isinstance(style, dict):
        return
    for name, text in style.items():
        widget = getattr(rd_widget, name, None)
        if widget is None:
            continue
        try:
            index = widget.findText(str(text))
            if index >= 0 and index != widget.currentIndex():
                widget.setCurrentIndex(index)
        except Exception:
            pass


def _store_mode_style(manager, data):
    """收集卡片数据之后：把当前模式的设置存入 _mode_styles，基本字段保持 OCG 的。"""
    if not isinstance(data, dict):
        return data
    app = manager.app
    mode_key = _active_style_key(app)
    tab = manager._current_tab() if hasattr(manager, "_current_tab") else None
    stored = (tab or {}).get("data") or {}
    # 完整快照走宿主的「导出数据」，导出的 JSON 里没有 _mode_styles；
    # 从这张卡已保存的数据接回来，否则其它模式的设置会被整个冲掉。
    styles = copy.deepcopy(data.get(_MODE_STYLES_KEY) or stored.get(_MODE_STYLES_KEY) or {})
    current = _extract_style(data)
    styles[mode_key] = current
    if mode_key == "rd":
        styles[_RD_PANEL_KEY] = _rd_panel_style(app)
    if mode_key != "ocg":
        # 基本字段始终是 OCG 的设置
        ocg_style = styles.get("ocg")
        if ocg_style is None:
            # 这张卡还没在 OCG 模式下保存过：沿用旧数据里的基本字段
            ocg_style = _extract_style(stored) if stored else current
            styles["ocg"] = ocg_style
        for key in list(data.keys()):
            if _is_style_key(key):
                data.pop(key, None)
        data.update(copy.deepcopy(ocg_style))
    data[_MODE_STYLES_KEY] = styles
    return data


def _data_for_mode(data, mode_key):
    """套用卡片数据前：用目标模式的那份设置覆盖基本字段（不改原数据）。"""
    if not isinstance(data, dict) or mode_key in (None, "ocg"):
        return data
    style = (data.get(_MODE_STYLES_KEY) or {}).get(mode_key)
    if not style:
        return data
    merged = dict(data)
    for key in list(merged.keys()):
        if _is_style_key(key):
            merged.pop(key, None)
    merged.update(copy.deepcopy(style))
    return merged


# ---------------------------------------------------------------------------
# OCG→RD 的防伪/版权/罕贵同步：RD 面板有自己的设置后就以它为准
# ---------------------------------------------------------------------------
# p09 的 _sync_rd_overlay_controls 只要发现 OCG 的下标变了，就把 OCG 的值灌进
# RD 面板。现在切换模式会套用不同的设置，OCG 的值本来就会变，于是 RD 面板刚恢复
# 的设置又被覆盖。卡片已有 RD 面板设置时，传给原函数的「OCG 编辑器」换成代理：
# 三个样式下拉取 RD 面板自己的控件（同步成自己，相当于不动），其余（防伪/版权
# 显示开关等）照旧取 OCG 编辑器——RD 模式下它存的就是 RD 那份设置。
_RD_SELF_SYNCED_SELECTORS = ("holo_selector", "copyright_selector", "rare_selector")


class _RdOverlayProxy:
    def __init__(self, rd_editor, otcg_editor):
        self._rd_editor = rd_editor
        self._otcg_editor = otcg_editor

    def __getattr__(self, name):
        if name in _RD_SELF_SYNCED_SELECTORS:
            return getattr(self._rd_editor, name)
        return getattr(self._otcg_editor, name)


def _sync_rd_overlay_controls(rd_editor, otcg_editor):
    app = getattr(rd_editor, "parent_app", None)
    if getattr(app, "_rd_panel_independent", False):
        return _sync_rd_overlay_controls_with_customization(rd_editor, _RdOverlayProxy(rd_editor, otcg_editor))
    return _sync_rd_overlay_controls_with_customization(rd_editor, otcg_editor)


# ---------------------------------------------------------------------------
# RD 的语言下拉（RD 面板原本没有语言设置，绘制时直接用 OCG 编辑器的语言）
# ---------------------------------------------------------------------------
def _rd_language_bar_sync(app):
    bar = getattr(app, "_rd_language_bar", None)
    editor = getattr(app, "otcg_widget", None)
    if bar is None or editor is None:
        return
    blocked = bar.selector.blockSignals(True)
    try:
        bar.selector.setCurrentIndex(editor.lan_selector.currentIndex())
    finally:
        bar.selector.blockSignals(blocked)


def _rd_language_changed(app, index):
    editor = getattr(app, "otcg_widget", None)
    if editor is None or index < 0:
        return
    editor.lan_selector.setCurrentIndex(index)
    # RD 卡框随 OCG 编辑器的语言重画
    _safe_call(globals().get("_schedule_rd_frame_sync"), app)


def _translate_previous_install_rd_language_bar(app):
    if getattr(app, "_rd_language_bar", None) is not None:
        return
    from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

    combo = getattr(app, "combo_box", None)
    editor = getattr(app, "otcg_widget", None)
    panel = combo.parentWidget() if combo is not None else None
    layout = panel.layout() if panel is not None else None
    if layout is None or editor is None:
        return
    bar = QWidget(panel)
    row = QHBoxLayout(bar)
    row.setContentsMargins(4, 2, 4, 2)
    row.addWidget(QLabel("语言"))
    bar.selector = QComboBox(bar)
    bar.selector.addItems([editor.lan_selector.itemText(i) for i in range(editor.lan_selector.count())])
    row.addWidget(bar.selector, 1)
    layout.insertWidget(layout.indexOf(combo) + 1, bar)
    bar.setVisible(False)
    app._rd_language_bar = bar
    _rd_language_bar_sync(app)
    bar.selector.currentIndexChanged.connect(lambda index: _rd_language_changed(app, index))


# ---------------------------------------------------------------------------
# 模式切换
# ---------------------------------------------------------------------------
def _mode_style_switch(app, index, previous_switch):
    old_key = _active_style_key(app) if getattr(app, "_style_mode_key", None) else None
    new_key = _mode_style_key_of(app, index)
    manager = getattr(app, "card_tab_manager", None)
    if manager is not None and old_key and new_key and old_key != new_key:
        # 按旧模式保存一次，把它的显示设置写进 _mode_styles
        _safe_call(getattr(manager, "_save_current_snapshot", None), full=False)
    result = _call_original(previous_switch, app, (index,), {})
    bar = getattr(app, "_rd_language_bar", None)
    if bar is not None:
        bar.setVisible(getattr(app, "current_mode", None) == 1)
    if new_key is None or getattr(app, "current_mode", None) != index:
        return result
    app._style_mode_key = new_key
    if manager is not None and old_key and old_key != new_key:
        tab = manager._current_tab()
        if tab is not None and isinstance(tab.get("data"), dict):
            # 用新模式的那份设置重新套用当前卡
            manager._apply_editor_data(tab["data"])
            refresh = globals().get("_manga_refresh")
            if new_key == "manga" and refresh is not None:
                refresh(app, force=True)
    _rd_language_bar_sync(app)
    return result


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_frame import _schedule_rd_frame_sync
from customization import _sync_rd_overlay_controls_with_customization
from manga import _manga_refresh
