"""RD 卡面上的日文注音「[汉字(读音)]」：去掉标记，读音以小字画在汉字上方。

由补丁分片 p35 整理而来。
"""

import re
import traceback

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QFont, QPen, QTextCursor, QTransform

from common import _tab_log


_RD_RUBY_PATTERN = re.compile(r"\[([^\[\]()]+?)\(([^()]*?)\)\]")
# 读音字号相对正文字号（真卡效果栏约 0.42）；种族栏另有更小的比例，见下。
_RD_RUBY_SIZE_RATIO = 0.42
# 种族栏（色条高约 90px，从文本项原点上方 3px 起）：真卡上粗体正文只占色条高度
# 的四成多、位于色条中部，读音（约正文字号的三成）在它上方的空当里。
# 原字号 55px 的正文要占五成半，下移只会贴到色条底，所以有注音时：
#   - 正文缩到原字号的 _RD_DETAIL_RUBY_BASE_SCALE；
#   - 用文档上边距把正文字形中心放到文本项原点下方 _RD_DETAIL_GLYPH_CENTER_Y 像素
#     （色条中心约 42px；真卡正文中心在色条 46% 处，略高于正中）。
_RD_DETAIL_RUBY_SIZE_RATIO = 0.3
_RD_DETAIL_RUBY_BASE_SCALE = 0.8
_RD_DETAIL_GLYPH_CENTER_Y = 40.0
# CJK 字形在基线上方约 0.88em、下方约 0.12em，字形中心在基线上方 0.38em。
_RD_GLYPH_TOP_EM = 0.88
_RD_GLYPH_CENTER_EM = 0.38
# 读音比汉字宽时最多横向压到这个比例，再宽就居中溢出两侧（与真卡一致）。
_RD_RUBY_MIN_SCALE_X = 0.6


def _rd_parse_ruby(text):
    """返回 (正文, [(正文起点, 汉字长度, 读音), ...])。没有注音时列表为空。"""
    text = str(text or "")
    spans = []
    parts = []
    length = 0
    last = 0
    for match in _RD_RUBY_PATTERN.finditer(text):
        before = text[last:match.start()]
        parts.append(before)
        length += len(before)
        base, reading = match.group(1), match.group(2)
        if reading:
            spans.append((length, len(base), reading))
        parts.append(base)
        length += len(base)
        last = match.end()
    parts.append(text[last:])
    return "".join(parts), spans


def _rd_ruby_font(item):
    ratio = float(getattr(item, "_rd_ruby_ratio", _RD_RUBY_SIZE_RATIO) or _RD_RUBY_SIZE_RATIO)
    base = QFont(item.font())
    size = base.pixelSize()
    if size > 0:
        base.setPixelSize(max(1, int(round(size * ratio))))
    else:
        base.setPointSizeF(max(1.0, base.pointSizeF() * ratio))
    base.setLetterSpacing(QFont.AbsoluteSpacing, 0)
    return base


def _rd_cursor_x(line, position):
    value = line.cursorToX(position)
    return float(value[0] if isinstance(value, tuple) else value)


def _rd_ruby_signature(item):
    try:
        doc = item.document()
        size = doc.size()
        return (
            item.toPlainText(),
            tuple(getattr(item, "_rd_ruby_spans", ()) or ()),
            item.font().key(),
            float(item.textWidth()),
            int(doc.defaultTextOption().alignment()),
            float(doc.rootFrame().frameFormat().topMargin()),
            round(size.width(), 2),
            round(size.height(), 2),
            item.defaultTextColor().rgba(),
            bool(item.isVisible()),
        )
    except Exception:
        return None


def _rd_layout_ruby(item):
    from PyQt5.QtGui import QFontMetricsF
    from PyQt5.QtWidgets import QGraphicsSimpleTextItem

    spans = getattr(item, "_rd_ruby_spans", None) or ()
    children = getattr(item, "_rd_ruby_children", None)
    if children is None:
        children = item._rd_ruby_children = []
    while len(children) > len(spans):
        child = children.pop()
        try:
            child.setParentItem(None)
            scene = child.scene()
            if scene is not None:
                scene.removeItem(child)
        except Exception:
            pass
    while len(children) < len(spans):
        children.append(QGraphicsSimpleTextItem(item))
    doc = item.document()
    base_em = _rd_apply_detail_base(item, doc, bool(spans))
    item._rd_ruby_signature = _rd_ruby_signature(item)
    if not spans:
        return

    ruby_font = _rd_ruby_font(item)
    ruby_metrics = QFontMetricsF(ruby_font)
    color = item.defaultTextColor()
    for child, (start, length, reading) in zip(children, spans):
        child.setFont(ruby_font)
        child.setBrush(QBrush(color))
        child.setPen(QPen(Qt.NoPen))
        child.setText(reading)
        try:
            block = doc.findBlock(start)
            layout = block.layout()
            rel = start - block.position()
            line = layout.lineForTextPosition(rel)
            if not line.isValid():
                child.setVisible(False)
                continue
            end_rel = rel + length
            end_line = layout.lineForTextPosition(max(rel, end_rel - 1))
            if end_line.isValid() and end_line.lineNumber() != line.lineNumber():
                end_rel = line.textStart() + line.textLength()
            origin = layout.position()
            left = origin.x() + _rd_cursor_x(line, rel)
            right = origin.x() + _rd_cursor_x(line, end_rel)
            base_width = max(1.0, right - left)
            # 读音紧贴汉字字形顶端，只留 0.03em 空隙。
            baseline = origin.y() + line.y() + line.ascent()
            ruby_baseline = baseline - base_em * (_RD_GLYPH_TOP_EM + 0.03)
            reading_width = ruby_metrics.horizontalAdvance(reading)
            scale_x = 1.0
            if reading_width > base_width:
                scale_x = max(_RD_RUBY_MIN_SCALE_X, base_width / reading_width)
            shown_width = reading_width * scale_x
            child.setTransform(QTransform.fromScale(scale_x, 1.0))
            child.setPos(left + (base_width - shown_width) / 2, ruby_baseline - ruby_metrics.ascent())
            child.setVisible(True)
        except Exception:
            child.setVisible(False)


def _rd_font_em(font, metrics):
    size = font.pixelSize()
    if size > 0:
        return float(size)
    return float(metrics.ascent() + metrics.descent()) or 1.0


def _rd_set_top_margin(doc, wanted):
    frame = doc.rootFrame()
    frame_format = frame.frameFormat()
    if abs(float(frame_format.topMargin()) - wanted) < 0.01:
        return
    frame_format.setTopMargin(wanted)
    frame.setFrameFormat(frame_format)


def _rd_apply_detail_base(item, doc, has_ruby):
    """种族栏有注音时缩小正文并居中到色条；返回正文实际字号（像素）。"""
    from PyQt5.QtGui import QFontMetricsF, QTextCharFormat, QTextFormat

    font = item.font()
    em = _rd_font_em(font, QFontMetricsF(font))
    scale = float(getattr(item, "_rd_ruby_base_scale", 0) or 0)
    if not scale:
        return em
    if not has_ruby:
        _rd_set_top_margin(doc, 0.0)
        return em
    base_px = max(1, int(round(em * scale)))
    cursor = QTextCursor(doc)
    cursor.select(QTextCursor.Document)
    if cursor.charFormat().intProperty(QTextFormat.FontPixelSize) != base_px:
        char_format = QTextCharFormat()
        char_format.setProperty(QTextFormat.FontPixelSize, base_px)
        cursor.mergeCharFormat(char_format)
    _rd_set_top_margin(doc, 0.0)
    doc.size()  # 触发重新排版，下面读到的才是缩小后的行位置
    block = doc.firstBlock()
    layout = block.layout()
    line = layout.lineAt(0) if layout is not None and layout.lineCount() else None
    if line is None or not line.isValid():
        return float(base_px)
    baseline = layout.position().y() + line.y() + line.ascent()
    glyph_center = baseline - base_px * _RD_GLYPH_CENTER_EM
    _rd_set_top_margin(doc, round(max(0.0, _RD_DETAIL_GLYPH_CENTER_Y - glyph_center), 2))
    doc.size()
    return float(base_px)


def _rd_tag_detail_item(rd_widget):
    item = getattr(rd_widget, "detail_text_item", None)
    if item is None:
        return
    item._rd_ruby_ratio = _RD_DETAIL_RUBY_SIZE_RATIO
    item._rd_ruby_base_scale = _RD_DETAIL_RUBY_BASE_SCALE
    if getattr(item, "_rd_ruby_spans", None):
        _rd_layout_ruby(item)


def _set_plain_text_with_ruby(item, text, set_plain_text):
    """MixTextItem.setPlainText 的实现：去掉「[汉字(读音)]」标记再写正文，读音另行摆放。"""
    raw = str(text or "")
    plain, spans = _rd_parse_ruby(raw)
    had_ruby = bool(getattr(item, "_rd_ruby_spans", None))
    if (spans or had_ruby) and raw == getattr(item, "_rd_ruby_raw", None) and plain == item.toPlainText():
        return
    item._rd_ruby_raw = raw
    item._rd_ruby_spans = spans
    set_plain_text(plain)
    if spans or had_ruby:
        try:
            _rd_layout_ruby(item)
        except Exception:
            _tab_log("摆放RD注音失败:\n" + traceback.format_exc())


def _relayout_ruby_after_font(item):
    """MixTextItem.setFont 之后：有注音就按新字体重新摆放。"""
    if getattr(item, "_rd_ruby_spans", None):
        try:
            _rd_layout_ruby(item)
        except Exception:
            pass


def _relayout_ruby_if_stale(item):
    """MixTextItem.paint 之前：字体 / 位置变过就重新摆放注音。"""
    if getattr(item, "_rd_ruby_spans", None):
        try:
            if _rd_ruby_signature(item) != getattr(item, "_rd_ruby_signature", None):
                _rd_layout_ruby(item)
        except Exception:
            pass


def _rd_effect_fit_previous_sync_text_adjustments(rd_editor, otcg_editor):
    try:
        item = getattr(rd_editor, "detail_text_item", None)
        if item is not None and getattr(item, "_rd_ruby_ratio", None) != _RD_DETAIL_RUBY_SIZE_RATIO:
            _rd_tag_detail_item(rd_editor)
    except Exception:
        _tab_log("标记RD种族栏注音样式失败:\n" +traceback.format_exc())
    return _rd_ruby_previous_sync_text_adjustments(rd_editor, otcg_editor)


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_frame import _rd_ruby_previous_sync_text_adjustments
