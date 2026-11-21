"""具名的对局接口积木。槽的顺序与原接口一致，可选尾参数和回调也能接表达式。"""

# 名称以冒号开头时，第一个槽是调用方法的对象，冒号本身保留 Lua 的 self 语义。
CALLS = {
    "Effect.CreateEffect": ("创建卡片效果", "持有卡"),
    ":Clone": ("复制效果或卡片组", ""),
    ":RegisterEffect": ("将效果登记到卡片", "效果,是否强制"),
    "Duel.RegisterEffect": ("将效果登记到玩家", "效果,玩家"),
    ":SetType": ("设置效果类型", "效果类型"),
    ":SetCode": ("设置效果代码或事件时机", "代码"),
    ":SetCategory": ("设置效果分类", "分类"),
    ":SetProperty": ("设置效果属性", "属性"),
    ":SetRange": ("设置效果的适用区域", "区域"),
    ":SetTargetRange": ("设置双方受影响的区域", "己方,对方"),
    ":SetCountLimit": ("设置效果使用次数", "次数,共享编号"),
    ":SetCondition": ("设置发动或适用条件", "条件函数"),
    ":SetCost": ("设置支付代价的函数", "代价函数"),
    ":SetTarget": ("设置取对象及发动检查", "取对象函数"),
    ":SetOperation": ("设置效果处理", "处理函数"),
    ":SetValue": ("设置效果数值或判定函数", "数值或函数"),
    ":SetReset": ("设置效果重置条件", "重置时机,次数"),
    ":SetDescription": ("设置效果提示文字", "提示编号"),
    ":SetLabel": ("记录效果的数值", "数值"),
    ":GetLabel": ("读取效果记录的数值", ""),
    ":SetLabelObject": ("记录效果关联的对象", "对象"),
    ":GetLabelObject": ("读取效果关联的对象", ""),
    ":GetHandler": ("取得效果持有卡", ""),
    ":GetHandlerPlayer": ("取得效果持有玩家", ""),
    ":GetReasonEffect": ("取得造成此次变化的效果", ""),
    ":IsHasEffect": ("查询施加在卡上的效果", "效果代码"),
    ":IsRelateToEffect": ("检查卡与效果是否仍有关联", "效果"),
    ":GetCardTarget": ("取得持续取为对象的卡片组", ""),
    ":SetCardTarget": ("建立卡片间的持续对象关系", "对象卡"),
    ":CancelCardTarget": ("解除持续对象关系", "对象卡"),
    ":GetLinkedZone": ("取得连接箭头指向的区域", "从哪方查看"),
    ":GetColumnGroup": ("取得同一纵列的卡", "左侧距离,右侧距离"),
    ":GetFlagEffect": ("取得卡片标记数", "标记编号"),
    ":RegisterFlagEffect": ("给卡片登记标记", "标记编号,重置时机,属性,次数,数值"),
    "Duel.RaiseEvent": ("对卡片组发出事件", "卡片组,事件编号,原因效果,原因,原因玩家,事件玩家,事件数值"),
    "Duel.RaiseSingleEvent": ("对单张卡发出事件", "卡片,事件编号,原因效果,原因,原因玩家,事件玩家,事件数值"),
    "Duel.GetChainInfo": ("查询指定连锁的资料", "连锁编号,资料种类"),
    "Duel.SetTargetPlayer": ("记下效果处理的目标玩家", "玩家"),
    "Duel.SetTargetParam": ("记下效果处理要用的数值", "数值"),
    "Duel.IsPlayerCanDraw": ("检查玩家能否抽指定张数", "玩家,张数"),
    "Duel.GetMatchingGroup": ("取得符合条件的卡片组", "筛选函数,玩家,己方区域,对方区域,排除的卡"),
    "Duel.SelectMatchingCard": ("让玩家从指定区域选卡", "选择玩家,筛选函数,参考玩家,己方区域,对方区域,最少张数,最多张数,排除的卡"),
    "Duel.IsExistingMatchingCard": ("检查指定区域是否有符合条件的卡", "筛选函数,玩家,己方区域,对方区域,至少几张,排除的卡"),
    "Duel.SelectTarget": ("发动时选择效果对象", "选择玩家,筛选函数,参考玩家,己方区域,对方区域,最少张数,最多张数,排除的卡"),
    "Duel.GetFirstTarget": ("取得第一个效果对象", ""),
    "Duel.SetOperationInfo": ("登记即将进行的处理", "连锁编号,效果分类,涉及的卡,数量,玩家,附加数值"),
    ":Filter": ("按条件筛选卡片组", "筛选函数,排除的卡"),
    ":IsExists": ("卡片组是否含有符合条件的卡", "筛选函数,至少几张,排除的卡"),
    ":Select": ("从卡片组选择卡片", "玩家,最少张数,最多张数,排除的卡"),
    "Duel.Destroy": ("破坏指定卡片", "卡片,原因"),
    "Duel.SendtoGrave": ("将指定卡片送去墓地", "卡片,原因"),
    "Duel.Remove": ("除外指定卡片", "卡片,表示形式,原因"),
    "Duel.SpecialSummon": ("特殊召唤指定卡片", "卡片,召唤类型,召唤玩家,场地方,无视条件,无视苏生限制,表示形式"),
    "Duel.Draw": ("让玩家抽卡", "玩家,张数,原因"),
    "Duel.Damage": ("给与玩家伤害", "玩家,数值,原因"),
    "aux.Stringid": ("取得卡片的提示文字", "卡号,提示序号"),
}


def block_id(api):
    return "ls_api_" + api.replace(":", "method_").replace(".", "_")


BY_BLOCK = {block_id(api): api for api in CALLS}
ENGINE_TABLES = ("Duel", "Card", "Effect", "Group", "aux", "Auxiliary")


def arguments(api):
    names = CALLS[api][1]
    return names.split(",") if names else []


def call_node(api, receiver, args):
    node = {"block": block_id(api)}
    if api.startswith(":"):
        node["receiver"] = [receiver]
    n = len(arguments(api))
    for i, arg in enumerate(args[:n]):
        node["arg%d" % i] = [arg]
    if len(args) > n:
        node["more"] = args[n:]
    return node
