"""引擎常量名：积木里的种族、属性 → Lua 常量（衍生物等用）。"""

from .compile import RACE

RACE_CONST = {k: "RACE_" + v for k, v in RACE.items()}
ATTRIBUTE_CONST = {k: "ATTRIBUTE_" + k.upper() for k in ("light", "dark", "earth", "water", "fire", "wind", "divine")}
