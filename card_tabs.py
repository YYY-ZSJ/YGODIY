"""卡包与标签页管理（_CardTabManager）：状态读写与历史、卡图缓存、撤销、卡包导出。

由补丁分片 p01、p02、p03、p04、p10、p11、p12、p14、p15、p40、p46、p47 整理而来。
"""

import base64
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import threading
import time
import traceback

from PIL import Image
from PyQt5.QtCore import QEvent, QObject, QTimer, Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from common import (
    _ATTRIBUTES,
    _EFFECT_LAYOUT_DEFAULTS,
    _LINK_MARKERS,
    _MAIN_TYPES,
    _RACES,
    _app_dir,
    _bounded_cache_get,
    _bounded_cache_put,
    _json_clone,
    _safe_call,
    _schedule_preview_update_restore,
    _tab_log,
)


_CARD_TABS_STATE_FILE = "制卡器标签页.json"
_CARD_TABS_BACKUP_FILE = "制卡器标签页.json.bak"
_CARD_TABS_ASSET_DIR = "制卡器标签页资源"
_CARD_TAB_IMAGE_REF_KEY = "_image_ref"
_TEXT_ADJUST_DEFAULTS_VERSION = 2

_IMAGE_CACHE_LIMIT = 24
_RENDER_CACHE_LIMIT = 24

# 切卡 / 切卡包后，延迟多久把状态写盘（毫秒）；期间再次切换会重新计时。
_NAVIGATION_WRITE_DELAY_MS = 3000
_IMAGE_PREWARM_LIMIT = 8
_IMAGE_PREWARM_BYTE_BUDGET = 24 * 1024 * 1024

_CARD_TABS_INSTALL_DELAY_MS = 120
_UNDO_HISTORY_LIMIT = 100

_FALLBACK_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR4nGP4//8/AwAI/AL+p5qgoAAAAABJRU5ErkJggg=="
)

_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _safe_path_component(value, fallback):
    text = str(value or "").strip()
    for char in '<>:"/\\|?*':
        text = text.replace(char, "_")
    text = "".join("_" if ord(char) < 32 else char for char in text).strip(" .")
    if not text:
        text = str(fallback or "导出")
    if text.upper() in _WINDOWS_RESERVED_NAMES:
        text = "_" + text
    return text


def _dedup_export_base(base, counts):
    key = base.casefold()
    count = counts.get(key, 0)
    counts[key] = count + 1
    if count:
        return f"{base}({count})"
    return base


def _card_tabs_state_path():
    return os.path.join(_app_dir(), _CARD_TABS_STATE_FILE)


def _card_tabs_backup_path():
    return os.path.join(_app_dir(), _CARD_TABS_BACKUP_FILE)


def _card_tabs_asset_dir():
    return os.path.join(_app_dir(), _CARD_TABS_ASSET_DIR)


_STATE_HISTORY_LIMIT = 8
_STATE_HISTORY_INTERVAL = 60.0
_state_history_last = [0.0]


def _state_history_dir():
    return os.path.join(_app_dir(), "制卡器标签页历史")


def _rotate_state_history(path):
    """Snapshot the outgoing state file so a bad write can never wipe user data.

    At most one snapshot per minute, keeping the newest _STATE_HISTORY_LIMIT.
    """
    try:
        now = time.time()
        if now - _state_history_last[0] < _STATE_HISTORY_INTERVAL:
            return
        if not os.path.exists(path):
            return
        history_dir = _state_history_dir()
        os.makedirs(history_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = os.path.join(history_dir, "标签页-" + stamp + ".json")
        if os.path.exists(target):
            target = os.path.join(
                history_dir,
                "标签页-" + stamp + "-" + str(int(now * 1000) % 1000) + ".json",
            )
        shutil.copy2(path, target)
        _state_history_last[0] = now
        snapshots = sorted(
            name for name in os.listdir(history_dir) if name.endswith(".json")
        )
        for name in snapshots[:-_STATE_HISTORY_LIMIT]:
            try:
                os.remove(os.path.join(history_dir, name))
            except OSError:
                pass
    except Exception:
        pass


def _card_tab_image_path(image_ref):
    image_ref = str(image_ref or "")
    if len(image_ref) != 64 or any(char not in "0123456789abcdef" for char in image_ref):
        return None
    return os.path.join(_card_tabs_asset_dir(), image_ref + ".img")


def _externalize_image_data(data):
    if not isinstance(data, dict):
        return False
    encoded = data.get("image")
    if not isinstance(encoded, str) or not encoded:
        return False
    try:
        image_bytes = base64.b64decode(encoded)
        image_ref = hashlib.sha256(image_bytes).hexdigest()
        image_path = _card_tab_image_path(image_ref)
        if image_path is None:
            return False
        if not os.path.exists(image_path):
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            temp_path = image_path + f".tmp-{os.getpid()}-{threading.get_ident()}"
            try:
                with open(temp_path, "wb") as image_file:
                    image_file.write(image_bytes)
                os.replace(temp_path, image_path)
            finally:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass
        data[_CARD_TAB_IMAGE_REF_KEY] = image_ref
        data.pop("image", None)
        return True
    except Exception:
        return False


def _externalize_state_images(state):
    migrated = 0
    for tab in _state_tabs_for_upgrade(state):
        if isinstance(tab, dict) and _externalize_image_data(tab.get("data")):
            migrated += 1
    return migrated


def _referenced_image_path(data):
    if not isinstance(data, dict):
        return None
    image_path = _card_tab_image_path(data.get(_CARD_TAB_IMAGE_REF_KEY))
    return image_path if image_path and os.path.exists(image_path) else None


def _load_referenced_image(data):
    image_path = _referenced_image_path(data)
    if image_path is None:
        return None
    try:
        with Image.open(image_path) as source:
            image = source.convert("RGBA")
            image.load()
            return image
    except Exception:
        return None


def _data_has_saved_image(data):
    return bool(
        isinstance(data, dict)
        and (data.get("image") or _referenced_image_path(data))
    )


def _undo_data_signature(data):
    try:
        return json.dumps(
            data,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        return repr(data)


def _tab_title_from_data(data, fallback):
    title = ""
    if isinstance(data, dict):
        title = str(data.get("name") or "").strip()
    if not title:
        title = fallback
    return title[:14] + ("..." if len(title) > 14 else "")


def _enable_text_adjust_defaults_in_data(data):
    if not isinstance(data, dict):
        return data
    data.setdefault("text_sizeable", True)
    data.setdefault("text_size_change", 0)
    data.setdefault("text_weightable", True)
    data.setdefault("text_weight_change", 0)
    for key, value in _EFFECT_LAYOUT_DEFAULTS.items():
        data.setdefault(key, value)
    return data


def _state_is_usable(state):
    return isinstance(state, dict) and (
        isinstance(state.get("packs"), list)
        or isinstance(state.get("tabs"), list)
    )


def _state_tabs_for_upgrade(state):
    if isinstance(state.get("packs"), list):
        return [
            tab
            for pack in state.get("packs") or []
            if isinstance(pack, dict)
            for tab in (pack.get("tabs") or [])
        ]
    return state.get("tabs") or []


def _upgrade_state_defaults(state):
    if state.get("text_adjust_defaults_version", 0) >= _TEXT_ADJUST_DEFAULTS_VERSION:
        return state
    for tab in _state_tabs_for_upgrade(state):
        if isinstance(tab, dict):
            _enable_text_adjust_defaults_in_data(tab.get("data"))
    state["text_adjust_defaults_version"] = _TEXT_ADJUST_DEFAULTS_VERSION
    return state


def _import_data_with_image(data, default_data, image_sentinel=None):
    if not isinstance(data, dict):
        return data
    if image_sentinel is not None:
        import_data = dict(data)
        import_data["image"] = image_sentinel
        return import_data
    if data.get("image"):
        return data
    import_data = dict(data)
    default_image = (
        default_data.get("image")
        if isinstance(default_data, dict) and default_data.get("image")
        else None
    )
    import_data["image"] = default_image or _FALLBACK_IMAGE_BASE64
    return import_data


class _UndoEventFilter(QObject):
    def __init__(self, manager):
        super().__init__(manager.app)
        self.manager = manager

    def eventFilter(self, obj, event):
        try:
            return self._handle_event(obj, event)
        except Exception:
            _tab_log("处理撤销事件失败:\n" + traceback.format_exc())
            return False

    def _handle_event(self, obj, event):
        event_type = event.type()
        if event_type not in (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel):
            return False
        manager = self.manager
        if not manager._should_handle_undo_event(obj):
            return False

        if event_type == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            control_modifier = getattr(Qt, "ControlModifier", 0)
            if key == getattr(Qt, "Key_Z", None) and modifiers & control_modifier:
                return bool(manager.undo())

            ignored_keys = {
                getattr(Qt, "Key_Control", None),
                getattr(Qt, "Key_Shift", None),
                getattr(Qt, "Key_Alt", None),
                getattr(Qt, "Key_Meta", None),
                getattr(Qt, "Key_Escape", None),
            }
            if key not in ignored_keys:
                manager._record_undo_snapshot()
            return False

        if event_type == QEvent.MouseButtonPress:
            manager._record_undo_snapshot()
        elif event_type == QEvent.Wheel:
            # 一次滚动手势只记一步撤销：连续滚动（间隔小于 _UNDO_WHEEL_GESTURE_GAP 秒）
            # 算同一次。以前每一格都做一次快照（可能是完整导出），滚轮缩放超框卡图时很卡。
            now = time.monotonic()
            last = getattr(manager, "_undo_last_wheel", 0.0)
            manager._undo_last_wheel = now
            if now - last >= _UNDO_WHEEL_GESTURE_GAP:
                manager._record_undo_snapshot()
        return False


_UNDO_WHEEL_GESTURE_GAP = 0.6


class _CardTabManager:
    _PANEL_STYLE = """
        QLabel#card_pack_title, QLabel#card_tab_title {
            padding: 5px;
            font-weight: bold;
        }
        QListWidget#card_pack_list::item, QListWidget#card_tab_list::item {
            padding: 7px 4px;
            min-height: 28px;
        }
        QPushButton { min-height: 25px; }
    """

    def __init__(self, app, editor):
        self.app = app
        self.editor = editor
        self.packs = []
        self.current_pack_index = -1
        self.tabs = []
        self.current_index = -1
        self._busy = False
        self._image_dirty = False
        self._state_write_lock = threading.Lock()
        self._state_file_lock = threading.Lock()
        self._state_write_generation = 0
        self._state_write_pending = None
        self._state_writer_running = False
        self._apply_token = 0
        self._image_cache = {}
        self._render_cache = {}
        self._undo_history = []
        self._undo_recording = False
        self._undo_applying = False
        self._undo_method_depth = 0
        self._undo_event_filter = None
        self._default_data = self._blue_eyes_minimal_data()
        _externalize_image_data(self._default_data)
        _enable_text_adjust_defaults_in_data(self._default_data)
        self._default_visuals = (
            self._capture_editor_visuals()
            if self._editor_is_blue_eyes_default()
            else {}
        )

        self.pack_panel = self._build_pack_panel()
        self.panel = self._build_panel()
        self._insert_panel()
        self._load_initial_packs()
        self._start_image_prewarm()
        self._wrap_image_dirty_methods()
        self._install_pack_export_button()
        self._connect_signals()
        self._install_undo_support()

    def _build_pack_panel(self):
        panel = QFrame(self.app)
        panel.setObjectName("card_pack_panel")
        panel.setFixedWidth(130)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(self._PANEL_STYLE)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        title = QLabel("卡包", panel)
        title.setObjectName("card_pack_title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.pack_list = QListWidget(panel)
        self.pack_list.setObjectName("card_pack_list")
        self.pack_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pack_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.pack_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pack_list.setSpacing(4)
        self.pack_list.setUniformItemSizes(True)
        layout.addWidget(self.pack_list, 1)

        self.new_pack_button = QPushButton("新建", panel)
        self.copy_pack_button = QPushButton("复制", panel)
        self.delete_pack_button = QPushButton("删除", panel)
        layout.addWidget(self.new_pack_button)
        layout.addWidget(self.copy_pack_button)
        layout.addWidget(self.delete_pack_button)
        self.pack_advanced_search_button = QPushButton("高级搜索", panel)
        layout.addWidget(self.pack_advanced_search_button)
        return panel

    def _build_panel(self):
        panel = QFrame(self.app)
        panel.setObjectName("card_tab_panel")
        panel.setFixedWidth(142)
        panel.setFrameShape(QFrame.StyledPanel)
        panel.setStyleSheet(self._PANEL_STYLE)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(5)

        title = QLabel("卡片", panel)
        title.setObjectName("card_tab_title")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.tab_list = QListWidget(panel)
        self.tab_list.setObjectName("card_tab_list")
        self.tab_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_list.setSpacing(4)
        self.tab_list.setUniformItemSizes(True)
        layout.addWidget(self.tab_list, 1)

        self.new_button = QPushButton("新建", panel)
        self.copy_button = QPushButton("复制", panel)
        self.delete_button = QPushButton("删除", panel)
        layout.addWidget(self.new_button)
        layout.addWidget(self.copy_button)
        layout.addWidget(self.delete_button)
        self.card_advanced_search_button = QPushButton("高级搜索", panel)
        layout.addWidget(self.card_advanced_search_button)
        return panel

    def _insert_panel(self):
        layout = getattr(self.app, "hbox", None)
        if layout is None:
            layout = self.app.layout()
        if layout is None:
            return
        layout.insertWidget(0, self.pack_panel)
        layout.insertWidget(1, self.panel)
        try:
            available = QApplication.primaryScreen().availableGeometry().width()
            added_width = self.pack_panel.width() + self.panel.width()
            self.app.resize(min(self.app.width() + added_width, available), self.app.height())
        except Exception:
            pass

    def _connect_signals(self):
        self.pack_list.currentRowChanged.connect(self._on_pack_changed)
        self.pack_list.itemChanged.connect(self._on_pack_item_changed)
        self.pack_list.customContextMenuRequested.connect(self._show_pack_context_menu)
        self.pack_advanced_search_button.clicked.connect(self.open_pack_advanced_search)
        self.new_pack_button.clicked.connect(self.new_pack)
        self.copy_pack_button.clicked.connect(self.copy_pack)
        self.delete_pack_button.clicked.connect(self.delete_pack)
        self.tab_list.currentRowChanged.connect(self._on_row_changed)
        self.tab_list.customContextMenuRequested.connect(self._show_card_context_menu)
        self.card_advanced_search_button.clicked.connect(self.open_card_advanced_search)
        self.new_button.clicked.connect(self.new_tab)
        self.copy_button.clicked.connect(self.copy_tab)
        self.delete_button.clicked.connect(self.delete_tab)
        try:
            self.editor.card_name_edit.textChanged.connect(self._on_card_name_changed)
        except Exception:
            pass
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.aboutToQuit.connect(self.save_all)
        self.autosave_timer = QTimer(self.panel)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start(30000)

    def _install_undo_support(self):
        self._wrap_undo_methods()
        app_instance = QApplication.instance()
        if app_instance is None or self._undo_event_filter is not None:
            return
        try:
            self._undo_event_filter = _UndoEventFilter(self)
            app_instance.installEventFilter(self._undo_event_filter)
        except Exception:
            self._undo_event_filter = None
            _tab_log("安装撤销事件过滤器失败:\n" + traceback.format_exc())

    def _wrap_undo_methods(self):
        for method_name in (
            "after_info_fetch",
            "on_cardpass_return",
            "random_card",
            "on_import_clicked",
            "load_image_nocrop",
            "load_image_crop",
            "set_card_img_nocrop",
            "set_card_img_crop",
            "on_overframe_upload",
            "set_overframe_img",
            "overframe_toggle_change",
            "show_overframe_setting",
            "switch_card_type",
            "switch_template",
            "switch_info",
            "attribute_clicked",
            "star_zero_clicked",
            "star_clicked",
            "rank_zero_clicked",
            "rank_clicked",
            "detail_custom_cliked",
            "show_hide_attr",
            "full_effect_clicked",
            "first_line_compress",
            "update_MT_type",
            "link_btn_clicked",
            "color_btn_clicked",
            "change_color_mode",
            "advanced_btn_clicked",
            "holo_change",
            "copyright_change",
            "rare_change",
            "watermark_change",
            "LB_ratio_changed",
            "LB_Zack_clicked",
            "on_toggle_source",
            "on_local_clicked",
            "on_toggle_pass",
            "on_toggle_pack",
            "on_toggle_holo",
            "on_toggle_copy",
            "on_toggle_corner",
            "on_toggle_ATK_DEF",
            "update_tc_type",
            "name_align_change",
            "text_align_change",
        ):
            method = getattr(self.editor, method_name, None)
            if method is None or getattr(method, "_undo_history_wrapped", False):
                continue

            def wrapped(*args, _method=method, **kwargs):
                should_record = self._undo_method_depth == 0
                if should_record:
                    self._record_undo_snapshot()
                self._undo_method_depth += 1
                try:
                    return _method(*args, **kwargs)
                finally:
                    self._undo_method_depth = max(0, self._undo_method_depth - 1)

            wrapped._undo_history_wrapped = True
            setattr(self.editor, method_name, wrapped)

    def _event_widget(self, obj):
        current = obj
        while current is not None:
            if isinstance(current, QWidget):
                return current
            try:
                current = current.parent()
            except Exception:
                return None
        return None

    def _widget_is_child_of(self, widget, parent):
        if widget is None or parent is None:
            return False
        current = widget
        while current is not None:
            if current is parent:
                return True
            try:
                current = current.parentWidget()
            except Exception:
                return False
        return False

    def _should_handle_undo_event(self, obj):
        if self._busy or self._undo_applying or self._undo_recording:
            return False
        widget = self._event_widget(obj)
        if widget is None:
            return False
        try:
            if widget.window() is not self.app:
                return False
        except Exception:
            return False
        if self._widget_is_child_of(widget, self.pack_panel):
            return False
        if self._widget_is_child_of(widget, self.panel):
            return False
        ai = getattr(self.app, "_ai_dock", None)
        if ai is not None and self._widget_is_child_of(widget, ai.dock):
            return False
        return self._current_tab() is not None

    def _last_undo_entry_index(self, tab_id):
        for index in range(len(self._undo_history) - 1, -1, -1):
            if self._undo_history[index].get("tab_id") == tab_id:
                return index
        return -1

    def _update_current_tab_data(self, data):
        tab = self._current_tab()
        if tab is None or not isinstance(data, dict):
            return
        title = _tab_title_from_data(data, f"卡片{self.current_index + 1}")
        tab["title"] = title
        tab["data"] = _json_clone(data)
        item = self.tab_list.item(self.current_index)
        if item is not None:
            item.setText(title)
            item.setToolTip(title)

    def _capture_undo_data(self):
        if not (0 <= self.current_index < len(self.tabs)):
            return None
        self._cache_current_visuals()
        if self._image_dirty:
            data = self._export_editor_data()
            if data:
                _externalize_image_data(data)
                self._image_dirty = False
                self._update_current_tab_data(data)
        else:
            data = self._collect_editor_data_fast()
        if not isinstance(data, dict):
            return None
        _externalize_image_data(data)
        return _json_clone(data)

    def _record_undo_snapshot(self):
        if self._busy or self._undo_applying or self._undo_recording:
            return
        tab = self._current_tab()
        if tab is None:
            return
        self._undo_recording = True
        try:
            data = self._capture_undo_data()
            if not data:
                return
            signature = _undo_data_signature(data)
            tab_id = id(tab)
            last_index = self._last_undo_entry_index(tab_id)
            if (
                last_index >= 0
                and self._undo_history[last_index].get("signature") == signature
            ):
                return
            self._undo_history.append(
                {
                    "tab_id": tab_id,
                    "signature": signature,
                    "data": data,
                }
            )
            while len(self._undo_history) > _UNDO_HISTORY_LIMIT:
                self._undo_history.pop(0)
        finally:
            self._undo_recording = False

    def undo(self):
        if self._busy or self._undo_applying:
            return False
        tab = self._current_tab()
        if tab is None:
            return False
        self._undo_recording = True
        try:
            current_data = self._capture_undo_data()
            current_signature = _undo_data_signature(current_data) if current_data else None
        finally:
            self._undo_recording = False

        tab_id = id(tab)
        entry = None
        while True:
            index = self._last_undo_entry_index(tab_id)
            if index < 0:
                return False
            candidate = self._undo_history.pop(index)
            if candidate.get("signature") != current_signature:
                entry = candidate
                break

        data = _json_clone(entry.get("data") or {})
        if not data:
            return False
        self._undo_applying = True
        try:
            _externalize_image_data(data)
            self._update_current_tab_data(data)
            self._image_cache.pop(tab_id, None)
            self._render_cache.pop(tab_id, None)
            self._image_dirty = False
            self._apply_editor_data(data)
            self._request_write_state()
            return True
        finally:
            self._undo_applying = False

    def _install_pack_export_button(self):
        button = getattr(self.editor, "batch_btn", None)
        if button is None:
            return
        try:
            button.setText("卡包导出")
            button.setToolTip("导出当前卡包中的所有卡片")
        except Exception:
            pass
        try:
            button.clicked.disconnect()
        except Exception:
            pass

        def on_clicked(*args, **kwargs):
            return self.export_current_pack()

        self._pack_export_click_handler = on_clicked
        try:
            button.clicked.connect(on_clicked)
        except Exception:
            pass
        try:
            self.editor.on_batch_clicked = on_clicked
        except Exception:
            pass

    def _wrap_image_dirty_methods(self):
        for method_name in (
            "set_card_img_nocrop",
            "set_card_img_crop",
            "transform_normal_img",
            "transform_LB_img",
            "on_overframe_upload",
            "set_overframe_img",
        ):
            method = getattr(self.editor, method_name, None)
            if method is None or getattr(method, "_card_tabs_wrapped", False):
                continue

            def wrapped(*args, _method=method, **kwargs):
                result = _method(*args, **kwargs)
                if not self._busy:
                    self._image_dirty = True
                return result

            wrapped._card_tabs_wrapped = True
            setattr(self.editor, method_name, wrapped)

    def _new_default_tab(self):
        return {
            "title": "青眼白龙",
            "data": _json_clone(self._default_data),
        }

    def _new_default_pack(self, title="卡包1"):
        return {
            "title": title,
            "current_index": 0,
            "tabs": [self._new_default_tab()],
        }

    def _normalize_pack(self, pack, fallback_title):
        if not isinstance(pack, dict):
            pack = {}
        title = str(pack.get("title") or fallback_title).strip() or fallback_title
        tabs = [
            tab
            for tab in pack.get("tabs", [])
            if isinstance(tab, dict) and isinstance(tab.get("data"), dict)
        ]
        if not tabs:
            tabs = [self._new_default_tab()]
        try:
            current = int(pack.get("current_index", 0) or 0)
        except Exception:
            current = 0
        current = max(0, min(current, len(tabs) - 1))
        normalized = {"title": title, "current_index": current, "tabs": tabs}
        if isinstance(pack.get("diy"), dict):
            normalized["diy"] = pack["diy"]  # DIY 工作台的卡包设置（作者、卡号段、自己的字段）
        return normalized

    def _load_initial_packs(self):
        saved = self._read_state()
        needs_state_write = bool(getattr(self, "_loaded_state_needs_write", False))
        if saved and isinstance(saved.get("packs"), list):
            packs = saved.get("packs") or []
            current_pack = saved.get("current_pack_index", 0)
        elif saved and isinstance(saved.get("tabs"), list):
            needs_state_write = True
            packs = [
                {
                    "title": "默认卡包",
                    "current_index": saved.get("current_index", 0),
                    "tabs": saved.get("tabs") or [],
                }
            ]
            current_pack = 0
        else:
            # 状态文件存在却读不出内容时,绝不能拿默认数据覆盖它。
            if os.path.exists(_card_tabs_state_path()):
                _tab_log("标签页数据无法解析，已保留原文件不做覆盖。")
                needs_state_write = False
            else:
                needs_state_write = True
            packs = [self._new_default_pack()]
            current_pack = 0

        self.packs = [
            self._normalize_pack(pack, f"卡包{index + 1}")
            for index, pack in enumerate(packs)
        ]
        if not self.packs:
            self.packs = [self._new_default_pack()]
            needs_state_write = True

        try:
            current_pack = int(current_pack or 0)
        except Exception:
            current_pack = 0
        current_pack = max(0, min(current_pack, len(self.packs) - 1))
        self.current_pack_index = current_pack
        current_pack_data = self.packs[current_pack]
        self.tabs = current_pack_data["tabs"]
        self.current_index = current_pack_data["current_index"]

        self._busy = True
        try:
            self.pack_list.clear()
            for index, pack in enumerate(self.packs):
                self._add_pack_item(index, pack)
            self.pack_list.setCurrentRow(current_pack)
            self._refresh_card_list()
            self.tab_list.setCurrentRow(self.current_index)
        finally:
            self._busy = False
        self._apply_editor_data(self.tabs[self.current_index]["data"])
        if needs_state_write:
            self._request_write_state()
        _assign_card_uids(self)  # 卡片内部编号（language_switch 按它认卡）

    def _refresh_card_list(self):
        self.tab_list.setUpdatesEnabled(False)
        try:
            self.tab_list.clear()
            for index, tab in enumerate(self.tabs):
                self._add_list_item(index, tab)
        finally:
            self.tab_list.setUpdatesEnabled(True)

    def _add_pack_item(self, index, pack):
        title = str(pack.get("title") or f"卡包{index + 1}")
        item = QListWidgetItem(title)
        item.setToolTip(title)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.pack_list.addItem(item)

    def _show_pack_context_menu(self, position):
        item = self.pack_list.itemAt(position)
        menu = QMenu(self.pack_list)
        if item is None:
            new_action = menu.addAction("新建")
            advanced_action = menu.addAction("高级搜索")
            chosen = menu.exec_(self.pack_list.mapToGlobal(position))
            if chosen == new_action:
                self.new_pack()
            elif chosen == advanced_action:
                self.open_pack_advanced_search()
            return

        row = self.pack_list.row(item)
        self.pack_list.setCurrentRow(row)
        rename_action = menu.addAction("重命名")
        copy_action = menu.addAction("复制")
        delete_action = menu.addAction("删除")
        chosen = menu.exec_(self.pack_list.mapToGlobal(position))
        if chosen == rename_action:
            self.pack_list.editItem(item)
        elif chosen == copy_action:
            self.copy_pack()
        elif chosen == delete_action:
            self.delete_pack()

    def _show_card_context_menu(self, position):
        item = self.tab_list.itemAt(position)
        menu = QMenu(self.tab_list)
        if item is None:
            new_action = menu.addAction("新建")
            advanced_action = menu.addAction("高级搜索")
            chosen = menu.exec_(self.tab_list.mapToGlobal(position))
            if chosen == new_action:
                self.new_tab()
            elif chosen == advanced_action:
                self.open_card_advanced_search()
            return

        row = self.tab_list.row(item)
        self.tab_list.setCurrentRow(row)
        copy_action = menu.addAction("复制")
        delete_action = menu.addAction("删除")
        chosen = menu.exec_(self.tab_list.mapToGlobal(position))
        if chosen == copy_action:
            self.copy_tab()
        elif chosen == delete_action:
            self.delete_tab()

    def _on_pack_item_changed(self, item):
        if self._busy:
            return
        row = self.pack_list.row(item)
        if not (0 <= row < len(self.packs)):
            return
        title = item.text().strip() or f"卡包{row + 1}"
        self._busy = True
        try:
            item.setText(title)
            item.setToolTip(title)
        finally:
            self._busy = False
        self.packs[row]["title"] = title
        self._request_write_state()

    def _sync_current_pack(self):
        if not (0 <= self.current_pack_index < len(self.packs)):
            return
        pack = self.packs[self.current_pack_index]
        pack["tabs"] = self.tabs
        pack["current_index"] = max(0, self.current_index)

    def _on_pack_changed(self, row):
        if self._busy or row < 0 or row == self.current_pack_index:
            return
        self._apply_token += 1
        token = self._apply_token
        self._save_current_snapshot(full=False)
        self._sync_current_pack()

        self.current_pack_index = row
        pack = self.packs[row]
        self.tabs = pack["tabs"]
        self.current_index = max(0, min(pack.get("current_index", 0), len(self.tabs) - 1))
        self._busy = True
        try:
            self._refresh_card_list()
            self.tab_list.setCurrentRow(self.current_index)
        finally:
            self._busy = False
        self._request_write_state(_NAVIGATION_WRITE_DELAY_MS)
        self._apply_tab_if_current(self.current_index, token)

    def _add_list_item(self, index, tab):
        title = tab.get("title") or _tab_title_from_data(tab.get("data"), f"卡片{index + 1}")
        item = QListWidgetItem(title)
        item.setToolTip(title)
        self.tab_list.addItem(item)

    def _read_state(self):
        last_error = None
        self._loaded_state_needs_write = False
        for path, label in (
            (_card_tabs_state_path(), "主状态"),
            (_card_tabs_backup_path(), "备份状态"),
        ):
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as state_file:
                    state = json.load(state_file)
                if _state_is_usable(state):
                    needs_upgrade = (
                        state.get("text_adjust_defaults_version", 0)
                        < _TEXT_ADJUST_DEFAULTS_VERSION
                    )
                    if label == "备份状态":
                        _tab_log("主标签页数据不可用，已从备份恢复。")
                    state = _upgrade_state_defaults(state)
                    migrated = _externalize_state_images(state)
                    self._loaded_state_needs_write = bool(
                        label == "备份状态" or needs_upgrade or migrated
                    )
                    if migrated:
                        _tab_log(f"已将 {migrated} 张标签页卡图迁移到按需资源目录。")
                    return state
            except Exception:
                last_error = traceback.format_exc()
        if last_error:
            _tab_log("读取标签页数据失败:\n" + last_error)
        return None

    def _state_snapshot(self):
        _assign_card_uids(self)  # 新建、搜索加入等途径来的卡在写盘前补上内部编号
        self._sync_current_pack()
        packs = []
        for pack in self.packs:
            saved = copy.deepcopy({key: value for key, value in pack.items() if key != "tabs"})
            saved["tabs"] = []
            for tab in pack.get("tabs", []):
                card = copy.deepcopy({key: value for key, value in tab.items() if key != "diy"})
                if "diy" in tab:
                    card["diy"] = copy.deepcopy({key: value for key, value in tab["diy"].items() if key != "ai"})
                    if "ai" in tab["diy"]:
                        # 旧聊天仅供迁移，当前版本不再修改；大段只读原文可以共享。
                        card["diy"]["ai"] = tab["diy"]["ai"]
                saved["tabs"].append(card)
            packs.append(saved)
        return {
            "version": 3,
            "text_adjust_defaults_version": _TEXT_ADJUST_DEFAULTS_VERSION,
            "current_pack_index": max(0, self.current_pack_index),
            "packs": packs,
        }

    def _state_json(self):
        """诊断/显式导出入口；自动保存只采集快照，后台序列化。"""
        state = self._state_snapshot()
        _externalize_state_images(state)
        return json.dumps(state, ensure_ascii=False, separators=(",", ":"))

    def _write_state_data(self, payload):
        try:
            path = _card_tabs_state_path()
            backup_path = _card_tabs_backup_path()
            temp_path = path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as state_file:
                if isinstance(payload, str):
                    state_file.write(payload)
                else:
                    json.dump(payload, state_file, ensure_ascii=False, separators=(",", ":"))
            if os.path.exists(path):
                _rotate_state_history(path)
                try:
                    os.replace(path, backup_path)
                except OSError:
                    pass
            os.replace(temp_path, path)
        except Exception:
            _tab_log("写入标签页数据失败:\n" + traceback.format_exc())

    def _write_state(self):
        self._queue_state_write(self._state_write_generation)
        writer = getattr(self, "_state_writer_thread", None)
        if writer is not None:
            writer.join()

    def _write_state_in_background(self):
        while True:
            with self._state_write_lock:
                payload = self._state_write_pending
                self._state_write_pending = None
                if payload is None:
                    self._state_writer_running = False
                    return
            with self._state_file_lock:
                _externalize_state_images(payload)
                self._write_state_data(payload)

    def _queue_state_write(self, generation):
        if generation != self._state_write_generation:
            return
        payload = self._state_snapshot()
        with self._state_write_lock:
            self._state_write_pending = payload
            if self._state_writer_running:
                return
            self._state_writer_running = True
        self._state_writer_thread = threading.Thread(target=self._write_state_in_background, daemon=True)
        self._state_writer_thread.start()

    def _request_write_state(self, delay=800):
        # 无人值守运行（回归测试等）不写状态文件：
        # 既避免测试动到用户数据，也避免后台写线程与解释器退出竞态导致段错误。
        # 连续编辑只提交最后一次；后台只使用独立快照，不读取活动 Qt 编辑器。
        if os.environ.get("YGODIY_NO_STATE_WRITE"):
            return
        self._state_write_generation += 1
        generation = self._state_write_generation
        QTimer.singleShot(
            delay,
            lambda generation=generation: self._queue_state_write(generation),
        )

    def _editor_module(self):
        return sys.modules.get(self.editor.__class__.__module__)

    def _current_tab(self):
        if 0 <= self.current_index < len(self.tabs):
            return self.tabs[self.current_index]
        return None

    def _capture_editor_visuals(self):
        visuals = {}
        card_img = getattr(self.editor, "card_img", None)
        if card_img is not None:
            visuals["card_img"] = card_img
        card_img_item = getattr(self.editor, "card_img_item", None)
        if card_img_item is not None:
            try:
                visuals["card_pixmap"] = card_img_item.pixmap()
                visuals["card_pos"] = card_img_item.pos()
            except Exception:
                pass
        return visuals

    def _cache_current_visuals(self):
        tab = self._current_tab()
        if tab is None:
            return
        visuals = self._capture_editor_visuals()
        if "card_img" in visuals:
            _bounded_cache_put(
                self._image_cache,
                id(tab),
                visuals["card_img"],
                _IMAGE_CACHE_LIMIT,
            )
        if "card_pixmap" in visuals:
            _bounded_cache_put(
                self._render_cache,
                id(tab),
                (visuals["card_pixmap"], visuals.get("card_pos")),
                _RENDER_CACHE_LIMIT,
            )

    def _copy_visual_cache(self, source, target):
        source_id = id(source)
        target_id = id(target)
        if source_id in self._image_cache:
            _bounded_cache_put(
                self._image_cache,
                target_id,
                _bounded_cache_get(self._image_cache, source_id),
                _IMAGE_CACHE_LIMIT,
            )
        if source_id in self._render_cache:
            _bounded_cache_put(
                self._render_cache,
                target_id,
                _bounded_cache_get(self._render_cache, source_id),
                _RENDER_CACHE_LIMIT,
            )

    def _set_default_visual_cache(self, tab):
        if "card_img" in self._default_visuals:
            _bounded_cache_put(
                self._image_cache,
                id(tab),
                self._default_visuals["card_img"],
                _IMAGE_CACHE_LIMIT,
            )
        if "card_pixmap" in self._default_visuals:
            _bounded_cache_put(
                self._render_cache,
                id(tab),
                (
                    self._default_visuals["card_pixmap"],
                    self._default_visuals.get("card_pos"),
                ),
                _RENDER_CACHE_LIMIT,
            )

    def _restore_cached_visuals(self, tab):
        tab_id = id(tab)
        card_img = _bounded_cache_get(self._image_cache, tab_id)
        if card_img is not None:
            self.editor.card_img = card_img
        rendered = _bounded_cache_get(self._render_cache, tab_id)
        if rendered:
            pixmap, pos = rendered
            try:
                self.editor.card_img_item.setPixmap(pixmap)
                if pos is not None:
                    self.editor.card_img_item.setPos(pos)
            except Exception:
                pass

    def _editor_is_blue_eyes_default(self):
        card_name = self._line_text("card_name_edit", "")
        card_pass = self._line_text("card_pass_edit", "")
        return card_name == "青眼白龙" or card_pass == "89631139"

    def _prime_tab_image_cache(self, tab):
        if not isinstance(tab, dict):
            return False
        if id(tab) in self._image_cache:
            return not bool(getattr(self._image_cache[id(tab)], "_card_tab_placeholder", False))
        data = tab.get("data") or {}
        image = _load_referenced_image(data)
        target_image_found = image is not None
        if image is None:
            card_id = data.get("_search_card_id")
            image_path = _local_image_path(card_id) if card_id else None
            if image_path:
                try:
                    with Image.open(image_path) as source:
                        image = source.convert("RGBA")
                        image.load()
                        target_image_found = True
                except Exception:
                    image = None
            elif card_id:
                image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
                image._card_tab_placeholder = True
        if image is not None:
            _bounded_cache_put(
                self._image_cache,
                id(tab),
                image,
                _IMAGE_CACHE_LIMIT,
            )
        return target_image_found

    def _prepare_current_image_for_mode_switch(self):
        tab = self._current_tab()
        if tab is None or self._image_dirty:
            return False
        self._prime_tab_image_cache(tab)
        image = _bounded_cache_get(self._image_cache, id(tab))
        if image is None or getattr(image, "_card_tab_placeholder", False):
            return False
        self.editor.card_img = image
        self.editor._rd_image_cache_token = (
            (tab.get("data") or {}).get(_CARD_TAB_IMAGE_REF_KEY)
            or (tab.get("data") or {}).get("_search_card_id")
            or id(tab)
        )
        self._restore_cached_visuals(tab)
        return True

    def _prewarm_tabs(self):
        tabs = []
        seen = set()

        def add_tabs(pack):
            if not isinstance(pack, dict):
                return
            for tab in pack.get("tabs", []):
                tab_id = id(tab)
                if tab_id in seen:
                    continue
                seen.add(tab_id)
                tabs.append(tab)

        if 0 <= self.current_pack_index < len(self.packs):
            add_tabs(self.packs[self.current_pack_index])
        for pack in self.packs:
            add_tabs(pack)

        selected = []
        total_size = 0
        for tab in tabs:
            data = tab.get("data") or {}
            encoded = data.get("image")
            image_path = _referenced_image_path(data)
            if not encoded and not image_path:
                continue
            try:
                image_size = os.path.getsize(image_path) if image_path else len(encoded)
            except Exception:
                image_size = len(encoded) if encoded else 0
            if selected and total_size + image_size > _IMAGE_PREWARM_BYTE_BUDGET:
                break
            selected.append(tab)
            total_size += image_size
            if len(selected) >= _IMAGE_PREWARM_LIMIT:
                break
        return selected

    def _start_image_prewarm(self):
        tabs = self._prewarm_tabs()

        def prewarm():
            for tab in tabs:
                tab_id = id(tab)
                if tab_id in self._image_cache:
                    continue
                data = tab.get("data") or {}
                encoded = data.get("image")
                if not encoded and not _referenced_image_path(data):
                    continue
                try:
                    if encoded:
                        image_data = base64.b64decode(encoded)
                        image = Image.open(io.BytesIO(image_data)).convert("RGBA")
                        image.load()
                    else:
                        image = _load_referenced_image(data)
                    if image is not None:
                        _bounded_cache_put(
                            self._image_cache,
                            tab_id,
                            image,
                            _IMAGE_CACHE_LIMIT,
                        )
                except Exception:
                    continue

        threading.Thread(target=prewarm, daemon=True).start()

    def _export_editor_data(self):
        """经宿主「导出数据」得到的完整卡片数据（含卡图），补上各功能自己的字段。"""
        return self._with_feature_fields(self._export_from_editor())

    def _collect_editor_data_fast(self):
        """直接从控件读出的卡片数据（不含卡图，切卡时用），补上各功能自己的字段。"""
        return self._with_feature_fields(self._collect_from_editor())

    def _with_feature_fields(self, data):
        """补上自定义文本、RD 文字颜色 / 样式 / 超框、OCG 超框图层、自定义防伪 / 版权、漫画卡选项，
        最后把当前模式的显示设置存进 _mode_styles（基本字段始终是 OCG 的）。"""
        data = _inject_feature_state_into_data(self, data)
        data = _inject_customization_data(self, data)
        data = _manga_inject_options(self, data)
        try:
            return _store_mode_style(self, data)
        except Exception:
            _tab_log("保存模式显示设置失败:\n" + traceback.format_exc())
            return data

    def _export_from_editor(self):
        try:
            # 过一遍 JSON：与「导出数据」写进文件再读回来的结果完全相同（元组变列表等）
            data = json.loads(json.dumps(self.editor.export_card_data(), ensure_ascii=False))
            _enable_text_adjust_defaults_in_data(data)
            return _inject_effect_layout_data(self.editor, data)
        except Exception:
            _tab_log("导出当前标签页失败:\n" + traceback.format_exc())
            return None

    def _apply_editor_data(self, data):
        """把一张卡的数据套回编辑器（切卡、撤销、启动、卡包导出都走这里）。"""
        result = self._apply_editor_data_for_mode(data)
        _of_sync_after_apply(self, data)
        return result

    def _apply_editor_data_for_mode(self, data):
        """按当前模式（OCG / RD / 漫画卡）自己的那份显示设置套用（mode_styles）。"""
        mode_key = _active_style_key(self.app)
        rd_panel = (data.get(_MODE_STYLES_KEY) or {}).get(_RD_PANEL_KEY) if isinstance(data, dict) else None
        # 卡片还没有 RD 面板设置时沿用旧行为（RD 跟随 OCG），有了就各自独立
        self.app._rd_panel_independent = bool(rd_panel)
        try:
            effective = _data_for_mode(data, mode_key)
        except Exception:
            _tab_log("读取模式显示设置失败:\n" + traceback.format_exc())
            effective = data
        result = self._apply_editor_data_with_features(effective)
        if mode_key == "rd" and rd_panel:
            try:
                _apply_rd_panel_style(self.app, rd_panel)
            except Exception:
                _tab_log("恢复 RD 面板显示设置失败:\n" + traceback.format_exc())
        _rd_language_bar_sync(self.app)
        return result

    def _apply_editor_data_with_features(self, data):
        editor = getattr(self, "editor", None)
        # 自定义防伪 / 版权：先装回这张卡的自定义项；套用期间下拉的切换不处理
        _load_customization_data(editor, data)
        if editor is not None:
            setattr(editor, "_ygodiy_custom_restoring", True)
        try:
            result = self._apply_to_editor(data)
            # 自定义文本、RD 文字颜色与超框、RD 文字样式
            _ensure_free_text(editor)
            try:
                _apply_free_text_data(editor, data)
            except Exception:
                pass
            rd_widget = getattr(getattr(self, "app", None), "rd_widget", None)
            try:
                _apply_rd_text_colors(rd_widget, data)
                _apply_rd_overframe_data(rd_widget, data)
            except Exception:
                pass
            _apply_rd_style_data(getattr(getattr(self, "app", None), "rd_widget", None), data)
            # 套用时可能屏蔽了信号，水印下拉的切换没触发：这一串跑完再重查秘密水印
            try:
                if editor is not None:
                    _schedule_secret_watermark_recheck(editor)
            except Exception:
                _tab_log("secret watermark apply_editor_data recheck error:\n" + traceback.format_exc())
        finally:
            if editor is not None:
                setattr(editor, "_ygodiy_custom_restoring", False)
        _sync_customization_selection(editor)
        _manga_restore_options(self, data)
        return result

    def _apply_to_editor(self, data):
        if not isinstance(data, dict):
            return
        was_busy = self._busy
        rd_sync_was_suspended = bool(getattr(self.app, "_rd_sync_suspended", False))
        self.app._rd_sync_suspended = True
        rd_sync_completed = False
        rd_sync_timer = getattr(self.app, "_rd_frame_sync_timer", None)
        _safe_call(getattr(rd_sync_timer, "stop", None))
        tab = self._current_tab()
        if tab is not None:
            self._prime_tab_image_cache(tab)
        if tab is not None and id(tab) not in self._image_cache:
            image = _load_referenced_image(self._default_data)
            if image is not None:
                _bounded_cache_put(self._image_cache, id(tab), image, _IMAGE_CACHE_LIMIT)
        cached_image = tab is not None and id(tab) in self._image_cache
        cached_render = tab is not None and id(tab) in self._render_cache
        image_transform_called = False
        image_sentinel = "__CARD_TAB_CACHED_IMAGE__"  # 卡图用缓存的，数据里的卡图字段只占个位
        import_data = _import_data_with_image(
            data,
            self._default_data,
            image_sentinel if cached_image else None,
        )
        original_transform_normal = getattr(self.editor, "transform_normal_img", None)
        original_transform_lb = getattr(self.editor, "transform_LB_img", None)
        original_switch_base = getattr(self.editor, "switch_base_image", None)
        original_update_card_name = getattr(self.editor, "update_card_name", None)
        original_update_text = getattr(self.editor, "update_text", None)
        self_image = (
            _bounded_cache_get(self._image_cache, id(tab))
            if tab is not None
            else None
        )

        card_image = None
        if cached_image:
            card_image = self_image.copy()
            # 与缓存里的卡图像素相同：标上原图身份，卡图缩放缓存把两者当作同一张图
            card_image._ygodiy_identity = id(self_image)

        def track_transform(method):
            def wrapped_transform(*args, **kwargs):
                nonlocal image_transform_called
                image_transform_called = True
                return method(*args, **kwargs)

            return wrapped_transform

        try:
            self._busy = True
            self.editor.setUpdatesEnabled(False)
            card_name_edit = getattr(self.editor, "card_name_edit", None)
            if card_name_edit is not None:
                card_name_edit.blockSignals(True)
            view = getattr(self.app, "view", None)
            if view is not None:
                view.setUpdatesEnabled(False)
            if original_switch_base is not None:
                self.editor.switch_base_image = lambda *args, **kwargs: None
            if original_update_card_name is not None:
                self.editor.update_card_name = lambda *args, **kwargs: None
            if original_update_text is not None:
                self.editor.update_text = lambda *args, **kwargs: None
            if cached_render:
                self.editor.transform_normal_img = lambda: None
                self.editor.transform_LB_img = lambda: None
            elif cached_image:
                if original_transform_normal is not None:
                    self.editor.transform_normal_img = track_transform(original_transform_normal)
                if original_transform_lb is not None:
                    self.editor.transform_LB_img = track_transform(original_transform_lb)
            self.editor.apply_card_data(import_data, card_image)
            _set_effect_layout_state(
                self.editor,
                _effect_layout_state_from_data(data),
            )
            _sync_effect_layout_controls(self.editor)
            for timer, callback in getattr(
                self.editor,
                "_input_debounce_timers",
                (),
            ) or ():
                _safe_call(getattr(timer, "stop", None))
            if tab is not None and cached_image:
                self.editor.card_img = _bounded_cache_get(self._image_cache, id(tab))
                if cached_render:
                    self._restore_cached_visuals(tab)
                elif not image_transform_called and getattr(self.editor, "detail_extra1", "") == "灵摆":
                    self.editor.transform_LB_img()
                elif not image_transform_called:
                    self.editor.transform_normal_img()
                self._cache_current_visuals()
            elif tab is not None:
                self._cache_current_visuals()
            if original_switch_base is not None:
                self.editor.switch_base_image = original_switch_base
                original_switch_base()
            if original_update_card_name is not None:
                self.editor.update_card_name = original_update_card_name
                original_update_card_name()
            if original_update_text is not None:
                self.editor.update_text = original_update_text
                original_update_text()
            image_identity = data.get(_CARD_TAB_IMAGE_REF_KEY) or data.get("_search_card_id")
            self.editor._rd_image_cache_token = image_identity or None
            if getattr(self.app, "current_mode", None) == 1:
                _sync_rd_frame_from_otcg(self.app)
                self.app._rd_sync_pending = False
                rd_sync_completed = True
            _apply_rd_text_colors(getattr(self.app, "rd_widget", None), data)
            _apply_rd_overframe_data(getattr(self.app, "rd_widget", None), data)
        except Exception:
            _tab_log("应用标签页数据失败:\n" + traceback.format_exc())
        finally:
            if original_transform_normal is not None:
                self.editor.transform_normal_img = original_transform_normal
            if original_transform_lb is not None:
                self.editor.transform_LB_img = original_transform_lb
            if original_switch_base is not None:
                self.editor.switch_base_image = original_switch_base
            if original_update_card_name is not None:
                self.editor.update_card_name = original_update_card_name
            if original_update_text is not None:
                self.editor.update_text = original_update_text
            self.app._rd_sync_suspended = rd_sync_was_suspended
            if (
                not rd_sync_completed
                and not rd_sync_was_suspended
                and getattr(self.app, "_rd_sync_pending", False)
            ):
                _schedule_rd_frame_sync(self.app)
            self._busy = was_busy
            card_name_edit = getattr(self.editor, "card_name_edit", None)
            if card_name_edit is not None:
                card_name_edit.blockSignals(False)
            self.editor.setUpdatesEnabled(True)
            view = getattr(self.app, "view", None)
            if view is not None:
                view.setUpdatesEnabled(True)
                viewport = _safe_call(getattr(view, "viewport", None))
                if viewport is not None:
                    _safe_call(getattr(viewport, "setUpdatesEnabled", None), True)
                    _safe_call(getattr(viewport, "update", None))
                    _safe_call(getattr(viewport, "repaint", None))
                view.update()
                _schedule_preview_update_restore(self.app)
            self.editor.update()

    def _blue_eyes_minimal_data(self):
        return {
            "name": "青眼白龙",
            "card_type": 0,
            "template": 0,
            "language": 0,
            "tc_type": 0,
            "translation": 0,
            "race": 0,
            "call_way": 0,
            "extra1": 0,
            "extra2": 0,
            "level": 8,
            "rank": 0,
            "attribute": "光",
            "ATK": "3000",
            "DEF": "2500",
            "effect_text": "以高攻击力著称的传说之龙。任何对手都能粉碎，其破坏力不可估量。",
            "text_sizeable": True,
            "text_size_change": 0,
            "text_weightable": True,
            "text_weight_change": 0,
            "cardpass": "89631139",
            "cardpack": "LPST-JP003",
            "_search_card_id": "89631139",
        }

    def _combo_index(self, name, default=0):
        widget = getattr(self.editor, name, None)
        try:
            return widget.currentIndex()
        except Exception:
            return default

    def _line_text(self, name, default=""):
        widget = getattr(self.editor, name, None)
        try:
            return widget.text()
        except Exception:
            return default

    def _plain_text(self, name, default=""):
        widget = getattr(self.editor, name, None)
        try:
            return widget.toPlainText()
        except Exception:
            return default

    def _toggle_checked(self, name, default=False):
        widget = getattr(self.editor, name, None)
        if widget is None:
            return default
        if hasattr(widget, "is_checked"):
            return bool(widget.is_checked)
        try:
            return bool(widget.isChecked())
        except Exception:
            return default

    def _attr_value(self, name, default=None):
        return getattr(self.editor, name, default)

    def _color_tuple(self, value, default=(0, 0, 0)):
        try:
            return (int(value.red()), int(value.green()), int(value.blue()))
        except Exception:
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                try:
                    return (int(value[0]), int(value[1]), int(value[2]))
                except Exception:
                    pass
        return default

    def _visible(self, name, default=True):
        widget = getattr(self.editor, name, None)
        try:
            return bool(widget.isVisible())
        except Exception:
            return default

    def _gradient_to_data(self, data, attr_name, suffix):
        gradient = getattr(self.editor, attr_name, None)
        if not gradient:
            return
        try:
            data[f"gradient_process_flag{suffix}"] = [bool(v[0]) for v in gradient]
            data[f"gradient_process_pos{suffix}"] = [float(v[1]) for v in gradient]
            data[f"gradient_process_r{suffix}"] = [int(v[2]) for v in gradient]
            data[f"gradient_process_g{suffix}"] = [int(v[3]) for v in gradient]
            data[f"gradient_process_b{suffix}"] = [int(v[4]) for v in gradient]
        except Exception:
            return

    def _rd_attr(self, name, default=None):
        """读取 RD 编辑器属性（RD 与 OCG 是不同对象）。"""
        rd_widget = getattr(self.app, "rd_widget", None)
        if rd_widget is None:
            return default
        return getattr(rd_widget, name, default)

    def _collect_from_editor(self):
        if not (0 <= self.current_index < len(self.tabs)):
            return None
        previous = self.tabs[self.current_index].get("data") or {}
        data = dict(previous) if isinstance(previous, dict) else {}
        effect_layout = _effect_layout_state(self.editor)

        data.update(
            {
                "name": self._line_text("card_name_edit", data.get("name", "")),
                "card_type": self._combo_index("type_selector", data.get("card_type", 0)),
                "template": self._combo_index("template_selector", data.get("template", 0)),
                "language": self._combo_index("lan_selector", data.get("language", 0)),
                "tc_type": self._combo_index("tc_type_selector", data.get("tc_type", 0)),
                "translation": self._combo_index("trans_selector", data.get("translation", 0)),
                "mt_type": self._combo_index("MT_type_selector", data.get("mt_type", 0)),
                "color_flag": bool(self._attr_value("color_flag", data.get("color_flag", False))),
                "color_option": int(self._attr_value("color_option", data.get("color_option", 0))),
                "title_color": self._color_tuple(self._attr_value("title_color", data.get("title_color", (0, 0, 0)))),
                "text_color_flag": bool(self._rd_attr("text_color_flag", data.get("text_color_flag", False))),
                "text_color": str(self._rd_attr("text_color", data.get("text_color", "#000000")) or "#000000"),
                "detail_color_flag": bool(self._rd_attr("detail_color_flag", data.get("detail_color_flag", False))),
                "detail_color": str(self._rd_attr("detail_color", data.get("detail_color", "#000000")) or "#000000"),
                "rd_overframe_layers": self._rd_attr(
                    "_rd_overframe_layers", data.get("rd_overframe_layers", [])
                ),
                "color_advanced_activated": self._toggle_checked("color_advanced_btn", data.get("color_advanced_activated", False)),
                "mix_mode_flag": bool(self._attr_value("mix_mode_flag", data.get("mix_mode_flag", False))),
                "mix_option": int(self._attr_value("mix_option", data.get("mix_option", 0))),
                "HD_img_flag": bool(self._attr_value("HD_card_img", data.get("HD_img_flag", False))),
                "race": self._combo_index("race_selector", data.get("race", 0)),
                "call_way": self._combo_index("info_selector_left", data.get("call_way", 0)),
                "extra1": self._combo_index("info_selector_mid", data.get("extra1", 0)),
                "extra2": self._combo_index("info_selector_right", data.get("extra2", 0)),
                "level": int(self._attr_value("current_level", data.get("level", 0)) or 0),
                "rank": int(self._attr_value("current_rank", data.get("rank", 0)) or 0),
                "attribute": self._attr_value("current_attribute", data.get("attribute", "光")),
                "ATK": self._line_text("ATK_edit", data.get("ATK", "")),
                "DEF": self._line_text("DEF_edit", data.get("DEF", "")),
                "cn_atk_def_flag": bool(self._attr_value("cn_ATK_DEF_flag", data.get("cn_atk_def_flag", False))),
                "link_status": list(self._attr_value("arrow_status_list", data.get("link_status", [False] * 8))),
                "effect_text": self._plain_text("text_input", data.get("effect_text", "")),
                "lb_text": self._plain_text("LB_text_edit", data.get("lb_text", "")),
                "lb_level": self._line_text("LB_level_edit", data.get("lb_level", "")),
                "text_sizeable": bool(self._attr_value("text_sizeable", data.get("text_sizeable", True))),
                "text_size_change": self._slider_value("text_size_slider", data.get("text_size_change", 0)),
                "text_weightable": bool(self._attr_value("text_weightable", data.get("text_weightable", True))),
                "text_weight_change": self._slider_value("text_weight_slider", data.get("text_weight_change", 0)),
                "effect_first_line_compress": effect_layout["first_line_compress"],
                "effect_h_align": effect_layout["h_align"],
                "effect_v_align": effect_layout["v_align"],
                "effect_line_height_mode": effect_layout["line_height_mode"],
                "effect_line_height": effect_layout["line_height"],
                "effect_letter_spacing": effect_layout["letter_spacing"],
                "cardpass": self._line_text("card_pass_edit", data.get("cardpass", "")),
                "cardpack": self._line_text("card_pack_edit", data.get("cardpack", "")),
                "holo": self._combo_index("holo_selector", data.get("holo", 0)),
                "copyright": self._combo_index("copyright_selector", data.get("copyright", 0)),
                "rare": self._combo_index("rare_selector", data.get("rare", 0)),
                "watermark": self._combo_index("water_selector", data.get("watermark", 0)),
                "cardpass_vis": self._visible("card_pass_item", data.get("cardpass_vis", True)),
                "cardpack_vis": self._visible("card_pack_item", data.get("cardpack_vis", True)),
                "holo_vis": self._visible("holo_item", data.get("holo_vis", True)),
                "copyright_vis": self._visible("copyright_item", data.get("copyright_vis", True)),
                "local_source_flag": self._toggle_checked("source_toggle", data.get("local_source_flag", False)),
                "local_source_folder": self._attr_value("local_image_folder", data.get("local_source_folder", "")),
                "round_corner": self._toggle_checked("toggle_corner", data.get("round_corner", False)),
                "output_format": self._attr_value("output_format", data.get("output_format", "PNG")),
                "output_name": self._attr_value("output_name", data.get("output_name", 0)),
                "detail_custom_toggle": self._toggle_checked("detail_custom_toggle", data.get("detail_custom_toggle", False)),
                "detail_custom_text": self._line_text("detail_custom_edit", data.get("detail_custom_text", "")),
                "attr_hide": self._toggle_checked("attr_hide_toggle", data.get("attr_hide", False)),
                "full_effect": self._toggle_checked("full_effect_toggle", data.get("full_effect", False)),
                "LB_ratio": self._combo_index("LB_ratio_selector", data.get("LB_ratio", 0)),
                "LB_Zack": self._toggle_checked("LB_Zack_toggle", data.get("LB_Zack", False)),
                "name_align": self._combo_index("name_align_selector", data.get("name_align", 0)),
                "text_align": self._combo_index("text_align_selector", data.get("text_align", 0)),
            }
        )

        for name in (
            "outline_enabled",
            "outline_enabled_c",
            "outline_thickess",
            "outline_thickess_c",
            "shadow_flag",
            "shadow_flag_c",
            "shadow_blur_size",
            "shadow_blur_size_c",
            "shadow_x_offset",
            "shadow_x_offset_c",
            "shadow_y_offset",
            "shadow_y_offset_c",
            "gradient_flag",
            "gradient_flag_c",
        ):
            if hasattr(self.editor, name):
                data[name] = self._attr_value(name, data.get(name))
        for name in ("outline_color", "outline_color_c", "shadow_color", "shadow_color_c", "single_color", "single_color_c"):
            if hasattr(self.editor, name):
                data[name] = self._color_tuple(self._attr_value(name), data.get(name, (0, 0, 0)))
        self._gradient_to_data(data, "gradient_process", "")
        self._gradient_to_data(data, "gradient_process_c", "_c")

        if hasattr(self.editor, "overframe_toggle"):
            data["overframe"] = self._toggle_checked("overframe_toggle", data.get("overframe", False))
            for name in ("overframe_scale", "overframe_sizex", "overframe_sizey", "overframe_posx", "overframe_posy"):
                if hasattr(self.editor, name):
                    data[name] = self._attr_value(name, data.get(name))

        _enable_text_adjust_defaults_in_data(data)
        return data

    def _slider_value(self, name, default=0):
        widget = getattr(self.editor, name, None)
        try:
            return widget.value()
        except Exception:
            return default

    def _save_current_snapshot(self, full=True):
        if self._busy or not (0 <= self.current_index < len(self.tabs)):
            return
        self._cache_current_visuals()
        if full or self._image_dirty:
            data = self._export_editor_data()
            _externalize_image_data(data)
            self._image_dirty = False if data else self._image_dirty
        else:
            data = self._collect_editor_data_fast()
        if not data:
            return
        title = _tab_title_from_data(data, f"卡片{self.current_index + 1}")
        tab = self.tabs[self.current_index]
        tab["title"] = title
        tab["data"] = data
        item = self.tab_list.item(self.current_index)
        if item is not None:
            item.setText(title)
            item.setToolTip(title)

    def _current_export_settings(self):
        output_format = str(self._attr_value("output_format", "PNG") or "PNG").upper()
        if output_format == "JPG":
            output_format = "JPG"
        else:
            output_format = "PNG"
        try:
            output_name = int(self._attr_value("output_name", 0) or 0)
        except Exception:
            output_name = 0
        return {
            "format": output_format,
            "name": output_name,
            "hd": bool(self._attr_value("HD_card_img", False)),
        }

    def _apply_export_settings(self, settings):
        try:
            self.editor.output_format = settings["format"]
            self.editor.output_name = settings["name"]
            self.editor.HD_card_img = settings["hd"]
        except Exception:
            pass

    def _pack_export_base_name(self, tab, index, output_name):
        data = tab.get("data") or {}
        module = self._editor_module()
        if output_name == 0:
            raw_name = (
                self._line_text("card_name_edit", "")
                or data.get("name")
                or tab.get("title")
                or f"卡片{index + 1}"
            )
            cleaner = getattr(module, "clean_filename", None) if module is not None else None
            if cleaner is not None:
                try:
                    raw_name = cleaner(raw_name)
                except Exception:
                    pass
            return _safe_path_component(raw_name, f"卡片{index + 1}")

        raw_pass = (
            self._line_text("card_pass_edit", "")
            or data.get("cardpass")
            or f"卡片{index + 1}"
        )
        remover = getattr(module, "remove_leading_zeros", None) if module is not None else None
        if remover is not None:
            try:
                raw_pass = remover(raw_pass)
            except Exception:
                pass
        return _safe_path_component(raw_pass, f"卡片{index + 1}")

    def _load_search_card_for_export(self, data):
        if not isinstance(data, dict) or _data_has_saved_image(data):
            return
        card_id = data.get("_search_card_id")
        if not card_id:
            return
        try:
            card_pass_edit = getattr(self.editor, "card_pass_edit", None)
            if card_pass_edit is not None:
                if hasattr(card_pass_edit, "has_user_type"):
                    card_pass_edit.has_user_type = True
                card_pass_edit.setText(str(card_id))
            fetch_info = getattr(self.editor, "fetch_info", None)
            after_info_fetch = getattr(self.editor, "after_info_fetch", None)
            if fetch_info is not None and after_info_fetch is not None:
                fetch_info()
                if getattr(getattr(self.editor, "info_fetcher", None), "valid", False):
                    after_info_fetch()
            elif hasattr(self.editor, "on_cardpass_return"):
                self.editor.on_cardpass_return()
        except Exception:
            _tab_log("导出前加载搜索卡片失败:\n" + traceback.format_exc())

    def export_current_pack(self):
        if not (0 <= self.current_pack_index < len(self.packs)):
            return
        self._save_current_snapshot(full=False)
        self._sync_current_pack()
        pack = self.packs[self.current_pack_index]
        tabs = [
            tab
            for tab in pack.get("tabs", [])
            if isinstance(tab, dict) and isinstance(tab.get("data"), dict)
        ]
        if not tabs:
            try:
                QMessageBox.warning(self.app, "卡包导出", "当前卡包没有可导出的卡片。")
            except Exception:
                pass
            return

        parent_dir = QFileDialog.getExistingDirectory(self.app, "选择卡包导出路径")
        if not parent_dir:
            return

        pack_title = str(pack.get("title") or f"卡包{self.current_pack_index + 1}")
        target_dir = os.path.join(
            parent_dir,
            _safe_path_component(pack_title, f"卡包{self.current_pack_index + 1}"),
        )
        try:
            os.makedirs(target_dir, exist_ok=True)
        except Exception:
            _tab_log("创建卡包导出目录失败:\n" + traceback.format_exc())
            try:
                QMessageBox.warning(self.app, "卡包导出", "创建卡包导出目录失败。")
            except Exception:
                pass
            return

        original_index = self.current_index
        original_settings = self._current_export_settings()
        original_busy = self._busy
        exported = 0
        failures = []
        name_counts = {}
        extension = ".jpg" if original_settings["format"] == "JPG" else ".png"

        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        except Exception:
            pass

        self._busy = True
        try:
            for index, tab in enumerate(tabs):
                try:
                    self.current_index = index
                    self._apply_editor_data(tab["data"])
                    self._load_search_card_for_export(tab["data"])
                    self._apply_export_settings(original_settings)
                    base_name = self._pack_export_base_name(
                        tab,
                        index,
                        original_settings["name"],
                    )
                    file_name = _dedup_export_base(base_name, name_counts) + extension
                    self.editor.save_image(os.path.join(target_dir, file_name))
                    exported += 1
                    QApplication.processEvents()
                except Exception:
                    failures.append(tab.get("title") or f"卡片{index + 1}")
                    _tab_log("导出卡包卡片失败:\n" + traceback.format_exc())
        finally:
            if 0 <= original_index < len(self.tabs):
                self.current_index = original_index
                try:
                    self._apply_editor_data(self.tabs[original_index]["data"])
                    self._apply_export_settings(original_settings)
                except Exception:
                    _tab_log("恢复卡包导出前的卡片失败:\n" + traceback.format_exc())
                try:
                    self.tab_list.setCurrentRow(original_index)
                except Exception:
                    pass
            self._busy = original_busy
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

        if failures:
            try:
                QMessageBox.warning(
                    self.app,
                    "卡包导出",
                    f"已导出 {exported} 张卡片，失败 {len(failures)} 张。详情见制卡器标签页.log。",
                )
            except Exception:
                pass
            return
        try:
            QMessageBox.information(
                self.app,
                "卡包导出",
                f"已导出 {exported} 张卡片到：\n{target_dir}",
            )
        except Exception:
            pass

    def _on_row_changed(self, row):
        if self._busy or row < 0 or row == self.current_index:
            return
        self._apply_token += 1
        token = self._apply_token
        self._save_current_snapshot(full=False)
        self.current_index = row
        self._sync_current_pack()
        self._request_write_state(_NAVIGATION_WRITE_DELAY_MS)
        self._apply_tab_if_current(row, token)

    def _on_card_name_changed(self, text):
        if self._busy or not (0 <= self.current_index < len(self.tabs)):
            return
        title = (text or "").strip() or f"卡片{self.current_index + 1}"
        title = title[:14] + ("..." if len(title) > 14 else "")
        self.tabs[self.current_index]["title"] = title
        item = self.tab_list.item(self.current_index)
        if item is not None:
            item.setText(title)
            item.setToolTip(title)

    def _select_pack(self, row, apply_data=True):
        if not (0 <= row < len(self.packs)):
            return
        self._apply_token += 1
        token = self._apply_token
        self.current_pack_index = row
        pack = self.packs[row]
        self.tabs = pack["tabs"]
        self.current_index = max(0, min(pack.get("current_index", 0), len(self.tabs) - 1))
        self._busy = True
        try:
            self.pack_list.setCurrentRow(row)
            self._refresh_card_list()
            self.tab_list.setCurrentRow(self.current_index)
        finally:
            self._busy = False
        self._sync_current_pack()
        self._request_write_state(_NAVIGATION_WRITE_DELAY_MS)
        if apply_data:
            self._apply_tab_if_current(self.current_index, token)

    def _selector_index_for_text(self, selector_name, text, default=0):
        selector = getattr(self.editor, selector_name, None)
        if selector is None or not text:
            return default
        try:
            index = selector.findText(text)
            return index if index >= 0 else default
        except Exception:
            return default

    def _search_tab_from_card(self, card):
        card_id = str(card.get("id") or "").zfill(8)
        text = card.get("text") or {}
        raw_data = card.get("data") or {}
        type_text = text.get("types") or ""
        first_line = type_text.splitlines()[0] if type_text else ""
        left = first_line.find("[")
        right = first_line.find("]")
        details = first_line[left + 1 : right].split("|") if left >= 0 and right > left else []
        main_type = details[0] if details else "怪兽"
        card_type = main_type + "卡"
        call_way = ""
        extra = []
        mt_type = "通常"
        if card_type in ("魔法卡", "陷阱卡"):
            mt_type = details[1] if len(details) > 1 else "通常"
        else:
            for detail in details[1:]:
                if detail == "效果":
                    continue
                if detail in _MAIN_TYPES:
                    call_way = detail
                else:
                    extra.append(detail)
            if not call_way:
                call_way = "效果"
            if "效果" in details and "通常" in details:
                extra.append("通常")

        raw_level = raw_data.get("level")
        raw_level = raw_level if isinstance(raw_level, int) else 0
        level = raw_level & 255
        defense = raw_data.get("def")
        is_link = call_way == "连接"
        data = self._blue_eyes_minimal_data()
        data.update(
            {
                "name": _card_display_name(card).replace("·", "・"),
                "card_type": self._selector_index_for_text("type_selector", card_type, 0),
                "race": self._selector_index_for_text(
                    "race_selector", _RACES.get(raw_data.get("race"), ""), 0
                ),
                "call_way": self._selector_index_for_text("info_selector_left", call_way, 0),
                "extra1": self._selector_index_for_text(
                    "info_selector_mid", extra[0] if extra else "", 0
                ),
                "extra2": self._selector_index_for_text(
                    "info_selector_right", extra[1] if len(extra) > 1 else "", 0
                ),
                "mt_type": self._selector_index_for_text("MT_type_selector", mt_type, 0),
                "level": level,
                "rank": level,
                "attribute": _ATTRIBUTES.get(raw_data.get("attribute"), ""),
                "ATK": str(raw_data.get("atk")) if isinstance(raw_data.get("atk"), int) and raw_data.get("atk") >= 0 else "?",
                "DEF": "-" if is_link else (
                    str(defense) if isinstance(defense, int) and defense >= 0 else "?"
                ),
                "link_status": [
                    bool((defense if isinstance(defense, int) else 0) & marker)
                    for marker in _LINK_MARKERS
                ],
                "effect_text": text.get("desc") or "",
                "lb_text": text.get("pdesc") or "",
                "lb_level": str((raw_level >> 24) & 255) if "灵摆" in extra else "",
                "cardpass": card_id,
                "cardpack": _pack_for(card_id),
                "_search_card_id": card_id,
            }
        )
        _enable_text_adjust_defaults_in_data(data)
        return {"title": _tab_title_from_data(data, card_id), "data": data}

    def open_pack_advanced_search(self):
        _open_manager_advanced_search(self, "pack")

    def open_card_advanced_search(self):
        _open_manager_advanced_search(self, "card")

    def create_pack_from_search(self, filters):
        cards = _search_cards(filters)
        if not cards:
            return
        self._save_current_snapshot(full=False)
        self._sync_current_pack()
        pack = {
            "title": _advanced_search_title(filters),
            "current_index": 0,
            "tabs": [self._search_tab_from_card(card) for card in cards],
        }
        self.packs.append(pack)
        self._add_pack_item(len(self.packs) - 1, pack)
        self._select_pack(len(self.packs) - 1)

    def add_card_tab(self, card_pass):
        card = _card_for(card_pass)
        if card is None:
            return
        self._save_current_snapshot(full=False)
        tab = self._search_tab_from_card(card)
        self.tabs.append(tab)
        self._add_list_item(len(self.tabs) - 1, tab)
        row = len(self.tabs) - 1
        self._apply_token += 1
        token = self._apply_token
        self._busy = True
        try:
            self.tab_list.setCurrentRow(row)
        finally:
            self._busy = False
        self.current_index = row
        self._sync_current_pack()
        self._request_write_state()
        self._apply_tab_if_current(row, token)

    def new_pack(self):
        self._save_current_snapshot(full=False)
        self._sync_current_pack()
        pack = self._new_default_pack(f"卡包{len(self.packs) + 1}")
        self.packs.append(pack)
        self._set_default_visual_cache(pack["tabs"][0])
        self._add_pack_item(len(self.packs) - 1, pack)
        self._select_pack(len(self.packs) - 1)

    def copy_pack(self):
        before = {id(tab) for tab in _all_tabs(self)}
        self._duplicate_pack()
        _renew_copied_pack_uids(self, before)

    def _duplicate_pack(self):
        self._save_current_snapshot(full=False)
        self._sync_current_pack()
        source_index = self.current_pack_index
        if not (0 <= source_index < len(self.packs)):
            return
        source = self.packs[source_index]
        cloned = _json_clone(source)
        title = (str(source.get("title") or f"卡包{source_index + 1}") + " 副本").strip()
        cloned["title"] = title
        for source_tab, cloned_tab in zip(source.get("tabs", []), cloned.get("tabs", [])):
            self._copy_visual_cache(source_tab, cloned_tab)
        row = source_index + 1
        self.packs.insert(row, cloned)
        item = QListWidgetItem(title)
        item.setToolTip(title)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        self.pack_list.insertItem(row, item)
        self._select_pack(row, apply_data=False)

    def delete_pack(self):
        row = self.pack_list.currentRow()
        if not (0 <= row < len(self.packs)):
            return
        self._save_current_snapshot(full=False)
        removed = self.packs.pop(row)
        for tab in removed.get("tabs", []):
            self._image_cache.pop(id(tab), None)
            self._render_cache.pop(id(tab), None)
        self._busy = True
        try:
            self.pack_list.takeItem(row)
        finally:
            self._busy = False
        if not self.packs:
            pack = self._new_default_pack()
            self.packs.append(pack)
            self._set_default_visual_cache(pack["tabs"][0])
            self._add_pack_item(0, pack)
        self._select_pack(min(row, len(self.packs) - 1))

    def new_tab(self):
        self._save_current_snapshot(full=False)
        tab = {"title": "青眼白龙", "data": _json_clone(self._default_data)}
        self.tabs.append(tab)
        self._set_default_visual_cache(tab)
        self._add_list_item(len(self.tabs) - 1, tab)
        row = len(self.tabs) - 1
        self._apply_token += 1
        token = self._apply_token
        self._busy = True
        try:
            self.tab_list.setCurrentRow(row)
        finally:
            self._busy = False
        self.current_index = row
        self._sync_current_pack()
        self._request_write_state()
        self._apply_tab_if_current(row, token)

    def copy_tab(self):
        before = {id(tab) for tab in _all_tabs(self)}
        source = self.tabs[self.current_index] if 0 <= self.current_index < len(self.tabs) else None
        self._duplicate_tab()
        _renew_copied_tab_uids(self, before, source)

    def _duplicate_tab(self):
        self._save_current_snapshot(full=False)
        source_index = self.current_index if self.current_index >= 0 else self.tab_list.currentRow()
        if not (0 <= source_index < len(self.tabs)):
            return
        source_was_current = source_index == self.current_index
        source = self.tabs[source_index]
        title = (source.get("title") or f"卡片{source_index + 1}") + " 副本"
        title = title[:14] + ("..." if len(title) > 14 else "")
        tab = {"title": title, "data": _json_clone(source.get("data") or self._default_data)}
        if isinstance(source.get("diy"), dict):
            tab["diy"] = _json_clone(source["diy"])  # DIY 工作台的效果与字段随卡复制
        self.tabs.insert(source_index + 1, tab)
        self._copy_visual_cache(source, tab)
        item = QListWidgetItem(title)
        item.setToolTip(title)
        self.tab_list.insertItem(source_index + 1, item)
        row = source_index + 1
        self._apply_token += 1
        token = self._apply_token
        self._busy = True
        try:
            self.tab_list.setCurrentRow(row)
        finally:
            self._busy = False
        self.current_index = row
        self._sync_current_pack()
        self._request_write_state()
        if not source_was_current:
            self._apply_tab_if_current(row, token)

    def delete_tab(self):
        row = self.tab_list.currentRow()
        if not (0 <= row < len(self.tabs)):
            return
        removed_pack = False
        target = -1
        self._busy = True
        try:
            removed = self.tabs.pop(row)
            self._image_cache.pop(id(removed), None)
            self._render_cache.pop(id(removed), None)
            self.tab_list.takeItem(row)
            if not self.tabs:
                removed_pack = True
                pack_row = self.current_pack_index
                if 0 <= pack_row < len(self.packs):
                    self.packs.pop(pack_row)
                    self.pack_list.takeItem(pack_row)
                    if not self.packs:
                        pack = self._new_default_pack()
                        self.packs.append(pack)
                        self._set_default_visual_cache(pack["tabs"][0])
                        self._add_pack_item(0, pack)
                    target = min(pack_row, len(self.packs) - 1)
            else:
                target = min(row, len(self.tabs) - 1)
        finally:
            self._busy = False
        if removed_pack:
            self.current_pack_index = -1
            self._select_pack(target)
            return
        self._apply_token += 1
        token = self._apply_token
        self._busy = True
        try:
            self.tab_list.setCurrentRow(target)
        finally:
            self._busy = False
        self.current_index = target
        self._sync_current_pack()
        self._request_write_state()
        self._apply_tab_if_current(target, token)

    def _apply_tab_if_current(self, row, token):
        if token != self._apply_token or row != self.current_index:
            return
        if not (0 <= row < len(self.tabs)):
            return
        tab = self.tabs[row]
        target_image_ready = self._prime_tab_image_cache(tab)
        data = tab["data"]
        self._apply_editor_data(data)
        assistant = getattr(self.app, "_ai_dock", None)
        if assistant is not None:
            assistant.editor_applied(tab)
        card_id = data.get("_search_card_id") if isinstance(data, dict) else None
        if card_id and not target_image_ready:
            QTimer.singleShot(
                20,
                lambda row=row, token=token, card_id=card_id: self._load_search_card_if_current(
                    row, token, card_id
                ),
            )

    def _load_search_card_if_current(self, row, token, card_id):
        if token == self._apply_token and row == self.current_index and 0 <= row < len(self.tabs):
            tab = self.tabs[row]
            if isinstance(tab.get("data"), dict):
                # 重新查卡只为补卡图：查完把这张卡原来的内容套回去（OTCGWidget.after_info_fetch 的装饰器处理）
                self.editor._ygodiy_refetch_restore = (self, tab, token, _json_clone(tab["data"]))
        if token != self._apply_token or row != self.current_index:
            return
        try:
            if hasattr(self.editor.card_pass_edit, "has_user_type"):
                self.editor.card_pass_edit.has_user_type = True
            self.editor.card_pass_edit.setText(str(card_id))
            self.editor.on_cardpass_return()
        except Exception:
            _tab_log("加载搜索卡片失败:\n" + traceback.format_exc())

    def autosave(self):
        self._save_current_snapshot(full=False)
        self._request_write_state()

    def save_all(self):
        self._save_current_snapshot(full=True)
        self._state_write_generation += 1
        self._write_state()


def _install_card_tabs(app, editor):
    try:
        if app is None or getattr(app, "_card_tabs_installed", False):
            return
        if not hasattr(editor, "on_export_clicked") or not hasattr(editor, "on_import_clicked"):
            return
        _optimize_graphics_view(app)
        _clear = globals().get("_clear_demo_card")
        if _clear is not None:
            _clear(editor)
        app.card_tab_manager = _CardTabManager(app, editor)
        app._card_tabs_installed = True
        assistant = getattr(app, "_ai_dock", None)
        if assistant is not None:
            assistant.bind_manager()
        performance_output_path = os.environ.get("YGODIY_PERFORMANCE_DIAGNOSTIC")
        if performance_output_path:
            QTimer.singleShot(
                2500,
                lambda: _export_performance_diagnostic(
                    app,
                    editor,
                    performance_output_path,
                ),
            )
        output_path = os.environ.get("YGODIY_RD_DIAGNOSTIC")
        if output_path:
            QTimer.singleShot(2500, lambda: _export_rd_diagnostic(app, output_path))
    except Exception:
        _tab_log("安装标签页失败:\n" + traceback.format_exc())


def _schedule_card_tabs(editor):
    try:
        QTimer.singleShot(
            _CARD_TABS_INSTALL_DELAY_MS,
            lambda: _install_card_tabs(getattr(editor, "parent_app", None), editor),
        )
    except Exception:
        _tab_log("计划安装标签页失败:\n" + traceback.format_exc())


def _prev_inject_feature_state_into_data(manager, data):
    if not isinstance(data, dict):
        return data
    editor = getattr(manager, "editor", None)
    app = getattr(manager, "app", None)
    _inject_free_text_into_data(editor, data)
    rd_widget = getattr(app, "rd_widget", None)
    if rd_widget is not None:
        for flag_name, color_name, _item_names in _RD_TEXT_COLOR_TARGETS:
            if hasattr(rd_widget, flag_name):
                data[flag_name] = bool(getattr(rd_widget, flag_name, False))
            if hasattr(rd_widget, color_name):
                data[color_name] = str(getattr(rd_widget, color_name, "#000000") or "#000000")
        data["rd_overframe_layers"] = [
            dict(layer) for layer in _rd_overframe_layers(rd_widget)
        ]
    return data


def _ocg_of_previous_inject(manager, data):
    data = _prev_inject_feature_state_into_data(manager, data)
    if isinstance(data, dict):
        rd_widget = getattr(getattr(manager, "app", None), "rd_widget", None)
        if rd_widget is not None:
            _rd_style_state(rd_widget)
            for name in ("attr_style", "level_style", "AD_style"):
                data[name] = int(getattr(rd_widget, name, 0) or 0)
    return data


def _restore_after_search_refetch(original_after):
    """OTCGWidget.after_info_fetch 的装饰器：切回标签页时「按卡密重新查卡」只用来补卡图。

    查卡完成后把刚查到的卡图存进这张卡的缓存，再把这张卡原来的内容（查卡期间用户打的字也算）套回去；
    查卡回来时已经切到别的卡，就丢弃这次结果。
    """
    def after_info_fetch(self, *args, **kwargs):
        pending = self.__dict__.get("_ygodiy_refetch_restore")
        if pending:
            manager, tab, token, _saved = pending
            if not (token == manager._apply_token and manager._current_tab() is tab):
                # 查卡还没回来用户就切到了别的卡：这次结果属于上一张卡，丢弃，
                # 否则会写进现在这张卡（p09 的过期判断按卡密比较，新建的卡卡密都相同，拦不住）
                self.__dict__.pop("_ygodiy_refetch_restore", None)
                _safe_call(getattr(getattr(self, "parent_app", None), "hide_loading_gif", None))
                for name in ("name_search_btn", "card_pass_btn", "random_btn"):
                    _safe_call(getattr(getattr(self, name, None), "setEnabled", None), True)
                return None
        keep = None
        if pending:
            # 查卡期间用户可能已经在这张卡上打了字：以「查卡完成这一刻」编辑器里的内容为准
            try:
                keep = pending[0]._collect_editor_data_fast()
            except Exception:
                keep = None
            keep = keep if isinstance(keep, dict) else pending[3]
        result = original_after(self, *args, **kwargs)
        pending = self.__dict__.pop("_ygodiy_refetch_restore", None)
        if pending and keep is not None:
            manager, tab, token, _saved = pending
            try:
                if token == manager._apply_token and manager._current_tab() is tab:
                    manager._cache_current_visuals()  # 刚查到的卡图归这张卡
                    manager._apply_editor_data(keep)  # 其余内容还原成用户自己的
                    tab["data"] = keep
            except Exception:
                _tab_log("重新查卡后还原卡片内容失败:\n" + traceback.format_exc())
        return result

    after_info_fetch.__name__, after_info_fetch.__qualname__ = original_after.__name__, original_after.__qualname__
    after_info_fetch.__wrapped__ = original_after
    return after_info_fetch


def _of_sync_previous_inject(manager, data):
    """所有标签页快照（完整 / 快速 / 撤销）都写入当前的 OCG 超框图层。"""
    data = _ocg_of_previous_inject(manager, data)
    editor = getattr(getattr(manager, "app", None), "otcg_widget", None)
    if isinstance(data, dict) and editor is not None:
        _ocg_of_inject(editor, data)
    return data


def _inject_feature_state_into_data(manager, data):
    data = _of_sync_previous_inject(manager, data)
    if not isinstance(data, dict):
        return data
    try:
        app = getattr(manager, "app", None)
        active = getattr(app, "_of_last_mode", None)
        if active is None:
            active = getattr(app, "current_mode", 0) if getattr(app, "current_mode", 0) in _OF_SYNC_MODES else 0
        ocg, rd = _of_sync_editors(app)
        if ocg is not None:
            data[_OCG_OF_DATA_KEY] = [dict(layer) for layer in _ocg_of_layers(ocg)]
        if rd is not None:
            data["rd_overframe_layers"] = [dict(layer) for layer in _rd_overframe_layers(rd)]
        # 不在用的那个模式写换算后的图层（只写数据，不动它的画面）
        inactive = "ocg" if active == 1 else "rd"
        converted = _of_converted(app, _of_kind(active), inactive)
        if converted is not None:
            data[_OCG_OF_DATA_KEY if inactive == "ocg" else "rd_overframe_layers"] = converted
    except Exception:
        _tab_log("快照时同步超框卡图失败:\n" + traceback.format_exc())
    return data


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from card_library import _card_display_name, _card_for, _local_image_path, _pack_for, _search_cards
from card_search import _advanced_search_title, _open_manager_advanced_search
from effect_layout import (
    _effect_layout_state,
    _effect_layout_state_from_data,
    _inject_effect_layout_data,
    _set_effect_layout_state,
    _sync_effect_layout_controls,
)
from rd_frame import _schedule_rd_frame_sync, _sync_rd_frame_from_otcg
from rd_style import _RD_TEXT_COLOR_TARGETS, _apply_rd_style_data, _apply_rd_text_colors, _rd_style_state
from overframe import (
    _OCG_OF_DATA_KEY,
    _OF_SYNC_MODES,
    _apply_rd_overframe_data,
    _ocg_of_inject,
    _ocg_of_layers,
    _of_converted,
    _of_kind,
    _of_sync_after_apply,
    _of_sync_editors,
    _rd_overframe_layers,
)
from free_text import _apply_free_text_data, _ensure_free_text, _inject_free_text_into_data
from customization import _inject_customization_data, _load_customization_data, _sync_customization_selection
from watermark import _schedule_secret_watermark_recheck
from manga import _manga_inject_options, _manga_restore_options
from mode_styles import (
    _MODE_STYLES_KEY,
    _RD_PANEL_KEY,
    _active_style_key,
    _apply_rd_panel_style,
    _data_for_mode,
    _rd_language_bar_sync,
    _store_mode_style,
)
from language_switch import _all_tabs, _assign_card_uids, _renew_copied_pack_uids, _renew_copied_tab_uids
from editor_setup import _clear_demo_card, _optimize_graphics_view
from diagnostics import _export_performance_diagnostic, _export_rd_diagnostic
