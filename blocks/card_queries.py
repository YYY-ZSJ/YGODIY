"""卡片关系、能力和数值的中文名称与对应的 MDPro3 接口。"""

RELATED_GROUPS = {
    "materials_used": ("这张卡召唤使用的素材", "GetMaterial"),
    "mutual_linked_group": ("和这张卡互相连接的怪兽", "GetMutualLinkedGroup"),
    "persistent_targets": ("这张卡持续取为对象的全部卡", "GetCardTarget"),
    "battled_group": ("这个回合和这张卡战斗过的怪兽", "GetBattledGroup"),
}
RELATED_CARDS = {
    "reason_card": ("使这张卡发生此次变化的卡", "GetReasonCard"),
    "overlay_host": ("以这张卡为超量素材的怪兽", "GetOverlayTarget"),
}
RELATIONS = {**RELATED_GROUPS, **RELATED_CARDS}
CAPABILITIES = {
    "destroy": ("能被这个效果破坏", "c:IsDestructable(e)"),
    "target": ("能成为这个效果的对象", "c:IsCanBeEffectTarget(e)"),
    "position": ("能改变表示形式", "c:IsCanChangePosition()"),
    "control": ("能转移控制权", "c:IsAbleToChangeControler()"),
}
CARD_VALUES = {
    "announced_attacks": ("本回合攻击宣言次数", "GetAttackAnnouncedCount"),
    "location_turn": ("进入当前区域的回合编号", "GetTurnID"),
    "turn_counter_of": ("回合计数", "GetTurnCounter"),
    "overlay_count_of": ("持有的超量素材数量", "GetOverlayCount"),
}
CARD_STATES = {
    "immune": ("不受这个效果影响", "c:IsImmuneToEffect(e)"),
    "disabled": ("处于效果无效状态", "c:IsDisabled()"),
    "in_battle": ("仍与本次战斗有关联", "c:IsRelateToBattle()"),
}
PREVIOUS_VALUES = {
    "def": ("守备力", "GetPreviousDefenseOnField"),
    "level": ("等级", "GetPreviousLevelOnField"),
    "rank": ("阶级", "GetPreviousRankOnField"),
    "atk": ("攻击力", "GetPreviousAttackOnField"),
}
SHUFFLE_PILES = {
    "deck": ("卡组", "Duel.ShuffleDeck"),
    "hand": ("手卡", "Duel.ShuffleHand"),
    "extra": ("额外卡组", "Duel.ShuffleExtra"),
}


def choices(entries):
    return [(key, label) for key, (label, _) in entries.items()]
