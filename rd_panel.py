"""RD 右栏：按 OCG/TCG 的版式重排，补齐自定种族、灵摆、文字调整、特殊符号等控件。

由补丁分片 p06、p09、p14、p15、p25、p26、p28、p39、p44、p45 整理而来。
"""

import traceback

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from common import (
    _attach_editor_button,
    _combo_text_from,
    _install_symbol_bar,
    _plain_text_from,
    _set_line_text_silent,
    _set_plain_text_silent,
    _set_toggle_checked_silent,
    _tab_log,
    _text_from,
    _toggle_checked,
)


def _sync_rd_custom_detail(rd_editor, otcg_editor):
    toggle = getattr(rd_editor, "detail_custom_toggle", None)
    edit = getattr(rd_editor, "detail_custom_edit", None)
    if toggle is None or edit is None:
        return
    checked = _toggle_checked(getattr(otcg_editor, "detail_custom_toggle", None))
    if _toggle_checked(toggle) != checked:
        _set_toggle_checked_silent(toggle, checked)
    _set_line_text_silent(edit, _text_from(getattr(otcg_editor, "detail_custom_edit", None)))
    edit.setEnabled(checked)
    rd_editor._rd_custom_detail_panel.setVisible(
        _combo_text_from(getattr(otcg_editor, "type_selector", None)) == "怪兽卡"
    )


def _rd_add_custom_detail_row(rd_editor):
    """RD 控件读写 OCG 的现有字段，沿用卡面生成和保存流程。"""
    if getattr(rd_editor, "detail_custom_toggle", None) is not None:
        return
    otcg_editor = getattr(getattr(rd_editor, "parent_app", None), "otcg_widget", None)
    root = rd_editor.layout()
    if otcg_editor is None or root is None:
        return
    anchor = _rd_layout_row_containing(root, "详细")
    index = _rd_root_index_of(root, anchor) if anchor is not None else None
    if index is None:
        return
    from customComponents import CustomLineEdit, ToggleButton

    panel = QWidget(rd_editor)
    row = QHBoxLayout(panel)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(_RD_OCG_SPACING)
    toggle = ToggleButton(panel)
    toggle.setFixedSize(*_RD_OCG_TOGGLE_SIZE)
    edit = CustomLineEdit()
    edit.setPlaceholderText(otcg_editor.detail_custom_edit.placeholderText())
    row.addWidget(QLabel("自定", panel))
    row.addWidget(toggle)
    row.addWidget(edit, 1)
    root.insertWidget(index + 1, panel)
    rd_editor.detail_custom_toggle = toggle
    rd_editor.detail_custom_edit = edit
    rd_editor._rd_custom_detail_panel = panel

    def on_toggled(checked):
        source = otcg_editor.detail_custom_toggle
        # 宿主 ToggleButton 使用 toggled(bool)，让原有槽函数收到完整的状态。
        _set_toggle_checked_silent(source, checked)
        source.toggled.emit(checked)
        edit.setEnabled(checked)
        _schedule_rd_frame_sync(rd_editor.parent_app)

    def on_text_changed(text):
        otcg_editor.detail_custom_edit.setText(text)

    toggle.toggled.connect(on_toggled)
    edit.textChanged.connect(on_text_changed)
    _sync_rd_custom_detail(rd_editor, otcg_editor)


def _rd_set_text_adjust_value(rd_editor, slider_name, value):
    otcg_editor = rd_editor.parent_app.otcg_widget
    getattr(otcg_editor, slider_name).setValue(value)
    _sync_rd_text_adjustments(rd_editor, otcg_editor)


def _rd_set_text_adjust_enabled(rd_editor, toggle_name, checked):
    otcg_editor = rd_editor.parent_app.otcg_widget
    toggle = getattr(otcg_editor, toggle_name)
    _set_toggle_checked_silent(toggle, checked)
    toggle.toggled.emit(checked)
    _sync_rd_text_adjustments(rd_editor, otcg_editor)


def _add_rd_text_color_button(rd_widget):
    if getattr(rd_widget, "_rd_text_color_button", None) is not None:
        return
    try:
        from PyQt5.QtWidgets import QPushButton

        button = QPushButton("文字颜色", rd_widget)
        button.setObjectName("rd_text_color_button")
        button.clicked.connect(
            lambda _=False, target=rd_widget: _open_rd_text_color_dialog(target)
        )
        rd_widget._rd_text_color_button = button
        placed = _attach_editor_button(
            rd_widget, button, ("color_black_btn", "color_defined_btn", "color_custom_btn")
        )
        if not placed:
            _tab_log("RD 文字颜色按钮未能进入布局，已作为浮动按钮放置。")
    except Exception:
        _tab_log("创建 RD 文字颜色按钮失败:\n" + traceback.format_exc())


# ---------------------------------------------------------------------------
# RD action rows and exact three-section overframe dialog.
# ---------------------------------------------------------------------------
def _rd_existing_text_effect_bridge(rd_widget):
    if getattr(rd_widget, "_rd_effect_layout_bridge", False):
        return
    original = getattr(rd_widget, "update_text", None)
    if not callable(original):
        return

    def wrapped(*args, **kwargs):
        result = original(*args, **kwargs)
        _apply_effect_layout_to_editor(rd_widget)
        return result

    wrapped._rd_effect_layout_original = original
    rd_widget.update_text = wrapped
    rd_widget._rd_effect_layout_bridge = True


# RD 文本调整控件的取值范围，与 OCG/TCG 面板保持一致。
_RD_TEXT_SIZE_MIN = -15
_RD_TEXT_SIZE_MAX = 20
_RD_TEXT_WEIGHT_MIN = 0
_RD_TEXT_WEIGHT_MAX = 15
_RD_TEXT_ADJUST_CONTROLS = (
    ("text_size_slider", "text_adjust_btn", "text_sizeable"),
    ("text_weight_slider", "text_weight_adjust_btn", "text_weightable"),
)
_RD_NAME_ALIGN_LABELS = ("居左", "居中", "居右")
_RD_TEXT_ALIGN_LABELS = ("默认", "居中")


def _install_rd_text_adjust_controls(rd_widget):
    """为 RD 面板补齐与 OCG/TCG 一致的字号、字重与对齐控件。

    调整数值写回 OCG 的现有字段，沿用卡片保存与模式同步流程。
    """
    if rd_widget is None or getattr(rd_widget, "_rd_text_adjust_controls_installed", False):
        return
    root = getattr(rd_widget, "rd_layout", None) or rd_widget.layout()
    if root is None:
        return
    try:
        from PyQt5.QtWidgets import QSizePolicy

        r = rd_widget
        r.text_size_slider = QSlider(Qt.Horizontal, r)
        r.text_size_slider.setRange(_RD_TEXT_SIZE_MIN, _RD_TEXT_SIZE_MAX)
        r.text_size_slider.setValue(0)
        r.text_size_slider.setToolTip("字号偏移")
        r.text_weight_slider = QSlider(Qt.Horizontal, r)
        r.text_weight_slider.setRange(_RD_TEXT_WEIGHT_MIN, _RD_TEXT_WEIGHT_MAX)
        r.text_weight_slider.setValue(0)
        r.text_weight_slider.setToolTip("描边粗细")
        r.name_align_selector = QComboBox(r)
        r.name_align_selector.addItems(_RD_NAME_ALIGN_LABELS)
        r.text_align_selector = QComboBox(r)
        r.text_align_selector.addItems(_RD_TEXT_ALIGN_LABELS)

        panel = QWidget(r)
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        grid.addWidget(QLabel("字号", panel), 0, 0)
        grid.addWidget(r.text_size_slider, 0, 1)
        grid.addWidget(QLabel("字重", panel), 0, 2)
        grid.addWidget(r.text_weight_slider, 0, 3)
        grid.addWidget(QLabel("卡名对齐", panel), 1, 0)
        grid.addWidget(r.name_align_selector, 1, 1)
        grid.addWidget(QLabel("效果对齐", panel), 1, 2)
        grid.addWidget(r.text_align_selector, 1, 3)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        r.text_sizeable = True
        r.text_weightable = True
        for slider_name, _toggle_name, _flag_name in _RD_TEXT_ADJUST_CONTROLS:
            getattr(r, slider_name).valueChanged.connect(
                lambda value, name=slider_name: _rd_set_text_adjust_value(r, name, value)
            )
        r.name_align_selector.currentIndexChanged.connect(
            lambda _index, target=r: _sync_rd_text_alignments(target, target)
        )
        r.text_align_selector.currentIndexChanged.connect(
            lambda _index, target=r: _sync_rd_text_alignments(target, target)
        )

        insert_at = min(9, root.count())
        try:
            root.insertWidget(insert_at, panel)
        except Exception:
            root.addWidget(panel)
        r._rd_text_adjust_panel = panel
        r._rd_text_adjust_controls_installed = True
    except Exception:
        _tab_log("安装 RD 文字调整控件失败:" + "\n" + traceback.format_exc())


def _install_rd_reference_buttons(rd_widget):
    if rd_widget is None or getattr(rd_widget, "_rd_reference_buttons_installed", False):
        return
    root = getattr(rd_widget, "rd_layout", None) or rd_widget.layout()
    if root is None:
        return
    try:
        # p13/p14 加的同名旧按钮已被下面新建的按钮取代。只 hide() 的话它们
        # 仍占着根布局的整行，RD 底部会白多出一行空白；这里从布局里摘掉。
        for name in ("_rd_text_color_button", "_rd_overframe_button"):
            old = getattr(rd_widget, name, None)
            if old is None:
                continue
            old.hide()
            old.setParent(None)
        r = rd_widget
        r.text_style_button = QPushButton("文字样式", r)
        r.text_style_button.setObjectName("rd_text_style_button")
        r.rd_text_color_button = QPushButton("文本颜色", r)
        r.rd_text_color_button.setObjectName("rd_text_color_button")
        r.effect_layout_button = QPushButton("效果排版", r)
        r.effect_layout_button.setObjectName("rd_effect_layout_button")
        r.notation_button = QPushButton("一键注音", r)
        r.notation_button.setObjectName("rd_notation_button")
        r.text_style_button.clicked.connect(lambda _=False, target=r: _open_rd_text_style_dialog(target))
        r.rd_text_color_button.clicked.connect(lambda _=False, target=r: _open_rd_text_color_dialog(target))
        r.effect_layout_button.clicked.connect(lambda _=False, target=r: _show_effect_layout_dialog(target))
        r.notation_button.clicked.connect(lambda _=False, target=r: _open_rd_notation_dialog(target))
        from PyQt5.QtWidgets import QSizePolicy

        actions_widget = QWidget(r)
        grid = QGridLayout(actions_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for column, button in enumerate((r.text_style_button, r.effect_layout_button)):
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(button, 0, column)
        for column, button in enumerate((r.rd_text_color_button, r.notation_button)):
            button.setMinimumHeight(30)
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            grid.addWidget(button, 1, column)
        actions_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        actions_widget.setMinimumHeight(70)
        insert_at = min(9, root.count())
        try:
            root.insertWidget(insert_at, actions_widget)
        except Exception:
            root.addWidget(actions_widget)
        def _show_action_widgets():
            try:
                actions_widget.show()
                for button in (
                    r.text_style_button,
                    r.rd_text_color_button,
                    r.effect_layout_button,
                    r.notation_button,
                ):
                    button.show()
                actions_widget.updateGeometry()
                r.updateGeometry()
            except Exception:
                pass

        _show_action_widgets()
        QTimer.singleShot(0, _show_action_widgets)
        QTimer.singleShot(250, _show_action_widgets)
        try:
            root.activate()
            r.updateGeometry()
        except Exception:
            pass
        upload_layout = getattr(r, "upload_btn_hbox", None)
        if upload_layout is not None:
            # 与 OCG/TCG 面板一致：这里是开关（ToggleButton），不是复选框。
            # ToggleButton 没有 setChecked，初值由构造参数决定。
            from PyQt5.QtWidgets import QSizePolicy

            from customComponents import ToggleButton

            # 初值跟着数据走：只要还有启用的超框图层，开关就是开着的。
            overframe_toggle = ToggleButton(
                r,
                any(bool(layer.get("enabled")) for layer in _rd_overframe_layers(r)),
            )
            # 这一行里只有标签和开关会吸收余量（实测标签被抻到 186px，
            # 文字才 60px 左右，多出来的就是那段空隙），都固定住才能挨在一起。
            overframe_toggle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            r._rd_overframe_toggle = overframe_toggle  # 供 p47 在模式间同步后刷新开关显示
            overframe_label = QLabel("超框卡图", r)
            overframe_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            overframe_settings = QPushButton("超框设置", r)
            upload_layout.addWidget(overframe_label)
            upload_layout.addWidget(overframe_toggle)
            upload_layout.addWidget(overframe_settings)

            def toggle_overframe(state, target=r):
                # 开关一次控制所有超框图层。
                for layer in _rd_overframe_layers(target):
                    layer["enabled"] = bool(state)
                _rd_apply_overframe_image(target)

            overframe_toggle.toggled.connect(toggle_overframe)
            overframe_settings.clicked.connect(lambda _=False, target=r: _open_rd_overframe_dialog(target))
        free_button = QPushButton("自定义文本", r)
        free_button.setObjectName("rd_free_text_button")
        free_button.clicked.connect(lambda _=False, target=r: _open_free_text_editor(target))
        root.addWidget(free_button)
        r.free_text_button = free_button
        _install_rd_text_adjust_controls(r)
        _ensure_free_text(r)
        _rd_existing_text_effect_bridge(r)
        _rd_style_state(r)
        r._rd_reference_buttons_installed = True
    except Exception:
        _tab_log("创建 RD 参考按钮失败:\n" + traceback.format_exc())


_RD_LAYOUT_DELAY_MS = 400
# 面板构建完成后 RD 右栏的实际行数（去掉那些转发给 OCG 的多余控件后是 16~17 行）。
# 这个下限只用来挡住「面板还没建完就重排」，不必跟着行数一起涨。
_RD_LAYOUT_MIN_ROWS = 12

# 目标行序，按特征匹配。labels 用子串匹配；kind="text_edit" 表示效果文本域。
_RD_ROW_RULES = (
    {"labels": ("卡名",)},                        # 卡名 / 类型
    {"labels": ("卡名颜色：",)},                   # 卡名颜色 / 高级选项
    {"labels": ("上传卡图",)},                    # 上传卡图 / 超框
    {"labels": ("详细",)},                        # 详细 / 种族 / 召唤方式 / 副类型
    {"labels": ("属性：",)},                      # 属性
    {"labels": ("等级", "阶级")},                  # 等级 / 阶级
    {"labels": ("攻击",)},                        # 攻击 / 防御 / 极限攻击
    # 灵摆刻度 + 灵摆效果自成一块，必须排在下面的 text_edit 规则之前，
    # 否则会被它抢先匹配走。
    {"labels": ("灵摆刻度",)},                    # 灵摆刻度 / 灵摆效果
    {"kind": "text_edit"},                       # 效果文本
    {"labels": ("字号",)},                        # 字号 / 字重 / 卡名对齐 / 效果对齐
    {"labels": ("卡密",), "need_edit": True},      # 卡密 / 卡包 输入行
    {"labels": ("防伪",)},                        # 防伪 / 版权
    {"labels": ("罕贵",)},                        # 罕贵 / 水印
    {"labels": ("卡包",), "min_toggles": 3},       # 开关行（卡密/卡包/防伪/版权/圆角…）
    {"labels": ("导出图片",)},                     # 导出图片 / 导出设置
)


def _rd_layout_row_info(item):
    """提取一行的特征。

    item 既可能是子布局（多数行），也可能是直接控件（效果文本框、底部按钮行），
    两种都要覆盖，否则这些行会识别不出来、被当成陌生行丢到末尾。
    """
    from PyQt5.QtWidgets import QLineEdit, QTextEdit

    texts = []
    state = {"edit": False, "toggles": 0, "text_edit": False}

    def inspect(widget):
        if widget is None:
            return
        try:
            texts.append(str(widget.text()))
        except Exception:
            pass
        if isinstance(widget, QTextEdit):
            state["text_edit"] = True
        elif isinstance(widget, QLineEdit):
            state["edit"] = True
        if hasattr(widget, "is_checked"):
            state["toggles"] += 1

    def walk(layout):
        for index in range(layout.count()):
            child = layout.itemAt(index)
            if child is None:
                continue
            inspect(child.widget())
            sub = child.layout()
            if sub is not None:
                walk(sub)

    if item is None:
        return texts, state["edit"], state["toggles"], state["text_edit"]
    sub = item.layout()
    if sub is not None:
        walk(sub)
    else:
        widget = item.widget()
        inspect(widget)
        # 有些行是「带内部布局的 QWidget」（字号面板、样式按钮组），要展开它。
        inner = widget.layout() if widget is not None else None
        if inner is not None:
            walk(inner)
    return texts, state["edit"], state["toggles"], state["text_edit"]


def _rd_layout_row_matches(info, rule):
    texts, has_edit, toggle_count, has_text_edit = info
    if rule.get("kind") == "text_edit":
        return has_text_edit
    labels = rule.get("labels", ())
    # 注意是子串匹配：控件文本是「上传卡图(不裁剪)」，规则里只写「上传卡图」。
    if labels and not any(needle in text for needle in labels for text in texts):
        return False
    if rule.get("need_edit") and not has_edit:
        return False
    minimum = rule.get("min_toggles")
    if minimum is not None and toggle_count < minimum:
        return False
    return True


def _rd_layout_widget_count(layout):
    """布局子树里的控件总数，用于校验重排没有弄丢控件。"""
    total = 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        if item.widget() is not None:
            total += 1
        sub = item.layout()
        if sub is not None:
            total += _rd_layout_widget_count(sub)
    return total


def _rd_layout_direct_labels(layout):
    """该布局「直接」包含的控件文本（不下钻）。"""
    labels = []
    if layout is None:
        return labels
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if widget is None:
            continue
        try:
            labels.append(str(widget.text()))
        except Exception:
            continue
    return labels


def _rd_layout_has_label(layout, label_text):
    if layout is None:
        return False
    if any(label_text in label for label in _rd_layout_direct_labels(layout)):
        return True
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        sub = item.layout()
        if sub is not None and _rd_layout_has_label(sub, label_text):
            return True
    return False


def _rd_layout_row_containing(root, label_text):
    """根布局里哪一行含有该标签（返回行布局本身）。"""
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is None:
            continue
        sub = item.layout()
        if sub is None:
            continue
        if _rd_layout_has_label(sub, label_text):
            return sub
    return None


def _rd_layout_apply(rd_widget):
    """按 OCG 的行序重排 RD 面板。"""
    if rd_widget is None or getattr(rd_widget, "_rd_layout_reordered", False):
        return
    root = rd_widget.layout()
    if root is None:
        return
    count = root.count()
    if count < _RD_LAYOUT_MIN_ROWS:
        _tab_log("RD 面板只有 %d 行，跳过重排" % count)
        return
    items = [(index, root.itemAt(index)) for index in range(count)]
    order = []
    used = set()
    for rule in _RD_ROW_RULES:
        for index, item in items:
            if index in used or item is None:
                continue
            if _rd_layout_row_matches(_rd_layout_row_info(item), rule):
                order.append(index)
                used.add(index)
                break
    # 没被规则命中的行（RD 专属功能）保持原相对顺序，统一收到末尾
    order.extend(index for index, _ in items if index not in used)

    before = _rd_layout_widget_count(root)
    rd_widget._rd_layout_reordered = True
    # 先把行数记下来：takeAt 会让 count() 递减。
    taken = [root.takeAt(0) for _ in range(count)]
    for new_index, source_index in enumerate(order):
        root.insertItem(new_index, taken[source_index])
    after = _rd_layout_widget_count(root)
    _tab_log(
        "RD 重排：行数 %d，规则命中 %d 行，控件 %d -> %d"
        % (count, len(used), before, after)
    )
    if before != after:
        _tab_log("RD 重排后控件数不一致，请检查")


def _schedule_rd_layout(rd_widget):
    """RDWidget.init_vis 末尾调用：延后到所有面板都构建完再按 OCG 行序重排一次（兜底，
    _complete_rd_panel 会先同步做；_rd_layout_reordered 保证只重排一次）。"""
    try:
        QTimer.singleShot(_RD_LAYOUT_DELAY_MS, lambda target=rd_widget: _rd_layout_run(target))
    except Exception:
        _tab_log("安排 RD 面板重排失败:\n" + traceback.format_exc())


def _rd_layout_run(rd_widget):
    try:
        _rd_layout_apply(rd_widget)
    except Exception:
        _tab_log("重排 RD 面板失败:\n" + traceback.format_exc())


_RD_EXTRA_DELAY_MS = 650
# 详细行下拉的宽度区间。面板实际只有约 771px：
# 「详细」标签 + 三个下拉要挤在一行，每个超过约 180px 就会把最后一个挤出去。
_RD_DETAIL_COMBO_MIN_WIDTH = 96
_RD_DETAIL_COMBO_MAX_WIDTH = 176
_RD_BOTTOM_MERGE_LABELS = ("超框卡图", "自定义文本")


def _rd_row_layout_for(root, label_text):
    return _rd_layout_row_containing(root, label_text)


# 灵摆刻度与灵摆效果是卡片信息（两个版式共享同一张卡），不是版式显示选项。
# OCG 面板的 LB_level_edit / LB_text_edit 是这两项的存放处，RD 卡面本来就由
# _sync_rd_pendulum_* 从那里取值绘制；这里只补一个 RD 自己的编辑入口，
# 写回后立刻刷新 RD 卡面，OCG 面板的显示选项一个都不碰。
_RD_PENDULUM_DEBOUNCE_MS = 45
_RD_PENDULUM_LEVEL_WIDTH = 56
_RD_PENDULUM_TEXT_MIN_HEIGHT = 58
_RD_PENDULUM_TEXT_MAX_HEIGHT = 104


def _rd_is_pendulum(rd_widget):
    """当前 RD 卡是不是灵摆卡。

    RD 的「种族 / 召唤方式 / 副类型」三个下拉变量名与内容对不上
    （extra_info_selector 存的其实是副类型），所以逐个看哪个带「灵摆」。
    """
    if getattr(rd_widget, "_rd_pendulum_mode", None):
        return True
    for name in ("call_way_selector", "extra_info_selector", "race_selector"):
        combo = getattr(rd_widget, name, None)
        if combo is None:
            continue
        try:
            if "灵摆" in str(combo.currentText()):
                return True
        except Exception:
            continue
    return False


def _rd_effect_text_row(rd_widget, root):
    """效果文本行在根布局里的下标。"""
    text_input = getattr(rd_widget, "text_input", None)
    if text_input is None:
        return None
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is not None and item.widget() is text_input:
            return index
    return None


def _rd_add_pendulum_editor(rd_widget, editor, root):
    """在效果文本行上方补「灵摆刻度 / 灵摆效果」两个输入框。"""
    if getattr(rd_widget, "_rd_pendulum_editor_installed", False):
        return
    level_source = getattr(editor, "LB_level_edit", None)
    text_source = getattr(editor, "LB_text_edit", None)
    row_index = _rd_effect_text_row(rd_widget, root)
    if level_source is None or text_source is None or row_index is None:
        return
    rd_widget._rd_pendulum_editor_installed = True

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QLabel, QLineEdit, QTextEdit, QVBoxLayout, QWidget

    level_edit = QLineEdit(rd_widget)
    level_edit.setFixedWidth(_RD_PENDULUM_LEVEL_WIDTH)
    _set_line_text_silent(level_edit, _text_from(level_source, ""))
    lb_text = QTextEdit(rd_widget)
    lb_text.setMinimumHeight(_RD_PENDULUM_TEXT_MIN_HEIGHT)
    lb_text.setMaximumHeight(_RD_PENDULUM_TEXT_MAX_HEIGHT)
    lb_text.setPlaceholderText("灵摆效果")
    _set_plain_text_silent(lb_text, _plain_text_from(text_source))
    rd_widget.LB_level_edit = level_edit
    rd_widget.LB_text_edit = lb_text

    # 整块放进一个 QWidget：这样它只占根布局的一行，p25 的行重排才能用
    # 「灵摆刻度」这个标签把它整体认出来（散成两行的话第二行没有标签可匹配）。
    panel = QWidget(rd_widget)
    box = QVBoxLayout(panel)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    row.addWidget(QLabel("灵摆刻度", panel))
    row.addWidget(level_edit)
    row.addStretch(1)
    box.addLayout(row)
    box.addWidget(lb_text)
    root.insertWidget(row_index, panel)
    rd_widget._rd_pendulum_editor_panel = panel
    # 后加的控件必须显式显示，否则不会出现在界面上（父控件已可见）。
    for widget in (panel, level_edit, lb_text):
        widget.show()

    timer = QTimer(rd_widget)
    timer.setSingleShot(True)
    timer.setInterval(_RD_PENDULUM_DEBOUNCE_MS)

    def flush():
        # 先写回数据存放处，再按当前卡是否灵摆刷新 RD 卡面。
        _set_line_text_silent(level_source, level_edit.text())
        _set_plain_text_silent(text_source, lb_text.toPlainText())
        is_pendulum = _rd_is_pendulum(rd_widget)
        _sync_rd_pendulum_scales(rd_widget, editor, is_pendulum)
        _sync_rd_pendulum_text(rd_widget, editor, is_pendulum)

    timer.timeout.connect(flush)
    level_edit.textChanged.connect(lambda *_: timer.start())
    lb_text.textChanged.connect(lambda *_: timer.start())
    rd_widget._rd_pendulum_editor_timer = timer


# RD 详细行的下拉 -> 卡片信息的存放处（OCG 面板上的对应下拉）。
# 种族 / 召唤方式 / 副类型都是卡片信息、两个版式共享同一张卡，所以 RD 侧的改动
# 写回数据；这与版式显示选项（卡模 / 语言 / 属性显示…）的隔离并不冲突 ——
# 那一类控件 RD 面板上本来就没有。
_RD_DETAIL_SOURCES = (
    ("race_selector", "race_selector"),
    ("call_way_selector", "info_selector_left"),
    ("extra_info_selector", "info_selector_mid"),
    ("extra_info_selector2", "info_selector_right"),
)


def _rd_first_combo_in(layout):
    """行里第一个下拉，用来给新加的控件对齐尺寸。"""
    from PyQt5.QtWidgets import QComboBox

    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, QComboBox):
            return widget
        sub = item.layout()
        if sub is not None:
            found = _rd_first_combo_in(sub)
            if found is not None:
                return found
    return None


def _rd_bind_detail_selector(rd_widget, editor, rd_name, source_name):
    """把 RD 详细行的一个下拉接到共享的卡片信息上。

    这里用非静默的 setCurrentIndex：OCG 那条信号链会顺带重算详情文本并安排
    RD 卡面同步；静默设置会漏掉这一步，卡面就一直停留在旧文本上。
    """
    selector = getattr(rd_widget, rd_name, None)
    source = getattr(editor, source_name, None)
    if selector is None or source is None or getattr(selector, "_rd_detail_bound", False):
        return False
    selector._rd_detail_bound = True

    def push(*_args, _rd=rd_widget, _selector=selector, _source=source):
        if getattr(_rd, "_rd_detail_pushing", False):
            return
        text = _combo_text_from(_selector)
        # 空字符串是合法取值（副类型可以不填），不能当成无效值跳过。
        if _combo_text_from(_source) == text:
            return
        index = _source.findText(text)
        if index < 0:
            # RD 有 OCG 没有的选项（例如 RD 独有种族），写不回去时保持原样。
            return
        _rd._rd_detail_pushing = True
        try:
            _source.setCurrentIndex(index)
            _schedule_rd_frame_sync(getattr(_rd, "parent_app", None))
        finally:
            _rd._rd_detail_pushing = False

    try:
        selector.currentIndexChanged.connect(push)
    except Exception:
        return False
    return True


def _rd_bind_detail_selectors(rd_widget, editor):
    for rd_name, source_name in _RD_DETAIL_SOURCES:
        _rd_bind_detail_selector(rd_widget, editor, rd_name, source_name)


def _rd_trim_call_way_options(rd_widget):
    """召唤方式下拉只保留 OCG/TCG 那 8 项，去掉所有含「灵摆」的条目。

    灵摆由第 3 个下拉（副类型）表达，和 OCG 一致；卡框仍按副类型细分到
    Pend_Normal / Pend_Effect …，由 _install_rd_frame_key_bridge 在算卡框时补回键值。
    """
    combo = getattr(rd_widget, "call_way_selector", None)
    if combo is None:
        return
    texts = [combo.itemText(index) for index in range(combo.count())]
    kept = [text for text in texts if "灵摆" not in text]
    if kept == texts:
        return
    current = _combo_text_from(combo)
    combo.blockSignals(True)
    try:
        combo.clear()
        combo.addItems(kept)
        index = combo.findText(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
    finally:
        combo.blockSignals(False)
    _tab_log("RD 召唤方式去掉细分灵摆项：%d -> %d 项" % (len(texts), len(kept)))


def _rd_align_extra_info_options(rd_widget, editor):
    """把 RD 第 3 个下拉的选项补齐成 OCG 的副类型列表。

    RD 原生把它硬编码成 ['通常', '效果']，而详情文本的第 3 段在 OCG 那边是
    info_selector_mid（10 项）。不补齐的话，在 RD 面板根本选不到「调整」这类
    副类型，同步过来的值也匹配不上。
    """
    selector = getattr(rd_widget, "extra_info_selector", None)
    source = getattr(editor, "info_selector_mid", None)
    if selector is None or source is None:
        return
    wanted = [source.itemText(index) for index in range(source.count())]
    before = [selector.itemText(index) for index in range(selector.count())]
    if not wanted or before == wanted:
        return
    current = _combo_text_from(selector)
    selector.blockSignals(True)
    try:
        selector.clear()
        selector.addItems(wanted)
        index = selector.findText(current)
        selector.setCurrentIndex(index if index >= 0 else 0)
    finally:
        selector.blockSignals(False)
    _tab_log("RD 副类型下拉补齐为 %d 项（原 %d 项）" % (len(wanted), len(before)))


def _rd_add_detail_extra_selector(rd_widget, editor, root):
    """在详细行末尾补第 4 个下拉，对应 OCG 的副类型2（info_selector_right）。

    详情文本本来就会拼上这一项（见 p06 的 _fallback_otcg_detail_text），
    RD 面板此前只是缺少设置它的入口。
    """
    if getattr(rd_widget, "extra_info_selector2", None) is not None:
        return
    source = getattr(editor, "info_selector_right", None)
    row = _rd_row_layout_for(root, "详细")
    if source is None or row is None:
        return
    from PyQt5.QtWidgets import QComboBox

    combo = QComboBox(rd_widget)
    for index in range(source.count()):
        combo.addItem(source.itemText(index))
    combo.setCurrentIndex(source.currentIndex())
    # 与同行已有下拉取一致尺寸：默认 100x30，而 RD 详细行的下拉是 155x17，
    # 不一致会被布局挤到看不见。
    template = _rd_first_combo_in(row)
    if template is not None:
        try:
            combo.setFixedHeight(template.height())
            combo.setMinimumWidth(template.minimumWidth())
            combo.setMaximumWidth(template.maximumWidth())
            combo.setSizePolicy(template.sizePolicy())
        except Exception:
            pass
    row.addWidget(combo)
    # 父控件已显示时新加的控件不会自动显示，布局也不给它位置，必须显式 show。
    combo.show()
    rd_widget.extra_info_selector2 = combo


_RD_SHORT_LABELS = (("防伪标志", "防伪"), ("版权文字", "版权"))


def _rd_shorten_labels(rd_widget):
    """把 RD 的两个长标签改成 OCG 的叫法，压紧底部版面。"""
    from PyQt5.QtWidgets import QLabel

    changed = []
    for label in rd_widget.findChildren(QLabel):
        text = str(label.text())
        for old, new in _RD_SHORT_LABELS:
            if text == old:
                label.setText(new)
                changed.append(old)
                break
    if changed:
        _tab_log("RD 标签压紧：%s" % sorted(set(changed)))


def _rd_fit_detail_row(root):
    """让详细行的下拉能收缩均分宽度。

    RD 原生的下拉是固定宽度（约 198px），面板真实宽度只有 771px 左右，
    三个下拉加上「详细」标签会超出可视区 —— 最后一个会被裁掉。
    """
    from PyQt5.QtWidgets import QComboBox, QSizePolicy

    row = _rd_row_layout_for(root, "详细")
    if row is None:
        return
    combos = []
    for index in range(row.count()):
        item = row.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QComboBox):
            combos.append(widget)
        elif item is not None and item.layout() is not None:
            combos.extend(_rd_collect_combos(item.layout()))
    if len(combos) < 2:
        return
    # 行首的「详细」标签也要固定宽度：它默认会吃掉剩余空间（实测被拉到 261px），
    # 结果四个下拉依然被挤出可视区。
    from PyQt5.QtWidgets import QLabel, QSizePolicy as _QSP

    for index in range(row.count()):
        item = row.itemAt(index)
        widget = item.widget() if item is not None else None
        if isinstance(widget, QLabel):
            try:
                widget.setSizePolicy(_QSP.Fixed, _QSP.Fixed)
                widget.setFixedWidth(max(24, widget.sizeHint().width()))
            except Exception:
                continue
    for combo in combos:
        try:
            # 关键是限死上限：这些下拉原本跟着内容撑到 250px 左右，
            # 四个加起来远超面板宽度（约 771px），最后一个就被裁掉。
            # OCG 那边的下拉只有约 123px，所以四个放得下。
            combo.setMinimumWidth(_RD_DETAIL_COMBO_MIN_WIDTH)
            combo.setMaximumWidth(_RD_DETAIL_COMBO_MAX_WIDTH)
            combo.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        except Exception:
            continue
    _tab_log("RD 详细行下拉限宽 %d-%d（%d 个）" % (_RD_DETAIL_COMBO_MIN_WIDTH, _RD_DETAIL_COMBO_MAX_WIDTH, len(combos)))


def _rd_collect_combos(layout):
    from PyQt5.QtWidgets import QComboBox

    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, QComboBox):
            found.append(widget)
        sub = item.layout()
        if sub is not None:
            found.extend(_rd_collect_combos(sub))
    return found


def _rd_take_widgets(layout):
    """把布局里的控件全部取出（返回控件列表），布局随之变空。"""
    widgets = []
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widgets.append(widget)
            continue
        sub = item.layout()
        if sub is not None:
            widgets.extend(_rd_take_widgets(sub))
    return widgets


def _rd_root_index_of(root, layout):
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is not None and item.layout() is layout:
            return index
    return None


def _rd_merge_rows_two_column(root, top_label, bottom_label):
    """把两行合并成 OCG 那种「左右两栏、每栏两组」的一行。

    做法是取出两行的控件、删掉旧行、再新建一行装上：
    直接在被掏空的旧行上继续 addLayout 会嵌套出错（实测标签错位、下拉全丢）。
    """
    top = _rd_row_layout_for(root, top_label)
    bottom = _rd_row_layout_for(root, bottom_label)
    if top is None or bottom is None or top is bottom:
        return False
    top_index = _rd_root_index_of(root, top)
    bottom_index = _rd_root_index_of(root, bottom)
    if top_index is None or bottom_index is None:
        return False
    top_widgets = _rd_take_widgets(top)
    bottom_widgets = _rd_take_widgets(bottom)
    for layout in (top, bottom, bottom):
        pass
    # 删掉旧的两行（先删下标大的，避免位移）
    for index in sorted((top_index, bottom_index), reverse=True):
        root.takeAt(index)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    left = QHBoxLayout()
    left.setContentsMargins(0, 0, 0, 0)
    left.setSpacing(4)
    right = QHBoxLayout()
    right.setContentsMargins(0, 0, 0, 0)
    right.setSpacing(4)
    for widget in top_widgets:
        left.addWidget(widget)
    for widget in bottom_widgets:
        right.addWidget(widget)
    row.addLayout(left, 1)
    row.addLayout(right, 1)
    root.insertLayout(min(top_index, bottom_index), row)
    for widget in top_widgets + bottom_widgets:
        try:
            widget.show()
        except Exception:
            continue
    _tab_log("RD 合并「%s」+「%s」为一行（两栏）" % (top_label, bottom_label))
    return True


def _rd_merge_row_widgets_into(root, host_label, source_label):
    """把 source_label 那一行的控件平铺并入 host_label 行，删掉空出来的行。

    用于把「自定义文本」并到「导出图片 / 导出设置」那一行，底部因此再省一行。
    source 既可能是装着多个控件的子布局，也可能是直接挂在根布局上的单个按钮
    （「自定义文本」就是后者，只按标签找子布局会漏掉它）。
    """
    host = _rd_row_layout_for(root, host_label)
    source = _rd_row_layout_for(root, source_label)
    if host is None or source is None or host is source:
        return False
    source_index = _rd_root_index_of(root, source)
    if source_index is None:
        return False
    widgets = _rd_take_widgets(source)
    if not widgets:
        return False
    root.takeAt(source_index)
    for widget in widgets:
        host.addWidget(widget)
        try:
            widget.show()
        except Exception:
            continue
    _tab_log("RD 并入「%s」到「%s」行" % (source_label, host_label))
    return True


def _rd_compact_action_grid(rd_widget):
    """把 p15 那个 2 行 x 2 列的按钮组压成 1 行 4 列。

    那四个按钮（文字样式/效果排版/文本颜色/一键注音）在宽度足够时排一行即可，
    排成两行会让底部比 OCG 高出两行。
    """
    from PyQt5.QtWidgets import QGridLayout, QPushButton, QWidget

    wanted = ("文字样式", "效果排版", "文本颜色", "一键注音")
    for child in rd_widget.findChildren(QWidget):
        grid = child.layout()
        if not isinstance(grid, QGridLayout) or grid.count() != 4:
            continue
        buttons = []
        for index in range(grid.count()):
            item = grid.itemAt(index)
            button = item.widget() if item is not None else None
            if not isinstance(button, QPushButton) or str(button.text()) not in wanted:
                buttons = []
                break
            buttons.append(button)
        if len(buttons) != 4:
            continue
        for button in buttons:
            grid.removeWidget(button)
        for column, button in enumerate(buttons):
            grid.addWidget(button, 0, column)
        child.setMinimumHeight(34)
        _tab_log("RD 按钮组压缩为 1 行：%s" % [str(b.text()) for b in buttons])
        return


def _rd_compact_bottom(root, rd_widget):
    """把 RD 独有的散按钮并成一行，别让底部比 OCG 臃肿太多。"""
    from PyQt5.QtWidgets import QPushButton

    rows = []
    for index in range(root.count()):
        item = root.itemAt(index)
        if item is None:
            continue
        widget = item.widget()
        if isinstance(widget, QPushButton) and str(widget.text()) in _RD_BOTTOM_MERGE_LABELS:
            rows.append(index)
    if len(rows) < 2:
        return
    # 复用原按钮本身，不要新建：新建会让界面上出现两个同名按钮。
    buttons = []
    for index in reversed(rows):
        item = root.takeAt(index)
        if item is not None and item.widget() is not None:
            buttons.append(item.widget())
    buttons.reverse()
    # 面板别处已有的同名按钮不在这里重复放
    elsewhere = set()
    for other in rd_widget.findChildren(QPushButton):
        if other not in buttons:
            elsewhere.add(str(other.text()))
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    merged = []
    seen = set()
    for widget in buttons:
        label = str(widget.text())
        if label in seen or label in elsewhere:
            widget.setParent(None)
            widget.deleteLater()
            continue
        seen.add(label)
        row.addWidget(widget)
        merged.append(label)
    root.insertLayout(min(rows[0], root.count()), row)
    _tab_log("RD 底部合并按钮：%s" % merged)


def _rd_apply_completeness_before_ocg_style(rd_widget):
    root = rd_widget.layout() if rd_widget is not None else None
    if root is None:
        return
    if getattr(rd_widget, "_rd_completeness_done", False):
        return
    rd_widget._rd_completeness_done = True
    editor = getattr(getattr(rd_widget, "parent_app", None), "otcg_widget", None)
    _rd_add_pendulum_editor(rd_widget, editor, root)
    _rd_add_detail_extra_selector(rd_widget, editor, root)
    _rd_align_extra_info_options(rd_widget, editor)
    _rd_trim_call_way_options(rd_widget)
    _rd_shorten_labels(rd_widget)
    _rd_fit_detail_row(root)
    _rd_bind_detail_selectors(rd_widget, editor)
    _rd_compact_bottom(root, rd_widget)
    _rd_compact_action_grid(rd_widget)
    _rd_merge_rows_two_column(root, "防伪", "罕贵")
    _rd_merge_row_widgets_into(root, "导出图片", "自定义文本")
    # 灵摆编辑区建出来时是显示的。这里立刻按当前卡校正一次，否则要等下一次
    # 同步才会隐藏 —— 表现就是「非灵摆卡有时也挂着灵摆刻度/灵摆效果」。
    _sync_rd_pendulum_editor_visibility(rd_widget, _rd_is_pendulum(rd_widget))


def _sync_rd_pendulum_editor_visibility(rd_widget, is_pendulum):
    """只有灵摆卡才显示灵摆刻度 / 灵摆效果这一块。"""
    panel = getattr(rd_widget, "_rd_pendulum_editor_panel", None)
    if panel is None:
        return
    try:
        panel.setVisible(bool(is_pendulum))
    except Exception:
        pass


def _rd_refresh_pendulum_editor(rd_widget, editor, is_pendulum):
    """把数据里的灵摆刻度 / 灵摆效果刷到 RD 面板的输入框上。

    切卡时必须做：否则输入框里留着上一张卡的刻度，用户一改就写到新卡上了。
    输入框有焦点时跳过，免得冲掉用户正在敲的内容。
    """
    _sync_rd_pendulum_editor_visibility(rd_widget, is_pendulum)
    level_edit = getattr(rd_widget, "LB_level_edit", None)
    lb_text = getattr(rd_widget, "LB_text_edit", None)
    if level_edit is None or lb_text is None:
        return
    try:
        if level_edit.hasFocus() or lb_text.hasFocus():
            return
    except Exception:
        return
    _set_line_text_silent(level_edit, _text_from(getattr(editor, "LB_level_edit", None), ""))
    _set_plain_text_silent(lb_text, _plain_text_from(getattr(editor, "LB_text_edit", None)))


def _sync_rd_pendulum_scales(rd_editor, otcg_editor, is_pendulum):
    _rd_sync_pendulum_scales_inner(rd_editor, otcg_editor, is_pendulum)
    _rd_refresh_pendulum_editor(rd_editor, otcg_editor, is_pendulum)


def _sync_rd_pendulum_text(rd_editor, otcg_editor, is_pendulum):
    _rd_sync_pendulum_text_inner(rd_editor, otcg_editor, is_pendulum)
    _rd_refresh_pendulum_editor(rd_editor, otcg_editor, is_pendulum)


def _rd_finalize_panel(rd_widget):
    """RD 面板刚由 init_vis 建完、尚未显示时，当场完成 p25 重排与本分片的补齐。

    RD 面板是首次切到 RD 模式时才构建的；原先这两步只靠 400/650ms 定时器，
    切换后会先画出原版布局再跳成新布局。这里同步做掉，定时器只作兜底。
    """
    for step in ("_rd_layout_apply", "_rd_apply_completeness"):
        func = globals().get(step)
        if func is None:
            continue
        try:
            func(rd_widget)
        except Exception:
            _tab_log("RD 面板即时整理失败（%s）:\n%s" % (step, traceback.format_exc()))


def _complete_rd_panel(rd_widget):
    """RDWidget.init_vis 末尾调用：当场完成重排与补齐，定时器再兜底补一次（两步都有幂等标记）。"""
    _rd_finalize_panel(rd_widget)
    try:
        QTimer.singleShot(_RD_EXTRA_DELAY_MS, lambda target=rd_widget: _rd_apply_completeness(target))
    except Exception:
        _tab_log("安排 RD 面板补齐失败:\n" + traceback.format_exc())


_RD_OCG_SPACING = 7
_RD_OCG_HALF_STRETCH = 4
_RD_OCG_GAP_STRETCH = 1
_RD_OCG_TOGGLE_SIZE = (42, 20)
_RD_OCG_ATTRIBUTE_SIZE = (35, 25)
_RD_OCG_PENDULUM_TEXT_HEIGHT = 120
_RD_OCG_LIMIT_EDIT_WIDTH = 60


def _rd_ocg_hbox():
    from PyQt5.QtWidgets import QHBoxLayout

    box = QHBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(_RD_OCG_SPACING)
    return box


def _rd_ocg_halves(left_widgets, right_widgets, tail_widgets=(), even=False):
    """OCG 的典型行：左半栏 + 弹性间隔 + 右半栏（+ 行尾控件）。

    even=True 时半栏内的控件按 1:1 均分（OCG 的「标签 + 下拉」都是对半分）。
    元素也可以是一个布局（防伪行的半栏里还嵌着两组「标签 + 下拉」）。
    """
    from PyQt5.QtWidgets import QLayout

    row = _rd_ocg_hbox()
    for index, widgets in enumerate((left_widgets, right_widgets)):
        half = _rd_ocg_hbox()
        for widget in widgets:
            if isinstance(widget, QLayout):
                half.addLayout(widget, 1 if even else 0)
            else:
                if even:
                    _rd_ocg_ignore_hint(widget)
                half.addWidget(widget, 1 if even else 0)
        if not widgets:
            half.addStretch(1)
        row.addLayout(half, _RD_OCG_HALF_STRETCH)
        if index == 0:
            row.addStretch(_RD_OCG_GAP_STRETCH)
    for widget in tail_widgets:
        row.addWidget(widget)
    return row


def _rd_ocg_ignore_hint(widget):
    """宽度只按拉伸系数分配（不理会控件自身的 sizeHint），才能像 OCG 那样等分。"""
    from PyQt5.QtWidgets import QSizePolicy

    try:
        widget.setMinimumWidth(0)
        widget.setMaximumWidth(16777215)
        widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())
    except Exception:
        pass


def _rd_ocg_pair(label, field):
    box = _rd_ocg_hbox()
    for widget in (label, field):
        _rd_ocg_ignore_hint(widget)
        box.addWidget(widget, 1)
    return box


def _rd_ocg_text(widget):
    try:
        return str(widget.text())
    except Exception:
        return ""


def _rd_ocg_find(widgets, text=None, kind=None):
    for widget in widgets:
        if kind is not None and not isinstance(widget, kind):
            continue
        if text is not None and _rd_ocg_text(widget) != text:
            continue
        return widget
    return None


def _rd_ocg_replace_row(root, label_text, builder):
    """取出含 label_text 的那一行的全部控件，交给 builder 装成新行，放回原位置。

    builder 返回 None 表示不认识这一行的内容：此时按原顺序平铺放回，不丢控件。
    """
    row = _rd_layout_row_containing(root, label_text)
    if row is None:
        return False
    index = _rd_root_index_of(root, row)
    if index is None:
        return False
    widgets = _rd_take_widgets(row)
    root.takeAt(index)
    new_row = None
    try:
        new_row = builder(widgets)
    except Exception:
        _tab_log("RD 按 OCG 重排「%s」行失败:\n%s" % (label_text, traceback.format_exc()))
    if new_row is None:
        new_row = _rd_ocg_hbox()
        for widget in widgets:
            new_row.addWidget(widget)
    root.insertLayout(index, new_row)
    return True


def _rd_ocg_upload_row(widgets):
    """上传卡图(不裁剪) 上传卡图(裁剪) | 超框卡图 [开关] 超框设置"""
    from PyQt5.QtWidgets import QPushButton

    uploads = [w for w in widgets if isinstance(w, QPushButton) and "上传卡图" in _rd_ocg_text(w)]
    rest = [w for w in widgets if w not in uploads]
    if len(uploads) != 2:
        return None
    label = _rd_ocg_find(rest, "超框卡图")
    if label is not None:
        label.setFixedWidth(60)
    row = _rd_ocg_hbox()
    left = _rd_ocg_hbox()
    for widget in uploads:
        left.addWidget(widget)
    right = _rd_ocg_hbox()
    for widget in rest:
        right.addWidget(widget)
    row.addLayout(left, 1)
    row.addLayout(right, 1)
    return row


def _rd_ocg_detail_row(widgets):
    """详细 + 4 个下拉，五格等宽（OCG 是 154/155 交替）。"""
    row = _rd_ocg_hbox()
    for widget in widgets:
        _rd_ocg_ignore_hint(widget)
        row.addWidget(widget, 1)
    return row


def _rd_ocg_attack_row(widgets):
    """攻击 [  ] (5) 防御 [  ] (5) 极限攻击 [开关][数值]，与 OCG 的 35:5:35:5 一致。"""
    from PyQt5.QtWidgets import QLabel, QLineEdit

    labels = [w for w in widgets if isinstance(w, QLabel)]
    edits = [w for w in widgets if isinstance(w, QLineEdit)]
    if len(labels) < 2 or len(edits) < 2:
        return None
    row = _rd_ocg_hbox()
    for index in range(2):
        pair = _rd_ocg_hbox()
        pair.addWidget(labels[index])
        pair.addWidget(edits[index])
        row.addLayout(pair, 35)
        row.addStretch(5)
    used = set(labels[:2] + edits[:2])
    tail = _rd_ocg_hbox()
    for widget in widgets:
        if widget in used:
            continue
        if isinstance(widget, QLineEdit):
            widget.setFixedWidth(_RD_OCG_LIMIT_EDIT_WIDTH)
        tail.addWidget(widget)
    row.addLayout(tail, 0)
    return row


def _rd_ocg_guard_row(widgets):
    """防伪 [ ] 版权 [ ] (间隔) 罕贵 [ ] 水印 [ ]，四组标签/下拉各占 1:1。"""
    from PyQt5.QtWidgets import QComboBox, QLabel

    labels = [w for w in widgets if isinstance(w, QLabel)]
    combos = [w for w in widgets if isinstance(w, QComboBox)]
    if len(labels) != 4 or len(combos) != 4:
        return None
    pairs = [_rd_ocg_pair(labels[i], combos[i]) for i in range(4)]
    return _rd_ocg_halves(pairs[:2], pairs[2:])


def _rd_ocg_value_label(rd_widget, slider):
    """OCG 的字号/字重后面跟着当前数值，RD 补一个只读标签。"""
    from PyQt5.QtWidgets import QLabel

    label = QLabel(str(slider.value()), rd_widget)
    label.setFixedWidth(24)
    slider.valueChanged.connect(lambda value, _label=label: _label.setText(str(value)))
    return label


def _rd_ocg_text_adjust_toggle(rd_widget, slider_name, toggle_name):
    from customComponents import HollowHandleStyle, ToggleButton

    otcg_editor = rd_widget.parent_app.otcg_widget
    source = getattr(otcg_editor, toggle_name)
    slider = getattr(rd_widget, slider_name)
    source_style = getattr(otcg_editor, slider_name).style()
    style = HollowHandleStyle(dict(source_style.config))
    style.setParent(slider)
    slider.setStyle(style)
    toggle = ToggleButton(
        rd_widget, check=_toggle_checked(source),
        on_color=source.on_color, off_color=source.off_color,
        disable_color=source.disable_color,
        width=source.width(), height=source.height(),
    )
    setattr(rd_widget, toggle_name, toggle)
    toggle.toggled.connect(
        lambda checked: _rd_set_text_adjust_enabled(rd_widget, toggle_name, checked)
    )
    return toggle


def _rd_ocg_split_text_adjust(rd_widget, root):
    """把 p15 的 2x4 网格拆成 OCG 的两行：字号/字重 一行，卡名/效果对齐 一行。

    返回对齐行（由调用方插到卡密行之后），失败返回 None。
    """
    from PyQt5.QtWidgets import QGridLayout

    panel = getattr(rd_widget, "_rd_text_adjust_panel", None)
    grid = panel.layout() if panel is not None else None
    if not isinstance(grid, QGridLayout):
        return None
    index = None
    for position in range(root.count()):
        item = root.itemAt(position)
        if item is not None and item.widget() is panel:
            index = position
            break
    if index is None:
        return None
    cells = {}
    for position in range(grid.count()):
        item = grid.itemAt(position)
        if item is not None and item.widget() is not None:
            row, column, _rs, _cs = grid.getItemPosition(position)
            cells[(row, column)] = item.widget()
    needed = [(r, c) for r in range(2) for c in range(4)]
    if any(key not in cells for key in needed):
        return None
    for widget in cells.values():
        grid.removeWidget(widget)
    root.takeAt(index)

    size_row = []
    for column, (slider_name, toggle_name, _flag_name) in zip((0, 2), _RD_TEXT_ADJUST_CONTROLS):
        label, slider = cells[(0, column)], cells[(0, column + 1)]
        label.setFixedWidth(30)
        value_label = _rd_ocg_value_label(rd_widget, slider)
        setattr(rd_widget, "_rd_" + slider_name + "_label", value_label)
        toggle = _rd_ocg_text_adjust_toggle(rd_widget, slider_name, toggle_name)
        size_row.append([label, value_label, toggle, slider])
    root.insertLayout(index, _rd_ocg_halves(size_row[0], size_row[1]))
    _sync_rd_text_adjustments(rd_widget, rd_widget.parent_app.otcg_widget)

    tail = []
    button = getattr(rd_widget, "effect_layout_button", None)
    if button is not None:
        tail.append(button)
    align_row = _rd_ocg_halves(
        [cells[(1, 0)], cells[(1, 1)]],
        [cells[(1, 2)], cells[(1, 3)]],
        tail,
        even=True,
    )
    # 先把控件挂到新布局（会改到 rd_widget 名下），再收起已空的旧面板。
    for widget in list(cells.values()) + size_row[0][1:3] + size_row[1][1:3]:
        widget.show()
    panel.hide()
    return align_row


def _rd_ocg_take_action_buttons(rd_widget, root):
    """拆掉 p15 的样式按钮组：效果排版去对齐行，其余三个单独成一行。"""
    names = ("text_style_button", "rd_text_color_button", "notation_button")
    buttons = [getattr(rd_widget, name, None) for name in names]
    if any(button is None for button in buttons):
        return None
    holder = buttons[0].parentWidget()
    index = None
    for position in range(root.count()):
        item = root.itemAt(position)
        if item is not None and item.widget() is holder and holder is not rd_widget:
            index = position
            break
    if index is None:
        return None
    root.takeAt(index)
    row = _rd_ocg_hbox()
    for button in buttons:
        button.setMinimumHeight(0)
        row.addWidget(button, 1)
    for button in buttons:
        button.show()
    effect_button = getattr(rd_widget, "effect_layout_button", None)
    if effect_button is not None:
        effect_button.setMinimumHeight(0)
    holder.hide()
    return row


def _rd_ocg_fix_pendulum_panel(rd_widget):
    """灵摆刻度占左半栏、灵摆效果固定 120 高，与 OCG 一致。"""
    from PyQt5.QtWidgets import QSizePolicy

    panel = getattr(rd_widget, "_rd_pendulum_editor_panel", None)
    level_edit = getattr(rd_widget, "LB_level_edit", None)
    lb_text = getattr(rd_widget, "LB_text_edit", None)
    box = panel.layout() if panel is not None else None
    if box is None or level_edit is None or lb_text is None:
        return
    first = box.itemAt(0)
    old_row = first.layout() if first is not None else None
    if old_row is None:
        return
    widgets = _rd_take_widgets(old_row)
    box.takeAt(0)
    label = _rd_ocg_find(widgets, "灵摆刻度")
    level_edit.setMinimumWidth(0)
    level_edit.setMaximumWidth(16777215)
    left = [w for w in (label, level_edit) if w is not None]
    box.insertLayout(0, _rd_ocg_halves(left, []))
    box.setSpacing(_RD_OCG_SPACING)
    lb_text.setMinimumHeight(_RD_OCG_PENDULUM_TEXT_HEIGHT)
    lb_text.setMaximumHeight(_RD_OCG_PENDULUM_TEXT_HEIGHT)
    panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)


def _rd_ocg_fix_sizes(rd_widget):
    for widget in rd_widget.findChildren(QWidget):
        name = type(widget).__name__
        try:
            if name == "ToggleButton":
                widget.setFixedSize(*_RD_OCG_TOGGLE_SIZE)
            elif name == "AttributeButton":
                widget.setFixedSize(*_RD_OCG_ATTRIBUTE_SIZE)
        except Exception:
            continue


def _rd_ocg_set_spacing(layout):
    """RD 原生布局的 spacing 是 -1（实际为 0），统一成 OCG 的 7。"""
    if layout is None:
        return
    try:
        layout.setSpacing(_RD_OCG_SPACING)
    except Exception:
        return
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        sub = item.layout()
        if sub is not None:
            _rd_ocg_set_spacing(sub)
            continue
        widget = item.widget()
        # 只下钻普通容器（灵摆编辑区之类），别动自定义控件的内部布局。
        if widget is not None and type(widget) is QWidget:
            _rd_ocg_set_spacing(widget.layout())


def _rd_ocg_insert_after(root, anchor_label, row):
    anchor = _rd_layout_row_containing(root, anchor_label)
    index = _rd_root_index_of(root, anchor) if anchor is not None else None
    root.insertLayout(root.count() - 1 if index is None else index + 1, row)


def _rd_apply_ocg_style(rd_widget):
    root = rd_widget.layout() if rd_widget is not None else None
    if root is None or getattr(rd_widget, "_rd_ocg_style_done", False):
        return
    rd_widget._rd_ocg_style_done = True
    before = _rd_layout_widget_count(root)
    _rd_ocg_fix_sizes(rd_widget)
    _rd_ocg_replace_row(root, "上传卡图(不裁剪)", _rd_ocg_upload_row)
    _rd_ocg_replace_row(root, "详细", _rd_ocg_detail_row)
    _rd_add_custom_detail_row(rd_widget)
    _rd_ocg_replace_row(root, "攻击", _rd_ocg_attack_row)
    _rd_ocg_replace_row(root, "罕贵", _rd_ocg_guard_row)
    _rd_ocg_fix_pendulum_panel(rd_widget)
    align_row = _rd_ocg_split_text_adjust(rd_widget, root)
    action_row = _rd_ocg_take_action_buttons(rd_widget, root)
    # 行序照 OCG：卡密/卡包 → 卡名/效果对齐(+效果排版) → 防伪… → RD 样式按钮 → 开关
    if align_row is not None:
        _rd_ocg_insert_after(root, "随机一卡", align_row)
    if action_row is not None:
        _rd_ocg_insert_after(root, "罕贵", action_row)
    _rd_ocg_set_spacing(root)
    after = _rd_layout_widget_count(root)
    _tab_log("RD 按 OCG 版式重排完成：控件 %d -> %d" % (before, after))


def _rd_apply_completeness_before_language_row(rd_widget):
    _rd_apply_completeness_before_ocg_style(rd_widget)
    try:
        _rd_apply_ocg_style(rd_widget)
    except Exception:
        _tab_log("RD 按 OCG 版式重排失败:\n" + traceback.format_exc())


def _rd_move_language_row(rd_widget):
    root = rd_widget.layout() if rd_widget is not None else None
    app = getattr(rd_widget, "parent_app", None)
    bar = getattr(app, "_rd_language_bar", None)
    if root is None or bar is None or getattr(rd_widget, "_rd_language_row_moved", False):
        return
    name_row = _rd_layout_row_containing(root, "卡名")
    index = _rd_root_index_of(root, name_row) if name_row is not None else None
    if index is None:
        _tab_log("RD 语言行：找不到卡名行，保持原位置")
        return
    old_layout = bar.parentWidget().layout() if bar.parentWidget() is not None else None
    if old_layout is not None:
        old_layout.removeWidget(bar)
    visible = not bar.isHidden()
    bar.setParent(rd_widget)
    row = bar.layout()
    if row is not None:
        # 与 RD 面板其它行对齐：不留边距，间距同 OCG
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_RD_OCG_SPACING)
    root.insertWidget(index + 1, bar)
    bar.setVisible(visible)
    rd_widget._rd_language_row_moved = True
    _tab_log("RD 语言行已移到卡名行下面")


def _rd_apply_completeness_before_name_color(rd_widget):
    _rd_apply_completeness_before_language_row(rd_widget)
    try:
        _rd_move_language_row(rd_widget)
    except Exception:
        _tab_log("移动 RD 语言行失败:\n" + traceback.format_exc())


_NAME_COLOR_ADVANCED_TEXT = "高级"


def _name_color_row(editor):
    """直接包含「高级选项」标签的那一层布局。"""
    label = getattr(editor, "color_advanced_label", None)
    root = editor.layout() if editor is not None else None
    if label is None or root is None:
        return None

    def find(layout):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                continue
            if item.widget() is label:
                return layout
            if item.layout() is not None:
                found = find(item.layout())
                if found is not None:
                    return found
        return None

    return find(root)


def _move_name_color_advanced(editor):
    from PyQt5.QtWidgets import QSizePolicy

    if editor is None or getattr(editor, "_name_color_advanced_moved", False):
        return
    title = getattr(editor, "color_label", None)
    label = getattr(editor, "color_advanced_label", None)
    toggle = getattr(editor, "color_advanced_btn", None)
    row = _name_color_row(editor)
    if title is None or label is None or toggle is None or row is None or row.indexOf(toggle) < 0:
        return
    # 整行清空（含那段固定间隔），再按新顺序放回同样的三个控件
    while row.count():
        row.takeAt(0)
    label.setText(_NAME_COLOR_ADVANCED_TEXT)
    for widget in (title, label):
        widget.setSizePolicy(QSizePolicy.Maximum, widget.sizePolicy().verticalPolicy())
    row.addWidget(title)
    row.addWidget(label)
    row.addWidget(toggle)
    row.addStretch(1)
    row.invalidate()
    editor._name_color_advanced_moved = True


def _rd_apply_completeness_before_symbols(rd_widget):
    _rd_apply_completeness_before_name_color(rd_widget)
    try:
        _move_name_color_advanced(rd_widget)
    except Exception:
        _tab_log("调整 RD 卡名颜色行失败:\n" + traceback.format_exc())


def _rd_apply_completeness(rd_widget):
    # RD 面板要等它自己的行重排（p25/p28）完成才装
    _rd_apply_completeness_before_symbols(rd_widget)
    try:
        _install_symbol_bar(rd_widget, "text_input", ("LB_text_edit",))
    except Exception:
        _tab_log("安装 RD 特殊符号按钮失败:\n" + traceback.format_exc())


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from effect_layout import _apply_effect_layout_to_editor, _show_effect_layout_dialog
from rd_frame import (
    _rd_sync_pendulum_scales_inner,
    _rd_sync_pendulum_text_inner,
    _schedule_rd_frame_sync,
    _sync_rd_text_adjustments,
    _sync_rd_text_alignments,
)
from rd_style import (
    _open_rd_notation_dialog,
    _open_rd_text_color_dialog,
    _open_rd_text_style_dialog,
    _rd_style_state,
)
from overframe import _open_rd_overframe_dialog, _rd_apply_overframe_image, _rd_overframe_layers
from free_text import _ensure_free_text, _open_free_text_editor
