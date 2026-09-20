# Mindmate AI 项目文档
> 文档编号：DOC-PROJECT-INDEX-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 生效条件：当前项目
> 创建日期：2026-09-20
> 更新时间：2026-09-20
> 关联来源：SRC-001 至 SRC-007
> 关联决策：HIGH-01 至 LOW-02

## 文档定位

本目录是 mindmate-ai 的项目专属文档根目录。它记录当前项目的来源登记、决策基线、项目画像、治理评估、Capability 激活和 Workflow。仓库根目录的 AGENTS.md 与 doc/ 下的通用治理资产仍然是方法和路由来源，本目录才记录本项目已经确认或明确保留为 TBD 的内容。

本轮 G2 已完成来源盘点、用户决策持久化、来源/决策基线生成和 Workflow 确认落盘。当前项目仍处于 BOOTSTRAP，Workflow 已确认，但 G3 尚未开始。

## 当前状态

- PROJECT_STAGE：BOOTSTRAP
- CURRENT_STAGE：G2 来源和决策基线
- G1_SOURCE_REGISTER：COMPLETED
- G2_BASELINE：COMPLETED
- G2_EXIT：PASSED_WORKFLOW_CONFIRMED
- WORKFLOW_ID：WF-MINDMATE-001
- WORKFLOW_VERSION：0.1
- WORKFLOW_STATUS：CONFIRMED
- WORKFLOW_CONFIRMATION：COMPLETED
- RUNTIME_WORK_MODE：DOCUMENT_WRITE（仅本轮项目治理文档）
- CODE_BASELINE_MODE：NONE
- 代码、脚手架、依赖、Git 提交：本轮未修改

## 阅读顺序

1. sources/SOURCE_REGISTER.md
2. baseline/01_SOURCE_INVENTORY.md
3. baseline/02_DECISION_BASELINE.md
4. baseline/04_CONFLICT_MATRIX.md
5. governance/PROJECT_PROFILE.yaml
6. governance/ASSESSMENT.yaml
7. governance/CAPABILITY_ACTIVATION.yaml
8. governance/WORKFLOW_BLUEPRINT.yaml
9. governance/RUNTIME_CONTEXT.md
10. decisions/DEC-BOOTSTRAP-001.md

## 状态边界

- 本目录中的已确认决策记录的是用户确认的项目方向，不等同于 Approved PRD、最终技术架构或已发布系统。
- 具体 Provider、模型、Embedding 模型、前后端框架、数据库、向量存储、文件上传协议和流式协议仍以 TBD 记录。
- Workflow 已确认，但 G3 PRD 准入审计尚未启动。
- G3 入口门禁已满足；进入 G3 仍需单独执行 G3 提示词，不因本轮确认自动执行。
- 原始 DOCX、Figma 和 Sketch 文件继续保留在 项目业务资料/，不复制到本目录。
