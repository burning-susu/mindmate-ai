# Mindmate AI 项目文档指南
> 文档编号：DOC-GUIDE-001
> 文档版本：v1.1
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 生效条件：当前项目
> 创建日期：2026-09-20
> 更新时间：2026-09-20
> 关联来源：AGENTS.md、doc/governance/通用文档提示词v3.2.md

## 事实与指令分离

本项目文档必须区分以下内容：

- 项目事实：来自业务资料、当前代码、配置、契约或运行证据。
- 用户确认决策：当前流程来自用户明确的 `决策ID=方案` 选择并在同轮自动应用；历史记录中的二次确认仍作为审计事实保留。
- 操作指令：来自启动提示词或本轮提示词，只约束 AI 如何工作，不自动成为业务事实。
- 通用参考：来自 doc/governance、doc/capabilities、doc/rules 和 doc/handbook，只提供方法，不自动成为项目结论。
- TBD：当前无法由项目事实或用户确认确定的内容。

第二轮提示词中的“已确认决策”是对当前会话确认结果的结构化输入，不是独立业务资料。实际决策证据引用当前会话确认记录，并由 EVID-004 登记。

## Single Source of Truth

- 原始业务资料：项目业务资料/需求文档/
- 原始设计资料：项目业务资料/设计文件/
- 来源总登记：sources/SOURCE_REGISTER.md
- G2 来源和决策基线：baseline/
- 项目画像：governance/PROJECT_PROFILE.yaml
- 治理评估：governance/ASSESSMENT.yaml
- Capability 激活：governance/CAPABILITY_ACTIVATION.yaml
- 候选流程：governance/WORKFLOW_BLUEPRINT.yaml
- 当前运行上下文：governance/RUNTIME_CONTEXT.md
- 项目决策：decisions/README.md 和 decisions/ 下对应 DEC
- 待复核清单：decisions/REVIEW_BACKLOG.md
- 决策流程迁移记录：baseline/DECISION_WORKFLOW_MIGRATION.md

衍生文档只能引用上述事实源，不得复制出第二份业务规则、API 契约或技术栈事实。

## 写入和状态规则

- G2 只生成项目治理和基线文件，不生成代码、脚手架、API 实现或最终架构。
- 未确认的技术选择必须保持 TBD。
- WORKFLOW_STATUS 在用户确认前保持 PROPOSED；完成确认落盘后才可变为 CONFIRMED。
- 本目录的 active 不代表 PRD、架构或发布已批准。
- 需求、架构、API、数据、UI 或验收范围发生变化时，先登记变更并执行影响分析。

### 即时决策应用

- 每轮最多展示 5 个彼此独立的决策；用户可以逐行回复多个 `决策ID=方案`。
- 明确选择后同轮内部写入并同步 DEC/ADR/CR/UI-DEC、基线、Evidence、Runtime、Trace 和开放项。
- 不要求二次确认，不要求用户输入 `DECISION_APPLY`；应用结果报告不是新的确认门禁。
- `REVIEW_BACKLOG` 用于后续集中复核，不替代 G6/G7、`MANDATORY`、`TECH_DECISION` 或安全停止条件。

## v3.2.4 任务前上下文治理

当前仓库实际读取的通用治理文档为主文档 v3.2.7、完整使用说明 v3.2.5；后续每次具体任务开始前必须：

1. 读取当前 Runtime Context、governance/CONTEXT_INDEX.yaml 和可复用的 context-summaries/。
2. 设置 CONTEXT_LOADING_MODE、TOKEN_BUDGET_LEVEL 和 DISCOVERY_MODE。
3. 默认最小读取、优先复用 CURRENT 摘要、先索引后深读。
4. 只对版本变化、状态为 STALE 或摘要覆盖不足的资源重新读取。
5. Token 节约不得省略事实核验、权限、安全、生产和阶段门禁。

本轮核对的更新内容包括模型路由与“即时决策应用”。模型路由仍遵循当前 registry、实际可验证能力和 no-call 约束；不能以治理文档中的候选模型或 Provider 名称替代运行证据。项目 Provider runtime 仍按 G6 guards 保持禁用。

上下文索引和摘要的项目入口：

- governance/CONTEXT_INDEX.yaml
- governance/context-summaries/

## 证据规则

任何完成声明必须引用 EVIDENCE_REGISTER.yaml 中的证据编号。文件创建只能证明文件产出，不能证明 PRD 已批准、代码已完成、测试已通过或产品已发布。
