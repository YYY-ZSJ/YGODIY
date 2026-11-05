"""当前开放字段的参数说明与校验；模型不能指定控件名或执行方法。"""

import copy
import re

from . import card_context as context

SHARED_MODES = ("OCG/TCG", "超速决斗(Rush Duel)", "游戏王漫画卡", "DIY 工作台")
SESSION_MODES = ("fc", "back", "past")
SESSION_NOTE = "该模式的设置不随卡片保存；本次修改当前编辑器状态，可在本次启动期间整批撤销。"
MODE_LABELS = {"ocg": "OCG/TCG", "rd": "超速决斗(Rush Duel)", "manga": "游戏王漫画卡", "diy": "DIY 工作台",
               "fc": "场地中心卡", "back": "卡背", "past": "旧版卡"}
FIELD_LABELS = {"name": "卡名", "card_type": "卡片种类", "effect_text": "效果文字", "lb_text": "灵摆效果",
                "ATK": "攻击力", "DEF": "防御力", "attribute": "属性", "race": "种族", "level": "等级", "rank": "阶级",
                "cardpass": "卡密", "cardpack": "卡包编号", "blocks": "DIY 积木", "setcodes": "所属字段", "design_text": "效果设计稿", "strings": "提示文本", "category": "效果分类", "script": "手写脚本",
                "max_atk": "极限攻击力", "max_atk_enabled": "极限攻击开关", "legend": "传说标记",
                "text_sizeable": "字号调整开关", "text_size_change": "字号调整", "text_weightable": "字重调整开关",
                "text_weight_change": "字重调整", "only_img": "仅卡图", "attr_style": "属性文字样式",
                "level_style": "等级数字样式", "AD_style": "攻守数字样式", "template": "卡模/期数", "language": "语言",
                "translation": "中文翻译类型", "tc_type": "TCG 卡模", "call_way": "详细类型", "extra1": "附加类型一",
                "extra2": "附加类型二", "mt_type": "魔法/陷阱类型", "holo": "防伪", "copyright": "版权",
                "rare": "罕贵度", "watermark": "水印", "name_align": "卡名对齐", "text_align": "效果对齐",
                "LB_ratio": "灵摆卡图比例", "lb_level": "灵摆刻度", "LB_Zack": "扎克灵摆样式",
                "detail_custom_text": "自定种族文字", "detail_custom_toggle": "自定种族开关", "attr_hide": "隐藏属性",
                "full_effect": "效果全栏", "copyright_vis": "显示版权", "cardpass_vis": "显示卡密",
                "cardpack_vis": "显示卡包编号", "holo_vis": "显示防伪", "round_corner": "圆角",
                "manga_layout": "漫画布局", "manga_art": "漫画卡图风格", "manga_watermark": "漫画水印",
                "manga_ruby": "日文注音", "manga_halftone": "网点外框", "mode": "场地中心模式",
                "background": "背景", "center": "经典中心图", "center_back": "卡背中心图", "center_full": "全图中心图",
                "border": "边框", "text": "文字样式", "title": "场地标题", "icon": "场地图标", "logo": "标志",
                "type": "卡背类型", "konami": "K 标", "r_symbol": "R 标"}
FIELD_LABELS["tests"] = "测试情景与结果"
for _prefix, _label in (("text", "效果文字"), ("detail", "详细文字"), ("lb_text", "灵摆文字")):
    FIELD_LABELS[_prefix + "_color"] = _label + "颜色"
    FIELD_LABELS[_prefix + "_color_flag"] = _label + "颜色开关"


def editor_for(app, mode):
    name = {"past": "past_widget", "fc": "fc_widget", "back": "back_widget", "rd": "rd_widget"}.get(mode, "otcg_widget")
    return getattr(app, name)


def is_session(mode, field):
    return mode in SESSION_MODES or (mode == "rd" and field in context.RD_SESSION_FIELDS)


def affected(mode, field):
    if mode not in SESSION_MODES and field in context.SHARED_CARD_FIELDS:
        return list(SHARED_MODES)
    if mode in ("ocg", "diy") and field not in ("setcodes", "blocks", "tests", "design_text", "strings", "category", "script"):
        return ["OCG/TCG", "DIY 工作台"]
    return [MODE_LABELS[mode]]


def combo_map(mode):
    if mode == "fc":
        return context.FC_COMBOS
    if mode == "back":
        return context.BACK_COMBOS
    return context.CARD_COMBOS


def field_rules(app, mode):
    editor = editor_for(app, mode) if mode in SESSION_MODES else app.otcg_widget
    rules = {}
    for key, name in combo_map(mode).items():
        source = app.rd_widget if mode == "rd" and key in context.RD_PANEL_FIELDS else editor
        widget = getattr(source, name, None)
        if widget is not None:
            rules[key] = {"type": "choice", "choices": [widget.itemText(i) for i in range(widget.count())]}
    if mode not in ("fc", "back"):
        for key, name in {**context.CARD_LINES, **context.CARD_TEXT}.items():
            widget = getattr(editor, name, None)
            if widget is not None:
                rules[key] = {"type": "string", "max_length": min(12000, widget.maxLength()) if hasattr(widget, "maxLength") else 12000}
        rules.update({key: {"type": "boolean"} for key in context.CARD_TOGGLES if hasattr(editor, context.CARD_TOGGLES[key])})
        for key, name in context.CARD_SLIDERS.items():
            slider = getattr(editor, name, None)
            if slider is not None:
                rules[key] = {"type": "integer", "minimum": slider.minimum(), "maximum": slider.maximum()}
        rules.update({"level": {"type": "integer", "minimum": 0, "maximum": 13},
                      "rank": {"type": "integer", "minimum": 0, "maximum": 13},
                      "attribute": {"type": "choice", "choices": ["光", "暗", "水", "炎", "地", "风", "神"], "text_value": True},
                      "link_status": {"type": "arrows"}})
    if mode == "past":
        rules["only_img"] = {"type": "boolean"}
    if mode == "back":
        rules.update({key: {"type": "boolean"} for key in ("konami", "r_symbol", "round_corner")})
    if mode == "fc":
        rules["round_corner"] = {"type": "boolean"}
    if mode == "rd":
        rules.update({"max_atk": {"type": "string", "max_length": 4}, "max_atk_enabled": {"type": "boolean"}, "legend": {"type": "boolean"}})
        for prefix in ("text", "detail", "lb_text"):
            rules[prefix + "_color"] = {"type": "color"}
            rules[prefix + "_color_flag"] = {"type": "boolean"}
        for key in ("attr_style", "level_style", "AD_style"):
            choices = ["默认", "银色", "金色"] if key == "AD_style" else ["默认", "银色", "金色1", "金色2"]
            rules[key] = {"type": "choice", "choices": choices}
    if mode == "manga":
        from manga import _MANGA_ART_OPTIONS, _MANGA_LAYOUT_OPTIONS, _MANGA_WATERMARK_OPTIONS
        rules = {key: rule for key, rule in rules.items() if key in context.MANGA_FIELDS}
        rules.update({"manga_layout": {"type": "choice", "choices": [""] + [row[0] for row in _MANGA_LAYOUT_OPTIONS],
                                       "text_value": True, "labels": {"": "自动", **dict(_MANGA_LAYOUT_OPTIONS)}},
                      "manga_art": {"type": "choice", "choices": [row[0] for row in _MANGA_ART_OPTIONS],
                                    "text_value": True, "labels": dict(_MANGA_ART_OPTIONS)},
                      "manga_watermark": {"type": "choice", "choices": list(_MANGA_WATERMARK_OPTIONS), "text_value": True},
                      "manga_ruby": {"type": "boolean"}, "manga_halftone": {"type": "boolean"}})
    if mode == "diy":
        rules["setcodes"] = {"type": "setcodes"}
    return rules


def validate_value(value, rule):
    kind = rule["type"]
    if kind == "choice":
        options = rule["choices"]
        if rule.get("text_value") and isinstance(value, str) and value in options:
            return value
        if not rule.get("text_value"):
            if type(value) is int and 0 <= value < len(options):
                return value
            if isinstance(value, str) and value in options:
                return options.index(value)
    elif kind == "integer" and type(value) is int and rule["minimum"] <= value <= rule["maximum"]:
        return value
    elif kind == "boolean" and type(value) is bool:
        return value
    elif kind == "string" and isinstance(value, str) and len(value) <= rule["max_length"] and "\x00" not in value:
        return value
    elif kind == "arrows" and isinstance(value, list) and len(value) == 8 and all(type(v) is bool for v in value):
        return list(value)
    elif kind == "color" and isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value.lower()
    elif kind == "setcodes" and isinstance(value, list) and len(value) <= 32:
        if all(isinstance(v, str) and re.fullmatch(r"0x[0-9a-fA-F]{1,4}", v) for v in value):
            return list(dict.fromkeys("0x%x" % int(v, 16) for v in value))
    raise ValueError("字段值不符合类型、选项或范围要求。")


def validate_patch(app, mode, fields):
    if not isinstance(fields, dict) or not fields or len(fields) > 64:
        raise ValueError("fields 必须是非空字段对象，一次最多 64 项。")
    rules = field_rules(app, mode)
    result = {}
    for key, value in fields.items():
        if key not in rules:
            raise ValueError("字段 %s 尚未开放修改，请先查看 describe_fields。" % key)
        try:
            result[key] = validate_value(value, rules[key])
            if key in ("ATK", "DEF", "max_atk") and not re.fullmatch(r"\d*|\?|∞|-", result[key]):
                raise ValueError("攻守数值只能是数字、?、∞、- 或空白。")
        except ValueError as error:
            raise ValueError("%s：%s" % (key, error)) from None
    return result


def describe(app, mode):
    rows = []
    for key, rule in field_rules(app, mode).items():
        row = dict(copy.deepcopy(rule), name=key, label=FIELD_LABELS.get(key, key), access="modify", affected_modes=affected(mode, key))
        row["storage_scope"] = "editor_session" if is_session(mode, key) else "card"
        if is_session(mode, key):
            row["note"] = SESSION_NOTE
        rows.append(row)
    return {"fields": rows, "note": "基础资料按现有设计共用；修改默认先预览，自动应用仍保留批次和冲突检查。"}


def display_value(value, rule):
    if type(value) is bool:
        return "开启" if value else "关闭"
    if rule.get("type") == "choice":
        if not rule.get("text_value") and type(value) is int and 0 <= value < len(rule["choices"]):
            return rule["choices"][value]
        return rule.get("labels", {}).get(value, value)
    if rule.get("type") == "arrows" and isinstance(value, list):
        return "、".join(label for label, enabled in zip(("左上", "上", "右上", "左", "右", "左下", "下", "右下"), value) if enabled) or "无"
    return value
