# Mindmate AI 项目文档
> 文档编号：DOC-PROJECT-INDEX-001
> 文档版本：v1.2
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 生效条件：当前项目
> 创建日期：2026-09-20
> 更新时间：2026-09-21
> 关联来源：SRC-001 至 SRC-007
> 关联决策：HIGH-01 至 LOW-02、DEC-G6-001 至 DEC-G6-003

## 文档定位

本目录是 mindmate-ai 的项目专属文档根目录。它记录当前项目的来源登记、决策基线、项目画像、治理评估、Capability 激活和 Workflow。仓库根目录的 AGENTS.md 与 doc/ 下的通用治理资产仍然是方法和路由来源，本目录才记录本项目已经确认或明确保留为 TBD 的内容。

G1/G2/G3/G4/G5/G5.5 已按证据完成；PRD v1.0-Draft.3 已批准。当前项目仍处于 BOOTSTRAP 代码基线，Workflow 已确认；G6 已通过入口核验并生成总体架构 Draft，但 OPEN-01 阻断 G6 正式出口。

## 当前状态

- PROJECT_STAGE：BOOTSTRAP
- CURRENT_STAGE：G6 总体技术架构（BLOCKED）
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
- G6_ENTRY_GATE：READY
- G6_ENTRY_VERIFICATION：PASSED
- TECH-DEC-004：DEC-G6-003/004 已条件性应用 DeepSeek API / `deepseek-flash`、本地 BGE Embedding、本地嵌入式向量存储方向和成本政策；Provider runtime disabled，DEC-G6-001 no-call guards 保持有效
- G6_STATUS：BLOCKED（EVID-033 DeepSeek Guard Verification 未通过；OPEN-01 guards 未决）
- PROVIDER_DECISION_STATUS：APPLIED_CONDITIONAL；DEC-G6-003/004 Chat=DeepSeek API、Embedding=Local BGE、Vector=Local Embedded Direction，Guard/Spike 仍未完成，runtime disabled
- ARCHITECTURE_STATUS：DRAFT
- G7_ENTRY_GATE：NOT_READY
- G7_EXECUTION：NOT_STARTED
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
- RUNTIME_WORK_MODE：DOCUMENT_WRITE（仅本轮项目治理文档）
- CODE_BASELINE_MODE：NONE
- 本轮未修改代码、脚手架或依赖；未执行 Git commit/tag/push

当前 Provider/技术决策记录：[`DEC-G6-003.md`](decisions/DEC-G6-003.md)、[`DEC-G6-004.md`](decisions/DEC-G6-004.md)、[`G6_DEEPSEEK_PROVIDER_CHANGE_REVIEW.md`](baseline/G6_DEEPSEEK_PROVIDER_CHANGE_REVIEW.md)、[`12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md`](baseline/12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md)。

## 决策工作流

用户明确回复 `决策ID=方案` 后，系统在同一轮内部完成应用和同步，不再要求二次确认或用户单独输入 `DECISION_APPLY`。每轮最多处理 5 个彼此独立的决策；已应用决策进入 [`decisions/REVIEW_BACKLOG.md`](decisions/REVIEW_BACKLOG.md)。历史决策中的二次确认记录保留为审计事实。

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
11. architecture/SYSTEM_ARCHITECTURE.md
12. baseline/09_G6_ARCHITECTURE_REVIEW.md

## 状态边界

- 本目录中的已确认决策记录的是用户确认的项目方向，不等同于 Approved PRD、最终技术架构或已发布系统。
- Provider Chat 基线已由 DEC-G6-003/004 条件性应用为 DeepSeek API / `deepseek-flash`；Alibaba Chat 路线由 DEC-G6-002 保留为历史；Embedding、本地向量存储方向和成本政策已应用但 Spike/运行实现未完成，API 数据条款、账号资格、地区可用性和 Provider guards 未通过；Provider runtime 仍禁用。前后端框架、数据库具体产品、文件上传协议和流式协议仍以 TBD 记录。
- Workflow 已确认；G3/G4/G5/G5.5 已完成。PRD v1.0-Draft.3 为 Approved。
- G6 已生成供应商无关架构 Draft；DeepSeek Chat 的条件性基线已记录，但 Embedding、API 数据条款、账号资格、地区可用性和成本 guards 未确认，G6 Exit 与 G7 入口保持阻断。
- Provider、数据库和向量产品、流式协议、备份技术细节仍按相应 TECH-DEC/OPEN ITEM 保持 TBD。
- 原始 DOCX、Figma 和 Sketch 文件继续保留在 项目业务资料/，不复制到本目录。
