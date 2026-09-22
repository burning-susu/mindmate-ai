# Decision Review Backlog
> 文档编号：DECISION-REVIEW-BACKLOG-MINDMATE-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 创建日期：2026-09-21
> 更新时间：2026-09-21

## 使用规则

- 用户明确回复 `决策ID=方案` 后，决策在同一轮立即应用；本清单不是第二次确认队列。
- 每轮最多展示 5 个彼此独立的决策；多项回复使用逐行 `决策ID=方案` 格式。
- 每个已应用决策都登记在本清单中，默认状态为 `PENDING_REVIEW`。复核结果只能通过新的 DEC、ADR、CR 或 UI-DEC 形成，不覆盖历史决策。
- `PENDING_REVIEW` 不等于 `TBD`、无效或等待应用，也不自动阻塞普通 Draft 和开发。
- 高风险、难回退项在进入 `Approved`、`Baselined` 或生产发布前集中检查；复核发现必须改变方案时，走正式变更链。
- `OPEN-01` 是当前 G6 出口阻断，不属于可放入非阻断 backlog 后继续推进的事项；任何 Provider guards 未通过时仍禁止真实外部请求。

## 待复核事项

### RBL-001：当前 DeepSeek Provider 条件性基线与 G6 出口 guards

- Review ID：`RBL-001`
- 来源 Decision ID：`DEC-G6-003`（Chat route；保留 `DEC-G6-001` no-call）
- 标题：DeepSeek API Chat Provider 条件性基线复核
- 风险级别：HIGH
- 风险与影响：数据处理/保留/训练条款、账号资格、地区可用性、模型目录和成本防护尚未全部核验；错误放行会导致数据出站或成本风险。
- 当前采用方案：DeepSeek API；`deepseek-flash`；`https://api.deepseek.com`；Embedding TBD；runtime disabled。
- 为什么当前不阻塞：该条目记录已应用的条件性 Chat 基线，但不替代 `OPEN-01`。普通文档整理可以继续；G6 Exit、运行时启用和 G7 仍被 guards 阻断。
- 最迟复核门禁：G6 Exit / Provider runtime enablement 之前；在 Approved/Baselined 或生产发布前再次集中检查。
- 触发复核的事件：DeepSeek API 条款正文可引用、账号/模型/余额/地区确认、Embedding 选择、模型目录和价格变化、成本停止策略落地。
- 负责人：项目所有者 / 架构评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`（`OPEN-01` 仍为 BLOCKER）
- 复核结论/关联 DEC：未完成；关联 `EVID-033`、`OPEN-01`、`DEC-G6-003`。

### RBL-002：Provider 详情未决期间的 no-call 边界

- Review ID：`RBL-002`
- 来源 Decision ID：`DEC-G6-001`
- 标题：Provider 详情核验完成前禁止真实外部请求
- 风险级别：HIGH
- 风险与影响：在条款、账号、地区和成本边界未核验前发起外部调用，可能造成敏感数据出站、未授权费用或不可审计的运行时行为。
- 当前采用方案：保留外部 Provider 总体方向，但只允许逻辑 Adapter 和文档分析；真实 Provider 请求禁用。
- 为什么当前不阻塞：这是当前 G6 的安全停止边界，保护文档工作可以继续；它不能被解释为 G6 出口已通过。
- 最迟复核门禁：G6 Exit / Provider runtime enablement 之前。
- 触发复核的事件：`OPEN-01` guards 全部通过、运行时启用评审或 Provider 方案发生正式变更。
- 负责人：项目所有者 / 安全与架构评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`
- 复核结论/关联 DEC：继续由 `DEC-G6-003` 承接；关联 `EVID-025`、`EVID-029`、`EVID-030`、`EVID-032`、`EVID-033`。

### RBL-003：V1 本地轻量备份与恢复技术细节

- Review ID：`RBL-003`
- 来源 Decision ID：`DEC-G5-001`
- 标题：本地备份格式、加密、覆盖、索引重建和失败恢复
- 风险级别：MEDIUM
- 风险与影响：格式和恢复语义未冻结可能造成数据丢失、覆盖误操作或索引不一致。
- 当前采用方案：V1 提供轻量本地导出/备份和恢复，不提供云同步或远程备份。
- 为什么当前不阻塞：PRD 只确认方向；技术细节明确留给 G6/G8/G10，当前未进入实现。
- 最迟复核门禁：G8 详细设计前，G10 开发批次确认前。
- 触发复核的事件：进入数据模型、文件状态机、备份实现或恢复验收设计。
- 负责人：项目所有者 / 数据与可靠性评审
- 创建日期：2026-09-21
- 当前状态：`PENDING_REVIEW`
- 复核结论/关联 DEC：待形成后续技术 DEC/TD；关联 `DEC-G5-001`。

### RBL-004：V1 页面树与嵌套详情范围

- Review ID：`RBL-004`
- 来源 Decision ID：`DEC-G3-001`
- 标题：五个一级页面壳和详情嵌套方式复核
- 风险级别：LOW
- 风险与影响：页面层级、导航或详情承载方式变化会影响 UI Contract、路由和验收追踪。
- 当前采用方案：五个一级页面壳；知识库详情和文件详情作为嵌套页面；学习陪练保留在 AI 对话模式；设置页和独立错题本不进入 V1。
- 为什么当前不阻塞：G3/G5.5 已形成当前 UI 逻辑范围，后续只在发现需求或实现冲突时复核。
- 最迟复核门禁：G9.1 真实应用目录和 G10 UI Contract 确认前。
- 触发复核的事件：Approved PRD 变化、路由实现发现冲突、G9.5 正式 UI 规范启用。
- 负责人：项目所有者 / UI 评审
- 创建日期：2026-09-21
- 当前状态：`PENDING_REVIEW`
- 复核结论/关联 DEC：待复核；关联 `DEC-G3-001`、`UI_LOGIC_SCOPE`。

### RBL-005：首版本地运行、打包、升级和卸载边界

- Review ID：`RBL-005`
- 来源 Decision ID：`DEC-BOOTSTRAP-001`
- 标题：本地单用户运行交付参数
- 风险级别：MEDIUM
- 风险与影响：操作系统、打包方式、升级、卸载和本地数据保留策略未定，可能影响交付和恢复体验。
- 当前采用方案：本地单用户 MVP；模块化单体；不引入云服务器和复杂后台。
- 为什么当前不阻塞：当前仍处于 G6，开发和发布交付参数尚未进入正式计划；不影响本轮文档治理迁移。
- 最迟复核门禁：G10 开发计划和 G11 发布准备前。
- 触发复核的事件：确认目标 OS、打包工具、升级通道或数据迁移策略。
- 负责人：项目所有者 / 交付评审
- 创建日期：2026-09-21
- 当前状态：`PENDING_REVIEW`
- 复核结论/关联 DEC：待形成开发计划和交付决策；关联 `DEC-BOOTSTRAP-001`。

### RBL-006：通用 Capability 旧流程文字与新治理源冲突

- Review ID：`RBL-006`
- 来源 Decision ID：`DECISION_WORKFLOW_MIGRATION`（治理冲突，无业务方案选择）
- 标题：`technical-selection.md` 仍描述二次确认
- 风险级别：LOW
- 风险与影响：后续跨项目读取通用 Capability 时，可能误把历史二次确认方法当成当前项目交互门禁。
- 当前采用方案：当前项目以 v3.2.7/v3.2.5 实际治理源和本迁移记录的即时应用规则为准；本轮不修改 `doc/` 通用库。
- 为什么当前不阻塞：项目级 Runtime、Workflow 和决策入口已明确覆盖当前执行；没有因此改变 G6/G7 状态。
- 最迟复核门禁：下一次通用治理库版本发布或本项目重新激活技术选型 Capability 前。
- 触发复核的事件：通用 Capability 更新、治理源冲突修复或跨项目流程校准。
- 负责人：治理维护者
- 创建日期：2026-09-21
- 当前状态：`OPEN`
- 复核结论/关联 DEC：待治理库维护；关联 `DECISION_WORKFLOW_MIGRATION.md`。

### RBL-007：Alibaba Chat 路线历史替代关系

- Review ID：`RBL-007`
- 来源 Decision ID：`DEC-G6-002`
- 标题：Alibaba Chat Provider 被 DeepSeek 修订替代
- 风险级别：MEDIUM
- 风险与影响：旧文档或旧 Guard 若被误当作当前 Provider，会导致错误的账号、条款、价格和数据出站判断。
- 当前采用方案：保留 Alibaba 条件性基线、Guard、价格和 Evidence 作为历史；Chat 路线由 `DEC-G6-003` 取代，Alibaba 不是自动回退。
- 为什么当前不阻塞：历史证据可审计，当前入口已由 Runtime、Architecture 和 DEC-G6-003 指向 DeepSeek；不改变 G6 阻断。
- 最迟复核门禁：任何 Provider runtime 启用或重新选择 Provider 前。
- 触发复核的事件：重新选择 Alibaba、需要复用 Alibaba Embedding、历史资料清理或新的 Provider 变更。
- 负责人：架构评审
- 创建日期：2026-09-21
- 当前状态：`SUPERSEDED`
- 复核结论/关联 DEC：Chat route 已由 `DEC-G6-003` 取代；历史 DEC/Evidence 不删除。

### RBL-008：DeepSeek API 数据与账号 Guard

- Review ID：`RBL-008`
- 来源 Decision ID：`DEC-G6-003`
- 标题：DeepSeek API 数据处理、账号、地区和余额核验
- 风险级别：HIGH
- 风险与影响：API 数据条款、地域、账号资格或余额不可用会导致数据合规、运行失败和费用风险。
- 当前采用方案：DeepSeek Chat 条件性应用；runtime disabled；不调用、不读取 Key。
- 为什么当前不阻塞：文档工作和剩余决策整理可以继续，但 G6 Exit、运行启用和 G7 仍被 Guard 阻断。
- 最迟复核门禁：G6 Exit / Provider runtime enablement 前。
- 触发复核的事件：取得 API 官方条款、确认账号/模型/余额/地区、价格或限流变化。
- 负责人：项目所有者 / 安全与架构评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`
- 复核结论/关联 DEC：未完成；关联 `EVID-033`、`OPEN-01`。

### RBL-009：Embedding 方案

- Review ID：`RBL-009`
- 来源 Decision ID：`DEC-G6-004` / `TECH-G6-EMBEDDING`
- 标题：DeepSeek Chat 与 Embedding 解耦后的 Embedding 选择
- 风险级别：HIGH
- 风险与影响：Embedding 选择决定知识库切片是否外发、安装负担、中文检索质量、重建成本和 G6 出口。
- 当前采用方案：本地 `BAAI/bge-small-zh-v1.5`；DeepSeek 官方当前公开模型价格页未列 Embedding API。
- 为什么当前不阻塞：方向已同轮应用，但本机性能、质量、许可证和安装 Spike 尚未执行；本轮不下载或运行本地模型。
- 最迟复核门禁：G6 Exit、G8 RAG 详细设计前。
- 触发复核的事件：本地模型 Spike、新的官方 Embedding 资料、质量/许可证/资源约束变化。
- 负责人：项目所有者 / RAG 评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`
- 复核结论/关联 DEC：`DEC-G6-004` 已应用方向；待完成 Spike 和后续技术记录。

### RBL-010：DeepSeek 成本保护

- Review ID：`RBL-010`
- 来源 Decision ID：`DEC-G6-004` / `COST-G6-PROVIDER`
- 标题：USD 5 预算、提醒、停止和余额不足行为
- 风险级别：HIGH
- 风险与影响：DeepSeek 峰/非峰和缓存价格不同，缺少本地预算阻断可能导致超预算、自动重试或余额透支。
- 当前采用方案：USD 5 月软预算；USD 4 提醒；USD 5 停止新调用；禁自动充值/提额；手动恢复。
- 为什么当前不阻塞：政策已应用但成本计数、停止和手动恢复尚未实现；Provider runtime 仍禁用，本轮没有真实费用操作。
- 最迟复核门禁：G6 Exit / Provider runtime enablement 前。
- 触发复核的事件：成本计数和停止策略进入 G8/G9 设计、价格/余额规则变化或实现验收。
- 负责人：项目所有者 / 成本与可靠性评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`
- 复核结论/关联 DEC：`DEC-G6-004` 已应用政策；待形成实现设计和验证证据。

### RBL-011：DeepSeek Chat Model

- Review ID：`RBL-011`
- 来源 Decision ID：`DEC-G6-004` / `TECH-G6-CHAT-MODEL`
- 标题：`deepseek-flash` 官方候选与默认模型确认
- 风险级别：MEDIUM
- 风险与影响：模型 ID 影响价格、上下文、thinking、输出限制、质量和账号可用性；Provider 选择不能自动等同于模型批准。
- 当前采用方案：`deepseek-flash`；用户已明确选择 A，作为当前 Chat Model 条件性基线。
- 为什么当前不阻塞：账号、模型权限、地区和 Provider guards 仍阻断 runtime；官方模型候选还需接入前核验。
- 最迟复核门禁：G6 Exit / G8 Chat 详细设计前。
- 触发复核的事件：官方模型目录/价格变化、账号模型权限核验或 Chat 质量评测。
- 负责人：项目所有者 / Chat 质量评审
- 创建日期：2026-09-21
- 当前状态：`REVIEW_DUE`
- 复核结论/关联 DEC：`DEC-G6-004` 已应用 `deepseek-flash`；待完成账号/模型 Guard 和接入前评测。

### RBL-012：本地嵌入式向量存储方向

- Review ID：`RBL-012`
- 来源 Decision ID：`DEC-G6-004` / `TECH-G6-VECTOR-STORE` / `TECH-DEC-005`
- 标题：本地嵌入式向量存储与 Storage Adapter
- 风险级别：MEDIUM
- 风险与影响：产品/类别、物理共置、索引格式、迁移、重建和失败恢复会影响安装复杂度、检索质量和备份兼容性。
- 当前采用方案：本地嵌入式向量存储，通过 `Storage Adapter` 隔离；具体产品留 G8 Spike。
- 为什么当前不阻塞：方向已应用，但不锁定具体依赖或数据库；G6 Draft 可继续，依赖产品的 G8/G9 设计不能提前完成。
- 最迟复核门禁：G8 RAG/数据详细设计和 G9 数据契约前。
- 触发复核的事件：Spike 结果、Windows 资源约束、索引重建/备份恢复设计或产品生命周期变化。
- 负责人：项目所有者 / RAG 与存储评审
- 创建日期：2026-09-21
- 当前状态：`PENDING_REVIEW`
- 复核结论/关联 DEC：`DEC-G6-004` 已应用方向；待 G8 Spike 和后续 TECH-DEC/TD。

## 已完成复核

暂无本迁移后产生的 `ACCEPTED`、`REVISE` 或 `REJECTED` 复核结论。历史决策仍保持其原有 DEC/Evidence；“历史上完成二次确认”是审计事实，不是本清单的新增确认步骤。

## 归档规则

- 只有在形成新的复核结论并完成对应 DEC、ADR、CR 或 UI-DEC 追踪后，才可将条目标记为 `RESOLVED`、`SUPERSEDED` 或归档。
- 归档不得删除原决策、原 Evidence 或原始用户选择；必须保留替代关系和生效时间。
- `OPEN-01` 在 guards 完成前不得归档为已解决，也不得通过 backlog 状态推断 G6 Exit 或 G7 已就绪。
