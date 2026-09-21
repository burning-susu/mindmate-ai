# 项目治理文件
> 文档编号：GOV-DIR-README-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active

本目录保存项目画像、治理评估、Capability 激活、Workflow、阶段策略、Runtime Context 和 Evidence 登记。

- PROJECT_PROFILE.yaml：项目是什么。
- ASSESSMENT.yaml：项目复杂度、风险和触发条件。
- CAPABILITY_ACTIVATION.yaml：按触发条件启用的专项能力。
- WORKFLOW_BLUEPRINT.yaml：本项目已确认的 G0-G11 执行蓝图。
- STAGE_POLICY.yaml：每个阶段的执行深度和门禁。
- RUNTIME_CONTEXT.md：当前任务的工作模式、允许写入和禁止动作。
- EVIDENCE_REGISTER.yaml：完成声明的证据索引。
- CONTEXT_INDEX.yaml：当前治理资源、摘要和哈希索引。
- context-summaries/：可复用的最小上下文摘要。

决策交互版本由 `RUNTIME_CONTEXT.md` 和 `WORKFLOW_BLUEPRINT.yaml` 中的 `V3.2_IMMEDIATE_APPLY` 字段定义；迁移记录位于 `../baseline/DECISION_WORKFLOW_MIGRATION.md`，已应用决策的后续复核位于 `../decisions/REVIEW_BACKLOG.md`。
