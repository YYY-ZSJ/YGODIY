"""积木树 → 萌卡一系（MDPro3 / ygopro2）的 Lua 卡片脚本。

逐块翻译：每种积木对应引擎的一个结构或一个操作。
    会发动的效果  Effect.CreateEffect + 各项设置；发动条件 / 代价 / 对象 / 处理 → condition / cost / target / operation
    永续效果      EFFECT_TYPE_SINGLE（这张卡）/ FIELD（一片区域、玩家）+ 效果代码
能否发动的检查（target 的 chk==0）、处理预告（SetOperationInfo）、效果分类（SetCategory）由处理里的动作自动算出。
召唤手续（素材、出场限制、灵摆）照 Effect Model v0.2 的 summon 结构，用原来的生成代码写。
"""

from .catalog import ATTRIBUTES, BLOCKS, COST_ACTS, MultiMap, events_of, fits, multi_parts

LOC = {"mzone": "LOCATION_MZONE", "field": "LOCATION_ONFIELD", "szone": "LOCATION_SZONE", "hand": "LOCATION_HAND",
       "deck": "LOCATION_DECK", "grave": "LOCATION_GRAVE", "banished": "LOCATION_REMOVED", "extra": "LOCATION_EXTRA",
       "fzone": "LOCATION_FZONE", "pzone": "LOCATION_PZONE",
       "hand_deck": "LOCATION_HAND+LOCATION_DECK", "hand_grave": "LOCATION_HAND+LOCATION_GRAVE",
       "deck_grave": "LOCATION_DECK+LOCATION_GRAVE", "hand_deck_grave": "LOCATION_HAND+LOCATION_DECK+LOCATION_GRAVE",
       "hand_field": "LOCATION_HAND+LOCATION_ONFIELD", "grave_banished": "LOCATION_GRAVE+LOCATION_REMOVED",
       "mzone_grave": "LOCATION_MZONE+LOCATION_GRAVE", "hand_mzone": "LOCATION_HAND+LOCATION_MZONE",
       "hand_mzone_grave": "LOCATION_HAND+LOCATION_MZONE+LOCATION_GRAVE",
       "hand_grave_banished": "LOCATION_HAND+LOCATION_GRAVE+LOCATION_REMOVED",
       "szone_grave": "LOCATION_SZONE+LOCATION_GRAVE", "hand_szone": "LOCATION_HAND+LOCATION_SZONE"}
RACE = {"warrior": "WARRIOR", "spellcaster": "SPELLCASTER", "fairy": "FAIRY", "fiend": "FIEND", "zombie": "ZOMBIE",
        "machine": "MACHINE", "aqua": "AQUA", "pyro": "PYRO", "rock": "ROCK", "winged_beast": "WINDBEAST",
        "plant": "PLANT", "insect": "INSECT", "thunder": "THUNDER", "dragon": "DRAGON", "beast": "BEAST",
        "beast_warrior": "BEASTWARRIOR", "dinosaur": "DINOSAUR", "fish": "FISH", "sea_serpent": "SEASERPENT",
        "reptile": "REPTILE", "psychic": "PSYCHO", "divine": "DIVINE", "wyrm": "WYRM", "cyberse": "CYBERSE",
        "illusion": "ILLUSION"}
TYPE = {"monster": "TYPE_MONSTER", "spell": "TYPE_SPELL", "trap": "TYPE_TRAP", "normal": "TYPE_NORMAL",
        "effect": "TYPE_EFFECT", "tuner": "TYPE_TUNER", "fusion": "TYPE_FUSION", "synchro": "TYPE_SYNCHRO",
        "xyz": "TYPE_XYZ", "link": "TYPE_LINK", "ritual": "TYPE_RITUAL", "pendulum": "TYPE_PENDULUM",
        "quick": "TYPE_QUICKPLAY", "continuous": "TYPE_CONTINUOUS", "equip": "TYPE_EQUIP", "field": "TYPE_FIELD",
        "counter": "TYPE_COUNTER", "token": "TYPE_TOKEN", "flip": "TYPE_FLIP", "spirit": "TYPE_SPIRIT",
        "gemini": "TYPE_DUAL", "union": "TYPE_UNION", "toon": "TYPE_TOON", "trapmonster": "TYPE_TRAPMONSTER"}
# 多选的值（hand+grave、dragon+machine……）：各自查表再用位或连起来
LOC = MultiMap(LOC, "|", wrap=True)
RACE = MultiMap(RACE, "|RACE_")                  # 用法都是 "RACE_%s" % RACE[...]
ATTR = MultiMap({k: "ATTRIBUTE_%s" % k.upper() for k, _ in ATTRIBUTES}, "|", wrap=True)
TYPE = MultiMap(TYPE, "|", wrap=True)
POSITION = {"faceup": "IsFaceup", "facedown": "IsFacedown", "attack": "IsAttackPos", "defense": "IsDefensePos"}
TO_POS = {"attack": "POS_FACEUP_ATTACK", "defense": "POS_FACEUP_DEFENSE", "facedown": "POS_FACEDOWN_DEFENSE",
          "swap": "POS_FACEUP_DEFENSE,POS_FACEDOWN_DEFENSE,POS_FACEUP_ATTACK,POS_FACEUP_ATTACK"}
LUA_OP = {">=": ">=", "<=": "<=", "==": "==", ">": ">", "<": "<", "!=": "~="}
STAT_FN = {("level", "<="): "IsLevelBelow", ("level", ">="): "IsLevelAbove", ("level", "=="): "IsLevel",
           ("atk", "<="): "IsAttackBelow", ("atk", ">="): "IsAttackAbove", ("atk", "=="): "IsAttack",
           ("def", "<="): "IsDefenseBelow", ("def", ">="): "IsDefenseAbove", ("def", "=="): "IsDefense"}
PLAYER = {"you": "tp", "opp": "1-tp"}
RANGE = {"you": "1,0", "opp": "0,1", "both": "1,1"}
# 移动卡片的动作 → (处理时的调用, 分类, 选卡提示, 能不能这样处理, 当代价时的检查, 当代价时的调用)
ACTS = {
    "destroy": ("Duel.Destroy(%s,REASON_EFFECT)", "CATEGORY_DESTROY", "HINTMSG_DESTROY", None, None, None),
    "to_hand": ("Duel.SendtoHand(%s,nil,REASON_EFFECT)", "CATEGORY_TOHAND", "HINTMSG_ATOHAND", "c:IsAbleToHand()",
                "c:IsAbleToHandAsCost()", "Duel.SendtoHand(%s,nil,REASON_COST)"),
    "send_to_gy": ("Duel.SendtoGrave(%s,REASON_EFFECT)", "CATEGORY_TOGRAVE", "HINTMSG_TOGRAVE", "c:IsAbleToGrave()",
                   "c:IsAbleToGraveAsCost()", "Duel.SendtoGrave(%s,REASON_COST)"),
    "banish": ("Duel.Remove(%s,POS_FACEUP,REASON_EFFECT)", "CATEGORY_REMOVE", "HINTMSG_REMOVE", "c:IsAbleToRemove()",
               "c:IsAbleToRemoveAsCost()", "Duel.Remove(%s,POS_FACEUP,REASON_COST)"),
    "to_deck": ("Duel.SendtoDeck(%s,nil,SEQ_DECKSHUFFLE,REASON_EFFECT)", "CATEGORY_TODECK", "HINTMSG_TODECK",
                "c:IsAbleToDeck()", "c:IsAbleToDeckOrExtraAsCost()", "Duel.SendtoDeck(%s,nil,SEQ_DECKSHUFFLE,REASON_COST)"),
    "special_summon": ("Duel.SpecialSummon(%s,0,tp,tp,false,false,POS_FACEUP)", "CATEGORY_SPECIAL_SUMMON",
                       "HINTMSG_SPSUMMON", "c:IsCanBeSpecialSummoned(e,0,tp,false,false)", None, None),
    "set_card": ("Duel.SSet(tp,%s)", None, "HINTMSG_SET", "c:IsSSetable()", None, None),
    "discard": ("Duel.SendtoGrave(%s,REASON_EFFECT+REASON_DISCARD)", "CATEGORY_HANDES", "HINTMSG_DISCARD",
                "c:IsDiscardable(REASON_EFFECT)", "c:IsDiscardable()", "Duel.SendtoGrave(%s,REASON_COST+REASON_DISCARD)"),
    "release": ("Duel.Release(%s,REASON_EFFECT)", "CATEGORY_RELEASE", "HINTMSG_RELEASE", "c:IsReleasableByEffect()",
                "c:IsReleasable()", "Duel.Release(%s,REASON_COST)"),
    "get_control": ("(Duel.GetControl(%s,tp) and 1 or 0)", "CATEGORY_CONTROL", "HINTMSG_CONTROL",
                    "c:IsControlerCanBeChanged()", None, None),
    "change_position": (None, "CATEGORY_POSITION", "HINTMSG_POSCHANGE", None, None, None),
    "reveal": ("Duel.ConfirmCards(1-tp,%s)", None, "HINTMSG_CONFIRM", None, "not c:IsPublic()",
               "Duel.ConfirmCards(1-tp,%s)"),
    "place": (None, None, "HINTMSG_TOFIELD", "not c:IsForbidden()", None, None),
    "attach": (None, None, "HINTMSG_XMATERIAL", "c:IsCanOverlay()", None, None),
}
EVENT_CODE = {"free": "EVENT_FREE_CHAIN", "summon": "EVENT_SUMMON_SUCCESS", "spsummon": "EVENT_SPSUMMON_SUCCESS",
              "summon_both": "EVENT_SUMMON_SUCCESS",           # 再复制一份 EVENT_SPSUMMON_SUCCESS
              "to_grave": "EVENT_TO_GRAVE", "destroyed": "EVENT_DESTROYED", "draw": "EVENT_DRAW",
              "attack": "EVENT_ATTACK_ANNOUNCE", "chaining": "EVENT_CHAINING", "standby": "EVENT_PHASE+PHASE_STANDBY",
              "end": "EVENT_PHASE+PHASE_END", "be_attacked": "EVENT_BE_BATTLE_TARGET",
              "battle_end": "EVENT_PHASE+PHASE_BATTLE", "battle_destroyed": "EVENT_BATTLE_DESTROYED",
              "effect_destroyed": "EVENT_DESTROYED", "battle_destroying": "EVENT_BATTLE_DESTROYING",
              "leave_field": "EVENT_LEAVE_FIELD", "field_to_grave": "EVENT_TO_GRAVE", "banished": "EVENT_REMOVE",
              "released": "EVENT_RELEASE", "to_hand": "EVENT_TO_HAND", "flip_summon": "EVENT_FLIP_SUMMON_SUCCESS", "flip": "EVENT_FLIP",
              "be_material": "EVENT_BE_MATERIAL", "battle_damage": "EVENT_BATTLE_DAMAGE",
              "be_targeted": "EVENT_BECOME_TARGET", "monster_summoned": "EVENT_SUMMON_SUCCESS",
              "monster_spsummoned": "EVENT_SPSUMMON_SUCCESS", "summon_attempt": "EVENT_SUMMON",
              "spsummon_attempt": "EVENT_SPSUMMON", "battle_start": "EVENT_BATTLE_START",
              "pre_damage_calc": "EVENT_PRE_DAMAGE_CALCULATE", "battled": "EVENT_BATTLED", "battle_confirm": "EVENT_BATTLE_CONFIRM",
              "damage_step_end": "EVENT_DAMAGE_STEP_END", "monster_summoned_both": "EVENT_SUMMON_SUCCESS",
              "player_battle_damaged": "EVENT_BATTLE_DAMAGE", "player_damaged": "EVENT_DAMAGE",
              "equip_battle_damage": "EVENT_BATTLE_DAMAGE", "cards_to_grave": "EVENT_TO_GRAVE",
              "cards_banished": "EVENT_REMOVE", "cards_destroyed": "EVENT_DESTROYED", "cards_to_hand": "EVENT_TO_HAND",
              "cards_to_deck": "EVENT_TO_DECK", "cards_leave_field": "EVENT_LEAVE_FIELD",
              "monster_battle_destroyed": "EVENT_BATTLE_DESTROYED", "monster_battle_start": "EVENT_BATTLE_START",
              "monster_damage_step_end": "EVENT_DAMAGE_STEP_END", "chain_solved": "EVENT_CHAIN_SOLVED",
              "chain_negated": "EVENT_CHAIN_NEGATED", "chain_end": "EVENT_CHAIN_END",
              "bp_start": "EVENT_PHASE_START+PHASE_BATTLE_START", "cards_set": "EVENT_SSET", "monsters_set": "EVENT_MSET",
              "pos_changed": "EVENT_CHANGE_POS", "detached": "EVENT_DETACH_MATERIAL", "recovered": "EVENT_RECOVER",
              "equipped": "EVENT_EQUIP", "leaving": "EVENT_LEAVE_FIELD_P", "cards_moved": "EVENT_MOVE",
              "predraw": "EVENT_PREDRAW"}
CHAIN_IS = {"monster": "re:IsActiveType(TYPE_MONSTER)", "spell": "re:IsActiveType(TYPE_SPELL)",
            "trap": "re:IsActiveType(TYPE_TRAP)", "activation": "re:IsHasType(EFFECT_TYPE_ACTIVATE)",
            "from_hand": "Duel.GetChainInfo(ev,CHAININFO_TRIGGERING_LOCATION)==LOCATION_HAND",
            "from_grave": "Duel.GetChainInfo(ev,CHAININFO_TRIGGERING_LOCATION)==LOCATION_GRAVE",
            "from_field": "Duel.GetChainInfo(ev,CHAININFO_TRIGGERING_LOCATION)&LOCATION_ONFIELD~=0"}
# 「数值：只对这样的卡成立」：这些效果代码的数值函数收到的是效果（按发动那个效果的卡判断），其余收到的是卡
VALUE_BY_EFFECT = {"EFFECT_IMMUNE_EFFECT", "EFFECT_INDESTRUCTABLE_EFFECT", "EFFECT_CANNOT_BE_EFFECT_TARGET",
                   "EFFECT_CANNOT_ACTIVATE"}
SS_POS = {"faceup": "POS_FACEUP", "attack": "POS_FACEUP_ATTACK", "defense": "POS_FACEUP_DEFENSE",
          "facedown": "POS_FACEDOWN_DEFENSE"}
FUSION_LOC = {"hf": "LOCATION_HAND+LOCATION_MZONE", "hfg": "LOCATION_HAND+LOCATION_MZONE+LOCATION_GRAVE",
              "hfd": "LOCATION_HAND+LOCATION_MZONE+LOCATION_DECK", "hand": "LOCATION_HAND", "field": "LOCATION_MZONE"}
RITUAL_LOC = {"hand": "LOCATION_HAND", "hand_grave": "LOCATION_HAND+LOCATION_GRAVE",
              "hand_deck": "LOCATION_HAND+LOCATION_DECK"}
ACTIVITY = {"spsummon": "ACTIVITY_SPSUMMON", "summon": "ACTIVITY_SUMMON", "attack": "ACTIVITY_ATTACK",
            "chain": "ACTIVITY_CHAIN"}
ANNOUNCE_CALL = {"attribute": ("HINTMSG_ATTRIBUTE", "Duel.AnnounceAttribute(%s,1,ATTRIBUTE_ALL)"),
                 "race": ("HINTMSG_RACE", "Duel.AnnounceRace(%s,1,RACE_ALL)"),
                 "type": ("HINTMSG_CARDTYPE", "1<<Duel.AnnounceType(%s)"),
                 "level": ("HINTMSG_LVRANK", "Duel.AnnounceLevel(%s,1,12)"),
                 "card": ("HINTMSG_CODE", "Duel.AnnounceCard(%s)"),
                 "number": ("HINTMSG_NUMBER", "Duel.AnnounceNumber(%s,1,2,3,4,5,6,7,8,9,10,11,12)"),
                 "race_or_attr": None}
DECLARED = {"attribute": "c:IsAttribute(e:GetLabel())", "race": "c:IsRace(e:GetLabel())", "type": "c:IsType(e:GetLabel())",
            "level": "c:IsLevel(e:GetLabel())", "card": "c:IsCode(e:GetLabel())", "number": "c:IsLevel(e:GetLabel())",
            "race_or_attr": "(e:GetLabel()>0 and c:IsRace(e:GetLabel()) or e:GetLabel()<0 and c:IsAttribute(-e:GetLabel()))"}
DELAY = {"this_end": ("EVENT_PHASE+PHASE_END", "RESET_PHASE+PHASE_END", False),
         "next_end": ("EVENT_PHASE+PHASE_END", "RESET_PHASE+PHASE_END,2", True),
         "next_standby": ("EVENT_PHASE+PHASE_STANDBY", "RESET_PHASE+PHASE_STANDBY+RESET_SELF_TURN,Duel.GetTurnPlayer()==tp and 2 or 1",
                          True)}
DRAW_FLAG = 90           # 这个回合抽卡张数：玩家身上的标记 id+90，每抽1张记1个
CARRY_FLAG = 80          # 「之后再处理」带上的卡：卡身上的标记 id+80，标签是那次处理的编号
PREV_POS = {"faceup": "POS_FACEUP", "facedown": "POS_FACEDOWN", "attack": "POS_ATTACK", "defense": "POS_DEFENSE"}
STAT_GET = {"atk": "Card.GetAttack", "def": "Card.GetDefense", "level": "Card.GetLevel"}
FLAG_RESET = {("card", "end_of_turn"): "RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END",
              ("card", "permanent"): "RESET_EVENT+RESETS_STANDARD",
              ("player", "end_of_turn"): "RESET_PHASE+PHASE_END", ("player", "permanent"): "0"}
PLACE_FREE = {"szone": "Duel.GetLocationCount(tp,LOCATION_SZONE)>0", "fzone": None,
              "pzone": "(Duel.CheckLocation(tp,LOCATION_PZONE,0) or Duel.CheckLocation(tp,LOCATION_PZONE,1))"}
# 时机本身带的发动条件（事件只说了「破坏」，要再看原因、之前的位置……）
EVENT_COND = {"effect_destroyed": "e:GetHandler():IsReason(REASON_EFFECT)",
              "battle_destroying": "aux.bdocon(e,tp,eg,ep,ev,re,r,rp)",
              "field_to_grave": "e:GetHandler():IsPreviousLocation(LOCATION_ONFIELD)",
              "battle_damage": "ep~=tp", "be_targeted": "eg:IsContains(e:GetHandler())",
              "summon_attempt": "Duel.GetCurrentChain()==0", "spsummon_attempt": "Duel.GetCurrentChain()==0",
              "equip_battle_damage": "ep~=tp and e:GetHandler():GetEquipTarget() and "
                                     "eg:IsContains(e:GetHandler():GetEquipTarget())"}
# 时机的「谁的」→ 发动条件（%s 是 tp / 1-tp）
EVENT_PLAYER = {"draw": "ep==%s", "attack": "Duel.GetAttacker():IsControler(%s)", "chaining": "rp==%s",
                "standby": "Duel.GetTurnPlayer()==%s", "end": "Duel.GetTurnPlayer()==%s",
                "battle_end": "Duel.GetTurnPlayer()==%s", "be_targeted": "rp==%s",
                "monster_summoned": "eg:IsExists(Card.IsSummonPlayer,1,nil,%s)",
                "monster_spsummoned": "eg:IsExists(Card.IsSummonPlayer,1,nil,%s)",
                "summon_attempt": "eg:IsExists(Card.IsSummonPlayer,1,nil,%s)",
                "spsummon_attempt": "eg:IsExists(Card.IsSummonPlayer,1,nil,%s)",
                "monster_summoned_both": "eg:IsExists(Card.IsSummonPlayer,1,nil,%s)",
                "player_battle_damaged": "ep==%s", "player_damaged": "ep==%s",
                # 别的卡：送去墓地 / 除外 / 加入手卡 / 回到卡组看现在的控制者（就是持有者），破坏 / 离场看之前的控制者
                "cards_to_grave": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "cards_banished": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "cards_to_hand": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "cards_to_deck": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "cards_destroyed": "eg:IsExists(Card.IsPreviousControler,1,nil,%s)",
                "cards_leave_field": "eg:IsExists(Card.IsPreviousControler,1,nil,%s)",
                "monster_battle_destroyed": "eg:IsExists(Card.IsPreviousControler,1,nil,%s)",
                "monster_battle_start": "Duel.GetBattleMonster(%s)~=nil",
                "monster_damage_step_end": "Duel.GetBattleMonster(%s)~=nil",
                "chain_solved": "rp==%s", "chain_negated": "rp==%s", "bp_start": "Duel.GetTurnPlayer()==%s",
                "cards_set": "eg:IsExists(Card.IsControler,1,nil,%s)", "monsters_set": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "pos_changed": "eg:IsExists(Card.IsControler,1,nil,%s)", "detached": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "recovered": "ep==%s", "equipped": "eg:IsExists(Card.IsControler,1,nil,%s)",
                "cards_moved": "eg:IsExists(Card.IsControler,1,nil,%s)", "predraw": "Duel.GetTurnPlayer()==%s"}
SUMMON_TYPE = {"special": "SUMMON_TYPE_SPECIAL", "advance": "SUMMON_TYPE_ADVANCE", "fusion": "SUMMON_TYPE_FUSION",
               "synchro": "SUMMON_TYPE_SYNCHRO", "xyz": "SUMMON_TYPE_XYZ", "link": "SUMMON_TYPE_LINK",
               "ritual": "SUMMON_TYPE_RITUAL", "pendulum": "SUMMON_TYPE_PENDULUM"}
REASON = {"battle": "REASON_BATTLE", "effect": "REASON_EFFECT", "cost": "REASON_COST", "material": "REASON_MATERIAL",
          "release": "REASON_RELEASE", "discard": "REASON_DISCARD", "destroy": "REASON_DESTROY",
          "fusion": "REASON_FUSION", "synchro": "REASON_SYNCHRO", "xyz": "REASON_XYZ", "link": "REASON_LINK",
          "return": "REASON_RETURN", "reveal": "REASON_REVEAL", "draw": "REASON_DRAW"}
REASON = MultiMap(REASON, "|", wrap=True)          # 「被战斗·效果破坏」
NL = chr(10)
MAT_PRED = {"fusion": [("c:IsSetCard(", "c:IsFusionSetCard("), ("c:IsAttribute(", "c:IsFusionAttribute("),
                       ("c:IsType(", "c:IsFusionType("), ("c:IsCode(", "c:IsFusionCode(")],
            "link": [("c:IsSetCard(", "c:IsLinkSetCard("), ("c:IsAttribute(", "c:IsLinkAttribute("),
                     ("c:IsRace(", "c:IsLinkRace("), ("c:IsType(", "c:IsLinkType("), ("c:IsCode(", "c:IsLinkCode(")]}
TWICE_FLAG = 60          # 「最多2次」的使用次数：这张卡身上的标记 id+60+效果编号
ZONE_GROUP = {"column_group": "GetColumnGroup", "linked_group": "GetLinkedGroup", "equip_group": "GetEquipGroup"}
PHASE_COND = {"main": "Duel.IsMainPhase()", "battle": "Duel.IsBattlePhase()",
              "main1": "Duel.GetCurrentPhase()==PHASE_MAIN1", "main2": "Duel.GetCurrentPhase()==PHASE_MAIN2",
              "standby": "Duel.GetCurrentPhase()==PHASE_STANDBY", "end": "Duel.GetCurrentPhase()==PHASE_END",
              "draw": "Duel.GetCurrentPhase()==PHASE_DRAW", "battle_step": "Duel.GetCurrentPhase()==PHASE_BATTLE_STEP",
              "damage": "Duel.GetCurrentPhase()==PHASE_DAMAGE", "damage_calc": "Duel.GetCurrentPhase()==PHASE_DAMAGE_CAL"}
PHASE_COND = MultiMap(PHASE_COND, " or ", wrap=True)     # 「主要阶段或者战斗阶段」
# 「只对对方的效果」的抗性：效果代码 → SetValue 的函数
AGAINST_OPP = {"EFFECT_CANNOT_BE_EFFECT_TARGET": "aux.tgoval", "EFFECT_INDESTRUCTABLE_EFFECT": "aux.indoval",
               "EFFECT_IMMUNE_EFFECT": "s.efilter_opp"}
FUNC_LIB = {"s.efilter_opp": "function s.efilter_opp(e,te)\n\treturn te:GetOwnerPlayer()~=e:GetHandlerPlayer()\nend",
            "s.efilter_other": "function s.efilter_other(e,te)\n\treturn te:GetOwner()~=e:GetOwner()\nend",
            "s.eqlimit": "function s.eqlimit(e,c)\n\treturn c==e:GetLabelObject()\nend",
            "s.indct": "function s.indct(e,re,r,rp)\n\treturn r&(REASON_BATTLE+REASON_EFFECT)~=0\nend",
            "s.chlimit": "function s.chlimit(e,ep,tp)\n\treturn tp==ep\nend"}
CHAIN_CAT = {"destroy": "CATEGORY_DESTROY", "special_summon": "CATEGORY_SPECIAL_SUMMON", "search": "CATEGORY_SEARCH",
             "remove": "CATEGORY_REMOVE", "to_grave": "CATEGORY_TOGRAVE", "draw": "CATEGORY_DRAW",
             "negate": "CATEGORY_NEGATE", "to_hand": "CATEGORY_TOHAND"}
PROC_FLAG = 70           # 用这张卡的召唤手续出场的：卡身上的标记 id+70
# 没放数值时默认 SetValue(1) 的效果代码（「不会被破坏」之类：引擎按数值真假判断）
VALUE_ONE = {"EFFECT_INDESTRUCTABLE_BATTLE", "EFFECT_INDESTRUCTABLE_EFFECT", "EFFECT_INDESTRUCTABLE",
             "EFFECT_CANNOT_BE_EFFECT_TARGET", "EFFECT_CANNOT_BE_BATTLE_TARGET", "EFFECT_ATTACK_ALL",
             "EFFECT_UNRELEASABLE_SUM", "EFFECT_UNRELEASABLE_NONSUM", "EFFECT_CANNOT_BE_FUSION_MATERIAL",
             "EFFECT_CANNOT_BE_SYNCHRO_MATERIAL", "EFFECT_CANNOT_BE_XYZ_MATERIAL", "EFFECT_CANNOT_BE_LINK_MATERIAL",
             "EFFECT_EXTRA_ATTACK", "EFFECT_EXTRA_ATTACK_MONSTER"}
# 这张卡自己的事件：单体诱发
SELF_EVENTS = ("summon", "spsummon", "summon_both", "to_grave", "destroyed", "be_attacked", "battle_destroyed",
               "effect_destroyed", "battle_destroying", "leave_field", "field_to_grave", "banished", "released",
               "to_hand", "flip_summon", "flip", "be_material", "battle_damage", "battle_start", "pre_damage_calc", "battled",
               "damage_step_end", "battle_confirm", "leaving")
# 「……的场合」：不会错过时点
DELAY_EVENTS = ("summon", "spsummon", "summon_both", "to_grave", "destroyed", "draw", "battle_destroyed",
                "effect_destroyed", "leave_field", "field_to_grave", "banished", "released", "to_hand", "flip_summon", "flip",
                "be_material", "monster_summoned", "monster_spsummoned", "monster_summoned_both", "cards_to_grave",
                "cards_banished", "cards_destroyed", "cards_to_hand", "cards_to_deck", "cards_leave_field",
                "monster_battle_destroyed")
PHASE_EVENTS = ("standby", "end", "battle_end", "bp_start")


class CompileError(Exception):
    pass


def single(var):
    """cards_expr 给出的变量是一张卡（不是卡片组）。"""
    return var in ("c", "tc", "atk", "at", "bc", "eqm", "re:GetHandler()") or var.startswith(("ec", "tc_", "bm_"))


def indent(lines, n=1):
    return ["\t" * n + l for l in lines]


def one(node, slot):
    """单块的槽：放了就返回那一块，没放返回 None。"""
    items = node.get(slot) or []
    return items[0] if items else None


NO_MULTI_SUMMON = "not Duel.IsPlayerAffectedByEffect(tp,59822133)"      # 「青眼精灵龙」：不能同时特殊召唤 2 只以上


def walk(node):
    """积木树里所有积木（深度优先）。"""
    if isinstance(node, dict):
        if "block" in node:
            yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def tokens(card):
    """DIY 衍生物：按出现顺序编号 1、2……，导出时卡号＝这张卡的卡号＋编号。返回 [(编号, 衍生物积木)]。"""
    return [(i + 1, n) for i, n in enumerate(b for b in walk(card.get("effects", [])) if b["block"] == "create_token")]


class Compiler:
    def __init__(self, card):
        self.card = card
        self.funcs = []
        self.filters = {}        # 过滤条件 → 函数名
        self.strings = []        # aux.Stringid(id, n) 的提示文字
        self.n = 0               # 局部变量 / 函数的序号
        self.k = 0               # 第几个效果
        self.target = None       # 当前效果的取对象积木
        self.each = []           # 「对每一张」的循环变量
        self.token_no = {id(b): n for n, b in tokens(card)}
        self.libs = set()        # 用到的固定辅助函数（FUNC_LIB）
        self.no_chain = False    # 正在翻译「每次……（不入连锁）」：没有连锁，不查 IsRelateToEffect
        self.in_delay = None     # 正在翻译「之后再处理」：None / "plain" / "carry"
        self.uses_cost_cards = False
        self.uses_by_proc = False
        self.targets = []        # 当前效果的全部取对象积木（「自己1只和对方1只」是两块）

    def fresh(self, base):
        self.n += 1
        return "%s%d" % (base, self.n)

    def add_func(self, text):
        self.funcs.append(text)

    def fn(self, base, body):
        """按函数体去重登记一个辅助函数（body 里的 %s 是函数名）。"""
        key = body % "@"
        if key not in self.filters:
            self.filters[key] = "s.%s" % self.fresh(base)
            self.add_func(body % self.filters[key])
        return self.filters[key]

    def lib(self, name):
        """用到一个固定的辅助函数（只写一次）。"""
        if name in FUNC_LIB and name not in self.libs:
            self.libs.add(name)
            self.add_func(FUNC_LIB[name])
        return name

    def special_value(self, code, against):
        """抗性类效果代码的 SetValue：只对对方的效果、「其他卡的效果」。没有特别的写法返回 None。"""
        if against == "opp" and code in AGAINST_OPP:
            return self.lib(AGAINST_OPP[code])
        if code == "EFFECT_IMMUNE_EFFECT":
            return self.lib("s.efilter_other")
        if code == "EFFECT_INDESTRUCTABLE_COUNT":        # 「只有1次不会被战斗以及卡的效果破坏」
            return self.lib("s.indct")
        return None

    def count_of(self, node):
        """张数：放了「算出来的张数」就用它，不然用填的数字。"""
        n = one(node, "count_n")
        return self.number(n) if n is not None else str(node["count"])

    def span(self, node):
        """选卡的张数 → (最少, 最多, 发动时至少要有几张)。「最多N张」最少1张；算出来的张数发动时只要求有1张。"""
        hi = self.count_of(node)
        lo = "1" if node.get("upto") == "yes" else hi
        need = node["count"] if one(node, "count_n") is None and node.get("upto") != "yes" else 1
        return lo, hi, need

    def ability(self, st):
        """动作要求的「能不能这样处理」（选卡时只给能处理的卡）。"""
        b = st["block"]
        if b == "special_summon":
            return self.ss_parts(st)[1]
        if b == "change_position" and st.get("to") == "facedown":
            return "c:IsCanTurnSet()"
        if b == "banish" and st.get("face") == "down":
            return "c:IsAbleToRemove(tp,POS_FACEDOWN)"
        return ACTS[b][3]

    def call_of(self, st, cost=False):
        """移动卡片的调用（%s 是卡）：除外的表示形式、回到卡组的位置。"""
        b = st["block"]
        reason = "REASON_COST" if cost else "REASON_EFFECT"
        if b == "banish":
            if st.get("temp") == "yes" and not cost:         # 暂时除外：之后用「回到场上」
                reason += "+REASON_TEMPORARY"
            return "Duel.Remove(%%s,%s,%s)" % ("POS_FACEDOWN" if st.get("face") == "down" else "POS_FACEUP", reason)
        if b == "to_hand" and st.get("to") == "opp":
            return "Duel.SendtoHand(%%s,1-tp,%s)" % reason
        if b == "to_deck" and st.get("seq") == "bottom_order":
            return "aux.PlaceCardsOnDeckBottom(tp,%%s,%s)" % reason
        if b == "to_deck":
            seq = {"top": "SEQ_DECKTOP", "bottom": "SEQ_DECKBOTTOM"}.get(st.get("seq"), "SEQ_DECKSHUFFLE")
            return "Duel.SendtoDeck(%%s,nil,%s,%s)" % (seq, reason)
        return ACTS[b][5] if cost else ACTS[b][0]

    def ss_parts(self, st):
        """特殊召唤 → (调用, 能不能特殊召唤, 在谁的场上)。"""
        pos = SS_POS[st.get("position") or "faceup"]
        to = PLAYER[st.get("to") or "you"]
        ign = "true" if st.get("ignore") == "yes" else "false"
        return ("Duel.SpecialSummon(%%s,0,tp,%s,%s,false,%s)" % (to, ign, pos),
                "c:IsCanBeSpecialSummoned(e,0,tp,%s,false,%s,%s)" % (ign, pos, to), to)

    def fusion_call(self, st, part, chk=None):
        """融合召唤：用引擎的 aux.FusionEffectUltimateTarget / Operation（素材选择、额外卡组的检查都在里面）。"""
        f = self.filter_fn(st) if st.get("filter") else "nil"
        # 参数的默认值照 aux.AddFusionEffectProcUltimate 补齐（墓地的素材除外，其余送去墓地）
        params = self.fn("fusparams", "\n".join([
            "function %s()",
            "\tlocal p={filter=%s,mat_location=%s}" % (f, FUSION_LOC[st.get("mats") or "hf"]),
            "\tp.mat_filter=aux.FMaterialFilter",
            "\tp.mat_operation=aux.FMaterialToGrave",
            "\tp.grave_filter=aux.FMaterialRemoveFilter",
            "\tp.grave_operation=aux.FMaterialRemove",
            "\tp.removed_operation=p.mat_operation",
            "\tp.deck_filter=aux.FMaterialToGraveFilter",
            "\tp.deck_operation=p.mat_operation",
            "\tp.extra_filter=aux.FMaterialToGraveFilter",
            "\tp.extra_operation=p.mat_operation",
            "\tp.spsummon_nocheck=false",
            "\treturn p",
            "end"]))
        return "aux.FusionEffectUltimate%s(%s())(e,tp,eg,ep,ev,re,r,rp%s)" % (part, params, "" if chk is None else "," + chk)

    def ritual_call(self, st, part, chk=None):
        """仪式召唤：aux.RitualUltimateTarget / Operation（解放手卡·场上的怪兽，等级合计以上 / 相同）。"""
        f = self.filter_fn(st) if st.get("filter") else "nil"
        how = '"Equal"' if st.get("level") == "equal" else '"Greater"'
        return "aux.RitualUltimate%s(%s,Card.GetOriginalLevel,%s,%s)(e,tp,eg,ep,ev,re,r,rp%s)" % (
            part, f, how, RITUAL_LOC[st.get("from") or "hand"], "" if chk is None else "," + chk)

    def string(self, text):
        self.strings.append(text)
        return len(self.strings) - 1

    # ------------------------------------------------------------ 卡片条件
    def preds(self, filters):
        kinds = [f["kind"] for f in filters if f["block"] == "f_kind"]
        out = []
        for f in filters:
            b = f["block"]
            if b == "f_subtype" and f["subtype"] == "normal" and kinds and kinds[0] in ("spell", "trap"):
                out.append("c:GetType()==%s" % TYPE[kinds[0]])         # 通常魔法 / 陷阱：只有「魔法」「陷阱」这一位
            else:
                out.append(self.pred(f))
        mode = getattr(self, "mat_mode", None)
        if mode:            # 融合 / 连接素材的条件：用素材专用的判断（代替素材、当作素材时的属性……）
            for a, b in MAT_PRED[mode]:
                out = [x.replace(a, b) for x in out]
        return out

    def pred(self, f):
        b = f["block"]
        if b == "f_kind":
            return "c:IsType(%s)" % TYPE[f["kind"]]
        if b == "f_subtype":
            return "c:IsType(%s)" % TYPE[f["subtype"]]
        if b == "f_race":
            return "c:IsRace(RACE_%s)" % RACE[f["race"]]
        if b == "f_attr":
            return "c:IsAttribute(%s)" % ATTR[f["attribute"]]
        if b in ("f_level", "f_atk", "f_def"):
            stat = {"f_level": "level", "f_atk": "atk", "f_def": "def"}[b]
            vn = one(f, "value_n")
            value = self.number(vn) if vn is not None else str(f["value"])     # 过滤函数里有 e、tp，数值照样能算
            if (stat, f["op"]) in STAT_FN:
                return "c:%s(%s)" % (STAT_FN[(stat, f["op"])], value)
            getter = {"level": "GetLevel", "atk": "GetAttack", "def": "GetDefense"}[stat]
            return "c:%s()%s%s" % (getter, LUA_OP[f["op"]], value)
        if b == "f_name":
            return "c:IsCode(%d)" % int(f["code"])
        if b == "f_set":
            return "c:IsSetCard(%s)" % (f["setcode"] or "0x0")
        if b == "f_position":
            return "c:%s()" % POSITION[f["position"]]
        if b == "f_not_self":
            return "c~=e:GetHandler()"
        if b == "f_controller":
            return "c:IsControler(%s)" % PLAYER[f["who"]]
        if b == "f_summon_type":
            ways = multi_parts(f["method"], SUMMON_TYPE)
            if len(ways) == 1:
                return "c:IsSummonType(%s)" % SUMMON_TYPE[ways[0]]
            return "(%s)" % " or ".join("c:IsSummonType(%s)" % SUMMON_TYPE[w] for w in ways)
        if b == "f_prev_location":
            return "c:IsPreviousLocation(%s)" % LOC[f["where"]]
        if b == "f_prev_position":
            return "c:IsPreviousPosition(%s)" % PREV_POS[f["position"]]
        if b == "f_lists_code":
            return "aux.IsCodeListed(c,%d)" % int(f["code"])
        if b == "f_zone_seq":
            return {"main": "c:GetSequence()<5", "extra": "c:GetSequence()>=5", "middle": "c:GetSequence()==2"}[f["seq"]]
        if b == "f_has_effect":
            return "c:IsHasEffect(%s)" % f["code"]
        if b == "f_not_destroying":
            return "not c:IsStatus(STATUS_DESTROY_CONFIRMED)"
        if b == "f_chaining":
            return "c:IsStatus(STATUS_CHAINING)"
        if b == "f_battle_pair":
            if f["who"] == "both":
                return "(e:GetHandler():GetBattleTarget()~=nil and (c==e:GetHandler() or c==e:GetHandler():GetBattleTarget()))"
            return "c==e:GetHandler():GetBattleTarget()"
        if b == "f_battled_opp":
            return "c:IsStatus(STATUS_OPPO_BATTLE)"
        if b == "f_can_attack":
            return "c:IsAttackable()"
        if b == "f_prev_name":
            return "c:GetPreviousCodeOnField()==%d" % int(f["code"])
        if b == "f_activated_effect":
            return "true"
        if b == "f_orig_race":
            return "c:GetOriginalRace()&(RACE_%s)~=0" % RACE[f["race"]]
        if b == "f_orig_attr":
            return "c:GetOriginalAttribute()&%s~=0" % ATTR[f["attribute"]]
        if b == "f_prev_kind":
            return "c:GetPreviousTypeOnField()&(%s)~=0" % TYPE[f["kind"]]
        if b == "f_by_this":
            return "(c:GetReasonCard()==e:GetHandler() or c:GetReasonEffect() and c:GetReasonEffect():GetHandler()==e:GetHandler())"
        if b == "f_prev_set":
            return "c:IsPreviousSetCard(%s)" % (f["setcode"] or "0x0")
        if b == "f_prev_race":
            return "c:GetPreviousRaceOnField()&(RACE_%s)~=0" % RACE[f["race"]]
        if b == "f_prev_attr":
            return "c:GetPreviousAttributeOnField()&%s~=0" % ATTR[f["attribute"]]
        if b == "f_same_column":
            return "e:GetHandler():GetColumnGroup():IsContains(c)"
        if b == "f_linked":
            return "e:GetHandler():GetLinkedGroup():IsContains(c)"
        if b == "f_link_state":
            return "c:IsLinkState()"
        if b in ("f_rank", "f_link"):
            word = "Rank" if b == "f_rank" else "Link"
            fn = {"<=": "Is%sBelow", ">=": "Is%sAbove", "==": "Is%s"}.get(f["op"])
            if fn:
                return "c:%s(%d)" % (fn % word, f["value"])
            return "c:Get%s()%s%d" % (word, LUA_OP[f["op"]], f["value"])
        if b in ("f_same_attr", "f_same_race"):
            card, group = self.card_inline(one(f, "card"))
            card = "%s:GetFirst()" % card if group else card
            what = "Attribute" if b == "f_same_attr" else "Race"
            return "c:Is%s(%s:Get%s())" % (what, card, what)
        if b == "f_any":
            parts = []
            for it in f.get("items") or []:
                inner = self.preds(it.get("filter") or []) if it["block"] == "f_all" else [self.pred(it)]
                parts.append("(%s)" % (" and ".join(inner) or "true"))
            return "(%s)" % (" or ".join(parts) or "false")
        if b == "f_all":
            return "(%s)" % (" and ".join(self.preds(f.get("filter") or [])) or "true")
        if b == "f_by_proc":
            return "c:GetFlagEffect(id+%d)>0" % PROC_FLAG
        if b == "f_same_code":
            card, group = self.card_inline(one(f, "card"))
            card = "%s:GetFirst()" % card if group else card
            return "c:IsOriginalCodeRule(%s:GetOriginalCodeRule())" % card
        if b == "f_by_player":
            return "c:GetReasonPlayer()==%s" % PLAYER[f["who"]]
        if b == "f_declared":
            return DECLARED[f["what"]]
        if b == "f_prev_controller":
            return "c:IsPreviousControler(%s)" % PLAYER[f["who"]]
        if b == "f_reason":
            return "c:IsReason(%s)" % REASON[f["reason"]]
        if b == "f_not":
            inner = self.preds(f.get("filter", []))
            return "not (%s)" % " and ".join(inner) if inner else "false"
        raise CompileError("卡片条件 %r 还不能翻译" % b)

    def filter_fn(self, node, ability=None):
        """卡片组积木的卡片条件 → 过滤函数名（没有条件时 aux.TRUE）。ability：动作要求的「能不能这样处理」。"""
        preds = self.preds(node.get("filter", []))
        if ability:
            preds.append(ability)
        if not preds:
            return "aux.TRUE"
        return self.fn("filter", "function %%s(c,e,tp)\n\treturn %s\nend" % " and ".join(preds))

    def sides(self, node, who="who", where="where"):
        loc = LOC[node[where]]
        return {"you": (loc, "0"), "opp": ("0", loc), "both": (loc, loc)}[node[who]]

    # ------------------------------------------------------------ 卡片组
    def cards_expr(self, node, ability=None, hint="HINTMSG_SELECT", cost=False):
        """卡片组积木 → (先执行的语句, 变量, 执行前的检查)。"""
        if node is None:
            raise CompileError("有一个「哪些卡」还没放卡片积木")
        b = node["block"]
        if b == "this_card":
            return [], "c", "c:IsRelateToEffect(e)" if not (cost or self.no_chain) else "true"
        if b == "card_target":
            return ["local tc_ct=e:GetHandler():GetFirstCardTarget()"], "tc_ct", "tc_ct"
        if b == "prev_equip_target":
            return ["local tc_pe=e:GetHandler():GetPreviousEquipTarget()"], "tc_pe", "tc_pe"
        if b == "carried":
            if self.in_delay != "carry":
                raise CompileError("「带过来的卡」只能放在选了「带上前一步处理的卡」的「之后再处理」里面")
            return [], "cg", "#cg>0"
        if b == "cost_cards":
            return ["local kg=e:GetLabelObject()"], "kg", "kg and #kg>0"
        if b == "random_pick":
            s_, o_ = self.sides(node)
            v = self.fresh("rg")
            f = self.filter_fn(node, ability)
            return ["local %s=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):RandomSelect(tp,%d)" % (v, f, s_, o_, node["count"])], \
                v, "#%s>0" % v
        if b in ("column_group", "linked_group", "equip_group"):
            v = self.fresh("zg")
            get = ZONE_GROUP[b]
            f = self.filter_fn(node, ability) if ability else None
            expr = "e:GetHandler():%s()" % get + (":Filter(%s,nil,e,tp)" % f if f else "")
            return ["local %s=%s" % (v, expr)], v, "#%s>0" % v
        if b == "max_of":
            pre, var, guard = self.cards_expr(one(node, "cards"), ability, hint, cost)
            if single(var):
                return pre, var, guard
            v = self.fresh("mg")
            get = {"atk": "Card.GetAttack", "def": "Card.GetDefense", "level": "Card.GetLevel"}[node["stat"]]
            return pre + ["local %s=%s:Get%sGroup(%s)" % (v, var, "Max" if node["which"] == "max" else "Min", get)], v, \
                "%s and #%s>0" % (v, v)
        if b == "target" and self.in_delay:
            raise CompileError("「之后再处理」里不能用「对象」：请选「带上前一步处理的卡」，里面用「带过来的卡」")
        if b == "target":
            t = next((x for x in self.targets if x["as"] == node["name"]), None)
            if t is None:
                raise CompileError("「对象 %s」：这个效果的「对象」槽里没有记作 %s 的取对象积木" % (node["name"], node["name"]))
            if len(self.targets) > 1:          # 几组对象：处理开头按组分好了
                if t["count"] == 1:
                    return [], "tc_%s" % t["as"], "tc_%s" % t["as"]
                return [], "tg_%s" % t["as"], "#tg_%s>0" % t["as"]
            if t["count"] == 1:
                return [], "tc", "tc and tc:IsRelateToEffect(e)"
            return [], "tg", "#tg>0"
        if b == "var":
            return [], "v%s" % node["name"], "#v%s>0" % node["name"]
        if b == "operated":
            v = self.fresh("og")
            if node.get("filter"):
                return ["local %s=Duel.GetOperatedGroup():Filter(%s,nil,e,tp)" % (v, self.filter_fn(node, ability))], \
                    v, "#%s>0" % v
            return ["local %s=Duel.GetOperatedGroup()" % v], v, "#%s>0" % v
        if b == "each":
            if not self.each:
                raise CompileError("「当前这张」只能放在「对每一张」里面")
            return [], self.each[-1], "true"
        if b == "chain_card":
            return [], "re:GetHandler()", "re:GetHandler():IsRelateToEffect(re)"
        if b == "event_cards":
            if node.get("filter"):
                v = self.fresh("eg")
                return ["local %s=eg:Filter(%s,nil,e,tp)" % (v, self.filter_fn(node, ability))], v, "#%s>0" % v
            return [], "eg", "#eg>0"
        if b == "attacker":
            return ["local atk=Duel.GetAttacker()"], "atk", "atk and atk:IsRelateToBattle()"
        if b == "attack_target":
            return ["local at=Duel.GetAttackTarget()"], "at", "at and at:IsRelateToBattle()"
        if b == "battling":
            v = "bm_%s" % node["who"]
            get = "(Duel.GetBattleMonster(tp))" if node["who"] == "you" else "select(2,Duel.GetBattleMonster(tp))"
            return ["local %s=%s" % (v, get)], v, "%s and %s:IsRelateToBattle()" % (v, v)
        if b == "battle_opp":
            return ["local bc=e:GetHandler():GetBattleTarget()"], "bc", "bc and bc:IsRelateToBattle()"
        if b == "equip_target":
            return ["local eqm=e:GetHandler():GetEquipTarget()"], "eqm", "eqm"
        if b == "overlay":
            v = self.fresh("xg")
            return ["local %s=e:GetHandler():GetOverlayGroup()" % v], v, "#%s>0" % v
        if b == "deck_top":
            v = self.fresh("dg")
            return ["Duel.DisableShuffleCheck()", "local %s=Duel.GetDecktopGroup(%s,%s)" % (v, PLAYER[node["who"]],
                                                                                        self.count_of(node))], v, \
                "#%s>0" % v
        if b in ("all", "pick"):
            s_, o_ = self.sides(node)
            v = self.fresh("g")
            if b == "all":
                f = self.filter_fn(node, ability)
                return ["local %s=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (v, f, s_, o_)], v, "#%s>0" % v
            f = self.filter_fn(node, ability)
            if "grave" in node["where"] and not cost:
                f = "aux.NecroValleyFilter(%s)" % f
            lo, hi, need = self.span(node)
            excl = "e:GetHandler()" if cost else "nil"
            if node.get("different") == "yes" and (need > 1 or one(node, "count_n") is not None):
                return ["local %sa=Duel.GetMatchingGroup(%s,tp,%s,%s,%s,e,tp)" % (v, f, s_, o_, excl),
                        "Duel.Hint(HINT_SELECTMSG,tp,%s)" % hint,
                        "local %s=%sa:SelectSubGroup(tp,aux.dncheck,false,%s,%s) or Group.CreateGroup()" % (v, v, lo, hi)], \
                    v, "#%s>0" % v
            return ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % hint,
                    "local %s=Duel.SelectMatchingCard(tp,%s,tp,%s,%s,%s,%s,%s,e,tp)" % (v, f, s_, o_, lo, hi, excl)], v, \
                "#%s>0" % v
        raise CompileError("卡片积木 %r 不能放在这里" % b)

    def card_inline(self, node):
        """在条件 / 数值里用的卡片：返回 (Lua 表达式, 是不是一组卡)；「全部」返回 (积木, True)。"""
        b = node["block"] if node else None
        if node is None:
            raise CompileError("条件 / 数值里有一个「哪张卡」还没放积木")
        if b == "this_card":
            return "e:GetHandler()", False
        if b == "card_target":
            return "e:GetHandler():GetFirstCardTarget()", False
        if b == "prev_equip_target":
            return "e:GetHandler():GetPreviousEquipTarget()", False
        if b == "chain_card":
            return "re:GetHandler()", False
        if b == "attacker":
            return "Duel.GetAttacker()", False
        if b == "each":
            if not self.each:
                raise CompileError("「当前这张」只能放在「对每一张」里面")
            return self.each[-1], False
        if b == "target":
            t = next((x for x in self.targets if x["as"] == node["name"]), None)
            if t is not None and len(self.targets) > 1:
                return ("tc_%s" if t["count"] == 1 else "tg_%s") % t["as"], t["count"] != 1
            if self.target and self.target["count"] == 1:
                return "Duel.GetFirstTarget()", False
            return "Duel.GetChainInfo(0,CHAININFO_TARGET_CARDS)", True
        if b == "var":
            return "s.v_%s" % node["name"], True
        if b == "event_cards":
            if node.get("filter"):
                return "eg:Filter(%s,nil,e,tp)" % self.filter_fn(node), True
            return "eg", True
        if b == "attack_target":
            return "Duel.GetAttackTarget()", False
        if b == "battling":
            return ("(Duel.GetBattleMonster(tp))" if node["who"] == "you" else "select(2,Duel.GetBattleMonster(tp))"), False
        if b == "battle_opp":
            return "e:GetHandler():GetBattleTarget()", False
        if b == "equip_target":
            return "e:GetHandler():GetEquipTarget()", False
        if b == "cost_cards":
            return "e:GetLabelObject()", True
        if b in ("column_group", "linked_group", "equip_group"):
            return "e:GetHandler():%s()" % ZONE_GROUP[b], True
        if b == "max_of":
            inner, group = self.card_inline(one(node, "cards"))
            if isinstance(inner, dict):
                s_, o_ = self.sides(inner)
                inner = "Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (self.filter_fn(inner), s_, o_)
            elif not group:
                return inner, False
            get = {"atk": "Card.GetAttack", "def": "Card.GetDefense", "level": "Card.GetLevel"}[node["stat"]]
            return "(%s:Get%sGroup(%s))" % (inner, "Max" if node["which"] == "max" else "Min", get), True
        if b == "operated":
            if node.get("filter"):
                return "Duel.GetOperatedGroup():Filter(%s,nil,e,tp)" % self.filter_fn(node), True
            return "Duel.GetOperatedGroup()", True
        if b == "carried":
            if self.in_delay != "carry":
                raise CompileError("「带过来的卡」只能放在选了「带上前一步处理的卡」的「之后再处理」里面")
            return "cg", True
        if b == "deck_top":
            return "Duel.GetDecktopGroup(%s,%s)" % (PLAYER[node["who"]], self.count_of(node)), True
        if b == "overlay":
            return "e:GetHandler():GetOverlayGroup()", True
        if b == "all":
            return node, True
        raise CompileError("条件和数值里不能用「%s」" % BLOCKS[b].label)

    # ------------------------------------------------------------ 数值与条件
    def number(self, node):
        if node is None:
            raise CompileError("有一个数值还没放积木")
        b = node["block"]
        if b == "num":
            return str(node["value"])
        if b == "turn_count":
            p = PLAYER[node["player"]]
            if node["what"] == "draw":
                self.need_draw_count = True
                return "Duel.GetFlagEffect(%s,id+%d)" % (p, DRAW_FLAG)
            return "Duel.GetActivityCount(%s,%s)" % (p, ACTIVITY[node["what"]])
        if b == "turn_number":
            return "Duel.GetTurnCount()"
        if b == "chain_count":
            return "Duel.GetCurrentChain()"
        if b == "declared_num":
            return "e:GetLabel()"
        if b == "dice_value":
            return "dice"
        if b == "event_value":
            return "ev"
        if b in ("counter_of", "sum_of"):
            key = "card" if b == "counter_of" else "cards"
            cards, group = self.card_inline(one(node, key))
            getter, arg = ("Card.GetCounter", "," + node["counter"]) if b == "counter_of" else (STAT_GET[node["stat"]], "")
            if isinstance(cards, dict):
                s_, o_ = self.sides(cards)
                return "Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):GetSum(%s%s)" % (self.filter_fn(cards), s_, o_, getter, arg)
            if group:
                return "%s:GetSum(%s%s)" % (cards, getter, arg)
            return "%s:%s(%s)" % (cards, getter.split(".")[1], arg.lstrip(","))
        if b == "name_kinds":
            cards, group = self.card_inline(one(node, "cards"))
            if isinstance(cards, dict):
                s_, o_ = self.sides(cards)
                return "Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):GetClassCount(Card.GetCode)" % (
                    self.filter_fn(cards), s_, o_)
            return "%s:GetClassCount(Card.GetCode)" % cards if group else "1"
        if b == "battle_damage":
            return "Duel.GetBattleDamage(%s)" % PLAYER[node["player"]]
        if b == "flag_count":
            if node["on"] == "card":
                return "e:GetHandler():GetFlagEffect(id+%d)" % node["name"]
            return "Duel.GetFlagEffect(tp,id+%d)" % node["name"]
        if b == "material_count":
            return "e:GetHandler():GetMaterialCount()"
        if b == "prev_atk_of":
            card, group = self.card_inline(one(node, "card"))
            return "%s:GetPreviousAttackOnField()" % ("%s:GetFirst()" % card if group else card)
        if b in ("rank_of", "link_of"):
            card, group = self.card_inline(one(node, "card"))
            return "%s:Get%s()" % ("%s:GetFirst()" % card if group else card, "Rank" if b == "rank_of" else "Link")
        if b in ("atk_of", "def_of", "level_of", "base_atk_of", "base_def_of", "text_atk_of", "text_def_of", "scale_of", "attacked_count", "prev_overlay_count"):
            card, group = self.card_inline(one(node, "card"))
            if isinstance(card, dict):
                raise CompileError("「%s」要接一张卡" % BLOCKS[b].label)
            getter = {"atk_of": "GetAttack", "def_of": "GetDefense", "level_of": "GetLevel",
                      "text_atk_of": "GetTextAttack", "text_def_of": "GetTextDefense", "scale_of": "GetLeftScale",
                      "attacked_count": "GetAttackedCount", "prev_overlay_count": "GetPreviousOverlayCountOnField",
                      "base_atk_of": "GetBaseAttack", "base_def_of": "GetBaseDefense"}[b]
            return "%s:%s()" % ("%s:GetFirst()" % card if group else card, getter)
        if b == "count_of":
            cards, group = self.card_inline(one(node, "cards"))
            if isinstance(cards, dict):
                s_, o_ = self.sides(cards)
                return "Duel.GetMatchingGroupCount(%s,tp,%s,%s,nil,e,tp)" % (self.filter_fn(cards), s_, o_)
            return "#%s" % cards if group else "1"
        if b == "lp_of":
            return "Duel.GetLP(%s)" % PLAYER[node["player"]]
        if b == "math":
            l, r = self.number(one(node, "left")), self.number(one(node, "right"))
            return "math.floor(%s/%s)" % (l, r) if node["op"] == "//" else "(%s%s%s)" % (l, node["op"], r)
        raise CompileError("数值积木 %r 还不能翻译" % b)

    def cond(self, node):
        if node is None:
            raise CompileError("有一个条件还没放积木")
        b = node["block"]
        if b == "compare":
            return "%s%s%s" % (self.number(one(node, "left")), LUA_OP[node["op"]], self.number(one(node, "right")))
        if b == "exists":
            cards, group = self.card_inline(one(node, "cards"))
            if isinstance(cards, dict):
                s_, o_ = self.sides(cards)
                return "Duel.IsExistingMatchingCard(%s,tp,%s,%s,1,nil,e,tp)" % (self.filter_fn(cards), s_, o_)
            return "(%s and #%s>0)" % (cards, cards) if group else "%s~=nil" % cards
        if b == "turn":
            return "Duel.GetTurnPlayer()==%s" % PLAYER[node["player"]]
        if b == "phase":
            return PHASE_COND[node["phase"]]
        if b == "coin_heads":
            return "coin==1"
        if b == "coin_right":
            return "coin==call"
        if b == "can_chain_attack":
            return "Duel.IsChainAttackable()"
        if b == "not_sent_this_turn":
            return "aux.exccon(e)"
        if b == "player_affected":
            return "Duel.IsPlayerAffectedByEffect(%s,%s)" % (PLAYER[node["player"]], node["code"])
        if b == "can_enter_bp":
            return "Duel.IsAbleToEnterBP()"
        if b == "can_normal_draw":
            return "aux.IsPlayerCanNormalDraw(tp)"
        if b == "this_battled":
            return "e:GetHandler():GetBattledGroupCount()>0"
        if b == "this_attacked":
            return "e:GetHandler():GetAttackAnnouncedCount()>0"
        if b == "gemini_state":
            return "aux.IsDualState(e)"
        if b == "union_state":
            return "aux.IsUnionState(e)"
        if b == "chain_is":
            return CHAIN_IS[node["what"]]
        if b == "chain_does":
            return "re:IsHasCategory(%s)" % CHAIN_CAT[node["what"]]
        if b == "materials_are":
            f = self.filter_fn({"filter": node.get("filter") or []})
            if node["mode"] == "all":
                return "(e:GetHandler():GetMaterialCount()>0 and not e:GetHandler():GetMaterial():IsExists(aux.NOT(%s),1,nil,e,tp))" % f
            return "e:GetHandler():GetMaterial():IsExists(%s,1,nil,e,tp)" % f
        if b == "has_flag":
            if node["on"] == "card":
                return "e:GetHandler():GetFlagEffect(id+%d)>0" % node["name"]
            return "Duel.GetFlagEffect(tp,id+%d)>0" % node["name"]
        if b == "card_is":
            src = one(node, "cards")
            filters = node.get("filter") or []
            if src is not None and src["block"] == "all":
                merged = dict(src, filter=list(src.get("filter") or []) + filters)
                s_, o_ = self.sides(merged)
                return "Duel.IsExistingMatchingCard(%s,tp,%s,%s,1,nil,e,tp)" % (self.filter_fn(merged), s_, o_)
            card, group = self.card_inline(src)
            f = self.filter_fn({"filter": filters})
            if group:
                return "%s:IsExists(%s,1,nil,e,tp)" % (card, f)
            return "(%s and %s(%s,e,tp))" % (card, f, card) if f != "aux.TRUE" else "%s~=nil" % card
        if b in ("all_of", "any_of"):
            items = [self.cond(x) for x in node.get("items", [])]
            if not items:
                return "true"
            return "(%s)" % (" and " if b == "all_of" else " or ").join(items)
        if b == "not_cond":
            return "not (%s)" % self.cond(one(node, "item"))
        raise CompileError("条件积木 %r 还不能翻译" % b)

    # ------------------------------------------------------------ 处理（语句）
    def uses_of(self, kind, name, stmts):
        """「记作 A」/「对象 T」之后第一个用到它的动作（选卡时就只给能这样处理的卡）。"""
        for st in walk(stmts):
            if st["block"] in ACTS and (one(st, "cards") or {}).get("block") == kind and \
                    one(st, "cards").get("name") == name:
                return st["block"]
        return None

    def statements(self, stmts):
        out, last = [], None          # last：前一步「做成了」的表达式（「那之后」用）
        for i, st in enumerate(stmts):
            lines, ok = self.statement(st, stmts[i + 1:], last)
            out += lines
            last = ok
        return out

    def reset(self, value, card=True):
        base = "RESET_EVENT+RESETS_STANDARD" if card else ""
        extra = {"permanent": "", "end_of_turn": "RESET_PHASE+PHASE_END", "end_of_next_turn": "RESET_PHASE+PHASE_END",
                 "next_standby": "RESET_PHASE+PHASE_STANDBY+RESET_SELF_TURN",
                 "opp_turn_end": "RESET_PHASE+PHASE_END"}[value]
        text = "+".join(x for x in (base, extra) if x)
        count = {"end_of_next_turn": ",2", "next_standby": ",Duel.GetTurnPlayer()==tp and 2 or 1",
                 "opp_turn_end": ",Duel.GetTurnPlayer()==tp and 2 or 1"}.get(value, "")
        return text + count if text else None

    def value_fn(self, code, filters):
        """「数值：只对这样的卡成立」→ SetValue 的函数（不会被魔法卡的效果破坏、不受陷阱卡影响、只能装备给……）。"""
        activated = any(x["block"] == "f_activated_effect" for x in filters)
        f = self.filter_fn({"filter": [x for x in filters if x["block"] != "f_activated_effect"]})
        if code in VALUE_BY_EFFECT:
            return self.fn("valte", "function %%s(e,te)\n\treturn %s%s(te:GetHandler(),e,e:GetHandlerPlayer())\nend" % (
                "te:IsActivated() and " if activated else "", f))
        return self.fn("valc", "function %%s(e,c)\n\treturn %s(c,e,e:GetHandlerPlayer())\nend" % f)

    def statement(self, st, rest, last):
        b = st["block"]
        if b == "place":
            return self.place(st)
        if b == "attach":
            return self.attach(st)
        if b == "delay":
            return self.delay(st), None
        if b == "fail":
            if last is None:
                raise CompileError("「做不到的场合」前面要有一个会「做成 / 做不成」的动作（除外、破坏、抽卡……）")
            return ["if not (%s) then" % last] + indent(self.statements(st.get("body", []))) + ["end"], None
        if b == "announce" and st["what"] == "race_or_attr":
            # 种族记成正数、属性记成负数（两种的位会重叠）
            p = PLAYER[st["player"]]
            return ["local opt=Duel.SelectOption(%s,aux.Stringid(id,%d),aux.Stringid(id,%d))" % (
                        p, self.string("宣言种族"), self.string("宣言属性")),
                    "local decl", "if opt==0 then",
                    "\tDuel.Hint(HINT_SELECTMSG,%s,HINTMSG_RACE)" % p, "\tdecl=Duel.AnnounceRace(%s,1,RACE_ALL)" % p, "else",
                    "\tDuel.Hint(HINT_SELECTMSG,%s,HINTMSG_ATTRIBUTE)" % p, "\tdecl=-Duel.AnnounceAttribute(%s,1,ATTRIBUTE_ALL)" % p,
                    "end", "e:SetLabel(decl)"], "true"
        if b == "announce":
            p = PLAYER[st["player"]]
            hint, call = ANNOUNCE_CALL[st["what"]]
            return ["Duel.Hint(HINT_SELECTMSG,%s,%s)" % (p, hint), "local decl=%s" % (call % p), "e:SetLabel(decl)"], "true"
        if b == "toss_coin":
            if st.get("call") == "yes":
                return ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_COIN)", "local call=Duel.AnnounceCoin(tp)",
                        "local coin=Duel.TossCoin(tp,1)"], "true"
            return ["local coin=Duel.TossCoin(tp,1)"], "true"
        if b == "toss_dice":
            return ["local dice=Duel.TossDice(tp,1)"], "true"
        if b == "change_chain_target":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            g = "Group.FromCards(%s)" % var if single(var) else var
            return pre + ["if %s then Duel.ChangeTargetCard(ev,%s) end" % (guard, g)], "true"
        if b == "change_chain_effect":
            name = "s.chainop%d" % self.fresh_num()
            old = (self.no_chain, self.each)
            self.no_chain, self.each = True, []
            body = self.statements(st.get("body", []))
            self.no_chain, self.each = old
            self.add_func(NL.join(["function %s(e,tp,eg,ep,ev,re,r,rp)" % name, "\tlocal c=e:GetHandler()"] +
                                  indent(body) + ["end"]))
            return ["Duel.ChangeChainOperation(ev,%s)" % name], "true"
        if b == "keep_target":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            card = var if single(var) else "%s:GetFirst()" % var
            # 刚特殊召唤的对象已经换了位置、和效果没有关联了：只看它在不在场上（照官方写法）
            return pre + ["local kt=%s" % card,
                          "if kt and kt:IsOnField() and e:GetHandler():IsRelateToEffect(e) then e:GetHandler():SetCardTarget(kt) end"], "true"
        if b == "skip_phase":
            return ["Duel.SkipPhase(%s,PHASE_%s,RESET_PHASE+PHASE_END,1)" % (PLAYER[st["player"]], st["phase"].upper())], "true"
        if b == "to_extra_faceup":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            return pre + ["if %s then Duel.SendtoExtraP(%s,nil,REASON_EFFECT) end" % (guard, var)], "true"
        if b == "stay_on_field":
            return ["if e:GetHandler():IsRelateToEffect(e) then e:GetHandler():CancelToGrave() end"], "true"
        if b == "give_up_draw":
            return ["aux.GiveUpNormalDraw(e,tp)"], "true"
        if b == "activate_card":
            loc = {"hand_deck": "LOCATION_HAND+LOCATION_DECK", "deck": "LOCATION_DECK", "hand": "LOCATION_HAND"}[st["where"]]
            f = self.activate_filter(st)
            return ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_TOFIELD)",
                    "local ac=Duel.SelectMatchingCard(tp,%s,tp,%s,0,1,1,nil,e,tp):GetFirst()" % (f, loc),
                    "if ac then",
                    "\tlocal zone=ac:IsType(TYPE_FIELD) and LOCATION_FZONE or LOCATION_SZONE",
                    "\tif ac:IsType(TYPE_FIELD) then",
                    "\t\tlocal fc=Duel.GetFieldCard(tp,LOCATION_FZONE,0)",
                    "\t\tif fc then Duel.SendtoGrave(fc,REASON_RULE) Duel.BreakEffect() end", "\tend",
                    "\tDuel.MoveToField(ac,tp,tp,zone,POS_FACEUP,true)",
                    "\tlocal te=ac:GetActivateEffect()", "\tte:UseCountLimit(tp,1,true)",
                    "\tlocal cost=te:GetCost()", "\tif cost then cost(te,tp,eg,ep,ev,re,r,rp,1) end",
                    "\tDuel.RaiseEvent(ac,4179255,te,0,tp,tp,Duel.GetCurrentChain())", "end"], "true"
        if b == "end_battle_phase":
            return ["Duel.SkipPhase(Duel.GetTurnPlayer(),PHASE_BATTLE,RESET_PHASE+PHASE_BATTLE_STEP,1)"], "true"
        if b == "normal_summon":
            return ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SUMMON)",
                    "local sm=Duel.SelectMatchingCard(tp,%s,tp,LOCATION_HAND+LOCATION_MZONE,0,1,1,nil,e,tp):GetFirst()"
                    % self.summon_filter(st), "if sm then Duel.Summon(tp,sm,true,nil) end"], "true"
        if b == "extra_summon":
            call = {"synchro": "Duel.SynchroSummon(tp,sm,nil)", "xyz": "Duel.XyzSummon(tp,sm,nil)",
                    "link": "Duel.LinkSummon(tp,sm,nil)"}[st["method"]]
            return ["Duel.Hint(HINT_SELECTMSG,tp,HINTMSG_SPSUMMON)",
                    "local sm=Duel.SelectMatchingCard(tp,%s,tp,LOCATION_EXTRA,0,1,1,nil,e,tp):GetFirst()"
                    % self.summon_filter(st), "if sm then %s end" % call], "true"
        if b == "trap_monster":
            mt = "TYPE_NORMAL" if st.get("mtype") == "normal" else "TYPE_EFFECT"
            return ["local tm=e:GetHandler()",
                    "if tm:IsRelateToEffect(e) and Duel.GetLocationCount(tp,LOCATION_MZONE)>0 and %s then"
                    % self.trap_monster_can(st),
                    "\ttm:AddMonsterAttribute(%s+TYPE_TRAP)" % mt,
                    "\tDuel.SpecialSummon(tm,0,tp,tp,true,false,POS_FACEUP)", "end"], "true"
        if b == "copy_effects":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            card = var if single(var) else "%s:GetFirst()" % var
            reset = "RESET_EVENT+RESETS_STANDARD" + ("" if st.get("reset") == "permanent" else "+RESET_PHASE+PHASE_END")
            body = ["\tlocal code=%s:GetOriginalCodeRule()" % card]
            if st.get("name") == "yes":
                body += ["\tlocal ce=Effect.CreateEffect(cc)", "\tce:SetType(EFFECT_TYPE_SINGLE)",
                         "\tce:SetCode(EFFECT_CHANGE_CODE)", "\tce:SetValue(code)", "\tce:SetReset(%s)" % reset,
                         "\tcc:RegisterEffect(ce)"]
            body.append("\tcc:CopyEffect(code,%s,1)" % reset)
            return pre + ["local cc=e:GetHandler()",
                          "if %s and cc:IsRelateToEffect(e) and cc:IsFaceup() then" % guard] + body + ["end"], "true"
        if b == "return_to_field":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            if single(var):
                return pre + ["if %s then Duel.ReturnToField(%s) end" % (guard, var)], "true"
            return pre + ["for rf in aux.Next(%s) do Duel.ReturnToField(rf) end" % var], "true"
        if b == "sort_deck":
            return ["Duel.SortDecktop(tp,%s,%d)" % (PLAYER[st["player"]], st["count"])], "true"
        if b == "move_zone":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            card = var if single(var) else "%s:GetFirst()" % var
            return pre + ["if %s and %s:IsControler(tp) and Duel.GetLocationCount(tp,LOCATION_MZONE)>0 then" % (guard, card),
                          "\tlocal zone=Duel.SelectDisableField(tp,1,LOCATION_MZONE,0,0)",
                          "\tDuel.MoveSequence(%s,math.log(zone,2))" % card, "end"], "true"
        if b == "change_attack_target":
            target = one(st, "cards")
            if target is None:
                return ["Duel.ChangeAttackTarget(nil)"], "true"
            pre, var, guard = self.cards_expr(target)
            card = var if single(var) else "%s:GetFirst()" % var
            return pre + ["if %s then Duel.ChangeAttackTarget(%s) end" % (guard, card)], "true"
        if b == "calc_damage":
            pre1, a, ga = self.cards_expr(one(st, "a"))
            pre2, d, gd = self.cards_expr(one(st, "b"))
            a = a if single(a) else "%s:GetFirst()" % a
            d = d if single(d) else "%s:GetFirst()" % d
            return pre1 + pre2 + ["if %s and %s then Duel.CalculateDamage(%s,%s) end" % (ga, gd, a, d)], "true"
        if b == "chain_attack":
            return ["Duel.ChainAttack()"], "true"
        if b == "confirm_top":
            return ["Duel.ConfirmDecktop(%s,%d)" % (PLAYER[st["player"]], st["count"])], "true"
        if b == "shuffle":
            return ["Duel.ShuffleDeck(%s)" % PLAYER[st["player"]]], "true"
        if b == "set_flag":
            reset = FLAG_RESET[(st["on"], st["reset"])]
            if st["on"] == "card":
                return ["e:GetHandler():RegisterFlagEffect(id+%d,%s,0,1)" % (st["name"], reset)], None
            return ["Duel.RegisterFlagEffect(tp,id+%d,%s,0,1)" % (st["name"], reset)], None
        if b == "fusion_summon":
            return [self.fusion_call(st, "Operation")], "true"
        if b == "ritual_summon":
            return [self.ritual_call(st, "Operation")], "true"
        if b in ACTS and b != "reveal":
            call, _, hint, _ = ACTS[b][:4]
            ability = self.ability(st)
            if b == "change_position":
                call = "Duel.ChangePosition(%%s,%s)" % TO_POS[st["to"]]
            if b == "special_summon":
                call = self.ss_parts(st)[0]
            if b in ("banish", "to_deck", "to_hand"):
                call = self.call_of(st)
            pre, var, guard = self.cards_expr(one(st, "cards"), ability, hint)
            r = self.fresh("r")
            src = one(st, "cards") or {}
            if b == "special_summon" and (src.get("block") == "all" or (src.get("block") == "pick" and self.span(src)[1] != "1")):
                guard = "%s and not (#%s>1 and Duel.IsPlayerAffectedByEffect(tp,59822133))" % (guard, var)
            lines = pre + ["local %s=0" % r, "if %s then" % guard, "\t%s=%s" % (r, call % var)]
            if b == "to_hand" and src.get("block") in ("var", "all", "pick") and \
                    ("deck" in src.get("where", "deck") or "grave" in src.get("where", "deck")):
                lines.append("\tif %s>0 then Duel.ConfirmCards(1-tp,%s) end" % (r, var))
            if b == "special_summon" and st.get("position") == "facedown":
                lines.append("\tif %s>0 then Duel.ConfirmCards(1-tp,%s) end" % (r, var))
            return lines + ["end"], "%s>0" % r
        if b in ("draw", "damage", "recover"):
            r = self.fresh("r")
            p = PLAYER[st["player"]]
            if b == "draw":
                return ["local %s=Duel.Draw(%s,%s,REASON_EFFECT)" % (r, p, self.count_of(st))], "%s>0" % r
            fn = "Damage" if b == "damage" else "Recover"
            return ["local %s=Duel.%s(%s,%s,REASON_EFFECT)" % (r, fn, p, self.number(one(st, "amount")))], "%s>0" % r
        if b == "pay_lp":
            return ["Duel.PayLPCost(tp,%s)" % self.number(one(st, "amount"))], "true"
        if b == "detach":
            r = self.fresh("r")
            n = self.count_of(st)
            if one(st, "cards") is None and st.get("all") != "yes":
                return ["local %s=c:RemoveOverlayCard(tp,%s,%s,REASON_EFFECT)" % (r, n, n)], "%s>0" % r
            pre, var, guard = self.cards_expr(one(st, "cards")) if one(st, "cards") else ([], "c", "true")
            each = "xc" if not single(var) else var
            if st.get("all") == "yes":         # 超量素材全部取除
                body = ["local og=%s:GetOverlayGroup()" % each, "%s=%s+Duel.SendtoGrave(og,REASON_EFFECT)" % (r, r)]
            else:
                body = ["%s=%s+%s:RemoveOverlayCard(tp,%s,%s,REASON_EFFECT)" % (r, r, each, n, n)]
            if single(var):
                return pre + ["local %s=0" % r, "if %s then" % guard] + indent(body) + ["end"], "%s>0" % r
            return pre + ["local %s=0" % r, "for xc in aux.Next(%s) do" % var] + indent(body) + ["end"], "%s>0" % r
        if b == "add_counter":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            add = "%%s:AddCounter(%s,%s)" % (st["counter"], self.count_of(st))
            if single(var):
                return pre + ["if %s then %s end" % (guard, add % var)], "true"
            return pre + ["for ac in aux.Next(%s) do %s end" % (var, add % "ac")], "true"
        if b == "remove_counter":
            if st.get("from") == "field":
                return ["Duel.RemoveCounter(tp,1,1,%s,%s,REASON_EFFECT)" % (st["counter"], self.count_of(st))], "true"
            return ["c:RemoveCounter(tp,%s,%s,REASON_EFFECT)" % (st["counter"], self.count_of(st))], "true"
        if b == "create_token":
            return self.create_token(st)
        if b == "equip":
            return self.equip(st)
        if b == "set_lp":
            return ["Duel.SetLP(%s,%s)" % (PLAYER[st["player"]], self.number(one(st, "amount")))], "true"
        if b == "reveal":
            pre, var, guard = self.cards_expr(one(st, "cards"))
            return pre + ["if %s then Duel.ConfirmCards(1-tp,%s) end" % (guard, var)], "true"
        if b == "negate_summon":
            return ["Duel.NegateSummon(eg)"], "true"
        if b == "each_player":
            # 双方各自：tp 换成正在做的那一方，里面的「自己」「对方」都跟着换
            body = self.statements(st.get("body", []))
            return ["for _,p in ipairs({tp,1-tp}) do", "\tlocal tp=p"] + indent(body) + ["end"], None
        if b == "negate_activation":
            return [], "Duel.NegateActivation(ev)"
        if b == "negate_effect":
            return [], "Duel.NegateEffect(ev)"
        if b == "negate_attack":
            return ["Duel.NegateAttack()"], "true"
        if b == "win":
            return ["Duel.Win(%s,0x11)" % PLAYER[st["player"]]], None
        if b == "raw":
            self.guard(st.get("lua"), "自定义 Lua")
            return [l for l in str(st.get("lua", "")).split("\n") if l.strip()], None
        if b == "register":
            return self.register(st), "true"
        if b in ("register_player", "register_zone"):
            return self.register_field(st), "true"
        if b == "select":
            src = one(st, "source")
            if not src or src["block"] not in ("all", "pick"):
                raise CompileError("「让玩家选卡」要从「全部……的卡」里选")
            purpose = self.uses_of("var", st["as"], rest)
            ability = ACTS[purpose][3] if purpose else None
            hint = ACTS[purpose][2] if purpose else "HINTMSG_SELECT"
            f = self.filter_fn(src, ability)
            s_, o_ = self.sides(src)
            v = "v%s" % st["as"]
            lo, hi, need = self.span(st)
            p = PLAYER[st["player"]]
            # 卡片条件里「和那只怪兽相同等级」要用到；登记到之后的效果里还会用，卡片组要留住
            keep = "s.v_%s=%s %s:KeepAlive()" % (st["as"], v, v)
            if st.get("sum") == "level_eq":          # 等级合计正好是……
                n = self.number(one(st, "sum_n")) if one(st, "sum_n") else str(st["count"])
                return ["local %sa=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (v, f, s_, o_),
                        "Duel.Hint(HINT_SELECTMSG,%s,%s)" % (p, hint),
                        "local %s=%sa:SelectWithSumEqual(%s,Card.GetLevel,%s,1,99) or Group.CreateGroup()" % (v, v, p, n),
                        keep], "#%s>0" % v
            if st.get("different") == "yes" and (need > 1 or one(st, "count_n") is not None):   # 卡名各不相同
                return ["local %sa=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (v, f, s_, o_),
                        "Duel.Hint(HINT_SELECTMSG,%s,%s)" % (p, hint),
                        "local %s=%sa:SelectSubGroup(%s,aux.dncheck,false,%s,%s) or Group.CreateGroup()" % (
                            v, v, p, lo, hi), keep], "#%s>0" % v
            return ["Duel.Hint(HINT_SELECTMSG,%s,%s)" % (p, hint),
                    "local %s=Duel.SelectMatchingCard(%s,%s,tp,%s,%s,%s,%s,nil,e,tp)" % (v, p, f, s_, o_, lo, hi), keep], \
                "#%s>0" % v
        if b == "if":
            lines = ["if %s then" % self.cond(one(st, "cond"))] + indent(self.statements(st.get("then", [])))
            if st.get("else"):
                lines += ["else"] + indent(self.statements(st["else"]))
            return lines + ["end"], None
        if b == "after":
            if last is None:
                raise CompileError("「那之后」前面要有一个能「做成」的动作（破坏、加入手卡、抽卡……）")
            brk = ["\tDuel.BreakEffect()"] if st.get("how", "then") == "then" else []
            return ["if %s then" % last] + brk + indent(self.statements(st.get("body", []))) + ["end"], None
        if b == "may":
            ask = "Duel.SelectYesNo(tp,aux.Stringid(id,%d))" % self.string(st.get("ask") or "是否继续处理？")
            return ["if %s then" % ask] + indent(self.statements(st.get("body", []))) + ["end"], None
        if b == "for_each":
            pre, var, _ = self.cards_expr(one(st, "cards"))
            ec = self.fresh("ec")
            self.each.append(ec)
            body = self.statements(st.get("body", []))
            self.each.pop()
            if single(var):
                return pre + ["local %s=%s" % (ec, var), "if %s then" % ec] + indent(body) + ["end"], None
            return pre + ["for %s in aux.Next(%s) do" % (ec, var)] + indent(body) + ["end"], None
        if b == "choose":
            return self.choose(st), None
        raise CompileError("积木「%s」不能放在处理里" % BLOCKS[b].label)

    def create_token(self, st):
        """特殊召唤 DIY 衍生物：卡号＝这张卡＋编号（写法同 v0.2 的衍生物）。"""
        from .compile_tables import ATTRIBUTE_CONST, RACE_CONST
        code = "id+%d" % self.token_no[id(st)]
        n = self.count_of(st)
        many = one(st, "count_n") is not None or st["count"] > 1
        pos = {"defense": "POS_FACEUP_DEFENSE", "attack": "POS_FACEUP_ATTACK"}[st["position"]]
        check = "Duel.GetLocationCount(tp,LOCATION_MZONE)>=%s and Duel.IsPlayerCanSpecialSummonMonster(tp,%s,0,TYPES_TOKEN_MONSTER,%d,%d,%d,%s,%s,%s)" % (
            n, code, st["atk"], st["def"], st["level"], RACE_CONST[st["race"]], ATTRIBUTE_CONST[st["attribute"]], pos)
        if many:
            check = "not Duel.IsPlayerAffectedByEffect(tp,59822133) and " + check
        r = self.fresh("r")
        return ["local %s=0" % r, "if %s then" % check,
                "\tfor i=1,%s do" % n, "\t\tlocal token=Duel.CreateToken(tp,%s)" % code,
                "\t\tif Duel.SpecialSummonStep(token,0,tp,tp,false,false,%s) then %s=%s+1 end" % (pos, r, r),
                "\tend", "\tDuel.SpecialSummonComplete()", "end"], "%s>0" % r

    def delay(self, st):
        """之后再处理：登记一个到时候才处理、不入连锁的效果（EFFECT_TYPE_FIELD+CONTINUOUS，1次，到期重置）。
        带上前一步处理的卡：给那些卡做标记（标签是这次处理的编号），到时候只处理标记还对得上的（还在原处的）。"""
        code, reset, later = DELAY[st["when"]]
        carry = st.get("carry") == "yes"
        name = "s.delay%d" % self.fresh_num()
        v = self.fresh("de")
        lines = []
        if carry:
            lines += ["local kg=Duel.GetOperatedGroup():Clone()", "local fid=c:GetFieldID()",
                      "for kc in aux.Next(kg) do kc:RegisterFlagEffect(id+%d,RESET_EVENT+RESETS_STANDARD,0,1,fid) end"
                      % CARRY_FLAG, "kg:KeepAlive()"]
        lines += ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)" % v,
                  "%s:SetCode(%s)" % (v, code), "%s:SetCountLimit(1)" % v, "%s:SetReset(%s)" % (v, reset),
                  "%s:SetLabel(Duel.GetTurnCount()%s)" % (v, ",fid" if carry else "")]
        if carry:
            lines.append("%s:SetLabelObject(kg)" % v)
        if later:      # 下次的……：这个回合不算
            cond = "Duel.GetTurnCount()~=e:GetLabel()"
            if st["when"] == "next_standby":
                cond += " and Duel.GetTurnPlayer()==tp"
            lines.append("%s:SetCondition(%s)" % (v, self.fn("delaycon", "function %%s(e,tp)\n\treturn %s\nend" % cond)))
        lines += ["%s:SetOperation(%s)" % (v, name), "Duel.RegisterEffect(%s,tp)" % v]
        old = (self.in_delay, self.no_chain, self.each)
        self.in_delay, self.no_chain, self.each = ("carry" if carry else "plain"), True, []
        body = self.statements(st.get("body", []))
        self.in_delay, self.no_chain, self.each = old
        head = ["local c=e:GetHandler()", "Duel.Hint(HINT_CARD,0,id)"]
        if carry:
            head += ["local _,fid=e:GetLabel()",
                     "local cg=e:GetLabelObject():Filter(function(kc) return kc:GetFlagEffectLabel(id+%d)==fid end,nil)"
                     % CARRY_FLAG]
        self.add_func("function %s(e,tp,eg,ep,ev,re,r,rp)\n%s\nend" % (name, "\n".join(indent(head + body))))
        return lines

    def fresh_num(self):
        self.n += 1
        return self.n

    def attach(self, st):
        """作为超量素材：Duel.Overlay（场上的卡原本带的超量素材按规则送去墓地）。"""
        pre1, var1, g1 = self.cards_expr(one(st, "cards"), self.ability(st), "HINTMSG_XMATERIAL")
        pre2, var2, g2 = self.cards_expr(one(st, "to"))
        lines = pre1 + pre2
        if not single(var2):
            lines.append("local xyz=%s:GetFirst()" % var2)
            var2, g2 = "xyz", "xyz"
        body = []
        if single(var1):
            body += ["local og=%s:GetOverlayGroup()" % var1, "if #og>0 then Duel.SendtoGrave(og,REASON_RULE) end"]
        else:
            body += ["for mc in aux.Next(%s) do" % var1,
                     "\tlocal og=mc:GetOverlayGroup()", "\tif #og>0 then Duel.SendtoGrave(og,REASON_RULE) end", "end"]
        body.append("Duel.Overlay(%s,%s)" % (var2, var1))
        return lines + ["if %s and %s and %s:IsType(TYPE_XYZ) and not %s:IsImmuneToEffect(e) then" % (g1, g2, var2, var2)] + \
            indent(body) + ["end"], "true"

    def place(self, st):
        """放置到场上：Duel.MoveToField（表侧表示，放进魔法与陷阱区域 / 场地区域 / 灵摆区域）。"""
        where = st.get("where") or "szone"
        pre, var, guard = self.cards_expr(one(st, "cards"), self.ability(st), "HINTMSG_TOFIELD")
        free = PLACE_FREE[where]
        move = "Duel.MoveToField(%%s,tp,tp,%s,POS_FACEUP,true)" % LOC[where]
        r = self.fresh("r")
        if single(var):
            check = guard + (" and " + free if free else "")
            return pre + ["local %s=0" % r, "if %s and %s then %s=1 end" % (check, move % var, r)], "%s>0" % r
        return pre + ["local %s=0" % r, "for pc in aux.Next(%s) do" % var,
                      "\tif %s%s then %s=%s+1 end" % (free + " and " if free else "", move % "pc", r, r),
                      "end"], "%s>0" % r

    def equip(self, st):
        """装备：Duel.Equip。装备魔法卡把自己装备（装备限制在 initial_effect 里写好）；别的卡加上「只能装备给这只」。"""
        what, to = one(st, "cards"), one(st, "to")
        pre1, var1, g1 = self.cards_expr(what)
        pre2, var2, g2 = self.cards_expr(to)
        lines = pre1 + pre2
        if not single(var1):
            lines.append("local eqc=%s:GetFirst()" % var1)
            var1, g1 = "eqc", "eqc"
        if not single(var2):
            lines.append("local eqt=%s:GetFirst()" % var2)
            var2, g2 = "eqt", "eqt"
        self_spell = (what or {}).get("block") == "this_card" and self.is_equip_spell()
        r = self.fresh("r")
        check = "%s and %s and %s:IsFaceup()" % (g1, g2, var2)
        if not self_spell:
            check += " and Duel.GetLocationCount(tp,LOCATION_SZONE)>0"
        lines += ["local %s=false" % r, "if %s then" % check, "\t%s=Duel.Equip(tp,%s,%s)" % (r, var1, var2)]
        if not self_spell:
            v = self.fresh("el")
            lines += ["\tif %s then" % r] + indent(
                ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                 "%s:SetCode(EFFECT_EQUIP_LIMIT)" % v, "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)" % v,
                 "%s:SetReset(RESET_EVENT+RESETS_STANDARD)" % v, "%s:SetLabelObject(%s)" % (v, var2),
                 "%s:SetValue(%s)" % (v, self.lib("s.eqlimit")), "%s:RegisterEffect(%s)" % (var1, v)], 2) + ["\tend"]
        return lines + ["end"], r

    def is_equip_spell(self):
        info = self.card.get("card") or {}
        return info.get("kind") == "spell" and "equip" in (info.get("subtypes") or [])

    def choose(self, st):
        """●选项：能选的选项列出来让玩家选一个，按选的做（Duel.SelectOption）。"""
        p = PLAYER[st["player"]]
        ops = st.get("options", [])
        if not ops:
            raise CompileError("「让玩家选一项」里还没有选项")
        lines = ["local ops,opv={},{}"]
        for i, op in enumerate(ops):
            add = "ops[#ops+1]=aux.Stringid(id,%d) opv[#opv+1]=%d" % (self.string(op.get("text") or "选项%d" % (i + 1)), i + 1)
            c = one(op, "cond")
            lines.append("if %s then %s end" % (self.cond(c), add) if c else add)
        lines += ["if #ops>0 then", "\tlocal sel=opv[Duel.SelectOption(%s,table.unpack(ops))+1]" % p]
        for i, op in enumerate(ops):
            lines.append("\t%s sel==%d then" % ("if" if i == 0 else "elseif", i + 1))
            lines += indent(self.statements(op.get("body", [])), 2)
        return lines + ["\tend", "end"]

    def register(self, st):
        """给卡片登记效果：单体效果 + 引擎的效果代码（259 种都能选）。"""
        value = one(st, "value")
        reset = self.reset(st["reset"])

        def lines(card):
            v = self.fresh("re")
            out = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                   "%s:SetCode(%s)" % (v, st["code"])]
            if st["code"] == "EFFECT_INDESTRUCTABLE_COUNT":
                out.append("%s:SetCountLimit(1)" % v)
            special = self.value_fn(st["code"], st["value_cards"]) if st.get("value_cards") else \
                self.special_value(st["code"], st.get("against"))
            if special:
                out.append("%s:SetValue(%s)" % (v, special))
            elif value is not None:
                out.append("%s:SetValue(%s)" % (v, self.number(value)))
            elif st["code"] in VALUE_ONE:
                out.append("%s:SetValue(1)" % v)
            return out + ["%s:SetReset(%s)" % (v, reset), "%s:RegisterEffect(%s)" % (card, v)]
        pre, var, guard = self.cards_expr(one(st, "cards"), "c:IsFaceup()")
        if single(var):
            card = var
            if var == "re:GetHandler()":
                pre, card = pre + ["local rc=re:GetHandler()"], "rc"
            return pre + ["if %s and %s:IsFaceup() then" % (guard, card)] + indent(lines(card)) + ["end"]
        return pre + ["for rc in aux.Next(%s) do" % var] + indent(["if rc:IsFaceup() then"] + indent(lines("rc")) + ["end"]) + \
            ["end"]

    def field_target(self, st, code):
        """「只针对这样的卡」→ SetTarget / （不能发动时）SetValue 用的函数；没有条件返回 (None, None)。"""
        filters = st.get("filter") or []
        if not filters:
            return None, None
        f = self.filter_fn({"filter": filters})
        if code == "EFFECT_CANNOT_ACTIVATE":                # 「不能把……的效果发动」：按发动的那张卡判断
            return None, self.fn("aclimit", "function %%s(e,re,tp)\n\treturn %s(re:GetHandler(),e,tp)\nend" % f)
        return self.fn("fieldtg", "function %%s(e,c)\n\treturn %s(c,e,e:GetHandlerPlayer())\nend" % f), None

    def register_field(self, st):
        """让玩家 / 一片区域的卡适用效果：EFFECT_TYPE_FIELD（玩家时加 EFFECT_FLAG_PLAYER_TARGET），注册给玩家。"""
        v = self.fresh("fe")
        code = st["code"]
        out = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetCode(%s)" % (v, code)]
        if st["block"] == "register_player":
            out += ["%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % v, "%s:SetTargetRange(%s)" % (v, RANGE[st["player"]])]
        else:
            s_, o_ = self.sides(st)
            out.append("%s:SetTargetRange(%s,%s)" % (v, s_, o_))
        tg, val = self.field_target(st, code)
        if tg:
            out.append("%s:SetTarget(%s)" % (v, tg))
        value = one(st, "value")
        if st.get("value_cards"):
            val = self.value_fn(code, st["value_cards"])
        if val:
            out.append("%s:SetValue(%s)" % (v, val))
        elif value is not None:
            out.append("%s:SetValue(%s)" % (v, self.number(value)))
        elif code == "EFFECT_CANNOT_ACTIVATE" or code in VALUE_ONE:
            out.append("%s:SetValue(1)" % v)
        reset = self.reset(st["reset"], card=False)
        if reset:
            out.append("%s:SetReset(%s)" % (v, reset))
        return out + ["Duel.RegisterEffect(%s,tp)" % v]

    # ------------------------------------------------------------ 代价
    def cost_fn(self, stmts):
        checks, body = self.cost_parts(stmts)
        name = "s.cost%d" % self.k
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,chk)" % name,
                                 "\tif chk==0 then return %s end" % " and ".join(checks)] + indent(body) + ["end"]))
        return name

    def cost_parts(self, stmts):
        """代价 → (能不能支付的检查, 支付的语句)；召唤手续的代价也用。"""
        checks, body = [], []
        for st in stmts:
            b = st["block"]
            if b not in COST_ACTS:
                raise CompileError("「%s」不能当代价" % BLOCKS[b].label)
            if b == "pay_lp":
                n = self.number(one(st, "amount"))
                checks.append("Duel.CheckLPCost(tp,%s)" % n)
                body.append("Duel.PayLPCost(tp,%s)" % n)
                continue
            if b == "detach":
                n = self.count_of(st)
                checks.append("e:GetHandler():CheckRemoveOverlayCard(tp,%s,REASON_COST)" % n)
                body.append("e:GetHandler():RemoveOverlayCard(tp,%s,%s,REASON_COST)" % (n, n))
                continue
            if b == "remove_counter" and st.get("from") == "field":
                n = self.count_of(st)
                checks.append("Duel.IsCanRemoveCounter(tp,1,1,%s,%s,REASON_COST)" % (st["counter"], n))
                body.append("Duel.RemoveCounter(tp,1,1,%s,%s,REASON_COST)" % (st["counter"], n))
                continue
            if b == "remove_counter":
                n = self.count_of(st)
                checks.append("e:GetHandler():IsCanRemoveCounter(tp,%s,%s,REASON_COST)" % (st["counter"], n))
                body.append("e:GetHandler():RemoveCounter(tp,%s,%s,REASON_COST)" % (st["counter"], n))
                continue
            src = one(st, "cards")
            _, _, hint, _, able, call = ACTS[b]
            if b in ("banish", "to_deck"):
                call = self.call_of(st, cost=True)
                if b == "banish" and st.get("face") == "down":
                    able = "c:IsAbleToRemoveAsCost(POS_FACEDOWN)"
            if src is None:
                raise CompileError("代价「%s」还没放「哪些卡」" % BLOCKS[b].label)
            if src["block"] == "this_card":
                checks.append(able.replace("c:", "e:GetHandler():"))
                body.append(call % "e:GetHandler()")
                if self.uses_cost_cards:
                    body += ["local kc=Group.FromCards(e:GetHandler())", "kc:KeepAlive()", "e:SetLabelObject(kc)"]
            elif src["block"] == "pick":
                f = self.filter_fn(src, able)
                s_, o_ = self.sides(src)
                lo, hi, need = self.span(src)
                g = self.fresh("cg")
                checks.append("Duel.IsExistingMatchingCard(%s,tp,%s,%s,%s,e:GetHandler(),e,tp)" % (
                    f, s_, o_, need if one(src, "count_n") is None else lo))
                body += ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % hint,
                         "local %s=Duel.SelectMatchingCard(tp,%s,tp,%s,%s,%s,%s,e:GetHandler(),e,tp)" % (g, f, s_, o_, lo, hi),
                         call % g]
                if self.uses_cost_cards:          # 处理里要用「作为代价的卡」
                    body += ["%s:KeepAlive()" % g, "e:SetLabelObject(%s)" % g]
                if b == "reveal" and src["where"] == "hand":
                    body.append("Duel.ShuffleHand(tp)")
            else:
                raise CompileError("代价里的卡只能是「这张卡」或「选几张」")
        return checks, body

    # ------------------------------------------------------------ 召唤条件与召唤手续
    def activate_filter(self, st):
        """从手卡 / 卡组发动的卡：能发动（IsActivatable）＋积木里的卡片条件。"""
        f = self.filter_fn({"filter": st.get("filter") or []}) if st.get("filter") else None
        return self.fn("actfilter", "function %%s(c,e,tp)\n\treturn c:GetActivateEffect() and "
                                    "c:GetActivateEffect():IsActivatable(tp,true,true)%s\nend" % (" and %s(c,e,tp)" % f if f else ""))

    def summon_filter(self, st):
        """效果里进行的召唤：能那样召唤的卡（＋积木里的卡片条件）。"""
        can = {"normal_summon": "c:IsSummonable(true,nil)", "synchro": "c:IsSynchroSummonable(nil)",
               "xyz": "c:IsXyzSummonable(nil)", "link": "c:IsLinkSummonable(nil)"}[
            st["method"] if st["block"] == "extra_summon" else "normal_summon"]
        f = self.filter_fn({"filter": st.get("filter") or []}) if st.get("filter") else None
        return self.fn("sumfilter", "function %%s(c,e,tp)\n\treturn %s%s\nend" % (can, " and %s(c,e,tp)" % f if f else ""))

    def target_link(self, node):
        """永续陷阱和它的对象怪兽：一方离场，另一方破坏（照活死人的呼声的写法）。"""
        self.k += 1
        v = "e%d" % self.k
        if node["link"] == "leave_destroy":
            chk = self.fn("ctcheck", "function %s(e,tp,eg,ep,ev,re,r,rp)\n\te:SetLabel(e:GetHandler():IsDisabled() and 1 or 0)\nend")
            op = self.fn("ctdes", "function %s(e,tp,eg,ep,ev,re,r,rp)\n\tif e:GetLabelObject():GetLabel()~=0 then return end\n"
                                  "\tlocal tc=e:GetHandler():GetFirstCardTarget()\n"
                                  "\tif tc and tc:IsLocation(LOCATION_MZONE) then Duel.Destroy(tc,REASON_EFFECT) end\nend")
            return ["local %sp=Effect.CreateEffect(c)" % v, "%sp:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_SINGLE)" % v,
                    "%sp:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)" % v, "%sp:SetCode(EVENT_LEAVE_FIELD_P)" % v,
                    "%sp:SetOperation(%s)" % (v, chk), "c:RegisterEffect(%sp)" % v,
                    "local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_SINGLE)" % v,
                    "%s:SetCode(EVENT_LEAVE_FIELD)" % v, "%s:SetLabelObject(%sp)" % (v, v),
                    "%s:SetOperation(%s)" % (v, op), "c:RegisterEffect(%s)" % v]
        extra = " and tc:IsReason(REASON_DESTROY)" if node["link"] == "target_destroyed" else ""
        con = self.fn("ctcon", "function %%s(e,tp,eg,ep,ev,re,r,rp)\n\tlocal tc=e:GetHandler():GetFirstCardTarget()\n"
                               "\treturn tc and eg:IsContains(tc)%s\nend" % extra)
        op = self.fn("ctselfdes", "function %s(e,tp,eg,ep,ev,re,r,rp)\n\tDuel.Destroy(e:GetHandler(),REASON_EFFECT)\nend")
        return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_FIELD)" % v,
                "%s:SetRange(%s)" % (v, LOC[node.get("range") or "szone"]), "%s:SetCode(EVENT_LEAVE_FIELD)" % v,
                "%s:SetCondition(%s)" % (v, con), "%s:SetOperation(%s)" % (v, op), "c:RegisterEffect(%s)" % v]

    def name_as(self, node):
        loc = {"": "nil", "field_grave": "LOCATION_ONFIELD+LOCATION_GRAVE",
               "hand_field_grave": "LOCATION_HAND+LOCATION_ONFIELD+LOCATION_GRAVE", "all": "0xff"}[node.get("where") or ""]
        if loc == "nil":
            return ["aux.EnableChangeCode(c,%d)" % int(node["code"])]
        return ["aux.EnableChangeCode(c,%d,%s)" % (int(node["code"]), loc)]

    def trap_monster_can(self, st):
        mt = "TYPE_NORMAL" if st.get("mtype") == "normal" else "TYPE_EFFECT"
        return "Duel.IsPlayerCanSpecialSummonMonster(tp,id,0,TYPE_MONSTER+%s+TYPE_TRAP,%d,%d,%d,RACE_%s,ATTRIBUTE_%s)" % (
            mt, st["atk"], st["def"], st["level"], RACE[st["race"]], st["attribute"].upper())

    def custom_effect(self, node):
        lua, helpers = str(node.get("lua") or ""), str(node.get("helpers") or "")
        if not lua.strip():
            raise CompileError("自定义效果还没写注册代码")
        self.guard(lua, "自定义效果")
        if helpers.strip():
            self.guard(helpers, "自定义效果的辅助函数", True)
            self.add_func(helpers.strip("\n"))
        return [line for line in lua.split("\n") if line.strip()]

    def guard(self, code, where, helpers=False):
        from .lua_guard import problems
        found = problems(code, helpers)
        if found:
            raise CompileError("%s没有通过安全检查：%s" % (where, "；".join(found)))

    def monster_trait(self, node):
        t = node["trait"]
        if t == "spirit":
            return ["aux.EnableSpiritReturn(c,EVENT_SUMMON_SUCCESS,EVENT_FLIP)"]
        if t == "gemini":
            return ["aux.EnableDualAttribute(c)"]
        f = self.filter_fn({"filter": node.get("filter") or []})
        return ["aux.EnableUnionAttribute(c,%s)" % self.fn("unionfilter", "function %%s(c)\n\treturn %s(c,nil,c:GetControler())\nend" % f)]

    def destroy_replace(self, node):
        """代替破坏：EFFECT_DESTROY_REPLACE（不入连锁）。target 里问「要不要代替」，operation 里付出代替的东西。"""
        self.k += 1
        k, v = self.k, "e%d" % self.k
        checks, body = self.cost_parts(node.get("cost") or [])
        body = [x.replace("REASON_COST", "REASON_EFFECT+REASON_REPLACE") for x in body]
        checks = [x.replace("REASON_COST", "REASON_EFFECT") for x in checks]
        tg, op = "s.reptg%d" % k, "s.repop%d" % k
        if node.get("mode") == "others":
            f = self.filter_fn({"filter": node.get("protect") or []})
            rf = self.fn("repfilter", "function %%s(c,tp)\n\treturn c:IsControler(tp) and c:IsOnField() and "
                                      "c:IsReason(REASON_BATTLE+REASON_EFFECT) and not c:IsReason(REASON_REPLACE) and %s(c,nil,tp)\nend" % f)
            test = "eg:IsExists(%s,1,nil,tp)" % rf
            lines = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)" % v,
                     "%s:SetCode(EFFECT_DESTROY_REPLACE)" % v, "%s:SetRange(%s)" % (v, LOC[node.get("range") or "mzone"]),
                     "%s:SetValue(%s)" % (v, self.fn("repval", "function %%s(e,c)\n\treturn %s(c,e:GetHandlerPlayer())\nend" % rf))]
        else:
            test = "e:GetHandler():IsReason(REASON_BATTLE+REASON_EFFECT) and not e:GetHandler():IsReason(REASON_REPLACE)"
            lines = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_CONTINUOUS+EFFECT_TYPE_SINGLE)" % v,
                     "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v, "%s:SetCode(EFFECT_DESTROY_REPLACE)" % v,
                     "%s:SetRange(%s)" % (v, LOC[node.get("range") or "mzone"])]
        if node.get("limit") == "card":
            lines.append("%s:SetCountLimit(1)" % v)
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,chk)" % tg,
                                 "\tif chk==0 then return %s end" % " and ".join([test] + checks),
                                 "\treturn Duel.SelectEffectYesNo(tp,e:GetHandler(),96)", "end"]))
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp)" % op] + indent(body or ["-- 不用付出什么"]) + ["end"]))
        return lines + ["%s:SetTarget(%s)" % (v, tg), "%s:SetOperation(%s)" % (v, op), "c:RegisterEffect(%s)" % v]

    def summon_rule(self, node):
        lines = []
        if node.get("normal") == "no":
            lines.append("c:EnableReviveLimit()")
        rule = node.get("special") or "any"
        if rule == "any":
            return lines
        lines += ["local e0=Effect.CreateEffect(c)", "e0:SetType(EFFECT_TYPE_SINGLE)",
                  "e0:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)", "e0:SetCode(EFFECT_SPSUMMON_CONDITION)"]
        value = {"fusion": "aux.fuslimit", "synchro": "aux.synlimit", "xyz": "aux.xyzlimit", "link": "aux.linklimit",
                 "ritual": "aux.ritlimit"}.get(rule)
        if rule == "own_effect":
            value = self.fn("splimit", "function %s(e,se,sp,st)\n\treturn se and se:GetHandler()==e:GetHandler()\nend")
        elif rule == "by_cards":
            f = self.filter_fn({"filter": node.get("by") or []})
            value = self.fn("splimit", "function %%s(e,se,sp,st)\n\treturn se and %s(se:GetHandler(),e,e:GetHandlerPlayer())\nend" % f)
        if value:                    # 只能用召唤手续：不设数值（用别的效果都不行）
            lines.append("e0:SetValue(%s)" % value)
        return lines + ["c:RegisterEffect(e0)"]

    def sp_proc(self, node):
        """特殊召唤手续：EFFECT_SPSUMMON_PROC（条件函数收到 (e,c)，代价在 operation 里支付）。"""
        self.k += 1
        k, v = self.k, "e%d" % self.k
        checks, body = self.cost_parts(node.get("cost") or [])
        cond = one(node, "condition")
        tests = ["Duel.GetLocationCount(tp,LOCATION_MZONE)>0"] + checks + ([self.cond(cond)] if cond else [])
        con = "s.sprcon%d" % k
        self.add_func("\n".join(["function %s(e,c)" % con, "\tif c==nil then return true end", "\tlocal tp=c:GetControler()",
                                 "\treturn %s" % " and ".join(tests), "end"]))
        props = "EFFECT_FLAG_UNCOPYABLE" + ("+EFFECT_FLAG_SPSUM_PARAM" if node.get("position") == "defense" else "")
        lines = ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_FIELD)" % v,
                 "%s:SetCode(EFFECT_SPSUMMON_PROC)" % v, "%s:SetProperty(%s)" % (v, props)]
        if node.get("position") == "defense":
            lines.append("%s:SetTargetRange(POS_FACEUP_DEFENSE,0)" % v)
        lines.append("%s:SetRange(%s)" % (v, LOC[node.get("range") or "hand"]))
        if node.get("limit") == "once":
            lines.append("%s:SetCountLimit(1,id+EFFECT_COUNT_CODE_OATH)" % v)
        lines.append("%s:SetCondition(%s)" % (v, con))
        if self.uses_by_proc:
            body.append("c:RegisterFlagEffect(id+%d,RESET_EVENT+RESETS_STANDARD-RESET_TOFIELD,0,1)" % PROC_FLAG)
        if body:
            op = "s.sprop%d" % k
            self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,c)" % op] + indent(body) + ["end"]))
            lines.append("%s:SetOperation(%s)" % (v, op))
        return lines + ["c:RegisterEffect(%s)" % v]

    def tribute_proc(self, node):
        """「可以把N只怪兽解放作召唤」「也能把对方怪兽解放」：EFFECT_SUMMON_PROC + CheckTribute / SelectTribute。"""
        self.k += 1
        k, v = self.k, "e%d" % self.k
        n = int(node["tribute"])
        mg = "nil"
        cond = one(node, "condition")
        con, op = "s.trcon%d" % k, "s.trop%d" % k
        self.add_func("\n".join(["function %s(e,c,minc)" % con, "\tif c==nil then return true end",
                                 "\tlocal tp=c:GetControler()",
                                 "\treturn minc<=%d and Duel.CheckTribute(c,%d,%d,%s)%s" % (
                                     n, n, n, mg, " and " + self.cond(cond) if cond else ""), "end"]))
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,c)" % op,
                                 "\tlocal g=Duel.SelectTribute(tp,c,%d,%d,%s)" % (n, n, mg),
                                 "\tc:SetMaterial(g)", "\tDuel.Release(g,REASON_SUMMON+REASON_MATERIAL)", "end"]))
        extra = []
        if node.get("opp") == "yes":         # 对方怪兽也能当祭品：EFFECT_ADD_EXTRA_TRIBUTE（照真龙的写法）
            extra = ["local %sx=Effect.CreateEffect(c)" % v, "%sx:SetType(EFFECT_TYPE_SINGLE)" % v,
                     "%sx:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                     "%sx:SetCode(EFFECT_ADD_EXTRA_TRIBUTE)" % v, "%sx:SetTargetRange(0,LOCATION_MZONE)" % v,
                     "%sx:SetValue(POS_FACEUP_ATTACK)" % v, "c:RegisterEffect(%sx)" % v]
        return extra + ["local %s=Effect.CreateEffect(c)" % v, "%s:SetDescription(aux.Stringid(id,%d))" % (v, self.string("解放召唤")),
                "%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                "%s:SetCode(EFFECT_SUMMON_PROC)" % v, "%s:SetCondition(%s)" % (v, con), "%s:SetOperation(%s)" % (v, op),
                "%s:SetValue(SUMMON_TYPE_ADVANCE)" % v, "c:RegisterEffect(%s)" % v]

    def extra_materials(self, node):
        """同调 / 超量 / 连接素材：卡上的素材行（写了这块，工作台素材栏的那份就不用了）。"""
        method = node.get("method") or "synchro"
        n = max(1, int(node.get("count") or 1))
        more = node.get("more") == "yes"
        self.mat_mode = "link" if method == "link" else None
        mat = self.filter_fn({"filter": node["material"]}) if node.get("material") else None
        lines = ["c:EnableReviveLimit()"]
        if method == "synchro":
            tuner = self.filter_fn({"filter": node["tuner"]}) if node.get("tuner") else "nil"
            if node.get("tuners") == "two":
                t = tuner if tuner != "nil" else "aux.Tuner(nil)"
                lines += ["local etuner=Effect.CreateEffect(c)", "etuner:SetType(EFFECT_TYPE_SINGLE)",      # 「红莲新星」要查这个效果
                          "etuner:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)",
                          "etuner:SetCode(21142671)", "c:RegisterEffect(etuner)"]
                lines.append("aux.AddSynchroMixProcedure(c,%s,%s,nil,aux.NonTuner(%s),%d,%d)" % (t, t, mat or "nil", n,
                                                                                               99 if more else n))
            else:
                lines.append("aux.AddSynchroProcedure(c,%s,aux.NonTuner(%s),%d,%d)" % (tuner, mat or "nil", n, 99 if more else n))
        elif method == "xyz":
            alter = "nil,nil"
            if node.get("alter"):
                f = self.filter_fn({"filter": node["alter"]})
                alter = "%s,aux.Stringid(id,%d)" % (
                    self.fn("alterfilter", "function %%s(c)\n\treturn c:IsFaceup() and %s(c,nil,c:GetControler())\nend" % f),
                    self.string("在怪兽上面重叠来超量召唤"))
            lines.append("aux.AddXyzProcedure(c,%s,%d,%d,%s,%d)" % (mat or "nil", int(node.get("rank") or 4), n, alter,
                                                                  99 if more else n))
        else:
            inc = ""
            if node.get("include"):
                f = self.filter_fn({"filter": node["include"]})
                inc = "," + self.fn("lcheck", "function %%s(g)\n\treturn g:IsExists(%s,1,nil)\nend" % f)
            lines.append("aux.AddLinkProcedure(c,%s,%d,%d%s)" % (mat or "nil", n, 99 if more else n, inc))
        self.mat_mode = None
        return lines

    def fusion_materials(self, node):
        """融合素材：第一种＋第二种×N（以上）。素材的条件函数只收到卡（e、tp 是 nil）。"""
        self.mat_mode = "fusion"
        try:
            lines = self.fusion_lines(node)
        finally:
            self.mat_mode = None
        contact = node.get("contact")
        if contact == "deck":
            lines.append("aux.AddContactFusionProcedure(c,aux.FilterBoolFunction(Card.IsAbleToDeckOrExtraAsCost),"
                         "LOCATION_ONFIELD,0,aux.ContactFusionSendToDeck(c))")
        elif contact == "grave":
            lines.append("aux.AddContactFusionProcedure(c,aux.FilterBoolFunction(Card.IsAbleToGraveAsCost),"
                         "LOCATION_ONFIELD,0,Duel.SendtoGrave,REASON_COST)")
        elif contact == "banish":
            lines.append("aux.AddContactFusionProcedure(c,aux.FilterBoolFunction(Card.IsAbleToRemoveAsCost),"
                         "LOCATION_ONFIELD,0,Duel.Remove,POS_FACEUP,REASON_COST)")
        return lines

    def fusion_lines(self, node):
        f2 = self.filter_fn({"filter": node.get("second") or []})
        n = max(1, int(node.get("count") or 1))
        more = node.get("more") == "yes"
        lines = ["c:EnableReviveLimit()"]
        if node.get("third") and node.get("first"):
            f1 = self.filter_fn({"filter": node["first"]})
            f3 = self.filter_fn({"filter": node["third"]})
            lines.append("aux.AddFusionProcMix(c,true,true,%s,%s,%s)" % (f1, f2, f3))
            return lines
        if not node.get("first"):
            if more:
                lines.append("aux.AddFusionProcFunRep2(c,%s,%d,127,true)" % (f2, n))
            else:
                lines.append("aux.AddFusionProcFunRep(c,%s,%d,true)" % (f2, n))
            return lines
        f1 = self.filter_fn({"filter": node["first"]})
        if n == 1 and not more:
            lines.append("aux.AddFusionProcFun2(c,%s,%s,true)" % (f1, f2))
        else:
            lines.append("aux.AddFusionProcFunFunRep(c,%s,%s,%d,%s,true)" % (f1, f2, n, "127" if more else str(n)))
        return lines

    def ns_proc(self, node):
        """不用解放召唤：EFFECT_SUMMON_PROC，条件 minc==0（不要解放）。解放数不是 0 的走 tribute_proc。"""
        if int(node.get("tribute") or 0) > 0:
            return self.tribute_proc(node)
        self.k += 1
        k, v = self.k, "e%d" % self.k
        cond = one(node, "condition")
        con = "s.ntcon%d" % k
        self.add_func("\n".join(["function %s(e,c,minc)" % con, "\tif c==nil then return true end",
                                 "\tlocal tp=c:GetControler()",
                                 "\treturn minc==0 and c:IsLevelAbove(5) and Duel.GetLocationCount(tp,LOCATION_MZONE)>0%s"
                                 % (" and " + self.cond(cond) if cond else ""), "end"]))
        return ["local %s=Effect.CreateEffect(c)" % v, "%s:SetType(EFFECT_TYPE_SINGLE)" % v,
                "%s:SetProperty(EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_UNCOPYABLE)" % v,
                "%s:SetCode(EFFECT_SUMMON_PROC)" % v, "%s:SetCondition(%s)" % (v, con)] + \
            (["%s:SetOperation(%s)" % (v, self.fn("ntop", "function %%s(e,tp,eg,ep,ev,re,r,rp,c)\n\t"
                                                      "c:RegisterFlagEffect(id+%d,RESET_EVENT+RESETS_STANDARD-RESET_TOFIELD,0,1)"
                                                      "\nend" % PROC_FLAG))] if self.uses_by_proc else []) + \
            ["c:RegisterEffect(%s)" % v]

    # ------------------------------------------------------------ 能否发动、处理预告
    def gates(self, stmts):
        """处理里最外层的动作，发动时要有卡可以处理（选卡要有卡可选、抽卡要能抽……）。"""
        out, info = [], []
        for i, st in enumerate(stmts):
            b = st["block"]
            src = one(st, "cards") if b in ACTS else None
            if b in ACTS and src and src["block"] in ("all", "pick") and \
                    not any(x["block"] in ("f_declared", "var") for x in walk(src.get("filter", []))):
                # 宣言的、前面选的卡，发动时还不知道：不查
                f = self.filter_fn(src, self.ability(st))
                s_, o_ = self.sides(src)
                need = self.span(src)[2] if src["block"] == "pick" else 1
                if src.get("different") == "yes" and need > 1:
                    out.append("Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):GetClassCount(Card.GetCode)>=%d" % (
                        f, s_, o_, need))
                else:
                    out.append("Duel.IsExistingMatchingCard(%s,tp,%s,%s,%d,nil,e,tp)" % (f, s_, o_, need))
                if b == "special_summon" and need > 1:
                    out.insert(0, NO_MULTI_SUMMON)
                if b == "place" and PLACE_FREE[st.get("where") or "szone"]:
                    out.insert(0, PLACE_FREE[st.get("where") or "szone"])
                if ACTS[b][1]:
                    if src["block"] == "all":
                        g = self.fresh("ig")
                        info += ["local %s=Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp)" % (g, f, s_, o_),
                                 "Duel.SetOperationInfo(0,%s,%s,#%s,0,0)" % (ACTS[b][1], g, g)]
                    else:
                        info.append("Duel.SetOperationInfo(0,%s,nil,%d,tp,%s)" % (ACTS[b][1], need,
                                                                                  s_ if s_ != "0" else o_))
                if b == "special_summon":
                    out.insert(0, "Duel.GetLocationCount(%s,LOCATION_MZONE)>0" % self.ss_parts(st)[2])
            elif b in ACTS and src and src["block"] == "this_card":
                if self.ability(st):
                    out.append(self.ability(st).replace("c:", "e:GetHandler():"))
                if b == "special_summon":
                    out.insert(0, "Duel.GetLocationCount(%s,LOCATION_MZONE)>0" % self.ss_parts(st)[2])
                if ACTS[b][1]:
                    info.append("Duel.SetOperationInfo(0,%s,e:GetHandler(),1,0,0)" % ACTS[b][1])
            elif b in ACTS and src and src["block"] == "target" and ACTS[b][1]:
                info.append("Duel.SetOperationInfo(0,%s,g,#g,0,0)" % ACTS[b][1])
            elif b in ACTS and src and src["block"] == "chain_card" and ACTS[b][1]:
                info += ["if re:GetHandler():IsRelateToEffect(re) then",
                         "\tDuel.SetOperationInfo(0,%s,eg,1,0,0)" % ACTS[b][1], "end"]
            elif b == "give_up_draw":
                out.append("aux.IsPlayerCanNormalDraw(tp)")
            elif b == "activate_card":
                loc = {"hand_deck": "LOCATION_HAND+LOCATION_DECK", "deck": "LOCATION_DECK", "hand": "LOCATION_HAND"}[st["where"]]
                out.append("Duel.IsExistingMatchingCard(%s,tp,%s,0,1,nil,e,tp)" % (self.activate_filter(st), loc))
            elif b == "normal_summon":
                out.append("Duel.IsExistingMatchingCard(%s,tp,LOCATION_HAND+LOCATION_MZONE,0,1,nil,e,tp)" % self.summon_filter(st))
                info.append("Duel.SetOperationInfo(0,CATEGORY_SUMMON,nil,1,0,0)")
            elif b == "extra_summon":
                out.append("Duel.IsExistingMatchingCard(%s,tp,LOCATION_EXTRA,0,1,nil,e,tp)" % self.summon_filter(st))
                info.append("Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,1,tp,LOCATION_EXTRA)")
            elif b == "trap_monster":
                out.append("Duel.GetLocationCount(tp,LOCATION_MZONE)>0 and %s" % self.trap_monster_can(st))
                info.append("Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,e:GetHandler(),1,0,0)")
            elif b == "select" and one(st, "source"):
                src = one(st, "source")
                purpose = self.uses_of("var", st["as"], stmts[i + 1:])
                f = self.filter_fn(src, ACTS[purpose][3] if purpose else None)
                s_, o_ = self.sides(src)
                need = self.span(st)[2]
                if st.get("sum") == "level_eq":
                    n = self.number(one(st, "sum_n")) if one(st, "sum_n") else str(st["count"])
                    out.append("Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):CheckWithSumEqual(Card.GetLevel,%s,1,99)" % (
                        f, s_, o_, n))
                elif st.get("different") == "yes" and need > 1:
                    out.append("Duel.GetMatchingGroup(%s,tp,%s,%s,nil,e,tp):GetClassCount(Card.GetCode)>=%d" % (
                        f, s_, o_, need))
                else:
                    out.append("Duel.IsExistingMatchingCard(%s,tp,%s,%s,%d,nil,e,tp)" % (f, s_, o_, need))
                if purpose and ACTS[purpose][1]:
                    info.append("Duel.SetOperationInfo(0,%s,nil,%d,tp,%s)" % (ACTS[purpose][1], need,
                                                                              s_ if s_ != "0" else o_))
                if purpose == "special_summon":
                    out.insert(0, "Duel.GetLocationCount(tp,LOCATION_MZONE)>0")
                    if need > 1:
                        out.insert(0, NO_MULTI_SUMMON)
            elif b == "draw":
                n = self.count_of(st)
                if one(st, "count_n") is None:       # 算出来的张数发动时不一定知道，不检查
                    out.append("Duel.IsPlayerCanDraw(%s,%s)" % (PLAYER[st["player"]], n))
                info.append("Duel.SetOperationInfo(0,CATEGORY_DRAW,nil,0,%s,%s)" % (PLAYER[st["player"]], n))
            elif b in ("toss_coin", "toss_dice"):
                info.append("Duel.SetOperationInfo(0,%s,nil,0,tp,1)" % ("CATEGORY_COIN" if b == "toss_coin" else "CATEGORY_DICE"))
            elif b in ("damage", "recover") and (one(st, "amount") or {}).get("block") == "num":
                info.append("Duel.SetOperationInfo(0,%s,nil,0,%s,%d)" % (
                    "CATEGORY_DAMAGE" if b == "damage" else "CATEGORY_RECOVER", PLAYER[st["player"]],
                    one(st, "amount")["value"]))
            elif b == "negate_activation":
                info.append("Duel.SetOperationInfo(0,CATEGORY_NEGATE,eg,1,0,0)")
            elif b == "negate_effect":
                info.append("Duel.SetOperationInfo(0,CATEGORY_DISABLE,eg,1,0,0)")
            elif b == "negate_summon":
                info.append("Duel.SetOperationInfo(0,CATEGORY_DISABLE_SUMMON,eg,#eg,0,0)")
            elif b == "confirm_top":
                out.append("Duel.GetFieldGroupCount(%s,LOCATION_DECK,0)>=%d" % (PLAYER[st["player"]], st["count"]))
            elif b == "fusion_summon":
                out.append(self.fusion_call(st, "Target", "0"))
                info.append(self.fusion_call(st, "Target", "1"))
            elif b == "ritual_summon":
                out.append(self.ritual_call(st, "Target", "0"))
                info.append(self.ritual_call(st, "Target", "1"))
            elif b == "equip":
                if (one(st, "cards") or {}).get("block") == "this_card":
                    info.append("Duel.SetOperationInfo(0,CATEGORY_EQUIP,e:GetHandler(),1,0,0)")
                if not ((one(st, "cards") or {}).get("block") == "this_card" and self.is_equip_spell()):
                    out.append("Duel.GetLocationCount(tp,LOCATION_SZONE)>0")
            elif b in ACTS and src and src["block"] == "deck_top":
                if one(src, "count_n") is None:
                    out.append("Duel.GetFieldGroupCount(%s,LOCATION_DECK,0)>=%d" % (PLAYER[src["who"]], src["count"]))
                if ACTS[b][1]:
                    info.append("Duel.SetOperationInfo(0,%s,nil,%d,%s,LOCATION_DECK)" % (ACTS[b][1], src["count"],
                                                                                     PLAYER[src["who"]]))
            elif b == "create_token":
                from .compile_tables import ATTRIBUTE_CONST, RACE_CONST
                code = "id+%d" % self.token_no[id(st)]
                pos = {"defense": "POS_FACEUP_DEFENSE", "attack": "POS_FACEUP_ATTACK"}[st["position"]]
                out += ["Duel.GetLocationCount(tp,LOCATION_MZONE)>%d" % (
                            (st["count"] - 1) if one(st, "count_n") is None else 0),
                        "Duel.IsPlayerCanSpecialSummonMonster(tp,%s,0,TYPES_TOKEN_MONSTER,%d,%d,%d,%s,%s,%s)" % (
                            code, st["atk"], st["def"], st["level"], RACE_CONST[st["race"]],
                            ATTRIBUTE_CONST[st["attribute"]], pos)]
                info += ["Duel.SetOperationInfo(0,CATEGORY_TOKEN,nil,%s,0,0)" % self.count_of(st),
                         "Duel.SetOperationInfo(0,CATEGORY_SPECIAL_SUMMON,nil,%s,0,0)" % self.count_of(st)]
        return out, info

    def categories(self, stmts):
        cats = []
        for st in walk(stmts):
            b = st["block"]
            if b in ACTS and ACTS[b][1]:
                cats.append(ACTS[b][1])
            elif b == "select":
                purpose = self.uses_of("var", st["as"], stmts)
                if purpose and ACTS[purpose][1]:
                    cats.append(ACTS[purpose][1])
                    if purpose == "to_hand" and (one(st, "source") or {}).get("where") == "deck":
                        cats.append("CATEGORY_SEARCH")
            elif b in ("draw", "damage", "recover"):
                cats.append({"draw": "CATEGORY_DRAW", "damage": "CATEGORY_DAMAGE", "recover": "CATEGORY_RECOVER"}[b])
            elif b == "negate_activation":
                cats.append("CATEGORY_NEGATE")
            elif b == "negate_effect":
                cats.append("CATEGORY_DISABLE")
            elif b == "create_token":
                cats += ["CATEGORY_TOKEN", "CATEGORY_SPECIAL_SUMMON"]
            elif b == "add_counter":
                cats.append("CATEGORY_COUNTER")
            elif b == "set_card":
                cats.append("CATEGORY_SSET")
            elif b == "toss_coin":
                cats.append("CATEGORY_COIN")
            elif b == "toss_dice":
                cats.append("CATEGORY_DICE")
            elif b == "equip":
                cats.append("CATEGORY_EQUIP")
            elif b == "negate_summon":
                cats.append("CATEGORY_DISABLE_SUMMON")
            elif b == "fusion_summon":
                cats += ["CATEGORY_SPECIAL_SUMMON", "CATEGORY_FUSION_SUMMON"]
            elif b == "ritual_summon":
                cats.append("CATEGORY_SPECIAL_SUMMON")
            if b == "change_position" and st.get("to") == "facedown":
                cats.append("CATEGORY_MSET")
            elif b in ("register", "register_zone"):
                if "ATTACK" in st["code"] and st["code"] != "EFFECT_CANNOT_ATTACK":
                    cats.append("CATEGORY_ATKCHANGE")
                if "DEFENSE" in st["code"]:
                    cats.append("CATEGORY_DEFCHANGE")
            if b == "to_hand" and (one(st, "cards") or {}).get("where") == "deck":
                cats.append("CATEGORY_SEARCH")
            if b == "send_to_gy" and ((one(st, "cards") or {}).get("where") == "deck" or
                                      (one(st, "cards") or {}).get("block") == "deck_top"):
                cats.append("CATEGORY_DECKDES")
        return list(dict.fromkeys(cats))

    # ------------------------------------------------------------ 会发动的效果
    def split_fn(self, t):
        """几组对象时，按「从哪些卡里取」把对象分回各组。"""
        src = one(t, "source")
        f = self.filter_fn(src)
        ctl = {"you": " and c:IsControler(tp)", "opp": " and c:IsControler(1-tp)", "both": ""}[src["who"]]
        return self.fn("tsplit", "function %%s(c,e,tp)\n\treturn c:IsLocation(%s)%s and %s(c,e,tp)\nend" % (
            LOC[src["where"]], ctl, f))

    def multi_target_fn(self, node, ops, forced):
        """几组对象：每组 IsExistingTarget / SelectTarget 一次，不支持 chkc（重新选对象的效果看不到）。"""
        gates, info = self.gates(ops)
        if forced:
            gates = []
        lines, picked = [], []
        for i, t in enumerate(self.targets):
            src = one(t, "source")
            if not src or src["block"] != "all":
                raise CompileError("「取对象」要从「全部……的卡」里取")
            purpose = self.uses_of("target", t["as"], ops)
            f = self.filter_fn(src, ACTS[purpose][3] if purpose else None)
            s_, o_ = self.sides(src)
            n = t["count"]
            gates.insert(i, "Duel.IsExistingTarget(%s,tp,%s,%s,%d,nil,e,tp)" % (f, s_, o_, n))
            lines += ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % (ACTS[purpose][2] if purpose else "HINTMSG_TARGET"),
                      "local g%d=Duel.SelectTarget(tp,%s,tp,%s,%s,%d,%d,nil,e,tp)" % (i + 1, f, s_, o_, n, n)]
            picked.append("g%d" % (i + 1))
        lines += ["local g=Group.CreateGroup()"] + ["g:Merge(%s)" % x for x in picked]
        name = "s.target%d" % self.k
        body = ["if chkc then return false end",
                "if chk==0 then return %s end" % (" and ".join(dict.fromkeys(gates)) or "true")]
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,chk,chkc)" % name] +
                                indent(body + lines + info + self.chain_limit(node)) + ["end"]))
        return name

    def chain_limit(self, node):
        """对方 / 双方不能对应这个效果的发动：发动时 Duel.SetChainLimit。（「最多2次」的使用次数也在发动时记）"""
        out = []
        if node.get("limit") == "card" and one(node, "twice_when") and getattr(self, "twice_flag", None):
            out.append("e:GetHandler():RegisterFlagEffect(%s,RESET_EVENT+RESETS_STANDARD+RESET_PHASE+PHASE_END,0,1)"
                       % self.twice_flag)
        return out + self.chain_limit_only(node)

    def chain_limit_only(self, node):
        how = node.get("chain_limit")
        if how == "opp":
            return ["Duel.SetChainLimit(%s)" % self.lib("s.chlimit")]
        if how == "all":
            return ["Duel.SetChainLimit(aux.FALSE)"]
        if how == "opp_end":
            return ["Duel.SetChainLimitTillChainEnd(%s)" % self.lib("s.chlimit")]
        return []

    def target_fn(self, node, ops, forced):
        if len(self.targets) > 1:
            return self.multi_target_fn(node, ops, forced)
        t = one(node, "target")
        gates, info = self.gates(ops)
        if forced:
            gates = []                    # 必须发动的效果：不管能不能处理都要发动
        lines, chkc = [], None
        if t is not None:
            src = one(t, "source")
            if not src or src["block"] != "all":
                raise CompileError("「取对象」要从「全部……的卡」里取")
            purpose = self.uses_of("target", t["as"], ops)
            f = self.filter_fn(src, ACTS[purpose][3] if purpose else None)
            s_, o_ = self.sides(src)
            n = t["count"]
            if n == 1:
                ctl = {"you": "chkc:IsControler(tp) and ", "opp": "chkc:IsControler(1-tp) and ", "both": ""}[src["who"]]
                chkc = "chkc:IsLocation(%s) and %s%s(chkc,e,tp)" % (LOC[src["where"]], ctl,
                                                                    f if f != "aux.TRUE" else "aux.TRUE")
            gates.insert(0, "Duel.IsExistingTarget(%s,tp,%s,%s,%d,nil,e,tp)" % (f, s_, o_, n))
            hint = ACTS[purpose][2] if purpose else "HINTMSG_TARGET"
            lines += ["Duel.Hint(HINT_SELECTMSG,tp,%s)" % hint,
                      "local g=Duel.SelectTarget(tp,%s,tp,%s,%s,%d,%d,nil,e,tp)" % (f, s_, o_, n, n)]
        name = "s.target%d" % self.k
        body = []
        if chkc:
            body.append("if chkc then return %s end" % chkc)
        body.append("if chk==0 then return %s end" % (" and ".join(dict.fromkeys(gates)) or "true"))
        self.add_func("\n".join(["function %s(e,tp,eg,ep,ev,re,r,rp,chk%s)" % (name, ",chkc" if t else "")] +
                                indent(body + lines + info + self.chain_limit(node)) + ["end"]))
        return name

    def event_type(self, t, ev):
        """效果类型 + 时机 → (SetType, SetCode, 要不要 SetRange)。"""
        if t == "activate":
            if ev in SELF_EVENTS:
                raise CompileError("魔法·陷阱卡的发动不能用「这张卡……」的时机")
            return "EFFECT_TYPE_ACTIVATE", EVENT_CODE.get(ev, "EVENT_FREE_CHAIN"), False
        if t == "ignition":
            return "EFFECT_TYPE_IGNITION", None, True
        if t in ("trigger_o", "trigger_f", "listener"):
            if ev == "free":
                raise CompileError("诱发效果要选一个时机" if t != "listener" else "「每次……」要选一个时机")
            single = ev in SELF_EVENTS
            kind = "TRIGGER_%s" % t[-1].upper() if t != "listener" else "CONTINUOUS"
            return "EFFECT_TYPE_%s+EFFECT_TYPE_%s" % ("SINGLE" if single else "FIELD", kind), EVENT_CODE[ev], not single
        if t == "flip":
            return "EFFECT_TYPE_SINGLE+EFFECT_TYPE_FLIP", None, False
        if t == "quick_f":
            return "EFFECT_TYPE_QUICK_F", EVENT_CODE.get(ev, "EVENT_FREE_CHAIN"), True
        return "EFFECT_TYPE_QUICK_O", EVENT_CODE.get(ev, "EVENT_FREE_CHAIN"), True

    def effect_head(self, v, node, ev, k, ops, suffix=""):
        """一个时机的效果「头」：类型、时机、属性、位置、次数、发动条件。两个时机的效果各有一个头，共用代价、对象、处理。"""
        t = node["type"]
        etype, code, ranged = self.event_type(t, ev)
        lines = ["%s:SetType(%s)" % (v, etype)]
        if code:
            lines.append("%s:SetCode(%s)" % (v, code))
        props = []
        if self.target is not None:
            props.append("EFFECT_FLAG_CARD_TARGET")
        if any(b["block"] == "equip" and (one(b, "cards") or {}).get("block") == "this_card" for b in walk(ops)) \
                and self.target is not None and t == "activate":
            props.append("EFFECT_FLAG_CONTINUOUS_TARGET")      # 装备魔法卡：对象就是装备怪兽
        if t.startswith("trigger") and ev in DELAY_EVENTS:
            props.append("EFFECT_FLAG_DELAY")
        if node.get("damage_step") == "yes":
            props.append("EFFECT_FLAG_DAMAGE_STEP")
        elif node.get("damage_step") == "calc":
            props.append("EFFECT_FLAG_DAMAGE_STEP+EFFECT_FLAG_DAMAGE_CAL")
        if node.get("unstoppable") == "yes":
            props.append("EFFECT_FLAG_CANNOT_INACTIVATE+EFFECT_FLAG_CANNOT_DISABLE+EFFECT_FLAG_CAN_FORBIDDEN")
        if props:
            lines.append("%s:SetProperty(%s)" % (v, "+".join(props)))
        if t == "quick_o" and ev == "free" or t == "activate" and ev == "free" and \
                (self.card.get("card") or {}).get("kind") == "trap":
            lines.append("%s:SetHintTiming(0,TIMINGS_CHECK_MONSTER+TIMING_END_PHASE)" % v)
        if ranged:
            rng = "pzone" if node.get("part") == "pendulum" else node.get("range", "mzone")
            lines.append("%s:SetRange(%s)" % (v, LOC[rng]))
        limit = node.get("limit")
        times = max(1, int(node.get("limit_n") or 1))
        mark = len(lines)
        twice = one(node, "twice_when") if limit == "card" else None
        if twice:                       # 「……的场合，1回合可以使用最多2次」：照官方，用标记数次数
            self.twice_flag = "id+%d" % (TWICE_FLAG + k)
        elif limit == "card":
            lines.append("%s:SetCountLimit(1)" % v)
        elif limit == "name":
            n = k if self.shared_limit else k - 1      # 有「其中1个」的共用额度时，id 留给它
            lines.append("%s:SetCountLimit(1,%s)" % (v, "id" if n == 0 else "id+o*%d" % n))
        elif limit == "name_shared":
            lines.append("%s:SetCountLimit(1,id)" % v)
        elif limit == "activate_card":
            lines.append("%s:SetCountLimit(1,id+EFFECT_COUNT_CODE_OATH)" % v)
        elif limit == "duel":
            lines.append("%s:SetCountLimit(1,id+EFFECT_COUNT_CODE_DUEL)" % v)
        elif limit == "chain":
            lines.append("%s:SetCountLimit(1,EFFECT_COUNT_CODE_CHAIN)" % v)
        elif limit == "card_shared":
            lines.append("%s:SetCountLimit(1,EFFECT_COUNT_CODE_SINGLE)" % v)
        elif ev in PHASE_EVENTS and t in ("trigger_o", "trigger_f", "listener"):
            lines.append("%s:SetCountLimit(1)" % v)       # 阶段的时机：不限次数的话引擎会在那个阶段一直触发
        if limit and times > 1:                            # 「1回合2次」：次数额度改成几次
            lines[mark:] = [x.replace(":SetCountLimit(1", ":SetCountLimit(%d" % times) for x in lines[mark:]]
        # 发动条件：条件积木 + 事件的「谁的」 + 无效类处理要求连锁能被无效
        conds = []
        who = node.get("event_player", "any")
        if ev in EVENT_COND:
            conds.append(EVENT_COND[ev])
        if who in PLAYER and ev in EVENT_PLAYER:
            conds.append(EVENT_PLAYER[ev] % PLAYER[who])
        if node.get("damage_step") == "yes":
            conds.append("aux.dscon(e,tp,eg,ep,ev,re,r,rp)")
        blocks = {b["block"] for b in walk(ops)}
        if "negate_activation" in blocks:
            conds.append("Duel.IsChainNegatable(ev)")
        elif "negate_effect" in blocks:
            conds.append("Duel.IsChainDisablable(ev)")
        if ev == "chaining" and ("negate_activation" in blocks or "negate_effect" in blocks) and t == "quick_o":
            conds.insert(0, "not e:GetHandler():IsStatus(STATUS_BATTLE_DESTROYED)")
        cond_node = one(node, "condition")
        if cond_node:
            conds.append(self.cond(cond_node))
        if twice:
            conds.append("e:GetHandler():GetFlagEffect(id+%d)<(%s and %d or %d)" % (TWICE_FLAG + k, self.cond(twice),
                                                                                    times + 1, times))
        if conds:
            name = "s.condition%d%s" % (k, suffix)
            self.add_func("function %s(e,tp,eg,ep,ev,re,r,rp)\n\treturn %s\nend" % (name, " and ".join(conds)))
            lines.append("%s:SetCondition(%s)" % (v, name))
        return lines

    def operation_lines(self, ops, no_chain=False):
        """处理函数的内容：先取出对象，再是处理。self.target、self.targets 由调用方设好。"""
        body = ["local c=e:GetHandler()"]
        if len(self.targets) > 1:
            body.append("local tg=Duel.GetChainInfo(0,CHAININFO_TARGET_CARDS):Filter(Card.IsRelateToEffect,nil,e)")
            for tn in self.targets:
                body.append("local tg_%s=tg:Filter(%s,nil,e,tp)" % (tn["as"], self.split_fn(tn)))
                if tn["count"] == 1:
                    body.append("local tc_%s=tg_%s:GetFirst()" % (tn["as"], tn["as"]))
        elif self.target is not None:
            if self.target["count"] == 1:
                body.append("local tc=Duel.GetFirstTarget()")
            else:
                body.append("local tg=Duel.GetChainInfo(0,CHAININFO_TARGET_CARDS):Filter(Card.IsRelateToEffect,nil,e)")
        self.no_chain = no_chain
        body += self.statements(ops)
        self.no_chain = False
        return body

    def modal_effect(self, node, desc):
        """「从以下效果选择1个发动」：发动时选分支，分类和取对象跟着分支走。"""
        modes = node["modes"]
        t = node["type"]
        evs = events_of(node)
        if t == "listener" or node.get("target") or node.get("operation") or len(evs) > 1:
            raise CompileError("「发动时选的分支」不能和效果自己的对象、处理或多个时机一起用，也不能用在不入连锁的效果上")
        self.k += 1
        k = self.k
        v = "e%d" % k
        all_ops = [st for mode in modes for st in mode.get("operation", [])]
        self.target, self.targets = None, []
        lines = ["local %s=Effect.CreateEffect(c)" % v]
        if desc is not None:
            lines.append("%s:SetDescription(aux.Stringid(id,%d))" % (v, desc))
        lines += self.effect_head(v, node, evs[0], k, all_ops)
        if node.get("cost"):
            lines.append("%s:SetCost(%s)" % (v, self.cost_fn(node["cost"])))
        args = "e,tp,eg,ep,ev,re,r,rp"
        chkc, checks, picks, choose, run = [], [], [], [], []
        for i, mode in enumerate(modes, 1):
            self.k += 1
            ops = mode.get("operation", [])
            self.target, self.targets = one(mode, "target"), list(mode.get("target") or [])
            target = self.target_fn(dict(node, target=mode.get("target") or [], operation=ops), ops, t in ("trigger_f", "flip", "quick_f"))
            operation = "s.operation%d" % self.k
            self.add_func("function %s(%s)\n%s\nend" % (operation, args, "\n".join(indent(self.operation_lines(ops)))))
            condition = one(mode, "cond")
            checks.append("local b%d=%s%s(%s,0)" % (i, "(%s) and " % self.cond(condition) if condition else "", target, args))
            picks.append("if b%d then ops[#ops+1]=aux.Stringid(id,%d) vals[#vals+1]=%d end" % (i, self.string(mode.get("text") or "分支%d" % i), i))
            flag = "prop+EFFECT_FLAG_CARD_TARGET" if self.target is not None else "prop"
            choose += ["%s op==%d then" % ("if" if i == 1 else "elseif", i),
                       "\te:SetCategory(%s)" % ("+".join(self.categories(ops)) or "0"), "\te:SetProperty(%s)" % flag, "\t%s(%s,1)" % (target, args)]
            run += ["%s op==%d then" % ("if" if i == 1 else "elseif", i), "\t%s(%s)" % (operation, args)]
            if self.target is not None and len(self.targets) == 1 and self.target["count"] == 1:
                chkc.append("if op==%d then return %s(%s,0,chkc) end" % (i, target, args))
        self.target, self.targets = None, []
        name = "s.modetarget%d" % k
        head = ["if chkc then", "\tlocal op=e:GetLabel()"] + ["\t" + line for line in chkc] + ["\treturn false", "end"]
        body = head + checks + ["if chk==0 then return %s end" % " or ".join("b%d" % i for i in range(1, len(modes) + 1)),
                                "local ops,vals={},{}"] + picks + ["local op=vals[Duel.SelectOption(tp,table.unpack(ops))+1]", "e:SetLabel(op)",
                                "local prop=e:GetProperty()&~EFFECT_FLAG_CARD_TARGET"] + choose + ["end"]
        self.add_func("\n".join(["function %s(%s,chk,chkc)" % (name, args)] + indent(body) + ["end"]))
        lines.append("%s:SetTarget(%s)" % (v, name))
        operation = "s.modeoperation%d" % k
        self.add_func("\n".join(["function %s(%s)" % (operation, args)] + indent(["local op=e:GetLabel()"] + run + ["end"]) + ["end"]))
        return lines + ["%s:SetOperation(%s)" % (v, operation), "c:RegisterEffect(%s)" % v]

    def effect(self, node, desc):
        if node.get("modes"):
            return self.modal_effect(node, desc)
        self.k += 1
        k = self.k
        v = "e%d" % k
        t = node["type"]
        evs = events_of(node)
        ev = evs[0]
        ops = node.get("operation", [])
        self.target = one(node, "target")
        self.targets = list(node.get("target") or [])
        base = []
        if desc is not None:
            base.append("%s:SetDescription(aux.Stringid(id,%d))" % (v, desc))
        cats = self.categories(ops) if t != "listener" else []
        if cats:
            base.append("%s:SetCategory(%s)" % (v, "+".join(cats)))
        head = self.effect_head(v, node, ev, k, ops)
        tail = []
        if t == "listener":                 # 不入连锁：没有代价、对象、发动检查
            if node.get("cost") or self.target is not None:
                raise CompileError("「每次……（不入连锁）」不能有代价和对象")
        else:
            if node.get("cost"):
                tail.append("%s:SetCost(%s)" % (v, self.cost_fn(node["cost"])))
            tail.append("%s:SetTarget(%s)" % (v, self.target_fn(node, ops, t in ("trigger_f", "flip", "quick_f"))))
        body = self.operation_lines(ops, t == "listener")
        name = "s.operation%d" % k
        self.add_func("function %s(e,tp,eg,ep,ev,re,r,rp)\n%s\nend" % (name, "\n".join(indent(body))))
        tail.append("%s:SetOperation(%s)" % (v, name))
        lines = ["local %s=Effect.CreateEffect(c)" % v] + base + head + tail + ["c:RegisterEffect(%s)" % v]
        if ev in ("summon_both", "monster_summoned_both"):
            lines += ["local %sb=%s:Clone()" % (v, v), "%sb:SetCode(EVENT_SPSUMMON_SUCCESS)" % v,
                      "c:RegisterEffect(%sb)" % v]
        # 「……的场合或者……的场合」：同一个效果按其余的时机各再登记一份（共用代价、对象、处理和次数）
        for i, ev2 in enumerate(evs[1:]):
            suffix = "x" if i == 0 else "x%d" % (i + 1)
            vb = v + suffix

            def again(text, vb=vb):
                return vb + text[len(v):] if text.startswith(v + ":") else text
            lines += ["local %s=Effect.CreateEffect(c)" % vb] + [again(x) for x in base] + \
                self.effect_head(vb, node, ev2, k, ops, suffix) + [again(x) for x in tail] + ["c:RegisterEffect(%s)" % vb]
        self.target = None
        self.targets = []
        return lines

    # ------------------------------------------------------------ 永续效果
    def continuous(self, node):
        self.k += 1
        k = self.k
        v = "e%d" % k
        mode, code = node["mode"], node["code"]
        rng = "pzone" if node.get("part") == "pendulum" else node.get("range", "mzone")
        lines = ["local %s=Effect.CreateEffect(c)" % v]
        if mode == "equipped":
            lines.append("%s:SetType(EFFECT_TYPE_EQUIP)" % v)
        elif mode == "self":
            lines += ["%s:SetType(EFFECT_TYPE_SINGLE)" % v, "%s:SetProperty(EFFECT_FLAG_SINGLE_RANGE)" % v]
        elif mode == "card_target":
            lines += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetTargetRange(LOCATION_MZONE,LOCATION_MZONE)" % v,
                      "%s:SetTarget(%s)" % (v, self.fn("cttg", "function %s(e,c)\n\treturn e:GetHandler():IsHasCardTarget(c)\nend"))]
        elif mode == "player":
            lines += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetProperty(EFFECT_FLAG_PLAYER_TARGET)" % v,
                      "%s:SetTargetRange(%s)" % (v, RANGE[node["player"]])]
        else:
            s_, o_ = self.sides(node)
            lines += ["%s:SetType(EFFECT_TYPE_FIELD)" % v, "%s:SetTargetRange(%s,%s)" % (v, s_, o_)]
        lines.append("%s:SetCode(%s)" % (v, code))
        if code == "EFFECT_INDESTRUCTABLE_COUNT":
            lines.append("%s:SetCountLimit(1)" % v)
        if mode != "equipped":
            lines.append("%s:SetRange(%s)" % (v, LOC[rng]))
        special = self.value_fn(code, node["value_cards"]) if node.get("value_cards") else \
            self.special_value(code, node.get("against"))
        if special:
            lines.append("%s:SetValue(%s)" % (v, special))
        if mode in ("zone", "player"):
            tg, val = self.field_target(node, code)
            if tg:
                lines.append("%s:SetTarget(%s)" % (v, tg))
            if val:
                lines.append("%s:SetValue(%s)" % (v, val))
        value = one(node, "value")
        if special:
            pass
        elif value is not None:
            expr = self.number(value)
            if value["block"] == "num":
                lines.append("%s:SetValue(%s)" % (v, expr))
            else:
                name = "s.value%d" % k
                self.add_func("function %s(e,c)\n\tlocal tp=e:GetHandlerPlayer()\n\treturn %s\nend" % (name, expr))
                lines.append("%s:SetValue(%s)" % (v, name))
        elif not any(l.startswith("%s:SetValue" % v) for l in lines) and (
                code == "EFFECT_CANNOT_ACTIVATE" and mode == "player" or code in VALUE_ONE):
            lines.append("%s:SetValue(1)" % v)
        cond_node = one(node, "condition")
        if cond_node:
            name = "s.condition%d" % k
            self.add_func("function %s(e)\n\tlocal tp=e:GetHandlerPlayer()\n\treturn %s\nend" % (name, self.cond(cond_node)))
            lines.append("%s:SetCondition(%s)" % (v, name))
        return lines + ["c:RegisterEffect(%s)" % v]

    # ------------------------------------------------------------ 整张卡
    def summon_part(self):
        """召唤手续、出场限制、指示物、灵摆：沿用 Effect Model v0.2 的 summon 结构和生成代码。"""
        from effect_model.lua.gen import Gen
        from effect_model.lua.summon import summon_lines
        g = Gen(v02_shell(self.card))
        lines = summon_lines(g)
        self.funcs += g.funcs
        self.strings += g.strings
        return lines

    def compile(self):
        info = self.card["card"]
        hats = self.card.get("effects", [])
        body = self.summon_part()
        kind = info.get("kind", "monster")
        if kind in ("spell", "trap") and not any((h["block"] == "effect" and h["type"] == "activate") or
                                                 (h["block"] == "custom_effect" and "EFFECT_TYPE_ACTIVATE" in str(h.get("lua"))) for h in hats):
            # 永续 / 场地 / 装备魔陷没有单独写「卡的发动」时，补一个普通的发动（不然放不到场上）
            body += ["local e0=Effect.CreateEffect(c)", "e0:SetType(EFFECT_TYPE_ACTIVATE)", "e0:SetCode(EVENT_FREE_CHAIN)",
                     "c:RegisterEffect(e0)"]
        if self.is_equip_spell() and not any(h["block"] == "continuous" and h.get("code") == "EFFECT_EQUIP_LIMIT"
                                             for h in hats):
            # 装备魔法卡：只能装备给怪兽（具体装备给谁由发动时的对象决定）
            body += ["local eql=Effect.CreateEffect(c)", "eql:SetType(EFFECT_TYPE_SINGLE)", "eql:SetCode(EFFECT_EQUIP_LIMIT)",
                     "eql:SetProperty(EFFECT_FLAG_CANNOT_DISABLE)", "eql:SetValue(1)", "c:RegisterEffect(eql)"]
        self.shared_limit = any(h.get("limit") == "name_shared" for h in hats)
        used = {b["block"] for b in walk(hats)}
        self.uses_cost_cards = "cost_cards" in used
        self.uses_by_proc = "f_by_proc" in used
        self.need_draw_count = False
        for h in hats:
            if h["block"] == "unique":
                body.append("c:SetUniqueOnField(1,%d,id)" % (1 if h.get("who") == "both" else 0))
        # 卡的文字里提到的卡名登记起来（别的卡的「记述了这个卡名的卡」才认得出）
        listed = sorted({int(b["code"]) for b in walk(hats) if b["block"] == "f_name" and int(b.get("code") or 0) > 0})
        if listed:
            body.append("aux.AddCodeList(c,%s)" % ",".join(str(x) for x in listed))
        descs = []
        for i, node in enumerate(hats):
            if node["block"] == "effect":
                descs.append(None if node["type"] == "listener" else
                             self.string("效果%s" % "①②③④⑤⑥⑦⑧⑨⑩"[i] if i < 10 else str(i + 1)))
        d = iter(descs)
        for node in hats:
            if node.get("block") == "effect":
                body += self.effect(node, next(d))
            elif node.get("block") == "continuous":
                body += self.continuous(node)
            elif node.get("block") == "unique":
                pass
            elif node.get("block") == "destroy_replace":
                body += self.destroy_replace(node)
            elif node.get("block") == "monster_trait":
                body += self.monster_trait(node)
            elif node.get("block") == "custom_effect":
                body += self.custom_effect(node)
            elif node.get("block") == "name_as":
                body += self.name_as(node)
            elif node.get("block") == "target_link":
                body += self.target_link(node)
            elif node.get("block") == "summon_rule":
                body += self.summon_rule(node)
            elif node.get("block") == "sp_proc":
                body += self.sp_proc(node)
            elif node.get("block") == "ns_proc":
                body += self.ns_proc(node)
            elif node.get("block") == "fusion_materials":
                body += self.fusion_materials(node)
            elif node.get("block") == "extra_materials":
                body += self.extra_materials(node)
            else:
                raise CompileError("最外层只能放「会发动的效果」或「永续效果」")
        if self.need_draw_count:
            # 「这个回合抽卡的张数」：引擎不记，这张卡自己记（每抽1张给那个玩家1个到回合结束的标记）
            body += ["if not s.global_check then", "\ts.global_check=true",
                     "\tlocal ge=Effect.CreateEffect(c)", "\tge:SetType(EFFECT_TYPE_FIELD+EFFECT_TYPE_CONTINUOUS)",
                     "\tge:SetCode(EVENT_DRAW)", "\tge:SetOperation(s.drawcount)", "\tDuel.RegisterEffect(ge,0)", "end"]
            self.add_func("function s.drawcount(e,tp,eg,ep,ev,re,r,rp)\n"
                          "\tfor i=1,#eg do Duel.RegisterFlagEffect(ep,id+%d,RESET_PHASE+PHASE_END,0,1) end\nend" % DRAW_FLAG)
        head = ["--" + info.get("name", ""), "local s,id,o=GetID()", "function s.initial_effect(c)"]
        return "\n".join(head + indent(body) + ["end"] + self.funcs + self.script_flags(hats, used)) + "\n"

    def script_flags(self, hats, used):
        """别的卡要查的脚本标记：「废铁信号灯」「奇迹同调融合」、会投硬币 / 掷骰子的卡。"""
        custom = "\n".join(str(b.get("lua")) + str(b.get("helpers")) for b in walk(hats) if b["block"] in ("raw", "custom_effect"))
        flags = []
        if any(h["block"] in ("extra_materials", "fusion_materials") and (h["block"] == "fusion_materials" or h.get("method", "synchro") == "synchro")
               and any(x["block"] == "f_subtype" and "synchro" in str(x.get("subtype")).split("+") for x in walk(h)) for h in hats):
            flags.append("s.material_type=TYPE_SYNCHRO")
        if "toss_coin" in used or "Duel.TossCoin" in custom:
            flags.append("s.toss_coin=true")
        if "toss_dice" in used or "Duel.TossDice" in custom:
            flags.append("s.toss_dice=true")
        return flags


def v02_shell(card):
    """只有召唤手续、没有效果的 v0.2 模型：召唤手续的文字和 Lua 用 Effect Model v0.2 的代码生成。"""
    info = dict(card["card"])
    summon = dict(card.get("summon") or {})
    if any(e.get("block") in ("extra_materials", "fusion_materials") for e in card.get("effects", [])):
        summon.pop("materials", None)          # 素材写在积木里了，不用工作台素材栏的那份
    counters = {}
    for b in walk(card.get("effects", [])):
        if b["block"] in ("add_counter", "remove_counter"):
            counters["spell"] = dict(counters.get("spell") or {})
            if b.get("max"):
                counters["spell"]["max"] = int(b["max"])
    return {"schema": "ygodiy-effect/0.2",
            "card": {"code": info.get("code", 0), "name": info.get("name", ""), "kind": info.get("kind", "monster"),
                     "subtypes": info.get("subtypes", [])},
            "summon": summon, "limits": card.get("limits") or {},
            "counters": counters, "effects": [], "rules": []}


def compile_card(card):
    """积木树（v0.3 JSON，含 card 块）→ Lua 脚本文本。拼得不完整时抛 CompileError，说明缺什么。"""
    return Compiler(card).compile()


def compile_full(card):
    """→ (Lua, 提示字符串列表)。"""
    c = Compiler(card)
    return c.compile(), c.strings


def check(card):
    """所有积木都放在类型对的槽里：返回问题列表（空表示没问题）。"""
    problems = []

    def visit(node, where):
        b = BLOCKS.get(node.get("block"))
        if b is None:
            problems.append("%s：不认识的积木 %r" % (where, node.get("block")))
            return
        for slot in b.slots:
            name, label, accepts, count, only = slot
            items = node.get(name) or []
            if count == 1 and len(items) > 1:
                problems.append("%s「%s」只能放一块积木" % (where, label))
            for child in items:
                cb = BLOCKS.get(child.get("block"))
                if cb and not fits(slot, child["block"]):
                    problems.append("%s「%s」不能放「%s」" % (where, label, cb.label))
                visit(child, "%s › %s" % (where, cb.label if cb else "?"))
    for i, eff in enumerate(card.get("effects", [])):
        visit(eff, "效果%d" % (i + 1))
    return problems
