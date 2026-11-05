"""OCG/TCG 与旧版卡编辑器的初始化补充：清空演示卡、输入防抖、查卡竞态保护等。

由补丁分片 p01、p09、p12、p21、p23 整理而来。
"""

import threading
import traceback

from PyQt5.QtCore import QTimer

from common import (
    _EDITOR_TEXT_DEBOUNCE_MS,
    _bounded_cache_get,
    _bounded_cache_put,
    _combo_text_from,
    _safe_call,
    _set_line_text_silent,
    _set_plain_text_silent,
    _tab_log,
    _text_from,
    _toggle_checked,
)


_BASE_IMAGE_CACHE_LIMIT = 6

_EDITOR_SHORT_DEBOUNCE_MS = 45


def _normalized_card_pass(value):
    return str(value or "").strip().lstrip("0") or "0"


def _install_fetch_race_guard(editor):
    if editor is None or getattr(editor, "_fetch_race_guard_installed", False):
        return
    fetch_info = getattr(editor, "fetch_info", None)
    after_info_fetch = getattr(editor, "after_info_fetch", None)
    if fetch_info is None or after_info_fetch is None:
        return
    editor._fetch_race_guard_installed = True
    editor._fetch_lock = threading.RLock()
    editor._last_completed_fetch_pass = None
    editor._completed_fetch_generation = 0
    editor._applied_fetch_generation = 0

    def guarded_fetch_info(*args, **kwargs):
        with editor._fetch_lock:
            requested = _normalized_card_pass(
                _text_from(getattr(editor, "card_pass_edit", None))
            )
            try:
                return fetch_info(*args, **kwargs)
            except Exception:
                # 查卡失败（联网出错等）也算完成一次，并标记为无效：
                # 否则下面的 after_info_fetch 会把它当成「已应用过」直接返回，
                # 按钮一直禁用、加载动画一直转。异常继续抛给 p33 的 Worker 保护记录。
                fetcher = getattr(editor, "info_fetcher", None)
                if fetcher is not None:
                    try:
                        fetcher.valid = False
                    except Exception:
                        pass
                raise
            finally:
                editor._last_completed_fetch_pass = requested
                editor._completed_fetch_generation += 1

    def guarded_after_info_fetch(*args, **kwargs):
        with editor._fetch_lock:
            completed = getattr(editor, "_last_completed_fetch_pass", None)
            generation = int(getattr(editor, "_completed_fetch_generation", 0))
            current = _normalized_card_pass(
                _text_from(getattr(editor, "card_pass_edit", None))
            )
            if completed is not None and completed != current:
                editor._ignored_stale_fetches = int(
                    getattr(editor, "_ignored_stale_fetches", 0)
                ) + 1
                _safe_call(
                    getattr(getattr(editor, "parent_app", None), "hide_loading_gif", None)
                )
                for name in ("name_search_btn", "card_pass_btn", "random_btn"):
                    _safe_call(getattr(getattr(editor, name, None), "setEnabled", None), True)
                return None
            if generation and generation == int(
                getattr(editor, "_applied_fetch_generation", 0)
            ):
                return None
            result = after_info_fetch(*args, **kwargs)
            editor._applied_fetch_generation = generation
            return result

    guarded_fetch_info._fetch_race_guard_wrapped = True
    guarded_after_info_fetch._fetch_race_guard_wrapped = True
    editor.fetch_info = guarded_fetch_info
    editor.after_info_fetch = guarded_after_info_fetch


def _install_editor_input_debounce(editor):
    if editor is None or getattr(editor, "_input_debounce_installed", False):
        return
    editor._input_debounce_installed = True
    timers = []

    def debounce(signal_owner, signal_name, method_name, delay):
        owner = getattr(editor, signal_owner, None)
        method = getattr(editor, method_name, None)
        if owner is None or method is None:
            return
        try:
            signal = getattr(owner, signal_name)
            signal.disconnect(method)
        except Exception:
            return

        timer = QTimer(editor)
        timer.setSingleShot(True)
        timer.setInterval(delay)
        timer.timeout.connect(method)
        if signal_owner == "detail_custom_edit":
            # 防抖完成后再同步，确保 RD 读取的是刚生成的详情文本。
            timer.timeout.connect(
                lambda: _schedule_rd_frame_sync(getattr(editor, "parent_app", None))
            )

        def schedule(*args, _timer=timer):
            _timer.start()

        signal.connect(schedule)
        timers.append((timer, schedule))

    for signal_owner, method_name in (
        ("card_name_edit", "update_card_name"),
        ("text_input", "update_text"),
        ("detail_custom_edit", "update_detail_text_only"),
    ):
        debounce(
            signal_owner,
            "textChanged",
            method_name,
            _EDITOR_TEXT_DEBOUNCE_MS,
        )

    # 卡密 / 卡包刻意不在这里：OTCGWidget 里这两条原本就是
    # textChanged -> update_card_pass / update_card_pack 的直接连接，
    # 两个方法都只是给一个小文本项 setPlainText，没有整段重排的开销。
    # 换成定时器反而会丢掉「程序化写入卡片」这条路径的刷新：
    # _apply_editor_data 应用卡片数据后会停掉全部防抖计时器，
    # 卡面的卡密 / 卡包就停在上一次的值，切卡也不跟着变。
    for signal_owner, signal_name, method_name in (
        ("ATK_edit", "textChanged", "update_ATK"),
        ("DEF_edit", "textChanged", "update_DEF"),
        ("LB_level_edit", "textChanged", "update_lb_level"),
        ("text_size_slider", "valueChanged", "update_text_size"),
        ("text_weight_slider", "valueChanged", "update_text_weight"),
    ):
        debounce(
            signal_owner,
            signal_name,
            method_name,
            _EDITOR_SHORT_DEBOUNCE_MS,
        )

    editor._input_debounce_timers = timers


def _base_image_signature(editor):
    return (
        getattr(editor, "current_template", None),
        getattr(editor, "card_type", None),
        getattr(editor, "detail_call_way", None),
        getattr(editor, "detail_extra1", None),
        _combo_text_from(getattr(editor, "info_selector_left", None)),
        _toggle_checked(getattr(editor, "LB_Zack_toggle", None)),
    )


def _install_base_image_cache(editor):
    method = getattr(editor, "switch_base_image", None)
    if method is None or getattr(method, "_base_image_cache_wrapped", False):
        return
    cache = {}

    # 宿主 switch_base_image 同时换卡框图（base_item）和超框遮罩图（overframe_mask 的
    # pixmap，按卡框选）。两张图都要缓存；以前存的是 overframe_mask 这个图元本身，
    # 命中缓存时遮罩图不变，非灵摆卡开超框会露出初始的灵摆遮罩（LB_OF_mask）。
    def capture():
        base_item = getattr(editor, "base_item", None)
        mask_item = getattr(editor, "overframe_mask", None)
        if base_item is None or mask_item is None:
            return None
        try:
            return (base_item.pixmap(), mask_item.pixmap())
        except Exception:
            return None

    def restore(cached):
        pixmap, mask_pixmap = cached
        base_item = getattr(editor, "base_item", None)
        if base_item is not None:
            _safe_call(getattr(base_item, "setPixmap", None), pixmap)
        mask_item = getattr(editor, "overframe_mask", None)
        if mask_item is not None:
            _safe_call(getattr(mask_item, "setPixmap", None), mask_pixmap)

    # 不预存安装时的画面：那时遮罩可能还是 init_vis 的初始灵摆遮罩，与卡框不配套。

    def cached_switch_base_image(*args, **kwargs):
        signature = _base_image_signature(editor)
        cached = _bounded_cache_get(cache, signature)
        if cached is not None:
            restore(cached)
            return None
        result = method(*args, **kwargs)
        cached = capture()
        if cached is not None:
            _bounded_cache_put(
                cache,
                signature,
                cached,
                _BASE_IMAGE_CACHE_LIMIT,
            )
        return result

    cached_switch_base_image._base_image_cache_wrapped = True
    cached_switch_base_image._base_image_cache = cache
    editor.switch_base_image = cached_switch_base_image


def _optimize_graphics_view(app):
    view = getattr(app, "view", None)
    if view is None or getattr(view, "_performance_options_installed", False):
        return
    view._performance_options_installed = True
    try:
        mode = getattr(view, "BoundingRectViewportUpdate", None)
        if mode is not None:
            view.setViewportUpdateMode(mode)
    except Exception:
        pass
    try:
        flag = getattr(view, "DontSavePainterState", None)
        if flag is not None:
            view.setOptimizationFlag(flag, True)
    except Exception:
        pass
    for name in ("scene", "rd_scene", "fc_scene", "back_scene", "past_scene"):
        scene = getattr(app, name, None)
        if scene is None:
            continue
        try:
            no_index = getattr(scene, "NoIndex", None)
            if no_index is not None:
                scene.setItemIndexMethod(no_index)
        except Exception:
            pass


def _enable_default_text_adjustment(editor):
    try:
        if not getattr(editor, "text_sizeable", False):
            editor.text_adjust_btn.is_checked = True
            editor.text_adjust_btn.animate_circle()
            editor.text_sizeable_toggle(True)
        if not getattr(editor, "text_weightable", False):
            editor.text_weight_adjust_btn.is_checked = True
            editor.text_weight_adjust_btn.animate_circle()
            editor.text_weight_switch(True)
    except Exception:
        _tab_log("启用默认字号/字重调整失败:\n" + traceback.format_exc())


def _remove_editor_link_center(editor):
    try:
        center_button = editor.link_center_btn
        center_layout = editor.link_second_hbox
        index = center_layout.indexOf(center_button)
        width = max(center_button.sizeHint().width(), center_button.width())
        center_layout.removeWidget(center_button)
        center_button.hide()
        if center_button in editor.link_btn_list:
            editor.link_btn_list.remove(center_button)
        if index >= 0:
            center_layout.insertSpacing(index, width)
    except Exception:
        return


def _remove_editor_tc_type_selector(editor):
    selector = getattr(editor, "tc_type_selector", None)
    if selector is None:
        return
    for signal_name in ("currentIndexChanged", "activated", "currentTextChanged"):
        try:
            getattr(selector, signal_name).disconnect()
        except Exception:
            pass
    try:
        layout = getattr(editor, "lan_hbox", None)
        if layout is not None:
            layout.removeWidget(selector)
    except Exception:
        pass
    for method_name, value in (
        ("setMinimumWidth", 0),
        ("setMaximumWidth", 0),
        ("setFixedWidth", 0),
    ):
        try:
            getattr(selector, method_name)(value)
        except Exception:
            pass
    try:
        selector.hide()
    except Exception:
        pass
    try:
        selector.setVisible(False)
    except Exception:
        pass
    try:
        selector.setParent(None)
    except Exception:
        pass


def _schedule_remove_editor_tc_type_selector(editor):
    _remove_editor_tc_type_selector(editor)
    for delay in (0, 50, 200, 600, 1200):
        try:
            QTimer.singleShot(
                delay,
                lambda editor=editor: _remove_editor_tc_type_selector(editor),
            )
        except Exception:
            pass


def _setup_otcg_editor(editor):
    """OTCGWidget 构造完成后的补充（由 OTCGWidget.__init__ 末尾调用）。

    去掉「类型2」下拉与连接箭头中间那个按钮、默认打开字号 / 字重调整、RD 专用选项随模式切换、
    清掉构造时读入的演示卡，再装上卡图缓存、输入防抖、灵摆刻度实时刷新、效果排版、查卡竞态保护、
    RD 卡框同步，最后安排安装标签页。这些都在编辑器**实例**上挂钩子：信号此前已连到原方法上，顺序不能调换。
    """
    _schedule_remove_editor_tc_type_selector(editor)
    QTimer.singleShot(0, lambda editor=editor: _enable_default_text_adjustment(editor))
    QTimer.singleShot(0, lambda editor=editor: _install_rd_only_editor_controls(editor))
    # 控件构造时就会从 config 读入内置演示卡（demo_card_*），这里立刻擦掉，免得窗口首次绘制时闪出那张卡。
    _clear_demo_card(editor)
    editor.update_level_label()
    _install_base_image_cache(editor)
    _install_editor_input_debounce(editor)
    _install_pendulum_scale_live_refresh(editor)
    _install_effect_layout_controls(editor)
    _install_fetch_race_guard(editor)
    _install_rd_frame_sync_on_editor(editor)
    _schedule_card_tabs(editor)
    _remove_editor_link_center(editor)
    _remove_editor_search_buttons(editor)


def _setup_past_editor(editor):
    """PastWidget 构造完成后的补充（由 PastWidget.__init__ 末尾调用）。"""
    _install_pendulum_scale_live_refresh(editor)
    _install_effect_layout_controls(editor)
    _remove_editor_link_center(editor)
    _remove_editor_search_buttons(editor)


_PENDULUM_SCALE_DEBOUNCE_MS = 45


def _install_pendulum_scale_live_refresh(editor):
    """把灵摆刻度输入框接到 update_lb_level 上。"""
    if editor is None or getattr(editor, "_pendulum_scale_live_installed", False):
        return
    edit = getattr(editor, "LB_level_edit", None)
    update = getattr(editor, "update_lb_level", None)
    if edit is None or update is None:
        return
    try:
        timer = QTimer(editor)
        timer.setSingleShot(True)
        timer.setInterval(_PENDULUM_SCALE_DEBOUNCE_MS)
        timer.timeout.connect(update)
    except Exception:
        _tab_log("安装灵摆刻度实时刷新失败:\n" + traceback.format_exc())
        return

    def schedule(*_args):
        timer.start()

    try:
        edit.textChanged.connect(schedule)
    except Exception:
        _tab_log("连接灵摆刻度输入信号失败:\n" + traceback.format_exc())
        return
    editor._pendulum_scale_live_timer = timer
    editor._pendulum_scale_live_schedule = schedule
    editor._pendulum_scale_live_installed = True


_BLANK_TEXT_ITEMS = ("card_pass_item", "card_pack_item")
_BLANK_LINE_EDITS = ("card_name_edit", "LB_level_edit")
_BLANK_PLAIN_TEXTS = ("text_input", "LB_text_edit")


def _clear_card_visuals(editor):
    """清掉卡图与卡密/卡包文本项。

    卡图用「置空 pixmap」而不是 setVisible(False)：卡片加载有两条路径
    （transform_normal_img 与 _restore_cached_visuals），后者直接 setPixmap
    不经过前者，靠可见性开关表示空白会漏掉这条路径。置空 pixmap 两条路都会
    自然覆盖成真图。
    """
    if editor is None:
        return
    image_item = getattr(editor, "card_img_item", None)
    if image_item is not None:
        try:
            from PyQt5.QtGui import QPixmap

            image_item.setPixmap(QPixmap())
        except Exception:
            pass
    # 必须用静默版本：setPlainText 会发 textChanged，在控件构造期间连锁调用
    # update_text 等排版逻辑会访问尚未建立的属性（实测会让进程在退出时段错误）。
    for name in _BLANK_TEXT_ITEMS:
        _set_plain_text_silent(getattr(editor, name, None), "")


def _blank_editor_inputs(editor):
    """把编辑器上的文字输入清空。"""
    if editor is None:
        return
    for name in _BLANK_LINE_EDITS:
        _set_line_text_silent(getattr(editor, name, None), "")
    for name in _BLANK_PLAIN_TEXTS:
        _set_plain_text_silent(getattr(editor, name, None), "")


def _do_clear_demo_card(editor):
    if editor is None:
        return
    _blank_editor_inputs(editor)
    _clear_card_visuals(editor)


def _clear_demo_card(editor):
    """擦掉内置演示卡（demo_card_*），让启动后显示的是用户自己的卡片。

    延后到事件循环首轮执行，而不是在 OTCGWidget.__init__ 里直接做：
    在控件构造期间改这些显示项（卡图项 / 文本项 / 输入框）会让进程在
    退出时段错误（0xC0000417），撤掉这些操作即恢复正常。
    singleShot(0) 仍早于主窗口首次绘制，所以不会闪出演示卡。
    """
    if editor is None or getattr(editor, "_ygodiy_demo_cleared", False):
        return
    editor._ygodiy_demo_cleared = True
    try:
        QTimer.singleShot(0, lambda target=editor: _do_clear_demo_card(target))
    except Exception:
        _do_clear_demo_card(editor)


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from card_search import _remove_editor_search_buttons
from card_tabs import _schedule_card_tabs
from effect_layout import _install_effect_layout_controls
from rd_frame import (
    _install_rd_frame_sync_on_editor,
    _install_rd_only_editor_controls,
    _schedule_rd_frame_sync,
)
