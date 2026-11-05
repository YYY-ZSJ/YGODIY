"""v0.3 积木的检查：九张卡用通用积木拼出来，读成中文、翻译成 Lua，在测试沙盒里跑情景，
并把 Lua 改坏一处，情景要能查出来。样例存进 blocks/samples/（v0.3 积木树 JSON）。

    雷击（DIY 1000097 01）：对方场上的怪兽全部破坏
    增援（DIY 1000097 02）：让自己从卡组选1只4星以下的战士族怪兽，加入手卡（官方说法自动认出）
    没有官方先例的卡（DIY 1000097 03）：每次对方抽卡，这张卡攻击力上升100；攻击力在3000以上时自己决斗胜利
    04–09：代价与取对象、自肃（玩家效果）、永续效果、●选项、连锁无效（手坑）、衍生物与「对每一张」

用法（在 YGODIY_src 下）：python -m blocks.check_proto
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from blocks.catalog import new  # noqa: E402
from blocks import type_bits  # noqa: E402
from blocks.compile import check, compile_card, tokens  # noqa: E402
from blocks.read import read_card  # noqa: E402
from blocks.proto_flip import CASE as FLIP_CASE  # noqa: E402

SCHEMA = "ygodiy-blocks/0.3"
SPELL = {"type": 0x2, "level": 0, "attribute": 0, "race": 0, "atk": 0, "def": 0}
BE, DORON, LV4 = 89631139, 756652, 549481       # 青眼白龙、多隆（3星战士族）、硬毛鼠（兽族）


def card(code, name, kind, effects):
    return {"schema": SCHEMA, "card": {"code": code, "name": name, "kind": kind}, "effects": effects}


raigeki = card(100009701, "积木·雷击", "spell", [
    new("effect", type="activate", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_kind", kind="monster")])])])])

rota = card(100009702, "积木·增援", "spell", [
    new("effect", type="activate", operation=[
        new("select", player="you", count=1, **{"as": "A"}, source=[
            new("all", who="you", where="deck",
                filter=[new("f_level", op="<=", value=4), new("f_race", race="warrior"), new("f_kind", kind="monster")])]),
        new("to_hand", cards=[new("var", name="A")])])])

wild = card(100009703, "积木·贪婪的观星者", "monster", [
    new("effect", type="trigger_f", event="draw", event_player="opp", range="mzone", operation=[
        new("register", code="EFFECT_UPDATE_ATTACK", reset="permanent", cards=[new("this_card")], value=[new("num", value=100)]),
        new("if", cond=[new("compare", op=">=", left=[new("atk_of", card=[new("this_card")])],
                            right=[new("num", value=3000)])],
            then=[new("win", player="you")])])])
WILD_REC = {"type": 0x21, "level": 4, "attribute": 0x10, "race": 0x1, "atk": 2900, "def": 1000}
MON = {"type": 0x21, "level": 4, "attribute": 0x20, "race": 0x8, "atk": 1500, "def": 1000}       # 暗属性恶魔族
TRAP_MON = {"type": 0x21, "level": 3, "attribute": 0x10, "race": 0x1000, "atk": 0, "def": 1800}
TOKEN = {"type": 0x4011, "level": 1, "attribute": 0x10, "race": 0x1, "atk": 0, "def": 0}
RAIGEKI = 12580477

cost_target = card(100009704, "积木·丢弃破坏", "spell", [
    new("effect", type="activate",
        cost=[new("discard", cards=[new("pick", who="you", where="hand", count=1)])],
        target=[new("take_target", count=1, **{"as": "T"},
                    source=[new("all", who="opp", where="mzone", filter=[new("f_kind", kind="monster")])])],
        operation=[new("destroy", cards=[new("target", name="T")])])])

restrict = card(100009705, "积木·自肃抽卡", "monster", [
    new("effect", type="ignition", range="mzone", limit="name",
        cost=[new("pay_lp", amount=[new("num", value=1000)])],
        operation=[new("draw", player="you", count=1),
                   new("register_player", player="you", code="EFFECT_CANNOT_SUMMON", reset="end_of_turn")])])

aura = card(100009706, "积木·战士的号令", "monster", [
    new("continuous", mode="zone", code="EFFECT_UPDATE_ATTACK", range="mzone", who="you", where="mzone",
        value=[new("num", value=500)], filter=[new("f_race", race="warrior")])])

options = card(100009707, "积木·二选一", "spell", [
    new("effect", type="activate", operation=[
        new("choose", player="you", options=[
            new("option", text="自己抽1张卡", body=[new("draw", player="you", count=1)]),
            new("option", text="给与对方500伤害",
                cond=[new("exists", cards=[new("all", who="opp", where="mzone")])],
                body=[new("damage", player="opp", amount=[new("num", value=500)])])])])])

ash = card(100009708, "积木·手坑", "monster", [
    new("effect", type="quick_o", event="chaining", event_player="opp", range="hand", limit="name",
        cost=[new("discard", cards=[new("this_card")])],
        operation=[new("negate_activation"),
                   new("after", body=[new("destroy", cards=[new("chain_card")])])])])

tokens_ = card(100009709, "积木·衍生物列阵", "spell", [
    new("effect", type="activate", operation=[
        new("create_token", name="积木衍生物", count=2, race="warrior", attribute="light", level=1, atk=0, def_=0),
        new("for_each", cards=[new("all", who="you", where="mzone", filter=[new("f_race", race="warrior")])], body=[
            new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn", cards=[new("each")],
                value=[new("num", value=300)])])])])
tokens_["effects"][0]["operation"][0].pop("def_")

MIRROR = 44095762                                 # 神圣防护罩-反射镜力-（陷阱卡）
FLIP_REC = {"type": 0x200021, "level": 3, "attribute": 0x20, "race": 0x8, "atk": 1000, "def": 1000}
EQUIP_REC = {"type": 0x40002, "level": 0, "attribute": 0, "race": 0, "atk": 0, "def": 0}

both_banish = card(100009711, "积木·双方除外陷阱", "monster", [
    new("effect", type="quick_o", range="hand",
        condition=[new("all_of", items=[new("turn", player="opp"), new("phase", phase="main")])],
        cost=[new("discard", cards=[new("this_card")])],
        operation=[new("each_player", body=[
            new("banish", cards=[new("pick", who="you", where="deck", count=1, filter=[new("f_kind", kind="trap")])])])])])

equip_spell = card(100009712, "积木·装备之剑", "spell", [
    new("effect", type="activate",
        target=[new("take_target", count=1, **{"as": "T"},
                    source=[new("all", who="both", where="mzone",
                                       filter=[new("f_position", position="faceup"), new("f_kind", kind="monster")])])],
        operation=[new("equip", cards=[new("this_card")], to=[new("target", name="T")])]),
    new("continuous", mode="equipped", code="EFFECT_UPDATE_ATTACK", value=[new("num", value=500)])])
equip_spell["card"]["subtypes"] = ["equip"]

flip_mon = card(100009713, "积木·反转破坏者", "monster", [
    new("effect", type="flip", operation=[
        new("destroy", cards=[new("pick", who="opp", where="field", count=1)])])])

battle_draw = card(100009714, "积木·战殁抽卡", "monster", [
    new("effect", type="trigger_o", event="battle_destroyed", operation=[new("draw", player="you", count=1)])])

listener = card(100009715, "积木·召唤鼓舞", "monster", [
    new("effect", type="listener", event="monster_summoned", event_player="you", range="mzone", operation=[
        new("register", code="EFFECT_UPDATE_ATTACK", reset="permanent", cards=[new("this_card")],
            value=[new("num", value=300)])])])


TWIN, THUNDER = 54752875, 31786629                # 双头雷龙 = 雷龙＋雷龙
CHAOS_SOLDIER, MESSENGER = 5405694, 44656491      # 混沌战士（8星仪式）、和平使者（永续魔法）

fusion = card(100009716, "积木·融合", "spell", [
    new("effect", type="activate", operation=[new("fusion_summon", mats="hf")])])

ritual = card(100009717, "积木·仪式", "spell", [
    new("effect", type="activate", operation=[new("ritual_summon", level="greater", **{"from": "hand"})])])

place = card(100009718, "积木·放置", "spell", [
    new("effect", type="activate", operation=[
        new("place", where="szone", cards=[new("pick", who="you", where="deck", count=1,
                                               filter=[new("f_kind", kind="spell"), new("f_subtype", subtype="continuous")])])])])

different = card(100009719, "积木·卡名不同检索", "spell", [
    new("effect", type="activate", operation=[
        new("to_hand", cards=[new("pick", who="you", where="deck", count=2, different="yes",
                                  filter=[new("f_kind", kind="monster")])])])])

facedown = card(100009720, "积木·里侧特召", "spell", [
    new("effect", type="activate", operation=[
        new("special_summon", position="facedown", cards=[new("pick", who="you", where="hand", count=1,
                                                              filter=[new("f_kind", kind="monster")])])])])


XYZ_REC = {"type": 0x800021, "level": 4, "attribute": 0x20, "race": 0x8, "atk": 2000, "def": 1000}

attach = card(100009721, "积木·吸收素材", "monster", [
    new("effect", type="ignition", operation=[
        new("attach", cards=[new("pick", who="you", where="grave", count=1, filter=[new("f_kind", kind="monster")])],
            to=[new("this_card")])])])

equip_boost = card(100009722, "积木·强化装备", "spell", [
    new("effect", type="activate",
        target=[new("take_target", count=1, **{"as": "T"},
                    source=[new("all", who="both", where="mzone",
                                filter=[new("f_position", position="faceup"), new("f_kind", kind="monster")])])],
        operation=[new("equip", cards=[new("this_card")], to=[new("target", name="T")])]),
    new("effect", type="ignition", range="szone", limit="card", operation=[
        new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn", cards=[new("equip_target")],
            value=[new("num", value=1000)])])])
equip_boost["card"]["subtypes"] = ["equip"]

flagged = card(100009723, "积木·标记", "monster", [
    new("effect", type="ignition", limit="card", operation=[
        new("draw", player="you", count=1), new("set_flag", on="card", name=1, reset="end_of_turn")]),
    new("effect", type="ignition", limit="card", condition=[new("has_flag", on="card", name=1)], operation=[
        new("recover", player="you", amount=[new("num", value=1000)])])])

unique = card(100009724, "积木·唯一", "monster", [new("unique", who="you")])

summed = card(100009725, "积木·合计伤害", "monster", [
    new("effect", type="ignition", operation=[
        new("damage", player="opp", amount=[new("sum_of", stat="atk",
                                                cards=[new("all", who="you", where="mzone")])])])])


IRON_WALL = 30459350                              # 王宫的铁壁（双方不能把卡除外）

drawn_today = [new("turn_count", player="you", what="draw")]
greed_cost = card(100009726, "积木·贪欲的代价", "spell", [
    new("effect", type="activate", operation=[
        new("draw", player="you", count=2),
        new("delay", when="this_end", body=[
            new("banish", face="down", cards=[new("deck_top", who="you", count_n=[dict(drawn_today[0])])]),
            new("fail", body=[new("draw", player="opp", count_n=[dict(drawn_today[0])])])])])])

revive_until_end = card(100009727, "积木·一时苏生", "spell", [
    new("effect", type="activate", operation=[
        new("special_summon", cards=[new("pick", who="you", where="grave", count=1, filter=[new("f_kind", kind="monster")])]),
        new("delay", when="this_end", carry="yes", body=[new("destroy", cards=[new("carried")])])])])


opp_monsters = new("count_of", cards=[new("all", who="opp", where="mzone")])
mill_by_count = card(100009728, "积木·按数送墓", "spell", [
    new("effect", type="activate", operation=[
        new("send_to_gy", cards=[new("pick", who="you", where="deck", count=1, count_n=[opp_monsters],
                                     filter=[new("f_kind", kind="monster")])])])])

burn_destroyed = card(100009729, "积木·破坏烧伤", "spell", [
    new("effect", type="activate", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone")]),
        new("after", body=[new("damage", player="opp", amount=[
            new("math", op="*", left=[new("count_of", cards=[new("operated")])], right=[new("num", value=500)])])])])])

weaker = card(100009730, "积木·以下破坏", "monster", [
    new("effect", type="ignition", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone", filter=[
            new("f_atk", op="<=", value_n=[new("atk_of", card=[new("this_card")])])])])])])

upto_two = card(100009731, "积木·最多两只", "spell", [
    new("effect", type="activate", operation=[
        new("to_hand", cards=[new("pick", who="you", where="deck", count=2, upto="yes",
                                  filter=[new("f_kind", kind="monster")])])])])


spell_proof = card(100009732, "积木·魔法免疫", "monster", [
    new("continuous", mode="self", code="EFFECT_INDESTRUCTABLE_EFFECT", value_cards=[new("f_kind", kind="spell")])])

two_targets = card(100009733, "积木·一换一", "spell", [
    new("effect", type="activate",
        target=[new("take_target", count=1, **{"as": "A"}, source=[new("all", who="you", where="mzone")]),
                new("take_target", count=1, **{"as": "B"}, source=[new("all", who="opp", where="mzone")])],
        operation=[new("to_hand", cards=[new("target", name="A")]),
                   new("destroy", cards=[new("target", name="B")])])])

damage_heal = card(100009734, "积木·伤害回复", "monster", [
    new("effect", type="trigger_f", event="player_battle_damaged", event_player="any", range="mzone", operation=[
        new("recover", player="you", amount=[new("event_value")])])])

deck_or_grave = card(100009735, "积木·卡组墓地检索", "spell", [
    new("effect", type="activate", operation=[
        new("to_hand", cards=[new("pick", who="you", where="deck_grave", count=1,
                                  filter=[new("f_name", code=756652, name="多隆")])])])])


MONSTER_REBORN = 83764718                         # 死者苏生（魔法卡）
HIGH_REC = {"type": 0x21, "level": 7, "attribute": 0x20, "race": 0x8, "atk": 2500, "def": 2000}

cyber_like = card(100009736, "积木·电子龙式", "monster", [
    new("sp_proc", range="hand", condition=[new("all_of", items=[
        new("not_cond", item=[new("exists", cards=[new("all", who="you", where="mzone")])]),
        new("exists", cards=[new("all", who="opp", where="mzone")])])])])

grave_proc = card(100009737, "积木·墓地苏醒", "monster", [
    new("summon_rule", normal="no", special="proc_only"),
    new("sp_proc", range="grave", limit="once", cost=[
        new("banish", cards=[new("pick", who="you", where="grave", count=2, filter=[new("f_kind", kind="monster")])])])])

no_tribute = card(100009738, "积木·妥协召唤", "monster", [new("ns_proc")])

spell_only = card(100009739, "积木·魔法苏生限定", "monster", [
    new("summon_rule", normal="no", special="by_cards", by=[new("f_kind", kind="spell")])])


POLYMERIZATION = 24094653                         # 融合
FUSION_REC = {"type": 0x41, "level": 6, "attribute": 0x10, "race": 0x2000, "atk": 2600, "def": 2000}
diy_fusion = card(100009740, "积木·龙骑士", "monster", [
    new("fusion_materials", count=1, first=[new("f_race", race="warrior")], second=[new("f_race", race="dragon")])])


POT, BURIAL, SOUL_RELEASE = 55144522, 81439173, 5758500   # 强欲之壶、愚蠢的埋葬、魂之解放

own_to_grave = card(100009741, "积木·墓地感应", "monster", [
    new("effect", type="trigger_o", event="cards_to_grave", event_player="you", range="mzone", operation=[
        new("draw", player="you", count=1)])])

grave_or_banish = card(100009742, "积木·去哪都抽", "monster", [
    new("effect", type="trigger_o", event="to_grave", event2="banished", operation=[new("draw", player="you", count=1)])])

same_level = card(100009743, "积木·同级苏生", "spell", [
    new("effect", type="activate", operation=[
        new("select", player="you", count=1, **{"as": "A"}, source=[new("all", who="opp", where="mzone")]),
        new("special_summon", cards=[new("pick", who="you", where="grave", count=1, filter=[
            new("f_level", op="==", value_n=[new("level_of", card=[new("var", name="A")])])])])])])


JUNK_SYNCHRON = 63977008                          # 废品同调士（3星调整）
SYNCHRO_REC = {"type": 0x2021, "level": 5, "attribute": 0x10, "race": 0x1, "atk": 2300, "def": 1400}
XYZ4_REC = {"type": 0x800021, "level": 4, "attribute": 0x10, "race": 0x4000, "atk": 2000, "def": 1500}
LINK_REC = {"type": 0x4000021, "level": 2, "attribute": 0x10, "race": 0x1, "atk": 1600, "def": 0x28}

diy_synchro = card(100009744, "积木·战士同调", "monster", [
    new("extra_materials", method="synchro", count=1, more="yes", material=[new("f_race", race="warrior")])])
diy_xyz = card(100009745, "积木·兽族超量", "monster", [
    new("extra_materials", method="xyz", count=2, rank=4, material=[new("f_race", race="beast")])])
diy_link = card(100009746, "积木·战士连接", "monster", [
    new("extra_materials", method="link", count=2, include=[new("f_race", race="warrior")])])

dragon_or_warrior = card(100009747, "积木·龙或战士", "spell", [
    new("effect", type="activate", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone", filter=[
            new("f_any", items=[new("f_race", race="dragon"), new("f_race", race="warrior")])])])])])

cost_atk_burn = card(100009748, "积木·代价烧伤", "spell", [
    new("effect", type="activate",
        cost=[new("banish", cards=[new("pick", who="you", where="grave", count=1, filter=[new("f_kind", kind="monster")])])],
        operation=[new("damage", player="opp", amount=[new("atk_of", card=[new("cost_cards")])])])])


strongest = card(100009749, "积木·击倒最强", "spell", [
    new("effect", type="activate", operation=[
        new("destroy", cards=[new("max_of", stat="atk", which="max", cards=[new("all", who="opp", where="mzone")])])])])

level_sum = card(100009750, "积木·等级合计", "spell", [
    new("effect", type="activate", operation=[
        new("select", player="you", count=1, sum="level_eq", sum_n=[new("num", value=6)], **{"as": "A"},
            source=[new("all", who="you", where="deck", filter=[new("f_kind", kind="monster")])]),
        new("send_to_gy", cards=[new("var", name="A")])])])


SOLEMN = 41420027                                 # 神之宣告（反击陷阱）
no_response = card(100009751, "积木·不许对应", "spell", [
    new("effect", type="activate", chain_limit="opp", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone")])])])


same_column = card(100009752, "积木·纵列破坏", "monster", [
    new("effect", type="ignition", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_same_column")])])])])


replace_self = card(100009753, "积木·替身", "monster", [
    new("destroy_replace", mode="self", range="mzone", cost=[new("pay_lp", amount=[new("num", value=500)])])])

hand_random = card(100009754, "积木·随机丢弃", "spell", [
    new("effect", type="activate", operation=[
        new("send_to_gy", cards=[new("random_pick", who="opp", where="hand", count=1)])])])

temp_banish = card(100009755, "积木·暂时除外", "spell", [
    new("effect", type="activate", operation=[
        new("banish", temp="yes", cards=[new("all", who="opp", where="mzone")]),
        new("delay", when="this_end", carry="yes", body=[new("return_to_field", cards=[new("carried")])])])])


spirit = card(100009756, "积木·灵魂", "monster", [new("monster_trait", trait="spirit")])

gemini = card(100009757, "积木·二重", "monster", [
    new("monster_trait", trait="gemini"),
    new("effect", type="ignition", range="mzone", condition=[new("gemini_state")], operation=[
        new("damage", player="opp", amount=[new("num", value=500)])])])

trap_mon = card(100009758, "积木·陷阱怪兽", "trap", [
    new("effect", type="activate", operation=[
        new("trap_monster", mtype="normal", level=4, atk=1600, **{"def": 1800}, race="reptile", attribute="earth")])])


summon_more = card(100009759, "积木·追加召唤", "spell", [
    new("effect", type="activate", operation=[new("normal_summon", filter=[new("f_race", race="warrior")])])])


haunted = card(100009760, "积木·活死人", "trap", [
    new("effect", type="activate",
        target=[new("take_target", count=1, **{"as": "T"},
                    source=[new("all", who="you", where="grave", filter=[new("f_kind", kind="monster")])])],
        operation=[new("special_summon", cards=[new("target", name="T")]), new("keep_target", cards=[new("target", name="T")])]),
    new("target_link", link="leave_destroy", range="szone"),
    new("target_link", link="target_destroyed", range="szone"),
    new("continuous", mode="card_target", code="EFFECT_UPDATE_ATTACK", range="szone", value=[new("num", value=300)])])


contact = card(100009761, "积木·接触融合", "monster", [
    new("fusion_materials", count=1, contact="deck", first=[new("f_name", code=DORON)], second=[new("f_name", code=LV4)])])

opp_tribute = card(100009762, "积木·解放对方", "monster", [new("ns_proc", tribute=1, opp="yes")])


swap_effect = card(100009763, "积木·偷天换日", "trap", [
    new("effect", type="activate", event="chaining", event_player="opp",
        operation=[new("change_chain_effect", body=[new("recover", amount=[new("num", value=1000)])])])])


gift = card(100009764, "积木·礼物", "spell", [
    new("effect", type="activate", operation=[new("to_hand", to="opp", cards=[new("pick", who="you", where="hand", count=1)])])])

field_call = card(100009765, "积木·召来场地", "spell", [
    new("effect", type="activate", operation=[
        new("activate_card", where="deck", filter=[new("f_subtype", subtype="field")])])])


burial = card(100009766, "积木·清闲", "spell", [new("effect", type="activate", operation=[
    new("select", player="you", count=1, **{"as": "A"}, source=[new("all", who="you", where="deck")]),
    new("send_to_gy", cards=[new("var", name="A")]),
    new("register_player", player="you", code="EFFECT_CANNOT_ACTIVATE", reset="end_of_turn",
        filter=[new("f_same_code", card=[new("var", name="A")])])])])


decay = card(100009767, "积木·渐衰", "monster", [
    new("effect", type="listener", event="standby", event_player="you", range="mzone",
        operation=[new("register", code="EFFECT_UPDATE_ATTACK", reset="permanent", cards=[new("this_card")],
                       value=[new("num", value=-200)])])])

countdown = card(100009769, "积木·倒数", "spell", [
    new("effect", type="listener", event="end", event_player="opp", range="szone", operation=[
        new("set_flag", on="card", name=1, reset="permanent"),
        new("if", cond=[new("compare", op=">=", left=[new("flag_count", on="card", name=1)], right=[new("num", value=2)])],
            then=[new("destroy", cards=[new("this_card")])])])])

twice = card(100009768, "积木·两次", "monster", [
    new("effect", type="ignition", range="mzone", limit="card",
        twice_when=[new("exists", cards=[new("all", who="you", where="mzone", filter=[new("f_name", code=DORON)])])],
        operation=[new("damage", player="opp", amount=[new("num", value=100)])])])


two_places = card(100009770, "积木·两处发动", "monster", [
    new("effect", type="ignition", range="hand_grave", limit="name",
        operation=[new("special_summon", cards=[new("this_card")])])])


two_races = card(100009771, "积木·龙与战士", "spell", [
    new("effect", type="activate", operation=[
        new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_race", race="dragon+warrior")])])])])


many_events = card(100009772, "积木·召唤时抽卡", "monster", [
    new("effect", type="trigger_o", event="spsummon+summon+flip_summon", operation=[new("draw", count=1)])])

twice_a_turn = card(100009773, "积木·1回合2次", "monster", [
    new("effect", type="ignition", range="mzone", limit="card", limit_n=2,
        operation=[new("damage", player="opp", amount=[new("num", value=100)])])])


end_of_ss = card(100009774, "积木·特召回合结束送墓", "monster", [
    new("effect", type="ignition", range="hand", operation=[new("special_summon", cards=[new("this_card")])]),
    new("effect", type="listener", event="spsummon", operation=[new("set_flag", on="card", name=1, reset="end_of_turn")]),
    new("effect", type="trigger_f", event="end", range="mzone", condition=[new("has_flag", on="card", name=1)], operation=[
        new("send_to_gy", cards=[new("this_card")]),
        new("after", how="then", body=[new("may", ask="是否从墓地把战士族怪兽加入手卡？", body=[
            new("to_hand", cards=[new("pick", who="you", where="grave", count=1,
                                      filter=[new("f_race", race="warrior"), new("f_kind", kind="monster")])])])])])])


def act(p, do, c=None, **kw):
    a = {"player": p, "do": do}
    if c is not None:
        a["card"] = c
    a.update(kw)
    return a


def chk(kind, **kw):
    return dict({"check": kind}, **kw)


CASES = [
    ("雷击", raigeki, SPELL, "对方场上的怪兽全部破坏。",
     [{"field": {"0": {"hand": [100009701]}, "1": {"mzone": [BE, DORON]}},
       "actions": [act(0, "activate", 100009701), chk("count", player=1, **{"in": "mzone"}, eq=0)]}],
     ("tp,0,LOCATION_MZONE", "tp,LOCATION_MZONE,0")),
    ("增援", rota, SPELL, "从卡组把1只4星以下的战士族怪兽加入手卡。",
     [{"field": {"0": {"hand": [100009702], "deck": [BE, LV4, DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009702), chk("count", player=0, card=DORON, **{"in": "hand"}, eq=1)]}],
     ("c:IsRace(RACE_WARRIOR)", "c:IsRace(RACE_DRAGON)")),
    ("没有官方先例的卡", wild, WILD_REC, "①：对方抽卡的场合发动。这张卡的攻击力上升100。这张卡的攻击力是3000以上的场合，自己决斗胜利。",
     [{"field": {"0": {"mzone": [100009703]}, "1": {}},
       "actions": [act(0, "end_turn"), chk("win", player=0)]}],
     ("SetValue(100)", "SetValue(50)")),
    ("代价与取对象", cost_target, SPELL, "把1张手卡丢弃，以对方场上1只怪兽为对象才能发动。那只怪兽破坏。",
     [{"field": {"0": {"hand": [100009704, DORON]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "activate", 100009704), chk("count", player=1, **{"in": "mzone"}, eq=0),
                   chk("count", player=0, **{"in": "hand"}, eq=0), chk("count", player=0, **{"in": "grave"}, eq=2)]}],
     ("Duel.Destroy(tc,", "Duel.Destroy(c,")),
    ("自肃", restrict, MON, "这个卡名的效果1回合只能使用1次。\n①：支付1000基本分才能发动。自己从卡组抽1张。这个回合，自己不能把怪兽召唤。",
     [{"field": {"0": {"mzone": [100009705], "hand": [DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009705), chk("lp", player=0, eq=7000), chk("count", player=0, **{"in": "hand"}, eq=2),
                   chk("offered", card=DORON, **{"as": "summon"}, eq=False),
                   chk("offered", card=100009705, **{"as": "activate"}, eq=False)]}],
     ("EFFECT_CANNOT_SUMMON", "EFFECT_CANNOT_MSET")),
    ("永续效果", aura, MON, "①：只要这张卡在怪兽区域存在，自己场上的战士族怪兽的攻击力上升500。",
     [{"field": {"0": {"mzone": [100009706, DORON]}, "1": {}},
       "actions": [chk("atk", player=0, card=DORON, eq=1400), chk("atk", player=0, card=100009706, eq=1500)]}],
     ("SetValue(500)", "SetValue(0)")),
    ("●选项", options, SPELL, "从以下效果选择1个适用。\n●自己从卡组抽1张。\n●给与对方500伤害。",
     [{"field": {"0": {"hand": [100009707]}, "1": {}},
       "actions": [act(0, "activate", 100009707), chk("count", player=0, **{"in": "hand"}, eq=1), chk("lp", player=1, eq=8000)]},
      {"field": {"0": {"hand": [100009707]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "activate", 100009707), {"player": 0, "do": "option", "index": 1},
                   chk("lp", player=1, eq=7500), chk("count", player=0, **{"in": "hand"}, eq=0)]}],
     ("Duel.Damage(1-tp,", "Duel.Damage(tp,")),
    ("连锁无效", ash, TRAP_MON, "这个卡名的效果1回合只能使用1次。\n①：对方把卡的效果发动时，把这张卡从手卡丢弃才能发动。那个发动无效并破坏。",
     [{"field": {"0": {"hand": [RAIGEKI]}, "1": {"hand": [100009708], "mzone": [BE]}},
       "actions": [act(0, "activate", RAIGEKI), act(1, "activate", 100009708),
                   chk("count", player=1, **{"in": "mzone"}, eq=1), chk("count", player=1, **{"in": "hand"}, eq=0)]}],
     ("rp==1-tp", "rp==tp")),
    ("衍生物与对每一张", tokens_, SPELL, "在自己场上把2只「积木衍生物」（战士族·光·1星·攻0/守0）特殊召唤。自己场上的战士族怪兽的攻击力直到回合结束时各上升300。",
     [{"field": {"0": {"hand": [100009709]}, "1": {}},
       "actions": [act(0, "activate", 100009709), chk("count", player=0, **{"in": "mzone"}, eq=2),
                   chk("atk", player=0, card=100009710, eq=300)]}],
     ("SetValue(300)", "SetValue(0)")),
    ("双方各自", both_banish, MON, "①：对方主要阶段，把这张卡从手卡丢弃才能发动。双方各自从卡组把1张陷阱卡除外。",
     [{"field": {"0": {"hand": [RAIGEKI], "deck": [MIRROR]}, "1": {"hand": [100009711], "mzone": [BE], "deck": [MIRROR]}},
       "actions": [act(0, "activate", RAIGEKI), act(1, "activate", 100009711),
                   chk("count", player=0, **{"in": "banished"}, eq=1), chk("count", player=1, **{"in": "banished"}, eq=1)]}],
     ("local tp=p", "local tp=tp")),
    ("装备魔法", equip_spell, EQUIP_REC, "①：以场上1只表侧表示怪兽为对象才能发动。把这张卡给那只怪兽装备。\n②：装备怪兽的攻击力上升500。",
     [{"field": {"0": {"hand": [100009712], "mzone": [DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009712), chk("atk", player=0, card=DORON, eq=1400),
                   chk("count", player=0, **{"in": "szone"}, eq=1)]}],
     ("SetValue(500)", "SetValue(0)")),
    ("反转效果", flip_mon, FLIP_REC, "反转：选对方场上1张卡破坏。",
     [{"field": {"0": {"mzone": [{"code": 100009713, "pos": "set"}]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "reposition", 100009713), chk("count", player=1, **{"in": "mzone"}, eq=0)]}],
     ("tp,0,LOCATION_ONFIELD", "tp,0,LOCATION_HAND")),
    ("被战斗破坏", battle_draw, MON, "①：这张卡被战斗破坏的场合才能发动。自己从卡组抽1张。",
     [{"field": {"0": {"mzone": [100009714]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "battle"), act(0, "attack", 100009714, target=BE),
                   chk("count", player=0, **{"in": "hand"}, eq=1)]}],
     ("Duel.Draw(tp,1", "Duel.Draw(tp,0")),
    ("每次……（不入连锁）", listener, MON, "①：每次自己把怪兽召唤，这张卡的攻击力上升300。",
     [{"field": {"0": {"mzone": [100009715], "hand": [DORON]}, "1": {}},
       "actions": [act(0, "summon", DORON), chk("atk", player=0, card=100009715, eq=1800)]}],
     ("SetValue(300)", "SetValue(0)")),
    ("融合召唤", fusion, SPELL, "自己的手卡·场上的怪兽作为融合素材，从额外卡组把1只融合怪兽融合召唤。",
     [{"field": {"0": {"hand": [100009716, THUNDER, THUNDER], "extra": [TWIN]}, "1": {}},
       "actions": [act(0, "activate", 100009716), chk("count", player=0, card=TWIN, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, card=THUNDER, **{"in": "grave"}, eq=2)]}],
     ("mat_location=LOCATION_HAND+LOCATION_MZONE", "mat_location=LOCATION_MZONE")),
    ("仪式召唤", ritual, SPELL, "等级合计直到变成仪式召唤的怪兽的等级以上为止，把自己的手卡·场上的怪兽解放，从手卡把1只仪式怪兽仪式召唤。",
     [{"field": {"0": {"hand": [100009717, CHAOS_SOLDIER, BE]}, "1": {}},
       "actions": [act(0, "activate", 100009717), chk("count", player=0, card=CHAOS_SOLDIER, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, card=BE, **{"in": "grave"}, eq=1)]}],
     (",LOCATION_HAND)(e", ",LOCATION_GRAVE)(e")),
    ("放置到场上", place, SPELL, "从卡组把1张永续魔法卡在自己场上表侧表示放置。",
     [{"field": {"0": {"hand": [100009718], "deck": [MESSENGER]}, "1": {}},
       "actions": [act(0, "activate", 100009718), chk("count", player=0, card=MESSENGER, **{"in": "szone"}, eq=1)]}],
     ("TYPE_CONTINUOUS", "TYPE_FIELD")),
    ("卡名各不相同", different, SPELL, "从卡组把卡名不同的2只怪兽加入手卡。",
     [{"field": {"0": {"hand": [100009719], "deck": [BE, BE, LV4]}, "1": {}},
       "actions": [act(0, "activate", 100009719), chk("count", player=0, card=BE, **{"in": "hand"}, eq=1),
                   chk("count", player=0, card=LV4, **{"in": "hand"}, eq=1)]},
      {"field": {"0": {"hand": [100009719], "deck": [BE]}, "1": {}},     # 卡组里只有青眼白龙：不能发动
       "actions": [chk("offered", card=100009719, **{"as": "activate"}, eq=False)]}],
     ("GetClassCount(Card.GetCode)>=2", "GetClassCount(Card.GetCode)>=1")),
    ("里侧特殊召唤", facedown, SPELL, "从手卡把1只怪兽里侧守备表示特殊召唤。",
     [{"field": {"0": {"hand": [100009720, DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009720), chk("faceup", player=0, card=DORON, **{"in": "mzone"}, eq=False)]}],
     ("false,false,POS_FACEDOWN_DEFENSE)", "false,false,POS_FACEUP_ATTACK)")),
    ("作为超量素材", attach, XYZ_REC, "①：自己主要阶段才能发动。把自己墓地1只怪兽在这张卡下面重叠作为超量素材。",
     [{"field": {"0": {"mzone": [{"code": 100009721, "materials": [DORON]}], "grave": [LV4]}, "1": {}},
       "actions": [act(0, "activate", 100009721), chk("overlay", player=0, card=100009721, eq=2)]}],
     ("Duel.Overlay(", "Duel.Remove(")),
    ("装备怪兽", equip_boost, EQUIP_REC, "①：以场上1只表侧表示怪兽为对象才能发动。把这张卡给那只怪兽装备。\n②：1回合1次，自己主要阶段才能发动。装备怪兽的攻击力直到回合结束时上升1000。",
     [{"field": {"0": {"hand": [100009722], "mzone": [DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009722), act(0, "activate", 100009722),
                   chk("atk", player=0, card=DORON, eq=1900)]}],
     ("SetValue(1000)", "SetValue(0)")),
    ("标记", flagged, MON, "①：1回合1次，自己主要阶段才能发动。自己从卡组抽1张。\n②：1回合1次，这张卡有标记1的场合才能发动。自己回复1000基本分。",
     [{"field": {"0": {"mzone": [100009723]}, "1": {}},
       "actions": [act(0, "activate", 100009723), act(0, "activate", 100009723),
                   chk("lp", player=0, eq=9000), chk("count", player=0, **{"in": "hand"}, eq=1)]}],
     ("GetFlagEffect(id+1)>0", "GetFlagEffect(id+1)>1")),
    ("场上只能存在1张", unique, MON, "「积木·唯一」在自己场上只能有1张表侧表示存在。",
     [{"field": {"0": {"mzone": [100009724], "hand": [100009724]}, "1": {}},
       "actions": [chk("offered", card=100009724, **{"as": "summon"}, eq=False)]}],
     ("c:SetUniqueOnField(1,0,id)", "")),
    ("攻击力合计", summed, MON, "①：自己主要阶段才能发动。给与对方自己场上的怪兽的攻击力合计数值的伤害。",
     [{"field": {"0": {"mzone": [100009725, DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009725), chk("lp", player=1, eq=5600)]}],
     ("GetSum(Card.GetAttack)", "GetSum(Card.GetDefense)")),
    ("之后再处理·这个回合抽卡数", greed_cost, SPELL, "自己从卡组抽2张。这个回合的结束阶段，自己卡组上面这个回合自己抽卡的数量的卡里侧表示除外。不能除外的场合，对方从卡组抽这个回合自己抽卡的数量的卡。",
     [{"field": {"0": {"hand": [100009726]}, "1": {}},
       "actions": [act(0, "activate", 100009726), act(0, "end_turn"),
                   chk("count", player=0, **{"in": "banished"}, eq=2), chk("count", player=1, **{"in": "hand"}, eq=1)]},
      {"field": {"0": {"hand": [100009726]}, "1": {"szone": [{"code": IRON_WALL, "pos": "faceup"}]}},    # 不能除外
       "actions": [act(0, "activate", 100009726), act(0, "end_turn"),
                   chk("count", player=0, **{"in": "banished"}, eq=0), chk("count", player=1, **{"in": "hand"}, eq=3)]}],
     ("for i=1,#eg do", "for i=1,1 do")),
    ("之后再处理·带上的卡", revive_until_end, SPELL, "从墓地把1只怪兽特殊召唤。这个回合的结束阶段，这个效果特殊召唤的怪兽破坏。",
     [{"field": {"0": {"hand": [100009727], "grave": [DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009727), chk("count", player=0, card=DORON, **{"in": "mzone"}, eq=1),
                   act(0, "end_turn"), chk("count", player=0, card=DORON, **{"in": "grave"}, eq=1)]}],
     ("GetFlagEffectLabel(id+80)==fid", "GetFlagEffectLabel(id+80)==0")),
    ("张数是算出来的", mill_by_count, SPELL, "从卡组把对方场上的怪兽数量的怪兽送去墓地。",
     [{"field": {"0": {"hand": [100009728]}, "1": {"mzone": [BE, DORON]}},
       "actions": [act(0, "activate", 100009728), chk("count", player=0, **{"in": "grave"}, eq=3)]}],
     ("tp,0,LOCATION_MZONE,nil", "tp,LOCATION_MZONE,0,nil")),
    ("这个效果破坏的数量", burn_destroyed, SPELL, "对方场上的怪兽全部破坏。那之后，给与对方这个效果破坏的卡的数量×500数值的伤害。",
     [{"field": {"0": {"hand": [100009729]}, "1": {"mzone": [BE, DORON]}},
       "actions": [act(0, "activate", 100009729), chk("lp", player=1, eq=7000)]}],
     ("*500)", "*400)")),
    ("和算出来的数值比", weaker, MON, "①：自己主要阶段才能发动。对方场上的攻击力在这张卡的攻击力以下的怪兽全部破坏。",
     [{"field": {"0": {"mzone": [100009730]}, "1": {"mzone": [BE, DORON]}},
       "actions": [act(0, "activate", 100009730), chk("count", player=1, card=BE, **{"in": "mzone"}, eq=1),
                   chk("count", player=1, card=DORON, **{"in": "grave"}, eq=1)]}],
     ("IsAttackBelow(e:GetHandler():GetAttack())", "IsAttackBelow(9999)")),
    ("最多几张", upto_two, SPELL, "从卡组把最多2只怪兽加入手卡。",
     [{"field": {"0": {"hand": [100009731], "deck": [LV4, DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009731), chk("count", player=0, **{"in": "hand"}, eq=1)]}],
     ("tp,LOCATION_DECK,0,1,2,", "tp,LOCATION_DECK,0,2,2,")),
    ("数值只对这样的卡成立", spell_proof, MON, "①：这张卡不会被魔法卡的效果破坏。",
     [{"field": {"0": {"hand": [RAIGEKI]}, "1": {"mzone": [100009732, BE]}},
       "actions": [act(0, "activate", RAIGEKI), chk("count", player=1, card=100009732, **{"in": "mzone"}, eq=1),
                   chk("count", player=1, card=BE, **{"in": "grave"}, eq=1)]}],
     ("IsType(TYPE_SPELL)", "IsType(TYPE_TRAP)")),
    ("两组对象", two_targets, SPELL, "以自己场上1只怪兽和对方场上1只怪兽为对象才能发动。作为对象的自己怪兽加入手卡。作为对象的对方怪兽破坏。",
     [{"field": {"0": {"hand": [100009733], "mzone": [DORON]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "activate", 100009733), chk("count", player=0, card=DORON, **{"in": "hand"}, eq=1),
                   chk("count", player=1, card=BE, **{"in": "grave"}, eq=1)]}],
     ("Duel.SendtoHand(tc_A", "Duel.SendtoHand(tc_B")),
    ("受到战斗伤害的数值", damage_heal, MON, "①：自己或者对方受到战斗伤害时发动。自己回复那个数值的基本分。",
     [{"field": {"0": {"mzone": [100009734]}, "1": {}},
       "actions": [act(0, "battle"), act(0, "attack", 100009734), chk("lp", player=1, eq=6500),
                   chk("lp", player=0, eq=9500)]}],
     ("Duel.Recover(tp,ev,", "Duel.Recover(tp,100,")),
    ("从几个区域选", deck_or_grave, SPELL, "从卡组·墓地把1张「多隆」加入手卡。",
     [{"field": {"0": {"hand": [100009735], "grave": [DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009735), chk("count", player=0, card=DORON, **{"in": "hand"}, eq=1)]}],
     ("LOCATION_DECK+LOCATION_GRAVE", "LOCATION_DECK")),
    ("特殊召唤手续", cyber_like, MON, "自己场上没有怪兽存在并且对方场上有怪兽存在的场合，这张卡可以从手卡特殊召唤。",
     [{"field": {"0": {"hand": [100009736]}, "1": {"mzone": [BE]}},
       "actions": [chk("offered", card=100009736, **{"as": "spsummon"}, eq=True), act(0, "spsummon", 100009736),
                   chk("count", player=0, card=100009736, **{"in": "mzone"}, eq=1)]},
      {"field": {"0": {"hand": [100009736], "mzone": [DORON]}, "1": {"mzone": [BE]}},
       "actions": [chk("offered", card=100009736, **{"as": "spsummon"}, eq=False)]}],
     ("Duel.GetLocationCount(tp,LOCATION_MZONE)>0 and", "false and")),
    ("不能通常召唤·墓地手续", grave_proc, MON, "这张卡不能通常召唤。把自己墓地2只怪兽除外的场合才能从墓地特殊召唤。「积木·墓地苏醒」的方法的特殊召唤1回合只能有1次。",
     [{"field": {"0": {"grave": [100009737, DORON, LV4]}, "1": {}},
       "actions": [act(0, "spsummon", 100009737), chk("count", player=0, card=100009737, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, **{"in": "banished"}, eq=2)]},
      {"field": {"0": {"hand": [100009737]}, "1": {}},
       "actions": [chk("offered", card=100009737, **{"as": "summon"}, eq=False),
                   chk("offered", card=100009737, **{"as": "mset"}, eq=False)]}],
     ("0,2,e:GetHandler(),e,tp)", "0,3,e:GetHandler(),e,tp)")),
    ("不用解放召唤", no_tribute, HIGH_REC, "这张卡可以不用解放作召唤。",
     [{"field": {"0": {"hand": [100009738]}, "1": {}},
       "actions": [act(0, "summon", 100009738), chk("count", player=0, card=100009738, **{"in": "mzone"}, eq=1)]}],
     ("minc==0", "minc==9")),
    ("只能用魔法卡的效果特殊召唤", spell_only, MON, "这张卡不能通常召唤。用魔法卡的效果才能特殊召唤。",
     [{"field": {"0": {"hand": [MONSTER_REBORN], "grave": [100009739]}, "1": {}},
       "actions": [act(0, "activate", MONSTER_REBORN), chk("count", player=0, card=100009739, **{"in": "mzone"}, eq=1)]}],
     ("IsType(TYPE_SPELL)", "IsType(TYPE_TRAP)")),
    ("融合素材", diy_fusion, FUSION_REC, "战士族怪兽＋龙族怪兽",
     [{"field": {"0": {"hand": [POLYMERIZATION, DORON, BE], "extra": [100009740]}, "1": {}},
       "actions": [act(0, "activate", POLYMERIZATION), chk("count", player=0, card=100009740, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, **{"in": "grave"}, eq=3)]}],
     ("RACE_DRAGON", "RACE_ZOMBIE")),
    ("别的卡的时机", own_to_grave, MON, "①：自己的卡被送去墓地的场合才能发动。自己从卡组抽1张。",
     [{"field": {"0": {"mzone": [100009741], "hand": [POT]}, "1": {}},
       "actions": [act(0, "activate", POT), chk("count", player=0, **{"in": "hand"}, eq=3)]}],
     ("eg:IsExists(Card.IsControler,1,nil,tp)", "eg:IsExists(Card.IsControler,1,nil,1-tp)")),
    ("一个效果两个时机", grave_or_banish, MON, "①：这张卡被送去墓地的场合或者被除外的场合才能发动。自己从卡组抽1张。",
     [{"field": {"0": {"hand": [BURIAL], "deck": [100009742]}, "1": {}},
       "actions": [act(0, "activate", BURIAL), chk("count", player=0, **{"in": "hand"}, eq=1)]},
      {"field": {"0": {"hand": [SOUL_RELEASE], "grave": [100009742]}, "1": {}},     # 被除外的场合
       "actions": [act(0, "activate", SOUL_RELEASE), chk("count", player=0, **{"in": "hand"}, eq=1)]}],
     ("c:RegisterEffect(e1x)", "")),
    ("卡片条件引用前面选的卡", same_level, SPELL, "自己从对方场上选1只怪兽（记作A）。从墓地把1只和记下的卡A相同等级的怪兽特殊召唤。",
     [{"field": {"0": {"hand": [100009743], "grave": [LV4, DORON]}, "1": {"mzone": [DORON]}},
       "actions": [act(0, "activate", 100009743), chk("count", player=0, card=DORON, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, card=LV4, **{"in": "grave"}, eq=1)]}],
     ("IsLevel(s.v_A:GetFirst():GetLevel())", "IsLevel(4)")),
    ("同调素材", diy_synchro, SYNCHRO_REC, "调整＋调整以外的战士族怪兽1只以上",
     [{"field": {"0": {"mzone": [JUNK_SYNCHRON, DORON], "extra": [100009744]}, "1": {}},
       "actions": [act(0, "spsummon", 100009744), chk("count", player=0, card=100009744, **{"in": "mzone"}, eq=1)]}],
     ("RACE_WARRIOR", "RACE_DRAGON")),
    ("超量素材", diy_xyz, XYZ4_REC, "兽族4星怪兽×2",
     [{"field": {"0": {"mzone": [LV4, LV4], "extra": [100009745]}, "1": {}},
       "actions": [act(0, "spsummon", 100009745), chk("overlay", player=0, card=100009745, eq=2)]}],
     ("RACE_BEAST", "RACE_DRAGON")),
    ("连接素材", diy_link, LINK_REC, "包含战士族怪兽的怪兽2只",
     [{"field": {"0": {"mzone": [DORON, LV4], "extra": [100009746]}, "1": {}},
       "actions": [act(0, "spsummon", 100009746), chk("count", player=0, card=100009746, **{"in": "mzone"}, eq=1)]}],
     ("RACE_WARRIOR", "RACE_FIEND")),
    ("卡片条件的或者", dragon_or_warrior, SPELL, "对方场上的龙族怪兽或者战士族怪兽全部破坏。",
     [{"field": {"0": {"hand": [100009747]}, "1": {"mzone": [BE, DORON, LV4]}},
       "actions": [act(0, "activate", 100009747), chk("count", player=1, **{"in": "mzone"}, eq=1),
                   chk("count", player=1, card=LV4, **{"in": "mzone"}, eq=1)]}],
     (") or (", ") and (")),
    ("作为代价的卡", cost_atk_burn, SPELL, "把自己墓地1只怪兽除外才能发动。给与对方作为代价的卡的攻击力数值的伤害。",
     [{"field": {"0": {"hand": [100009748], "grave": [BE]}, "1": {}},
       "actions": [act(0, "activate", 100009748), chk("lp", player=1, eq=5000)]}],
     ("GetFirst():GetAttack()", "GetFirst():GetDefense()")),
    ("攻击力最高的", strongest, SPELL, "对方场上的攻击力最高的怪兽破坏。",
     [{"field": {"0": {"hand": [100009749]}, "1": {"mzone": [BE, DORON, LV4]}},
       "actions": [act(0, "activate", 100009749), chk("count", player=1, card=BE, **{"in": "grave"}, eq=1),
                   chk("count", player=1, **{"in": "mzone"}, eq=2)]}],
     ("GetMaxGroup(Card.GetAttack)", "GetMinGroup(Card.GetAttack)")),
    ("等级合计正好", level_sum, SPELL, "从卡组把等级合计是6的怪兽送去墓地。",
     [{"field": {"0": {"hand": [100009750], "deck": [LV4, DORON, DORON]}, "1": {}},
       "actions": [act(0, "activate", 100009750), chk("count", player=0, **{"in": "grave"}, eq=3)]}],
     ("Card.GetLevel,6,1,99", "Card.GetLevel,99,1,99")),
    ("对方不能对应", no_response, SPELL, "对方场上的怪兽全部破坏。对方不能对应这个效果的发动把卡的效果发动。",
     [{"field": {"0": {"hand": [100009751]}, "1": {"mzone": [BE], "szone": [{"code": SOLEMN, "pos": "set"}]}},
       "actions": [act(0, "activate", 100009751), chk("offered", player=1, card=SOLEMN, **{"as": "chain"}, eq=False),
                   chk("count", player=1, **{"in": "mzone"}, eq=0)]}],
     ("Duel.SetChainLimit(s.chlimit)", "")),
    ("相同纵列", same_column, MON, "①：自己主要阶段才能发动。对方场上的和这张卡相同纵列的怪兽全部破坏。",
     [{"field": {"0": {"mzone": [{"code": 100009752, "seq": 2}]},
                 "1": {"mzone": [{"code": BE, "seq": 2}, {"code": DORON, "seq": 0}]}},
       "actions": [act(0, "activate", 100009752), chk("count", player=1, card=BE, **{"in": "grave"}, eq=1),
                   chk("count", player=1, card=DORON, **{"in": "mzone"}, eq=1)]}],
     ("GetColumnGroup():IsContains(c)", "GetLinkedGroup():IsContains(c)")),
    ("代替破坏", replace_self, MON, '这张卡被战斗·效果破坏的场合，可以作为代替支付500基本分。',
     [{"field": {"0": {"mzone": [100009753]}, "1": {"hand": [RAIGEKI]}},
       "actions": [act(0, "end_turn"), act(1, "activate", RAIGEKI), chk("count", player=0, card=100009753, **{"in": "mzone"}, eq=1),
                   chk("lp", player=0, eq=7500)]}],
     ("Duel.SelectEffectYesNo(tp,e:GetHandler(),96)", "false")),
    ("随机选", hand_random, SPELL, '随机选对方手卡1张卡送去墓地。',
     [{"field": {"0": {"hand": [100009754]}, "1": {"hand": [BE, DORON]}},
       "actions": [act(0, "activate", 100009754), chk("count", player=1, **{"in": "hand"}, eq=1),
                   chk("count", player=1, **{"in": "grave"}, eq=1)]}],
     ("RandomSelect(tp,1)", "RandomSelect(tp,2)")),
    ("暂时除外再回来", temp_banish, SPELL, '对方场上的怪兽全部除外。这个回合的结束阶段，这个效果除外的卡回到场上。',
     [{"field": {"0": {"hand": [100009755]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "activate", 100009755), chk("count", player=1, **{"in": "banished"}, eq=1),
                   act(0, "end_turn"), chk("count", player=1, card=BE, **{"in": "mzone"}, eq=1)]}],
     ("Duel.ReturnToField(rf)", "")),
    ("灵魂：结束阶段回手", spirit, MON, '这张卡召唤·反转的回合的结束阶段发动。这张卡回到持有者手卡。',
     [{"field": {"0": {"hand": [100009756]}},
       "actions": [act(0, "summon", 100009756), act(0, "end_turn"), chk("count", player=0, card=100009756, **{"in": "hand"}, eq=1)]}],
     ("aux.EnableSpiritReturn(c,EVENT_SUMMON_SUCCESS,EVENT_FLIP)", "")),
    ("二重：再度召唤后才有效果", gemini, dict(MON, type=0x21 | 0x800), '这张卡在场上·墓地存在的场合，当作通常怪兽使用。场上的表侧表示的这张卡可以作为通常召唤再1次召唤，那个场合这张卡变成当作效果怪兽使用并得到以下效果。\n①：这张卡再度召唤的状态的场合才能发动。给与对方500伤害。',
     [{"field": {"0": {"hand": [100009757]}},
       "actions": [act(0, "summon", 100009757), chk("offered", player=0, card=100009757, **{"as": "activate"}, eq=False),
                   act(0, "end_turn"), act(1, "end_turn"), act(0, "summon", 100009757),
                   act(0, "activate", 100009757), chk("lp", player=1, eq=7500)]}],
     ("aux.IsDualState(e)", "true")),
    ("陷阱怪兽", trap_mon, dict(SPELL, type=0x4, level=4, atk=1600, race=0x800, attribute=0x1, **{"def": 1800}), '这张卡发动后变成通常怪兽（爬虫类族·地属性·4星·攻1600/守1800）在怪兽区域特殊召唤（也当作陷阱卡使用）。',
     [{"field": {"0": {"szone": [{"code": 100009758, "pos": "set"}]}},
       "actions": [act(0, "activate", 100009758), chk("count", player=0, card=100009758, **{"in": "mzone"}, eq=1),
                   chk("atk", player=0, card=100009758, eq=1600)]}],
     ("Duel.SpecialSummon(tm,0,tp,tp,true,false,POS_FACEUP)", "")),
    ("效果里召唤", summon_more, SPELL, '进行1只战士族怪兽的召唤。',
     [{"field": {"0": {"hand": [100009759, DORON]}},
       "actions": [act(0, "activate", 100009759), chk("count", player=0, card=DORON, **{"in": "mzone"}, eq=1)]}],
     ("Duel.Summon(tp,sm,true,nil)", "")),
    ("对象怪兽同生共死", haunted, dict(SPELL, type=0x4 | 0x20000), '①：以自己墓地1只怪兽为对象才能发动。那只怪兽特殊召唤。这张卡从场上离开时那只怪兽破坏。那只怪兽被破坏时这张卡破坏。\n②：只要这张卡在魔法与陷阱区域存在，那只怪兽的攻击力上升300。',
     [{"field": {"0": {"szone": [{"code": 100009760, "pos": "set"}], "grave": [BE]}, "1": {"hand": [RAIGEKI]}},
       "actions": [act(0, "activate", 100009760), chk("count", player=0, card=BE, **{"in": "mzone"}, eq=1),
                   chk("atk", player=0, card=BE, eq=3300), act(0, "end_turn"), act(1, "activate", RAIGEKI),
                   chk("count", player=0, card=100009760, **{"in": "grave"}, eq=1)]},
      {"field": {"0": {"szone": [{"code": 100009760, "pos": "set"}], "grave": [BE]}, "1": {"hand": [18144506]}},
       "actions": [act(0, "activate", 100009760), act(0, "end_turn"), act(1, "activate", 18144506),
                   chk("count", player=0, card=BE, **{"in": "grave"}, eq=1)]}],
     ("eg:IsContains(tc)", "false")),
    ("接触融合", contact, dict(MON, type=0x41, level=6), '「756652」＋「549481」\n这张卡用以下方法才能从额外卡组特殊召唤。\n●把自己场上的上记的卡回到持有者卡组的场合可以从额外卡组特殊召唤（不需要「融合」）。',
     [{"field": {"0": {"mzone": [DORON, LV4], "extra": [100009761]}},
       "actions": [act(0, "spsummon", 100009761), chk("count", player=0, card=100009761, **{"in": "mzone"}, eq=1),
                   chk("count", player=0, card=DORON, **{"in": "deck"}, eq=1)]}],
     ("LOCATION_ONFIELD,0,aux.ContactFusionSendToDeck", "0,0,aux.ContactFusionSendToDeck")),
    ("解放对方怪兽召唤", opp_tribute, dict(MON, level=7, atk=2500), '这张卡可以把自己或者对方场上的1只怪兽解放作召唤。',
     [{"field": {"0": {"hand": [100009762]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "summon", 100009762), chk("count", player=0, card=100009762, **{"in": "mzone"}, eq=1),
                   chk("count", player=1, card=BE, **{"in": "grave"}, eq=1)]}],
     ("SetTargetRange(0,LOCATION_MZONE)", "SetTargetRange(0,0)")),
    ("那个效果变成", swap_effect, dict(SPELL, type=0x4), '对方把卡的效果发动时才能发动。那个效果变成「自己回复1000基本分」的效果。',
     [{"field": {"0": {"mzone": [DORON], "szone": [{"code": 100009763, "pos": "set"}]}, "1": {"hand": [RAIGEKI]}},
       "actions": [act(0, "end_turn"), act(1, "activate", RAIGEKI), act(0, "activate", 100009763),
                   chk("count", player=0, card=DORON, **{"in": "mzone"}, eq=1), chk("lp", player=1, eq=9000)]}],
     ("Duel.ChangeChainOperation", "aux.TRUE")),
    ("加入对方手卡", gift, SPELL, '从手卡把1张卡加入对方手卡。',
     [{"field": {"0": {"hand": [100009764, DORON]}},
       "actions": [act(0, "activate", 100009764), chk("count", player=1, **{"in": "hand"}, eq=1)]}],
     ("1-tp", "nil")),
    ("从卡组发动场地", field_call, SPELL, '从卡组把1张场地魔法卡发动。',
     [{"field": {"0": {"hand": [100009765], "deck": [4064256]}},
       "actions": [act(0, "activate", 100009765), chk("count", player=0, card=4064256, **{"in": "szone"}, eq=1)]}],
     ("Duel.MoveToField(ac,tp,tp,zone,POS_FACEUP,true)", "")),
    ("不能发动送去墓地的同名卡", burial, SPELL, '从卡组把1张卡送去墓地。这个回合，自己不能把这个效果送去墓地的卡以及那些同名卡的效果发动。',
     [{"field": {"0": {"hand": [100009766, RAIGEKI], "deck": [RAIGEKI]}, "1": {"mzone": [BE]}},
       "actions": [act(0, "activate", 100009766), chk("count", player=0, card=RAIGEKI, **{"in": "grave"}, eq=1),
                   chk("offered", player=0, card=RAIGEKI, **{"as": "activate"}, eq=False)]}],
     ("SetTargetRange(1,0)", "SetTargetRange(0,0)")),
    ("每次准备阶段累计", decay, MON, '①：每次自己准备阶段，这张卡的攻击力下降200。',
     [{"field": {"0": {"mzone": [100009767]}},
       # 沙盒开局的第1回合也经过自己的准备阶段：到第3回合是2次
       "actions": [act(0, "end_turn"), act(1, "end_turn"), chk("atk", player=0, card=100009767, eq=1100),
                   act(0, "end_turn"), act(1, "end_turn"), chk("atk", player=0, card=100009767, eq=900)]}],
     ("-200", "0")),
    ("数回合后破坏", countdown, dict(SPELL, type=0x2 | 0x20000), '①：用对方回合计算的2回合后的对方结束阶段这张卡破坏。',
     [{"field": {"0": {"szone": [{"code": 100009769, "pos": "attack"}]}},
       "actions": [act(0, "end_turn"), chk("count", player=0, card=100009769, **{"in": "szone"}, eq=1),
                   act(1, "end_turn"), act(0, "end_turn"), act(1, "end_turn"),
                   chk("count", player=0, card=100009769, **{"in": "grave"}, eq=1)]}],
     ("GetFlagEffect(id+1)>=2", "GetFlagEffect(id+1)>=9")),
    ("按条件最多2次", twice, MON, '①：自己主要阶段才能发动。给与对方100伤害。这个效果1回合只能使用1次，自己场上有「756652」存在的场合，1回合可以使用最多2次。',
     [{"field": {"0": {"mzone": [100009768, DORON]}},
       "actions": [act(0, "activate", 100009768), act(0, "activate", 100009768), chk("lp", player=1, eq=7800),
                   chk("offered", player=0, card=100009768, **{"as": "activate"}, eq=False)]},
      {"field": {"0": {"mzone": [100009768]}},
       "actions": [act(0, "activate", 100009768), chk("offered", player=0, card=100009768, **{"as": "activate"}, eq=False)]}],
     ("and 2 or 1)", "and 1 or 1)")),
    ("手卡·墓地都能发动", two_places, MON, '这个卡名的效果1回合只能使用1次。\n①：这张卡在手卡·墓地存在的场合才能发动。这张卡特殊召唤。',
     [{"field": {"0": {"grave": [100009770]}},
       "actions": [act(0, "activate", 100009770), chk("count", player=0, card=100009770, **{"in": "mzone"}, eq=1)]},
      {"field": {"0": {"hand": [100009770]}},
       "actions": [act(0, "activate", 100009770), chk("count", player=0, card=100009770, **{"in": "mzone"}, eq=1)]}],
     ("SetRange(LOCATION_HAND+LOCATION_GRAVE)", "SetRange(LOCATION_HAND)")),
    ("种族勾两个", two_races, SPELL, '对方场上的龙族·战士族怪兽全部破坏。',
     [{"field": {"0": {"hand": [100009771]}, "1": {"mzone": [BE, DORON, LV4]}},
       "actions": [act(0, "activate", 100009771), chk("count", player=1, card=LV4, **{"in": "mzone"}, eq=1),
                   chk("count", player=1, **{"in": "grave"}, eq=2)]}],
     ("RACE_DRAGON|RACE_WARRIOR", "RACE_DRAGON")),
    ("时机勾几个", many_events, MON, '①：这张卡召唤·特殊召唤·反转召唤的场合才能发动。自己从卡组抽1张。',
     [{"field": {"0": {"hand": [100009772], "deck": [DORON]}},
       "actions": [act(0, "summon", 100009772), act(0, "activate", 100009772),
                   chk("count", player=0, card=DORON, **{"in": "hand"}, eq=1)]}],
     ("SetCode(EVENT_SUMMON_SUCCESS)", "SetCode(EVENT_FLIP)")),
    ("1回合2次", twice_a_turn, MON, '①：1回合2次，自己主要阶段才能发动。给与对方100伤害。',
     [{"field": {"0": {"mzone": [100009773]}},
       "actions": [act(0, "activate", 100009773), act(0, "activate", 100009773), chk("lp", player=1, eq=7800),
                   chk("offered", player=0, card=100009773, **{"as": "activate"}, eq=False)]}],
     ("SetCountLimit(2)", "SetCountLimit(1)")),
    ("特殊召唤的场合，结束阶段发动", end_of_ss, MON, '①：自己主要阶段才能发动。这张卡特殊召唤。\n②：这张卡特殊召唤的场合，结束阶段发动。这张卡送去墓地。那之后，可以从墓地把1只战士族怪兽加入手卡。',
     [{"field": {"0": {"hand": [100009774], "grave": [DORON]}},
       "actions": [act(0, "activate", 100009774), chk("count", player=0, card=100009774, **{"in": "mzone"}, eq=1),
                   act(0, "end_turn"), chk("count", player=0, card=100009774, **{"in": "grave"}, eq=1)]},
      {"field": {"0": {"mzone": [100009774]}},
       "actions": [act(0, "end_turn"), chk("count", player=0, card=100009774, **{"in": "mzone"}, eq=1)]}],
     ("GetFlagEffect(id+1)>0", "GetFlagEffect(id+1)>9")),
]


CASES.append(FLIP_CASE)


def load_only_cards():
    """没有情景的积木：每个时机、每种次数、各种新积木都拼进卡里，要能读成中文、被引擎加载（不出 Lua 错误）。"""
    from blocks.catalog import EVENTS
    out = []
    code = 100009800
    for ev, _ in EVENTS:
        if ev == "free":
            continue
        code += 1
        typ = "quick_o" if ev in ("chaining", "attack", "be_targeted", "summon_attempt", "spsummon_attempt",
                                  "be_attacked") else "trigger_o"
        ops = [new("draw", player="you", count=1)]
        if ev in ("summon_attempt", "spsummon_attempt"):
            ops = [new("negate_summon"), new("destroy", cards=[new("event_cards")])]
        out.append(card(code, "时机·" + ev, "monster", [
            new("effect", type=typ, event=ev, event_player="opp", range="mzone", operation=ops),
            new("effect", type="listener", event=ev, event_player="opp", range="mzone", operation=[
                new("recover", player="you", amount=[new("num", value=100)])])]))
    trap = [new("f_kind", kind="trap")]
    out.append(card(100009890, "各种次数与新积木", "monster", [
        new("effect", type="ignition", limit="name_shared", damage_step="yes",
            condition=[new("card_is", cards=[new("this_card")], filter=[new("f_summon_type", method="synchro")])],
            cost=[new("reveal", cards=[new("pick", who="you", where="hand", count=1, filter=trap)])],
            operation=[new("send_to_gy", cards=[new("deck_top", who="opp", count=2)]),
                       new("set_lp", player="opp", amount=[new("math", op="//", left=[new("lp_of", player="opp")],
                                                                    right=[new("num", value=2)])])]),
        new("effect", type="quick_o", limit="name_shared", event="attack",
            condition=[new("phase", phase="battle")],
            operation=[new("register", code="EFFECT_CANNOT_BE_EFFECT_TARGET", reset="end_of_turn", against="opp",
                           cards=[new("attack_target")]),
                       new("destroy", cards=[new("event_cards", filter=[new("f_controller", who="opp"),
                                                                        new("f_reason", reason="battle")])])]),
        new("effect", type="trigger_o", event="battle_destroying", limit="duel",
            operation=[new("banish", cards=[new("battle_opp")])]),
        new("effect", type="quick_o", limit="activate_card", range="hand",
            operation=[new("special_summon", cards=[new("this_card")])]),
        new("continuous", mode="self", code="EFFECT_INDESTRUCTABLE_EFFECT", against="opp"),
        new("continuous", mode="self", code="EFFECT_IMMUNE_EFFECT"),
        new("continuous", mode="zone", code="EFFECT_UPDATE_ATTACK", who="you", where="mzone",
            value=[new("num", value=100)], filter=[new("f_prev_location", where="extra")])]))
    out.append(card(100009891, "第二批的其余积木", "monster", [
        new("effect", type="quick_o", damage_step="calc",
            operation=[new("register", code="EFFECT_SET_ATTACK", reset="end_of_turn", cards=[new("this_card")],
                           value=[new("math", op="*", left=[new("base_atk_of", card=[new("this_card")])],
                                      right=[new("num", value=2)])]),
                       new("damage", player="opp", amount=[new("name_kinds", cards=[
                           new("all", who="you", where="grave", filter=[new("f_prev_controller", who="opp")])])])]),
        new("effect", type="ignition", range="grave", operation=[
            new("special_summon", to="opp", position="defense", ignore="yes", cards=[new("this_card")]),
            new("ritual_summon", level="equal", **{"from": "hand_grave"},
                filter=[new("f_race", race="warrior")]),
            new("fusion_summon", mats="hfg", filter=[new("f_set", setcode="0x8", name="英雄")]),
            new("change_position", to="facedown", cards=[new("pick", who="opp", where="mzone", count=1)]),
            new("select", player="you", count=2, different="yes", **{"as": "A"},
                source=[new("all", who="you", where="grave", filter=[new("f_kind", kind="monster")])]),
            new("to_deck", cards=[new("var", name="A")]),
            new("place", where="fzone", cards=[new("pick", who="you", where="deck", count=1,
                                                   filter=[new("f_subtype", subtype="field")])])])]))
    out.append(card(100009892, "第三批的其余积木", "monster", [
        new("unique", who="both"),
        new("effect", type="ignition", operation=[
            new("confirm_top", player="you", count=3),
            new("to_hand", cards=[new("pick", who="you", where="deck", count=1,
                                      filter=[new("f_lists_code", code=89631139, name="青眼白龙")])]),
            new("shuffle", player="you"),
            new("set_flag", on="player", name=2, reset="permanent"),
            new("detach", count=1),
            new("send_to_gy", cards=[new("overlay")])]),
        new("effect", type="trigger_o", event="leave_field",
            condition=[new("all_of", items=[
                new("has_flag", on="player", name=2),
                new("compare", op=">=", left=[new("counter_of", counter="0x1", card=[new("this_card")])],
                    right=[new("num", value=2)]),
                new("card_is", cards=[new("this_card")], filter=[new("f_prev_position", position="faceup")])])],
            operation=[new("special_summon", cards=[new("pick", who="you", where="grave", count=1,
                                                         filter=[new("f_name", code=89631139, name="青眼白龙")])])])]))
    out.append(card(100009893, "第四批的其余积木", "monster", [
        new("effect", type="ignition", operation=[
            new("announce", player="you", what="attribute"),
            new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_declared", what="attribute")])]),
            new("toss_coin"),
            new("if", cond=[new("coin_heads")], then=[new("draw", player="you", count=1)],
                **{"else": [new("damage", player="you", amount=[new("num", value=500)])]}),
            new("toss_dice"),
            new("recover", player="you", amount=[new("math", op="*", left=[new("dice_value")], right=[new("num", value=100)])]),
            new("to_deck", seq="bottom", cards=[new("pick", who="you", where="grave", count=1)]),
            new("delay", when="next_standby", body=[new("draw", player="you", count_n=[new("turn_number")])]),
            new("delay", when="next_end", body=[new("damage", player="opp", amount=[
                new("turn_count", player="opp", what="spsummon")])])]),
        new("effect", type="ignition", range="grave",
            cost=[new("banish", face="down", cards=[new("this_card")])],
            operation=[new("announce", player="opp", what="level"),
                       new("special_summon", cards=[new("pick", who="you", where="hand", count=1,
                                                         filter=[new("f_declared", what="level")])])])]))
    gy = [new("count_of", cards=[new("all", who="you", where="grave")])]
    out.append(card(100009894, "第五批的其余积木", "monster", [
        new("effect", type="ignition",
            cost=[new("remove_counter", count_n=[new("num", value=2)]),
                  new("discard", cards=[new("pick", who="you", where="hand", count=1, count_n=[new("num", value=1)])])],
            operation=[
                new("create_token", name="积木衍生物", count_n=[new("level_of", card=[new("this_card")])]),
                new("add_counter", counter="0x1", cards=[new("this_card")], count_n=[dict(gy[0])]),
                new("detach", count_n=[new("num", value=1)]),
                new("select", player="opp", count=1, upto="yes", different="yes", count_n=[dict(gy[0])], **{"as": "B"},
                    source=[new("all", who="opp", where="grave")]),
                new("to_deck", cards=[new("var", name="B")]),
                new("damage", player="opp", amount=[new("count_of", cards=[new("deck_top", who="you", count=3)])]),
                new("send_to_gy", cards=[new("all", who="you", where="mzone", filter=[
                    new("f_level", op="<", value_n=[new("count_of", cards=[new("operated")])])])])])]))
    out.append(card(100009895, "第六批的其余积木", "monster", [
        new("continuous", mode="self", code="EFFECT_IMMUNE_EFFECT", value_cards=[new("f_kind", kind="trap")]),
        new("continuous", mode="zone", who="both", where="deck", code="EFFECT_CANNOT_TO_GRAVE"),
        new("effect", type="ignition", operation=[
            new("special_summon", cards=[new("pick", who="you", where="pzone", count=1)]),
            new("banish", cards=[new("deck_top", who="you", count=3)]),
            new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn", cards=[new("this_card")], value=[
                new("math", op="*", left=[new("count_of", cards=[new("operated", filter=[new("f_set", setcode="0x8", name="英雄")])])],
                    right=[new("num", value=300)])])]),
        new("effect", type="trigger_o", event="monster_summoned_both", event_player="you", range="hand", operation=[
            new("special_summon", cards=[new("this_card")])]),
        new("effect", type="quick_o", event="equip_battle_damage", range="szone", operation=[new("draw", count=1)]),
        new("effect", type="ignition",
            cost=[new("remove_counter", **{"from": "field"}, count=1)],
            target=[new("take_target", count=2, **{"as": "X"}, source=[new("all", who="you", where="mzone",
                                                                            filter=[new("f_subtype", subtype="xyz")])])],
            operation=[
                new("detach", all="yes", cards=[new("target", name="X")]),
                new("remove_counter", **{"from": "field"}, count=1),
                new("add_counter", counter="0x1", max=3, cards=[new("this_card")]),
                new("toss_coin", call="yes"),
                new("if", cond=[new("coin_right")], then=[new("register", code="EFFECT_UPDATE_ATTACK", reset="next_standby",
                                                             cards=[new("this_card")], value=[new("num", value=1000)])]),
                new("destroy", cards=[new("all", who="opp", where="mzone", filter=[
                    new("f_same_code", card=[new("target", name="X")]), new("f_by_player", who="opp")])]),
                new("register_player", player="opp", code="EFFECT_CANNOT_ACTIVATE", reset="next_standby",
                    filter=[new("f_kind", kind="trap")])])]))
    out.append(card(100009896, "第七批的其余积木", "monster", [
        new("fusion_materials", count=2, more="yes", second=[new("f_subtype", subtype="effect")]),
        new("summon_rule", normal="no", special="fusion"),
        new("sp_proc", range="hand_grave", position="defense", condition=[new("turn", player="you")],
            cost=[new("release", cards=[new("pick", who="you", where="mzone", count=1)]),
                  new("pay_lp", amount=[new("num", value=1000)])]),
        new("ns_proc", condition=[new("not_cond", item=[new("exists", cards=[new("all", who="you", where="mzone")])])]),
        new("effect", type="trigger_o", event="be_material", condition=[
            new("card_is", cards=[new("this_card")], filter=[new("f_reason", reason="synchro")])],
            operation=[new("draw", player="you", count=1)])]))
    out.append(card(100009897, "第七批·融合素材×3", "monster", [
        new("fusion_materials", count=3, second=[new("f_race", race="dragon")]),
        new("summon_rule", normal="no", special="own_effect")]))
    out.append(card(100009898, "第八批的其余积木", "monster", [
        new("effect", type="trigger_o", event="cards_destroyed", event2="cards_banished", event_player="opp", range="grave",
            operation=[new("special_summon", cards=[new("this_card")])]),
        new("effect", type="quick_o", event="monster_battle_start", event_player="you", range="hand",
            cost=[new("discard", cards=[new("this_card")])],
            operation=[new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn",
                           cards=[new("battling", who="you")], value=[new("num", value=1000)])]),
        new("effect", type="trigger_f", event="monster_damage_step_end", event_player="opp", range="mzone",
            operation=[new("destroy", cards=[new("battling", who="opp")])]),
        new("effect", type="trigger_o", event="cards_to_hand", event2="cards_to_deck", event_player="opp", range="mzone",
            condition=[new("card_is", cards=[new("event_cards")], filter=[new("f_prev_location", where="deck")])],
            operation=[new("draw", player="you", count=1)]),
        new("effect", type="listener", event="monster_battle_destroyed", event2="cards_leave_field", event_player="you",
            range="mzone", operation=[new("recover", player="you", amount=[new("num", value=500)])])]))
    out.append(card(100009899, "第九批的其余积木", "monster", [
        new("ns_proc"),
        new("effect", type="trigger_f", event="summon", condition=[
            new("card_is", cards=[new("this_card")], filter=[new("f_by_proc")])],
            operation=[new("register", code="EFFECT_UPDATE_ATTACK", reset="opp_turn_end", cards=[new("this_card")],
                           value=[new("num", value=-500)])]),
        new("effect", type="quick_o", event="chaining", event_player="opp", range="hand",
            condition=[new("chain_does", what="destroy")],
            cost=[new("discard", cards=[new("this_card")])],
            operation=[new("negate_activation")]),
        new("effect", type="ignition", operation=[
            new("register", code="EFFECT_INDESTRUCTABLE_COUNT", reset="end_of_turn",
                cards=[new("pick", who="you", where="mzone", count=1)]),
            new("register_player", player="opp", code="EFFECT_CANNOT_SPECIAL_SUMMON", reset="opp_turn_end")])]))
    out.append(card(100009900, "第十批的其余积木", "monster", [
        new("effect", type="quick_o", event="attack", event_player="opp", range="mzone", operation=[
            new("change_attack_target", cards=[new("this_card")])]),
        new("effect", type="trigger_o", event="battle_destroying", condition=[new("can_chain_attack")],
            operation=[new("chain_attack")]),
        new("effect", type="ignition", target=[new("take_target", count=1, **{"as": "T"}, source=[
            new("all", who="opp", where="mzone", filter=[new("f_any", items=[
                new("f_rank", op="<=", value=4), new("f_link", op=">=", value=2),
                new("f_all", filter=[new("f_same_attr", card=[new("this_card")]), new("f_same_race", card=[new("this_card")])])])])])],
            operation=[new("calc_damage", a=[new("this_card")], b=[new("target", name="T")]),
                       new("damage", player="opp", amount=[new("math", op="+", left=[new("rank_of", card=[new("target", name="T")])],
                                                                    right=[new("link_of", card=[new("target", name="T")])])])]),
        new("effect", type="quick_o", event="attack", event_player="opp", range="hand",
            cost=[new("discard", cards=[new("this_card")])], operation=[new("change_attack_target")])]))
    out.append(card(100009901, "第十一批的其余积木", "monster", [
        new("effect", type="quick_o", event="chaining", event_player="opp", range="hand", limit="chain", unstoppable="yes",
            condition=[new("all_of", items=[new("chain_is", what="monster"), new("chain_is", what="from_grave"),
                                            new("compare", op=">=", left=[new("chain_count")], right=[new("num", value=2)])])],
            cost=[new("discard", cards=[new("this_card")])], operation=[new("negate_effect")]),
        new("effect", type="listener", event="chain_solved", event_player="opp", range="mzone", condition=[
            new("chain_is", what="spell")], operation=[new("add_counter", counter="0x1", cards=[new("this_card")])]),
        new("effect", type="trigger_o", event="chain_negated", event_player="you", range="grave", chain_limit="all",
            operation=[new("special_summon", cards=[new("this_card")])]),
        new("effect", type="listener", event="chain_end", range="mzone", operation=[new("recover", amount=[new("num", value=100)])])]))
    out.append(card(100009902, "第十二批的其余积木", "monster", [
        new("continuous", mode="zone", code="EFFECT_UPDATE_ATTACK", who="both", where="mzone", value=[new("num", value=500)],
            filter=[new("f_linked")]),
        new("continuous", mode="zone", code="EFFECT_CANNOT_TRIGGER", who="opp", where="field", filter=[new("f_same_column")]),
        new("effect", type="ignition", limit="card", operation=[
            new("move_zone", cards=[new("this_card")]),
            new("destroy", cards=[new("column_group")]),
            new("damage", player="opp", amount=[new("math", op="*", left=[new("count_of", cards=[new("linked_group")])],
                                                     right=[new("num", value=300)])]),
            new("send_to_gy", cards=[new("all", who="both", where="mzone", filter=[new("f_link_state")])])])]))
    out.append(card(100009903, "第十三批的其余积木", "monster", [
        new("destroy_replace", mode="others", range="szone", limit="card", protect=[new("f_race", race="warrior")],
            cost=[new("banish", cards=[new("pick", who="you", where="grave", count=1)])]),
        new("effect", type="trigger_o", event="bp_start", event_player="you", range="mzone",
            operation=[new("sort_deck", player="opp", count=3)]),
        new("effect", type="listener", event="pos_changed", event2="detached", event_player="opp", range="mzone",
            operation=[new("damage", player="opp", amount=[new("num", value=100)])]),
        new("effect", type="trigger_o", event="cards_destroyed", event_player="opp", range="mzone",
            condition=[new("card_is", cards=[new("event_cards")], filter=[new("f_by_this"), new("f_prev_set", setcode="0x8"),
                                                                         new("f_prev_race", race="warrior"),
                                                                         new("f_prev_attr", attribute="dark")])],
            operation=[new("damage", player="opp", amount=[new("prev_atk_of", card=[new("event_cards")])])]),
        new("effect", type="trigger_o", event="cards_set", event2="monsters_set", event_player="opp", range="mzone",
            operation=[new("draw", count=1)]),
        new("effect", type="listener", event="recovered", event2="equipped", event_player="you", range="mzone",
            operation=[new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn", cards=[new("this_card")],
                           value=[new("num", value=100)])])]))
    out.append(card(100009904, "第十四批的其余积木", "monster", [
        new("monster_trait", trait="union", filter=[new("f_race", race="machine")]),
        new("continuous", mode="equipped", code="EFFECT_UPDATE_ATTACK", condition=[new("union_state")],
            value=[new("num", value=500)]),
        new("effect", type="ignition", range="mzone", limit="card", target=[new("take_target", count=1, **{"as": "T"}, source=[new("all", who="opp", where="mzone", filter=[new("f_position", position="faceup")])])],
            operation=[new("copy_effects", name="yes", cards=[new("target", name="T")])]),
        new("effect", type="ignition", range="mzone", operation=[
            new("copy_effects", reset="permanent", cards=[new("pick", who="you", where="grave", count=1)])])]))
    out.append(card(100009905, "第十四批：陷阱怪兽（效果怪兽）", "trap", [
        new("effect", type="activate", operation=[
            new("trap_monster", mtype="effect", level=4, atk=1200, **{"def": 0}, race="fiend", attribute="dark")])]))
    out.append(card(100009906, "第十五批的其余积木", "monster", [
        new("name_as", code=89631139, name="青眼白龙", where="field_grave"),
        new("effect", type="quick_o", event="free", range="mzone", damage_step="calc",
            condition=[new("all_of", items=[new("phase", phase="damage_calc"), new("can_enter_bp"),
                                            new("player_affected", player="opp", code="EFFECT_SKIP_DP")])],
            operation=[new("register", code="EFFECT_UPDATE_ATTACK", reset="end_of_turn", cards=[new("this_card")],
                           value=[new("text_atk_of", card=[new("this_card")])])]),
        new("effect", type="ignition", range="grave", condition=[new("not_sent_this_turn")], operation=[
            new("destroy", cards=[new("all", who="opp", where="mzone", filter=[
                new("f_zone_seq", seq="extra"), new("f_has_effect", code="EFFECT_DISABLE"),
                new("f_subtype", subtype="token")])]),
            new("extra_summon", method="synchro", filter=[new("f_race", race="dragon")]),
            new("extra_summon", method="xyz"), new("extra_summon", method="link")]),
        new("effect", type="trigger_o", event="cards_destroyed", range="mzone",
            condition=[new("card_is", cards=[new("event_cards")], filter=[
                new("f_prev_kind", kind="monster"), new("f_reason", reason="return"), new("f_subtype", subtype="toon")])],
            operation=[new("damage", player="opp", amount=[new("math", op="+", left=[new("count_of", cards=[new("equip_group")])],
                                                                right=[new("text_def_of", card=[new("this_card")])])]),
                       new("normal_summon")])]))
    out.append(card(100009907, "第十六批的其余积木", "monster", [
        new("effect", type="ignition", range="mzone", limit="card_shared",
            cost=[new("to_hand", cards=[new("pick", who="you", where="mzone", count=1)])],
            operation=[new("announce", player="you", what="number"), new("end_battle_phase")]),
        new("effect", type="ignition", range="mzone", limit="card_shared",
            condition=[new("all_of", items=[new("this_battled"), new("this_attacked")])],
            operation=[new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_subtype", subtype="trapmonster")])])]),
        new("effect", type="trigger_f", event="battle_confirm", operation=[new("draw", count=1)])]))
    out.append(card(100009908, "第十七批的其余积木", "trap", [
        new("effect", type="activate", target=[new("take_target", count=1, **{"as": "T"},
                                                    source=[new("all", who="opp", where="mzone")])],
            operation=[new("keep_target", cards=[new("target", name="T")])]),
        new("target_link", link="target_leave", range="szone"),
        new("effect", type="quick_o", event="free", range="szone", operation=[
            new("change_position", to="defense", cards=[new("card_target")])])]))
    out.append(card(100009909, "第十八批：双调整同调", "monster", [
        new("extra_materials", method="synchro", tuners="two", count=1, more="yes", tuner=[new("f_attr", attribute="dark")])]))
    out.append(card(100009910, "第十八批：重叠超量", "monster", [
        new("extra_materials", method="xyz", rank=8, count=3, alter=[new("f_set", setcode="0x107b", name="银河眼"),
                                                                     new("f_subtype", subtype="xyz")])]))
    out.append(card(100009911, "第十八批：连接与三种融合", "monster", [
        new("extra_materials", method="link", count=2, more="yes", material=[new("f_race", race="cyberse")],
            include=[new("f_set", setcode="0x101", name="码语者")])]))
    out.append(card(100009912, "第十八批：三种融合素材", "monster", [
        new("fusion_materials", contact="banish", first=[new("f_name", code=89631139)], second=[new("f_attr", attribute="dark")],
            third=[new("f_set", setcode="0x3008", name="元素英雄")])]))
    out.append(card(100009913, "第十九批的其余积木", "monster", [
        new("effect", type="quick_o", event="chaining", event_player="opp", range="mzone", chain_limit="opp_end",
            operation=[new("change_chain_target", cards=[new("this_card")])]),
        new("effect", type="ignition", range="mzone", operation=[
            new("announce", player="you", what="race_or_attr"),
            new("destroy", cards=[new("all", who="opp", where="mzone", filter=[new("f_declared", what="race_or_attr"),
                                                                             new("f_orig_race", race="dragon"),
                                                                             new("f_orig_attr", attribute="light")])]),
            new("damage", player="opp", amount=[new("scale_of", card=[new("this_card")])])])]))
    out.append(card(100009914, "第二十批的其余积木", "monster", [
        new("continuous", mode="self", code="EFFECT_IMMUNE_EFFECT", range="mzone",
            value_cards=[new("f_activated_effect"), new("f_summon_type", method="special"), new("f_controller", who="opp")]),
        new("effect", type="trigger_o", event="predraw", event_player="you", range="mzone", condition=[new("can_normal_draw")],
            operation=[new("give_up_draw"), new("skip_phase", player="opp", phase="battle")]),
        new("effect", type="quick_f", event="attack", event_player="opp", range="mzone", operation=[
            new("damage", player="opp", amount=[new("math", op="+", left=[new("battle_damage", player="you")],
                                                     right=[new("attacked_count", card=[new("this_card")])])])]),
        new("effect", type="listener", event="leaving", operation=[new("recover", amount=[new("num", value=100)])]),
        new("effect", type="trigger_o", event="cards_moved", event_player="opp", range="mzone",
            cost=[new("to_deck", cards=[new("pick", who="you", where="mzone", count=1)])],
            operation=[new("to_deck", seq="bottom_order", cards=[new("all", who="opp", where="grave", filter=[
                new("f_battled_opp"), new("f_can_attack"), new("f_prev_name", code=89631139, name="青眼白龙")])]),
                       new("to_extra_faceup", cards=[new("all", who="you", where="hand", filter=[new("f_subtype", subtype="pendulum")])]),
                       new("damage", player="opp", amount=[new("prev_overlay_count", card=[new("this_card")])]),
                       new("destroy", cards=[new("prev_equip_target")])])]))
    out.append(card(100009915, "第二十批：留在场上", "spell", [
        new("effect", type="activate", operation=[new("draw", count=1), new("stay_on_field")])]))
    out.append(card(100009916, "第二十一批的其余积木", "monster", [
        new("effect", type="quick_o", event="chaining", range="mzone", operation=[
            new("destroy", cards=[new("all", who="opp", where="field", filter=[new("f_chaining"), new("f_not_destroying")])])])]))
    out.append(card(100009917, "第二十二批的其余积木", "monster", [
        new("effect", type="trigger_o", event="summon", condition=[new("all_of", items=[
            new("materials_are", mode="any", filter=[new("f_set", setcode="0x0a", name="侵入魔鬼")]),
            new("materials_are", mode="all", filter=[new("f_race", race="fiend")])])],
            operation=[new("damage", player="opp", amount=[new("math", op="*", left=[new("material_count")],
                                                                right=[new("num", value=500)])])]),
        new("continuous", mode="zone", code="EFFECT_INDESTRUCTABLE_BATTLE", who="both", where="mzone",
            filter=[new("f_battle_pair", who="both")], value=[new("num", value=1)]),
        new("continuous", mode="zone", code="EFFECT_UPDATE_ATTACK", who="opp", where="mzone",
            filter=[new("f_battle_pair", who="opp")], value=[new("flag_count", on="player", name=2)])]))
    out.append(card(100009918, "多处发动的其余组合", "monster", [
        new("effect", type="quick_o", range="mzone_grave", cost=[new("banish", cards=[new("this_card")])],
            operation=[new("draw", count=1)]),
        new("effect", type="ignition", range="grave_banished", operation=[new("to_hand", cards=[new("this_card")])]),
        new("effect", type="trigger_o", event="cards_destroyed", range="hand_mzone_grave", operation=[new("draw", count=1)]),
        new("continuous", mode="self", code="EFFECT_CANNOT_BE_EFFECT_TARGET", range="hand_mzone", value=[new("num", value=1)])]))
    out.append(card(100009919, "自定义组合", "monster", [
        new("effect", type="ignition", range="grave+banished", cost=[new("banish", cards=[new("this_card")])],
            operation=[new("to_hand", cards=[new("pick", who="you", where="hand+deck+grave", count=1, filter=[
                new("f_kind", kind="spell+trap"), new("f_attr", attribute="light+dark")])])]),
        new("effect", type="trigger_o", event="cards_destroyed", range="hand+mzone+grave", condition=[
            new("card_is", cards=[new("event_cards")], filter=[new("f_reason", reason="battle+effect"),
                                                              new("f_summon_type", method="fusion+synchro+xyz+link"),
                                                              new("f_subtype", subtype="fusion+synchro"),
                                                              new("f_prev_location", where="mzone+szone"),
                                                              new("f_orig_race", race="beast+beast_warrior+winged_beast"),
                                                              new("f_prev_attr", attribute="light+dark")])],
            operation=[new("draw", count=1)]),
        new("continuous", mode="zone", code="EFFECT_UPDATE_ATTACK", range="mzone+grave", who="you", where="mzone+szone",
            value=[new("num", value=100)])]))
    out.append(card(100009920, "阶段勾几个、次数几次", "monster", [
        new("effect", type="quick_o", range="mzone", limit="name", limit_n=3,
            condition=[new("phase", phase="main1+battle")], operation=[new("draw", count=1)]),
        new("effect", type="trigger_o", event="cards_to_grave+cards_banished+cards_destroyed", event_player="opp", range="mzone",
            limit="duel", limit_n=2, operation=[new("draw", count=1)])]))
    return out


def load_check_all(core):
    """load_only_cards 全部读成中文、生成 Lua、被引擎加载。返回问题列表。"""
    from sandbox.probe import load_check
    bad = []
    for model in load_only_cards():
        name = model["card"]["name"]
        try:
            notes = check(model)
            read_card(model)
            lua = compile_card(model)
            core.add_card(dict(MON, code=model["card"]["code"], name=name, alias=0, setcodes=[]))
            loaded, errs = load_check(core, model["card"]["code"], lua.encode("utf-8"))
            if not loaded or errs:
                notes.append("引擎加载失败：%s" % ("；".join(errs) or "没有加载"))
        except Exception as ex:
            notes = ["生成失败：%r" % ex]
        bad += ["%s：%s" % (name, n) for n in notes]
    return bad


def main():
    from sandbox.core import Core
    from sandbox.probe import load_check
    from sandbox.scenario import Runner
    os.makedirs(os.path.join(HERE, "samples"), exist_ok=True)
    core = Core()
    bad = 0
    for label, model, rec, text, scenarios, mutation in CASES:
        with open(os.path.join(HERE, "samples", "%d_%s.json" % (model["card"]["code"], label)), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(model, f, ensure_ascii=False, indent=1)
        notes = check(model)
        zh = read_card(model)
        lua = compile_card(model)
        rec = dict(rec, code=model["card"]["code"], name=model["card"]["name"], alias=0, setcodes=[])
        rec["type"] |= type_bits(dict(model, schema="ygodiy-blocks/0.3"))
        core.add_card(rec)
        for n, _ in tokens(model):
            core.add_card(dict(TOKEN, code=rec["code"] + n, name="衍生物", alias=0, setcodes=[]))
        loaded, errs = load_check(core, rec["code"], lua.encode("utf-8"))
        if not loaded or errs:
            notes.append("引擎加载失败：%s" % ("；".join(errs) or "没有加载"))
        core.overrides = {rec["code"]: lua.encode("utf-8")}
        for i, sc in enumerate(scenarios):
            runner = Runner(core, dict(sc, name="%s #%d" % (label, i + 1)))
            if not runner.run():
                notes.append("情景 %d 失败：%s" % (i + 1, "；".join(runner.failures)))
        old, new_ = mutation
        if old not in lua:
            notes.append("对照没找到要改的地方：%s" % old)
        else:
            core.overrides = {rec["code"]: lua.replace(old, new_, 1).encode("utf-8")}
            if all(Runner(core, dict(sc, name="对照")).run() for sc in scenarios):
                notes.append("改坏的对照没有被查出")
        if text is not None and zh != text:
            notes.append("中文：期望「%s」，读出「%s」" % (text, zh))
        bad += bool(notes)
        print("%s  %s（%d 个情景，改坏的对照%s）" % ("通过" if not notes else "失败", label, len(scenarios),
                                              "被查出" if not notes else "见下"))
        print("      读作：%s" % zh.replace("\n", " / "))
        for n in notes:
            print("      " + n)
    loads = load_check_all(core)
    print("%s  其余积木：每个时机、每种次数和新积木都能生成并被引擎加载（%d 张）" % (
        "通过" if not loads else "失败", len(load_only_cards())))
    for x in loads:
        print("      " + x)
    bad += bool(loads)
    print("积木原型：%s" % ("全部通过" if not bad else "%d 处失败" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
