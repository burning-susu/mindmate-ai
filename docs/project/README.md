# Mindmate AI 项目文档
> 文档编号：DOC-PROJECT-INDEX-001
> 文档版本：v2.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 生效条件：当前项目
> 创建日期：2026-09-20
> 更新时间：2026-09-22
> 关联来源：docs/project/requirements/v1/00–18、项目业务资料/
> 关联决策：docs/project/requirements/v1/18_最终决策表.md

## 文档定位

本目录是 mindmate-ai 的项目专属文档根目录。当前 V1 开发以 `docs/project/requirements/v1/` 的 00–18 规格为唯一需求输入；仓库根目录的 AGENTS.md 与 doc/ 下的通用治理资产提供方法和路由。旧的多轮 G6 治理文档已归档到 `docs/archive/2026-09-22-pre-v1/`，只用于追溯。

V1 需求规格已冻结并进入代码开发；当前仓库仍处于脚手架建立前的开发预备状态。

## 当前状态

- PROJECT_STAGE：DEVELOPMENT
- CURRENT_STAGE：DEVELOPMENT
- G1_SOURCE_REGISTER：COMPLETED
- G2_BASELINE：COMPLETED
- G2_EXIT：PASSED_WORKFLOW_CONFIRMED
- G3_STATUS：PASSED
- G4_ENTRY_GATE：READY
- G4_STATUS：COMPLETED
- PRD_STATUS：APPROVED
- G5_ENTRY_GATE：READY
- G5_REVIEW_STATUS：COMPLETED
- PRD_APPROVAL_GATE：COMPLETED
- G5_APPROVAL_STATUS：COMPLETED
- G5_5_STATUS：COMPLETED
- DEVELOPMENT_BASELINE：ESTABLISHED
- REQUIREMENTS_BASELINE：docs/project/requirements/v1/18_最终决策表.md
- DEVELOPMENT_TASKS：docs/project/requirements/v1/16_Codex开发任务书.md
- TECHNICAL_CONSTRAINTS：docs/project/requirements/v1/15_技术架构与开发约束.md
- PROVIDER_RUNTIME：MOCK_ONLY_FOR_DEVELOPMENT
- REAL_PROVIDER_CALLS：DISABLED
- DECISION_WORKFLOW_VERSION：V3.2_IMMEDIATE_APPLY
- SECOND_CONFIRMATION_REQUIRED：false
- USER_DECISION_APPLY_COMMAND_REQUIRED：false
- MAX_DECISIONS_PER_ROUND：5
- REVIEW_BACKLOG_ENABLED：true
- TECH_ARCHITECTURE_GATES_PRESERVED：true
- WORKFLOW_ID：WF-MINDMATE-001
- WORKFLOW_VERSION：0.1
- WORKFLOW_STATUS：CONFIRMED
- WORKFLOW_CONFIRMATION：COMPLETED
- RUNTIME_WORK_MODE：CODE_DEVELOPMENT
- CODE_BASELINE_MODE：V1_BOOTSTRAP
- BASELINE_TAG：baseline/pre-v1-rebaseline-2026-09-22
- 本轮已建立开发分支、保护 tag 和文档基线提交；未执行 push

当前开发基线：[`DEVELOPMENT_BASELINE.md`](DEVELOPMENT_BASELINE.md)。历史 Provider/技术决策记录位于 [`docs/archive/2026-09-22-pre-v1/`](../archive/2026-09-22-pre-v1/)，不作为当前开发入口。

## 当前开发入口

1. [`requirements/v1/18_最终决策表.md`](requirements/v1/18_最终决策表.md)：最终冻结选择。
2. [`requirements/v1/16_Codex开发任务书.md`](requirements/v1/16_Codex开发任务书.md)：阶段、测试和提交节点。
3. [`requirements/v1/00_需求规格总纲.md`](requirements/v1/00_需求规格总纲.md)：总纲和范围。
4. [`requirements/v1/15_技术架构与开发约束.md`](requirements/v1/15_技术架构与开发约束.md)：架构和安全边界。

## 阅读顺序

1. requirements/v1/18_最终决策表.md
2. requirements/v1/16_Codex开发任务书.md
3. requirements/v1/00_需求规格总纲.md
4. requirements/v1/15_技术架构与开发约束.md
5. requirements/v1/01–14 专题规格
6. 当前代码、配置和测试证据
7. governance/RUNTIME_CONTEXT.md
8. DEVELOPMENT_BASELINE.md
9. ../archive/2026-09-22-pre-v1/（仅追溯）

## 状态边界

- 00–18 规格是当前开发事实源；历史治理文档不再参与当前决策。
- Provider Runtime 在开发和自动化测试中使用 Mock Provider；真实 DeepSeek API 仅在明确的连接/发布流程中处理。
- 原始 DOCX、Figma 和 Sketch 文件继续保留在 `项目业务资料/`，不移动、不修改。
- 旧项目治理文档完整保存在 `docs/archive/2026-09-22-pre-v1/`。
