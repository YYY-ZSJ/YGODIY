# -*- coding: utf-8 -*-
"""神经翻译小模型（Qwen3-0.6B 经 LoRA 微调，GGUF Q8_0，llama.cpp CPU 推理）。

训练见 工具/翻译模型/neural/。模型文件放在 model/ygo_nmt_q8.gguf，
推理库（llama-cpp-python 及其依赖）放在本目录的 vendor/ 里。
任何一样缺失时 available() 返回 False，调用方退回实例翻译模型。
"""

import os
import re
import sys
import threading
from runtime_paths import rpath

_HERE = rpath("ygo_translator")
MODEL_PATH = os.path.join(_HERE, "model", "ygo_nmt_q8.gguf")
# 解码时允许的 token：训练译文里出现过的 + <|im_end|>（见 _allowed_mask 的说明）
ALLOWED_PATH = os.path.join(_HERE, "model", "ygo_nmt_allowed_tokens.json")
IM_END = 151645
VENDOR = os.path.join(_HERE, "vendor")

LANG_NAMES = {"zh": "简体中文", "ja": "日本語", "en": "English"}
KIND_NAMES = {"name": "卡名", "text": "效果", "pend": "灵摆效果"}

_LOCK = threading.Lock()
_STATE = {"llm": None, "error": None, "mask": None, "reason": ""}


def last_reason():
    """最近一次 translate() 返回 None 的原因（写日志用）。"""
    return _STATE["reason"] or _STATE["error"] or ""


def build_prompt(src, tgt, kind, text):
    # 必须与训练时（工具/翻译模型/neural/prompt.py）完全一致
    return "<|im_start|>游戏王 %s %s→%s\n%s<|im_end|>\n<|im_start|>%s\n" % (
        KIND_NAMES[kind], LANG_NAMES[src], LANG_NAMES[tgt], text, LANG_NAMES[tgt])


def available():
    return (
        os.path.exists(MODEL_PATH) and os.path.exists(ALLOWED_PATH)
        and os.path.isdir(VENDOR) and _STATE["error"] is None
    )


def _allowed_mask(vocab_size):
    """Qwen3-Base 的 <|im_end|> 嵌入几乎没训练过：到了该结束的位置，模型会滑向一批同样
    没训练过的怪 token，而不是结束符。只放行训练译文里出现过的 token，结束符就能胜出。"""
    import json

    import numpy

    with open(ALLOWED_PATH, encoding="utf-8") as handle:
        allowed = [token for token in json.load(handle) if token < vocab_size]
    mask = numpy.full(vocab_size, -numpy.inf, dtype=numpy.float32)
    mask[allowed] = 0.0
    return mask


def _load():
    with _LOCK:
        if _STATE["llm"] is not None or _STATE["error"] is not None:
            return _STATE["llm"]
        if "PyQt5.QtCore" in sys.modules:
            # Qt 之后再创建 llama.cpp 模型会访问违例，整个进程直接闪退（崩溃记录里的
            # llama.py __init__ 即此）。只有 preload() 能在 Qt 之前载入；没赶上就不再尝试。
            _STATE["error"] = "PyQt5 已先于翻译模型载入（llama.cpp 必须在 Qt 之前载入）"
            return None
        try:
            if VENDOR not in sys.path:
                sys.path.insert(0, VENDOR)
            from llama_cpp import Llama

            threads = max(2, (os.cpu_count() or 4) // 2)
            llm = Llama(model_path=MODEL_PATH, n_ctx=2048, n_threads=threads, verbose=False)
            _STATE["mask"] = _allowed_mask(llm.n_vocab())
            _STATE["llm"] = llm
        except Exception as error:  # 推理库或模型损坏：记下原因，之后都走实例模型
            _STATE["error"] = repr(error)
        return _STATE["llm"]


def warm_up():
    if available():
        _load()


def preload():
    """在 PyQt5 被导入之前载入模型。

    实测：进程里只要导入过 PyQt5.QtCore（DLL 冲突），之后再创建 llama.cpp 模型就会访问违例
    （OSError: access violation reading 0x0）；而先载入模型、之后再导入 Qt 一切正常
    （包括在后台线程里推理）。补丁包 offline_runtime 的 __init__ 在执行任何分片之前调用这里，
    fast_launch.py 导入补丁包时还没有导入 PyQt5。"""
    if _STATE["llm"] is not None:
        return True
    if not available():
        return False
    return _load() is not None


def _degenerate(text):
    """重复循环（小模型偶发）或空输出。"""
    if not text.strip():
        return True
    return bool(re.search(r"(.{6,}?)\1{3,}", text))


def translate(text, src, tgt, kind):
    """翻译一段文本；失败或输出可疑时返回 None。"""
    llm = _load()
    if llm is None or not text or not text.strip():
        _STATE["reason"] = "模型未载入" if llm is None else "空文本"
        return None
    prompt = build_prompt(src, tgt, kind, text.strip())
    prompt_tokens = len(llm.tokenize(prompt.encode("utf-8"), add_bos=False, special=True))
    budget = min(2048 - prompt_tokens - 8, prompt_tokens * 3 + 48)
    if budget < 8:
        _STATE["reason"] = "文本过长"
        return None
    mask = _STATE["mask"]

    def constrain(_input_ids, scores):
        return scores + mask

    def stop_on_end(input_ids, _logits):
        return len(input_ids) > 0 and int(input_ids[-1]) == IM_END

    from llama_cpp import LogitsProcessorList, StoppingCriteriaList

    with _LOCK:
        result = llm(
            prompt, max_tokens=budget, temperature=0.0,
            logits_processor=LogitsProcessorList([constrain]),
            stopping_criteria=StoppingCriteriaList([stop_on_end]),
        )
    choice = result["choices"][0]
    output = choice["text"].strip()
    if choice.get("finish_reason") == "length" or _degenerate(output):
        _STATE["reason"] = "输出被截断或重复：%r" % output[:60]
        return None
    _STATE["reason"] = ""
    return output
