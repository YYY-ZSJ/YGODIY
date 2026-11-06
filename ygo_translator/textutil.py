# -*- coding: utf-8 -*-
"""文本切分与去词汇化（训练与翻译共用，保证两边切法完全一致）。

去词汇化：把卡名「…」、数字、属性/种族/召唤种类等术语换成占位符（槽位），
得到的模板只保留句式本身，例如
    把1只「黑魔术师」从卡组加入手卡。
 -> 把<D0>只「<N0>」从<ZONE0>加入<ZONE1>。
槽位用私用区字符表示，一个槽位就是一个字符，方便做编辑距离。
"""

import re

from .glossary import JA_ALIASES, TERM_CLASSES

LANGS = ("zh", "ja", "en")

SLOT_BASE = 0xE000
SLOT_TYPES = ("N", "D", "S") + tuple(TERM_CLASSES)
_TYPE_CODE = {name: index for index, name in enumerate(SLOT_TYPES)}
_SLOT_END = SLOT_BASE + 64 * len(SLOT_TYPES)


def slot_char(kind, index):
    return chr(SLOT_BASE + _TYPE_CODE[kind] * 64 + index)


def slot_info(char):
    value = ord(char) - SLOT_BASE
    return SLOT_TYPES[value // 64], value % 64


def is_slot(char):
    return SLOT_BASE <= ord(char) < _SLOT_END


_FULL_DIGITS = str.maketrans("0123456789", "０１２３４５６７８９")
_HALF_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def to_full_digits(text):
    return text.translate(_FULL_DIGITS)


def to_half_digits(text):
    return text.translate(_HALF_DIGITS)


# ---------------------------------------------------------------- 术语索引

TERM_SURFACE = {lang: {} for lang in LANGS}  # 表层写法 -> (类别, 简中规范词)
TERM_OUTPUT = {lang: {} for lang in LANGS}  # (类别, 简中规范词) -> 输出写法
for _cls, _rows in TERM_CLASSES.items():
    for _row in _rows:
        _key = (_cls, _row[0])
        for _lang, _surface in zip(LANGS, _row):
            TERM_SURFACE[_lang][_surface] = _key
            TERM_OUTPUT[_lang][_key] = _surface
for _alias, _canon in JA_ALIASES.items():
    TERM_SURFACE["ja"][_alias] = TERM_SURFACE["ja"][_canon]


def _term_pattern(lang):
    words = sorted(TERM_SURFACE[lang], key=len, reverse=True)
    body = "|".join(re.escape(word) for word in words)
    if lang == "en":
        return r"(?<![A-Za-z\-])(?:%s)(?![A-Za-z])" % body
    return "(?:%s)" % body


_LITERAL_RE = {
    lang: re.compile(r"(?P<term>%s)|(?P<num>\d+)" % _term_pattern(lang)) for lang in LANGS
}
_LITERAL_NO_NUM_RE = {lang: re.compile(r"(?P<term>%s)" % _term_pattern(lang)) for lang in LANGS}

# ---------------------------------------------------------------- 日文注音

RUBY_RE = re.compile(r"\[([^\[\]()（）]*?)[(（]([^()（）]*?)[)）]\]")


def strip_ruby(text):
    return RUBY_RE.sub(lambda match: match.group(1), text or "")


# ---------------------------------------------------------------- 卡名引号

def quoted_spans(text, lang):
    """返回卡名引号内文本的 (起, 止) 区间（不含引号本身）。"""
    spans = []
    if lang == "en":
        for match in re.finditer(r'"([^"\n]+)"', text):
            spans.append((match.start(1), match.end(1)))
        return spans
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "「":
            if depth == 0:
                start = index + 1
            depth += 1
        elif char == "」" and depth > 0:
            depth -= 1
            if depth == 0:
                spans.append((start, index))
    return spans


def quote_depth_map(text, lang):
    """每个位置是否在卡名引号内。"""
    inside = [False] * len(text)
    for start, end in quoted_spans(text, lang):
        for index in range(start - 1, min(end + 1, len(text))):
            inside[index] = True
    return inside


# ---------------------------------------------------------------- 去词汇化

class Slots(object):
    """一段文本里各类槽位的取值（同值同号，按首次出现编号）。"""

    __slots__ = ("values",)

    def __init__(self):
        self.values = {kind: [] for kind in SLOT_TYPES}

    def add(self, kind, value):
        bucket = self.values[kind]
        if value not in bucket:
            if len(bucket) >= 63:
                return None
            bucket.append(value)
        return slot_char(kind, bucket.index(value))


def delex(text, lang, self_names=(), numbers=True):
    """文本 -> (模板, Slots)。self_names 中的卡名记为「自身」槽位 S。"""
    slots = Slots()
    out = []
    pattern = (_LITERAL_RE if numbers else _LITERAL_NO_NUM_RE)[lang]

    def literal(segment):
        position = 0
        for match in pattern.finditer(segment):
            out.append(segment[position : match.start()])
            if match.group("term") is not None:
                key = TERM_SURFACE[lang][match.group("term")]
                char = slots.add(key[0], key[1])
            else:
                char = slots.add("D", str(int(to_half_digits(match.group("num")))))
            out.append(char if char else match.group(0))
            position = match.end()
        out.append(segment[position:])

    position = 0
    for start, end in quoted_spans(text, lang):
        literal(text[position:start])
        name = text[start:end]
        if name in self_names:
            char = slots.add("S", name)
        else:
            char = slots.add("N", name)
        out.append(char if char else name)
        position = end
    literal(text[position:])
    return "".join(out), slots


def template_slots(template):
    return [char for char in template if is_slot(char)]


def renumber(template):
    """把模板里的槽位按首次出现重新编号，返回 (新模板, 旧槽字符->新槽字符)。"""
    mapping = {}
    counters = {}
    out = []
    for char in template:
        if is_slot(char):
            if char not in mapping:
                kind, _index = slot_info(char)
                number = counters.get(kind, 0)
                counters[kind] = number + 1
                mapping[char] = slot_char(kind, number)
            out.append(mapping[char])
        else:
            out.append(char)
    return "".join(out), mapping


# ---------------------------------------------------------------- 分块与分句

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_ZJ_MARKER_RE = re.compile(r"([①-⑳])\s*[：:]\s*|●\s*")
_EN_MARKER_RE = re.compile(r"\((\d{1,2})\)\s*:\s*|●\s*")


class Block(object):
    """一个效果块：编号（int / "B" 表示「●」/ None）+ 若干句。"""

    __slots__ = ("marker", "sentences", "newline")

    def __init__(self, marker, newline):
        self.marker = marker
        self.sentences = []
        self.newline = newline

    @property
    def body(self):
        return "".join(self.sentences) if self.sentences else ""

    def __repr__(self):
        return "Block(%r, %r)" % (self.marker, self.sentences)


def _split_sentences_zj(text):
    sentences = []
    inside = quote_depth_map(text, "zh")
    start = 0
    for index, char in enumerate(text):
        if char == "。" and not inside[index]:
            sentences.append(text[start : index + 1])
            start = index + 1
    tail = text[start:]
    if tail.strip():
        sentences.append(tail)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


_EN_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"(●])')


def _split_sentences_en(text):
    inside = quote_depth_map(text, "en")
    sentences = []
    start = 0
    for match in _EN_SENT_RE.finditer(text):
        if inside[match.start() - 1]:
            continue
        sentences.append(text[start : match.start()])
        start = match.end()
    tail = text[start:]
    if tail.strip():
        sentences.append(tail)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def split_sentences(text, lang):
    if lang == "en":
        return _split_sentences_en(text)
    return _split_sentences_zj(text)


def split_blocks(text, lang):
    """把效果文本切成块。换行与编号都会开始新块。"""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    marker_re = _EN_MARKER_RE if lang == "en" else _ZJ_MARKER_RE
    blocks = []
    for line_number, line in enumerate(text.split("\n")):
        if not line.strip():
            continue
        inside = quote_depth_map(line, lang)
        cuts = []
        for match in marker_re.finditer(line):
            if inside[match.start()]:
                continue
            if lang == "en" and match.group(1) and match.start() > 0:
                # 英文编号只认句首
                before = line[: match.start()].rstrip()
                if before and before[-1] not in ".:":
                    continue
            cuts.append(match)
        pieces = []
        position = 0
        marker = None
        for match in cuts:
            pieces.append((marker, line[position : match.start()]))
            if match.group(1):
                marker = int(match.group(1)) if lang == "en" else CIRCLED.index(match.group(1)) + 1
            else:
                marker = "B"
            position = match.end()
        pieces.append((marker, line[position:]))
        first = True
        for marker, body in pieces:
            if not body.strip() and marker is None:
                continue
            block = Block(marker, newline=first and line_number > 0 and bool(blocks))
            block.sentences = split_sentences(body.strip(), lang)
            blocks.append(block)
            first = False
    return blocks


def marker_text(marker, lang):
    if marker is None:
        return ""
    if marker == "B":
        return "● " if lang == "en" else "●"
    if lang == "en":
        return "(%d): " % marker
    return CIRCLED[marker - 1] + "："


_ZH_RESTRICT_RE = re.compile(r"回合.{0,8}(只能|各能|才能|仅能)|1回合只能|只能有1次")
_JA_RESTRICT_RE = re.compile(r"しか(使用|発動|特殊召喚|適用)|ターンに.{0,6}(度|回)しか")


def is_restriction(block, lang):
    if block.marker is not None:
        return False
    body = block.body
    if lang == "en":
        return body.startswith("You can only") or body.startswith("You cannot")
    if lang == "ja":
        return bool(_JA_RESTRICT_RE.search(body)) and "カード名" in body or body.startswith("このカード名")
    return body.startswith("这个卡名") or bool(_ZH_RESTRICT_RE.search(body)) and "卡名" in body


# ---------------------------------------------------------------- 灵摆文本拆分（训练数据用）

def split_pendulum(desc, lang):
    """数据库原文 -> (灵摆效果, 怪兽效果)。不是灵摆卡则灵摆部分为空。"""
    desc = (desc or "").replace("\r\n", "\n")
    if lang == "zh":
        match = re.match(r"^\s*←\d+ 【灵摆】 \d+→\n(.*?)\n?【怪兽(?:效果|描述)】\n(.*)$", desc, re.S)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    elif lang == "ja":
        match = re.match(r"^\s*【Ｐスケール：[^】]*】\n(.*?)\n?【(?:モンスター効果|フレーバーテキスト)】\n(.*)$", desc, re.S)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    else:
        match = re.match(
            r"^(?:Pendulum Scale = \d+\n)?\[ Pendulum Effect \]\n(.*?)\n-{10,}\n\[ (?:Monster Effect|Flavor Text) \]\n(.*)$",
            desc,
            re.S,
        )
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return "", desc.strip()


def norm_key(text):
    """整卡记忆的查表键：去掉空白与注音。"""
    return re.sub(r"\s+", "", strip_ruby(text or ""))
