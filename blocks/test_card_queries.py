"""用本机 MDPro3 核心验证实卡脚本中提炼的积木。python -m unittest blocks.test_card_queries"""

import unittest

from sandbox.probe import load_check
from sandbox.scenario import Runner
from . import build
from .catalog import new
from .check_proto import BE, DORON, LV4, MON, SPELL, TWIN, act, card, chk, regression_core

CODE = 100039001
MACRO_COSMOS, MONSTER_REBORN, UMI = 30241314, 83764718, 22702055


def eq(value, n):
    return new("compare", op="==", left=[value], right=[new("num", value=n)])


def count(key, **fields):
    return new("count_of", cards=[new(key, **fields)])


def damage(amount):
    return new("damage", player="opp", amount=[amount])


def offered(value):
    return {"check": "offered", "card": CODE, "as": "activate", "eq": value}


class CardScriptBlocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = regression_core()

    def play(self, effects, field, actions, record=SPELL):
        kind = "spell" if record == SPELL else "monster"
        model = card(CODE, self.id(), kind, effects)
        result = build(model)
        self.assertEqual(result["issues"], [])
        self.assertNotIn("（？）", result["desc"])
        self.core.add_card(dict(record, code=CODE, name="测试卡", alias=0, setcodes=[]))
        script = result["lua"].encode()
        self.assertEqual(load_check(self.core, CODE, script), (True, []))
        runner = Runner(self.core, {"name": self.id(), "field": field, "actions": actions})
        self.assertTrue(runner.run(), runner.failures)

    def test_mill_effect_cost_and_replacement(self):
        effect = new("effect", type="activate", cost=[new("mill_deck", count=2)], operation=[
            new("mill_deck", player="opp", count=3), new("after", body=[damage(count("cost_cards"))])])
        self.play([effect], {0: {"hand": [CODE], "deck": [DORON, DORON]}}, [act(0, "activate", CODE),
                  {"check": "count", "player": 0, "in": "grave", "card": DORON, "eq": 2},
                  {"check": "count", "player": 1, "in": "grave", "eq": 3}, chk("lp", player=1, eq=7998)])
        field = {0: {"hand": [CODE]}, 1: {"szone": [{"code": MACRO_COSMOS, "pos": "faceup"}]}}
        self.play([effect], field, [offered(False)])
        mill = new("effect", type="activate", operation=[
            new("mill_deck", count=2), new("after", body=[damage(new("num", value=100))])])
        self.play([mill], field, [act(0, "activate", CODE),
                  {"check": "count", "player": 0, "in": "banished", "card": BE, "eq": 2}, chk("lp", player=1, eq=8000)])
        for slot in ("cost", "operation"):
            with self.subTest(slot=slot):
                effect = new("effect", type="activate", operation=[new("draw")])
                effect[slot] = [new("mill_deck", count=21)]
                self.play([effect], {0: {"hand": [CODE]}}, [offered(False)])

    def test_combined_costs(self):
        effect = new("effect", type="activate", cost=[
            new("mill_deck", count=2), new("discard", cards=[new("pick", who="you", where="hand")])],
            operation=[damage(count("cost_cards"))])
        self.play([effect], {0: {"hand": [CODE, DORON]}}, [act(0, "activate", CODE), chk("lp", player=1, eq=7997)])
        effect["cost"] = [new("mill_deck", count=11), new("mill_deck", count=10)]
        self.play([effect], {0: {"hand": [CODE]}}, [offered(False)])

    def test_zones_after_materials_leave(self):
        allies = new("all", who="you", where="mzone")
        fusion = new("all", who="you", where="extra")
        conditions = [eq(new("free_zones"), 4), eq(new("free_zones", exclude=[allies]), 5),
                      eq(new("free_zones", player="opp", zone="szone"), 4),
                      eq(new("extra_zones", monster=[fusion]), 5),
                      eq(new("extra_zones", monster=[fusion], exclude=[allies]), 6),
                      eq(new("extra_zones", monster=[new("all", where="banished")]), 0)]
        effect = new("effect", type="activate", condition=[new("all_of", items=conditions)], operation=[new("draw")])
        field = {0: {"hand": [CODE], "mzone": [DORON], "extra": [TWIN]}, 1: {"szone": [MACRO_COSMOS]}}
        self.play([effect], field, [offered(True)])
        field[0]["mzone"].append(BE)
        self.play([effect], field, [offered(False)])

    def test_summon_from_hand_and_summoning_player(self):
        filters = [new("f_summon_location", where="hand+extra"), new("f_summon_player", who="you"),
                   new("f_location", where="mzone"), new("f_printed_type", kind="monster")]
        cond = new("exists", cards=[new("event_cards", filter=filters)])
        effect = new("effect", type="listener", event="monster_summoned_both", condition=[cond],
                     operation=[damage(new("num", value=200))])
        self.play([effect], {0: {"mzone": [CODE], "hand": [DORON, MONSTER_REBORN], "grave": [LV4]},
                             1: {"hand": [DORON]}}, [act(0, "summon", DORON), chk("lp", player=1, eq=7800),
                  act(0, "activate", MONSTER_REBORN), {"player": 0, "do": "select", "cards": [LV4]},
                  chk("lp", player=1, eq=7800), act(0, "end_turn"), act(1, "summon", DORON),
                  chk("lp", player=1, eq=7800)], MON)

    def test_mutual_link_selection_and_target_filter(self):
        right, left = 2220237, 30691817  # 安全守卫者的箭头向右，海晶少女 海天使的箭头向左
        source = new("mutual_linked_group", filter=[new("f_capable", ability="destroy")])
        pick = new("effect", type="ignition", operation=[new("select", source=[source]),
                   new("destroy", cards=[new("var", name="A")])])
        candidates = new("all", who="you", where="mzone", filter=[new("f_related", relation="mutual_linked_group")])
        target = new("effect", type="ignition", target=[new("take_target", source=[candidates])],
                     operation=[new("destroy", cards=[new("target")])])
        for effect in (pick, target):
            for partner, mutual in ((left, True), (right, False)):
                with self.subTest(block=effect["operation"][0]["block"], mutual=mutual):
                    actions = [offered(mutual)]
                    if mutual:
                        actions += [act(0, "activate", CODE), {"check": "count", "player": 0, "in": "grave", "card": partner, "eq": 1}]
                    self.play([effect], {0: {"mzone": [{"code": CODE, "seq": 1}, {"code": partner, "seq": 2}]}},
                              actions, dict(MON, type=0x4000021, level=1, **{"def": 0x20}))

    def test_field_environment(self):
        effect = new("effect", type="activate", condition=[new("environment", code=UMI, name="海", who="opp")],
                     operation=[new("draw")])
        for field, active in (({0: {"hand": [CODE]}}, False), ({0: {"hand": [CODE], "fzone": [UMI]}}, False),
                              ({0: {"hand": [CODE]}, 1: {"fzone": [UMI]}}, True),
                              ({0: {"hand": [CODE]}, 1: {"mzone": [17214465]}}, True)):
            with self.subTest(field=field):
                self.play([effect], field, [offered(active)])

    def test_turn_counter_and_flags(self):
        ops = [new("set_turn_counter", count=3)]
        for owner in ("card", "player"):
            ops += [new("set_flag", on=owner), new("if", cond=[new("has_flag", on=owner)], then=[
                damage(new("turn_counter_of", card=[new("this_card")]))]), new("reset_flag", on=owner),
                new("if", cond=[new("has_flag", on=owner)], then=[damage(new("num", value=1000))])]
        self.play([new("effect", type="ignition", operation=ops)], {0: {"mzone": [CODE]}},
                  [act(0, "activate", CODE), chk("lp", player=1, eq=7994)], MON)

    def test_activation_location_and_related_chain(self):
        upstart = 70368879  # 成金哥布林发动后，对方本应回复1000基本分
        for origin in ("hand", "szone"):
            with self.subTest(origin=origin):
                effect = new("effect", type="quick_o", event="chaining", event_player="opp",
                             condition=[new("chain_location", where=origin)],
                             operation=[new("negate_related", cards=[new("chain_card")])])
                self.play([effect], {0: {origin: [upstart]}, 1: {"mzone": [CODE]}},
                          [act(0, "activate", upstart), act(1, "activate", CODE), chk("lp", player=1, eq=8000),
                           {"check": "count", "player": 0, "in": "hand", "eq": 0}], MON)

    def test_material_event_and_destination(self):
        poly, five_headed = 24094653, 99267150  # 融合、五神龙
        cond = new("all_of", items=[
            new("event_reason", reason="fusion", match="exact"),
            new("card_is", cards=[new("this_card")], filter=[
                new("f_location", where="grave"), new("f_not", filter=[new("f_reason", reason="return")])])])
        effect = new("effect", type="trigger_f", event="be_material", condition=[cond],
                     operation=[damage(new("num", value=200))])
        for macro in (False, True):
            with self.subTest(macro=macro):
                field = {0: {"extra": [five_headed], "hand": [poly, CODE] + [BE] * 4}}
                if macro:
                    field[1] = {"szone": [{"code": MACRO_COSMOS, "pos": "faceup"}]}
                self.play([effect], field, [act(0, "activate", poly),
                          {"check": "count", "player": 0, "in": "mzone", "card": five_headed, "eq": 1},
                          chk("lp", player=1, eq=8000 if macro else 7800)], dict(MON, race=0x2000))

    def test_used_materials_and_overlay_host(self):
        materials = new("extra_materials", method="xyz", rank=4, count=2)
        cond = new("all_of", items=[
            eq(count("materials_used"), 2), eq(new("overlay_count_of", card=[new("this_card")]), 2),
            eq(count("overlay_host", card=[new("overlay")], filter=[new("f_name", code=CODE)]), 1)])
        effect = new("effect", type="ignition", condition=[cond], operation=[
            new("select", source=[new("materials_used")], **{"as": "M"}),
            new("select", source=[new("overlay_host", card=[new("var", name="M")])], **{"as": "X"}),
            damage(new("overlay_count_of", card=[new("var", name="X")]))])
        self.play([materials, effect], {0: {"mzone": [LV4, LV4], "extra": [CODE]}},
                  [act(0, "spsummon", CODE), offered(True), act(0, "activate", CODE), chk("lp", player=1, eq=7998)],
                  dict(MON, type=0x800021))

    def test_battle_history_and_reason_card(self):
        battled = new("effect", type="ignition", condition=[new("exists", cards=[new("battled_group")])],
                      operation=[damage(new("num", value=100))])
        calculated = new("effect", type="listener", event="battled", condition=[new("damage_calculated")],
                         operation=[damage(new("num", value=50))])
        self.play([battled, calculated], {0: {"mzone": [CODE]}, 1: {"mzone": [{"code": BE, "pos": "defense"}]}},
                  [offered(False), act(0, "battle"), act(0, "attack", CODE, target=BE), act(0, "main2"),
                   act(0, "activate", CODE), chk("lp", player=1, eq=7850)], MON)
        condition = new("all_of", items=[new("event_reason", reason="battle"),
                            new("exists", cards=[new("reason_card", filter=[new("f_name", code=BE)])])])
        grave = new("effect", type="trigger_f", event="to_grave", condition=[condition],
                    operation=[damage(new("previous_value", stat="def", card=[new("this_card")]))])
        self.play([grave], {0: {"mzone": [BE]}, 1: {"mzone": [CODE]}},
                  [act(0, "battle"), act(0, "attack", BE, target=CODE), chk("lp", player=0, eq=7000)], MON)

    def test_all_persistent_targets(self):
        ops = [new("keep_target", cards=[new("all", where="mzone", filter=[new("f_name", code=DORON)])]),
               new("keep_target", cards=[new("all", where="mzone", who="opp")]), damage(count("persistent_targets"))]
        self.play([new("effect", type="ignition", operation=ops)], {0: {"mzone": [CODE, DORON]}, 1: {"mzone": [BE]}},
                  [act(0, "activate", CODE), chk("lp", player=1, eq=7998)], MON)
