"""自定义文本（卡面上自由摆放的文字）。

由补丁分片 p13、p14 整理而来。
"""

import os
import sys
import traceback

from PyQt5.QtCore import Qt

from common import _app_dir, _attach_editor_button, _tab_log, _widget_scene


# ---------------------------------------------------------------------------
# 自定义文本（对应 YGOLD 的 FreeTextItem / TextGroup.setFreeTexts / TextEditorDialog）
# ---------------------------------------------------------------------------
_FREE_TEXT_DEFAULT_FONTS = (
    "mold/font/ygosc.ttf",
    "mold/font/Yu-Gi-Oh!DFGLeisho4.ttf",
    "mold/font/cn.ttf",
    "mold/font/ygo-tc2.ttf",
    "mold/font/YGO_JP_NO.ttf",
    "Microsoft YaHei",
    "SimSun",
    "SimHei",
    "KaiTi",
    "Arial",
    "Times New Roman",
    "Consolas",
)
_FREE_TEXT_DEFAULT_COUNT = 5
_FREE_TEXT_BASE_PIXEL_SIZE = 48
_FREE_TEXT_SLOT_LIMIT = 12
_free_text_font_cache = {}
_free_text_graphics_class_cache = None


class _FreeTextItem:
    """一条自定义文本的数据模型，字段与 YGOLD 的 FreeTextItem 保持一致。"""

    __slots__ = ("visible", "textFont", "color", "text", "x", "y", "scale")

    def __init__(self, text=""):
        self.visible = False
        self.textFont = 0
        self.color = "#000000"
        self.text = text
        self.x = 0
        self.y = 0
        self.scale = 100


def _free_text_asset_path(name):
    name = str(name or "")
    if not name:
        return ""
    if os.path.isabs(name):
        return name if os.path.exists(name) else ""
    roots = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(meipass)
    roots.append(os.path.join(_app_dir(), "提取文件", "_internal"))
    roots.append(_app_dir())
    for root in roots:
        path = os.path.join(root, name)
        if os.path.exists(path):
            return path
    return ""


def _free_text_fonts(editor):
    fonts = None
    config = getattr(editor, "config", None)
    if config is not None:
        fonts = getattr(config, "free_text_font", None)
    if not fonts:
        fonts = _FREE_TEXT_DEFAULT_FONTS
    return list(fonts)


def _free_text_count(editor):
    config = getattr(editor, "config", None)
    count = getattr(config, "free_text_num", None) if config is not None else None
    try:
        count = int(count)
    except (TypeError, ValueError):
        count = _FREE_TEXT_DEFAULT_COUNT
    return max(1, min(_FREE_TEXT_SLOT_LIMIT, count))


def _free_text_family(editor, index):
    """把字体条目（ttf 路径或系统字体名）解析成 Qt 可用的字体族名。"""
    from PyQt5.QtGui import QFontDatabase

    entries = _free_text_fonts(editor)
    if not entries:
        return ""
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0
    if not (0 <= index < len(entries)):
        index = 0
    entry = str(entries[index])
    if not entry.lower().endswith((".ttf", ".otf", ".ttc")):
        return entry
    if entry in _free_text_font_cache:
        return _free_text_font_cache[entry]
    family = ""
    path = _free_text_asset_path(entry)
    if path:
        try:
            font_id = QFontDatabase.addApplicationFont(path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                family = families[0]
        except Exception:
            family = ""
    _free_text_font_cache[entry] = family
    return family


def _free_text_graphics_class():
    global _free_text_graphics_class_cache
    if _free_text_graphics_class_cache is not None:
        return _free_text_graphics_class_cache
    from PyQt5.QtGui import QColor, QFont
    from PyQt5.QtWidgets import QGraphicsItem, QGraphicsTextItem

    class _FreeTextGraphicsItem(QGraphicsTextItem):
        """场景中可鼠标拖动的自定义文本项。"""

        def __init__(self, model, editor):
            super().__init__()
            self._model = model
            self._editor = editor
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemIsSelectable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.setTextInteractionFlags(Qt.NoTextInteraction)
            self._drag_scene_start = None
            self._drag_item_start = None
            self.setAcceptedMouseButtons(Qt.LeftButton)
            self.apply_model()

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_scene_start = event.scenePos()
                self._drag_item_start = self.pos()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if (
                self._drag_scene_start is not None
                and self._drag_item_start is not None
                and event.buttons() & Qt.LeftButton
            ):
                delta = event.scenePos() - self._drag_scene_start
                self.setPos(self._drag_item_start + delta)
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_scene_start = None
                self._drag_item_start = None
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def apply_model(self):
            model = self._model
            text = str(model.text or "")
            self.setPlainText(text)
            font = QFont()
            family = _free_text_family(self._editor, model.textFont)
            if family:
                font.setFamily(family)
            font.setPixelSize(_FREE_TEXT_BASE_PIXEL_SIZE)
            self.setFont(font)
            try:
                self.setDefaultTextColor(QColor(str(model.color or "#000000")))
            except Exception:
                pass
            try:
                scale = float(model.scale or 100) / 100.0
            except (TypeError, ValueError):
                scale = 1.0
            self.setScale(max(0.05, min(20.0, scale)))
            self.setPos(float(model.x or 0), float(model.y or 0))
            self.setVisible(bool(model.visible) and bool(text))

        def itemChange(self, change, value):
            if change == QGraphicsItem.ItemPositionHasChanged:
                try:
                    pos = self.pos()
                    self._model.x = round(pos.x())
                    self._model.y = round(pos.y())
                    self._sync_position_widgets()
                except Exception:
                    pass
            return super().itemChange(change, value)

        def _sync_position_widgets(self):
            dialog = getattr(self._editor, "_free_text_dialog", None)
            if dialog is None:
                return
            try:
                dialog.sync_position(self._model)
            except Exception:
                pass

    _free_text_graphics_class_cache = _FreeTextGraphicsItem
    return _free_text_graphics_class_cache


def _refresh_free_text(editor):
    for graphics, _model in getattr(editor, "_free_text_graphics", None) or ():
        try:
            graphics.apply_model()
        except Exception:
            pass


def _inject_free_text_into_data(editor, data):
    items = getattr(editor, "free_text_items", None)
    if not items or not isinstance(data, dict):
        return data
    try:
        data["free_text_visible"] = [bool(item.visible) for item in items]
        data["free_text_textFont"] = [int(item.textFont) for item in items]
        data["free_text_color"] = [str(item.color) for item in items]
        data["free_text_text"] = [str(item.text) for item in items]
        data["free_text_x"] = [int(item.x) for item in items]
        data["free_text_y"] = [int(item.y) for item in items]
        data["free_text_scale"] = [int(item.scale) for item in items]
    except Exception:
        pass
    return data


def _apply_free_text_data(editor, data):
    items = getattr(editor, "free_text_items", None)
    if not items or not isinstance(data, dict):
        return
    texts = data.get("free_text_text") or []
    visible = data.get("free_text_visible") or []
    fonts = data.get("free_text_textFont") or []
    colors = data.get("free_text_color") or []
    xs = data.get("free_text_x") or []
    ys = data.get("free_text_y") or []
    scales = data.get("free_text_scale") or []

    def pick(seq, index, default):
        try:
            return seq[index]
        except (IndexError, TypeError):
            return default

    for index, item in enumerate(items):
        try:
            item.text = str(pick(texts, index, "") or "")
            item.visible = bool(pick(visible, index, False))
            item.textFont = int(pick(fonts, index, 0) or 0)
            item.color = str(pick(colors, index, "#000000") or "#000000")
            item.x = int(pick(xs, index, 0) or 0)
            item.y = int(pick(ys, index, 0) or 0)
            item.scale = int(pick(scales, index, 100) or 100)
        except Exception:
            continue
    _refresh_free_text(editor)


def _open_free_text_editor(editor):
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import (
        QCheckBox,
        QColorDialog,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
    )

    items = getattr(editor, "free_text_items", None)
    if not items:
        return
    fonts = _free_text_fonts(editor)
    previous = getattr(editor, "_free_text_dialog", None)
    if previous is not None:
        try:
            previous.close()
        except Exception:
            pass

    class _FreeTextDialog(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("自定义文本")
            self._loading = False
            layout = QVBoxLayout(self)

            slot_row = QHBoxLayout()
            slot_row.addWidget(QLabel("文本项"))
            self.slot_box = QComboBox()
            for index in range(len(items)):
                self.slot_box.addItem("文本 %d" % (index + 1))
            slot_row.addWidget(self.slot_box, 1)
            self.visible_box = QCheckBox("显示")
            slot_row.addWidget(self.visible_box)
            layout.addLayout(slot_row)

            form = QFormLayout()
            self.text_edit = QLineEdit()
            form.addRow("内容", self.text_edit)
            self.font_box = QComboBox()
            for entry in fonts:
                self.font_box.addItem(os.path.basename(str(entry)), str(entry))
            form.addRow("字体", self.font_box)
            self.scale_spin = QSpinBox()
            self.scale_spin.setRange(10, 1000)
            self.scale_spin.setSuffix(" %")
            form.addRow("尺寸", self.scale_spin)
            self.x_spin = QSpinBox()
            self.x_spin.setRange(-5000, 5000)
            form.addRow("X", self.x_spin)
            self.y_spin = QSpinBox()
            self.y_spin.setRange(-5000, 5000)
            form.addRow("Y", self.y_spin)
            self.color_button = QPushButton("选择颜色")
            form.addRow("颜色", self.color_button)
            layout.addLayout(form)

            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(self.accept)
            layout.addWidget(buttons)

            self.slot_box.currentIndexChanged.connect(self.load_current)
            self.visible_box.toggled.connect(self.commit)
            self.text_edit.textChanged.connect(self.commit)
            self.font_box.currentIndexChanged.connect(self.commit)
            self.scale_spin.valueChanged.connect(self.commit)
            self.x_spin.valueChanged.connect(self.commit)
            self.y_spin.valueChanged.connect(self.commit)
            self.color_button.clicked.connect(self.pick_color)
            self.load_current()

        def current_item(self):
            index = self.slot_box.currentIndex()
            if 0 <= index < len(items):
                return items[index]
            return None

        def load_current(self):
            item = self.current_item()
            if item is None:
                return
            self._loading = True
            try:
                self.text_edit.setText(str(item.text or ""))
                self.visible_box.setChecked(bool(item.visible))
                self.scale_spin.setValue(int(item.scale or 100))
                self.x_spin.setValue(int(item.x or 0))
                self.y_spin.setValue(int(item.y or 0))
                entry = None
                try:
                    entry = str(fonts[int(item.textFont)])
                except (IndexError, TypeError, ValueError):
                    entry = None
                if entry is not None:
                    position = self.font_box.findData(entry)
                    if position >= 0:
                        self.font_box.setCurrentIndex(position)
                self._update_color_button(item.color)
            finally:
                self._loading = False

        def _update_color_button(self, color):
            try:
                self.color_button.setStyleSheet(
                    "background-color: %s;" % str(color or "#000000")
                )
            except Exception:
                pass

        def commit(self, *_args):
            if self._loading:
                return
            item = self.current_item()
            if item is None:
                return
            item.text = self.text_edit.text()
            item.visible = bool(self.visible_box.isChecked())
            item.scale = int(self.scale_spin.value())
            item.x = int(self.x_spin.value())
            item.y = int(self.y_spin.value())
            item.textFont = self.font_box.currentIndex()
            _refresh_free_text(editor)

        def pick_color(self):
            item = self.current_item()
            if item is None:
                return
            try:
                chosen = QColorDialog.getColor(
                    QColor(str(item.color or "#000000")), self, "选择文本颜色"
                )
            except Exception:
                return
            if chosen.isValid():
                item.color = chosen.name()
                self._update_color_button(item.color)
                _refresh_free_text(editor)

        def sync_position(self, model):
            if self._loading:
                return
            if model is not self.current_item():
                return
            self._loading = True
            try:
                self.x_spin.setValue(int(model.x or 0))
                self.y_spin.setValue(int(model.y or 0))
            finally:
                self._loading = False

    dialog = _FreeTextDialog(editor)
    editor._free_text_dialog = dialog
    dialog.exec_()
    editor._free_text_dialog = None


def _install_free_text_button(editor):
    try:
        if getattr(editor, "_free_text_button_installed", False):
            return
        from PyQt5.QtWidgets import QPushButton

        button = QPushButton("自定义文本", editor)
        button.setObjectName("free_text_button")
        button.clicked.connect(lambda _=False, target=editor: _open_free_text_editor(target))
        editor.free_text_button = button
        editor._free_text_button_installed = True
        placed = _attach_editor_button(
            editor, button, ("batch_btn", "random_btn", "name_search_btn")
        )
        if not placed:
            _tab_log("自定义文本按钮未能进入布局，已作为浮动按钮放置。")
    except Exception:
        _tab_log("创建自定义文本按钮失败:\n" + traceback.format_exc())


# ---------------------------------------------------------------------------
# Custom text: resolve the actual editor scene instead of relying on an
# instance attribute that does not exist in YGODIY 2.0.0.
# ---------------------------------------------------------------------------
def _ensure_free_text(editor):
    if editor is None:
        return
    scene = _widget_scene(editor)
    if scene is None:
        return
    graphics = list(getattr(editor, "_free_text_graphics", ()) or ())
    if graphics and all(item.scene() is scene for item, _model in graphics):
        _refresh_free_text(editor)
        return
    for item, _model in graphics:
        try:
            if item.scene() is not None:
                item.scene().removeItem(item)
        except Exception:
            pass
    try:
        count = _free_text_count(editor)
        models = [_FreeTextItem("") for _ in range(count)]
        graphics_class = _free_text_graphics_class()
        pairs = []
        for model in models:
            item = graphics_class(model, editor)
            item.setZValue(2000.0)
            scene.addItem(item)
            pairs.append((item, model))
        editor.free_text_items = models
        editor._free_text_graphics = pairs
        editor._free_text_installed = True
        _refresh_free_text(editor)
    except Exception:
        pass
