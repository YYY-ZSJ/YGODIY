"""卡名查询。模型里引用别的卡只存卡密，效果文字要写成「暗道化师 彼得」。

查找顺序：这张卡自己 → 调用方登记的名字（工作台把同一卡包里的 DIY 卡登记进来）→ 制卡器自带的离线卡库（百鸽中文名）。
"""

import functools
import json
import os

_registered = {}


def register(names):
    """登记 {卡密: (中文名, 是否怪兽)}，比离线卡库优先。"""
    _registered.update(names)


@functools.lru_cache(maxsize=None)
def _offline():
    try:
        from ygopack import mdpro3
        path = os.path.join(mdpro3.app_dir(), "离线卡库", "cards.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (ImportError, OSError, ValueError):
        return {}
    return {v["id"]: (v.get("cn_name") or v.get("sc_name") or "", bool(v.get("data", {}).get("type", 0) & 1))
            for v in data.values() if isinstance(v, dict) and "id" in v}


def _lookup(code, card):
    if card and card["card"].get("code") == code:
        return card["card"]["name"], card["card"].get("kind") == "monster"
    return _registered.get(code) or _offline().get(code)


def name_of(code, card=None):
    found = _lookup(code, card)
    return found[0] if found and found[0] else str(code)


def is_monster(code, card=None):
    """查不到时返回 None。"""
    found = _lookup(code, card)
    return found[1] if found else None


@functools.lru_cache(maxsize=None)
def _by_name():
    out = {}
    for code, (name, _) in sorted(_offline().items()):     # 同名（异画）取最小的卡密
        out.setdefault(name, code)
    return out


def code_of(name, card=None):
    """中文卡名 → 卡密（解析官方文本用）；查不到时返回 None。"""
    if card and card["card"].get("name") == name:
        return card["card"].get("code")
    for code, (n, _) in _registered.items():
        if n == name:
            return code
    return _by_name().get(name)
