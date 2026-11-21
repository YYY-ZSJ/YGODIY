# 意图式沙盒测试（YGODIY_INTENT_TEST_V1）

积木编译不代表效果已验证。按原文编号逐个处理：为①写少量情景并run_sandbox_test(effect=1)，看日志修正后再处理②；不要一次输出整卡完整大计划。write_test_scenario每次只写一个情景，进度随候选/卡片保存，不必重复读取刚提交内容。read_card.test_progress给出已写ID与最低清单。未列出的边界、缺项、执行受阻或过期结果都写“未验证”。结论“已实现/与原文一致”必须列出实际通过的情景及覆盖范围，不能把最低清单当作规则完备证明。

write_test_scenario参数：{"scenario":{...},"card_uid":"可省略"}。scenario键：
- id：稳定唯一字符串；name：玩家看得懂的测试目的；effect：原文编号（无编号填1）；basis：原文连续片段。
- template：positive（结果）、same_name_only（只有被排除同名卡）、count_exceeded（次数越限）、condition_unmet（条件不符）、no_target、insufficient_cost、decline（不发动）、flip_summon、flip_battle、flip_effect、no_chain。
- parameters：负面模板可填availability:{card:"self",player:0,as:"activate"或"chain"}，程序自动添加不能发动断言；same_name_only填source:"deck/hand/grave/banished"、excluded:"self"或被排除引用、player:0，程序把对应区域设成只剩被排除卡。次数越限：布足代价，intents先合法发动到上限，程序断言不能再发动；其中1个/各能要分别覆盖跨效果共享/独立次数。
- lp 可选，例如 [4000,6500] 指定双方开局基本分，缺省为 [8000,8000]。
- 需要陪测卡真正发动、触发或提供永续效果时，可把 virtual_cards 的一项写成 {"official_code":83764718}。该引用从本机 MDPro3 官方卡库载入「死者苏生」及其脚本，在 field、intents、expect 中都使用同一引用名。可用 search_cards 按名称查到卡密后选择与局面有关的官方卡，不要求主测卡原文点名。验证其他卡时切勿用陪测效果代替主测效果。
- 自定义陪测效果使用 effects 数组，格式同工作台积木。例如 {"name":"灼热试纸","kind":"spell","effects":[{"block":"effect","type":"activate","operation":[{"block":"damage","player":"opp","amount":[{"block":"num","value":300}]}]}]}。将陪测卡放入手牌并用 activate 发动，再断言基本分或主测卡的连锁处理。怪兽同样可配置触发和永续积木。陪测积木只接受目录中的结构化效果。
- virtual_cards：按引用定义{name,kind:"monster/spell/trap",subtype:"怪兽 normal/effect/fusion；魔法 normal/continuous/quickplay/field/equip/ritual；陷阱 normal/continuous/counter",attribute:"dark/light/earth/water/fire/wind/divine",race:"warrior/spellcaster/dragon等目录键",level,atk,def,setcodes:["0xa01"]}；未填怪兽属性默认地、植物族、1星、0攻守。虚拟融合怪兽用 materials:["A","B"] 指定两至三个素材引用，允许同名。省略时，测试手续固定为两只非填充怪兽。融合怪兽须放 extra，素材放原文允许的区域。效果执行受阻时，先读 errors 和 current_question，按实际缺项改布场或 choose 再运行。同一情景反复运行不会补出素材。虚拟卡声明effect不会自动产生能力。同名副本用self，不自造另一个名字代替；真实整数卡号仅在原文明确点名/给卡号时使用。
- 辅助卡可用{name,helper:"send_to_grave",source:"hand/deck/mzone"}，或helper="revive/flip_faceup/destroy_monster"，均是固定普通魔法，不能提交Lua。
- field：{"0":{"hand":["self"],"mzone":["A",{"ref":"B","pos":"set","seq":1}],"deck":["C"]},"1":{...}}。区域 hand/deck/grave/banished/extra/mzone/szone/fzone/pzone。场地区每方一张，灵摆区每方两张（seq 为 0 或 1）。省略卡组部分补无字段通常怪兽；repeat用于多个同名实体，区域不超格。
- intents：按发生顺序写意图，不写select/yes/no。例{"do":"activate","card":"self","effect":1,"choose":["A","B"]}，程序按每次提问选对应卡，一次问A或分两次问A/B都可以，唯一候选自动处理不会卡在多余动作上。from可填来源区域，player默认0。分支option从1起；不发动用decline:true。choose只含希望选择的卡；未能兑现时看current_question及可选项，不猜提示顺序。
- 事件意图：do="summon/spsummon/mset/sset/reposition/attack/battle/main2/end_turn"；spsummon只表示引擎已有手续，任意复活用revive辅助卡。attack填card和target。翻开统一{"do":"flip","card":"self","method":"summon/battle/effect","effect":对应诱发编号,"by":"攻击者或翻面辅助卡引用","choose":["检索卡"]}；summon不用by，battle的by在对方场上，程序推进对方回合并攻击，effect的by是翻面辅助卡。程序自行接受该卡的诱发，decline:true则拒绝，不必预排yes/select。
- expect：结果检查数组，例如{"check":"count","player":0,"in":"hand","card":"A","eq":1}或{"check":"lp","player":1,"eq":7700}；比较只填eq/ge/le之一。可用count、lp、atk/def/level、faceup/disabled/overlay、drawn、event(name消息名、card可选)、offered(as=activate/chain等)。offered是明确的“是否提供发动机会”预期，不是发动动作。默认在稳定时点检查；不编造断言类型。no_chain自动加本卡chaining=0，还必须给实际处理结果。反转三模板必须有对应method的flip意图，并断言实际效果/不发动的结果，不能仅测表侧。

通用示例（非开发题答案）：
{"id":"damage_once","name":"造成300伤害","effect":1,"basis":"给与对方300伤害","template":"positive","virtual_cards":{},"field":{"0":{"hand":["self"]}},"intents":[{"do":"activate","card":"self"}],"expect":[{"check":"lp","player":1,"eq":7700}]}

run_sandbox_test参数{"effect":1,"card_uid":"可省略","scenario_id":"可省略仅运行此情景"}。结果status=通过才有证据；执行受阻返回当前提问、可选项、unreached_assertions和recent_log，允许只修布场/意图，原文要求和预期不动。真正执行失败后修积木或新增更强情景；改已有失败反例的布场/意图/预期需要玩家确认，不能借换局面避错。工具不能删除情景。积木表达不了就说明缺口及失败证据，不改原文迎合当前实现。修改积木/效果/数值后旧结果自动过期，要对新版本重测。
