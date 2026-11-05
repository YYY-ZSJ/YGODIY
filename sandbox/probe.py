"""加载检查：把一张卡放进手卡 / 场上 / 墓地 / 灵摆区域 / 额外卡组，推进到先攻玩家的主要阶段 1。

期间引擎会加载它的脚本、执行 initial_effect，并对可发动的效果调用 condition、cost(chk=0)、target(chk=0)。
效果处理、诱发效果和连锁由情景测试（scenario.py）负责。
"""

from .duel import Duel

FILLER = 89631139      # 青眼白龙
OPP_EFFECT = 14558127  # 对方墓地里放的效果怪兽（灰流丽）
TYPE_SPELL, TYPE_TRAP, TYPE_PENDULUM = 0x2, 0x4, 0x1000000
TYPE_EXTRA = 0x40 | 0x2000 | 0x800000 | 0x4000000   # 融合、同调、超量、连接


def load_check(core, code, script=None):
    """返回 (脚本是否被加载, 错误列表)。script 给出时用它代替这张卡的脚本。"""
    core.overrides = {code: script} if script is not None else {}
    core.requested.clear()
    core.errors.clear()
    typ = core.card_type(code)
    mine = {"mzone": [FILLER]}
    if typ & TYPE_EXTRA:
        mine.update(extra=[code], mzone=[FILLER, code])
    else:
        mine.update(hand=[code], grave=[code])
        if typ & (TYPE_SPELL | TYPE_TRAP):
            mine["szone"] = [code]
        else:
            mine["mzone"].append(code)
        if typ & TYPE_PENDULUM:
            mine["pzone"] = [code]
    d = Duel(core)
    d.setup({"0": mine, "1": {"mzone": [FILLER, FILLER, {"code": FILLER, "pos": "facedown_defense"}],
                              "grave": [OPP_EFFECT], "szone": [FILLER]}})
    d.start()
    d.advance()
    d.end()
    return code in core.requested, list(core.errors)
