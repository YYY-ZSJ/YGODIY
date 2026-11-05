"""普通可选反转诱发的独立回归数据，由check_proto统一执行。"""

from .catalog import new

CODE, DRAW_CARD, ATTACKER = 100009775, 756652, 89631139
RECORD = {"type": 0x21, "level": 4, "attribute": 0x20, "race": 0x8, "atk": 1500, "def": 1000}
MODEL = {"schema": "ygodiy-blocks/0.3", "card": {"code": CODE, "name": "积木·可选反转", "kind": "monster"},
         "effects": [new("effect", type="trigger_o", event="flip", operation=[new("draw", count=1)])]}
SCENARIOS = [
    {"name": "反转召唤可选发动并抽卡", "field": {"0": {"mzone": [{"code": CODE, "pos": "set"}], "deck": [DRAW_CARD]}},
     "actions": [{"player": 0, "do": "reposition", "card": CODE}, {"player": 0, "do": "activate", "card": CODE},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 1}]},
    {"name": "被攻击翻开可选发动", "field": {"0": {"mzone": [{"code": CODE, "pos": "set"}], "deck": [DRAW_CARD]},
                                                "1": {"mzone": [ATTACKER]}},
     "actions": [{"player": 0, "do": "end_turn"}, {"player": 1, "do": "battle"},
                 {"player": 1, "do": "attack", "card": ATTACKER, "target": CODE},
                 {"player": 0, "do": "activate", "card": CODE},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 1}]},
    {"name": "效果翻开可选发动", "field": {"0": {"hand": [38699854], "mzone": [{"code": CODE, "pos": "set"}], "deck": [DRAW_CARD]}},
     "actions": [{"player": 0, "do": "activate", "card": 38699854}, {"player": 0, "do": "select", "cards": [CODE]},
                 {"player": 0, "do": "activate", "card": CODE},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 1}]},
    {"name": "可以拒绝发动", "field": {"0": {"mzone": [{"code": CODE, "pos": "set"}], "deck": [DRAW_CARD]}},
     "actions": [{"player": 0, "do": "reposition", "card": CODE}, {"player": 0, "do": "no"},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 0},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "deck", "eq": 1}]},
    {"name": "普通召唤不触发", "field": {"0": {"hand": [CODE], "deck": [DRAW_CARD]}},
     "actions": [{"player": 0, "do": "summon", "card": CODE},
                 {"check": "offered", "player": 0, "card": CODE, "as": "chain", "eq": False},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 0}]},
    {"name": "特殊召唤不触发", "field": {"0": {"hand": [83764718], "grave": [CODE], "deck": [DRAW_CARD]}},
     "actions": [{"player": 0, "do": "activate", "card": 83764718}, {"player": 0, "do": "select", "cards": [CODE]},
                 {"check": "offered", "player": 0, "card": CODE, "as": "chain", "eq": False},
                 {"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 0}]},
    {"name": "未翻开不触发", "field": {"0": {"mzone": [{"code": CODE, "pos": "set"}], "deck": [DRAW_CARD]}},
     "actions": [{"check": "count", "player": 0, "card": DRAW_CARD, "in": "hand", "eq": 0},
                 {"check": "offered", "player": 0, "card": CODE, "as": "activate", "eq": False}]},
]
CASE = ("普通诱发·可选反转", MODEL, RECORD, "①：这张卡反转的场合才能发动。自己从卡组抽1张。", SCENARIOS,
        ("SetCode(EVENT_FLIP)", "SetCode(EVENT_FLIP_SUMMON_SUCCESS)"))
