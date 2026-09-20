# v3.2.4 治理与 Mindmate 状态摘要
> 摘要编号：CTX-SUMMARY-001
> 摘要版本：v1.0
> 生成时间：2026-09-20
> 状态：CURRENT
> 用途：任务前最小上下文复用

## 来源

- doc/governance/通用文档提示词v3.2.md
  - SHA-256：19309D54CB5F3E60327FAD7940C8B3287D0A340821C36813B24E28CC4CB320C7
  - 覆盖：v3.2.4 变量、Token/上下文治理、G0-G11、Workflow、Runtime Context、Evidence 和目录规则。
- doc/governance/通用文档提示词v3.2完整使用说明.md
  - SHA-256：5FADB67527BF37ED56F394B3FEE145EEB2E114A2B0F55050599F61ABB2997A0E
  - 覆盖：第 2F 节 Token 与上下文节约治理、任务前运行顺序、索引和摘要规则。
- docs/project/governance/WORKFLOW_BLUEPRINT.yaml
  - 覆盖：WF-MINDMATE-001 v0.1 已确认，当前阶段仍为 G2，FLOW-01 仍为 PROPOSED。
- docs/project/governance/RUNTIME_CONTEXT.md
  - 覆盖：当前任务权限、Token 预算、上下文装载模式和 G3 未执行状态。
- docs/project/governance/EVIDENCE_REGISTER.yaml
  - 覆盖：EVID-007 Workflow 确认证据。

## 当前结论

- PROJECT_STAGE：BOOTSTRAP。
- WORKFLOW：WF-MINDMATE-001 v0.1 / CONFIRMED。
- CURRENT_STAGE：G2；G3 入口门禁通过，但 G3 尚未启动。
- 允许：继续执行 G3 提示词所需的项目文档审计。
- 禁止：开发、脚手架、依赖安装、API/数据库实现、Git commit/tag/push。
- 外部模型、Provider、前后端技术栈、数据库、向量实现、流式协议仍按项目文档保持 TBD。

## Token 与上下文规则

- 默认 MINIMAL；本任务采用 MEDIUM + TARGETED。
- 优先复用本摘要和 governance/CONTEXT_INDEX.yaml。
- 只有来源变化、摘要失效或证据不足时才扩大读取。
- 未发现独立的“模型自动切换”治理字段；不得将用户描述自动扩展为 Provider 路由实现。
