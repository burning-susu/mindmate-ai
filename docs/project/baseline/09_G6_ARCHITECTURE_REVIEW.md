# Mindmate AI G6 总体架构评审记录
> 文档编号：G6-ARCHITECTURE-REVIEW-001
> 文档版本：v1.0-Draft.1
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 文档状态：Draft / In Review
> 评审阶段：G6
> 执行级别：L3
> 创建日期：2026-09-21
> 更新日期：2026-09-21
> 关联 Workflow：WF-MINDMATE-001 v0.1
> 关联 PRD：PRD-MINDMATE-V1 v1.0-Draft.3 Approved
> 关联 UI 范围：UI-LOGIC-SCOPE-MINDMATE-001 v1.0-Draft.1
> 关联证据：EVID-018、EVID-021、EVID-022、EVID-023、EVID-024、EVID-025、EVID-026、EVID-027、EVID-028、EVID-029、EVID-030、EVID-032、EVID-033、EVID-034
> 关联决策：DEC-G6-001、DEC-G6-002、DEC-G6-003、DEC-G6-004

## 1. 本轮范围与限制

本轮实际进入并执行 G6，总体架构 Draft 与本评审记录已产生。未重复执行模型路由 Bootstrap、PRD 审批或 G5.5；未创建 UI 逻辑范围副本；未创建代码、脚手架、DDL、正式 OpenAPI、依赖配置或 G7 模块边界；未执行 Git commit、tag 或 push。

模型路由依当前 Runtime Context 保持 RECOMMEND_ONLY。路由日志仍为空；本轮没有真实模型切换证据，故 MODEL_SWITCH_EXECUTED=false，ACTUAL_MODEL_ID=TBD。路由降级没有阻断 G6 Draft。

当前 Provider 修订见 `DEC-G6-003`，剩余决策批量应用见 `DEC-G6-004`：Chat Provider/Model 为 DeepSeek API / `deepseek-flash`，Embedding 条件性采用本地 BGE，向量存储采用本地嵌入式方向，成本政策已应用但未实现。DeepSeek Guard、账号/数据/地区和运行门禁未完成，Provider runtime 继续禁用。

## 2. G6 入口核验

| 检查项 | 结果 | 证据 |
|---|---|---|
| PRD_STATUS=APPROVED | PASS | PRD v1.0-Draft.3、EVID-018、EVID-022 |
| G5.5_STATUS=COMPLETED | PASS | UI 逻辑范围、EVID-023 |
| G6_ENTRY_GATE=READY | PASS | Workflow、Runtime Context |
| G5.5 出口 Evidence 存在 | PASS | EVID-023 |
| UI 逻辑范围可追踪到 Approved PRD | PASS | UI_LOGIC_SCOPE、TRACE_MATRIX |
| 新 G6 入口 BLOCKER | NONE | OPEN-01 是 G6 出口阻断，不是入口阻断 |
| YAML 可解析 | PASS | 当前相关治理 YAML 使用 PyYAML 只读解析 |
| Context Index 当前哈希 | PASS | 最终核验确认 30 个被索引资源均存在且 SHA-256 一致，无缺失或不匹配 |

入口结论：G6_ENTRY_VERIFICATION=PASSED。G6 执行状态已转为 IN_PROGRESS，随后因出口阻断保持 BLOCKED。

## 3. 输入与事实来源

已读取并核对：Approved PRD、PRD Changelog、UI 逻辑范围、TRACE_MATRIX、OPEN_ITEMS、G5 评审报告、Workflow Blueprint、Runtime Context、Context Index、Evidence Register、Project Profile、Assessment、Capability Activation、DEC-BOOTSTRAP-001、DEC-G3-001、DEC-G5-001、G2 决策基线/待确认问题、模型注册表/路由日志及通用架构手册/技术选型 Capability。

已继承且不可在本轮扩大范围的架构事实：

- 本地单用户 MVP，桌面优先 Web + 同设备本地服务；无远程业务服务器。
- 模块化单体、内部异步任务；不采用微服务。
- Chat 使用 DeepSeek 外部 Provider，通过本地后端 Adapter；Embedding 条件性采用本地 BGE；只考虑当前任务必需文本/上下文，不等于完全离线。
- 原始文件、业务元数据、解析数据和向量默认本地；V1 轻量本地备份/恢复；无云同步/远程备份。
- 五个一级页面壳，知识库/文件详情嵌套；陪练属于 AI 对话模式；设置与独立错题本不进入 V1。
- REST + OpenAPI 为方向；DeepSeek Chat、本地 BGE Embedding、本地嵌入式向量存储方向和成本政策已条件性应用；具体产品、Spike、流式协议和备份技术仍 TBD。

## 4. 技术决策盘点

| ID | 主题 | 状态 | 依据或未决项 | G6 阻断 |
|---|---|---|---|---|
| TECH-DEC-001 | 应用交付形态 | CONFIRMED | 桌面优先 Web、本地服务；浏览器/OS 已有资料支持，打包启动细节 TBD | 否 |
| TECH-DEC-002 | 本地进程拓扑 | CONFIRMED | UI 与本地服务位于用户同一设备；静态资源与 API 是否同进程、端口/监听 TBD | 否 |
| TECH-DEC-003 | 前后端边界 | CONFIRMED | 模块化单体、内部异步任务、REST/OpenAPI 方向已有用户确认 | 否 |
| TECH-DEC-004 | Provider/Embedding、地域与数据处理条款 | APPLIED_CONDITIONAL / BLOCKED | DEC-G6-003/004 已应用 DeepSeek Chat + 本地 BGE；API 数据条款、账号资格、地区、成本运行门禁和本地 Spike 尚未完成，运行时保持禁用 | 是，唯一当前出口阻断 |
| TECH-DEC-005 | 本地元数据/文件/向量存储 | APPLIED_DIRECTIONAL / TBD_PRODUCT | DEC-G6-004 已应用本地嵌入式向量存储方向；具体数据库/向量产品与共置方式留 G8 Spike | 否 |
| TECH-DEC-006 | RAG 链路 | CONFIRMED | PRD 已定义导入、解析、切片、Embedding、检索、回答和真实引用；重排/切片算法 TBD | 否 |
| TECH-DEC-007 | 长任务与恢复 | CONFIRMED | 内部异步任务与刷新恢复需求确认；任务持久化、幂等/重试具体规则留 G8/G9 | 否 |
| TECH-DEC-008 | 数据出站 | CONFIRMED | 最小必要文本/上下文原则确认；具体接收 Provider 和条款仍受 TECH-DEC-004 阻断 | 同 TECH-DEC-004 |
| TECH-DEC-009 | 备份/恢复 | CONFIRMED | DEC-G5-001 确认本地轻量恢复；内容、格式、加密、覆盖/合并和失败回滚继续 TBD | 否 |
| TECH-DEC-010 | Secret/文件安全 | CONFIRMED | Key 位于本地后端配置，不进前端/仓库/普通日志；路径与 OS Secret 细节 TBD | 否 |
| TECH-DEC-011 | API/上传/流式 | CONFIRMED | REST/OpenAPI 已确认；上传与流式协议留 G9 | 否 |
| TECH-DEC-012 | 升级/迁移/本地诊断 | TBD_NONBLOCKING | 可提出版本化迁移及本地脱敏日志，但工具、兼容矩阵和指标 TBD | 否 |
| TECH-DEC-013 | 前后端语言、框架与工程工具 | TBD_NONBLOCKING | 桌面 Web、本地服务边界已确认；框架和语言未选择 | 否 |

## 5. TECH-DEC-004 候选评审摘要

**问题与阻断原因：**OPEN-01 要求 G6 正式架构出口前确认外部 Provider、模型/Embedding、地域和数据处理条款。已有证据只确认使用外部 Provider、经本地后端 Adapter、最小必要内容出站；它没有确认接收方、数据处理地域、留存/训练条款或预算上限。若把外部调用画成已选定服务或标记出口通过，会超出证据并隐含授权。

**功能在哪看到 / 人话 6 问：**

1. 哪一端、哪一业态：Mindmate 桌面优先 Web、本地单用户应用；不是企业后台或云端 SaaS。
2. 谁：本地用户；生成/Embedding 服务是自动调用对象，不替用户作出数据授权。
3. 怎么进入：用户从 AI 对话页选自由对话/资料问答/学习陪练，或从知识库/文件详情导入资料。
4. 人在哪看到：对话回答、引用、文件处理状态和失败提示；用户应能看到当前 AI 功能可能把哪些必要文本交给已确认的 Provider。
5. 怎么操作：导入文件会触发解析与 Embedding；提交问题会触发模型生成；实际外部调用只有在 Provider、地域和条款通过确认并配置后才允许发生。
6. 现在怎样 / 改完怎样：当前逻辑架构没有具体 Provider，也没有真实外部调用授权；完成确认后也只允许当前任务所需片段/问题/有限上下文，不得默认上传整份文件或全部历史。

**生活化例子：**用户把一份复习讲义放入本地知识库。系统为检索生成向量时，可能把切片文本发给 Embedding 服务；之后用户问“这段讲义如何定义闭包”，模型请求还可能带上命中的几段原文。原件和索引仍保存在本机，但切片已接触外部服务。若不知道具体服务在哪里处理、留存多久、是否用于改进模型，就无法准确告知用户，所以不能只凭“本地部署”把这条数据边界写成已批准。

**可行方案：**

- A：选择一个同时满足生成和 Embedding 需求的外部 Provider。一个服务边界和一组条款/密钥，开发与诊断较简单；代价是对其模型能力、价格、地域和政策形成较强耦合。只有在同一 Provider 的地域/留存/训练条款、费用及模型能力经过核验后才适用。
- B：模型生成与 Embedding 使用不同 Provider。可分别挑选能力和成本更合适的服务；代价是两份数据处理边界、两套密钥/故障/合规检查，文本切片和会话上下文可能交给不同服务，测试与撤换复杂度增加。
- C：当前保持供应商/模型/地域 TBD，只建本地 Adapter 边界，不执行任何真实外部请求；待用户确认可接受的候选及其处理条款后再应用。不会改变 Approved PRD 的“外部 Provider”方向，但 G6 保持 Draft/Blocked，进入依赖外部调用的实现前仍不可越过此门禁。

共同边界：本地仍是业务数据的权威存储；Provider 调用不与本地事务形成分布式事务，调用前后必须由本地任务状态追踪。具体幂等键、部分失败补偿和恢复策略留 G8/G9。

| 影响维度 | A：一个 Provider 承担生成与 Embedding | B：生成与 Embedding 分开 | C：维持 TBD，不发起调用 |
|---|---|---|---|
| 数据归属/隐私 | 两类文本由同一外部处理方接触；需同一地域/条款覆盖两种用途 | 文本可能流向两个处理方，需分别核验地域/保留/训练条款和告知范围 | 用户资料暂不离开设备；实际 AI 请求不可运行 |
| 依赖/锁定 | 实现简单，但两种能力共同依赖一个服务；更换可能同时影响对话与重建 | 可单独替换能力，适配和运维依赖增多 | 仅依赖本地适配接口，待服务确定后才增加网络依赖 |
| 事务/状态/失败 | 远程调用仍不能加入本地事务；一个服务异常同时影响两条链路 | 可隔离故障，但可能出现 Embedding 已成功、生成服务失败等部分状态 | 无远程部分结果；任务可显示未配置/不可用，不能伪装生成成功 |
| 性能/成本 | 单一报价/限额较易管理；是否同时满足两类延迟和质量需实测 | 可独立优化模型与 Embedding 成本/质量，但涉及多份账单和跨服务延迟 | 暂无调用费用，但 V1 AI 核心闭环不能真实验收 |
| 开发/测试/维护 | 一个 Adapter 集合、一个条款面和较少故障组合 | 多 Adapter、多密钥、多监控/错误组合，替换灵活性更高 | 当前可测试本地边界与阻断反馈，不能测试真实 Provider 链路 |
| 迁移/回滚 | 更换 Embedding 模型可能需要全量或分批重建；回退到旧向量需版本化 | 只替换其中一侧，但跨 Provider 数据策略和版本组合更多 | 不产生远端数据与向量；后续启用时仍要完成配置、重建与集成测试 |
| 测试/发布 | 需对单 Provider 的认证、限流、超时、版本变化和回退做验证 | 需分别覆盖两个服务及组合故障 | 需保证未确认/未配置时无外部请求，正式启用前补齐集成与隐私验收 |

**历史 Alibaba 应用：**A 曾由用户二次确认并由 DEC-G6-002 条件性应用，amends DEC-G6-001；该历史记录继续保留，但 Chat 路线已由 DEC-G6-003 修订为 DeepSeek API。当前仍保留 no-call guards，不发生真实 Provider 请求。

**影响：**数据所有权仍属本地用户；外发范围限制到当前任务必要数据。A 少一套数据接收方和密钥但更易形成单一供应商锁定；B 可独立替换能力但扩大外部数据边界。两者都要求适配层隔离、脱敏诊断、Provider 故障/限流/超时测试、隐私提示、配置安全、费用上限及退出/替换路径。数据库、事务和本地存储不因本决策自动改变；没有 Provider Key 前不产生连接、计费或用户数据请求。具体服务成本/性能必须在候选确定后以其官方条款和实际测试核验，当前均为 TBD。

**开发决策清单：**本轮只允许记录候选和逻辑 Adapter 约束；不改代码、不加 SDK、不写 Key、不调用外部服务。完成用户初选、影响复述、二次确认和应用前，G6 不创建正式 Provider ADR，也不进入依赖实际 Provider 的实现。

## 6. 架构 Draft 评审

产物：docs/project/architecture/SYSTEM_ARCHITECTURE.md，文档状态 Draft。

| 检查点 | 结果 |
|---|---|
| 本地优先拓扑、单用户边界与外部 Provider 入口 | 已描述；具体接收方受阻断项控制 |
| 逻辑分层与 14 个模块职责 | 已描述；不等于 G7 已批准模块边界 |
| 依赖方向/循环依赖 | 已列内向端口、Adapter 实现与事件单向流；没有模块环 |
| 核心数据分类/敏感度/删除/重建 | 已覆盖 |
| RAG 主链、失败/重试/取消/重启/删除 | 已覆盖，具体算法和阈值 TBD |
| 三种对话模式、页面映射、引用与持久化 | 已覆盖 |
| 后台任务状态/恢复 | 已覆盖，未选队列、线程或重试组件 |
| 数据出站矩阵、Secret 与文件安全 | 已覆盖；未把候选外发写作当前授权 |
| 备份/恢复及索引重建路径 | 逻辑组件已定义；实现细节保持 TBD |
| 错误、诊断与 NFR 映射 | 已覆盖；无虚构 SLO |
| TRACE_MATRIX 关系更新 | 本轮治理同步项 |
| 代码、DDL、正式 API 或依赖 | 未生成 |

## 7. 出口预检及阶段状态

| 出口检查 | 结果 | 说明 |
|---|---|---|
| Approved PRD / G5.5 入口 | PASS | EVID-018、EVID-023 |
| Blocking TECH_DEC 全部确认并应用 | BLOCKED | DEC-G6-004 四项条件性方向已应用；API 条款、账号/地区、成本运行门禁和本地 Spike 尚未完成，不能启用运行时 Provider |
| ARCHITECTURE_DECISION_REVIEW_STATUS | IN_PROGRESS | DeepSeek Chat、本地 BGE、向量方向和成本政策已应用；Provider 条款/账号/地域、Spike 与实现仍待评审 |
| ARCHITECTURE_DECISION_APPLY_STATUS | PARTIAL | DEC-G6-003/004 已应用 DeepSeek Chat、本地 BGE、向量方向和成本政策；guards、Spike、实现和 G6 Exit 仍未完成 |
| Proposed/TBD 与技术栈可追踪 | PASS | 每项均有 TECH-DEC 与责任阶段 |
| 互相冲突的组合方案 | NONE | 单一出口阻断；其余为可分阶段处理项 |
| Deferable 项责任阶段 | PASS | 详见 OPEN_ITEMS 与架构清单 |
| 正式 Approved/Baselined | NO | 当前只能保留 Draft |

当前状态：

```text
CURRENT_STAGE=G6
G6_ENTRY_VERIFICATION=PASSED
G6_STATUS=BLOCKED
ARCHITECTURE_STATUS=DRAFT
G7_ENTRY_GATE=NOT_READY
G7_EXECUTION=NOT_STARTED
```

G6 不能因为条件性 Provider/剩余技术方向已应用而宣称完成。待 OPEN-01 的数据处理/保留/训练条款、账号资格、地区可用性和成本运行门禁完成核验，并完成本地 Embedding/向量 Spike 后，再执行 G6 Exit preflight；本轮不进入 G7。

## 8. 问题统计与 Evidence

本轮 G6 架构范围统计（与 G3 历史等级分开；同一历史事项不重复计数）：

| 分类 | 数量 | 内容 |
|---|---:|---|
| BLOCKER | 1 | TECH-DEC-004 / OPEN-01 Provider 数据处理边界 |
| MAJOR（新增） | 0 | 无新增未分类重大项 |
| MINOR（新增） | 0 | 无新增未分类小项 |
| TBD / Deferable | 11 | TECH-DEC-005/006/007/009/010/011/012/013、OPEN-04、TBD-PRD-007/008；跨表重复项已合并 |
| CONFLICT（新增） | 0 | 未发现需覆盖 Approved PRD 的冲突 |

上游 G3-MAJOR-001 至 G3-MAJOR-004 仍按 PRD/OPEN_ITEMS 责任阶段追踪；其中 Provider 具体数据处理部分与当前唯一 BLOCKER 重叠。

11 个 Deferable 工作包只作本轮 G6 范围计数，不改变 PRD 中原始 TBD 编号；其余 G5/G8/G9/G10/G11 未决项继续保留在 OPEN_ITEMS。

- G6 Draft 与入口/出口核验记录：本文件及 EVID-024；no-call 应用证据：DEC-G6-001、EVID-025；DeepSeek 修订与 Guard：DEC-G6-003、EVID-032、EVID-033。
- UI 逻辑范围与 PRD 追踪：docs/project/ui/UI_LOGIC_SCOPE.md、docs/project/acceptance/TRACE_MATRIX.md。
- 模型路由既有降级 Evidence：EVID-021；本轮未伪造新模型切换记录。

## 9. 后续操作

官方候选与成本资料包已写入 docs/project/baseline/10_G6_PROVIDER_DECISION_REVIEW.md；DeepSeek Chat 的条件性应用由 DEC-G6-003 / EVID-032 登记，四项剩余决策批量应用由 DEC-G6-004 / EVID-034 登记，当前 Guard Verification 由 EVID-033 登记。Alibaba A 的原始应用由 DEC-G6-002 / EVID-029 保留为历史。当前 PROVIDER_DECISION_STATUS=APPLIED_CONDITIONAL；OPEN-01 guards、本地 Spike 和成本实现未关闭，真实请求保持禁用，G6 与 G7 状态不变。

## 10. DeepSeek 修订后的集中决策入口

本轮四项剩余 G6 决策已由 DEC-G6-004 同轮应用：`TECH-G6-CHAT-MODEL=A`、`TECH-G6-EMBEDDING=A`、`COST-G6-PROVIDER=A`、`TECH-G6-VECTOR-STORE=A`。本地 Spike、成本实现和 Provider guards 仍未完成，G6/G7 门禁保持不变。
