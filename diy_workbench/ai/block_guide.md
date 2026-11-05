积木格式与实际语义（以本项目catalog/compile为准）

1. set_effect_blocks只提交{"schema":"ygodiy-blocks/0.3","effects":[效果块...]}。每块是{"block":"ID",标量字段...,"槽名":[子块...]}，不是type/params/children三层包装。标量和槽都平铺在块对象中。只有block必填；字段省略会补目录默认值，槽省略补[]。单块槽也必须写数组。最外层只收hat；不能提交card、setcodes、Lua或旧元数据。默认空槽不代表效果完整；动作cards、if.cond等缺失会导致编译提示，必须按返回补齐。
2. choice填实际值，不填中文标签；int填JSON整数；multi填用+连接的字符串，例如"dragon+spellcaster"、"spell+trap"、"hand+grave"。不要填数组或用逗号、|分隔。multi_parts会先认整个选项名；winged_beast、beast_warrior是原子值，不拆下划线。旧hand_grave仅当拆开后每段都是合法选项时兼容，不应生成新旧混写。
3. limit="name"用于①②时是这个卡名的①②各自每回合1次，编译器分配id、id+o等独立额度；不是合计1次。①②只能使用其中1个时两项都用name_shared，合用id。card是每张卡自己的次数，card_shared是该张卡的几个效果共享。limit_n=2表示2次。name_shared与name混用时编译器会为独立额度避开共享id，不自行编造额度编号。
4. pick是在动作求值时选卡：to_hand.cards=[pick(...)]直接选后加入手卡，pick没有as字段，不会自动成为下一动作的输入。需要重复使用同一组卡时，先select，其as="A"，source=[all(...)或pick(...)]，后续用var.name="A"。as不是card_uid。两个独立pick会重新选择。operated表示Duel.GetOperatedGroup，即紧接前一步实际处理成功的卡；后面动作会改写它，需要更久就先select记组。target引用发动时取的对象，this_card永远是这个效果的持有卡，event_cards是事件卡组；不能混用。materials_are检查这张卡召唤时使用的素材，不是检查这张卡是否成了别人的素材。
5. fusion_summon.mats="hf"是自己的手卡和怪兽区，不包含对方；hfg还包含自己的墓地，hfd还包含自己的卡组。其filter限制融合召唤出的怪兽，不是素材条件。融合怪兽本身的fusion_materials描述素材要求。不要把hf解释为双方场上，也不要额外写pick融合素材替代引擎的素材处理。
6. f_set.setcode是实际十六进制字符串；name只用于中文读回，编译器调用IsSetCard(setcode)，不会用name查编号或创造字段。0x0不是“自动按名字查找”。自制字段先由玩家在卡包setnames登记编号与名字，卡片自己的setcodes决定这张卡属于哪些字段；过滤别的卡不要求当前卡也属该字段。没有已知编号时才询问，不能猜0x0。已核实的官方「星辰」为0x1c9，用户未明确另设自制同名字段时直接使用，不重复询问是不是官方字段；自制「星光」假例为0xa01，不能照搬到其他系列。
7. 返回的reading是中文读回，warnings是编译/语义提示，compiled仅表示本地生成成功，不是沙盒验证。提交后直接检查这些返回值，无需再get_effect_blocks读取自己刚提交的树。没有警告且语义匹配就结束；有警告则针对返回路径修复。没有实际沙盒工具，不得声称实测通过。
8. 固定前缀已含所有已开放积木的字段类型、全部可选值和槽类型，先据此构造。确需多个积木的补充细节时，get_block_catalog的ids一次填完，不逐块往返；已查细节可复用。独立工具一次发多个tool_calls，依赖新UID的操作仍等返回。
9. f_name.code必须填已知的真实卡号；name只用于读回，code=0不会按名字查找。未知编号应查卡库或询问，不能猜。比较“与这张卡原本卡名相同”可用f_same_code(card=[this_card])，排除这些同名卡则f_not(filter=[f_same_code(card=[this_card])])，包含所有同名副本。f_not_self只排除效果持有卡这个实体。f_same_code比较双方原本卡名（IsOriginalCodeRule）；f_name比较指定卡号对应的现在卡名（IsCode），有改名效果时不能互换。

完整双效果树示例（字段编号示范，不是当前卡的资料；①②各限1次）：
{"schema":"ygodiy-blocks/0.3","effects":[{"block":"effect","type":"quick_o","range":"hand","limit":"name","condition":[{"block":"phase","phase":"main"}],"cost":[{"block":"discard","cards":[{"block":"this_card"}]}],"operation":[{"block":"fusion_summon","mats":"hf","filter":[{"block":"f_race","race":"dragon+spellcaster"}]}]},{"block":"effect","type":"trigger_o","event":"to_grave","range":"grave","limit":"name","condition":[{"block":"card_is","cards":[{"block":"this_card"}],"filter":[{"block":"f_reason","reason":"fusion"}]}],"operation":[{"block":"set_card","cards":[{"block":"pick","who":"you","where":"deck","count":1,"filter":[{"block":"f_set","setcode":"0x1c9","name":"星辰"},{"block":"f_kind","kind":"spell+trap"}]}]}]}]}

注意：示例②是当前目录可表达的“因融合素材送去墓地”近似组合。be_material本身对应EVENT_BE_MATERIAL，但目前没有素材种类/必须在墓地的直接参数；单体诱发的range不会自动生成墓地条件，不能靠range="grave"假装过滤。to_grave配this_card的f_reason=fusion能排除普通送墓，事件时点仍与官方EVENT_BE_MATERIAL不同；此缺口已记录，需要明确告诉玩家，不擅自添加不存在的参数。不要用exists(event_cards(f_reason fusion))把别的事件卡当成这张卡。

常见写法 → 现有积木组合（以下为组合提示，字段/槽名仍以完整目录为准）：

| 文本写法 | 组合 |
| --- | --- |
| 自己·对方主要阶段，丢弃手卡的这张卡 | effect.type=quick_o,range=hand；condition=[phase(main)]；cost=[discard(cards=[this_card])]；phase不另加turn就涵盖双方 |
| 自己主要阶段才能发动 | effect.type=ignition（默认自己主要阶段） |
| 每次某事件发生，不入连锁地适用处理 | effect.type=listener，event按实际事件、event_player按事件玩家、range按生效区域；编译为EFFECT_TYPE_CONTINUOUS，不是trigger_f，也不能靠改成永续属性帽替代事件处理；“每次”本身不等于不入连锁，须按原效果机制判断 |
| 这张卡召唤·特殊召唤的场合 | effect.type=trigger_o,event=summon+spsummon |
| 这张卡反转的场合，可以发动 | effect.type=trigger_o,event=flip；EVENT_FLIP包括反转召唤、被攻击翻开和效果翻开，可选择不发动；不是type=flip（现有反转效果帽） |
| 这张卡反转召唤的场合，可以发动 | effect.type=trigger_o,event=flip_summon；EVENT_FLIP_SUMMON_SUCCESS只含反转召唤，不含被攻击或效果翻开；写“召唤·反转”时合并summon+flip，不能缩成summon+flip_summon |
| 这张卡被送去墓地的场合 | effect.type=trigger_o,event=to_grave |
| 这张卡因融合素材送去墓地 | event=to_grave；condition=[card_is(cards=[this_card],filter=[f_reason(fusion)])]；官方素材事件存在上述缺口 |
| 从卡组盖放1张「X」魔陷 | set_card(cards=[pick(who=you,where=deck,count=1,filter=[f_set(真实编号,X),f_kind(spell+trap)])]) |
| 自己手卡·场上的怪兽作为融合素材 | fusion_summon(mats=hf)；filter限制召唤出的融合怪兽 |
| 融合召唤龙族·魔法师族融合怪兽 | fusion_summon(filter=[f_race(race=dragon+spellcaster)]) |
| 各自1回合1次 | 各effect.limit=name,limit_n=1 |
| ①②只能用其中1个 | 两个effect.limit=name_shared |
| 同一张卡1回合2次 | effect.limit=card,limit_n=2 |
| 从卡组检索1只4星以下战士族 | to_hand(cards=[pick(where=deck,count=1,filter=[f_level(op=<=,value=4),f_race(warrior),f_kind(monster)])]) |
| 选卡后依次作两项处理 | select(as=A,source=[all(...)])；后续两动作的cards均用var(name=A) |
| 以对方1只怪兽为对象 | effect.target=[take_target(as=T,count=1,source=[all(who=opp,where=mzone,filter=[f_kind(monster)])])]；处理引用target(name=T) |
| 这张卡以外的自己怪兽 | all(who=you,where=mzone,filter=[f_kind(monster),f_not_self]) |
| 原本卡名与这张卡不同的卡 | filter=[f_not(filter=[f_same_code(card=[this_card])])]；排除所有原本同名副本，不能换成f_not_self；若文字指定某个现在卡名，则用f_not(filter=[f_name(code=真实卡号,name=显示名)]) |
| 场上全部怪兽破坏 | destroy(cards=[all(who=both,where=mzone,filter=[f_kind(monster)])]) |
| 抽1张 | draw(player=you,count=1) |
| 从以下效果选择1个发动（发动时选，分支可以取对象） | effect.modes=[effect_mode(text="抽1张",operation=[...]),effect_mode(text="破坏对象",target=[take_target(...)],operation=[...])]；effect自己的target和operation留空；选项不满足时用effect_mode.cond |
| 从以下效果选择1个适用（处理时选） | operation=[choose(options=[option(text=...,body=[...])])] |
| 支付1000基本分 | cost=[pay_lp(amount=[num(value=1000)])]；amount是数值槽，不是标量 |
| 从手卡丢弃1张 | discard(cards=[pick(who=you,where=hand,count=1)]) |
| 特殊召唤墓地1只怪兽 | special_summon(cards=[pick(who=you,where=grave,count=1,filter=[f_kind(monster)])]) |
| 把这张卡除外作为代价 | cost=[banish(cards=[this_card])]；range按实际发动区域填写 |
| 直到回合结束攻击力上升500 | register(code=EFFECT_UPDATE_ATTACK,reset=end_of_turn,cards=[this_card],value=[num(value=500)]) |
| 不是某条件 | not_cond(item=[条件块]) |
| 两个条件同时满足 | all_of(items=[条件1,条件2])，不是在单块condition槽放两块 |
| 同时满足两项卡片条件 | filter数组并列，或f_all.filter=[条件1,条件2]；任一满足用f_any.items |
| 那之后再处理 | after(how=then,body=[后续动作])，跟在前一动作后；仅前一动作成功才继续，不能把它当独立首动作 |
| 这个效果实际破坏的卡数量 | count_of(cards=[operated])，紧跟破坏处理使用；再接math做乘法 |

本参考的样例是已执行沙盒情景与改坏对照的本地样例，不意味着模型新生成的卡也已经验证。
