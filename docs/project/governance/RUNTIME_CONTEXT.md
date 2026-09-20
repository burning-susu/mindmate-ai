# Mindmate AI 当前 Runtime Context
> 文档编号：RUNTIME-CONTEXT-MINDMATE-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 创建日期：2026-09-20
> 更新时间：2026-09-20
> 关联 Workflow：WF-MINDMATE-001 v0.1
> 关联阶段：G2

## 当前上下文

- PROJECT_SCENARIO：NEW_PROJECT
- PROJECT_STAGE：BOOTSTRAP
- CURRENT_STAGE：G2
- CURRENT_STAGE_LEVEL：L2
- WORKFLOW_STATUS：CONFIRMED
- RUNTIME_WORK_MODE：DOCUMENT_WRITE
- RUNTIME_PERMISSION_PROFILE：PROJECT_DOCUMENTS_ONLY
- CODE_BASELINE_MODE：NONE
- ASSESSMENT_STATUS：COMPLETED
- G1_SOURCE_REGISTER：COMPLETED
- G2_BASELINE：COMPLETED
- WORKFLOW_CONFIRMATION_GATE：PASSED
- G3_STATUS：NOT_STARTED
- G3_ENTRY_GATE：READY
- G3_EXECUTION：NOT_STARTED

## v3.2.4 Token 与上下文治理

- ENABLE_TOKEN_GOVERNANCE：true
- CONTEXT_LOADING_MODE：MINIMAL
- TOKEN_BUDGET_LEVEL：MEDIUM
- ALLOW_FULL_CONTEXT_SCAN：false
- REUSE_CONTEXT_SUMMARY：true
- SKIP_UNCHANGED_RESOURCES：true
- DISCOVERY_MODE：TARGETED
- CONTEXT_INDEX：governance/CONTEXT_INDEX.yaml
- CONTEXT_SUMMARIES：governance/context-summaries/

本次任务范围是 Workflow 确认落盘和状态同步。必读资源为当前 Workflow、Runtime Context、Evidence Register、项目入口和两份已更新通用治理文档；已复用 G2 来源/决策基线，不重新读取未受影响的 DOCX、Figma、Sketch 和全部通用 Capability。两份通用治理文档的实际新增内容是 Token/上下文节约治理，未发现独立模型自动切换规则。

## 本轮允许写入

- docs/project/ 下项目专属治理、来源、基线、决策和证据文件。
- 与本轮 G1/G2 输出直接相关的项目文档。

## 本轮禁止动作

- 不修改 AGENTS.md。
- 不修改 doc/ 下通用治理、规则、Capability、手册或模板。
- 不创建或修改前端、后端、测试、数据库、API 实现或项目脚手架。
- 不安装依赖。
- 不修改生产配置、真实凭据或真实数据。
- 不启动 G3 PRD 准入审计；本轮只清除 Workflow 确认入口门禁。
- 不生成最终技术架构、最终开发计划或开发批次。

## 当前阶段有效 Capability

本轮只加载与 G2 相关的来源、决策和评估方法。技术架构 Capability 仅用于登记 TBD 和后续触发条件；UI、API、自动化测试、安全和性能 Capability 的正式执行按 WORKFLOW_BLUEPRINT 中的阶段进入，不在本轮执行。

## 退出条件

满足以下条件后停止：

1. SOURCE_REGISTER 已更新。
2. 10 项决策已持久化并可追溯到 EVID-004。
3. PROJECT_PROFILE、ASSESSMENT 和 CAPABILITY_ACTIVATION 已生成。
4. G2 基线文件和冲突矩阵已生成。
5. WORKFLOW_BLUEPRINT 为 CONFIRMED。
6. G3 入口门禁已满足，但 G3 尚未执行。
