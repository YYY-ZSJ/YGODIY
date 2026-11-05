"""Effect Model 的结构：词汇、v0.1 升级、补默认值、语义检查。设计见 effect_model/docs/v0.2-骨架设计.md。

只放与「输出到哪里」无关的部分：Lua 后端（lua.py）和中文文本（zh.py）都从 normalize() 的结果出发。
"""

from .lint import lint
from .normalize import ModelError, applies, effect_by_id, is_numbered, is_ref, item_by_id, limits_of, load, normalize
from .upgrade import upgrade, upgrade_cond, upgrade_step
from .vocab import CIRCLED, LINKS, SCHEMA, SCHEMA_V01
