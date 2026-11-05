# Effect Model（效果模型）

> **2026-10-29：全面换成 v0.2**（结构见 [docs/v0.2-骨架设计.md](docs/v0.2-骨架设计.md) 第 1、2 节）。中文文本、Lua 生成、
> DIY 工作台都直接读写 v0.2；样例（`samples/`）是 v0.2，升级前的 15 张 v0.1 原件留在 `samples/v01/`。
> v0.1 的数据（旧的工作台存档、`ygopack/demo` 的示例）读入时由 `model/upgrade.py` 自动升级，生成的 Lua 与升级前逐字一致。
> 下文「结构（schema `ygodiy-effect/0.1`）」一节保留作对照，新写法以设计文档为准。

Effect Model 是一张卡「效果」的结构化描述（JSON）。积木 / 填空编辑器编辑的就是它；
从它**同时**生成两样东西：

- **ygopro Lua 脚本**：导出卡包后能在 MDPro3 / ygopro2 里打，以后也是 YGODIY 测试沙盒、对 AI 用的脚本；
- **规范的简体中文效果文本**：写进卡面，再交给翻译（或以后直接生成日文 / 英文）。

两样东西出自同一份数据，所以「卡面写的」和「实际做的」不会对不上——这是手写 Lua 的 DIY 卡最常见的毛病。

```
积木编辑器 ──编辑──▶ Effect Model (JSON) ──┬─▶ lua.py  ──▶ cXXXX.lua + cdb 提示文字
                                          └─▶ zh.py   ──▶ 卡面效果文本 ──▶ 日 / 英
```

## 现状（2026-10-29）

46 张样例：15 张代表卡，调研压力卡里挑出的 26 张（替罪羊、神之通告、时间魔术师、闭锁世界的冥神、
电子龙·无限、封印之黄金柜、终焉的倒计时……各自压测的难点见设计文档第 4 节），以及任务 7 第一批的 5 张
（休战增援的自肃；隼骑士、枪兵龙人、暗黑共鸣者、朱罗纪单脊龙的永续效果）：

| 检查 | 结果 |
| --- | --- |
| 生成的中文文本与百鸽官方文本**逐字一致** | 42 / 46；另 4 张是已知的旧译法 / 旧式卡文差异（`check_text.py` 里逐条注明），其他不同 0 |
| 生成的 Lua 在 MDPro3 自带的 `ocgcore.dll` 里加载、注册效果、做发动检查，无 Lua 错误 | 46 / 46 |
| **情景测试**：在测试沙盒（`sandbox/`）里跑完整对局——发动、连锁、选对象、效果处理、诱发、跨回合——再检查场面 | 91 个情景，**生成脚本 91 / 91**；官方脚本 89 / 91（鹰身女郎1 的两条，见「已知差异」） |
| **变异测试**：把生成的脚本故意改坏一处（雷击破坏自己的怪兽、卡斯帕不检查纵列、终焉的倒计时提前一回合胜利……），情景应能发现 | 54 / 54 全部检出 |
| DIY 测试卡（官方卡里能完整表达的太少的写法）：多次额度、自肃（两批）、永续第一批、工作台第二批（放宽的写法、可选处理、引用前一步、魔陷种类、处理的后果），文字 + 沙盒 + 改坏一处的对照 | 5 + 20 + 19 + 23 项全部通过 |
| 需要逃生口（自定义 Lua）的卡 | 1 / 46（无限泡影的「同一纵列」部分） |

```
python -m effect_model.devtools.check_text            # 文本对照
python -m effect_model.devtools.ocgprobe              # 冒烟测试（需要 D:\Game\MDPro3）
python -m effect_model.devtools.run_scenarios [-v]    # 情景测试：官方脚本、生成脚本各跑一次
python -m effect_model.devtools.run_scenarios --mutate  # 变异测试
python -m effect_model.devtools.lint_examples         # 结构检查（含 v0.2 压力卡样例）
python -m effect_model.devtools.check_limits          # 多次额度：文字照官方多次写法，沙盒里正好能用 n 次
python -m effect_model.devtools.check_restrict        # 自肃（两批）：DIY 测试卡的文字与沙盒行为
python -m effect_model.devtools.check_cont            # 永续第一批：DIY 测试卡的文字与沙盒行为
python -m effect_model.devtools.check_acts            # 工作台第二批：放宽了的处理写法、DIY 衍生物
```

情景放在 `scenarios/`，每张卡一个文件，正向（效果确实做到了）和反向（条件不满足时确实不能发动、不会诱发）都有，
比如：灰流丽对「雷击」不能发动、一回合只能用一次；三眼怪从手卡送墓不诱发；增殖的G 连锁中和连锁外的特召各抽 1 张、
自己特召不抽；墓穴的指名者的无效持续到下个回合结束、再下个回合解除；光之护封剑在对方第 3 个结束阶段破坏；
霍普两次取除素材无效攻击、没素材时被选为攻击对象自我破坏；暗道化师 彼得作为上级召唤的祭品送墓时错过时点；
卡斯帕只对相同纵列的发动检索；封印之黄金柜在第 2 次准备阶段才回手；终焉的倒计时在第 20 回合结束时胜利。
情景格式见 `sandbox/scenario.py` 开头。

两项冒烟检查都带故意写坏的对照脚本，变异测试则证明情景本身「有牙齿」——它第一次运行时就揪出了情景运行器的一个毛病
（召唤会带来两个连锁时点，「能否连锁」的检查只看了第一个），已经修正。

## 几个关键决定

### 1. Lua 方言：萌卡 / Fluorohydride（MDPro3、ygopro2 用的那套），不是 Project Ignis

已确认的路线是「DIY 卡先导出成标准 ygopro 卡包，在 ygopro2 / MDPro3 里打」。这两个客户端用的是
Fluorohydride / 萌卡这一系的 ygopro-core 和 ygopro-scripts（`aux.AddXyzProcedure`、`local s,id,o=GetID()`），
本机 `D:\Game\MDPro3\Data\script.zip` 里就是这一套（13539 个文件）。Project Ignis（EDOPro）的脚本 API 不同
（`Xyz.AddProcedure` 等），它的脚本在 MDPro3 里跑不起来。

所以 Lua 后端先只做萌卡方言；以后 YGODIY 自己的沙盒 / 对 AI 也应该 fork **同一个** ygopro-core，
这样同一份 Lua 在导出的卡包和 YGODIY 里行为一致。模型本身不依赖方言，将来要出 EDOPro 版只需再写一个后端。
（2026-10-22 已与用户确认，取代此前「同步 Project Ignis」的设想；内核与脚本的许可证还需要核实。）

### 2. 模型描述「规则文字」，不描述引擎 API

模型里只有玩家看得懂的概念：「对象」「代价」「那之后」「这个回合」「这个卡名的效果1回合只能使用1次」。
引擎上的惯用法全部由生成器负责，制卡的人不需要知道，也不会写错：

- 效果分类（`CATEGORY_*`）从动作推出——灰流丽、屋敷童能不能对它发动全靠这个，手写最容易漏；
- 取对象的效果处理时检查 `IsRelateToEffect`，从墓地特召 / 加入手卡套 `NecroValleyFilter`；
- 从卡组检索后 `ConfirmCards` 给对方看；
- 「每次对方把怪兽特殊召唤，自己抽1张」在连锁处理中发生时要等连锁结束后合并抽卡（增殖的G 的三段写法）；
- 可选诱发「……的场合才能发动」加 `EFFECT_FLAG_DELAY`，「……时」不加；
- 卡名一回合一次的计数代码按 `id`、`id+o`、`id+o*2` 分配，特殊召唤手续用誓约次数。

### 3. 封闭词汇表 + 逃生口

每个动作 / 事件 / 条件都是词汇表里的一项，对应一段验证过的 Lua 和一套中文措辞。词汇表外的东西用 `raw`
（同时写 `lua` 和 `zh`），检查时会给出警告；整张卡也可以完全手写 Lua（留给高手的槽位，尚未实现）。

## 结构（schema `ygodiy-effect/0.1`）

```jsonc
{
  "schema": "ygodiy-effect/0.1",
  "card": {"code": 14558127, "name": "灰流丽", "kind": "monster", "subtypes": ["effect", "tuner"]},
  "summon": null,                       // 召唤手续：xyz / synchro / link / pendulum
  "effects": [ /* 效果，按卡面顺序 */ ]
}
```

卡的攻守、种族等资料仍由制卡器的卡片数据负责，这里只放写效果需要的最少信息。

### 效果

```jsonc
{
  "id": "negate",          // 可省略（默认 e1、e2…），给别的效果引用：「这张卡的①的效果适用的回合」
  "type": "quick",         // activate 魔陷发动 | ignition 起动 | quick 诱发即时 | trigger 诱发
                           // continuous 永续 | summon_rule 特殊召唤手续 | rule 不编号的规则文字
  "box": "monster",        // monster | pendulum（灵摆效果栏，编号各自从①开始）
  "from": ["hand"],        // 在哪里发动 / 适用；多数情况可省略，按卡种推断
  "on": { ... },           // 事件：什么时候（诱发、对发动的回应、攻击宣言时……）
  "optional": true,        // 诱发效果：「才能发动」还是「发动」
  "timing": "if",          // 可省略：if「……的场合」/ when「……时」，按事件推断
  "condition": [ ... ],    // 条件
  "cost": [ ... ],         // 代价（「把这张卡从手卡丢弃」）
  "target": [ ... ],       // 对象（「以对方场上1只表侧表示怪兽为对象」），每个带 "as" 名字
  "do": [ ... ],           // 效果处理，按顺序，用连接词串起来
  "limit": {"scope": "name"}  // 次数限制：name 这个卡名 / card 这张卡；kind: activate 表示誓约；group 共享次数
}
```

编号（①②）、「这个卡名的②③的效果1回合各能使用1次。」这一行、素材行（「4星怪兽×2」）都由生成器算出来。

### 选择器（指一张或一组卡）

```jsonc
{"ref": "self"}                         // 这张卡
{"ref": "t"}                            // 对象 t（那只怪兽）
{"ref": "chain"}                        // 正在回应的那个发动
{"ref": "x"}                            // 前面某一步用 "as": "x" 绑定的结果（这个效果除外的怪兽）
{"who": "opp", "where": ["mzone"], "filter": [{"position": "attack"}], "count": "all"}
{"who": "you", "where": ["deck"], "filter": [{"card_type": "monster"}, {"atk": ["<=", 1500]}], "count": 1}
```

`who`：you / opp / both；`where`：hand、mzone、szone、field、pzone、grave、deck、banished、extra、linked（这张卡所连接区）。
过滤条件：`card_type`、`subtype`、`atk` / `def` / `level`（比较）、`race`、`attribute`、`set` + `setcode`（字段）、
`position`、`name`，以及逃生口 `{"lua": "$c:IsXxx()", "zh": "……的"}`。中文名词短语按官方语序拼：
表示形式 → 数值 → 种族·属性 → 字段 → 卡种（「1只攻击力1500以下的灵摆怪兽」「1张「罪宝」魔法·陷阱卡」）。

### 步骤与连接词

```jsonc
{"act": "destroy", "what": {"ref": "self"}},
{"act": "add_to_hand", "link": "then", "what": { ... }}   // 「这张卡破坏，从卡组把……加入手卡」
```

| link | 中文 | 语义（Lua） |
| --- | --- | --- |
| `then` | 「，」 | 前一步做成了才做（`if 前一步>0 then`） |
| `after` | 「。那之后，」 | 同上，且不同时处理（`Duel.BreakEffect()`） |
| `and` | 「并」 | 同时处理（「那个发动无效并破坏」） |
| `also`（默认） | 「。」另起一句 | 彼此独立；但如果引用了前一步绑定的结果（「这个效果除外的怪兽」），前一步没做成就不适用 |

步骤还可以带 `if`（「盖放的这张卡发动的场合，再……」）和 `when_exists`（「……存在的场合，那些全部……」，不影响能否发动）。

PSCT 的这些区别正是 DIY 文本最容易写含糊的地方；模型要求作者明确选一个，文本和行为就都确定了。

### 当前词汇表（v0.2，两个生成器都已支持）

词汇键 = 调研构件 id 去掉大类前缀（`act.destroy` → `destroy`），对照表见 `docs/v0.2-词汇对照.csv`。

- **动作**：destroy、banish（含里侧、由对方选、宣言的卡名）、send_to_gy、add_to_hand、special_summon（含同名两只）、
  set_spell_trap、change_position、draw（含双方各自）、discard、return_to_extra、swap_control、attach_xyz_material、
  create_token、perform_summon（仪式）、activate_from_deck、copy_effect、damage、add_counter、toss_coin、win_duel、
  negate_activation / negate_effect / negate_attack / negate_summon / negate_card_effects、apply_continuous、
  schedule_operation（预约：第 N 次准备阶段、第 N 回合结束时……），以及模型自己的 select、branch、one_of、raw。
  代价另有 release、detach_xyz_material、pay_lp、remove_counter。
- **事件**：normal / special / flip_summon_success、sent_to_gy（可限定被破坏）、attack_declared、becomes_attack_target、
  phase_window、phase_end、effect_activated（可限定：谁发动、哪种卡、包含哪类效果、以什么为对象、相同纵列）、summon_attempt；
  每个效果显式写 `timing`：when「……时」/ if「……的场合」。
- **条件**：card_count、own_turn / opponent_turn、material_possession、named_card_used、self_location、value_compare、
  battle_participant、summon_history、raw。
- **持续适用**：atk_update / atk_set、def_update、change_level、indestructible_battle / indestructible_effect /
  indestructible_count、cannot_be_targeted、piercing、direct_attack / cannot_direct_attack、extra_attack、attack_all、
  cannot_be_attack_target、attack_target_restriction、cannot_attack、cannot_activate、effects_disabled、immune_effect、
  redirect_destination、battle_damage_change / battle_damage_zero、cannot_special_summon、cannot_change_position、
  cannot_release、skip_phase、trap_from_hand / quickplay_opponent_hand、「每次……，……」（on + do）。
  几条一起适用写成列表，官方并成一句的照样并（「攻击力·守备力上升」「不会被战斗·效果破坏」）。
- **自肃**（效果上的 `restrict`）：整回合 / 处理后；限制特殊召唤、召唤、通常召唤、战斗阶段、这张卡攻击 / 直接攻击；
  可限「从额外卡组」「不是X怪兽」「这张卡的效果以外」，期限到回合结束或下次的自己回合结束（设计文档 2.4）。
- **次数**：`limits` 里的额度（这张卡 / 这个卡名 / 表侧表示存在期间，按使用 / 卡的发动 / 手续计），效果用 id 引用；
  次数 `n` 默认 1，可以多次（「1回合最多2次」「1回合可以使用最多2次」，见设计文档 2.4）；誓约放 `restrict`。
- **出场规则**：xyz（含重叠超量）、synchro（含素材限定）、link（含用对方怪兽作素材）、fusion（含接触融合）、pendulum；
  编号的特殊召唤手续是 `type: "procedure"` 的效果，不编号的（接触融合、等级差送墓）放 `summon.procedures`；
  规则同名 `card.rule_names`（导出时写成不会被无效的改名效果，见「已知差异」）。

## 最初 15 张样例各自压测什么

（26 张压力卡各自压测什么见设计文档第 4 节。）

| 卡 | 压测点 |
| --- | --- |
| 雷击 | 最简单的魔法：全部破坏、能否发动的检查 |
| 死者苏生 | 取对象（双方墓地）、在自己场上特召、王家长眠之谷 |
| 神圣防护罩 -反射镜力- | 陷阱、攻击宣言时发动 |
| 三眼怪 | 强制诱发、「从场上」送墓、检索、绑定结果 + 同名卡不能发动 |
| 电子龙 | 特殊召唤手续、「只有对方场上才有怪兽存在」 |
| 灰流丽 | 手卡诱发即时、丢弃代价、对「包含某类效果的发动」回应、●列表 |
| 增殖的G | 从手卡送墓代价、「这个回合中，以下效果适用」、连锁中特召的合并抽卡 |
| 墓穴的指名者 | 取对象除外、引用「这个效果除外的怪兽」、持续到下个回合结束、原本卡名 |
| 无限泡影 | 陷阱从手卡发动的条件、效果无效直到回合结束、**逃生口**（同纵列） |
| 光之护封剑 | 留在场上 + 回合计数、「作为这张卡的发动时的效果处理」、永续限制 |
| No.39 希望皇 霍普 | 超量手续、取除素材代价、无效攻击、「没有超量素材的状态」 |
| 解码语者 | 连接手续、「×连接区怪兽数」、以自己场上的卡为对象的发动、解放连接区怪兽代价 |
| 星尘龙 | 同调手续、解放自身代价、「①的效果适用的回合」跨效果引用、墓地诱发 |
| 异色眼灵摆龙 | 灵摆效果栏、可选的伤害变 0、「这张卡破坏，从卡组……」、伤害 2 倍 |
| 黑魔女 迪亚贝尔斯塔尔 | 带代价的召唤手续 + 誓约次数、召唤·特殊召唤诱发、对方回合送墓诱发、三段次数限制 |

## 已知差异（与官方脚本 / 文本比较）

- 星尘龙②：v0.1 只能写「这张卡特殊召唤」；v0.2 有了跨效果绑定（「为那个效果发动而解放的这张卡」），样例已改成官方写法。
- 鹰身女郎1：官方卡库用 alias 表示「卡名当作「鹰身女郎」使用」，MDPro3 自带的引擎见到 alias 就改去加载 alias 那张卡的脚本，
  所以**官方**脚本在沙盒（以及 MDPro3 的本地对局）里跑不起来。导出的卡包 alias 一律写 0，生成器把规则同名写成
  在所有区域适用、不会被无效的改名效果（`EFFECT_CHANGE_CODE`）；情景测试证明它在卡组里也当作「鹰身女郎」。
- 星尘龙①：官方条件还排除了「回应的是让魔陷发动无效的效果」这种连锁，模型里没有这一条。
- 解码语者②：官方代价排除了已被战斗破坏确定的怪兽（`STATUS_BATTLE_DESTROYED`），生成的没有。
- 光之护封剑②：官方加了「这张卡仍是魔法卡」的条件，生成的没有。
- 无限泡影：官方把同纵列无效写在「对象怪兽效果无效」的分支**里面**，模型写成另起一句（对象不在时是否仍适用，需要对照裁定再定）。
- 生成的脚本统一用 `local s,id,o=GetID()` 写法，函数名是 `s.target1` 之类，和官方的命名不同，不影响行为。

这些都属于「词汇表还不够细」，不是结构问题：给对应的事件 / 代价加一个选项即可。

情景测试里官方脚本与生成脚本行为一致，说明上面几条在这些情景下不影响结果；它们属于情景还没覆盖到的边角（例如解码语者在伤害步骤被战斗破坏确定后的代价）。

## 下一步

1. ~~测试沙盒~~：已完成第一版（`sandbox/`），情景与变异测试见上。以后每加一个词汇项，都配一个情景和一个变异。
2. ~~v0.2 骨架~~：2026-10-29 完成（模型、中文、Lua、工作台）；下一步是设计文档第 8 节的「全卡库回归」。
3. **按 DIY 常用度扩充词汇**。官方卡文本里各动作出现的卡数：特殊召唤 7157、破坏 5085、送去墓地 3428、除外 3083、
   加入手卡 2557、伤害 2167、攻守升降 1248、装备 850、不会被破坏 833、超量素材 818、效果无效 774、回到卡组 762、
   抽卡 745、盖放 611、回到手卡 601、融合召唤 539……先补回到手卡 / 卡组、伤害 / 回复、攻守变化、抗性、融合。
4. **日文 / 英文直接从模型生成**：文本既然从结构生成，日文 PSCT（「～を対象として発動できる。」）和英文 PSCT
   也可以用同一套模板生成，比把中文再翻译一遍更准；翻译模型留给 `raw` 和自由文本。
5. ~~积木 / 填空编辑器~~：「DIY 工作台」模式（`diy_workbench/`），直接编辑 v0.2。
6. ~~导出卡包~~：`ygopack/`，cards.cdb（含 str1..str16 提示文字）+ `script/cXXXX.lua` + 卡图，导出前在沙盒里验证。

## 文件

| 文件 | 内容 |
| --- | --- |
| `model/` | v0.2 的结构：`vocab` 结构常量、`upgrade` v0.1 升级、`normalize` 补默认值（编号、id、发动位置）、`lint` 语义检查、`patterns` 两个后端共用的固定写法识别 |
| `zh.py` | 中文效果文本 |
| `names.py` | 卡号 → 卡名（离线卡库，工作台可以登记包里的 DIY 卡名） |
| `lua/` | 萌卡方言 Lua：`gen` 整张卡与过滤函数、`effect` 一个效果、`acts` 动作、`cont` 持续适用、`summon` 出场规则；`generate()` 同时返回 cdb 用的提示文字 |
| `samples/` | 41 张 v0.2 样例；`samples/v01/` 是升级前的 15 张 v0.1 原件 |
| `scenarios/` | 样例卡的情景测试（84 个） |
| `devtools/check_text.py` | 与离线卡库官方文本逐字对照 |
| `devtools/ocgprobe.py` | 冒烟测试：生成的 Lua 能加载、注册、做发动检查 |
| `devtools/run_scenarios.py` | 情景测试（官方 / 生成脚本对照）与变异测试 |
| `devtools/check_limits.py` | 多次额度：DIY 测试卡的文字与沙盒行为（能用 n 次、第 n+1 次不行） |
| `devtools/check_restrict.py`、`devtools/check_cont.py` | 自肃与永续第一批：DIY 测试卡的文字、沙盒行为与改坏一处的对照 |
| `devtools/check_acts.py` | 工作台第二批：放宽了的处理写法（自己选N张丢弃、处理中给对象加攻击力、攻击力变成、不受其他卡影响……）与 DIY 衍生物 |
| `devtools/lint_examples.py` | 结构检查：41 张样例、15 张 v0.1 原件与 27 张设计用压力卡样例无错误，lint 能查出故意改坏的地方 |
| `docs/v0.2-骨架设计.md` | v0.2 骨架设计（按调研的易错规则与压力卡难点重定结构），附 27 张压力卡样例 `docs/v0.2-压力卡样例.json`、514 项调研构件的对照 `docs/v0.2-词汇对照.csv` |
| `research/` | 调研数据：514 项构件清单、244 条规则、82 条文本规则、裁定、脚本构件频率、100 张压力卡（来源见其 README） |
