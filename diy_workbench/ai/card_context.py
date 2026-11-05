"""各模式的只读文字快照；只读取显式字段，不触发保存、翻译或渲染。"""

import copy
import hashlib
import json

CARD_COMBOS = {
    "card_type": "type_selector", "template": "template_selector", "language": "lan_selector",
    "translation": "trans_selector", "tc_type": "tc_type_selector", "race": "race_selector",
    "call_way": "info_selector_left", "extra1": "info_selector_mid", "extra2": "info_selector_right",
    "mt_type": "MT_type_selector", "holo": "holo_selector", "copyright": "copyright_selector",
    "rare": "rare_selector", "watermark": "water_selector", "name_align": "name_align_selector",
    "text_align": "text_align_selector",
    "LB_ratio": "LB_ratio_selector",
}
CARD_LINES = {"name": "card_name_edit", "ATK": "ATK_edit", "DEF": "DEF_edit",
              "cardpass": "card_pass_edit", "cardpack": "card_pack_edit", "lb_level": "LB_level_edit",
              "detail_custom_text": "detail_custom_edit"}
CARD_TEXT = {"effect_text": "text_input", "lb_text": "LB_text_edit"}
CARD_ATTRS = {"level": "current_level", "rank": "current_rank", "attribute": "current_attribute",
              "link_status": "arrow_status_list", "text_sizeable": "text_sizeable",
              "text_weightable": "text_weightable"}
CARD_TOGGLES = {"attr_hide": "attr_hide_toggle", "full_effect": "full_effect_toggle", "LB_Zack": "LB_Zack_toggle",
                "detail_custom_toggle": "detail_custom_toggle", "copyright_vis": "toggle_copy",
                "cardpass_vis": "toggle_pass", "cardpack_vis": "toggle_pack", "holo_vis": "toggle_holo",
                "round_corner": "toggle_corner", "text_sizeable": "text_adjust_btn", "text_weightable": "text_weight_adjust_btn"}
CARD_SLIDERS = {"text_size_change": "text_size_slider", "text_weight_change": "text_weight_slider"}
FC_COMBOS = {"mode": "mode_selector", "background": "back_selector", "center": "center_selector",
             "center_back": "center_back_selector", "center_full": "center_full_selector",
             "border": "border_selector", "text": "text_selector", "title": "title_selector",
             "icon": "icon_selector", "logo": "logo_selector"}
BACK_COMBOS = {"type": "type_selector", "logo": "logo_selector"}
SHARED_CARD_FIELDS = tuple(CARD_LINES) + tuple(CARD_TEXT) + (
    "card_type", "race", "call_way", "extra1", "extra2", "mt_type", "level", "rank", "attribute", "link_status", "detail_custom_toggle", "LB_Zack", "LB_ratio")
RD_SESSION_FIELDS = ("max_atk", "max_atk_enabled", "legend")
RD_PANEL_FIELDS = ("holo", "copyright", "rare", "watermark", "name_align", "text_align")
MANGA_FIELDS = ("name", "card_type", "language", "call_way", "level", "rank", "link_status", "ATK", "DEF",
                "effect_text", "cardpass", "cardpack", "copyright_vis")


def modes(app):
    keys = ["ocg", "rd", "fc", "back", "past"]
    extra = {getattr(app, "_manga_mode_index", -1): "manga",
             getattr(app, "_workbench_mode_index", -1): "diy"}
    return [{"id": keys[i] if i < len(keys) else extra.get(i, "unknown"),
             "index": i, "label": app.combo_box.itemText(i)} for i in range(app.combo_box.count())]


def active_mode(app):
    return next(row for row in modes(app) if row["index"] == app.current_mode)


def current(app):
    manager = getattr(app, "card_tab_manager", None)
    if manager is None or not 0 <= manager.current_index < len(manager.tabs):
        return None, None
    pack = manager.packs[manager.current_pack_index] if 0 <= manager.current_pack_index < len(manager.packs) else None
    return manager.tabs[manager.current_index], pack


def _read_controls(editor, combos, lines=None, texts=None, attrs=None):
    fields, labels = {}, {}
    for key, name in combos.items():
        widget = getattr(editor, name, None)
        if widget is not None:
            fields[key], labels[key] = widget.currentIndex(), widget.currentText()
    for mapping, method in ((lines or {}, "text"), (texts or {}, "toPlainText")):
        for key, name in mapping.items():
            widget = getattr(editor, name, None)
            if widget is not None:
                fields[key] = getattr(widget, method)()
    for key, name in (attrs or {}).items():
        value = getattr(editor, name, None)
        if isinstance(value, (str, int, float, bool, list, tuple)):
            fields[key] = copy.deepcopy(value)
    return fields, labels


def _toggles(editor, names):
    result = {}
    for key, name in names.items():
        widget = getattr(editor, name, None)
        if widget is not None:
            result[key] = bool(widget.is_checked) if hasattr(widget, "is_checked") else widget.isChecked()
    return result


def _extra_fields(app, kind, tab, live):
    if kind == "manga":
        from manga import _MANGA_DATA_KEYS
        source = (getattr(app, "_manga_options", None) or _MANGA_DATA_KEYS) if live else (tab.get("data") or {})
        return {k: copy.deepcopy(source.get(k, default)) for k, default in _MANGA_DATA_KEYS.items()}
    if kind == "rd":
        from rd_style import _RD_TEXT_COLOR_TARGETS
        names = [name for flag, color, _ in _RD_TEXT_COLOR_TARGETS for name in (flag, color)]
        names += ["attr_style", "level_style", "AD_style"]
        source = app.rd_widget.__dict__ if live else (tab.get("data") or {})
        result = {name: copy.deepcopy(source[name]) for name in names if name in source}
        if live:
            result["max_atk"] = app.rd_widget.Max_ATK_edit.text()
            result.update(_toggles(app.rd_widget, {"max_atk_enabled": "Max_ATK_toggle", "legend": "toggle_legend"}))
        return result
    return {}


def _card_fields(app, kind, tab, live):
    if live:
        editor = app.past_widget if kind == "past" else app.otcg_widget
        fields, labels = _read_controls(editor, CARD_COMBOS, CARD_LINES, CARD_TEXT, CARD_ATTRS)
        fields.update(_toggles(editor, CARD_TOGGLES))
        for key, name in CARD_SLIDERS.items():
            if hasattr(editor, name):
                fields[key] = getattr(editor, name).value()
        if kind == "past":
            fields.update(_toggles(editor, {"only_img": "only_img_toggle"}))
    else:
        from mode_styles import _data_for_mode
        data = _data_for_mode(tab.get("data") or {}, "ocg" if kind == "diy" else kind)
        fields = {k: copy.deepcopy(data[k]) for k in (*CARD_COMBOS, *CARD_LINES, *CARD_TEXT, *CARD_ATTRS, *CARD_TOGGLES, *CARD_SLIDERS) if k in data}
        labels = {}
    if kind == "rd":
        combos = {k: CARD_COMBOS[k] for k in RD_PANEL_FIELDS}
        if live:
            overrides, override_labels = _read_controls(app.rd_widget, combos)
            fields.update(overrides)
            labels.update(override_labels)
        else:
            panel = ((tab.get("data") or {}).get("_mode_styles") or {}).get("rd_panel") or {}
            for key, name in combos.items():
                if name in panel:
                    fields[key] = labels[key] = panel[name]
    if kind == "manga":
        fields = {k: v for k, v in fields.items() if k in MANGA_FIELDS}
        labels = {k: v for k, v in labels.items() if k in MANGA_FIELDS}
    return fields, labels


def snapshot(app, tab=None):
    selected, pack = current(app)
    tab = selected if tab is None else tab
    mode = active_mode(app)
    kind = mode["id"]
    result = {"mode": mode, "card_uid": (tab or {}).get("_card_uid"),
              "card_label": (tab or {}).get("title", "未选择卡片"), "fields": {}, "labels": {}}
    if tab is None:
        return result
    if kind in ("fc", "back", "past"):
        if tab is not selected:
            raise ValueError("该模式目前是编辑器会话状态，不能把当前控件冒充其他卡的存档。")
        result["storage_scope"] = "editor_session"
    else:
        result["storage_scope"] = "card"
    if kind in ("ocg", "rd", "manga", "diy", "past"):
        result["fields"], result["labels"] = _card_fields(app, kind, tab, tab is selected)
    elif kind == "fc":
        result["fields"], result["labels"] = _read_controls(app.fc_widget, FC_COMBOS)
        result["fields"].update(_toggles(app.fc_widget, {"round_corner": "toggle_round"}))
    elif kind == "back":
        result["fields"], result["labels"] = _read_controls(app.back_widget, BACK_COMBOS)
        result["fields"].update(_toggles(app.back_widget, {"konami": "toggle_konmai", "r_symbol": "toggle_rsymbol", "round_corner": "toggle_round"}))
    if kind == "diy":
        diy = tab.get("diy") or {}
        result["fields"]["setcodes"] = copy.deepcopy(diy.get("setcodes", []))
        result["fields"]["effect_count"] = len((diy.get("blocks") or {}).get("effects", []))
    result["fields"].update(_extra_fields(app, kind, tab, tab is selected))
    if kind == "rd" and tab is selected:
        result["session_fields"] = list(RD_SESSION_FIELDS)
    manager = getattr(app, "card_tab_manager", None)
    if manager is not None:
        result["pack_index"] = next((i for i, pack in enumerate(manager.packs) if any(card is tab for card in pack.get("tabs", []))), None)
    state = json.dumps({"mode": kind, "card_uid": result["card_uid"], "fields": result["fields"]}, sort_keys=True, ensure_ascii=False)
    result["fingerprint"] = hashlib.sha256(state.encode("utf-8")).hexdigest()
    return result


def field_description(app):
    from mode_styles import _MODE_STYLE_KEYS
    data = snapshot(app)
    kind = data["mode"]["id"]
    fields = []
    for key in data["fields"]:
        scope = "editor_session" if kind in ("fc", "back", "past") else "mode"
        if kind in ("ocg", "rd", "manga", "diy") and key in SHARED_CARD_FIELDS:
            scope = "shared_ocg_rd_manga_diy"
        if kind == "diy" and key in ("setcodes", "effect_count"):
            scope = "diy"
        if kind == "rd" and key in RD_SESSION_FIELDS:
            scope = "editor_session"
        fields.append({"name": key, "storage_scope": scope, "access": "read_only"})
    return {"mode": data["mode"], "fields": fields, "independent_style_keys": list(_MODE_STYLE_KEYS),
            "note": "此快照只读；基础资料保持共用。写入参数、影响模式和保存范围请查看 describe_fields。"}
