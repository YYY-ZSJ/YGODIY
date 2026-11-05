"""积木能复现多少官方卡：逐个扫 MDPro3 的官方卡脚本（script.zip），看每张卡用到的引擎接口和常量。

一张卡用到的东西分三种：
    积木写得出的       翻译器（compile.py，以及召唤手续借用的 effect_model/lua）里出现过的接口、常量，259 种效果代码
    等价写法           官方换了种写法、积木用别的办法做到同样的事（提示文字、抽卡对象玩家、融合素材的内部函数……）
    拼不出的           按「缺的是哪一类效果」归类（代替破坏、连锁控制、纵列……）；15 张卡以下才用的归为长尾
全部是前两种的卡算「积木能拼」。这是词汇层面的估计：词汇都有不代表结构一定拼得出，所以是偏乐观的上限。

用法（在 YGODIY_src 下）：python -m blocks.coverage [输出的 Markdown 路径]
"""

import collections
import glob
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
SCRIPT_ZIP = r"D:/Game/MDPro3/Data/script.zip"

TOKEN = re.compile(r"\b(?:Duel|aux|Auxiliary|Group|Effect)\.(\w+)|:(\w+)\(|\b((?:EFFECT|EVENT|CATEGORY|LOCATION|REASON|TYPE|"
                   r"RACE|ATTRIBUTE|SUMMON_TYPE|HINTMSG|PHASE|POS|RESET|TIMING|ACTIVITY|CHAININFO|STATUS|SEQ|HINT)_\w+)")
LONG_TAIL = 15

# ---------------------------------------------------------------- 等价写法：积木用别的办法做到同样的事
EQUIVALENT = {
    # 积木用拼出来的接口名（Get%sGroup、Is%sAbove……）、或者反过来问的写法做到同一件事
    "IsRank", "GetRank", "GetMaxGroup", "GetMinGroup", "GetPreviousControler", "GetActivateLocation",
    "GetEquipCount", "IsAllTypes", "IsNonAttribute",
    # 积木统一用 IsAbleToDeckOrExtraAsCost；阶级 / 连接值的上下限也是拼出来的接口名；
    # aux 的小工具都能用现有积木拼：nzatk = 表侧＋攻击力>0，bpcon = 能进行战斗阶段「或者」战斗阶段中，
    # IsCodeOrListed = 卡名「或者」记述了卡名，Negate*Filter = 表侧＋效果怪兽＋没被无效；
    # GetActiveType / 发动的玩家 = 「那个发动的是……」/ 时机的「谁的」
    "IsAbleToDeckAsCost", "IsAbleToExtraAsCost", "IsRankAbove", "IsRankBelow", "IsLinkAbove", "IsLinkBelow",
    "GetCurrentScale", "nzatk", "bpcon", "IsCodeOrListed", "NegateEffectMonsterFilter", "NegateAnyFilter",
    "GetActiveType", "CHAININFO_TRIGGERING_PLAYER",
    # 只是提示、给 AI 的分类信息
    "HINT_OPSELECTED", "HINT_ZONE", "EFFECT_FLAG_CLIENT_HINT", "GetDescription",
    # 抽卡、伤害的对象玩家先存进连锁信息再取出（积木直接写玩家）
    "SetTargetPlayer", "SetTargetParam", "CHAININFO_TARGET_PLAYER", "CHAININFO_TARGET_PARAM",
    # 取对象的另一种写法、对象是否还有效
    "SetTargetCard", "IsRelateToChain", "GetTargetsRelateToChain", "IsCanBeEffectTarget", "SelectTargetFromFieldFirst",
    "IsFaceupEx", "ExceptThisCard", "FALSE", "GetFirstMatchingCard", "IsInGroup", "Clear", "CancelableSelect",
    "IsCostChecked", "AdjustAll", "AdjustInstantly", "ClearOperationInfo", "mzctcheck", "mzctcheckrel",
    "NecroValleyNegateCheck", "IsCanAddCounter", "IsCanChangePosition", "IsEnvironment", "SUMMON_TYPE_NORMAL",
    "GetSummonType", "REASON_SUMMON", "IsSummonPlayer", "GetSummonPlayer",
    # 「把墓地的这张卡除外」当代价、解放 / 送墓当代价的另一种写法
    "bfgcost", "GetReleaseGroup", "CheckReleaseGroupEx", "SelectReleaseGroupEx", "UseExtraReleaseCount",
    # 卡组最上面送去墓地
    "DiscardDeck", "IsPlayerCanDiscardDeck", "IsPlayerCanDiscardDeckAsCost",
    # 是否 / 选项（积木：可以选择做、让玩家选一项）
    "SelectEffectYesNo", "SelectFromOptions",
    # 融合 / 仪式召唤的内部函数（积木用引擎的 aux.FusionEffectUltimate / RitualUltimate）
    "CheckFusionMaterial", "SelectFusionMaterial", "GetChainMaterial", "GetFusionMaterial", "IsCanBeFusionMaterial",
    "FCheckAdditional", "gffcheck", "gfcheck", "ReleaseRitualMaterial", "GetRitualMaterial", "RitualCheckAdditional",
    "RitualUltimateFilter", "AddRitualProcGreaterCode", "AddRitualProcGreater2", "CreateChecks",
    # 和效果无关的元数据
    "xyz_number", "AddSetNameMonsterList", "AddMaterialCodeList",
    # 场上只能存在1张的检查、选卡过程的内部函数
    "CheckUniqueOnField", "SetSelectedCard", "ClearTargetCard",
}
EQUIVALENT_PREFIX = ("HINTMSG_", "TIMING_", "CATEGORY_")

# ---------------------------------------------------------------- 拼不出的：缺的是哪一类效果
CATEGORIES = [
    ("代替破坏 / 代替处理", "「这张卡被破坏的场合，可以作为代替把……除外」",
     {"REASON_REPLACE", "STATUS_DESTROY_CONFIRMED", "REASON_REDIRECT"}),
    ("连锁控制", "「对方不能对应这个效果的发动把效果发动」「这个效果的发动不会被无效」、按发动的位置 / 玩家判断",
     {"SetChainLimit", "SetChainLimitTillChainEnd", "EFFECT_FLAG_CANNOT_INACTIVATE", "CHAININFO_TRIGGERING_LOCATION",
      "CHAININFO_TRIGGERING_EFFECT", "CHAININFO_TRIGGERING_PLAYER", "CHAININFO_TRIGGERING_CONTROLER", "CHAININFO_CHAIN_ID",
      "EVENT_CHAIN_END", "EVENT_CHAIN_DISABLED", "EVENT_CHAIN_NEGATED", "STATUS_CHAINING", "ChangeChainOperation",
      "ChangeTargetCard", "GetActivateLocation", "GetActiveType", "CheckActivateEffect", "EFFECT_COUNT_CODE_CHAIN",
      "IsCanBeQuickEffect", "NegateAnyFilter", "NegateEffectMonsterFilter", "EVENT_BREAK_EFFECT"}),
    ("纵列、格子、连接区", "「和这张卡相同纵列」「移动到旁边的怪兽区域」「这张卡所连接区」「指定不能使用的区域」",
     {"GetSequence", "MoveSequence", "GetLinkedZone", "SelectDisableField", "GetPreviousSequence", "GetSZoneCount",
      "GetMutualLinkedGroupCount", "IsLinkState", "LOCATION_REASON_TOFIELD", "SetAbsoluteRange", "EFFECT_FLAG_BOTH_SIDE"}),
    ("随机", "「对方随机选1张手卡」", {"RandomSelect"}),
    ("自定义召唤手续与素材限制", "「这张卡可以从手卡特殊召唤（条件）」、接触融合、特殊的融合 / 同调素材写法、只能用某种方法特殊召唤",
     {"MustMaterialCheck", "AddFusionProcFun2", "AddFusionProcFunRep", "AddFusionProcCode3", "AddSynchroMixProcedure",
      "fuslimit", "ritlimit", "synlimit", "IsMaterialListCode", "ContactFusionSendToDeck", "EFFECT_FLAG_SPSUM_PARAM",
      "GetSpecialSummonInfo", "IsSpecialSummonSetCard", "SetStatus", "REASON_FUSION", "REASON_SYNCHRO", "REASON_XYZ",
      "REASON_LINK", "IsFusionSetCard", "IsFusionAttribute", "IsFusionType", "IsFusionCode", "IsLinkRace",
      "IsLinkSetCard", "IsLinkAttribute", "IsXyzType", "GetSynchroMaterial", "IsCanBeXyzMaterial", "GetFusionAttribute",
      "SameValueCheck", "CheckTribute", "SelectTribute"}),
    ("效果里进行同调 / 超量 / 连接 / 通常召唤", "「用自己场上的怪兽为素材进行同调召唤」「进行1只怪兽的召唤」",
     {"SynchroSummon", "XyzSummon", "LinkSummon", "IsSynchroSummonable", "IsXyzSummonable", "IsLinkSummonable",
      "IsSummonable", "IsSummonableCard", "IsPlayerCanSummon", "IsPlayerCanAdditionalSummon", "MSet", "IsMSetable"}),
    ("得到效果、复制效果", "「得到那只怪兽的效果」「作为超量素材时给与这只怪兽效果」「当作和那张卡相同的效果」",
     {"EFFECT_TYPE_GRANT", "EFFECT_TYPE_XMATERIAL", "EnableChangeCode", "GetTextAttack", "GetTextDefense"}),
    ("战斗细节", "「改变攻击对象」「进行伤害计算」「可以再1次攻击」「跳过战斗阶段」「伤害计算时」",
     {"ChangeAttackTarget", "CalculateDamage", "ChainAttack", "IsChainAttackable", "GetBattleDamage",
      "GetBattledGroupCount", "GetBattleMonster", "GetAttackedCount", "IsAttackable", "IsAbleToEnterBP", "SkipPhase",
      "STATUS_ATTACK_CANCELED", "EVENT_BATTLE_CONFIRM", "PHASE_DAMAGE_CAL", "PHASE_BATTLE_START", "PHASE_BATTLE_STEP",
      "bpcon", "dsercon", "damcon1", "bdogcon", "bdcon", "nzatk", "STATUS_OPPO_BATTLE", "GetBattlePosition"}),
    ("原因的细节", "「被对方的效果破坏」「作为同调素材」「因为这张卡的效果」：谁、哪张卡、哪个效果造成的",
     {"GetReasonCard", "GetReasonPlayer", "GetReasonEffect", "GetReason", "REASON_TEMPORARY", "REASON_RETURN",
      "REASON_LOST_TARGET", "REASON_REVEAL", "REASON_DRAW"}),
    ("离开场上前的信息", "「原本在场上的「X」怪兽」「这张卡装备过的怪兽」「之前是什么种族 / 属性 / 卡名」",
     {"GetPreviousControler", "IsPreviousSetCard", "GetPreviousTypeOnField", "GetPreviousRaceOnField",
      "GetPreviousEquipTarget", "GetPreviousCodeOnField", "GetPreviousAttributeOnField", "GetPreviousPosition",
      "GetPreviousOverlayCountOnField"}),
    ("暂时除外再回来", "「直到结束阶段除外」「那些卡回到场上」", {"ReturnToField", "RESET_TOFIELD"}),
    ("卡与卡的持续关联、效果查询", "「以那只怪兽为对象的这张卡离场时」「这张卡的效果适用中的怪兽」、查询别的效果",
     {"SetCardTarget", "GetCardTarget", "GetFirstCardTarget", "CreateEffectRelation", "CreateRelation",
      "IsHasCardTarget", "GetCardTargetCount", "EFFECT_TYPE_TARGET", "EFFECT_FLAG_OWNER_RELATE", "SetOwnerPlayer",
      "GetTarget", "GetValue", "GetProperty", "IsHasEffect", "IsDisabled", "GetEffectCount", "STATUS_EFFECT_ENABLED",
      "GetTurnID", "STATUS_SPSUMMON_TURN", "EnableGlobalFlag", "AddThisCardInGraveAlreadyCheck", "SetFlagEffectLabel",
      "STATUS_LEAVE_CONFIRMED", "STATUS_TO_HAND_WITHOUT_CONFIRM", "IsImmuneToEffect", "IsDestructable"}),
    ("自定义事件", "「这张卡的效果特殊召唤的怪兽被破坏时」等需要自己发出的事件",
     {"EVENT_CUSTOM", "RaiseSingleEvent", "RegisterMergedDelayedEvent_ToSingleCard", "CheckEvent", "EVENT_ADJUST"}),
    ("特殊怪兽机制", "卡通、二重、灵魂、同盟、陷阱怪兽",
     {"TYPE_TOON", "TYPE_DUAL", "IsDualState", "EnableDualAttribute", "TYPE_SPIRIT", "EnableSpiritReturn", "TYPE_UNION",
      "SetUnionState", "IsUnionState", "EnableUnionAttribute", "GetUnionCount", "TYPE_TRAPMONSTER", "AddMonsterAttribute"}),
    ("卡组排序、代替通常抽卡", "「把卡组最上面的卡确认，用喜欢的顺序放回」「放弃通常抽卡」「放到卡组最下面」",
     {"SortDecktop", "PlaceCardsOnDeckBottom", "ShuffleExtra", "LOCATION_DECKBOT", "EVENT_PREDRAW", "IsPlayerCanNormalDraw",
      "GiveUpNormalDraw"}),
    ("更多时机", "阶段开始时、离场之前、移动、盖放、超量素材取除、基本分回复、表示形式变更、装备时",
     {"EVENT_PHASE_START", "EVENT_LEAVE_FIELD_P", "EVENT_MOVE", "EVENT_SSET", "EVENT_MSET", "EVENT_DETACH_MATERIAL",
      "EVENT_RECOVER", "EVENT_CHANGE_POS", "EVENT_EQUIP", "EVENT_TO_DECK", "EFFECT_TYPE_QUICK_F"}),
    ("更多卡片条件与数值", "阶级、连接值、和某卡相同的属性 / 种族、攻击力最高的、等级合计正好、宣言数字、卡上写的攻击力",
     {"IsRank", "GetRank", "IsRankAbove", "IsRankBelow", "IsLinkAbove", "IsLinkBelow", "GetAttribute", "GetRace",
      "GetOriginalRace", "GetOriginalAttribute", "GetMaxGroup", "GetMinGroup", "SelectWithSumEqual", "CheckSubGroupEach",
      "SelectSubGroupEach", "AnnounceNumber", "IsAllTypes", "IsNonAttribute", "IsCodeOrListed", "GetXyzNumber",
      "IsExtraDeckMonster", "TYPE_TOKEN", "GetTargetCount", "GetEquipCount", "GetEquipGroup", "GetCurrentScale",
      "GetLeftScale", "IsPlayerCanSpecialSummonCount", "LOCATION_OVERLAY", "IsDualState"}),
    ("装备、灵摆、表示形式的细节", "「装备卡回到手卡」「装备魔法卡的装备对象检查」「把灵摆怪兽加入额外卡组」「选择表示形式」",
     {"CheckEquipTarget", "EquipComplete", "CancelToGrave", "SendtoExtraP", "SelectPosition", "EVENT_SSET"}),
    ("次数和代价的其他写法", "「1连锁1次」「同1次连锁上只能」「作为代价加入手卡 / 回到额外卡组」",
     {"EFFECT_COUNT_CODE_SINGLE", "IsAbleToHandAsCost", "IsAbleToExtraAsCost", "IsAbleToDeckOrExtraAsCost",
      "CheckPhaseActivity", "EFFECT_FLAG_ACTIVATE_CONDITION", "EFFECT_TYPE_ACTIONS", "EFFECT_FLAG_EVENT_PLAYER",
      "sumreg", "tkfcon", "nbtg", "exccon", "gbspcon"}),
]
LONG_TAIL_NAME = "长尾（不到 15 张卡用到的个别写法）"
OTHER_NAME = "其他（还没归类）"


def ours_vocabulary():
    text = ""
    for p in [os.path.join(HERE, "compile.py")] + glob.glob(os.path.join(SRC, "effect_model", "lua", "*.py")):
        with open(p, encoding="utf-8") as f:
            text += f.read()
    with open(os.path.join(HERE, "effect_codes.json"), encoding="utf-8") as f:
        codes = {c["name"] for c in json.load(f)["codes"]}
    return text, codes


def scan(zip_path=SCRIPT_ZIP):
    """→ {卡号: 积木写不出的名字集合}（已经去掉等价写法）。"""
    text, codes = ours_vocabulary()
    z = zipfile.ZipFile(zip_path)
    out = {}
    for n in z.namelist():
        m = re.fullmatch(r"script/c(\d+)\.lua", n)
        if not m:
            continue
        lua = z.read(n).decode("utf-8", "ignore")
        miss = set()
        for t in TOKEN.finditer(lua):
            name = t.group(1) or t.group(2) or t.group(3)
            if not name or name in text or name in codes or name in EQUIVALENT or name.startswith(EQUIVALENT_PREFIX):
                continue
            miss.add(name)
        out[int(m.group(1))] = miss
    return out


def classify(missing):
    """→ ({卡号: 拼不出的类别集合}, 每个名字用到的卡数)。"""
    usage = collections.Counter(n for miss in missing.values() for n in miss)
    which = {}
    for name in usage:
        cat = next((c for c, _, names in CATEGORIES if name in names), None)
        which[name] = cat or (LONG_TAIL_NAME if usage[name] < LONG_TAIL else OTHER_NAME)
    return {code: {which[n] for n in miss} for code, miss in missing.items()}, usage, which


def report(missing, names=None):
    cats, usage, which = classify(missing)
    total = len(cats)
    full = [c for c, s in cats.items() if not s]
    touched, only = collections.Counter(), collections.Counter()
    examples = collections.defaultdict(list)
    for code, s in cats.items():
        for c in s:
            touched[c] += 1
        if len(s) == 1:
            c = next(iter(s))
            only[c] += 1
            if len(examples[c]) < 4:
                examples[c].append(code)
    name = names or (lambda code: str(code))
    lines = ["# 积木能复现多少官方卡", "",
             "由 `python -m blocks.coverage` 生成：逐个扫 MDPro3 的官方卡脚本，用到的引擎接口和常量全是积木写得出的"
             "（或者积木有等价写法）就算「能拼」。这是词汇层面的估计，偏乐观（词汇都有不代表结构一定拼得出）。", "",
             "| | 卡数 | 占比 |", "| --- | ---: | ---: |",
             "| 官方卡脚本 | %d | 100%% |" % total,
             "| 积木能拼 | %d | %.1f%% |" % (len(full), 100 * len(full) / total),
             "| 只差一类 | %d | %.1f%% |" % (sum(only.values()), 100 * sum(only.values()) / total),
             "| 差两类以上 | %d | %.1f%% |" % (total - len(full) - sum(only.values()),
                                         100 * (total - len(full) - sum(only.values())) / total), "",
             "## 拼不出的类别", "",
             "「用到」：这张卡用到了这一类；「只差这类」：补上这一类，这些卡就能拼（补哪类最划算看这一列）。", "",
             "| 类别 | 例子 | 用到 | 只差这类 | 只差这类的例卡 |", "| --- | --- | ---: | ---: | --- |"]
    desc = {c: d for c, d, _ in CATEGORIES}
    desc[LONG_TAIL_NAME] = "每种写法只有少数卡用，多是那张卡独有的特殊处理"
    desc[OTHER_NAME] = "15 张以上的卡用到、还没归类的写法"
    for c, n in sorted(touched.items(), key=lambda x: (-only[x[0]], -x[1])):
        lines.append("| %s | %s | %d | %d | %s |" % (c, desc.get(c, ""), n, only[c], "、".join(name(x) for x in examples[c])))
    other = [(n, usage[n]) for n, c in which.items() if c == OTHER_NAME]
    if other:
        lines += ["", "## 还没归类的写法（15 张卡以上）", "",
                  "、".join("%s（%d）" % (n, k) for n, k in sorted(other, key=lambda x: -x[1]))]
    return "\n".join(lines) + "\n", len(full), total


def main():
    sys.path.insert(0, SRC)
    try:
        from sandbox.core import Core
        core = Core()

        def names(code):
            return core.name(code) or str(code)
    except Exception:            # 没有 MDPro3 的卡片数据库时只写卡号
        names = None
    text, full, total = report(scan(), names)
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "覆盖统计.md")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(text)
    print("写到 %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
