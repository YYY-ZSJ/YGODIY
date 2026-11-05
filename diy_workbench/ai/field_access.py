"""字段写回适配：卡片沿用标签页数据/套用入口，会话编辑器使用已有控件信号。"""

import copy

from PyQt5.QtCore import QSignalBlocker

from . import card_context as context
from .field_rules import combo_map, editor_for, field_rules, is_session

SESSION_FLAGS = {"past": "Past_init", "fc": "FC_init", "back": "Back_init", "rd": "RD_init"}
FC_STATE_ATTRS = ("current_center", "current_full_center", "current_back_center", "current_full_border")
ART_ATTRS = ("card_img", "overframe_img", "center_img", "center_full_img")
ART_ITEMS = ("card_img_item", "overframe_item", "center_item", "full_center_item", "back_center_item")


def style_mode(mode):
    return "ocg" if mode == "diy" else mode


def location(uid, mode, field):
    from mode_styles import _is_style_key
    if is_session(mode, field):
        return ("editor", mode)
    if field in ("setcodes", "blocks", "tests", "design_text", "strings", "category", "script"):
        return ("diy", uid, field)
    if _is_style_key(field):
        return ("field", uid, style_mode(mode), field)
    return ("field", uid, "shared", field)


class FieldAccess:
    def __init__(self, app, project):
        self.app, self.project = app, project

    def values(self, document, mode, fields=None):
        from mode_styles import _data_for_mode
        source = document.get("data") or {}
        data = _data_for_mode(dict(self.project.manager._default_data, **source), style_mode(mode))
        result = {}
        for key, rule in field_rules(self.app, mode).items():
            if fields is not None and key not in fields:
                continue
            if is_session(mode, key):
                continue
            default = {"boolean": False, "integer": 0, "arrows": [False] * 8, "string": "", "color": "#000000"}.get(rule["type"], 0)
            if rule.get("text_value"):
                default = rule["choices"][0]
            value = copy.deepcopy(data.get(key, default))
            if mode == "rd" and key in context.RD_PANEL_FIELDS:
                selector = context.CARD_COMBOS[key]
                label = (source.get("_mode_styles", {}).get("rd_panel") or {}).get(selector)
                if label in rule["choices"]:
                    value = rule["choices"].index(label)
            if key == "setcodes":
                value = copy.deepcopy((document.get("diy") or {}).get("setcodes", []))
            result[key] = value
        return result

    def value(self, cell):
        key = cell["key"]
        if key[0] == "editor":
            return self.session(key[1])
        tab = self.project.card(key[1])
        if key[0] == "diy":
            if key[2] in ("tests", "design_text", "strings", "category", "script"):
                return copy.deepcopy((tab.get("diy") or {}).get(key[2]))
            if key[2] == "blocks":
                from blocks import SCHEMA
                return copy.deepcopy((tab.get("diy") or {}).get("blocks", {"schema": SCHEMA, "effects": []}))
            return copy.deepcopy((tab.get("diy") or {}).get(key[2], []))
        data = (self.project.manager._collect_editor_data_fast() if self.project.manager._current_tab() is tab
                else tab.get("data") or {})
        return self.values(dict(tab, data=data), cell["mode"], (key[-1],))[key[-1]]

    def put_document(self, document, mode, fields):
        from mode_styles import _is_style_key
        data = document["data"]
        for field, value in fields.items():
            if field in ("setcodes", "blocks", "tests", "design_text", "strings", "category", "script"):
                if field in ("tests", "design_text", "strings", "category", "script") and value is None:
                    document.setdefault("diy", {}).pop(field, None)
                else:
                    document.setdefault("diy", {})[field] = copy.deepcopy(value)
            elif _is_style_key(field):
                from mode_styles import _data_for_mode, _extract_style
                styles = data.setdefault("_mode_styles", {})
                if style_mode(mode) not in styles:
                    styles[style_mode(mode)] = _extract_style(_data_for_mode(data, style_mode(mode)))
                styles[style_mode(mode)][field] = copy.deepcopy(value)
                if style_mode(mode) == "ocg":
                    data[field] = copy.deepcopy(value)
                if mode == "rd" and field in context.RD_PANEL_FIELDS:
                    options = field_rules(self.app, mode)[field]["choices"]
                    data["_mode_styles"].setdefault("rd_panel", {})[context.CARD_COMBOS[field]] = options[value]
            else:
                data[field] = copy.deepcopy(value)

    def write(self, cells, desired, restore_assets=False):
        enabled = self.app.updatesEnabled()
        self.app.setUpdatesEnabled(False)
        try:
            self._write_cells(cells, desired, restore_assets)
        finally:
            self.app.setUpdatesEnabled(enabled)

    def _write_cells(self, cells, desired, restore_assets):
        changed = {}
        for cell in cells:
            key, value = cell["key"], desired(cell)
            if key[0] == "editor":
                self.restore_session(key[1], value, restore_assets)
                continue
            tab = self.project.card(key[1])
            field = key[-1]
            self.put_document(tab, cell["mode"], {field: value})
            changed[key[1]] = tab
        for tab in changed.values():
            self.project.changed(tab)
            self.sync_hidden_card_fields(tab)

    def sync_hidden_card_fields(self, tab):
        """宿主只载入当前类型可见的资料；隐藏字段也须保持本批写入/撤销后的值。"""
        from mode_styles import _active_style_key, _data_for_mode
        manager = self.project.manager
        if manager._current_tab() is not tab:
            return
        editor = manager.editor
        data = _data_for_mode(tab["data"], _active_style_key(self.app))
        monster = editor.type_selector.currentIndex() == 0
        link = monster and editor.info_selector_left.currentText() == "连接"
        pendulum = monster and editor.info_selector_mid.currentText() == "灵摆"
        combos, lines, texts, toggles = {}, {}, {}, {}
        if monster:
            combos["mt_type"] = "MT_type_selector"
        else:
            combos.update({key: context.CARD_COMBOS[key] for key in ("race", "call_way", "extra1", "extra2")})
            lines["ATK"] = "ATK_edit"
            for field in ("level", "rank", "attribute"):
                if field in data:
                    setattr(editor, context.CARD_ATTRS[field], data[field])
        if not monster or link:
            lines["DEF"] = "DEF_edit"
        if not link and "link_status" in data:
            editor.arrow_status_list = list(data["link_status"])
        if not pendulum:
            combos["LB_ratio"] = "LB_ratio_selector"
            lines["lb_level"], texts["lb_text"], toggles["LB_Zack"] = "LB_level_edit", "LB_text_edit", "LB_Zack_toggle"
        for mapping, method in ((combos, "setCurrentIndex"), (lines, "setText"), (texts, "setPlainText")):
            for field, name in mapping.items():
                if field in data:
                    widget = getattr(editor, name)
                    with QSignalBlocker(widget):
                        getattr(widget, method)(data[field])
        for field, name in toggles.items():
            if field in data:
                with QSignalBlocker(getattr(editor, name)):
                    self._toggle(getattr(editor, name), data[field])

    def ready(self, mode):
        return bool(getattr(self.app, SESSION_FLAGS[mode], False))

    def session(self, mode):
        if not self.ready(mode):
            raise ValueError("请先打开 %s 模式，再生成编辑器修改。" % mode)
        editor = editor_for(self.app, mode)
        if mode == "rd":
            fields = context._extra_fields(self.app, mode, {}, True)
            fields = {key: fields[key] for key in context.RD_SESSION_FIELDS}
        elif mode == "fc":
            fields, _ = context._read_controls(editor, context.FC_COMBOS)
            fields.update(context._toggles(editor, {"round_corner": "toggle_round"}))
        elif mode == "back":
            fields, _ = context._read_controls(editor, context.BACK_COMBOS)
            fields.update(context._toggles(editor, {"konami": "toggle_konmai", "r_symbol": "toggle_rsymbol", "round_corner": "toggle_round"}))
        else:
            fields, _ = context._card_fields(self.app, mode, {}, True)
            fields = {key: value for key, value in fields.items() if key in field_rules(self.app, mode)}
        objects = {key: getattr(editor, key) for key in ART_ATTRS if hasattr(editor, key)}
        pixmaps = {key: getattr(editor, key).pixmap() for key in ART_ITEMS if hasattr(editor, key)}
        extras = {key: getattr(editor, key) for key in FC_STATE_ATTRS if hasattr(editor, key)}
        return {"fields": copy.deepcopy(fields), "objects": objects, "pixmaps": pixmaps, "extras": extras}

    @staticmethod
    def same_session(a, b):
        return (a["fields"] == b["fields"] and a["extras"] == b["extras"]
                and {k: id(v) for k, v in a["objects"].items()} == {k: id(v) for k, v in b["objects"].items()}
                and {k: v.cacheKey() for k, v in a["pixmaps"].items()} == {k: v.cacheKey() for k, v in b["pixmaps"].items()})

    def candidate_session(self, mode, before, patch):
        result = dict(before, fields=dict(before["fields"], **patch), extras=dict(before["extras"]))
        if mode == "fc" and "mode" in patch:
            result["fields"]["border"] = patch.get("border", before["extras"].get("current_full_border", 0)) if patch["mode"] == 1 else 0
        if mode == "fc":
            for field, attr in (("center", "current_center"), ("center_full", "current_full_center"), ("center_back", "current_back_center")):
                if field in patch:
                    result["extras"][attr] = patch[field]
            if result["fields"]["mode"] == 1 and "border" in patch:
                result["extras"]["current_full_border"] = patch["border"]
        return result

    def restore_session(self, mode, snapshot, restore_assets=True):
        editor = editor_for(self.app, mode)
        for name, value in snapshot["extras"].items():
            setattr(editor, name, value)
        for field, value in snapshot["fields"].items():
            if self.session(mode)["fields"].get(field) != value:
                self._set_session_field(editor, mode, field, value)
        for name, value in snapshot["extras"].items():
            setattr(editor, name, value)
        if restore_assets:
            for name, image in snapshot["objects"].items():
                setattr(editor, name, image)
            for name, pixmap in snapshot["pixmaps"].items():
                getattr(editor, name).setPixmap(pixmap)
        editor._ygodiy_translation_job = None

    @staticmethod
    def _toggle(widget, value):
        if hasattr(widget, "is_checked"):
            if widget.is_checked != value:
                widget.is_checked = value
                widget.animate_circle()
                widget.toggled.emit(value)
        else:
            widget.setChecked(value)

    def _set_session_field(self, editor, mode, field, value):
        combos = combo_map(mode)
        toggles = dict(context.CARD_TOGGLES)
        toggles.update({"round_corner": "toggle_round", "konami": "toggle_konmai", "r_symbol": "toggle_rsymbol",
                        "max_atk_enabled": "Max_ATK_toggle", "legend": "toggle_legend", "only_img": "only_img_toggle"})
        if mode == "past":
            toggles["round_corner"] = "toggle_corner"
        if field in combos:
            getattr(editor, combos[field]).setCurrentIndex(value)
        elif field in context.CARD_LINES:
            getattr(editor, context.CARD_LINES[field]).setText(value)
        elif field in context.CARD_TEXT:
            getattr(editor, context.CARD_TEXT[field]).setPlainText(value)
        elif field in toggles:
            self._toggle(getattr(editor, toggles[field]), value)
        elif field in context.CARD_SLIDERS:
            getattr(editor, context.CARD_SLIDERS[field]).setValue(value)
        elif field == "max_atk":
            editor.Max_ATK_edit.setText(value)
        elif field == "attribute":
            editor.attribute_update(value)
        elif field in ("level", "rank"):
            setattr(editor, context.CARD_ATTRS[field], value)
            getattr(editor, "update_%s_status" % field)()
        elif field == "link_status":
            editor.arrow_status_list = list(value)
            editor.update_link_status()
