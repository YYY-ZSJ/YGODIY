# -*- coding: utf-8 -*-
"""简繁转换与「中文汉字 -> 日文新字体」转换。

直接读程序自带的 OpenCC 字典（提取文件/_internal/opencc/dictionary），
最长匹配替换，不依赖 opencc 包本身。
"""

import os
import threading
import opencc

_HERE = os.path.dirname(os.path.abspath(__file__))
_DICT_DIRS = (
    os.path.join(os.path.dirname(opencc.__file__), "dictionary"),
    os.path.join(os.path.dirname(_HERE), "_internal", "opencc", "dictionary"),
    os.path.join(_HERE, "opencc"),
)

_TABLES = {}
_LOCK = threading.Lock()

_SPECS = {
    "s2t": ("STPhrases.txt", "STCharacters.txt"),
    "t2tw": ("TWVariants.txt",),
    "t2s": ("TSPhrases.txt", "TSCharacters.txt"),
    "t2jp": ("JPVariants.txt",),
}


def _dict_path(name):
    for folder in _DICT_DIRS:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    return None


def _load(kind):
    with _LOCK:
        if kind in _TABLES:
            return _TABLES[kind]
        table = {}
        for name in _SPECS[kind]:
            path = _dict_path(name)
            if not path:
                continue
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 2 and parts[0] not in table:
                        table[parts[0]] = parts[1].split(" ")[0]
        longest = max((len(key) for key in table), default=1)
        _TABLES[kind] = (table, longest)
        return _TABLES[kind]


def _convert(text, kind):
    table, longest = _load(kind)
    if not table or not text:
        return text
    out = []
    index = 0
    length = len(text)
    while index < length:
        for size in range(min(longest, length - index), 0, -1):
            piece = text[index : index + size]
            hit = table.get(piece)
            if hit is not None:
                out.append(hit)
                index += size
                break
        else:
            out.append(text[index])
            index += 1
    return "".join(out)


def to_traditional(text):
    # 简 -> 繁，再按台湾通行字形（爲 -> 為 等）
    return _convert(_convert(text, "s2t"), "t2tw")


def to_simplified(text):
    return _convert(text, "t2s")


def to_japanese_kanji(text):
    """简体汉字 -> 日文写法（先转繁体再转日文新字体）。假名、标点不受影响。"""
    return _convert(_convert(text, "s2t"), "t2jp")
