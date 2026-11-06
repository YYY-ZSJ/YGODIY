# -*- coding: utf-8 -*-
"""YGODIY 内置游戏王卡片翻译模型。

对外接口：
    translate_card(name, text, pend_text, src_language, tgt_language, is_monster=True)
        -> (name, text, pend_text)
    src/tgt_language 用 YGODIY 语言下拉的文字：简体中文 / 繁体中文 / 繁体中文2 /
    日文 / 日文注音 / 英文。
    warm_up()  在后台预先载入模型，首次切换语言不卡顿。
"""

import os
import re
import threading
import traceback

from . import chinese
from . import textutil as T
from .furigana import add_furigana
from . import neural
from .translator import Translator, get_model, model_available
from .translator import _numbers_consistent as numbers_consistent

LANGUAGE_CODES = {
    "简体中文": "zh",
    "简体中文2": "zh",
    "繁体中文": "zh-hant",
    "繁体中文2": "zh-hant",
    "日文": "ja",
    "日文注音": "ja",
    "英文": "en",
}


def language_code(language):
    return LANGUAGE_CODES.get(str(language or "").strip())


def _uses_ruby(language):
    return str(language or "").startswith("日文")


def _to_base(text, code):
    """把输入整理成模型使用的三种基础语言之一。"""
    if code == "zh-hant":
        return chinese.to_simplified(text), "zh"
    if code == "ja":
        return T.strip_ruby(text), "ja"
    return text, code


def _name_reading():
    try:
        return get_model().ruby.get if model_available() else None
    except Exception:
        return None


def _from_base(text, code, language, names=()):
    if not text:
        return text
    if code == "zh-hant":
        return chinese.to_traditional(text)
    if code == "ja" and _uses_ruby(language):
        return add_furigana(text, names, _name_reading())
    return text


# 设为 False 则只用实例翻译模型（不加载神经模型）
USE_NEURAL = True


def _neural(text, src, tgt, kind):
    if not USE_NEURAL or not neural.available():
        return None
    try:
        output = neural.translate(text, src, tgt, kind)
    except Exception:
        _log_failure("神经模型翻译出错", traceback.format_exc())
        return None
    if output is None:
        _log_failure("神经模型未给出可用译文", "%s->%s %r (%s)" % (src, tgt, text[:40], neural.last_reason()))
    return output


def _log_failure(title, detail):
    """写到程序目录的 制卡器标签页.log（与补丁包的日志同一个文件）。"""
    try:
        import time

        from runtime_paths import app_dir

        root = app_dir()
        with open(os.path.join(root, "制卡器标签页.log"), "a", encoding="utf-8") as handle:
            handle.write("[%s] [翻译] %s: %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), title, detail))
    except Exception:
        pass


def _translate_body(model, translator, text, src, tgt, part):
    """效果文本：官方原文记忆 -> 神经模型 -> 实例翻译模型。"""
    if not text or not text.strip():
        return text
    official = model.card_memory(text, src, tgt, part)
    if official:
        return official
    output = _neural(text, src, tgt, "pend" if part else "text")
    if output and numbers_consistent(text, output):
        output = _drop_invented_restriction(output, text, src, tgt)
        output = _add_you_can(output, text, src, tgt, translator.is_monster)
        return _fix_self_name(model, output, text, src, tgt, translator.self_tgt)
    return translator.text(text, part)


# 原文里的「1 回合只能/各能…」类限制
_ZH_RESTRICTION_RE = re.compile(r"回合.{0,12}(只能|各能|才能)|决斗中只能|1回合只有1次")
_INVENTED_RESTRICTION = {
    "en": re.compile(r"\s*You can only (?:use|activate|apply|Special Summon)[^.]*?(?:per turn|per Duel|once)[^.]*\."),
    "ja": re.compile(r"[^。\n]*(?:ターン|デュエル中)[^。\n]*しか[^。\n]*できない。\n?"),
}


def _drop_invented_restriction(output, source, src, tgt):
    """小模型偶尔会给没有使用次数限制的效果补上一句「1 回合只能使用 1 次」，还编一个卡名。
    原文没有限制句时，译文里的限制句一律删掉。"""
    pattern = _INVENTED_RESTRICTION.get(tgt)
    if src != "zh" or pattern is None or _ZH_RESTRICTION_RE.search(source):
        return output
    return pattern.sub("", output).strip()


# 英文代价/对象子句开头的动词（「You can」之后除 Tribute 外都小写）
_EN_COST_START_RE = re.compile(
    r"(^|\n|: |\. )(Target|Discard|Banish|Send|Pay|Detach|Reveal|Shuffle|Return|Tribute)\b(?=[^.\n]*;)")


def _add_you_can(output, source, src, tgt, is_monster):
    """怪兽的「…才能发动」是可选效果，英文要写成「You can …;」。小模型不知道这是怪兽卡还是
    魔法陷阱卡（魔陷不写 You can），有时会漏掉。只补在「代价/对象; 效果」这种子句开头。"""
    if tgt != "en" or src != "zh" or not is_monster or "才能" not in source:
        return output

    def replace(match):
        verb = match.group(2)
        return "%sYou can %s" % (match.group(1), verb if verb == "Tribute" else verb.lower())

    return _EN_COST_START_RE.sub(replace, output)


_EN_SELF_RE = re.compile(r'((?:effects? of|preceding effects of|activate (?:only )?1)\s+)"([^"]+)"')


def _fix_self_name(model, output, source, src, tgt, card_name):
    """英文「You can only use this effect of "卡名" once per turn.」里的卡名：
    神经模型看不到本卡卡名，会自己编一个。原文里没有出现过的引号卡名一律换成本卡卡名。"""
    if tgt != "en" or not card_name:
        return output
    expected = set()
    for start, end in T.quoted_spans(source, src):
        name = source[start:end]
        expected.add(model.name_memory(name, src, tgt) or name)

    def replace(match):
        if match.group(2) in expected:
            return match.group(0)
        return '%s"%s"' % (match.group(1), card_name)

    return _EN_SELF_RE.sub(replace, output)


def translate_card(name, text, pend_text, src_language, tgt_language, is_monster=True):
    """翻译一张卡的卡名、效果、灵摆效果。无法翻译时原样返回。"""
    src_code = language_code(src_language)
    tgt_code = language_code(tgt_language)
    if not src_code or not tgt_code or src_language == tgt_language:
        return name, text, pend_text
    if src_code == tgt_code:
        # 日文 <-> 日文注音、繁体中文 <-> 繁体中文2：只调整注音
        if src_code == "ja":
            plain = [T.strip_ruby(value) for value in (name, text, pend_text)]
            return tuple(_from_base(value, "ja", tgt_language) for value in plain)
        return name, text, pend_text

    # 卡名不翻译，原样保留（只在目标不是日文时去掉日文注音标记，宿主其它语言排不了注音）
    out_name = (name or "") if tgt_code == "ja" else T.strip_ruby(name or "")
    plain_name = T.strip_ruby(name or "").strip()
    src_text, src = _to_base(text or "", src_code)
    src_pend, _src = _to_base(pend_text or "", src_code)
    tgt = "zh" if tgt_code == "zh-hant" else tgt_code

    if src == tgt:
        out_text, out_pend = src_text, src_pend
    else:
        model = get_model()
        translator = Translator(model, src, tgt, plain_name, plain_name, is_monster)
        out_text = _translate_body(model, translator, src_text, src, tgt, 0)
        out_pend = _translate_body(model, translator, src_pend, src, tgt, 1)

    ruby_names = (plain_name,) if plain_name else ()
    return (
        out_name,
        _from_base(out_text, tgt_code, tgt_language, ruby_names),
        _from_base(out_pend, tgt_code, tgt_language, ruby_names),
    )


_WARM = {"thread": None}


def warm_up():
    """后台载入模型（重复调用无副作用）。"""
    if _WARM["thread"] is not None or not model_available():
        return

    def run():
        try:
            neural.warm_up() if USE_NEURAL else None
        except Exception:
            pass
        try:
            model = get_model()
            # 与 Translator 里用到的检索组合一致，首次切换语言时就不必现建
            for tgt, groups in (
                ("ja", (("S", "B", "Q"), ("B",), ("Q",))),
                ("en", (("S", "E", "B"), ("B",), ("C",), ("K",))),
            ):
                for kinds in groups:
                    model.fuzzy(kinds, "zh", tgt)
                model.repair_tables("zh", tgt)
        except Exception:
            pass

    thread = threading.Thread(target=run, name="ygo-translator-warmup", daemon=True)
    _WARM["thread"] = thread
    thread.start()


__all__ = ["translate_card", "warm_up", "language_code", "model_available", "LANGUAGE_CODES"]
