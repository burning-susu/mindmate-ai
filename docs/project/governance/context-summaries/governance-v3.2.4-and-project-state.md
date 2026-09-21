# v3.2.6 治理与 Mindmate 状态摘要
> 摘要编号：CTX-SUMMARY-001
> 摘要版本：v1.3
> 生成时间：2026-09-21
> 状态：CURRENT
> 用途：任务前最小上下文复用

## 来源

- doc/governance/通用文档提示词v3.2.md
  - SHA-256：902C8C9F1C783742CB56AE803022FE0423D45D90B8AA9399606A9236ED265E25
  - 覆盖：v3.2.7 变量、模型路由、Token/上下文治理、即时决策应用、G0-G11、Workflow、Runtime Context、Evidence 和目录规则。
- doc/governance/通用文档提示词v3.2完整使用说明.md
  - SHA-256：DB0AC53C5C76A098356B8951A6C115EE567C7D9AEF4DD116EA9ADC389CA86A2A
  - 覆盖：v3.2.5 的 Token/context governance、model routing、即时决策应用、任务前运行顺序和索引规则。
- docs/project/governance/WORKFLOW_BLUEPRINT.yaml
  - 覆盖：WF-MINDMATE-001 v0.1 已确认，当前阶段 G6；G6 架构 Draft 已生成，OPEN-01 阻断正式出口。
- docs/project/governance/RUNTIME_CONTEXT.md
  - 覆盖：当前 G6 文档写入权限、架构出口阻断、Token 预算、上下文装载模式和模型路由降级。
- docs/project/governance/EVIDENCE_REGISTER.yaml
  - 覆盖：EVID-018 PRD 批准、EVID-021 模型路由降级、EVID-022/023 G5.5 出口及 EVID-024 G6 Draft/阻断证据。
- docs/project/architecture/SYSTEM_ARCHITECTURE.md
  - 覆盖：G6 供应商无关架构 Draft、模块/数据/RAG/Provider/备份/安全/NFR 边界。
- docs/project/baseline/09_G6_ARCHITECTURE_REVIEW.md
  - 覆盖：G6 入口核验、TECH-DEC 状态、OPEN-01 出口阻断及未决项统计。
- docs/project/decisions/DEC-G6-001.md
  - 覆盖：TECH-DEC-004=C 已应用为 Provider 详情确认前的 no-call 临时边界；不解除 OPEN-01 阻断。
- docs/project/decisions/DEC-G6-002.md
  - 覆盖：历史 Alibaba 条件性 Provider 基线；Chat route 已由 DEC-G6-003 修订替代；no-call 历史保留。
- docs/project/decisions/DEC-G6-003.md
  - 覆盖：当前 DeepSeek Chat Provider 条件性基线；剩余 G6 子决策由 DEC-G6-004 承接；runtime disabled。
- docs/project/decisions/DEC-G6-004.md
  - 覆盖：Chat Model、local BGE Embedding、本地嵌入式向量存储方向和 USD 5 成本政策的批量应用。
- docs/project/baseline/10_G6_PROVIDER_DECISION_REVIEW.md
  - 覆盖：官方 Provider/模型/Embedding 候选、价格与数据边界比较；DeepSeek Chat 已条件性应用，runtime disabled，guards 未完成。
- docs/project/baseline/G6_DEEPSEEK_PROVIDER_CHANGE_REVIEW.md
  - 覆盖：DeepSeek Provider 修订、官方 API 事实、目标架构和剩余决策批次。
- docs/project/baseline/12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md
  - 覆盖：DeepSeek 当前 Guard Matrix 和 G6 Exit Preflight；数据/账号/Embedding/成本 guards 阻断。

## 当前结论

- PROJECT_STAGE：BOOTSTRAP。
- WORKFLOW：WF-MINDMATE-001 v0.1 / CONFIRMED。
- CURRENT_STAGE：G6；G6 入口已通过，架构 Draft 已生成。
- G5_REVIEW_STATUS：COMPLETED。
- PRD_APPROVAL_GATE：COMPLETED。
- G5_5_ENTRY_GATE：READY。
- G5_5_STATUS：COMPLETED。
- G6_ENTRY_GATE：READY；G6_ENTRY_VERIFICATION：PASSED。
- G6_STATUS：BLOCKED；ARCHITECTURE_STATUS：DRAFT。
- ARCHITECTURE_DECISION_APPLY_STATUS：PARTIAL；DEC-G6-003/004 已条件性应用 DeepSeek Chat、local BGE、向量方向和成本政策，DEC-G6-001 no-call guards 保持有效。
- G7_ENTRY_GATE：NOT_READY；G7_EXECUTION：NOT_STARTED。
- TECH-DEC-004 Chat Provider 已通过 DEC-G6-003/004 / EVID-032/034 条件性应用为 DeepSeek API / `deepseek-flash`；Embedding=local BGE、Vector=local embedded direction、Cost policy=USD 5，runtime disabled。
- PROVIDER_DECISION_STATUS：APPLIED_CONDITIONAL；DEC-G6-003/004 已应用 Chat 与剩余子决策，但 EVID-033 DeepSeek Guard BLOCKED、本地 Spike/成本实现未完成、runtime disabled、OPEN-01 仍阻断。
- 唯一 G6 出口阻断：OPEN-01 的 DeepSeek API 数据处理/保留/训练/删除/地域条款、账号/模型/余额、成本运行门禁；本地 Embedding/Vector Spike 仍需完成。
- 已创建总体技术架构 Draft、G6 评审记录和 REQ→Page/Mode→Architecture→Data/NFR/Security→Decision/Evidence 追踪。
- 禁止：PRD 范围变更、真实 Provider 调用、代码/DDL/API/脚手架、G7、依赖安装、Git commit/tag/push。
- Chat Provider/模型、local BGE Embedding、本地嵌入式 Vector 方向和 USD 5 成本政策已有 DEC-G6-003/004 条件性基线，但 API 条款、账号/模型/余额、地区、成本运行门禁和本地 Spike 仍未通过；前后端技术栈、数据库具体产品、流式协议仍按项目文档保持 TBD。
- 决策工作流：`V3.2_IMMEDIATE_APPLY`；不要求二次确认或用户 `DECISION_APPLY`；每轮最多 5 个独立决策；已应用决策进入 `decisions/REVIEW_BACKLOG.md`。
- 本轮迁移记录：`docs/project/baseline/DECISION_WORKFLOW_MIGRATION.md`；历史二次确认记录保持不变。

## Token 与上下文规则

- 本轮按 G6 输入要求采用 TARGETED 读取，复用未变化的 Approved PRD 和 G5.5 Evidence。
- 优先复用本摘要和 governance/CONTEXT_INDEX.yaml。
- 只有来源变化、摘要失效或证据不足时才扩大读取。
- 注册表状态 PARTIAL：当前 Codex 主机能力元数据可验证 gpt-6-astra、gpt-5.6-sol、gpt-5.6-terra、gpt-5.6-luna、gpt-5.5；gpt-6-pro 和 gpt-5.6-sol-pro 保持 enabled=false、availability=TBD。
- MODEL_ROUTING_MODE=RECOMMEND_ONLY，MODEL_COST_LIMIT=TBD；G6 本轮未执行底层模型切换，ACTUAL_MODEL_ID=TBD，路由日志 routing_records 仍为空。

## 模型路由状态

- 当前平台：CHATGPT_CODEX。
- 当前任务：G6 总体技术架构 Draft/门禁。
- 建议思考程度：HIGH。
- 当前模型注册表：PARTIAL；成本上限 TBD。
- 底层模型切换：未执行。
- 跨 Provider 切换：禁用。

## 决策流程状态

- `DECISION_WORKFLOW_VERSION=V3.2_IMMEDIATE_APPLY`
- `SECOND_CONFIRMATION_REQUIRED=false`
- `USER_DECISION_APPLY_COMMAND_REQUIRED=false`
- `MAX_DECISIONS_PER_ROUND=5`
- `REVIEW_BACKLOG_ENABLED=true`
- `TECH_ARCHITECTURE_GATES_PRESERVED=true`
- `CHAT_PROVIDER=DEEPSEEK_API`
- `CURRENT_CHAT_MODEL=deepseek-flash`
- `EMBEDDING_DECISION_STATUS=APPLIED_CONDITIONAL_SPIKE_REQUIRED`
- `PROVIDER_CHANGE_STATUS=APPLIED_CONDITIONAL`
- `EMBEDDING_PROVIDER=LOCAL`
- `CURRENT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5`
- `VECTOR_STORE_STRATEGY=LOCAL_EMBEDDED_ADAPTER`
- `COST_POLICY_STATUS=APPLIED_NOT_IMPLEMENTED`
