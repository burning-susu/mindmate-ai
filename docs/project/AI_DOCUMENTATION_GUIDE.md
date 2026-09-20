# Mindmate AI 项目文档指南
> 文档编号：DOC-GUIDE-001
> 文档版本：v1.0
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
- 用户确认决策：来自当前会话中完成二次确认并授权应用的决策。
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
- 项目决策：decisions/DEC-BOOTSTRAP-001.md

衍生文档只能引用上述事实源，不得复制出第二份业务规则、API 契约或技术栈事实。

## 写入和状态规则

- G2 只生成项目治理和基线文件，不生成代码、脚手架、API 实现或最终架构。
- 未确认的技术选择必须保持 TBD。
- WORKFLOW_STATUS 在用户确认前保持 PROPOSED；完成确认落盘后才可变为 CONFIRMED。
- 本目录的 active 不代表 PRD、架构或发布已批准。
- 需求、架构、API、数据、UI 或验收范围发生变化时，先登记变更并执行影响分析。

## v3.2.4 任务前上下文治理

当前仓库的通用治理文档已更新到 v3.2.4（完整使用说明配套版本为 v3.2.2），后续每次具体任务开始前必须：

1. 读取当前 Runtime Context、governance/CONTEXT_INDEX.yaml 和可复用的 context-summaries/。
2. 设置 CONTEXT_LOADING_MODE、TOKEN_BUDGET_LEVEL 和 DISCOVERY_MODE。
3. 默认最小读取、优先复用 CURRENT 摘要、先索引后深读。
4. 只对版本变化、状态为 STALE 或摘要覆盖不足的资源重新读取。
5. Token 节约不得省略事实核验、权限、安全、生产和阶段门禁。

本轮核对的更新内容实际是“AI Token 与上下文节约治理”；在两份通用治理文档中未发现独立的“模型自动切换”字段、规则或 Provider 路由定义。模型选择、Provider 路由和具体技术实现仍须保持 TBD，不得根据这句描述自行补全。

上下文索引和摘要的项目入口：

- governance/CONTEXT_INDEX.yaml
- governance/context-summaries/

## 证据规则

任何完成声明必须引用 EVIDENCE_REGISTER.yaml 中的证据编号。文件创建只能证明文件产出，不能证明 PRD 已批准、代码已完成、测试已通过或产品已发布。
