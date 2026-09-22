# 决策工作流迁移记录
> 文档编号：DECISION-WORKFLOW-MIGRATION-MINDMATE-001
> 文档版本：v1.0
> 文档类型：governance / migration record
> 关联对象：PROJECT mindmate-ai
> 状态：COMPLETED
> 创建日期：2026-09-21
> 更新时间：2026-09-21

## 1. 迁移结论

本轮已将项目级决策入口迁移为 `V3.2_IMMEDIATE_APPLY`：用户对明确的 `决策ID=方案` 作出选择后，系统在同一轮内部完成应用和同步，并将已应用决策登记到 `docs/project/decisions/REVIEW_BACKLOG.md`。本轮只迁移流程和项目治理状态，不修改业务代码，不调用 Provider，不读取或验证 Secret，也不执行 Git commit、tag 或 push。

当前 G6 状态没有因流程迁移而改变：`G6_STATUS=BLOCKED`、`OPEN-01=G6_EXIT_BLOCKER`、`PROVIDER_RUNTIME_ENABLED=false`、`G7_ENTRY_GATE=NOT_READY`。

## 2. 实际规则源

本轮提示词要求查找以下名称：

- `svg通用文档提示词v3.2.md`
- `svg通用文档提示词v3.2完整使用说明.md`

仓库和当前项目目录未找到带 `svg` 前缀的文件。按提示词要求通过仓库搜索定位后，确认当前唯一匹配的治理源为：

| 请求名称 | 实际读取路径 | 版本 | SHA-256 | 状态 |
|---|---|---|---|---|
| `svg通用文档提示词v3.2.md` | `doc/governance/通用文档提示词v3.2.md` | v3.2.7 | `902C8C9F1C783742CB56AE803022FE0423D45D90B8AA9399606A9236ED265E25` | CURRENT |
| `svg通用文档提示词v3.2完整使用说明.md` | `doc/governance/通用文档提示词v3.2完整使用说明.md` | v3.2.5 | `DB0AC53C5C76A098356B8951A6C115EE567C7D9AEF4DD116EA9ADC389CA86A2A` | CURRENT |

两份实际治理源的当前正文均包含“一次选择、当轮自动应用”、每轮最多 5 个独立决策、`决策ID=方案` 多项回复和 `REVIEW_BACKLOG` 规则。名称映射是本轮事实记录，不把不存在的 `svg` 文件伪造为新文件。

### 规则源内部的精确冲突

- 主文档 v3.2.7 顶部的 v3.2.7 迭代说明和第 14 节附近正文已经定义即时应用；但同一文件 v3.2.6 历史迭代说明仍写着“用户初选→影响复述→二次确认→受控应用”、高影响每轮 1 项（约第 114-120 行）。
- 完整使用说明 v3.2.5 顶部的 v3.2.5 说明、第 2A/2B 之后的 `USER_SELECTION_AND_AUTO_APPLY` 流程（约第 444-478 行）定义即时应用；同一文件较早的旧摘要（约第 93-96 行）仍写着 `INFORMED_REVIEW → INFORMED_CONFIRMATION → DECISION_APPLY` 和高影响每轮 1 项。
- 本轮按来源内部的版本迭代顺序采用两份文档各自最新版本说明和即时应用正文；旧段落不删除、不改写，并登记为待复核冲突。若后续需要修复通用库，应另行提交治理变更，不在本项目迁移中静默修改 `doc/`。

## 3. 生效的项目级规则

```text
DECISION_WORKFLOW_VERSION=V3.2_IMMEDIATE_APPLY
SECOND_CONFIRMATION_REQUIRED=false
USER_DECISION_APPLY_COMMAND_REQUIRED=false
MAX_DECISIONS_PER_ROUND=5
REVIEW_BACKLOG_ENABLED=true
TECH_ARCHITECTURE_GATES_PRESERVED=true
```

后续执行约束如下：

1. AI 先展示不超过 5 个彼此独立的候选决策；存在依赖或互斥关系时必须显式说明，并按依赖关系分批。
2. 用户回复一个或多个明确的 `决策ID=方案` 后，该选择即构成当前项的确认和应用授权。
3. 系统在同一轮内部执行 `DECISION_APPLY`（包括创建或更新 DEC/ADR/CR/UI-DEC、同步基线、Evidence、Runtime、Trace 和开放项），不得再要求用户输入该口令。
4. 应用完成后进入 `REVIEW_BACKLOG`；待复核不等于第二次确认，也不自动阻塞普通 Draft 或开发。
5. 高风险、难回退项在进入 Approved、Baselined 或生产发布前集中复核；发现需要改变方案时走正式变更链，不覆盖历史记录。
6. 凭证泄露、数据破坏、违法风险、生产事故以及 `OPEN-01` 这类架构出口阻断仍是即时停止或阶段门禁，不得塞入非阻断 backlog 后继续推进。

## 4. 旧规则迁移清单

| 旧内容 | 分类 | 本轮处理 |
|---|---|---|
| 当前项目后续决策要求二次确认 | 必须修改 | Runtime、Workflow、Assessment、项目决策入口改为一次选择当轮应用 |
| 要求用户单独输入 `DECISION_APPLY` 或“应用并同步” | 必须修改 | 改为系统内部步骤；项目文档不再将其作为用户操作要求 |
| 每轮 1 项或低影响最多 2 项的交互限制 | 必须修改 | 当前项目采用最多 5 个彼此独立决策；依赖/互斥项仍分批 |
| 历史 `EVID-004`、`EVID-025`、`EVID-028`、`DEC-G6-001`、`DEC-G6-002` 等中的二次确认事实 | 只保留历史 | 不改写、不删除；这些记录描述当时真实发生的流程 |
| `doc/capabilities/architecture/technical-selection.md` 的旧二次确认方法 | 待复核冲突 | 本轮不修改 `doc/` 通用 Capability；记录为通用库与新版治理源的待复核冲突 |
| G6/G7、`MANDATORY`、`TECH_DECISION`、依赖/互斥、架构出口门禁 | 必须保留 | 在项目运行字段和本记录中显式保留，未改变门禁语义 |
| 产品中的“删除操作二次确认” | 与本迁移无关 | 这是产品交互安全规则，不是决策工作流确认；不修改 |

## 5. 历史状态处理

本轮只迁移当前运行规则，不批量把历史待确认项标成已批准。已存在的明确用户选择保持原有 DEC 和 Evidence；其中 `DEC-G6-002` 已合法条件性应用，不重新要求选择或二次确认。没有明确、唯一且仍有效用户选择的事项继续保持 `TBD/PENDING`，不得由 AI 补选。

历史的“初选→二次确认→应用”记录继续作为审计证据，不能被改写成即时应用记录。新流程从本迁移记录生效时间起用于后续用户选择。

## 6. G6/G7 与 Provider 边界

- `DEC-G6-001` 的 no-call 边界继续有效。
- `DEC-G6-002` 的 Alibaba Cloud Model Studio 条件性基线继续有效；Provider runtime 仍禁用。
- 数据处理/保留/训练条款、账号资格、地区可用性、模型目录和成本防护未全部核验，`OPEN-01` 仍阻断 G6 Exit。
- 不因即时应用规则迁移而设置 `ARCHITECTURE_STATUS=APPROVED`、`G6_STATUS=COMPLETED` 或 `G7_ENTRY_GATE=READY`。

## 7. 校验与证据

本轮新增 `EVID-031`，证明规则源映射、即时应用字段、Review Backlog 和状态边界已同步。校验范围包括项目 YAML 解析、Context Index 资源存在与哈希一致、Markdown 引用目标、`git diff --check`、Secret 扫描和 Provider no-call 边界。

## 8. 后续入口

- 决策交互规则：`docs/project/decisions/README.md`
- 待复核清单：`docs/project/decisions/REVIEW_BACKLOG.md`
- 当前运行字段：`docs/project/governance/RUNTIME_CONTEXT.md`
- 当前流程蓝图：`docs/project/governance/WORKFLOW_BLUEPRINT.yaml`
