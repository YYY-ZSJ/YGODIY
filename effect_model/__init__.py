"""YGODIY Effect Model：卡片效果的结构化描述，可生成 ygopro Lua 与规范效果文本。

    from effect_model import build
    result = build(model_dict)   # {"lua": ..., "desc": ..., "pdesc": ..., "strings": [...], "issues": [...]}

当前结构是 v0.2（设计见 docs/v0.2-骨架设计.md）；v0.1 的数据读入时自动升级。
"""

from .model import SCHEMA, SCHEMA_V01, ModelError, item_by_id, lint, load, normalize, upgrade
from . import zh


def build(card):
    from . import lua
    issues = lint(card)
    text = zh.render(card)
    code, strings = lua.generate(card)
    return {"lua": code, "desc": text["desc"], "pdesc": text["pdesc"], "strings": strings, "issues": issues}
