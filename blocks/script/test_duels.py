"""在 MDPro3 的同一副残局上分别跑官方脚本及积木生成的脚本。"""

import unittest

from sandbox.probe import load_check
from sandbox.scenario import Runner
from blocks import SCHEMA, build
from blocks.catalog import new
from blocks.check_proto import BE, DORON, LV4, SPELL, act, card, chk, regression_core
from . import parse


def count(player, zone, code, n):
    return chk("count", player=player, **{"in": zone, "card": code, "eq": n})


class ScriptDuels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = regression_core()

    def duel(self, field, actions):
        runner = Runner(self.core, {"field": field, "actions": actions})
        self.assertTrue(runner.run(), runner.failures)
        self.assertFalse(self.core.errors, self.core.errors)
        return runner.lines

    def compare(self, code, field, actions):
        original = self.core.zip.read("script/c%d.lua" % code)
        program = parse(original.decode("utf-8-sig"), code)
        result = build({"schema": SCHEMA, "card": {"code": code}, "effects": [program]})
        traces = []
        for script in (original, result["lua"].encode()):
            self.assertEqual(load_check(self.core, code, script), (True, []))
            traces.append(self.duel(field, actions))
        self.assertEqual(*traces)

    def test_pot_of_greed(self):
        code = 55144522
        self.compare(code, {0: {"hand": [code]}}, [act(0, "activate", code), chk("drawn", player=0, eq=2)])
        self.compare(code, {0: {"hand": [code]}, 1: {"szone": [{"code": 58921041, "pos": "faceup"}]}},
                     [chk("offered", card=code, **{"as": "activate", "eq": False})])

    def test_monster_reborn(self):
        code = 83764718
        self.compare(code, {0: {"hand": [code]}, 1: {"grave": [BE]}},
                     [act(0, "activate", code), count(0, "mzone", BE, 1), count(1, "grave", BE, 0)])
        self.compare(code, {0: {"hand": [code]}}, [chk("offered", card=code, **{"as": "activate", "eq": False})])

    def test_raigeki(self):
        code = 12580477
        self.compare(code, {0: {"hand": [code], "mzone": [DORON]}, 1: {"mzone": [BE, LV4]}},
                     [act(0, "activate", code), count(0, "mzone", DORON, 1), count(1, "grave", BE, 1),
                      count(1, "grave", LV4, 1)])

    def test_upstart_goblin(self):
        code = 70368879
        self.compare(code, {0: {"hand": [code]}}, [act(0, "activate", code), chk("drawn", player=0, eq=1),
                                                  chk("lp", player=1, eq=9000)])

    def test_premature_burial(self):
        code = 70828912
        self.compare(code, {0: {"hand": [code], "grave": [DORON]}}, [act(0, "activate", code),
                     chk("lp", player=0, eq=7200), count(0, "mzone", DORON, 1), count(0, "szone", code, 1)])

    def test_new_code_and_edited_argument(self):
        code = 100039711
        program = parse(self.core.zip.read("script/c55144522.lua").decode())
        from blocks.compile import walk
        draw = next(b for b in walk(program) if b["block"] == "ls_api_Duel_Draw")
        draw["arg1"] = [new("ls_number", value="3")]
        src = build(card(code, "抽三张", "spell", [program]))["lua"]
        self.core.add_card(dict(SPELL, code=code, alias=0, name="抽三张", setcodes=[]))
        self.assertEqual(load_check(self.core, code, src.encode()), (True, []))
        self.duel({0: {"hand": [code]}}, [act(0, "activate", code), chk("drawn", player=0, eq=3)])

    def test_reason_and_owner_in_effect_blocks(self):
        code, hole = 100039713, 53129443
        src_name = new("f_name", code=hole)
        cards = new("event_cards", filter=[new("f_reason_handler", filter=[src_name]),
                                           new("f_card_owner", who="you")])
        condition = new("all_of", items=[new("event_effect_from", filter=[src_name]), new("exists", cards=[cards])])
        effect = new("effect", type="trigger_f", event="cards_to_grave", range="grave",
                     condition=[condition], operation=[new("damage", player="opp", amount=[new("num", value=500)])])
        from blocks.check_proto import MON
        self.core.add_card(dict(MON, code=code, alias=0, name="原因检查", setcodes=[]))
        model = card(code, "原因检查", "monster", [effect])
        result = build(model)
        self.assertFalse(result["issues"], result["issues"])
        self.assertEqual(load_check(self.core, code, result["lua"].encode()), (True, []))
        self.duel({0: {"grave": [code], "mzone": [DORON], "hand": [hole]}},
                  [act(0, "activate", hole), chk("lp", player=1, eq=7500)])
        self.duel({0: {"grave": [code], "hand": [hole]}, 1: {"mzone": [BE]}},
                  [act(0, "activate", hole), chk("lp", player=1, eq=8000)])

    def test_effect_state_and_numbers(self):
        code, drain, ash = 100039717, 82732705, 14558127
        monster = new("all", who="you", where="mzone")
        def compare(value, op, target):
            return new("compare", op=op, left=[value], right=[new("num", value=target)])
        tests = [new("exists", cards=[dict(monster, filter=[new("f_effect_state", state="disabled")])]),
                 compare(new("effect_instances", code="EFFECT_DISABLE", card=[monster]), ">=", 1),
                 compare(new("announced_attacks", card=[monster]), "==", 0),
                 compare(new("location_turn", card=[monster]), ">=", 0)]
        effect = new("effect", type="activate", condition=[new("all_of", items=tests)], operation=[new("draw")])
        self.core.add_card(dict(SPELL, code=code, alias=0, name="状态检查", setcodes=[]))
        result = build(card(code, "状态检查", "spell", [effect]))
        self.assertEqual(load_check(self.core, code, result["lua"].encode()), (True, []))
        mine = {"mzone": [ash], "hand": [code]}
        self.duel({0: mine, 1: {"szone": [{"code": drain, "pos": "faceup"}]}},
                  [act(0, "activate", code), chk("drawn", player=0, eq=1)])
        self.duel({0: mine}, [chk("offered", card=code, **{"as": "activate", "eq": False})])
