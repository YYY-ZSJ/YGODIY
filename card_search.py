"""卡名搜索对话框的增强（翻页按钮、加入标签页）与高级搜索对话框。

由补丁分片 p01、p03 整理而来。
"""

import traceback

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QIcon, QIntValidator, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common import (
    _ABILITY_FILTERS,
    _ATTRIBUTES,
    _CARD_TYPE_FILTERS,
    _LINK_MARKERS,
    _RACES,
    _SPELL_TRAP_FILTERS,
    _tab_log,
)


_RACE_FILTERS = tuple((name, value) for value, name in _RACES.items())
_ATTRIBUTE_FILTERS = tuple((name, value) for value, name in _ATTRIBUTES.items())
_LINK_FILTERS = tuple(
    zip(("↖", "↑", "↗", "←", "→", "↙", "↓", "↘"), _LINK_MARKERS)
)


class _AdvancedSearchDialog(QDialog):
    def __init__(self, search_dialog, manager=None, target="card"):
        super().__init__(search_dialog)
        self.search_dialog = search_dialog
        self.manager = manager
        self.target = target
        self.toggle_buttons = {}
        self.range_edits = {}
        self.setWindowTitle("高级搜索")
        self.resize(1050, 780)

        root = QVBoxLayout(self)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("卡名搜索"))
        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("可留空，只搜索卡名")
        name_row.addWidget(self.name_edit)
        root.addLayout(name_row)

        pass_row = QHBoxLayout()
        pass_row.addWidget(QLabel("卡密搜索"))
        self.pass_edit = QLineEdit(self)
        self.pass_edit.setPlaceholderText("可留空，只搜索卡密")
        pass_row.addWidget(self.pass_edit)
        root.addLayout(pass_row)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        self._add_toggle_group(content_layout, "卡片种类", _CARD_TYPE_FILTERS, 5)
        self._add_toggle_group(content_layout, "属性", _ATTRIBUTE_FILTERS, 7)
        self._add_toggle_group(content_layout, "魔法·陷阱的种类", _SPELL_TRAP_FILTERS, 5)
        self._add_toggle_group(content_layout, "种族", _RACE_FILTERS, 5)
        self._add_toggle_group(content_layout, "能力·其他", _ABILITY_FILTERS, 4)
        self._add_numeric_group(content_layout)
        self._add_link_group(content_layout)
        self._add_pack_group(content_layout)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        reset_button = QPushButton("重置", self)
        reset_button.clicked.connect(self.reset_filters)
        cancel_button = QPushButton("取消", self)
        cancel_button.clicked.connect(self.reject)
        search_button = QPushButton("搜索", self)
        search_button.setDefault(True)
        search_button.clicked.connect(self.apply_search)
        action_row.addWidget(reset_button)
        action_row.addWidget(cancel_button)
        action_row.addWidget(search_button)
        root.addLayout(action_row)

    def _add_toggle_group(self, parent_layout, title, options, columns):
        group = QGroupBox(title, self)
        grid = QGridLayout(group)
        buttons = {}
        for index, (name, value) in enumerate(options):
            button = QPushButton(name, group)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setStyleSheet(
                "QPushButton:checked { background-color: #4f8fd8; color: white; }"
            )
            grid.addWidget(button, index // columns, index % columns)
            buttons[name] = (button, value)
        self.toggle_buttons[title] = buttons
        parent_layout.addWidget(group)

    def _add_link_group(self, parent_layout):
        group = QGroupBox("连接箭头", self)
        grid = QGridLayout(group)
        buttons = {}
        positions = (
            (0, 0),
            (0, 1),
            (0, 2),
            (1, 0),
            (1, 2),
            (2, 0),
            (2, 1),
            (2, 2),
        )
        for (name, value), (row, column) in zip(_LINK_FILTERS, positions):
            button = QPushButton(name, group)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setStyleSheet(
                "QPushButton:checked { background-color: #4f8fd8; color: white; }"
            )
            grid.addWidget(button, row, column)
            buttons[name] = (button, value)
        self.toggle_buttons["连接箭头"] = buttons
        parent_layout.addWidget(group)

    def _add_numeric_group(self, parent_layout):
        group = QGroupBox("数值", self)
        grid = QGridLayout(group)
        grid.addWidget(QLabel("种类"), 0, 0)
        grid.addWidget(QLabel("最小值"), 0, 1)
        grid.addWidget(QLabel("最大值"), 0, 2)
        for row, field in enumerate(("星数", "攻击力", "守备力", "刻度"), start=1):
            minimum = QLineEdit(group)
            maximum = QLineEdit(group)
            minimum.setPlaceholderText("Min")
            maximum.setPlaceholderText("Max")
            minimum.setValidator(QIntValidator(0, 999999, minimum))
            maximum.setValidator(QIntValidator(0, 999999, maximum))
            grid.addWidget(QLabel(field), row, 0)
            grid.addWidget(minimum, row, 1)
            grid.addWidget(maximum, row, 2)
            self.range_edits[field] = (minimum, maximum)
        parent_layout.addWidget(group)

    def _add_pack_group(self, parent_layout):
        group = QGroupBox("卡包", self)
        layout = QHBoxLayout(group)
        self.pack_combo = QComboBox(group)
        self.pack_combo.setEditable(True)
        self.pack_combo.addItem("所有卡包")
        self.pack_combo.addItems(sorted(set(_load_packs().values())))
        layout.addWidget(self.pack_combo)
        parent_layout.addWidget(group)

    def reset_filters(self):
        self.name_edit.clear()
        self.pass_edit.clear()
        for buttons in self.toggle_buttons.values():
            for button, _ in buttons.values():
                button.setChecked(False)
        for minimum, maximum in self.range_edits.values():
            minimum.clear()
            maximum.clear()
        self.pack_combo.setCurrentIndex(0)

    def _selected_values(self, group):
        return {
            value
            for button, value in self.toggle_buttons[group].values()
            if button.isChecked()
        }

    def _selected_names(self, group):
        return {
            name
            for name, (button, _) in self.toggle_buttons[group].items()
            if button.isChecked()
        }

    def collect_filters(self):
        ranges = {}
        for field, (minimum_edit, maximum_edit) in self.range_edits.items():
            minimum_text = minimum_edit.text().strip()
            maximum_text = maximum_edit.text().strip()
            if minimum_text or maximum_text:
                ranges[field] = (
                    int(minimum_text) if minimum_text else None,
                    int(maximum_text) if maximum_text else None,
                )
        pack = self.pack_combo.currentText().strip()
        if pack == "所有卡包":
            pack = ""
        return {
            "keyword": "",
            "卡名搜索": self.name_edit.text().strip(),
            "卡密搜索": self.pass_edit.text().strip(),
            "卡片种类": self._selected_names("卡片种类"),
            "属性": self._selected_values("属性"),
            "魔法·陷阱的种类": self._selected_names("魔法·陷阱的种类"),
            "种族": self._selected_values("种族"),
            "能力·其他": self._selected_names("能力·其他"),
            "数值": ranges,
            "连接箭头": self._selected_values("连接箭头"),
            "卡包": pack,
        }

    def apply_search(self):
        filters = self.collect_filters()
        if self.target == "pack" and self.manager is not None:
            self.manager.create_pack_from_search(filters)
            self.accept()
            return
        self.search_dialog.fetcher._advanced_filters = filters
        display_text = _advanced_search_title(filters)
        self.search_dialog.text_edit.setText(display_text)
        self.search_dialog.search_btn_clicked()
        self.accept()


def _advanced_search_title(filters):
    parts = []
    for key in ("卡名搜索", "卡密搜索", "卡包"):
        value = str(filters.get(key) or "").strip()
        if value:
            parts.append(value)

    value_groups = (
        ("卡片种类", None),
        ("属性", _ATTRIBUTES),
        ("魔法·陷阱的种类", None),
        ("种族", _RACES),
        ("能力·其他", None),
        ("连接箭头", {value: label for label, value in _LINK_FILTERS}),
    )
    for key, labels in value_groups:
        selected = filters.get(key) or ()
        names = []
        for value in selected:
            names.append(str(labels.get(value, value) if labels else value))
        parts.extend(sorted(names))

    for field, limits in sorted((filters.get("数值") or {}).items()):
        try:
            minimum, maximum = limits
        except Exception:
            continue
        if minimum is not None and maximum is not None:
            parts.append(f"{field}{minimum}-{maximum}")
        elif minimum is not None:
            parts.append(f"{field}>={minimum}")
        elif maximum is not None:
            parts.append(f"{field}<={maximum}")

    return " / ".join(parts) if parts else "高级搜索"


def _enhance_search_dialog_pagination(dialog):
    try:
        screen = QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen else 780
        current_height = max(dialog.height(), 640)
        max_safe_height = max(current_height, available_height - 60)
        target_height = min(max(current_height, 780), max_safe_height)
        target_width = max(dialog.width(), 700)
        dialog.setMaximumSize(16777215, 16777215)
        dialog.setMinimumSize(660, min(target_height, 700))
        dialog.resize(target_width, target_height)

        page_y = target_height - 122
        button_y = target_height - 74

        dialog.current_page_edit.setFixedSize(82, 32)
        dialog.current_page_edit.move(260, page_y)
        dialog.current_page_edit.setAlignment(Qt.AlignCenter)
        dialog.current_page_edit.setStyleSheet(
            "font-size: 20px; font-weight: bold; padding: 1px;"
        )

        dialog.total_page_label.setFixedSize(120, 32)
        dialog.total_page_label.move(348, page_y)
        dialog.total_page_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        dialog.total_page_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        for button, text, x in (
            (dialog.last_page_btn, "上一页", 180),
            (dialog.next_page_btn, "下一页", 360),
        ):
            button.setText(text)
            button.setIcon(QIcon())
            button.setFixedSize(140, 38)
            button.move(x, button_y)
            _style_search_page_button(button)
            button.setToolTip(text)
        _sync_search_page_proxy_buttons(dialog, button_y)
        dialog.current_page_edit.raise_()
        dialog.total_page_label.raise_()
    except Exception:
        _tab_log("增强搜索翻页控件失败:\n" + traceback.format_exc())


def _style_search_page_button(button):
    try:
        button.setFlat(False)
        button.setAutoFillBackground(True)
        palette = button.palette()
        for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
            palette.setColor(group, QPalette.Button, QColor("#ffffff"))
            palette.setColor(group, QPalette.ButtonText, QColor("#000000"))
            palette.setColor(group, QPalette.WindowText, QColor("#000000"))
            palette.setColor(group, QPalette.Text, QColor("#000000"))
        button.setPalette(palette)
        button.setStyleSheet(
            """
            QPushButton {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #000000;
                border-radius: 5px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:disabled,
            QPushButton:!enabled {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #000000;
            }
            QPushButton:hover:enabled {
                background-color: #f0f0f0;
                color: #000000;
            }
            """
        )
        button.update()
    except Exception:
        pass


def _schedule_search_page_button_style(dialog):
    # 先同步套一次，避免对话框首帧露出原版按钮；后续定时器再按最终尺寸校正位置。
    _style_search_page_buttons(dialog)
    for delay in (0, 50, 200, 600, 1200, 2500):
        QTimer.singleShot(delay, lambda dialog=dialog: _style_search_page_buttons(dialog))


def _style_search_page_buttons(dialog):
    try:
        button_y = max(dialog.height(), 640) - 74
        _sync_search_page_proxy_buttons(dialog, button_y)
    except Exception:
        _tab_log("设置搜索翻页按钮样式失败:\n" + traceback.format_exc())


def _sync_search_page_proxy_buttons(dialog, button_y):
    _sync_search_page_proxy_button(
        dialog,
        source_attr="last_page_btn",
        proxy_attr="_patched_last_page_btn",
        text="上一页",
        method_name="last_page",
        x=180,
        y=button_y,
    )
    _sync_search_page_proxy_button(
        dialog,
        source_attr="next_page_btn",
        proxy_attr="_patched_next_page_btn",
        text="下一页",
        method_name="next_page",
        x=360,
        y=button_y,
    )


def _sync_search_page_proxy_button(dialog, source_attr, proxy_attr, text, method_name, x, y):
    source = getattr(dialog, source_attr, None)
    if source is None:
        return
    try:
        source.setText("")
        source.hide()
    except Exception:
        pass

    proxy = getattr(dialog, proxy_attr, None)
    if proxy is None:
        proxy = QPushButton(text, dialog)
        proxy.clicked.connect(
            lambda _=False,
            dialog=dialog,
            source_attr=source_attr,
            method_name=method_name: _trigger_search_page_button(
                dialog, source_attr, method_name
            )
        )
        setattr(dialog, proxy_attr, proxy)
    proxy.setText(text)
    proxy.setGeometry(x, y, 140, 38)
    proxy.setEnabled(True)
    proxy.setToolTip(text)
    _style_search_page_button(proxy)
    proxy.show()
    proxy.raise_()


def _trigger_search_page_button(dialog, source_attr, method_name):
    source = getattr(dialog, source_attr, None)
    if source is not None and not source.isEnabled():
        return
    return getattr(dialog, method_name)()


def _open_manager_advanced_search(manager, target):
    try:
        import customComponents

        search_dialog = customComponents.NameSearchDialog("", manager.editor)
        if target == "card":
            search_dialog._card_tab_manager = manager
        advanced_dialog = _AdvancedSearchDialog(search_dialog, manager, target)
        if advanced_dialog.exec_() == QDialog.Accepted and target == "card":
            search_dialog.exec_()
    except Exception:
        _tab_log("打开高级搜索失败:\n" + traceback.format_exc())
        return


def _remove_editor_search_buttons(editor):
    name_search_button = getattr(editor, "name_search_btn", None)
    if name_search_button is not None:
        name_search_button.hide()

    card_pass_button = getattr(editor, "card_pass_btn", None)
    if card_pass_button is not None:
        QTimer.singleShot(600, card_pass_button.hide)


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from card_library import _load_packs
