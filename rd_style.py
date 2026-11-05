"""RD 文字样式：属性 / 等级 / 攻守的样式图、文字颜色、一键注音。

由补丁分片 p13、p14、p15 整理而来。
"""

from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from common import _RD_RANK_RESOURCE_PREFIX
from utils import runtime_resource_path


# ---------------------------------------------------------------------------
# RD text colours.  MixTextItem paints through single_color/gradient, so only
# calling setDefaultTextColor is not enough; update all three paint paths.
# ---------------------------------------------------------------------------
_RD_TEXT_COLOR_TARGETS = (
    ("text_color_flag", "text_color", ("text_item",)),
    ("detail_color_flag", "detail_color", ("detail_text_item", "MT_text_item")),
    ("lb_text_color_flag", "lb_text_color", ("lb_text_item", "LB_text_item")),
)


def _set_mix_text_color(item, color):
    if item is None:
        return
    try:
        qcolor = QColor(str(color or "#000000"))
        if not qcolor.isValid():
            return
        if hasattr(item, "setDefaultTextColor"):
            item.setDefaultTextColor(qcolor)
        if hasattr(item, "setSingleColor"):
            try:
                item.setSingleColor(qcolor)
            except Exception:
                pass
        if hasattr(item, "setGradientProcess"):
            gradient = getattr(item, "gradient_process", None)
            if isinstance(gradient, (list, tuple)):
                converted = []
                for entry in gradient:
                    if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                        converted.append([entry[0], entry[1], QColor(qcolor)])
                    else:
                        converted.append(entry)
                try:
                    item.setGradientProcess(converted)
                except Exception:
                    pass
        if hasattr(item, "update"):
            item.update()
    except Exception:
        pass


def _apply_rd_text_colors(rd_widget, source=None):
    if rd_widget is None:
        return
    for flag_name, color_name, _item_names in _RD_TEXT_COLOR_TARGETS:
        if not hasattr(rd_widget, flag_name):
            setattr(rd_widget, flag_name, False)
        if not hasattr(rd_widget, color_name):
            setattr(rd_widget, color_name, "#000000")
        if isinstance(source, dict):
            if flag_name in source:
                setattr(rd_widget, flag_name, bool(source.get(flag_name)))
            value = source.get(color_name)
            if isinstance(value, str) and value:
                setattr(rd_widget, color_name, value)
    detail_default = "#000000"
    # 深色卡框（连接 / 普通超量）的详情栏只有白字看得见。
    # 判据用 RD 自己的 _rd_frame_call_way —— 原来读的 detail_call_way 是 OCG 面板
    # 的属性，RDWidget 上没有，永远取到空串，所以白字分支从来没生效过。
    # 超量灵摆这里算出的是「超量灵摆」，不在列表里，保持黑字。
    if (
        getattr(rd_widget, "card_type", "") == "怪兽卡"
        and str(getattr(rd_widget, "_rd_frame_call_way", "") or "") in ("连接", "超量")
    ):
        detail_default = "#FFFFFF"
    defaults = {
        "text_color_flag": "#000000",
        "detail_color_flag": detail_default,
        "lb_text_color_flag": "#000000",
    }
    for flag_name, color_name, item_names in _RD_TEXT_COLOR_TARGETS:
        custom = bool(getattr(rd_widget, flag_name, False))
        color = str(getattr(rd_widget, color_name, defaults[flag_name]) or defaults[flag_name])
        if not custom:
            color = defaults[flag_name]
        for item_name in item_names:
            _set_mix_text_color(getattr(rd_widget, item_name, None), color)


def _open_rd_text_color_dialog(rd_widget):
    from PyQt5.QtWidgets import QColorDialog, QDialogButtonBox, QFormLayout

    class _RdColorDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("RD 文字颜色")
            layout = QVBoxLayout(self)
            form = QFormLayout()
            self.rows = {}
            for key, label in (
                ("text", "效果文本"),
                ("detail", "种族魔陷/详情"),
                ("lb", "灵摆效果"),
            ):
                check = QCheckBox("自定义")
                line = QVBoxLayout()
                line.addWidget(check)
                picker = QPushButton("选择颜色")
                line.addWidget(picker)
                form.addRow(QLabel(label), line)
                self.rows[key] = (check, picker)
            layout.addLayout(form)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(self.accept)
            layout.addWidget(buttons)
            for key, (check, picker) in self.rows.items():
                check.setChecked(bool(getattr(rd_widget, key + "_color_flag", False)))
                self._refresh(key)
                picker.clicked.connect(lambda _=False, k=key: self._pick(k))
                check.toggled.connect(lambda _state, k=key: self._toggle(k))

        def _current(self, key):
            return str(getattr(rd_widget, key + "_color", "#000000") or "#000000")

        def _refresh(self, key):
            check, picker = self.rows[key]
            color = self._current(key)
            picker.setText(color)
            try:
                picker.setStyleSheet("background-color: %s;" % color)
            except Exception:
                pass
            picker.setEnabled(bool(check.isChecked()))

        def _toggle(self, key):
            setattr(rd_widget, key + "_color_flag", bool(self.rows[key][0].isChecked()))
            self._refresh(key)
            _apply_rd_text_colors(rd_widget)

        def _pick(self, key):
            chosen = QColorDialog.getColor(QColor(self._current(key)), self, "选择颜色")
            if chosen.isValid():
                setattr(rd_widget, key + "_color", chosen.name())
                self._refresh(key)
                _apply_rd_text_colors(rd_widget)

    dialog = _RdColorDialog(rd_widget)
    dialog.exec_()


# ---------------------------------------------------------------------------
# RD style resources and text-style dialog.
# ---------------------------------------------------------------------------
_RD_ATTR_STYLE_DIRS = ("white", "sliver", "gold1", "gold2")
_RD_ATTRIBUTE_CODES = {
    "光": "light", "暗": "dark", "炎": "fire", "水": "water",
    "地": "ground", "风": "wind", "神": "god", "魔": "magic", "罠": "trap",
}
_RD_SILVER_GRADIENT = [
    (True, 0.0, "#ffffff"), (True, 0.24, "#e6e6e6"),
    (True, 0.56, "#a2a2a2"), (True, 0.83, "#e7e7e7"),
    (True, 1.0, "#ffffff"), (False, 1.0, "#ffffff"),
]
_RD_GOLD_GRADIENT = [
    (True, 0.0, "#ffffff"), (True, 0.12, "#ffec6a"),
    (True, 0.34, "#e9b406"), (True, 0.56, "#a77800"),
    (True, 0.81, "#e9b406"), (True, 1.0, "#ffee33"),
]


def _rd_decrypt_pixmap(path):
    try:
        module = __import__("RD_widget")
        decrypt = getattr(module, "decrypt_image_qpixmap", None)
        if decrypt is not None and str(path).lower().endswith(".enc"):
            return decrypt(path)
    except Exception:
        pass
    return QPixmap(runtime_resource_path(path))


def _rd_style_state(rd_widget):
    for name in ("attr_style", "level_style", "AD_style"):
        if not hasattr(rd_widget, name):
            setattr(rd_widget, name, 0)


def _rd_current_attribute(rd_widget):
    value = str(getattr(rd_widget, "current_attribute", "") or "")
    if value:
        return value
    buttons = getattr(rd_widget, "attribute_btn_dict", {}) or {}
    for name, button in buttons.items():
        try:
            checked = bool(button.isChecked())
        except Exception:
            checked = bool(getattr(button, "is_checked", False))
        if checked:
            return str(name)
    return "光"


def _apply_rd_attribute_style(rd_widget):
    attribute = _rd_current_attribute(rd_widget)
    code = _RD_ATTRIBUTE_CODES.get(attribute)
    if not code:
        return
    index = max(0, min(len(_RD_ATTR_STYLE_DIRS) - 1, int(getattr(rd_widget, "attr_style", 0) or 0)))
    path = "Rush_Duel/attribute/%s/attribute_%s.enc" % (_RD_ATTR_STYLE_DIRS[index], code)
    pixmap = _rd_decrypt_pixmap(path)
    item = getattr(rd_widget, "attribute_item", None)
    if item is not None and pixmap is not None and not pixmap.isNull():
        item.setPixmap(pixmap)


def _apply_rd_level_style(rd_widget):
    try:
        level = int(getattr(rd_widget, "current_level", 1) or 1)
    except Exception:
        level = 1
    level = max(0, min(13, level))
    item = getattr(rd_widget, "level_item", None)
    if item is None:
        return
    # 超量怪物用阶级图标，其余卡种用等级图标。
    # 注意：Rush_Duel/level{n}.enc 与 rank{n}.enc 才是「圆球+星星+数字」的
    # 完整图标；Rush_Duel/level/{样式}/level{n}.enc 里只有数字，直接用它会把
    # 球和星星整个盖掉（等级球/阶级球消失），所以样式目录一律不取。
    if bool(getattr(rd_widget, "_rd_synced_detail_is_xyz", False)):
        path = "%s%d.enc" % (_RD_RANK_RESOURCE_PREFIX, level)
    else:
        path = "Rush_Duel/level%d.enc" % level
    pixmap = _rd_decrypt_pixmap(path)
    if pixmap is not None and not pixmap.isNull():
        item.setPixmap(pixmap)


def _rd_gradient(colors):
    result = []
    for enabled, position, color in colors:
        result.append([bool(enabled), float(position), QColor(str(color))])
    return result


def _apply_rd_ad_style(rd_widget):
    style = int(getattr(rd_widget, "AD_style", 0) or 0)
    items = [
        getattr(rd_widget, "ATK_number_item", None),
        getattr(rd_widget, "DEF_number_item", None),
        getattr(rd_widget, "Max_number_item", None),
        getattr(rd_widget, "LINK_number_item", None),
        getattr(rd_widget, "Link_number_item", None),
    ]
    for item in items:
        if item is None:
            continue
        try:
            if style == 0:
                if hasattr(item, "enableGradient"):
                    item.enableGradient(False)
                item.duplicate = True
            else:
                process = _RD_SILVER_GRADIENT if style == 1 else _RD_GOLD_GRADIENT
                if hasattr(item, "setGradientProcess"):
                    item.setGradientProcess(_rd_gradient(process))
                if hasattr(item, "enableGradient"):
                    item.enableGradient(True)
                item.duplicate = False
            item.update()
        except Exception:
            pass


def _apply_rd_text_styles(rd_widget):
    if rd_widget is None:
        return
    _rd_style_state(rd_widget)
    _apply_rd_attribute_style(rd_widget)
    _apply_rd_level_style(rd_widget)
    _apply_rd_ad_style(rd_widget)


def _open_rd_text_style_dialog(rd_widget):
    from PyQt5.QtWidgets import QComboBox, QDialogButtonBox, QFormLayout

    class _RdTextStyleDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("文字样式")
            layout = QVBoxLayout(self)
            form = QFormLayout()
            self.attribute_box = QComboBox(self)
            self.attribute_box.addItems(["默认", "银色", "金色1", "金色2"])
            self.level_box = QComboBox(self)
            self.level_box.addItems(["默认", "银色", "金色1", "金色2"])
            self.ad_box = QComboBox(self)
            self.ad_box.addItems(["默认", "银色", "金色"])
            form.addRow("属性文字: ", self.attribute_box)
            form.addRow("等级数字: ", self.level_box)
            form.addRow("攻守数字: ", self.ad_box)
            layout.addLayout(form)
            buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            _rd_style_state(rd_widget)
            self.attribute_box.setCurrentIndex(int(getattr(rd_widget, "attr_style", 0) or 0))
            self.level_box.setCurrentIndex(int(getattr(rd_widget, "level_style", 0) or 0))
            self.ad_box.setCurrentIndex(int(getattr(rd_widget, "AD_style", 0) or 0))

    dialog = _RdTextStyleDialog(rd_widget)
    if dialog.exec_() == QDialog.Accepted:
        rd_widget.attr_style = dialog.attribute_box.currentIndex()
        rd_widget.level_style = dialog.level_box.currentIndex()
        rd_widget.AD_style = dialog.ad_box.currentIndex()
        _apply_rd_text_styles(rd_widget)


# ---------------------------------------------------------------------------
# One-click Japanese notation, using YGOLD's Gitee notation table.
# ---------------------------------------------------------------------------
_JP_NOTATION_CACHE = None


def _remove_ruby_annotation(text):
    import re

    text = re.sub(r"\[([^\[\]()]+?)\([^()]*?\)\]", r"\1", str(text))
    text = re.sub(r"\([^()]*?\)", "", text)
    return text.replace("[", "").replace("]", "")


def _replace_with_ruby(notation_dict, text):
    if not notation_dict:
        return str(text)
    keys = [str(key) for key in notation_dict.keys() if key]
    if not keys:
        return str(text)
    max_len = max(len(key) for key in keys)
    text = str(text)
    result = []
    index = 0
    while index < len(text):
        match = None
        match_len = 0
        for length in range(min(max_len, len(text) - index), 0, -1):
            part = text[index:index + length]
            if part in notation_dict and notation_dict[part]:
                match = str(notation_dict[part])
                match_len = length
                break
        if match is not None:
            result.append(match)
            index += match_len
        else:
            result.append(text[index])
            index += 1
    return "".join(result)


def _load_jp_notation():
    global _JP_NOTATION_CACHE
    if isinstance(_JP_NOTATION_CACHE, dict):
        return _JP_NOTATION_CACHE
    try:
        import requests

        response = requests.get(
            "https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/JP_NOTATION.json",
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            _JP_NOTATION_CACHE = data
            return data
    except Exception:
        pass
    return None


def _open_rd_notation_dialog(rd_widget):
    from PyQt5.QtWidgets import QTextEdit

    notation = _load_jp_notation()
    if not notation:
        QMessageBox.information(rd_widget, "一键注音", "加载注音失败")
        return
    dialog = QDialog(rd_widget)
    dialog.setWindowTitle("一键注音")
    dialog.setMinimumSize(700, 480)
    root = QVBoxLayout(dialog)
    top = QHBoxLayout()
    left = QVBoxLayout()
    right = QVBoxLayout()
    left.addWidget(QLabel("注音只支持OCG常用语"))
    text_edit = QTextEdit(dialog)
    text_edit.setPlaceholderText("请输入文本")
    text_input = getattr(rd_widget, "text_input", None)
    if text_input is not None:
        text_edit.setPlainText(text_input.toPlainText())
    left.addWidget(text_edit)
    right.addWidget(QLabel("常用注音表（点击可插入）"))
    search_edit = QLineEdit(dialog)
    search_edit.setPlaceholderText("输入关键字检索...")
    list_widget = QListWidget(dialog)
    list_widget.setWordWrap(True)
    for key, value in notation.items():
        list_widget.addItem("%s: %s" % (key, value))
    right.addWidget(search_edit)
    right.addWidget(list_widget)
    top.addLayout(left, 3)
    top.addLayout(right, 2)
    root.addLayout(top)
    actions = QHBoxLayout()
    actions.addStretch(1)
    remove_button = QPushButton("移除注音", dialog)
    add_button = QPushButton("一键注音", dialog)
    apply_button = QPushButton("应用到文本", dialog)
    actions.addWidget(remove_button)
    actions.addWidget(add_button)
    actions.addWidget(apply_button)
    root.addLayout(actions)

    def filter_list(query):
        query = str(query or "")
        list_widget.clear()
        for key, value in notation.items():
            line = "%s: %s" % (key, value)
            if query in line:
                list_widget.addItem(line)

    def insert_item(item):
        line = item.text() if item is not None else ""
        insert_text = line.split(":", 1)[1].strip() if ":" in line else line
        text_edit.setPlainText(text_edit.toPlainText() + insert_text)

    search_edit.textChanged.connect(filter_list)
    list_widget.itemClicked.connect(insert_item)
    remove_button.clicked.connect(lambda: text_edit.setPlainText(_remove_ruby_annotation(text_edit.toPlainText())))
    add_button.clicked.connect(lambda: text_edit.setPlainText(_replace_with_ruby(notation, _remove_ruby_annotation(text_edit.toPlainText()))))

    def apply_text():
        if text_input is not None:
            text_input.setPlainText(text_edit.toPlainText())
        update_text = getattr(rd_widget, "update_text", None)
        if callable(update_text):
            update_text()
        dialog.accept()

    apply_button.clicked.connect(apply_text)
    dialog.exec_()


def _apply_rd_style_data(rd_widget, data):
    if rd_widget is None or not isinstance(data, dict):
        return
    _rd_style_state(rd_widget)
    for name in ("attr_style", "level_style", "AD_style"):
        if name in data:
            try:
                setattr(rd_widget, name, int(data.get(name) or 0))
            except Exception:
                pass
    _apply_rd_text_styles(rd_widget)
