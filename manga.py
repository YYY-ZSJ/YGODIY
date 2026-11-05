"""游戏王漫画卡模式：卡面绘制、选项条、独立右栏。

由补丁分片 p32、p41 整理而来。
"""

import traceback

from PyQt5.QtCore import QEvent, QObject, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPixmap

from common import _plain_text_from, _safe_call, _schedule_preview_update_restore, _tab_log, _text_from


_MANGA_MODE_LABEL = "游戏王漫画卡"
_MANGA_CARD_W = 1626
_MANGA_CARD_H = 2370
_MANGA_RENDER_INTERVAL_MS = 150
# 实卡的字是中等粗细的黑体（漫画手写字的感觉）：日文 / 英文用 Rodin Pro；
# Rodin 缺简体字（会混进系统字体），中文改用字形统一、简繁都有的 cn.ttf。
# 两者都偏细，绘制时用描边加粗到实卡的粗细（见 _MANGA_TEXT_WEIGHT）。
_MANGA_JP_FONT = "mold/font/FOT-Rodin Pro.ttf"
_MANGA_ZH_FONT = "mold/font/cn.ttf"
_MANGA_TEXT_WEIGHT = 0.045
_MANGA_COPYRIGHT = "©スタジオ・ダイス／集英社・テレビ東京・KONAMI"
# 卡图默认黑白。旧版的 manga_mono 每张进过漫画卡模式的卡都被自动写成了 False，
# 分不清是不是用户选的，所以换成新键 manga_art，旧键不再读取。
# 「漫画」：用算法把卡图转成上世纪黑白漫画的质感（墨线 + 网点 + 大面积留白），见 _manga_screentone
# 「特典卡」：仿高桥和希原画展「决斗王之证」——金色卡面、黑墨卡图配彩虹镭射光泽，见 _manga_tokuten_*
_MANGA_ART_OPTIONS = (("mono", "黑白"), ("color", "彩色"), ("manga", "漫画"), ("tokuten", "特典卡"))
# 水印：漫画版样卡的灰色「SAMPLE」按实卡重画；其余直接沿用 OCG 的整卡水印图
# （同为 1626x2370）。secret / secret_P 是专门盖住 OCG 效果框的黑块，会盖掉攻守，不收录。
_MANGA_SAMPLE_WATERMARK = "SAMPLE(漫画)"
_MANGA_WATERMARK_OPTIONS = (
    "无", _MANGA_SAMPLE_WATERMARK, "sample", "sample2", "DIY", "10000", "20th", "25th", "star",
)
# 漫画卡的「详细」只有 通常 / 效果 两种版式（各自独立于 OCG 的召唤方式；后者是
# 卡面信息，仍决定星星是等级还是阶级）。空值 = 自动：通常怪兽或没有效果文字的用通常版。
_MANGA_LAYOUT_OPTIONS = (("normal", "通常"), ("effect", "效果"))
_MANGA_DATA_KEYS = {
    "manga_layout": "",
    "manga_art": "mono",
    "manga_watermark": "无",
    "manga_ruby": True,
    "manga_halftone": True,
}
_MANGA_FONT_FAMILIES = {}


# ---------------------------------------------------------------------------
# 读取 OCG 编辑器的当前状态
# ---------------------------------------------------------------------------
def _manga_language(editor):
    selector = getattr(editor, "lan_selector", None)
    try:
        return str(selector.currentText()) if selector is not None else "简体中文"
    except Exception:
        return "简体中文"


def _manga_font_family(relative_path):
    family = _MANGA_FONT_FAMILIES.get(relative_path)
    if family is not None:
        return family
    family = ""
    try:
        import OTCG_widget
        from PyQt5.QtGui import QFontDatabase

        font_id = QFontDatabase.addApplicationFont(OTCG_widget.rpath(relative_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        family = families[0] if families else ""
    except Exception:
        family = ""
    _MANGA_FONT_FAMILIES[relative_path] = family
    return family


def _manga_name_family(editor, language):
    if language.startswith("日文") or language == "英文":
        return _manga_font_family(_MANGA_JP_FONT)
    return _manga_font_family(_MANGA_ZH_FONT)


def _manga_labels(language):
    """返回 (攻击标签, 守备标签, 攻击注音, 守备注音, 魔法, 陷阱, 连接)。注音按字给出。"""
    if language.startswith("日文"):
        return ("攻撃力", "守備力", ("こう", "げき", "りょく"), ("しゅ", "び", "りょく"),
                "魔法カード", "罠カード", "リンク")
    if language.startswith("繁体"):
        return ("攻擊力", "守備力", None, None, "魔法卡", "陷阱卡", "連結")
    if language == "英文":
        return ("ATK", "DEF", None, None, "Spell Card", "Trap Card", "LINK")
    return ("攻击力", "守备力", None, None, "魔法卡", "陷阱卡", "连接")


def _manga_resolve_layout(choice, card_type, call_way, effect_text):
    """漫画卡版式：用户选过就用选的；否则通常怪兽或没有效果文字的用通常版。"""
    if choice in ("normal", "effect"):
        return choice
    if card_type == "怪兽卡" and (call_way == "通常" or not str(effect_text or "").strip()):
        return "normal"
    return "effect" if str(effect_text or "").strip() else "normal"


def _manga_state(app):
    editor = getattr(app, "otcg_widget", None)
    if editor is None:
        return None

    def text_of(name):
        widget = getattr(editor, name, None)
        try:
            return str(widget.text()) if widget is not None else ""
        except Exception:
            return ""

    card_type = str(getattr(editor, "card_type", "") or "")
    call_way = str(getattr(editor, "detail_call_way", "") or "")
    if card_type != "怪兽卡":
        stars = 0
    elif call_way == "连接":
        stars = 0
    elif call_way == "超量":
        stars = int(getattr(editor, "current_rank", 0) or 0)
    else:
        stars = int(getattr(editor, "current_level", 0) or 0)
    arrows = getattr(editor, "arrow_status_list", None) or ()
    art_item = getattr(editor, "card_img_item", None)
    try:
        art = art_item.pixmap() if art_item is not None else None
    except Exception:
        art = None
    copyright_toggle = getattr(editor, "toggle_copy", None)
    options = getattr(app, "_manga_options", None) or dict(_MANGA_DATA_KEYS)
    text_input = getattr(editor, "text_input", None)
    try:
        effect_text = str(text_input.toPlainText()) if text_input is not None else ""
    except Exception:
        effect_text = ""
    return {
        "name": text_of("card_name_edit"),
        "language": _manga_language(editor),
        "card_type": card_type,
        "call_way": call_way,
        "stars": max(0, min(13, stars)),
        "link": sum(1 for value in arrows if value),
        "atk": text_of("ATK_edit"),
        "def": text_of("DEF_edit"),
        "effect_text": effect_text,
        "layout": _manga_resolve_layout(options.get("manga_layout"), card_type, call_way, effect_text),
        "art": art,
        "art_key": art.cacheKey() if art is not None and not art.isNull() else None,
        "copyright": bool(getattr(copyright_toggle, "is_checked", True)) if copyright_toggle is not None else True,
        "mono": options.get("manga_art", "mono") != "color",
        "art_mode": str(options.get("manga_art") or "mono"),
        "watermark": str(options.get("manga_watermark") or "无"),
        "ruby": bool(options.get("manga_ruby")),
        "halftone": bool(options.get("manga_halftone")),
        "name_family": _manga_name_family(editor, _manga_language(editor)),
    }


def _manga_signature(state):
    if state is None:
        return None
    return tuple((key, value) for key, value in sorted(state.items()) if key != "art")


# ---------------------------------------------------------------------------
# 绘制
# ---------------------------------------------------------------------------
def _manga_star_path(cx, cy, radius):
    import math
    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QPainterPath, QPolygonF

    inner = radius * 0.42
    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        r = radius if index % 2 == 0 else inner
        points.append(QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(points))
    path.closeSubpath()
    return path


def _manga_halftone_brush(scale):
    from PyQt5.QtGui import QBrush, QColor, QPixmap

    cell = max(2, int(round(6 * scale)))
    tile = QPixmap(cell * 2, cell * 2)
    tile.fill(QColor(8, 8, 8))
    painter = QPainter(tile)
    painter.fillRect(0, 0, cell, cell, QColor(58, 58, 58))
    painter.fillRect(cell, cell, cell, cell, QColor(58, 58, 58))
    painter.end()
    return QBrush(tile)


# cn.ttf 的字面比 Rodin 小一圈，同字号下中文会显得缩水；按字面高度补偿。
_MANGA_FAMILY_SCALE = {_MANGA_ZH_FONT: 1.22}


def _manga_font(family, pixel_size, bold=False):
    for path, factor in _MANGA_FAMILY_SCALE.items():
        if family and family == _MANGA_FONT_FAMILIES.get(path):
            pixel_size *= factor
    font = QFont(family) if family else QFont()
    font.setPixelSize(max(1, int(round(pixel_size))))
    font.setBold(bold)
    return font


def _manga_draw_text(painter, text, font, x, baseline, max_width=None, align="left", stretch=1.0,
                     weight=_MANGA_TEXT_WEIGHT):
    """画一行文字；超出 max_width 时横向压缩，weight>0 时按字号比例描边加粗。

    返回实际占用的 (左, 右)。
    """
    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QFontMetricsF, QPainterPath, QPen

    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text) * stretch
    scale_x = stretch
    if max_width and width > max_width:
        scale_x = stretch * max_width / max(1.0, width)
        width = max_width
    left = x - width if align == "right" else x
    path = QPainterPath()
    path.addText(QPointF(0, 0), font, text)
    color = painter.pen().color()
    painter.save()
    painter.translate(left, baseline)
    painter.scale(scale_x, 1.0)
    painter.fillPath(path, color)
    if weight > 0:
        pen = QPen(color)
        pen.setWidthF(font.pixelSize() * weight)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.strokePath(path, pen)
    painter.restore()
    return left, left + width


# 攻守是两栏固定排版（按实卡实测）：标签左缘固定在 0.479W，两行对齐；
# 数值右对齐到 right（0.877W）。数值长短不影响标签位置。
_MANGA_STAT_LABEL_LEFT = 0.476   # 字形左侧有留白，实际墨迹左缘落在 0.479W
_MANGA_STAT_LABEL_SIZE = 0.053   # 标签「攻撃力」实测宽 0.219W
# 标签栏宽固定：中文字体（cn.ttf 放大补偿后）比日文宽一截，不限宽会挤占数值栏，
# 把 4 位数压窄、和短数值对不齐。任何语言的标签都只压不放，最宽到这里。
_MANGA_STAT_LABEL_WIDTH = 0.222


def _manga_draw_stat(painter, label, ruby, value, family, scale, right, baseline, show_ruby):
    from PyQt5.QtGui import QFontMetricsF

    H = _MANGA_CARD_H * scale
    W = _MANGA_CARD_W * scale
    label_font = _manga_font(family, _MANGA_STAT_LABEL_SIZE * H)
    # 数字一律用 Rodin 再横向压窄，和实卡的窄体数字一致
    number_font = _manga_font(_manga_font_family(_MANGA_JP_FONT), 0.050 * H)
    number_stretch = 0.86
    gap = 0.018 * W
    label_left = _MANGA_STAT_LABEL_LEFT * W
    column_right = label_left + _MANGA_STAT_LABEL_WIDTH * W
    natural_width = QFontMetricsF(label_font).horizontalAdvance(label)
    if natural_width < 0.9 * _MANGA_STAT_LABEL_WIDTH * W:
        # 明显比标签栏窄（如英文 ATK / DEF）：靠栏的右侧放，紧挨数值
        label_left, _ = _manga_draw_text(painter, label, label_font, column_right, baseline, align="right")
    else:
        # 日文 / 中文标签基本占满整栏：左对齐到实卡的位置
        _manga_draw_text(painter, label, label_font, label_left, baseline,
                         max_width=_MANGA_STAT_LABEL_WIDTH * W)
    label_right = column_right
    # 数值太长、会碰到标签时横向压窄，而不是推动标签
    if value:
        _manga_draw_text(painter, value, number_font, right, baseline, align="right",
                         stretch=number_stretch, max_width=max(1.0, right - label_right - gap))
    if not (show_ruby and ruby):
        return
    # 注音：逐字居中放在对应汉字上方
    ruby_font = _manga_font(family, 0.0175 * H)
    ruby_metrics = QFontMetricsF(ruby_font)
    label_metrics = QFontMetricsF(label_font)
    cursor = label_left
    ruby_baseline = baseline - label_metrics.ascent() * 0.98
    for char, reading in zip(label, ruby):
        char_width = label_metrics.horizontalAdvance(char)
        reading_width = ruby_metrics.horizontalAdvance(reading)
        _manga_draw_text(painter, reading, ruby_font, cursor + (char_width - reading_width) / 2, ruby_baseline,
                         weight=_MANGA_TEXT_WEIGHT * 0.6)
        cursor += char_width


# ---------------------------------------------------------------------------
# 效果版：卡图下方 4 行效果文字 + 一行攻守（按实卡「インセクト女王」实测，407x593）
# ---------------------------------------------------------------------------
_MANGA_EFFECT = {
    "left": 0.097,          # 文字左缘（与卡图框对齐）
    "right": 0.897,         # 换行宽度到卡图框右缘
    "size": 0.0287,         # 字号（汉字字面高约 0.0253H）
    # 文字块顶端贴着卡图框（框下缘 0.744H）：实卡首行注音从 0.752H 起，
    # 正文不带注音，所以直接从这里开始；文字块底端到第 4 行字底 0.901H。
    # 首行正文墨迹上缘：实卡为 0.762H，上方 0.752~0.759H 是这一行的日文注音，要留出来
    "block_top": 0.762,
    "block_bottom": 0.901,
    "first_baseline": 0.783,  # 仅用于计算攻守行位置（= 4 行版式下的第 1 行基线）
    "pitch": 0.0385,        # 行距
    "lines": 4,             # 效果文字最多 4 行，超出时整体缩小字号
    "min_scale": 0.55,
    "stats_gap_label": 0.022,   # 「攻撃力」与数值之间
    "stats_gap_pair": 0.020,    # 攻击数值与「守備力」之间
    "ruby_size": 0.0105,
}
# 行首禁则：这些标点不放在行首，挂到上一行末尾
_MANGA_NO_LINE_START = set("、。，．・）」』】〕〉》！？：；ー…,.!?)]}")


def _manga_wrap_ruby(text, spans, font, width):
    """按宽度换行：汉字/假名逐字断行，连续的英文数字整词不断开，遵守行首禁则；
    text 是去掉注音后的正文，带注音的汉字（spans）整段不拆开。
    返回每行在正文里的 (起, 止)。"""
    import re
    from PyQt5.QtGui import QFontMetricsF

    metrics = QFontMetricsF(font)
    ruby_ranges = [(start, start + length) for start, length, _ in spans]

    def same_ruby(a, b):
        return any(rs < a[1] and a[0] < re_ and rs < b[1] and b[0] < re_ for rs, re_ in ruby_ranges)

    lines = []
    offset = 0
    for paragraph in text.split("\n"):
        tokens = []
        for match in re.finditer(r"[A-Za-z0-9+\-'.,%/]+|\s+|.", paragraph):
            token = (offset + match.start(), offset + match.end())
            if tokens and same_ruby(tokens[-1], token):
                tokens[-1] = (tokens[-1][0], token[1])
            else:
                tokens.append(token)
        start = end = None
        for token_start, token_end in tokens:
            token = text[token_start:token_end]
            if start is None or metrics.horizontalAdvance(text[start:token_end]) <= width:
                if start is None:
                    start = token_start
                end = token_end
                continue
            if token.isspace():
                lines.append((start, end)); start = None
                continue
            if token[0] in _MANGA_NO_LINE_START:
                end = token_end           # 禁则字符挂在行尾（允许略微超出）
                continue
            lines.append((start, end)); start, end = token_start, token_end
        paragraph_end = offset + len(paragraph)
        lines.append((start, end) if start is not None else (paragraph_end, paragraph_end))
        offset = paragraph_end + 1
    stripped = []
    for start, end in lines:
        while end > start and text[end - 1].isspace():
            end -= 1
        stripped.append((start, end))
    while stripped and stripped[-1][0] == stripped[-1][1]:
        stripped.pop()
    return stripped


def _manga_ruby_baseline_offset(body_font, ruby_px):
    """读音基线相对正文基线的位置（负数，向上）：放在汉字实际墨迹上缘（含描边）之上留一点空。
    以前用 ascent * 0.98，Rodin 的 ascent 比汉字字面还矮，读音会压进汉字顶端。"""
    from PyQt5.QtGui import QFontMetricsF

    stroke = body_font.pixelSize() * _MANGA_TEXT_WEIGHT
    # 各汉字字面高度不一，取几个偏高的字的上缘
    return QFontMetricsF(body_font).tightBoundingRect("漢高撃壊").top() - stroke / 2 - 0.1 * ruby_px


def _manga_ruby_ink_top(body_font, family, ruby_px):
    """读音墨迹上缘相对正文基线的位置（负数，向上），含读音描边。"""
    from PyQt5.QtGui import QFontMetricsF

    ruby_font = _manga_font(family, ruby_px)
    ruby_top = QFontMetricsF(ruby_font).tightBoundingRect("あ").top()
    ruby_stroke = ruby_font.pixelSize() * _MANGA_TEXT_WEIGHT * 0.6
    return _manga_ruby_baseline_offset(body_font, ruby_px) + ruby_top - ruby_stroke / 2


def _manga_draw_effect_line_ruby(painter, line, line_spans, font, left, baseline, max_width, family, ruby_px):
    """效果栏一行的注音：按这一行实际的横向压缩比例，把读音居中放在汉字上方。"""
    from PyQt5.QtGui import QFontMetricsF

    if not line_spans:
        return
    metrics = QFontMetricsF(font)
    full = metrics.horizontalAdvance(line)
    scale_x = max_width / full if max_width and full > max_width else 1.0
    ruby_font = _manga_font(family, ruby_px)
    ruby_metrics = QFontMetricsF(ruby_font)
    ruby_baseline = baseline + _manga_ruby_baseline_offset(font, ruby_px)
    for start, length, reading in line_spans:
        base_x = left + metrics.horizontalAdvance(line[:start]) * scale_x
        base_w = metrics.horizontalAdvance(line[start:start + length]) * scale_x
        reading_w = ruby_metrics.horizontalAdvance(reading)
        # 读音比汉字宽时最多压到 0.6，再宽就居中溢出两侧（与 RD 注音一致）
        draw_w = min(reading_w, max(base_w, reading_w * 0.6))
        _manga_draw_text(painter, reading, ruby_font, base_x + (base_w - draw_w) / 2, ruby_baseline,
                         max_width=draw_w, weight=_MANGA_TEXT_WEIGHT * 0.6)


def _manga_draw_label_ruby(painter, label, ruby, label_font, label_left, baseline, family, ruby_px):
    """逐字把注音居中放在对应汉字上方。"""
    from PyQt5.QtGui import QFontMetricsF

    if not ruby:
        return
    ruby_font = _manga_font(family, ruby_px)
    ruby_metrics = QFontMetricsF(ruby_font)
    label_metrics = QFontMetricsF(label_font)
    cursor = label_left
    ruby_baseline = baseline + _manga_ruby_baseline_offset(label_font, ruby_px)
    for char, reading in zip(label, ruby):
        char_width = label_metrics.horizontalAdvance(char)
        reading_width = ruby_metrics.horizontalAdvance(reading)
        _manga_draw_text(painter, reading, ruby_font, cursor + (char_width - reading_width) / 2, ruby_baseline,
                         weight=_MANGA_TEXT_WEIGHT * 0.6)
        cursor += char_width


def _manga_draw_effect_block(painter, state, family, labels, W, H, show_ruby):
    geo = dict(_MANGA_EFFECT)
    # cn.ttf 在 _manga_font 里整体放大了 1.22 倍（卡名/攻守标签需要），用在大段正文上
    # 偏大；效果栏里收回一些，让中文字宽和日文 Rodin 相当。
    if family and family == _MANGA_FONT_FAMILIES.get(_MANGA_ZH_FONT):
        geo["size"] *= 0.85
    atk_label, def_label, atk_ruby, def_ruby, spell_label, trap_label, link_label = labels
    left, width = geo["left"] * W, (geo["right"] - geo["left"]) * W

    # 效果文字：文字块顶端固定贴着卡图框，放不下时整体缩小字号和行距
    # （以前固定的是首行基线，缩小后字顶下沉，离卡框越缩越远）
    # 日文注音写法「[汉字(读音)]」：正文按去掉注音后的文字排版，读音另画在汉字上方；
    # 关掉「日文注音」时只画正文，不再把方括号原样印出来。
    from PyQt5.QtGui import QFontMetricsF

    text, ruby_spans = _rd_parse_ruby(str(state.get("effect_text") or "").replace("\r", ""))
    with_ruby = bool(show_ruby and ruby_spans)
    block_top, block_bottom = geo["block_top"] * H, geo["block_bottom"] * H
    stats_baseline = (geo["first_baseline"] + geo["lines"] * geo["pitch"]) * H
    label_font = _manga_font(family, geo["size"] * H)
    if show_ruby and state.get("card_type") == "怪兽卡":
        # 攻守标签的注音在效果文字块下方，末行正文不能压到它
        stats_ruby_top = stats_baseline + _manga_ruby_ink_top(label_font, family, geo["ruby_size"] * H)
        block_bottom = min(block_bottom, stats_ruby_top - 0.2 * geo["ruby_size"] * H)
    scale_text, line_ranges, lines, font, pitch = 1.0, [], [], None, 0.0
    while True:
        font = _manga_font(family, geo["size"] * H * scale_text)
        line_ranges = _manga_wrap_ruby(text, ruby_spans, font, width)
        lines = [text[start:end] for start, end in line_ranges]
        px = font.pixelSize()
        pitch = geo["pitch"] * H * scale_text
        if with_ruby:
            # 有注音时行距要容下「上一行字底 + 间隙 + 这一行的读音」，否则读音压到上一行；
            # 按实际字体量，不同字体的字面高度差得不少。
            ruby_px = geo["ruby_size"] * H * scale_text
            metrics = QFontMetricsF(font)
            ink_bottom = max([metrics.tightBoundingRect(line).bottom() for line in lines if line] + [0.12 * px])
            ink_bottom += px * _MANGA_TEXT_WEIGHT / 2      # 描边加粗的半宽
            ruby_rise = -_manga_ruby_ink_top(font, family, ruby_px)
            pitch = max(pitch, ink_bottom + 0.25 * ruby_px + ruby_rise)
        # 汉字字面约占字号的 0.88（字顶到基线）与 0.12（基线到字底）
        needed = 0.88 * px + max(0, len(lines) - 1) * pitch + 0.12 * px
        if needed <= block_bottom - block_top + 0.5 or scale_text <= geo["min_scale"]:
            break
        scale_text = max(geo["min_scale"], scale_text * 0.95)
    # 以第一行文字的实际墨迹上缘对齐 block_top（各字体的字面高度不同，固定比例会偏）
    first_ink_top = QFontMetricsF(font).tightBoundingRect(lines[0]).top() if lines and lines[0] else -0.88 * font.pixelSize()
    baseline = block_top - first_ink_top
    for line, (line_start, line_end) in zip(lines, line_ranges):
        _manga_draw_text(painter, line, font, left, baseline, max_width=width)
        if show_ruby:
            line_spans = [
                (start - line_start, length, reading)
                for start, length, reading in ruby_spans
                if line_start <= start < line_end
            ]
            _manga_draw_effect_line_ruby(painter, line, line_spans, font, left, baseline, width, family,
                                         geo["ruby_size"] * H * scale_text)
        baseline += pitch

    # 最后一行：攻守与效果文字同字号，左对齐；数字用 Rodin
    number_font = _manga_font(_manga_font_family(_MANGA_JP_FONT), geo["size"] * H)
    card_type = state.get("card_type")
    if card_type != "怪兽卡":
        kind = spell_label if card_type == "魔法卡" else trap_label
        _manga_draw_text(painter, kind, label_font, left, stats_baseline)
        return
    if state.get("call_way") == "连接":
        pairs = ((atk_label, atk_ruby, state.get("atk", "")), (link_label, None, str(int(state.get("link") or 0))))
    else:
        pairs = ((atk_label, atk_ruby, state.get("atk", "")), (def_label, def_ruby, state.get("def", "")))
    cursor = left
    for index, (label, ruby, value) in enumerate(pairs):
        label_left = cursor
        _, cursor = _manga_draw_text(painter, label, label_font, cursor, stats_baseline)
        if show_ruby:
            _manga_draw_label_ruby(painter, label, ruby, label_font, label_left, stats_baseline, family,
                                   geo["ruby_size"] * H)
        cursor += geo["stats_gap_label"] * W
        if value:
            _, cursor = _manga_draw_text(painter, value, number_font, cursor, stats_baseline, stretch=0.92)
        if index == 0:
            cursor += geo["stats_gap_pair"] * W


# ---------------------------------------------------------------------------
# 卡图「漫画」模式：上世纪黑白漫画质感
# ---------------------------------------------------------------------------
# 按官方漫画版卡片的画风归纳：纯黑白；大面积留白；粗而连贯的墨线勾边；
# 中间调用 45° 网点表现，暗处网点更大（渐变）；最暗处实心涂黑。步骤：
#   1. 灰度 + 自动对比度，两次中值滤波 + 轻微模糊，压掉照片式的细碎纹理；
#   2. 按这张图自己的亮度分布分层：最暗 12% 涂黑、接下来 38% 铺网点、其余留白，
#      层级图再做众数滤波，让每块区域干净成片；
#   3. XDoG（高斯差分）抽墨线，模糊后重新二值化成圆润的粗线，去掉孤立噪点；
#   4. 网点区内点的大小随亮度连续变化（调幅网点），最后叠上墨线。
# 在不超过 _MANGA_TONE_WORK_SIZE 的边长上计算（约 1 秒），结果按卡图缓存。
_MANGA_TONE = {
    "shares": (0.12, 0.16, 0.22),   # 涂黑 / 浓网点 / 淡网点 各占画面的比例，其余留白
    "line_thresh": 0.008,
    "region": 9,                    # 众数滤波尺寸（区域平整度）
    "tone_range": (0.08, 0.48),     # 网点覆盖率：最亮的网点区 ~ 最暗的网点区
    "pitch_div": 75.0,              # 网点间距 = 边长 / 75
}
_MANGA_TONE_WORK_SIZE = 1240
_MANGA_TONE_CACHE = {}
_MANGA_TONE_CACHE_LIMIT = 6


def _manga_screentone(image):
    """PIL 图（正方形）→ 黑白漫画网点风格的 PIL 'L' 图。"""
    import numpy as np
    from PIL import Image as _Image, ImageFilter, ImageOps

    def blur(a, sigma):
        img = _Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
        return np.asarray(img.filter(ImageFilter.GaussianBlur(sigma))).astype(np.float32) / 255.0

    geo = _MANGA_TONE
    gray = ImageOps.autocontrast(image.convert("L"), cutoff=1)
    w, h = gray.size
    pitch = max(4.0, w / geo["pitch_div"])
    flat_img = gray.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.MedianFilter(5))
    flat = blur(np.asarray(flat_img).astype(np.float32) / 255.0, w / 400.0)

    b, d, l = geo["shares"]
    t_black, t_dense, t_light = np.quantile(flat, [b, b + d, b + d + l])
    levels = np.full((h, w), 3, np.uint8)
    levels[flat < t_light] = 2
    levels[flat < t_dense] = 1
    levels[flat < t_black] = 0
    levels = np.asarray(_Image.fromarray(levels * 60).filter(ImageFilter.ModeFilter(geo["region"]))).astype(np.uint8) // 60

    s = max(0.8, w / 500.0)
    dog = blur(flat, s) - 0.99 * blur(flat, s * 1.6)
    soft = blur((dog < -geo["line_thresh"]).astype(np.float32), max(0.6, w / 900.0))
    lines = np.asarray(_Image.fromarray(((soft > 0.32) * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(3))) > 127

    lo, hi = geo["tone_range"]
    darkness = np.clip((t_light - flat) / max(1e-4, t_light - t_black), 0, 1)
    coverage = np.clip(lo + (hi - lo) * darkness, 0, 0.78)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    angle = np.deg2rad(45.0)
    u = (xx * np.cos(angle) + yy * np.sin(angle)) / pitch
    v = (-xx * np.sin(angle) + yy * np.cos(angle)) / pitch
    du, dv = u - np.round(u), v - np.round(v)
    dots = np.sqrt(du * du + dv * dv) < np.sqrt(coverage / np.pi)

    white = np.ones((h, w), dtype=bool)
    white[levels == 0] = False
    white[(levels >= 1) & (levels <= 2) & dots] = False
    white[lines] = False
    return _Image.fromarray((white * 255).astype(np.uint8))


# ---------------------------------------------------------------------------
# 卡图「特典卡」模式：仿「决斗王之证」（高桥和希原画展特典，金箔加工）
# ---------------------------------------------------------------------------
# 照片放大观察：
#   * 卡面是哑光的卡其金，带细密金沙颗粒和零星闪点（不是拉丝）；
#   * 卡图是「浮雕烫金」：以原图明暗当作高度做浮雕光照，线条像凸起的金属，
#     有受光高光和背光阴影；暗部近黑，亮部是有金属反射的亮金；
#   * 镭射是大范围柔和的彩虹色块，落在卡图的金属亮部。
_MANGA_TOKUTEN = {
    "stock": (160, 140, 92),        # 卡面金色（照片实测约 153,134,88）
    "dark": (22, 18, 10),           # 卡图暗部墨色
    "gold_lo": (128, 98, 38),       # 烫金背光处
    "gold_hi": (242, 208, 112),     # 烫金受光处
    "relief": 28.0,                 # 浮雕起伏（越小越立体）
    "groove": 0.55,                 # 墨线刻成凹槽的深度
    "grain": 1.0,                   # 卡面金沙颗粒强度
    "holo": 0.65,                   # 彩虹镭射强度
}
_MANGA_TOKUTEN_CACHE = {}


def _manga_np_to_qimage(np, rgb):
    from PyQt5.QtGui import QImage

    rgb = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
    h, w = rgb.shape[:2]
    return QImage(rgb.tobytes(), w, h, w * 3, QImage.Format_RGB888).copy()


def _manga_qimage_to_np(np, image):
    from PyQt5.QtGui import QImage

    image = image.convertToFormat(QImage.Format_RGB888)
    pointer = image.constBits()
    pointer.setsize(image.byteCount())
    rows = np.frombuffer(pointer, np.uint8).reshape(image.height(), image.bytesPerLine())
    return rows[:, :image.width() * 3].reshape(image.height(), image.width(), 3).astype(np.float32)


def _manga_np_blur(np, a, sigma):
    from PIL import Image as _Image, ImageFilter

    img = _Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(sigma))).astype(np.float32) / 255.0


def _manga_tokuten_gold(width, height):
    """哑光金沙卡面（按尺寸缓存；最多按标准卡宽生成，高清导出时由绘制放大）。"""
    if width > _MANGA_CARD_W:
        height = max(1, int(round(height * _MANGA_CARD_W / float(width))))
        width = _MANGA_CARD_W
    key = ("gold", width, height, _MANGA_TOKUTEN["stock"], _MANGA_TOKUTEN.get("grain"))
    cached = _MANGA_TOKUTEN_CACHE.get(key)
    if cached is not None:
        return cached
    import numpy as np

    rng = np.random.default_rng(3)
    base = np.array(_MANGA_TOKUTEN["stock"], np.float32)
    grain = _manga_np_blur(np, np.clip(rng.normal(0, 1, (height, width)).astype(np.float32) * 0.18 + 0.5, 0, 1), 0.9) - 0.5
    spark = _manga_np_blur(np, (rng.random((height, width)) > 0.993).astype(np.float32), 0.8) * 3.0
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    sheen = 0.06 * np.sin((xx / width * 0.9 + yy / height * 0.6) * np.pi)
    amount = _MANGA_TOKUTEN.get("grain", 1.0)
    t = 1.0 + grain * 0.9 * amount + sheen + spark * 0.45 * amount
    image = _manga_np_to_qimage(np, base[None, None] * t[..., None])
    _MANGA_TOKUTEN_CACHE[key] = image
    return image


def _manga_tokuten_art_qimage(art_image, source, target_size, art_key):
    """卡图 → 浮雕烫金 + 柔和彩虹镭射（按卡图与尺寸缓存）。"""
    from PIL import Image as _Image, ImageOps
    import numpy as np

    geo = _MANGA_TOKUTEN
    size = int(min(_MANGA_TONE_WORK_SIZE, max(64, round(target_size))))
    key = ("art", art_key, size, tuple(sorted(geo.items())))
    cached = _MANGA_TOKUTEN_CACHE.get(key)
    if cached is not None:
        return cached
    crop = art_image.copy(int(source.x()), int(source.y()), int(source.width()), int(source.height()))
    pil = _Image.fromarray(_manga_qimage_to_np(np, crop).astype(np.uint8)).resize((size, size), _Image.LANCZOS)
    g = np.asarray(ImageOps.autocontrast(pil.convert("L"), cutoff=1)).astype(np.float32) / 255.0

    # 浮雕光照：明暗当高度，墨线（高斯差分）再刻成凹槽，光从左上方来。
    # 凹槽两侧一边受光一边背光，形成照片上那种刻进金属里的锐利线纹。
    base_h = _manga_np_blur(np, g, max(0.6, size / 900.0))
    s1 = max(0.8, size / 520.0)
    dog = _manga_np_blur(np, g, s1) - _manga_np_blur(np, g, s1 * 1.6)
    groove = np.clip(-dog * 25.0, 0, 1)
    height = base_h - geo["groove"] * _manga_np_blur(np, groove, max(0.6, size / 1000.0))
    gy, gx = np.gradient(height * (size / geo["relief"]))
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    nx, ny = -gx * nz, -gy * nz
    lx, ly, lz = -0.5, -0.6, 0.62
    diffuse = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)
    hx, hy, hz = lx, ly, lz + 1.0
    hn = np.sqrt(hx * hx + hy * hy + hz * hz)
    spec = np.clip((nx * hx + ny * hy + nz * hz) / hn, 0, 1) ** 40

    gold_lo, gold_hi = np.array(geo["gold_lo"], np.float32), np.array(geo["gold_hi"], np.float32)
    lum = np.clip(0.35 + 0.75 * diffuse, 0, 1.2)[..., None]
    foil = gold_lo + (gold_hi - gold_lo) * np.clip(lum * (0.55 + 0.45 * g[..., None]), 0, 1)

    # 大范围柔和彩虹
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32) / size
    # 照片上的镭射以暖色为主：红 → 橙 → 黄 → 绿，在这段色相里来回渐变（不转满一圈）
    sweep = 0.5 + 0.5 * np.sin((0.55 * xx + 0.35 * yy) * 2.0 * np.pi + 0.15 * np.sin(xx * 5.0 + yy * 3.0))
    hue = 0.97 + 0.32 * sweep
    hue = hue % 1.0
    k = np.stack([(hue * 6 + n) % 6 for n in (5, 3, 1)], -1)
    rainbow = 255.0 * (1 - np.clip(np.minimum(k, 4 - k), 0, 1))
    patch = np.clip(np.sin(xx * 3.1 + 0.6) * np.cos(yy * 2.3 - 0.4) * 0.5 + 0.5, 0, 1)
    hmask = (geo["holo"] * patch)[..., None] * np.clip(g * 1.4, 0, 1)[..., None]
    foil = foil * (1 - hmask * 0.5) + (foil * 0.45 + rainbow * 0.55) * hmask * 0.5
    foil = foil + 255.0 * spec[..., None] * 0.75

    metal = (np.clip((g - 0.12) / 0.75, 0, 1) ** 0.8)[..., None]
    out = np.array(geo["dark"], np.float32) * (1 - metal) + foil * metal
    image = _manga_np_to_qimage(np, out)
    _MANGA_TOKUTEN_CACHE[key] = image
    while len(_MANGA_TOKUTEN_CACHE) > 12:
        _MANGA_TOKUTEN_CACHE.pop(next(iter(_MANGA_TOKUTEN_CACHE)))
    return image


def _manga_screentone_qimage(art_image, source, target_size, art_key):
    """裁成正方形的卡图 → 漫画网点 QImage（按卡图与尺寸缓存）。"""
    from PyQt5.QtGui import QImage
    from PIL import Image as _Image

    work = int(min(_MANGA_TONE_WORK_SIZE, max(64, round(target_size))))
    key = (art_key, work, tuple(sorted(_MANGA_TONE.items())))
    cached = _MANGA_TONE_CACHE.get(key)
    if cached is None:
        crop = art_image.copy(int(source.x()), int(source.y()), int(source.width()), int(source.height()))
        crop = crop.convertToFormat(QImage.Format_RGB888)
        pointer = crop.constBits()
        pointer.setsize(crop.byteCount())
        pil = _Image.frombuffer("RGB", (crop.width(), crop.height()), bytes(pointer), "raw", "RGB",
                                crop.bytesPerLine(), 1)
        pil = pil.resize((work, work), _Image.LANCZOS)
        result = _manga_screentone(pil)
        data = result.tobytes()
        cached = QImage(data, work, work, work, QImage.Format_Grayscale8).copy()
        _MANGA_TONE_CACHE[key] = cached
        while len(_MANGA_TONE_CACHE) > _MANGA_TONE_CACHE_LIMIT:
            _MANGA_TONE_CACHE.pop(next(iter(_MANGA_TONE_CACHE)))
    return cached


_MANGA_WATERMARK_IMAGES = {}
# 漫画版样卡的浅灰「SAMPLE」（以卡宽 W、卡高 H 计）：left 左缘、width 总宽、
# baseline 基线、size 字号、spacing 字距（负值收紧）。按官方样卡逐字母实测拟合：
# 「S」应落在 0.148W~0.254W、0.786H~0.914H。
_MANGA_SAMPLE_GEOMETRY = {
    "left": 0.144, "width": 0.70, "baseline": 0.913, "size": 0.175, "spacing": -0.008,
}


def _manga_watermark_image(name):
    """OCG 的整卡水印图（1626x2370，透明底），按名字缓存。"""
    if name in _MANGA_WATERMARK_IMAGES:
        return _MANGA_WATERMARK_IMAGES[name]
    from PyQt5.QtGui import QImage

    image = None
    try:
        import OTCG_widget

        loaded = QImage(OTCG_widget.rpath("mold/watermark/%s.png" % name))
        image = None if loaded.isNull() else loaded
    except Exception:
        image = None
    _MANGA_WATERMARK_IMAGES[name] = image
    return image


def _manga_draw_watermark(painter, name, W, H, scale):
    from PyQt5.QtCore import QRectF

    if not name or name == "无":
        return
    if name == _MANGA_SAMPLE_WATERMARK:
        geo = _MANGA_SAMPLE_GEOMETRY
        family = _manga_font_family("mold/font/Yu-Gi-Oh! FOT-Rodin ProN DB.ttf")
        painter.save()
        painter.setPen(QColor(197, 197, 197))
        font = _manga_font(family, geo["size"] * H)
        font.setLetterSpacing(QFont.AbsoluteSpacing, geo["spacing"] * H)
        # stretch 取大值：文字总是被横向压到正好 geo["width"] 宽
        _manga_draw_text(painter, "SAMPLE", font, geo["left"] * W, geo["baseline"] * H,
                         max_width=geo["width"] * W, stretch=4.0, weight=0.03)
        painter.restore()
        return
    image = _manga_watermark_image(name)
    if image is not None:
        painter.drawImage(QRectF(0, 0, W, H), image)


def _manga_render(state, width=_MANGA_CARD_W, height=_MANGA_CARD_H):
    from PyQt5.QtCore import QRectF
    from PyQt5.QtGui import QImage, QPen

    scale = float(width) / _MANGA_CARD_W
    W, H = float(width), float(height)
    image = QImage(int(width), int(height), QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    black = QColor(17, 17, 17)

    # 外框与白底
    tokuten = state.get("art_mode") == "tokuten"
    if tokuten:
        # 特典卡：一圈细黑边 + 拉丝金色卡面（不用网点外框）
        border = 0.018 * W
        painter.fillRect(QRectF(0, 0, W, H), black)
        painter.drawImage(QRectF(border, border, W - 2 * border, H - 2 * border),
                          _manga_tokuten_gold(int(W - 2 * border), int(H - 2 * border)))
    else:
        border = 0.033 * W
        if state.get("halftone", True):
            painter.fillRect(QRectF(0, 0, W, H), _manga_halftone_brush(scale))
        else:
            painter.fillRect(QRectF(0, 0, W, H), black)
        painter.fillRect(QRectF(border, border, W - 2 * border, H - 2 * border), QColor(255, 255, 255))
    painter.setPen(black)

    language = state.get("language", "简体中文")
    family = state.get("name_family") or ""
    jp_family = _manga_font_family(_MANGA_JP_FONT)
    labels = _manga_labels(language)
    if tokuten and language == "英文":
        # 特典卡（决斗王之证）上写的是完整的 ATTACK / DEFENCE
        labels = ("ATTACK", "DEFENCE") + tuple(labels[2:])
    stat_family = family

    # 卡名
    name = state.get("name") or ""
    _manga_draw_text(painter, name, _manga_font(family, 0.046 * H), 0.10 * W, 0.100 * H,
                     max_width=0.79 * W)

    # 星星：最右一颗的右缘对齐 0.89W，太多时缩小间距
    stars = int(state.get("stars") or 0)
    if stars:
        right = 0.89 * W
        pitch = min(0.069 * W, (0.79 * W) / stars)
        radius = min(0.0205 * H, pitch * 0.47)
        painter.setPen(Qt.NoPen)
        painter.setBrush(black)
        for index in range(stars):
            cx = right - radius - pitch * (stars - 1 - index)
            painter.drawPath(_manga_star_path(cx, 0.144 * H, radius))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(black)

    # 卡图框：实卡由外到内是 外黑线 / 亮色带 / 内黑线，卡图嵌在里面。
    # 亮色带黑白版是白色、彩色版是黄色（按样卡实测，换算到 1626 宽约 9 / 12 / 6 px）。
    # 位置按两张 407 宽的实卡实测（通常版与效果版相同）：0.101W~0.897W、0.197H 起，正方形。
    frame_rect = QRectF(0.101 * W, 0.197 * H, 0.796 * W, 0.796 * W)
    mono = bool(state.get("mono", True))
    band_color = QColor(242, 242, 242) if mono else QColor(245, 222, 12)
    if state.get("art_mode") == "tokuten":
        band_color = QColor(150, 118, 52)   # 特典卡：深金色斜面
    outer, band, inner = 9.0 * scale, 12.0 * scale, 6.0 * scale
    painter.fillRect(frame_rect, black)
    band_rect = frame_rect.adjusted(outer, outer, -outer, -outer)
    painter.fillRect(band_rect, band_color)
    inner_rect = band_rect.adjusted(band, band, -band, -band)
    painter.fillRect(inner_rect, black)
    art_rect = inner_rect.adjusted(inner, inner, -inner, -inner)
    # 四个角的斜接线：像画框一样斜穿亮色带，把外黑线和内黑线连起来（实卡四角都有）。
    # 两端各伸进外黑线、内黑线的中线，保证连上（平头粗线斜着画时端点会缺一角）。
    from PyQt5.QtCore import QPointF

    miter_pen = QPen(black)
    miter_pen.setWidthF(max(1.0, 5.0 * scale))
    miter_pen.setCapStyle(Qt.FlatCap)
    painter.setPen(miter_pen)
    o, i = outer / 2.0, inner / 2.0
    for outer_corner, inner_corner, (sx, sy) in (
        (band_rect.topLeft(), inner_rect.topLeft(), (1, 1)),
        (band_rect.topRight(), inner_rect.topRight(), (-1, 1)),
        (band_rect.bottomLeft(), inner_rect.bottomLeft(), (1, -1)),
        (band_rect.bottomRight(), inner_rect.bottomRight(), (-1, -1)),
    ):
        start = outer_corner - QPointF(sx * o, sy * o)
        end = inner_corner + QPointF(sx * i, sy * i)
        painter.drawLine(start, end)
    painter.setPen(black)

    # 卡图：中心裁成正方形
    art = state.get("art")
    if art is not None and not art.isNull():
        side = min(art.width(), art.height())
        source = QRectF((art.width() - side) / 2.0, (art.height() - side) / 2.0, side, side)
        art_image = art.toImage()
        manga_art = None
        if state.get("art_mode") == "manga":
            try:
                manga_art = _manga_screentone_qimage(art_image, source, art_rect.width(), state.get("art_key"))
            except Exception:
                _tab_log("漫画网点处理失败:\n" + traceback.format_exc())
        elif state.get("art_mode") == "tokuten":
            try:
                manga_art = _manga_tokuten_art_qimage(art_image, source, art_rect.width(), state.get("art_key"))
            except Exception:
                _tab_log("特典卡卡图处理失败:\n" + traceback.format_exc())
        if manga_art is not None:
            painter.drawImage(art_rect, manga_art)
        else:
            if mono:
                art_image = art_image.convertToFormat(QImage.Format_Grayscale8)
            painter.drawImage(art_rect, art_image, source)
    else:
        painter.fillRect(art_rect, QColor(225, 225, 225))
    painter.setPen(black)

    # 水印压在攻守、版权文字下面（实卡样张的「SAMPLE」就是这样）
    _manga_draw_watermark(painter, state.get("watermark") or "无", W, H, scale)
    painter.setPen(black)

    # 攻守 / 卡种
    atk_label, def_label, atk_ruby, def_ruby, spell_label, trap_label, link_label = labels
    stat_right = 0.880 * W   # 数字右侧有留白，实际墨迹右缘落在 0.876W
    show_ruby = bool(state.get("ruby"))
    card_type = state.get("card_type")
    if state.get("layout") == "effect":
        _manga_draw_effect_block(painter, state, family, labels, W, H, show_ruby)
    elif card_type == "怪兽卡":
        _manga_draw_stat(painter, atk_label, atk_ruby, state.get("atk", ""), stat_family, scale,
                         stat_right, 0.827 * H, show_ruby)
        if state.get("call_way") == "连接":
            # 连接值与攻守同一套两栏排版：标签靠左栏、数值靠右栏
            _manga_draw_stat(painter, link_label, None, str(int(state.get("link") or 0)), stat_family,
                             scale, stat_right, 0.917 * H, False)
        else:
            _manga_draw_stat(painter, def_label, def_ruby, state.get("def", ""), stat_family, scale,
                             stat_right, 0.917 * H, show_ruby)
    else:
        kind = spell_label if card_type == "魔法卡" else trap_label
        _manga_draw_text(painter, kind, _manga_font(stat_family, 0.050 * H), stat_right, 0.917 * H,
                         align="right")

    # 版权
    if state.get("copyright", True):
        painter.setPen(QColor(60, 60, 60))
        _manga_draw_text(painter, _MANGA_COPYRIGHT, _manga_font(jp_family, 0.0125 * H), 0.90 * W,
                         0.968 * H, align="right", weight=0)
    painter.end()
    return image


# ---------------------------------------------------------------------------
# 场景、选项栏与模式切换
# ---------------------------------------------------------------------------
def _manga_ensure_scene(app):
    scene = getattr(app, "manga_scene", None)
    if scene is not None:
        return scene
    from PyQt5.QtCore import QRectF, QTimer
    from PyQt5.QtWidgets import QGraphicsPixmapItem, QGraphicsScene

    scene = QGraphicsScene(QRectF(0, 0, _MANGA_CARD_W, _MANGA_CARD_H), app)
    item = QGraphicsPixmapItem()
    item.setTransformationMode(Qt.SmoothTransformation)
    scene.addItem(item)
    app.manga_scene = scene
    app.manga_item = item
    app._manga_signature = None
    timer = QTimer(app)
    timer.setInterval(_MANGA_RENDER_INTERVAL_MS)
    timer.timeout.connect(lambda target=app: _manga_refresh(target))
    app._manga_timer = timer
    return scene


def _manga_refresh_before_panel(app, force=False):
    try:
        state = _manga_state(app)
        if state is None:
            return
        signature = _manga_signature(state)
        if not force and signature == getattr(app, "_manga_signature", None):
            return
        app._manga_signature = signature
        app.manga_item.setPixmap(QPixmap.fromImage(_manga_render(state)))
        _manga_sync_detail_combo(app)
    except Exception:
        _tab_log("刷新漫画卡预览失败:\n" + traceback.format_exc())


def _manga_options_changed(app):
    bar = getattr(app, "_manga_bar", None)
    if bar is None:
        return
    previous = getattr(app, "_manga_options", None) or {}
    app._manga_options = {
        # 版式只由「详细」下拉自己改（见 _manga_layout_changed），这里原样保留
        "manga_layout": previous.get("manga_layout", ""),
        "manga_art": _MANGA_ART_OPTIONS[max(0, bar.art_selector.currentIndex())][0],
        "manga_watermark": bar.water_selector.currentText() or "无",
        "manga_ruby": bar.ruby_check.isChecked(),
        "manga_halftone": bar.halftone_check.isChecked(),
    }
    if getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", -1):
        _manga_refresh(app, force=True)


def _manga_layout_changed(app, index):
    if index < 0:
        return
    options = dict(getattr(app, "_manga_options", None) or _MANGA_DATA_KEYS)
    options["manga_layout"] = _MANGA_LAYOUT_OPTIONS[index][0]
    app._manga_options = options
    if getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", -1):
        _manga_refresh(app, force=True)


def _manga_sync_detail_combo_before_panel(app):
    combo = getattr(app, "_manga_detail_combo", None)
    if combo is None:
        return
    state = _manga_state(app)
    layout = state.get("layout") if state else "normal"
    codes = [code for code, _label in _MANGA_LAYOUT_OPTIONS]
    blocked = combo.blockSignals(True)
    try:
        combo.setCurrentIndex(codes.index(layout) if layout in codes else 0)
    finally:
        combo.blockSignals(blocked)
    # 效果文字输入框只在效果版显示（通常版的卡面上没有效果文字）
    text_input = getattr(getattr(app, "otcg_widget", None), "text_input", None)
    in_manga = getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", -2)
    if text_input is not None and in_manga:
        text_input.setVisible(layout == "effect")


class _MangaModeOnlyGuard(QObject):
    """只允许控件在漫画卡模式下显示。"""

    def __init__(self, app):
        super().__init__(app)
        self._app = app

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.ShowToParent:
                app = self._app
                if getattr(app, "current_mode", None) != getattr(app, "_manga_mode_index", -2):
                    QTimer.singleShot(0, lambda widget=obj: _manga_hide_if_not_manga(app, widget))
        except Exception:
            pass
        return False


def _manga_hide_if_not_manga(app, widget):
    try:
        if getattr(app, "current_mode", None) != getattr(app, "_manga_mode_index", -2):
            widget.setVisible(False)
    except Exception:
        pass


def _manga_install_detail_combo(app):
    """在 OCG 面板「详细」那一行放漫画卡专用的 通常 / 效果 下拉（只在漫画卡模式显示）。"""
    if getattr(app, "_manga_detail_combo", None) is not None:
        return
    from PyQt5.QtWidgets import QComboBox

    editor = getattr(app, "otcg_widget", None)
    label = getattr(editor, "detail_info_label", None)
    root = editor.layout() if editor is not None else None
    if label is None or root is None:
        return

    def find(layout):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item.widget() is label:
                return layout, index
            if item.layout() is not None:
                found = find(item.layout())
                if found:
                    return found
        return None

    found = find(root)
    if not found:
        return
    row, index = found
    combo = QComboBox(editor)
    combo.addItems([text for _code, text in _MANGA_LAYOUT_OPTIONS])
    row.insertWidget(index + 1, combo, 1)
    combo.setVisible(False)
    # 宿主处理「详细」这一行时会把行里的控件逐个显示出来，连带把它也显示了；
    # 不在漫画卡模式时一出现就收回去。
    guard = _MangaModeOnlyGuard(app)
    combo.installEventFilter(guard)
    app._manga_detail_guard = guard
    app._manga_detail_combo = combo
    combo.currentIndexChanged.connect(lambda index: _manga_layout_changed(app, index))


def _manga_sync_bar(app):
    _manga_sync_detail_combo(app)
    bar = getattr(app, "_manga_bar", None)
    if bar is None:
        return
    options = getattr(app, "_manga_options", None) or dict(_MANGA_DATA_KEYS)
    art_codes = [code for code, _label in _MANGA_ART_OPTIONS]
    art = options.get("manga_art", "mono")
    watermark_index = max(0, bar.water_selector.findText(str(options.get("manga_watermark") or "无")))
    for widget, setter, value in (
        (bar.art_selector, "setCurrentIndex", art_codes.index(art) if art in art_codes else 0),
        (bar.water_selector, "setCurrentIndex", watermark_index),
        (bar.ruby_check, "setChecked", bool(options.get("manga_ruby"))),
        (bar.halftone_check, "setChecked", bool(options.get("manga_halftone"))),
    ):
        blocked = widget.blockSignals(True)
        try:
            getattr(widget, setter)(value)
        finally:
            widget.blockSignals(blocked)


def _manga_install_bar(app):
    if getattr(app, "_manga_bar", None) is not None:
        return
    from PyQt5.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QWidget

    combo = getattr(app, "combo_box", None)
    panel = combo.parentWidget() if combo is not None else None
    layout = panel.layout() if panel is not None else None
    if layout is None:
        return
    bar = QWidget(panel)
    row = QHBoxLayout(bar)
    row.setContentsMargins(4, 2, 4, 2)
    row.addWidget(QLabel("漫画卡卡图"))
    bar.art_selector = QComboBox(bar)
    bar.art_selector.addItems([label for _code, label in _MANGA_ART_OPTIONS])
    row.addWidget(bar.art_selector)
    row.addSpacing(12)
    row.addWidget(QLabel("水印"))
    bar.water_selector = QComboBox(bar)
    bar.water_selector.addItems(list(_MANGA_WATERMARK_OPTIONS))
    row.addWidget(bar.water_selector)
    row.addSpacing(12)
    bar.ruby_check = QCheckBox("日文注音", bar)
    row.addWidget(bar.ruby_check)
    bar.halftone_check = QCheckBox("网点外框", bar)
    row.addWidget(bar.halftone_check)
    row.addStretch(1)
    layout.insertWidget(layout.indexOf(combo) + 1, bar)
    bar.setVisible(False)
    app._manga_bar = bar
    app._manga_options = dict(_MANGA_DATA_KEYS)
    _manga_sync_bar(app)
    bar.art_selector.currentIndexChanged.connect(lambda *_: _manga_options_changed(app))
    bar.water_selector.currentIndexChanged.connect(lambda *_: _manga_options_changed(app))
    bar.ruby_check.toggled.connect(lambda *_: _manga_options_changed(app))
    bar.halftone_check.toggled.connect(lambda *_: _manga_options_changed(app))


# ---------------------------------------------------------------------------
# 导出：漫画卡模式下「导出图片」「卡包导出」输出漫画卡
# ---------------------------------------------------------------------------
def _manga_save_image(editor, file_name):
    """OTCGWidget.save_image 开头调用：漫画卡模式下「导出图片」「卡包导出」输出漫画卡，返回 True；
    不在漫画卡模式时返回 False，由宿主照常导出。"""
    app = getattr(editor, "parent_app", None)
    manga_index = getattr(app, "_manga_mode_index", -1)
    if app is None or manga_index < 0 or getattr(app, "current_mode", None) != manga_index:
        return False
    if not file_name:
        return True
    try:
        from PyQt5.QtGui import QImage

        factor = 2 if getattr(editor, "HD_card_img", False) else 1
        image = _manga_render(_manga_state(app), _MANGA_CARD_W * factor, _MANGA_CARD_H * factor)
        if str(file_name).lower().endswith((".jpg", ".jpeg")):
            image = image.convertToFormat(QImage.Format_RGB888)
            image.save(file_name, "JPG", 95)
        else:
            # 压缩等级 80：特典卡的金色拉丝纹几乎压不动，默认最高压缩写高清图要 5 秒，
            # 80 只要约 1 秒，文件只大约四分之一
            image.save(file_name, "PNG", 80)
    except Exception:
        _tab_log("导出漫画卡失败:\n" + traceback.format_exc())
    return True


# ---------------------------------------------------------------------------
# 标签页：漫画卡选项随卡片保存与恢复
# ---------------------------------------------------------------------------
def _manga_option_value(value, default):
    """按默认值的类型规整选项（布尔开关 / 字符串选项）。"""
    if isinstance(default, bool):
        return bool(value)
    return str(value) if value is not None else default


def _manga_inject_options(manager, data):
    """卡片数据补上漫画卡选项（卡图彩色 / 黑白、注音、网点外框等），随卡保存。"""
    if isinstance(data, dict):
        options = getattr(manager.app, "_manga_options", None) or _MANGA_DATA_KEYS
        for key, default in _MANGA_DATA_KEYS.items():
            data[key] = _manga_option_value(options.get(key, default), default)
    return data


def _manga_restore_options(manager, data):
    """套用卡片数据之后恢复这张卡的漫画卡选项。"""
    try:
        if isinstance(data, dict):
            manager.app._manga_options = {
                key: _manga_option_value(data.get(key, default), default)
                for key, default in _MANGA_DATA_KEYS.items()
            }
            _manga_sync_bar(manager.app)
    except Exception:
        _tab_log("恢复漫画卡选项失败:\n" + traceback.format_exc())


_MANGA_PANEL_SPACING = 7
_MANGA_PANEL_EFFECT_MIN_HEIGHT = 250


def _manga_panel_hbox():
    from PyQt5.QtWidgets import QHBoxLayout

    box = QHBoxLayout()
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(_MANGA_PANEL_SPACING)
    return box


def _manga_panel_halves(left, right):
    """OCG 的典型行：左半栏(4) + 间隔(1) + 右半栏(4)。元素可以是控件或布局。"""
    from PyQt5.QtWidgets import QLayout

    row = _manga_panel_hbox()
    for index, items in enumerate((left, right)):
        half = _manga_panel_hbox()
        for entry in items:
            if isinstance(entry, tuple):
                entry, stretch = entry
            else:
                stretch = 0
            if isinstance(entry, QLayout):
                half.addLayout(entry, stretch)
            else:
                half.addWidget(entry, stretch)
        if not items:
            half.addStretch(1)
        row.addLayout(half, 4)
        if index == 0:
            row.addStretch(1)
    return row


def _manga_panel_even(widget):
    """宽度只按拉伸系数分配，标签与下拉才能像 OCG 那样对半分。"""
    from PyQt5.QtWidgets import QSizePolicy

    widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())
    return (widget, 1)


def _manga_flip_toggle(toggle, checked):
    """把宿主的 ToggleButton 拨到指定状态（与它的 mousePressEvent 做的事相同）。"""
    if toggle is None or bool(getattr(toggle, "is_checked", False)) == bool(checked):
        return
    toggle.is_checked = bool(checked)
    _safe_call(getattr(toggle, "animate_circle", None))
    toggle.toggled.emit(toggle.is_checked)


def _manga_show_toggle(toggle, checked):
    """只改本面板开关的显示，不发信号。"""
    if toggle is None or bool(getattr(toggle, "is_checked", False)) == bool(checked):
        return
    toggle.is_checked = bool(checked)
    _safe_call(getattr(toggle, "animate_circle", None))
    toggle.update()


class _MangaPanelFields:
    """本面板控件 <-> OCG 编辑器上存放数据的控件 的对应关系与同步。"""

    LINE_FIELDS = (
        ("name_edit", "card_name_edit"),
        ("atk_edit", "ATK_edit"),
        ("def_edit", "DEF_edit"),
        ("pass_edit", "card_pass_edit"),
        ("pack_edit", "card_pack_edit"),
    )
    COMBO_FIELDS = (
        ("type_selector", "type_selector"),
        ("lan_selector", "lan_selector"),
    )
    TOGGLE_FIELDS = (
        ("source_toggle", "source_toggle"),
        ("copy_toggle", "toggle_copy"),
    )


def _manga_panel_build(app):
    from PyQt5.QtWidgets import QComboBox, QLabel, QLineEdit, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget
    import customComponents as components

    editor = getattr(app, "otcg_widget", None)
    stack = getattr(app, "stacked_widget", None)
    if editor is None or stack is None:
        return None
    panel = QWidget()
    panel.setObjectName("manga_panel")
    root = QVBoxLayout(panel)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(_MANGA_PANEL_SPACING)
    style = editor.styleSheet()
    if style:
        panel.setStyleSheet(style)

    def label(text):
        return QLabel(text, panel)

    def line_edit():
        return QLineEdit(panel)

    def combo_like(source):
        combo = QComboBox(panel)
        combo.addItems([source.itemText(i) for i in range(source.count())])
        return combo

    def button(text):
        return QPushButton(text, panel)

    def toggle():
        return components.ToggleButton(panel, check=False, width=42, height=20)

    # 卡名 | 类型
    panel.name_edit = line_edit()
    panel.type_selector = combo_like(editor.type_selector)
    root.addLayout(_manga_panel_halves(
        [label("卡名"), panel.name_edit],
        [_manga_panel_even(label("类型")), _manga_panel_even(panel.type_selector)],
    ))
    # 语言
    panel.lan_selector = combo_like(editor.lan_selector)
    root.addLayout(_manga_panel_halves(
        [_manga_panel_even(label("语言")), _manga_panel_even(panel.lan_selector)], []))
    # 漫画卡选项（p32 的选项条，整条搬进来）
    bar = getattr(app, "_manga_bar", None)
    if bar is not None:
        _manga_panel_adopt_bar(panel, root, bar)
    # 上传卡图
    panel.upload_nocrop = button("上传卡图(不裁剪)")
    panel.upload_crop = button("上传卡图(裁剪)")
    root.addLayout(_manga_panel_halves([(panel.upload_nocrop, 1), (panel.upload_crop, 1)], []))
    # 详细：漫画卡版式（通常 / 效果）。p32 原本把它插在 OCG 的详细行里，这里接管过来。
    detail = getattr(app, "_manga_detail_combo", None)
    if detail is not None:
        _manga_panel_adopt_detail(app, panel, detail)
        detail_row = _manga_panel_hbox()
        detail_label = label("详细")
        for widget in (detail_label, detail):
            widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())
            detail_row.addWidget(widget, 1)
        detail_row.addStretch(3)
        root.addLayout(detail_row)
    # 等级 / 阶级（星星）
    panel.level_row = QWidget(panel)
    stars = _manga_panel_hbox()
    panel.level_row.setLayout(stars)
    panel.level_label = label("等级 0")
    panel.level_label.setFixedWidth(62)
    panel.level_zero = components.CloseButton(20, 20, panel)
    stars.addWidget(panel.level_label)
    stars.addWidget(panel.level_zero)
    panel.stars = []
    for _ in range(13):
        stars.addStretch(1)
        star = components.StarButton(editor.bg_undo_color, editor.star_undo_color, 10, 0.85, panel)
        stars.addWidget(star)
        panel.stars.append(star)
    root.addWidget(panel.level_row)
    # 连接箭头
    panel.link_row = QWidget(panel)
    arrows = _manga_panel_hbox()
    panel.link_row.setLayout(arrows)
    panel.link_label = label("LINK 0")
    panel.link_label.setFixedWidth(62)
    arrows.addWidget(panel.link_label)
    panel.arrows = []
    for _ in range(len(getattr(editor, "link_control_list", ()) or ())):
        arrows.addStretch(1)
        arrow = components.LinkButton(20, True, panel)
        arrows.addWidget(arrow)
        panel.arrows.append(arrow)
    arrows.addStretch(4)
    root.addWidget(panel.link_row)
    # 攻击 / 防御
    panel.atk_row = QWidget(panel)
    stat = _manga_panel_hbox()
    panel.atk_row.setLayout(stat)
    panel.atk_edit = line_edit()
    panel.def_edit = line_edit()
    for caption, edit in (("攻击", panel.atk_edit), ("防御", panel.def_edit)):
        pair = _manga_panel_hbox()
        pair.addWidget(label(caption))
        pair.addWidget(edit)
        stat.addLayout(pair, 35)
        stat.addStretch(5)
    root.addWidget(panel.atk_row)
    # 效果文字（只在效果版显示）
    panel.effect_edit = QTextEdit(panel)
    panel.effect_edit.setAcceptRichText(False)
    panel.effect_edit.setMinimumHeight(_MANGA_PANEL_EFFECT_MIN_HEIGHT)
    root.addWidget(panel.effect_edit, 1)
    # 卡密 | 卡包 随机一卡
    panel.pass_edit = line_edit()
    panel.pack_edit = line_edit()
    panel.random_btn = components.RoundedButton("随机一卡", 80, 25, parent=panel)
    root.addLayout(_manga_panel_halves(
        [label("卡密"), panel.pass_edit],
        [label("卡包"), panel.pack_edit, panel.random_btn],
    ))
    # 本地卡图 | 导出数据 导入数据
    panel.source_toggle = toggle()
    panel.source_btn = button("来源文件夹")
    panel.source_help = components.HelpButton(parent=panel)
    panel.export_data_btn = button("导出数据")
    panel.import_data_btn = button("导入数据")
    root.addLayout(_manga_panel_halves(
        [_manga_panel_even(label("本地卡图")), panel.source_toggle, (panel.source_btn, 1), panel.source_help],
        [(panel.export_data_btn, 1), (panel.import_data_btn, 1)],
    ))
    # 版权开关（漫画卡只有版权这一项）
    panel.copy_toggle = toggle()
    copy_row = _manga_panel_hbox()
    copy_row.addWidget(label("版权"))
    copy_row.addWidget(panel.copy_toggle)
    copy_row.addStretch(1)
    root.addLayout(copy_row)
    # 导出图片 | 卡包导出 | 导出设置
    panel.save_btn = button("导出图片")
    panel.batch_btn = button("卡包导出")
    panel.setting_btn = button("导出设置")
    for widget in (panel.batch_btn, panel.setting_btn):
        widget.setFixedWidth(120)
    export_row = _manga_panel_hbox()
    for widget in (panel.save_btn, panel.batch_btn, panel.setting_btn):
        export_row.addWidget(widget)
    root.addLayout(export_row)
    # 效果文字隐藏（通常版）时由它吸收多余高度，其余行保持紧凑
    panel.bottom_stretch = QWidget(panel)
    panel.bottom_stretch.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
    root.addWidget(panel.bottom_stretch, 1)

    _manga_panel_connect(app, panel, editor)
    stack.addWidget(panel)
    app._manga_panel = panel
    _manga_panel_pull(app)
    return panel


def _manga_panel_adopt_bar(panel, root, bar):
    """把 p32 的选项条（卡图 / 水印 / 日文注音 / 网点外框）改成 OCG 的半栏样式放进面板。"""
    from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

    old = bar.layout()
    captions = [w for w in (old.itemAt(i).widget() for i in range(old.count())) if isinstance(w, QLabel)]
    old_parent = bar.parentWidget()
    if old_parent is not None and old_parent.layout() is not None:
        old_parent.layout().removeWidget(bar)
    while old.count():
        old.takeAt(0)
    QWidget().setLayout(old)  # 旧布局转给临时控件，随之销毁
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(_MANGA_PANEL_SPACING)
    left = _manga_panel_hbox()
    pairs = list(zip(captions, (bar.art_selector, bar.water_selector)))
    for caption, field in pairs:
        pair = _manga_panel_hbox()
        for widget in (caption, field):
            pair.addWidget(*_manga_panel_even(widget))
        left.addLayout(pair, 1)
    right = _manga_panel_hbox()
    right.addWidget(bar.ruby_check, 1)
    right.addWidget(bar.halftone_check, 1)
    row.addLayout(left, 4)
    row.addStretch(1)
    row.addLayout(right, 4)
    bar.setParent(panel)
    root.addWidget(bar)
    bar.setVisible(True)
    for widget in captions + [bar.art_selector, bar.water_selector, bar.ruby_check, bar.halftone_check]:
        widget.setVisible(True)


def _manga_panel_adopt_detail(app, panel, combo):
    """把 p32 插在 OCG 详细行里的「通常 / 效果」下拉移出来，OCG 面板从此不含漫画卡控件。"""
    guard = getattr(app, "_manga_detail_guard", None)
    if guard is not None:
        combo.removeEventFilter(guard)
    editor = getattr(app, "otcg_widget", None)
    root = editor.layout() if editor is not None else None

    def detach(layout):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            if item is None:
                continue
            if item.widget() is combo:
                layout.takeAt(index)
                return True
            if item.layout() is not None and detach(item.layout()):
                return True
        return False

    if root is not None:
        detach(root)
    combo.setParent(panel)
    combo.setVisible(True)


def _manga_panel_connect(app, panel, editor):
    from PyQt5.QtWidgets import QLineEdit, QTextEdit

    # 输入框：按「用户亲手输入」写回（绕过 CustomLineEdit.setText，宿主才会记 has_user_type）
    for mine, theirs in _MangaPanelFields.LINE_FIELDS:
        source = getattr(editor, theirs)
        getattr(panel, mine).textEdited.connect(
            lambda text, _source=source: QLineEdit.setText(_source, text))
    panel.pass_edit.returnPressed.connect(lambda: editor.card_pass_edit.returnPressed.emit())

    def push_effect():
        if getattr(panel, "_pulling", False):
            return
        text = panel.effect_edit.toPlainText()
        if _plain_text_from(editor.text_input) != text:
            QTextEdit.setPlainText(editor.text_input, text)

    panel.effect_edit.textChanged.connect(push_effect)

    # 类型、语言：只响应用户的选择（activated），写回后宿主照常重排卡面
    panel.type_selector.activated.connect(lambda index: editor.type_selector.setCurrentIndex(index))

    def language_chosen(index):
        editor.lan_selector.setCurrentIndex(index)
        translate = globals().get("_translate_after_user_switch")
        if translate is not None:
            translate(editor)

    panel.lan_selector.activated.connect(language_chosen)

    # 开关
    for mine, theirs in _MangaPanelFields.TOGGLE_FIELDS:
        getattr(panel, mine).toggled.connect(
            lambda checked, _theirs=getattr(editor, theirs): _manga_flip_toggle(_theirs, checked))

    # 按钮：转给 OCG 编辑器上的同名按钮
    for mine, theirs in (
        ("upload_nocrop", "load_image_button_nocrop"),
        ("upload_crop", "load_image_button_crop"),
        ("random_btn", "random_btn"),
        ("source_btn", "source_btn"),
        ("source_help", "source_helper"),
        ("export_data_btn", "export_setting_btn"),
        ("import_data_btn", "import_setting_btn"),
        ("save_btn", "save_image_button"),
        ("batch_btn", "batch_btn"),
        ("setting_btn", "setting_btn"),
    ):
        target = getattr(editor, theirs, None)
        if target is not None:
            getattr(panel, mine).clicked.connect(lambda _=False, _target=target: _target.click())

    # 星星：超量点阶级，其余点等级
    def star_clicked(index):
        targets = editor.rank_star_btn_list if _manga_panel_is_rank(editor) else editor.level_star_btn_list
        if index < len(targets):
            targets[index].click()
        _manga_panel_pull(app)

    for index, star in enumerate(panel.stars):
        star.clicked.connect(lambda _=False, i=index: star_clicked(i))

    def zero_clicked():
        (editor.rank_zero_btn if _manga_panel_is_rank(editor) else editor.level_zero_btn).click()
        _manga_panel_pull(app)

    panel.level_zero.clicked.connect(zero_clicked)

    def arrow_clicked(index):
        controls = getattr(editor, "link_control_list", None) or ()
        if index < len(controls):
            controls[index].click()
        _manga_panel_pull(app)

    for index, arrow in enumerate(panel.arrows):
        arrow.clicked.connect(lambda _=False, i=index: arrow_clicked(i))


def _manga_panel_is_rank(editor):
    return str(getattr(editor, "detail_call_way", "") or "") == "超量"


def _manga_panel_pull(app):
    """把 OCG 编辑器里的卡片信息刷到本面板（切卡、查卡、撤销之后都会经过这里）。"""
    panel = getattr(app, "_manga_panel", None)
    editor = getattr(app, "otcg_widget", None)
    if panel is None or editor is None:
        return
    panel._pulling = True
    try:
        for mine, theirs in _MangaPanelFields.LINE_FIELDS:
            widget = getattr(panel, mine)
            text = _text_from(getattr(editor, theirs, None), "")
            if widget.text() != text and not widget.hasFocus():
                blocked = widget.blockSignals(True)
                widget.setText(text)
                widget.blockSignals(blocked)
        text = _plain_text_from(editor.text_input)
        if panel.effect_edit.toPlainText() != text and not panel.effect_edit.hasFocus():
            panel.effect_edit.setPlainText(text)
        for mine, theirs in _MangaPanelFields.COMBO_FIELDS:
            widget = getattr(panel, mine)
            index = getattr(editor, theirs).currentIndex()
            if widget.currentIndex() != index:
                blocked = widget.blockSignals(True)
                widget.setCurrentIndex(index)
                widget.blockSignals(blocked)
        for mine, theirs in _MangaPanelFields.TOGGLE_FIELDS:
            _manga_show_toggle(getattr(panel, mine), getattr(getattr(editor, theirs, None), "is_checked", False))
        panel.source_btn.setEnabled(editor.source_btn.isEnabled())
        _manga_panel_pull_stars(panel, editor)
    finally:
        panel._pulling = False


def _manga_panel_pull_stars(panel, editor):
    card_type = str(getattr(editor, "card_type", "") or "")
    call_way = str(getattr(editor, "detail_call_way", "") or "")
    monster = card_type == "怪兽卡"
    link = monster and call_way == "连接"
    rank = monster and call_way == "超量"
    panel.level_row.setVisible(monster and not link)
    panel.link_row.setVisible(link)
    panel.atk_row.setVisible(monster)
    if link:
        status = list(getattr(editor, "arrow_status_list", None) or ())
        for index, arrow in enumerate(panel.arrows):
            on = index < len(status) and bool(status[index])
            arrow.setInnerColor(editor.link_btn_on_color if on else editor.link_btn_off_color)
        panel.link_label.setText("LINK %d" % sum(1 for value in status if value))
        return
    if rank:
        value = int(getattr(editor, "current_rank", 0) or 0)
        on_star, on_bg, caption = editor.star_rank_color, editor.rank_bg_color, "阶级"
        count = len(editor.rank_star_btn_list)
    else:
        value = int(getattr(editor, "current_level", 0) or 0)
        on_star, on_bg, caption = editor.star_level_color, editor.level_bg_color, "等级"
        count = len(editor.level_star_btn_list)
    panel.level_label.setText("%s %d" % (caption, value))
    for index, star in enumerate(panel.stars):
        star.setVisible(index < count)
        lit = index < value
        star.setStarColor(on_star if lit else editor.star_undo_color)
        star.setCircleColor(on_bg if lit else editor.bg_undo_color)


# ---------------------------------------------------------------------------
# 接管 p32 的进入 / 离开：不再隐藏 OCG 控件，改为切到漫画卡自己的那一页
# ---------------------------------------------------------------------------
def _manga_enter(app, switch_to_ocg):
    """先按 OCG/TCG 切换（卡框、数据都回到 OCG），再把右栏和预览换成漫画卡的。"""
    switch_to_ocg(app, 0)
    panel = getattr(app, "_manga_panel", None) or _manga_panel_build(app)
    scene = _manga_ensure_scene(app)
    _manga_refresh(app, force=True)
    app.view.setScene(scene)
    app.view.fitInView(app.manga_item.boundingRect(), Qt.KeepAspectRatio)
    app.current_mode = app._manga_mode_index
    if panel is not None:
        app.stacked_widget.setCurrentWidget(panel)
        _manga_panel_pull(app)
    _manga_sync_detail_combo(app)
    app._manga_timer.start()
    _schedule_preview_update_restore(app)


def _manga_leave(app):
    timer = getattr(app, "_manga_timer", None)
    if timer is not None:
        timer.stop()


def _manga_sync_detail_combo(app):
    """版式下拉的取值仍按 p32 同步，但效果文字框换成本面板自己的（不再动 OCG 的）。"""
    in_manga = getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", -2)
    editor = getattr(app, "otcg_widget", None)
    text_input = getattr(editor, "text_input", None)
    # 看的是「是否被显式隐藏」：OCG 面板这时不在前台，isVisible() 恒为 False
    hidden = text_input.isHidden() if text_input is not None else None
    _manga_sync_detail_combo_before_panel(app)
    if text_input is not None and hidden is not None and text_input.isHidden() != hidden:
        text_input.setVisible(not hidden)  # p32 会按版式改 OCG 的效果框，这里撤销
    panel = getattr(app, "_manga_panel", None)
    if panel is None or not in_manga:
        return
    state = _manga_state(app)
    effect = (state or {}).get("layout") == "effect"
    panel.effect_edit.setVisible(effect)
    panel.bottom_stretch.setVisible(not effect)


def _manga_refresh(app, force=False):
    _manga_refresh_before_panel(app, force)
    if getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", -2):
        try:
            _manga_panel_pull(app)
        except Exception:
            _tab_log("同步漫画卡面板失败:\n" + traceback.format_exc())


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_ruby import _rd_parse_ruby
from language_switch import _translate_after_user_switch
