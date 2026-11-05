# 全局 AI 设计助手 · 第2步最小沙盒闭环

入口：主窗口模式下拉旁的「AI 助手」。原生 QDockWidget 可停靠、收起或浮动，首次展开才加载服务 Key 和控制器。
当前开放聊天、读取/浏览、新建复制、字段与积木批次修改，以及意图式测试情景与沙盒。基础资料保持共用，预览列出会同时影响的模式；原有保存缺口按编辑器会话处理。
按第一版收尾路线实施第2步，离线检查已完成，AI自主发现错误的真实验证另待本批批准。通用删除、导出、安装、文件覆盖工具留在第3步，未开始实施。
包仍放在 diy_workbench/ai，沿用已有协议、配置和会话模块，避免为全局化搬动无关代码。

## 使用

1. 点顶部设置图标，选择服务商预设，填自己的 Key。点开模型下拉时，后台请求所选地址的 /models；保留手填内容。
2. 按实际服务修改 base_url。支持 OpenAI 兼容 Chat Completions 和 Claude Messages，没有 Responses 接口。
3. 「测试连接与工具调用」请求模型调用一个无副作用的检查工具，并严格校验返回参数；使用默认工具选择，兼容不接受强制 tool_choice 的思考模式，不能仅凭聊天成功判断支持工具。
4. 首次向某个接口类型和地址发请求前，需要确认隐私提示。卡片文字和对话会发送，卡图不发送。
5. 默认 Enter 发送、Shift+Enter 换行，可在设置里改成 Ctrl+Enter 发送。生成时框内按钮变为停止。
6. 顶部仅保留完整模型名、余额、新对话/历史/设置图标；点模型切换服务。过长的模型名在按钮内换行，不截断，也不撑宽面板。
7. 对话独立于卡片；切卡、切模式和收起面板不会取消聊天。输入上方默认附带当前卡，点 × 后持续不附带，可点“附带当前卡”恢复。发送时冻结附件，只含该卡当前模式的资料。生成中可切换会话，回复仍归发起会话；删除正在生成的会话会协作取消。
8. 输入区“自动应用”小开关默认关闭，新对话关闭；开启高亮显示“自动应用中”。默认生成候选，完成后点“完整预览”检查，再应用整批；自动模式直接生效，仍可整批撤销。
9. 输入区“批次”可跨卡查看本次启动内的修改记录。若源卡被删除或已新建对话，仍可在这里找到批次；保存的历史只保留审计预览，不能跨重启应用/撤销。
10. 历史图标打开独立会话列表，可新建、改名、置顶、全文搜索、确认删除及导出 Markdown。修改记录中的卡名可跳转到目标卡片；删会话不删卡片和本次启动内的修改批次。
11. 输入框下方依次显示会话轮数/工具步数/最近输出速度、累计词元及缓存命中率、上下文圆环百分比；每项均可点击展开浮层。上下文超过70%黄、90%红，容量显示1M/128K等单位；底栏窄时优先保留命中百分比，完整数字在悬停与浮层。
12. 词元浮层查看累计用量、缓存命中率、分档费用及每次HTTP请求。数字可在每四位分组和“万”之间切换，悬停/底栏/会话列表同步。服务未返回的统计明确未知，费用均为约计、币种分别累计。上下文浮层按系统提示、工具定义、消息（含摘要）列出估算，并提供压缩/原文入口；容量仍优先模型信息，内置表兜底，允许高级手填。
13. “压缩对话”使用当前模型总结较早的完整轮次，原文保留在本地；摘要/原文窗口按选中消息展开。发送和工具往返前超限会自动压缩，失败则停止发送并保留原文。采用晚压缩、一次压大段，避免每轮小压缩。
14. 工具默认每次最多60次，可在高级修改或选“不限制”，没有额外的6轮限制。达到上限在回复下方显示一次提示及“继续”；续接同一回复与批次，已执行操作不重做，不增加用户轮次，仍保护暂停后的手改。继续使用本次启动内快照，重启不开放旧批次的应用/撤销；原文与协议进度保留。新发要求会结束此前续接。

接口类型、输出上限和超时放在默认收起的「高级」，收起后窗口自动缩小。预设自动填写协议；输出默认“不限制”：OpenAI 兼容请求省略 max_tokens；Claude 在后台查询 Models API 的 max_tokens。
无法获取 Claude 上限时明确提示，不猜默认值；可在高级中手填经服务商确认的上限。不限制不改变服务商自身模型上限。

### 请求健壮性（2026-11-04）

- 「单次请求时限」默认600秒，可设30～7200秒；每次HTTP发送及重试独立计时。工具执行、重试等待和多段压缩不共用整轮截止时间，没有隐藏的180秒任务上限。
- 「网络读取超时」是连续无数据的等待时间，默认120秒，可设5～600秒。旧配置原默认30秒已迁移；其他手填值及新版再次设置的30秒保留。心跳也会检查取消和截止时间，阻塞读取在有数据或读取超时时退出。
- 请求超时保留部分显示内容及已完成工具的协议历史，回复下方显示一次提示和「继续」。继续沿用原批次，重发未完成的HTTP，不重做已完成操作；未完成的工具片段不执行。手动压缩对话也可暂停续接。
- 无法解析或顶层不是对象的工具参数返回结构化错误（`error_code/path/expected/received`），交给模型修正；调用记录保留错误，不执行该操作，同批其他正常调用可继续。连续3次同类参数错误停止；工具编号无效/重复仍按协议错误终止。
- 429/503支持`Retry-After`秒数和HTTP日期，等待最多60秒，可随时停止；无有效头时沿用有限退避，最多重试2次。402及可识别的余额/付费额度不足错误明确提示且不重试。始终使用玩家所选服务和模型，不自动切换。
- 可选「单次任务费用上限」默认关闭，按当前模型的计价币种与单价累计，包含压缩请求。它在请求之间检查，**单次响应仍可能越过上限**，不会偷偷改写“不限制”的输出参数；并非服务商硬扣费限额。
- 达到费用上限会暂停并保留待执行响应，提示「继续」会再增加一份设置的额度，历史费用保留累计。暂停期间修改或启用额度，以新金额作为续做额度；未知单价先暂停，输入输出齐全但缓存明细缺失时按最高输入档保守估算，整体用量未知时需检查记录并关闭上限后才继续，不能当作0费用。

离线测试：`./_tools/run.ps1 ai_robustness_unit.py <报告.json>`（继承阶段1～2和文档循环测试）；`./_tools/run.ps1 ai_robustness_ui.py <输出目录>`（真实主窗口，mock）。完整积木回归可用`./_tools/run.ps1 ai_docs_samples.py <报告.json> --all`，样例写入临时目录，原有失败照实返回。
旧版配置中默认的 4096 自动升级为不限制，其他显式设置保留。配置版本升级为 2。

聊天使用微软雅黑等无衬线字体、左右气泡和原生 QTextDocument Markdown，围栏代码使用独立等宽文本框及复制按钮。
状态和错误在消息外显示，失败可重试；调用过程卡片随文字高度变化。气泡随面板宽度调整，最大约 85%，标题最多增大 2px，其他级别与正文同号加粗。
聊天外层提供主竖向滚动；代码和调用记录按内容增高，思考块内部使用有界滚动视口。自动跟随底部，上翻暂停跟随。无 QtWebEngine、新依赖或网页登录。
思考内容在正文上方默认折叠，流式显示“思考中…”，结束显示累计阶段用时，可随时展开。思考正文不混入回答，独立保存在消息的reasoning_parts中；停止保留已收到部分，重启不再显示仍在思考。可明确关联到旧回复的wire思考也能回看，旧用时显示“未记录”；更换过协议或不能对应时不猜测关联。服务返回reasoning_tokens时单列“其中思考”，已经计入输出，不重复相加或计费。
流式以 80ms 合并刷新，期间增量追加纯文本，完成后完整渲染 Markdown。只为可见区及上下缓冲区创建消息气泡，最早历史也可到达。
会话保存使用 1 秒防抖，消息结束保存，长请求每 5 秒检查点；不再逐片段保存卡包。设置、模型缓存、布局、会话和大 JSON 编码均在后台队列。

请求在 QThread 中执行，复用已有 requests，无新依赖、无 QtNetwork、无请求子进程。
连接超时8秒、读取超时默认120秒、单次HTTP默认600秒；每个SSE行检查取消和当前HTTP截止时间，没有整轮180秒限制。
阻塞中的读取不能靠取消标志立即中断，会在收到数据或读取超时后退出。退出主窗口时先协作取消，线程结束后再关闭；不使用 QThread.terminate。
只有尚未收到响应内容、工具或用量时的连接错误及部分临时 HTTP 错误会有限重试，最多两次。

## 当前操作与线程边界

统一目录定义名称、参数 schema、风险、支持模式和处理函数，生成两协议的模型工具。应用侧再次校验类型、枚举和未开放参数。

| 读取 | 浏览（直接执行并记录） |
| --- | --- |
| get_context、list_modes、describe_fields、list_packs、list_cards、read_card、search_cards | switch_mode、select_card、open_page |

修改目录：set_card_fields、set_effect_blocks、new_card、copy_card、new_pack、copy_pack、write_test_scenario、run_sandbox_test。补充读取：get_effect_blocks、get_block_catalog。
set_card_fields 明确 mode，以 describe_fields 的实时字段类型/选项为准。list_packs 的 pack_id 是本次启动的内存标识，不改变存档。
同一请求中的多次修改形成一个批次；默认目标固定为发起卡，只有 AI 显式 select_card 改变它，玩家手动切卡不会把旧请求套到新卡。

请求和 SSE 在 QThread；操作经信号交给主线程执行，不模拟鼠标键盘。待执行操作有有效期，停止、超时、退出或原卡被删除后不再执行。
工具次数默认60，0为不限；用量合计各轮服务返回值。多工具响应可在批次中途暂停并续接剩余调用。相同工具相同参数连续第3次前拦截；同一错误连续返回3次也停止并显示具体原因，相同字段的不同错误值不绕过检测。不限制不关闭循环检测、单次HTTP超时或权限边界。删除、导出、安装每次都由玩家在弹窗确认（risky_actions.py），伪造 approved 或提交应用工具不能放行。

## 意图式测试

新对话启用两个测试工具，旧对话保留原始前缀与工具集合。AI按效果编号逐个写入、运行：只给布场、发动/翻开、对象选择和预期，程序应答实际提问，不需要枚举底层select。格式见[test_guide.md](test_guide.md)。虚拟卡由属性描述生成；辅助设施仅有固定的送墓、复活、翻面、破坏四种，不接受模型Lua。

程序从原文生成最低反向清单，缺项、未达断言、失败及过期均为未验证。每个情景的结果和原文依据在消息下展示，完整情景/日志默认折叠。情景、结果保存在卡片的`diy.tests`，不绑定会话；仍走候选、应用、手改冲突检测及整批撤销。

未达断言时可修布场/意图，已有要求和预期不能静默改动。实际断言失败后，只有追加更强断言或修积木可直接生成候选；改弱原反例须玩家单独确认，默认拒绝。工具没有删除情景入口。修改卡片后旧结果自动过期，不能用新增的弱情景盖过旧失败。最低清单通过也不等于所有规则已验证。

网络仍在QThread；本地原生Core在可终止子进程，绝不传入Key。每次复制引擎、脚本和卡库到临时目录，逐情景启动，单情景25秒，可取消；异常、无效返回或崩溃留下结果后继续其他情景。启动及纯pyc加载已离线验证，完整安装包仍留第5步验通。

每次聊天HTTP发送前，先后台保存会话，再在网络线程原子写`AI会话/_requests/<会话ID>/<请求ID>.json`；只记录服务、请求状态、用量和错误类型，不含Key、认证头或正文。正常错误/停止在界面提示；硬结束后重开会话恢复中断及未知用量，不自动重发、不重复计费。此记录能发现中断，不能凭空恢复未保留的退出原因。

## 候选与撤销

- 请求开始在本机取原值快照。候选仅改副本，完整预览提供前后值、受影响模式、积木 IR 和中文读回；生成提示如实保留，不记作沙盒验证。
- 应用前逐字段比较原值；不覆盖请求期间的手改。撤销比较应用值，默认遇到冲突整批停止，也可选择“撤销其余字段，保留我的手改”。确认后再次校验，记录保留和恢复项，部分撤销的批次不能再次撤掉保留项。
- FC/卡背/旧版与 RD 极限攻击、传说按整份编辑器快照比较，包含卡图资源。操作和预览明确“该模式的设置不随卡片保存”，只提供本次启动期间的批次撤销，不补序列化。
- 卡片写入沿用原数据采集/套用入口，样式沿用 _mode_styles；DIY 和 OCG 共用样式槽。积木/字段写原 tab.diy，不自动覆盖效果文字；仅run_sandbox_test在隔离Core里执行编译结果。
- 新建/复制各用新卡片 UID，不继承来源 AI 会话。单批最多新增 100 张；预览保留默认或来源卡图，模型不能指定图片路径。
- 撤销未被玩家改过的 AI 新建卡片/卡包时直接删除恢复。创建后有手改或后续批次依赖则整批停止；选择部分撤销时保留该新对象。不能删掉最后的卡包/卡片。删除玩家原有对象要用 delete_card / delete_pack，每次都由玩家确认，不能撤销。
- 模型工具没有批准、应用、撤销或开启自动应用的入口。开关只由玩家控制，正在生成时锁定；停止保留已生成候选/已应用部分和记录。
- 批次记录保存在对应 AI 消息的 changes 中；原值资源和可执行批次留在内存。普通聊天完成后释放不用的快照，关闭时清理批次资源。

系统提示及全部工具 schema 固定在前缀；模式切换不改变工具集合。当前卡和模式只放在本轮用户消息末尾，JSON 使用固定键序和格式。
现有会话不会因重启或修改提示词文件而替换已发送的前缀；新建会话采用当前版本的提示词和工具目录。
已经发送的协议消息、tool_calls、工具结果只追加，原样保存在独立会话wire中；DeepSeek带tools时历轮reasoning_content完整回传，无tools时不发送该字段。显示折叠、计时等只影响reasoning_parts视图，不改变wire或请求前缀；Claude签名仍只供续传，不展示。思考不进入卡片/调试日志/Markdown导出。更换接口协议保留旧协议原文、另建当前协议历史，会重建缓存。
新会话固定前缀包含完整积木目录、格式/实际语义、27条写法和8张沙盒样例。目录按ID排序、枚举去重，列出每项字段类型/默认/全部选项和槽类型/容量/限定ID。按官方V4分词器离线计数目录21788词元、样例1478词元；真实DeepSeek完整首请求输入29195（含系统、工具、附件）。目录本身低于3万，采用全量；离线分词与服务端统计分别标明。
get_block_catalog可用ids一次查询1～60个ID，批量结果完整返回；query/limit兼容旧单块查询。set_effect_blocks返回reading、warnings、compiled，不必再读取自己的提交；结构错误精确到effects[index]及字段，并列正确选项/示例。编译未完成仍可保存候选，warnings如实说明，不能冒充沙盒通过。f_set=0x0另加警告，name只影响读回；原文要求融合素材送墓、树采用现有近似时会额外返回语义差异警告。
工具结果仍用稳定紧凑JSON，完整本地候选/影响模式/审计不删。引导同次assistant发出多个独立tool_calls，程序按返回顺序执行，依赖UID时仍需等待结果。
旧会话保留既有前缀，首次紧凑结果附带代号图例；请新建会话使用完整文档。已发送历史不重写。旧版被6轮上限丢弃的响应不会伪造恢复；新上限的待执行响应会明确保存用于本次启动内继续。
DeepSeek 使用前缀自动缓存；Claude 在工具尾、系统尾和历史尾放最多四个 cache_control 断点，含前一请求末尾。摘要固定放在前缀之后，后续继续只追加；压缩必然重建摘要后的缓存。
逐请求只留一行实际命中/未命中/命中率。缓存构建说明每会话最多一条，详细间隔保留在逐请求用量的悬停详情；旧重复说明和重复终态仅从视图隐藏，存档/wire不改。调用卡标题区分工具次数和HTTP请求数，避免把所有过程条目当成工具。
DeepSeek官方当前说明缓存构建为秒级，按完整落盘前缀单元命中，未公布固定最小词元数；不足1秒可能尚未落盘只是推测，不人为等待。实际连续新建两会话的system/tools字节相同，第二个首请求命中29056/29195（99.5%），记录见下方验收文档；这次结果不保证所有账户、缓存清退和后续版本始终相同。
采用 OpenAI Docs 和 Claude 的工具返回格式；DeepSeek 默认思考模式要求的续传行为依据下方官方文档。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| settings.py | 独立配置、DPAPI 密钥保护、输入校验；服务类型当前为 text |
| providers.py | 服务预设、两种协议请求、SSE 解析、工具检查参数校验 |
| client.py / worker.py | 带超时、有限重试和取消标志的 HTTP 请求 / QThread 信号 |
| history.py | 消息构造/中断恢复，以及供旧数据迁移的历史兼容入口 |
| session_store.py / session_controller.py / session_view.py | 分文件会话、迁移与索引 / 会话及附件协调 / 列表 |
| file_jobs.py | 顺序后台文件队列、原子替换及关闭排空 |
| request_context.py / cache_policy.py | 固定前缀、只追加协议历史、稳定 JSON 与 Claude 缓存断点 |
| context_budget.py / context_meter.py / transcript_view.py | 后台容量估算/晚压缩、上下文协调、按条展开原文 |
| usage.py / usage_view.py / model_info.py / model_options.py | 用量归一化/逐档计价、用量面板、容量/价格兜底、高级手填 |
| http_policy.py / task_budget.py | 单请求截止、Retry-After与付费错误；请求之间检查的任务约计费用上限 |
| panel.py / settings_dialog.py | 中文聊天侧栏与服务设置 |
| message_view.py / chat_view.py / appearance.py | 原生 Markdown和气泡 / 可见区懒加载 / AI 区域字体 |
| header_view.py / status_view.py / context_view.py | 模型名折行 / 三项底栏与速度浮层 / 上下文构成浮层 |
| reasoning_view.py / stream_metrics.py | 思考折叠与有界滚动 / 仅本地流式阶段计时，不改变API历史 |
| tool_results.py | 发给模型的精简工具结果；与完整本地预览分开 |
| service_info.py | 官方只读余额接口、Claude 模型最大输出信息 |
| model_catalog.py | 按需后台获取实际模型列表、本机缓存及旧查询失效 |
| dock.py | 主窗口局部停靠容器、全局入口、导航绑定与布局保存 |
| card_context.py | 各模式的白名单只读快照、字段范围、版本指纹 |
| operations.py / conversation.py | 唯一操作目录、参数校验 / 有界工具往返 |
| project_access.py / field_rules.py / field_access.py | 项目对象入口 / 字段白名单与影响范围 / 现有卡片和编辑器会话适配 |
| block_edits.py | 复用积木目录校验参数与槽位；限制深度/数量；自定义 Lua 只能原样保留已有的 |
| design_tools.py | 效果文本设计稿的规范检查，以及设计稿和积木读回的逐编号对比 |
| lua_tools.py | write_custom_lua、官方脚本检索、积木缺口日志（AI会话/积木缺口日志.jsonl） |
| risky_actions.py | 删除、导出、安装的逐次确认；未通过验证时可强制，卡包内标记 ygodiy-verify/*-unverified.txt |
| block_reference.py / block_guide.md / block_examples.json | 从目录生成固定完整参考 / 格式、语义与写法 / 已验证样例的固定读回和完整树；运行时不再重生成样例读回 |
| tool_loop.py / continuation.py | 重复检测、暂停进度 / 同一消息和批次续接 |
| change_plan.py / change_book.py / undo_batch.py | 请求快照与字段候选 / 整批应用、失败恢复 / 撤销审查与保留手改 |
| change_view.py / change_coordinator.py | 按字段或新卡展开差异、应用/撤销按钮、冲突对话框和批次入口 |
| controller.py | 在主线程绑定当前卡、处理隐私确认、保存、操作调度与线程生命周期 |
| system_prompt.md | 可独立修改的提示词，明确当前操作、共享字段和候选/应用的能力边界 |
| sandbox_tools.py / sandbox_controller.py | 卡片情景候选、失败反例保护 / 异步沙盒桥接与证据提示 |
| sandbox_process.py / sandbox_view.py | 隔离资源和可终止进程 / 玩家测试清单与折叠详情 |
| request_journal.py | 请求开始与完成日志、异常结束恢复，磁盘操作只在后台线程 |

## 数据与隐私

- 新会话在 `AI服务设置.json` 同目录下的 `AI会话/<UUID>.json`，版本 4。索引可重建，原子写入；不进入卡片、卡包或安装包。
- 旧 `tab["diy"]["ai"]` 和 archives 自动迁移为“卡名 · 日期”，没有时间戳时使用迁移日期并注明。用源 UID、会话来源和内容摘要保证幂等；迁移中断后继续，原数据不改不删，删除已迁移会话后不复活。
- 消息保留发起时的 mode/mode_label/card_label/card_uid；会话本身不绑定卡片，输入草稿、自动应用开关及累计用量按会话保存。
- `messages` 含回复状态、调用过程、该次服务/模型和用量；中断回复不会伪装成完整回复发回模型。
- `messages[].changes` 仅存可序列化差异、状态和错误，不包含快照里的 QPixmap、PIL 对象或请求协议片段；重启显示为只读记录。
- 当前协议历史只追加，超过容量时使用模型摘要缩短发送窗口，原文不删。测试情景归卡片存档，后续效果设计稿也归卡片。
- 卡片内容只读当前模式明确的文字/数值字段，不读取或上传卡图、路径或其他模式快照；卡片中的文字不能开放额外工具。
- FC、卡背、旧版明确标记 editor_session，RD 极限攻击/传说列入 session_fields，不能用当前控件冒充另一张卡的存档。共享影响见 `_tools/AI字段共享影响清单.md`。
- `AI服务设置.json` 独立保存服务配置，Key 使用当前 Windows 用户的 DPAPI 加密。更换 Windows 账户后可能需要重填。
- Key 不进入聊天和卡包；网络异常不直接显示原始异常/HTTP 正文，避免认证数据泄漏。
- 安装脚本排除 `AI服务设置.json*` 和 `AI会话`。发布时仍按导读用干净的组装目录，不从用户数据目录直接打包。
- 布局在 `AI服务设置.json.layout`，模型缓存为同名 `.models`；都受上述排除规则覆盖。缓存按协议/地址/账户摘要分开，只保存模型 ID，没有 Key。
- 测试用 `YGODIY_AI_SETTINGS_DIR` 指向临时目录。AI 修改卡片仍使用 `_request_write_state()`；会话保存走独立文件队列。
- 未配置、断网、认证失败、不支持工具等错误只显示在 AI 区，积木与其他模式照常使用。
- 获取 Key 按钮仅在用户点击时打开相应服务商的官方创建页面；不处理密码、网页登录或第三方登录。

## 余额

只在每次模型请求（含连接测试）结束后启动一次独立 QThread，不定时轮询，也不阻塞下一条聊天。
仅对配置中的已核实官方域名查询：DeepSeek 的 `/user/balance`、Kimi 的 `/v1/users/me/balance`（中国 CNY、国际 USD）。余额四舍五入保留两位小数。
自定义代理不会将 Key 转发到另一个官方域名；不支持或查询失败时，底栏仍显示当前会话用量，不影响聊天。
切换服务会使旧查询结果失效；关闭窗口会协作取消余额线程。

硅基流动已于 2026-08-14 停用 `/user/info`，当前未核实替代接口，因此不调用旧接口，按不支持余额显示用量。

## 本批验收与文档维护

验收见 `_tools/AI积木文档与循环调整验收.md`，真实会话统计和逐请求对比见 `_work/ai_docs_20261103/实测对照.md`。本批确实使用用户已有DeepSeek配置，在隔离副本上完成同卡同指令重测；没有写回原卡片、会话或配置，Key未进入请求正文/报告。

`_tools/ai_docs_unit.py`继承旧单元回归；`ai_docs_ui.py`继承旧修改/撤销/思考UI；`ai_docs_samples.py`复跑选中8张的原情景/变异/读法锁定和90张额外加载，输出目录均用绝对路径。`ai_docs_live.py`会使用真实Key，只能在本批另获明确批准后运行；不得沿用此前批次授权。其余AI测试仍用mock。

样例更新时先跑沙盒检查，再用系统Python执行 `_tools/ai_docs_examples.py`显式刷新固定资料；单元测试核对它与blocks/samples及锁定读回一致。不要在请求或渲染时临时生成样例，不把卡片UID/日期等资料混入固定前缀。

素材事件缺口见 `blocks/AI缺口记录.md`：当前近似组合与官方EVENT_BE_MATERIAL时点不同。本批没有改积木编译器/目录/读回；没有声称新生成的两效果已通过严格素材语义沙盒测试。

## 服务预设依据（2026-11-01 核对）

预设是可修改的填写示例，不保证账户权限或模型始终可用，需用「测试连接」复核。

- [OpenAI Chat 流式格式](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)
- [OpenAI Models](https://developers.openai.com/api/reference/resources/models/methods/list)、[Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Claude Models](https://platform.claude.com/docs/en/api/models/list)、[工具返回](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- [DeepSeek 默认思考与工具续传](https://api-docs.deepseek.com/guides/thinking_mode/)、[模型列表](https://api-docs.deepseek.com/api/list-models/)
- [Grok 模型列表](https://docs.x.ai/developers/rest-api-reference/inference/models)、[Qt 5 QDockWidget](https://doc.qt.io/archives/qt-5.15/qdockwidget.html)
- [Qt 批次撤销的宏操作概念](https://doc.qt.io/qt-6/qundostack.html)、[Qt 对话框尺寸约束](https://doc.qt.io/qt-6/qdialog.html)：本项目用字段原值比较提供冲突保护，未引入另一套 Qt 或第三方库。
- [Claude Messages 流式格式](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [DeepSeek 地址与模型](https://api-docs.deepseek.com/)
- [DeepSeek 余额](https://api-docs.deepseek.com/zh-cn/api/get-user-balance/)
- [Grok Chat Completions 和 API 地址](https://docs.x.ai/developers/model-capabilities/legacy/chat-completions)
- [Kimi 中国余额](https://platform.kimi.com/docs/api/balance)、[国际余额](https://platform.kimi.ai/docs/api/balance)、[当前模型](https://platform.kimi.ai/docs/models)
- [Claude 模型信息的 max_tokens](https://platform.claude.com/docs/en/api/models/retrieve)
- [硅基流动接口停用公告](https://docs.siliconflow.cn/docs/release-notes/overview)
- [百炼 OpenAI 兼容](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)：当前预设用仍兼容的北京公共域名，也可改成自己的业务空间域名。
- [智谱模型](https://docs.bigmodel.cn/cn/guide/start/model-overview)、[智谱地址示例](https://docs.bigmodel.cn/cn/best-practice/case/ai-search-engine)
- [硅基流动示例](https://docs.siliconflow.cn/docs/usercases/use-siliconcloud-in-openmanus)
- [Ollama OpenAI 兼容](https://docs.ollama.com/api/openai-compatibility)

## 测试

在源码目录运行（全部用 mock，不需要真实 Key）：

```
./_tools/run.ps1 ai_unit_test.py [报告.json]
./_tools/run.ps1 ai_stage15_test.py [报告.json] [预览截图目录]
./_tools/run.ps1 ai_stage2_test.py [报告.json] [预览截图目录]
./_tools/run.ps1 ai_workbench_test.py [报告与截图目录]
./_tools/run.ps1 ai_adjustment_unit.py [报告.json]
./_tools/run.ps1 ai_adjustment_test.py [报告与截图目录]
./_tools/run.ps1 ai_changes_test.py [报告与截图目录]
./_tools/run.ps1 ai_feedback_unit.py [报告.json]
./_tools/run.ps1 ai_feedback_ui.py [报告与截图目录]
./_tools/run.ps1 ai_cache_feedback_bench.py [结构重放目录]
./_tools/run.ps1 ai_sandbox_test.py [报告绝对路径.json]
./_tools/run.ps1 ai_sandbox_ui_test.py [输出绝对目录]
./_tools/ai_sandbox_trial.ps1 plan
./_tools/ai_sandbox_trial.ps1 dry
```

最后一条用真实主窗口、隔离标签页路径和临时配置，检查所有模式、工具往返、持久化、恢复、停止、关闭及禁止改卡。
服务商真实连通性需玩家填入自己的 Key 后检查，不把 mock 测试记成真实服务验证。
