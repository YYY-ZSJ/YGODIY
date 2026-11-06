# -*- coding: utf-8 -*-
"""YGODIY 内置的游戏王卡片翻译模型（推理部分）。

模型由 工具/翻译模型/build_model.py 用官方简中/日文/英文三语卡库训练得到，
是一个「基于实例的翻译模型」：

1. 整卡记忆：效果原文与某张官方卡一致 -> 直接给出那张卡的官方译文。
2. 句式模板：把卡名、数字、属性、种族等抽成槽位后，按块（一个①效果）
   -> 分句 -> 分子句（条件/代价/效果）逐级查官方句式，再把槽位填回。
3. 模糊匹配 + 修补：找最相近的官方句式，差异处用术语表替换。
4. 术语兜底：以上都失败时按术语表逐词转写。

全部是查表与字符串运算，单张卡通常在几毫秒内完成。
"""

import difflib
import gzip
import json
import os
import re
import threading
from collections import Counter, defaultdict

from . import chinese
from . import textutil as T
from .glossary import PHRASES
from runtime_paths import rpath

MODEL_PATH = rpath("ygo_translator/model/ygo_mt.json.gz")

_ZH_ACT_RE = re.compile(r"^(.*?)(才能发动|才能把这个效果发动|发动)。(.*)$", re.S)


class _FuzzyIndex(object):
    """按字二元组倒排的近似检索。"""

    def __init__(self, keys):
        self.keys = keys
        postings = defaultdict(list)
        for number, key in enumerate(keys):
            for gram in set(_bigrams(key)):
                postings[gram].append(number)
        self.postings = postings

    def search(self, query, top=6):
        # 只用最罕见的若干个二元组召回候选，常见二元组（「怪兽」「发动」）倒排表太长
        scores = Counter()
        lists = sorted(
            (hits for hits in (self.postings.get(gram) for gram in set(_bigrams(query))) if hits),
            key=len,
        )
        budget = 30000
        for hits in lists[:16]:
            if len(hits) > budget:
                break
            budget -= len(hits)
            for number in hits:
                scores[number] += 1
        if not scores:
            return []
        shortlist = [number for number, _count in scores.most_common(40)]
        ranked = []
        for number in shortlist:
            key = self.keys[number]
            ratio = difflib.SequenceMatcher(None, key, query, autojunk=False).ratio()
            ranked.append((ratio, number))
        ranked.sort(reverse=True)
        return [(ratio, self.keys[number]) for ratio, number in ranked[:top]]


def _bigrams(text):
    return [text[index : index + 2] for index in range(len(text) - 1)] or [text]


def build_table(records, src, tgt):
    """句式记录 -> {源模板: 目标模板}，同一源模板取票数最多的译法。"""
    col = T.LANGS.index
    votes = defaultdict(Counter)
    for record in records:
        source, target, count = record[col(src)], record[col(tgt)], record[3]
        if not source or not target:
            continue
        renumbered, mapping = T.renumber(source)
        if any(T.is_slot(char) and char not in mapping and T.slot_info(char)[0] != "S" for char in target):
            continue
        remapped = "".join(mapping.get(char, char) for char in target)
        votes[renumbered][remapped] += count
    return {source: counter.most_common(1)[0][0] for source, counter in votes.items()}


class Model(object):
    def __init__(self, path=MODEL_PATH):
        with gzip.open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
        self.version = data.get("version")
        self.cards = data["cards"]
        self.records = data["records"]
        self.holdout = set(data.get("holdout") or ())
        self._lock = threading.RLock()
        self._indices = {}
        self._fuzzy = {}
        self._build_memory(data.get("series") or ())
        self._learned_rules = data.get("rules") or {}
        self._learned_phrases = data.get("phrases") or {}
        self._repair_tables = {}

    # ------------------------------------------------------------ 记忆与词典

    def _build_memory(self, series):
        col = {"zh": 0, "ja": 1, "en": 2}
        self.text_memory = {(lang, part): {} for lang in T.LANGS for part in (0, 1)}
        self.names = {(a, b): {} for a in T.LANGS for b in T.LANGS if a != b}
        self.ruby = {}
        for row in self.cards:
            card_names = row[1:4]
            for lang in T.LANGS:
                main_text, pend = row[5 + col[lang] * 2], row[6 + col[lang] * 2]
                if main_text:
                    self.text_memory[(lang, 0)].setdefault(T.norm_key(main_text), row)
                if pend:
                    self.text_memory[(lang, 1)].setdefault(T.norm_key(pend), row)
            self._add_names(card_names)
            if row[2] and row[4]:
                self.ruby.setdefault(row[2], row[4])
        for triple in series:
            self._add_names(triple)

    def _add_names(self, triple):
        for a, name_a in zip(T.LANGS, triple):
            if not name_a:
                continue
            for b, name_b in zip(T.LANGS, triple):
                if b != a and name_b:
                    self.names[(a, b)].setdefault(name_a, name_b)

    def card_memory(self, text, src, tgt, part):
        row = self.text_memory[(src, part)].get(T.norm_key(text))
        if row is None:
            return None
        translated = row[5 + T.LANGS.index(tgt) * 2 + part]
        return translated or None

    def name_memory(self, name, src, tgt):
        return self.names[(src, tgt)].get(name)

    # ------------------------------------------------------------ 句式索引

    def index(self, kind, src, tgt):
        key = (kind, src, tgt)
        with self._lock:
            if key in self._indices:
                return self._indices[key]
            table = build_table(self.records.get(kind, ()), src, tgt)
            self._indices[key] = table
            return table

    def fuzzy(self, kinds, src, tgt):
        key = (kinds, src, tgt)
        with self._lock:
            if key not in self._fuzzy:
                merged = {}
                for kind in kinds:
                    for source, target in self.index(kind, src, tgt).items():
                        merged.setdefault(source, target)
                self._fuzzy[key] = (_FuzzyIndex(list(merged)), merged)
            return self._fuzzy[key]

    def repair_tables(self, src, tgt):
        """修补用的 (替换规则, 短语表, 按长度排序的短语)。

        规则与短语从官方语料的「最小差异句对」学得（只有 简中 -> 日文/英文 方向），
        手写术语表补在后面。"""
        key = (src, tgt)
        with self._lock:
            if key in self._repair_tables:
                return self._repair_tables[key]
            col = T.LANGS.index
            rules = {}
            glossary = {}
            for row in PHRASES:
                if "{" in row[col(src)] or "{" in row[col(tgt)]:
                    continue
                glossary.setdefault(row[col(src)], row[col(tgt)])
            phrases = dict(glossary)
            if src == "zh":
                for old, new, old_t, new_t, _count in self._learned_rules.get(tgt, ()):
                    rules.setdefault((old, new), (old_t, new_t))
                for source, target, _count in self._learned_phrases.get(tgt, ()):
                    phrases.setdefault(source, target)
            ordered = sorted(glossary, key=len, reverse=True)
            self._repair_tables[key] = (rules, phrases, glossary, ordered)
            return self._repair_tables[key]


_MODEL = None
_MODEL_LOCK = threading.Lock()


def get_model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is None:
            _MODEL = Model()
        return _MODEL


def model_available():
    return os.path.exists(MODEL_PATH)


# ---------------------------------------------------------------- 翻译器

class Translator(object):
    """一次翻译（一张卡）的上下文：源/目标语言、卡名、卡片种类。"""

    def __init__(self, model, src, tgt, self_src="", self_tgt="", is_monster=True):
        self.model = model
        self.src = src
        self.tgt = tgt
        self.self_src = self_src
        self.self_tgt = self_tgt
        self.is_monster = is_monster
        self.self_names = {self_src} if self_src else set()

    # ------------------------------------------------------------ 槽位

    def name(self, name):
        return translate_name(self.model, name, self.src, self.tgt)

    def fill(self, template, slots):
        out = []
        for char in template:
            if not T.is_slot(char):
                out.append(char)
                continue
            kind, number = T.slot_info(char)
            if kind == "S":
                out.append(self.self_tgt or (self.name(slots.values["S"][0]) if slots.values["S"] else ""))
                continue
            values = slots.values[kind]
            if number >= len(values):
                return None
            value = values[number]
            if kind == "N":
                out.append(self.name(value))
            elif kind == "D":
                out.append(T.to_full_digits(value) if self.tgt == "ja" else value)
            else:
                out.append(T.TERM_OUTPUT[self.tgt][(kind, value)])
        return "".join(out)

    def lookup(self, kinds, text):
        """精确查句式：先查「数字照抄」的，再查「数字作槽」的。"""
        for numbers in (False, True):
            key, slots = T.delex(text, self.src, self.self_names, numbers)
            for kind in kinds:
                template = self.model.index(kind, self.src, self.tgt).get(key)
                if template is not None:
                    result = self.fill(template, slots)
                    if result is not None and _numbers_consistent(text, result):
                        return result
        return None

    def approximate(self, kinds, text, threshold=0.6):
        """近似匹配官方句式，差异部分用学到的替换规则/短语表修补；
        有一处修补不了就放弃这个候选（宁可不译，也不给出意思不对的句子）。"""
        key, slots = T.delex(text, self.src, self.self_names, True)
        index, table = self.model.fuzzy(tuple(kinds), self.src, self.tgt)
        tables = self.model.repair_tables(self.src, self.tgt)
        for ratio, candidate in index.search(key):
            if ratio < threshold:
                break
            repaired = _repair(candidate, table[candidate], key, tables)
            if repaired is not None:
                result = self.fill(repaired, slots)
                if result is not None and _numbers_consistent(text, result):
                    return result
        return None

    def gloss(self, text):
        """兜底：术语表逐词转写。"""
        key, slots = T.delex(text, self.src, self.self_names, True)
        _rules, _phrases, phrases, ordered = self.model.repair_tables(self.src, self.tgt)
        out = []
        index = 0
        while index < len(key):
            char = key[index]
            if T.is_slot(char):
                out.append(char)
                index += 1
                continue
            for phrase in ordered:
                if key.startswith(phrase, index):
                    out.append(phrases[phrase])
                    index += len(phrase)
                    break
            else:
                out.append(char)
                index += 1
        if self.tgt == "en":
            return text
        joined = "".join(out)
        if self.tgt == "ja" and self.src == "zh":
            joined = chinese.to_japanese_kanji(joined)
        if self.tgt == "zh" and self.src == "en":
            joined = joined.replace(". ", "。").replace(", ", "，")
        result = self.fill(joined, slots)
        return result if result is not None else text

    # ------------------------------------------------------------ 分级翻译

    def sentence(self, text):
        kinds = ("S", "E", "B") if self.tgt == "en" else ("S", "B")
        if self.src == "zh" and self.tgt == "ja":
            kinds = ("S", "B", "Q")
        result = self.lookup(kinds, text)
        if result is None:
            result = self.approximate(kinds, text)
        if result is None and self.src == "zh" and self.tgt == "ja":
            result = self.clauses_ja(text)
        if result is None:
            result = self.gloss(text)
        return result

    def clauses_ja(self, text):
        body = text[:-1] if text.endswith("。") else text
        inside = T.quote_depth_map(body, "zh")
        pieces, start = [], 0
        for index, char in enumerate(body):
            if char == "，" and not inside[index]:
                pieces.append(body[start:index])
                start = index + 1
        pieces.append(body[start:])
        if len(pieces) < 2:
            return None
        out = []
        for piece in pieces:
            translated = self.lookup(("Q", "S"), piece)
            if translated is None:
                translated = self.approximate(("Q",), piece)
            if translated is None:
                return None
            out.append(translated.rstrip("。"))
        return "、".join(out) + ("。" if text.endswith("。") else "")

    def block(self, body, sentences):
        result = self.lookup(("B",), body)
        if result is not None:
            return result
        if self.src == "zh" and self.tgt == "en":
            result = self.parts_en(body)
            if result is not None:
                return result
        result = self.approximate(("B",), body, threshold=0.75)
        if result is not None:
            return result
        joiner = " " if self.tgt == "en" else ""
        return joiner.join(self.sentence(sentence) for sentence in sentences)

    def parts_en(self, body):
        match = _ZH_ACT_RE.match(body)
        if not match:
            return None
        head, verb, rest = match.group(1), match.group(2), match.group(3).strip()
        optional = verb != "发动"
        cond = cost = None
        if head:
            cond = self.lookup(("C",), head)
            if cond is None and "，" in head:
                left, right = head.rsplit("，", 1)
                cond_left = self.lookup(("C",), left) or self.approximate(("C",), left)
                cost_right = self.lookup(("K",), right) or self.approximate(("K",), right)
                if cond_left and cost_right:
                    cond, cost = cond_left, cost_right
            if cond is None and cost is None:
                cost = self.lookup(("K",), head)
            if cond is None and cost is None:
                cond = self.approximate(("C",), head)
            if cond is None and cost is None:
                cost = self.approximate(("K",), head)
            if cond is None and cost is None:
                return None
        effect = ""
        if rest:
            effect = self.lookup(("E", "S"), rest)
            if effect is None:
                effect = " ".join(self.sentence(sentence) for sentence in T.split_sentences(rest, "zh"))
        if not effect and not cost:
            return None
        lead = optional and self.is_monster
        out = cond + ": " if cond else ""
        if cost:
            out += ("You can " + _lower_first(cost)) if lead else _upper_first(cost)
            out += ("; " + _lower_first(effect)) if effect else "."
        else:
            out += ("You can " + _lower_first(effect)) if lead else _upper_first(effect)
        return out.strip()

    # ------------------------------------------------------------ 整段

    def text(self, text, part=0):
        if not text or not text.strip():
            return text
        memory = self.model.card_memory(text, self.src, self.tgt, part)
        if memory:
            return memory
        blocks = T.split_blocks(text, self.src)
        rendered = []
        for block in blocks:
            if not block.sentences:
                continue
            body = self.block(block.body, block.sentences)
            marker = block.marker
            if self.tgt == "en" and isinstance(marker, int):
                marker = None  # TCG 文本不给效果编号
            rendered.append((block, T.marker_text(marker, self.tgt) + body))
        if self.tgt == "en" and self.src != "en":
            head = [item for item in rendered if T.is_restriction(item[0], self.src)]
            rest = [item for item in rendered if not T.is_restriction(item[0], self.src)]
            rendered = rest + head
            return _join_en(rendered)
        if self.src == "en" and self.tgt != "en":
            head = [item for item in rendered if T.is_restriction(item[0], "en")]
            rest = [item for item in rendered if not T.is_restriction(item[0], "en")]
            rendered = head + rest
        return "\n".join(body for _block, body in rendered)


def _join_en(rendered):
    lines = []
    paragraph = []
    for block, body in rendered:
        material = "。" not in "".join(block.sentences) and "＋" in block.body
        if block.marker == "B" or material:
            if paragraph:
                lines.append(" ".join(paragraph))
                paragraph = []
            lines.append(body)
        else:
            paragraph.append(body)
    if paragraph:
        lines.append(" ".join(paragraph))
    return "\n".join(lines)


_DIGITS_RE = re.compile(r"\d+")


def _numbers_consistent(source, result):
    """译文里出现的数字必须都在原文里出现过。

    训练数据偶有切分错位的句对，会把别的子句（如「Tribute 2 Tokens」）带进模板；
    这类模板的特征就是凭空多出数字，直接拒用。"""
    allowed = {str(int(n)) for n in _DIGITS_RE.findall(T.to_half_digits(source))}
    found = {str(int(n)) for n in _DIGITS_RE.findall(T.to_half_digits(T.strip_ruby(result)))}
    return found <= allowed


def _lower_first(text):
    if not text:
        return text
    first = text.split(" ", 1)[0]
    if first in ("Special", "Normal", "Tribute", "Set", "Fusion", "Synchro", "Xyz", "Link", "Ritual", "Pendulum", "Flip"):
        return text
    return text[0].lower() + text[1:]


def _upper_first(text):
    return text[:1].upper() + text[1:] if text else text


def _contexts(i1, i2, size, widest=4):
    """差异区间向两边各扩 0~widest 个字，按扩展总长从小到大。"""
    for total in range(0, widest * 2 + 1):
        for left in range(0, min(widest, total) + 1):
            right = total - left
            if right <= widest and i1 - left >= 0 and i2 + right <= size:
                yield i1 - left, i2 + right


def _repair(candidate, target, query, tables):
    rules, phrases, _glossary, _ordered = tables
    matcher = difflib.SequenceMatcher(None, candidate, query, autojunk=False)
    result = target
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if any(T.is_slot(char) for char in candidate[i1:i2] + query[j1:j2]):
            return None
        fixed = False
        for start, end in _contexts(i1, i2, len(candidate)):
            left, right = candidate[start:i1], candidate[i2:end]
            if i1 == i2 and not left and not right:
                continue
            if query[max(0, j1 - len(left)) : j1] != left or query[j2 : j2 + len(right)] != right:
                continue
            old = candidate[start:end]
            new = left + query[j1:j2] + right
            rule = rules.get((old, new))
            if rule and rule[0] in result:
                result = result.replace(rule[0], rule[1], 1)
                fixed = True
                break
            old_t, new_t = phrases.get(old), phrases.get(new)
            if old_t and new_t and old_t in result:
                result = result.replace(old_t, new_t, 1)
                fixed = True
                break
        if not fixed:
            return None
    return result


# ---------------------------------------------------------------- 卡名

_NAME_PARTS = {}


def _name_parts(model, src, tgt):
    key = (src, tgt)
    if key not in _NAME_PARTS:
        table = {name: value for name, value in model.names[(src, tgt)].items() if len(name) >= 2}
        _NAME_PARTS[key] = (table, sorted(table, key=len, reverse=True)[:40000])
    return _NAME_PARTS[key]


def translate_name(model, name, src, tgt):
    if not name or src == tgt:
        return name
    hit = model.name_memory(name, src, tgt)
    if hit:
        return hit
    table, ordered = _name_parts(model, src, tgt)
    out = []
    index = 0
    by_first = defaultdict(list)
    for part in ordered:
        if part[0] in name:
            by_first[part[0]].append(part)
    while index < len(name):
        for part in by_first.get(name[index], ()):
            if name.startswith(part, index):
                out.append(("hit", table[part]))
                index += len(part)
                break
        else:
            out.append(("raw", name[index]))
            index += 1
    pieces = []
    for kind, value in out:
        if kind == "raw" and pieces and pieces[-1][0] == "raw":
            pieces[-1] = ("raw", pieces[-1][1] + value)
        else:
            pieces.append((kind, value))
    if tgt == "en":
        return " ".join(value.strip() for _kind, value in pieces if value.strip())
    if tgt == "ja" and src == "zh":
        return "".join(chinese.to_japanese_kanji(value) if kind == "raw" else value for kind, value in pieces).replace("·", "・")
    return "".join(value for _kind, value in pieces)
