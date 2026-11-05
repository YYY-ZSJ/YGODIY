# AI实测发现的积木缺口

## 2026-11-03：成为指定种类召唤素材并送去墓地

- 来源：用户对「星宿炮手 法魅那」的真实会话。文本为“这张卡成为融合召唤的素材送去墓地的场合”。
- 现状：`be_material`对应`EVENT_BE_MATERIAL`，没有素材种类参数，也没有针对这句的墓地条件与中文读回。`materials_are`检查当前卡召唤时使用的素材，不能用于判断当前卡成为别人的素材。
- 现有近似：`to_grave`加`card_is(cards=[this_card],filter=[f_reason(reason="fusion")])`可表达因融合素材送墓；比`exists(event_cards(f_reason fusion))`明确判断这张卡。事件仍是`EVENT_TO_GRAVE`，不可宣称与官方素材事件完全一致，中文读回也较拗口。
- 编译器事实：单体诱发的`range`不生成`SetRange`或墓地条件，因此不能单靠`be_material,range="grave"`表示“送去墓地”。
- 官方参考：[c1498449.lua](https://github.com/Fluorohydride/ygopro-scripts/blob/master/c1498449.lua)使用素材事件，并判断当前卡在墓地、事件原因是融合、排除`REASON_RETURN`。仅添加一个`IsReason(REASON_FUSION)`并不足以照搬这句全部语义。
- 本批处理：补全AI格式/语义文档、示例及明确警告；不改`catalog.py`、`compile.py`、`read.py`。原`check_proto`中文读法既有问题仍由用户另行安排。
- 后续建议：新增素材种类与去向的显式参数，保持旧树默认行为；分别覆盖融合、同调、超量、连接，含送墓/除外替代及原因返回边界。需独立告知用户、跑沙盒正反情景/变异、`check_proto`和三关后交付，不把超量素材默认当作送墓。
- 实测解释校正：最终A答复中声称“素材改为除外/回卡组时，官方②也会发动”，这不正确；原文本和官方脚本都要求送去/位于墓地，两种情况下都不发动。该答复保留并标注，不作为语义验收通过的依据。近似组合的实际差异是事件时点和原因边界，不能用这条错误解释替代测试。

## 2026-11-04：普通可选的反转事件（阿莱斯特②）

- 后续状态：用户第二轮验收后批准小扩展，现已开放`effect.type=trigger_o,event=flip`（EVENT_FLIP，单体可选诱发及场合延迟），读回“这张卡反转的场合”。现有`flip_summon`和反转帽不改，不迁移旧树；素材事件缺口仍未扩展。
- 修复证据：新增独立`blocks/proto_flip.py`的7个正反场景接入check_proto；专项另检出事件缩窄、可选改必发、错误特召时机3类变异。阿莱斯特原候选仅事件改为`summon+flip`后原8/8场景通过，为事后人工开发对照，不回填模型原成绩。验收见`../_tools/AI开发集小修验收.md`。
- 来源：第二轮7题实测，官方「召唤师 阿莱斯特」②为“这张卡召唤·反转的场合才能发动”，原参考脚本为`EVENT_SUMMON_SUCCESS`及`EVENT_FLIP`的单体可选诱发。
- 第二轮时普通`effect.type=trigger_o`的事件目录含`flip_summon`，没有`flip`。模型用`summon+flip_summon`只覆盖反转召唤，漏掉被攻击翻开；原8情景通过7个，战斗反转检索失败。
- 第二轮直接用`summon+flip`被当时校验明确拒绝。另一类型`effect.type=flip`编译成`EFFECT_TYPE_SINGLE+EFFECT_TYPE_FLIP`，本机MDPro3 Core将它作为必发反转处理，不能直接代替原卡可选诱发。
- 本地正反对照：反转帽能通过战斗翻开检索的正向；但同一“翻开后选择不发动”的诊断，官方Lua允许选择否、卡组/手卡断言通过，反转帽却自动入连锁检索，之后“否”无处应答。故不能只看正向通过就宣称等价。
- 证据：`_work/ai_eval_20261104/real_round2_1/failure_proofs.json`的`aleister_optional_flip_event_not_exposed`、`aleister_decline_official_control`、`aleister_decline_flip_hat`及`aleister_flip_hat_battle_positive`。诊断只在事后本地进行，未回传模型、不改原始成绩。
- 当时归类：正常开放积木缺少精确的普通可选反转事件入口；不以自定义Lua或近似时机冒充完成。模型未报告缺口，仍称与原文一致，该答复也不正确。
- 第二轮试跑批次只记日志，未改catalog/compile/read或系统提示词；扩展在后续小修批次实施。未来闭环的“发现旧缺口”验收必须使用修复前版本，不能被新事件掩盖。
