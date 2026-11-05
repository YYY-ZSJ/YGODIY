"""Effect Model → ygopro Lua（萌卡 / Fluorohydride ygopro-scripts 方言，MDPro3、ygopro2 用的就是它）。

生成器只认词汇表里的东西：每个动作、事件、条件对应一段验证过的 Lua 写法。
引擎上的惯用法（效果分类、NecroValleyFilter、IsRelateToEffect、检索后给对方确认、增殖的G 的连锁处理……）
全部由这里负责，制卡的人不需要知道。
"""

from .gen import Gen, generate  # noqa: F401
