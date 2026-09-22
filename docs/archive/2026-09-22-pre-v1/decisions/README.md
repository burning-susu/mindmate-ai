# 项目决策目录
> 文档编号：DEC-DIR-README-001
> 文档版本：v1.2
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 创建日期：2026-09-20
> 更新时间：2026-09-21

本目录保存项目级已确认决策。自 `DECISION_WORKFLOW_VERSION=V3.2_IMMEDIATE_APPLY` 生效后，用户对明确的 `决策ID=方案` 作出选择即构成确认和应用授权，系统在同一轮完成 DEC/ADR/CR/UI-DEC 及关联基线同步。历史记录中的“二次确认”和“应用并同步”保留为审计事实，不代表当前仍要求重复确认。

| 决策 | 结论 | 关联阶段 |
|---|---|---|
| DEC-BOOTSTRAP-001 | V1 单用户本地 MVP、外部 Provider Adapter、模块化单体等首版约束 | G2 |
| DEC-G3-001 | 五个一级页面壳、详情嵌套、V1 排除设置/独立错题本 | G3 |
| DEC-G5-001 | 本地轻量备份/恢复，不提供云同步或远程备份 | G5 |
| DEC-G6-001 | Provider 详情确认前禁止真实外部调用；Provider 选择仍 TBD，G6 继续阻断 | G6 |
| DEC-G6-002 | Alibaba Cloud Model Studio / qwen3.8-flash / text-embedding-v4 的条件性 Provider 基线；guards 完成前保持 no-call | G6 |
| DEC-G6-003 | Chat Provider 修订为 DeepSeek API / deepseek-flash；Embedding TBD；guards 完成前保持 no-call | G6 |
| DEC-G6-004 | Chat Model、Embedding、本地向量存储方向和 USD 5 成本政策的四项 G6 批量应用；Spike/运行门禁继续保留 | G6 |

本目录记录用户已确认并受控应用的项目决策，不自动等同于 ADR。DEC-G6-002 的 Alibaba Chat 路线已由 DEC-G6-003 修订替代，但其历史证据仍保留；DEC-G6-004 已应用四项 G6 子决策，但本地 Spike、成本实现、DeepSeek API 数据条款、账号资格和地区 guards 仍未通过，不自动完成 G6 Exit，也不等同于已经启用运行时 Provider。

## 当前决策交互

- 每轮最多展示 5 个彼此独立的决策；有依赖或互斥关系时按依赖分批。
- 用户可一次回复多个选择：

  ```text
  TECH-01=A
  TECH-02=C
  ```

- 明确选择后同轮立即应用；`DECISION_APPLY` 仅是系统内部步骤，不要求用户单独输入。
- 已应用决策进入 [`REVIEW_BACKLOG.md`](./REVIEW_BACKLOG.md)。待复核不等于第二次确认，也不自动解除 G6/G7 门禁。
- `MANDATORY`、`TECH_DECISION` 候选/组合分析、依赖/互斥分析、G6/G7 门禁和用户最终选择权继续有效。

## 当前状态边界

`DEC-G6-003`/`DEC-G6-004` 已条件性应用当前 Chat、Embedding、向量存储方向和成本政策，但 `OPEN-01` 仍阻断 G6 Exit；Provider runtime 禁用，`G7_ENTRY_GATE=NOT_READY`。详见 [`DEC-G6-004.md`](./DEC-G6-004.md)、[`DEC-G6-003.md`](./DEC-G6-003.md)、[`G6_DEEPSEEK_PROVIDER_CHANGE_REVIEW.md`](../baseline/G6_DEEPSEEK_PROVIDER_CHANGE_REVIEW.md)、[`DECISION_WORKFLOW_MIGRATION.md`](../baseline/DECISION_WORKFLOW_MIGRATION.md) 和 [`REVIEW_BACKLOG.md`](./REVIEW_BACKLOG.md)。
