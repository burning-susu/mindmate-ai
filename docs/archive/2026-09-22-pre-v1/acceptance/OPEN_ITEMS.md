# Mindmate AI G4 开放项
> 文档编号：OPEN-ITEMS-MINDMATE-001
> 文档版本：v1.1-Draft.1
> 文档类型：acceptance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 关联 PRD：PRD-MINDMATE-V1

| 编号 | 类型 | 内容 | 当前处理 | 最晚阶段 | 是否阻断 G5 |
|---|---|---|---|---|---|
| G3-MAJOR-001 | CARRY_FORWARD_NON_BLOCKING | Provider 不可用、限流、Key 错误、Embedding 失败和重试语义 | PRD 已描述用户可观察行为，具体错误码/策略 TBD | G8/G9 | 不阻断 G5；技术设计前闭合 |
| G3-MAJOR-002 | CARRY_FORWARD_NON_BLOCKING | 本地备份、保留、恢复和卸载风险 | DEC-G5-001 已确认 V1 提供轻量本地导出/备份和恢复，技术细节 TBD | G6/G10 | 不阻断 PRD 批准，技术设计前闭合 |
| G3-MAJOR-003 | CARRY_FORWARD_NON_BLOCKING | AI 质量评测集和阈值 | 建立固定小型资料集和人工评审表的 Proposed 方案 | G4/G11 | 不阻断 G5；进入测试/验收基线 |
| G3-MAJOR-004 | CARRY_FORWARD_NON_BLOCKING | 删除、重索引、恢复和索引版本 | PRD 固化 V1 删除边界，技术状态机 TBD | G4/G8 | 不阻断 G5；技术设计前闭合 |
| TBD-PRD-001 | PARTIAL_CONDITIONAL | Chat Provider/模型已由 DEC-G6-003/004 条件性应用为 DeepSeek API / `deepseek-flash`；Embedding 已选本地 BGE 方向，API 条款、地域、账号和 Runtime Guard 仍未通过 | DEC-G6-003、DEC-G6-004；继续 no-call | G6 | 是 |
| TBD-PRD-002 | TBD | 前后端语言和框架 | 保持 TBD | G6/G9 | 否 |
| TBD-PRD-003 | PARTIAL_DIRECTIONAL | 解析器和本地向量存储 | 本地嵌入式向量存储 + Storage Adapter 方向已由 DEC-G6-004 应用；具体产品、解析器和 Spike TBD | G8/G9 | 否 |
| TBD-PRD-004 | TBD | 上传、异步状态和流式协议 | 保持 TBD | G8/G9 | 否 |
| TBD-PRD-005 | TBD | URL、路由字符串、组件拆分和 Design Token | 保持 TBD | G5.5/G9.1 | 否 |
| TBD-PRD-006 | TBD | 本地备份、恢复、保留周期和卸载风险 | 保持 TBD | G6/G10 | 需在批准前有边界 |
| TBD-PRD-007 | TBD | AI 质量评测集和验收阈值 | 保持 TBD，禁止编造百分比 | G4/G11 | 需进入测试/验收基线 |
| TBD-PRD-008 | TBD | 负责人、目标发布日期和开发工期 | 保持 TBD | G10 | 否 |
| TBD-PRD-009 | TBD | 重复文件是否允许另存为新文件 | 当前只确认重复提示和跳过 | G5/G8 | 影响文件规则和验收 |

## G5 评审状态

- G5-BLOCKER-001：已由 DEC-G5-001 应用；本地备份/恢复方向确认，技术细节继续 TBD。
- G3-MAJOR-001：PRD 已写入用户可观察失败行为，具体错误码和重试策略留 G8/G9，不阻断本次批准门禁。
- G3-MAJOR-003：PRD 已写入评测集和人工评审表要求，指标阈值 TBD，需在 G4/G11 完成，不阻断本次批准门禁。
- G3-MAJOR-004：PRD 已写入删除不可恢复和索引失效边界，重索引技术规则留 G8，不阻断本次批准门禁。

本清单中的 Proposed 方案不是已确认决策。任何改变 V1 业务范围、数据归属、隐私边界或恢复责任的选择，必须重新走知情决策协议。

## G6 架构出口与责任阶段

上表“是否阻断 G5”是历史 G5 门禁字段。G6 当前状态单独记录如下：

| 编号 | 类型 | 内容 | 当前处理 | 最晚阶段 | 对当前阶段的影响 |
|---|---|---|---|---|---|
| TECH-DEC-004 / OPEN-01 / TBD-PRD-001 | HIGH / G6_EXIT_BLOCKER | DeepSeek Chat Provider、Embedding、处理地域、留存/训练条款、账号资格和成本边界 | DEC-G6-003/004 已条件性应用 Chat=DeepSeek API / `deepseek-flash`、local BGE、向量方向和成本政策；EVID-033 Guard 仍 BLOCKED，运行时禁用，API 条款、账号资格、地区、成本实现和本地 Spike 未完成 | G6 正式出口前 | 阻断 G6 Exit 与 G7 入口 |
| TECH-G6-EMBEDDING | HIGH / G6_EXIT_BLOCKER | Embedding Provider/模型与本地数据出站边界 | `DEC-G6-004` 已应用本地 `BAAI/bge-small-zh-v1.5` 方向；未下载/安装/性能验证，Spike 和质量证据待完成 | G6 Exit / G8 RAG Spike 前 | 阻断依赖 Embedding 的 G6/G7 |
| COST-G6-PROVIDER | HIGH / G6_EXIT_BLOCKER | 月预算、提醒、停止新调用、余额不足和重试策略 | `DEC-G6-004` 已应用 USD 5 软预算、USD 4 提醒、USD 5 停止和禁自动充值/提额政策；计数与运行时停止尚未实现 | G6 正式出口前 | 阻断运行时启用和 G6 Exit |
| TECH-DEC-005 / TECH-G6-VECTOR-STORE / OPEN-02 / TBD-PRD-003 | DEFERABLE | 本地元数据数据库、向量存储产品/类别、解析器及物理共置方式 | `DEC-G6-004` 已应用本地嵌入式向量存储 + `Storage Adapter` 方向；具体产品/类别和 Spike 保持 TBD | G8；早于 G9 数据设计 | 不阻断 G6 Draft；到期未定则阻断依赖该选择的详细设计 |
| TECH-DEC-001 / OPEN-04 | DEFERABLE | OS 支持、安装包、启动器、升级与卸载行为 | 桌面 Web + 本地服务形态成立；具体分发与启动流程 TBD | G10 发布准备前 | 不阻断逻辑架构；用户启动/安装方案确定前不得作发布承诺 |
| TECH-DEC-013 / OPEN-05 / TBD-PRD-002 | DEFERABLE | 前后端语言、框架和工程工具 | 保持 TBD；模块化单体与本地服务边界不锁定具体栈 | G8/G9 | 不阻断当前 Draft；技术规则激活前不得假定栈 |
| TECH-DEC-011 / OPEN-03 / TBD-PRD-004 | DEFERABLE | 上传协议、异步状态 API、流式协议和断线恢复 | REST/OpenAPI 方向确认；协议保持 TBD | G9 API Contract 前 | 不阻断总体逻辑架构；依赖流式/上传实现前必须确认 |
| TECH-DEC-009 / TBD-PRD-006 | DEFERABLE | 备份内容、格式、加密、覆盖/合并、兼容与失败回滚 | 仅确认本地轻量导出/恢复方向；恢复后保留解析、切片、Embedding、索引重建路径 | G8/G10 | 不阻断 G6 Draft；正式恢复实现前必须形成决策 |
| TECH-DEC-012 / TBD-PRD-007 | DEFERABLE | AI 质量评测集、阈值与非功能验证环境 | 不编造指标；保留固定小型资料集和人工评审方向 | G11 验收基线前 | 不阻断 G6；验收前必须有测试证据 |
| TECH-DEC-012 / TBD-PRD-008 | INFORMATIONAL | 负责人、目标发布日期、可投入工时 | 未提供，保持 TBD | G10 计划前 | 不阻断 G6 |

G6 当前状态：`G6_ENTRY_VERIFICATION=PASSED`；`G6_STATUS=BLOCKED`；`ARCHITECTURE_STATUS=DRAFT`；`G7_ENTRY_GATE=NOT_READY`。唯一当前出口阻断为 TECH-DEC-004 / OPEN-01。其余 TBD 不得静默升级为 Confirmed，且须在表中责任阶段解决。
