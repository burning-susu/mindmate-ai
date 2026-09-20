# G2 决策基线
> 文档编号：G2-DECISION-BASELINE-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 关联决策：DEC-BOOTSTRAP-001
> 关联证据：EVID-004

## 基线状态

以下 10 项决策已经在当前会话完成影响复述、二次确认和应用授权。它们是当前项目的方向约束，但不等同于已批准 PRD、最终技术架构或已发布系统。

## 已确认决策

| 原始编号 | 当前结论 | 状态 | 主要约束 |
|---|---|---|---|
| HIGH-01 | 本地单用户 MVP；V1 不做真实登录；保留 userId 和资源归属校验 | APPLIED | 暂不公网多用户 |
| HIGH-02 | 外部模型和 Embedding；本地后端 Provider Adapter；本地向量存储；本地部署；不需要云服务器 | APPLIED | Provider、模型和 Embedding 名称 TBD |
| HIGH-03 | 模块化单体；内部异步任务；V1 禁用微服务 | APPLIED | 模块边界仍需 G7/G8 设计 |
| HIGH-04 | 核心闭环 MVP；设置页和独立错题本延后 | APPLIED | 陪练过程数据仍可保存 |
| MEDIUM-01 | Figma/Sketch 为结构和视觉参考，允许产品化改造 | APPLIED | 不要求像素级复刻 |
| MEDIUM-02 | 文本型 PDF、DOCX、Markdown、TXT；不做 OCR；20MB；单次最多 5 个 | APPLIED | 复杂扫描件不进入 V1 |
| MEDIUM-03 | 单元、API/契约、核心 E2E、基础安全、轻量性能基线 | APPLIED | V1 不做完整压测和专业渗透 |
| MEDIUM-04 | REST + OpenAPI | APPLIED | 路径、字段、流式协议和鉴权 TBD |
| LOW-01 | 关键事件和必要运行日志 | APPLIED | 不做复杂分析后台 |
| LOW-02 | 产品中性文案；模板结构可参考；不继承模板品牌和颜色 | APPLIED | 最终 Design Token TBD |

## 基线解释

HIGH-01 和 HIGH-02 的组合不是完全离线：应用和数据默认在用户本地，但必要的问题、文本片段或上下文可以发送给外部模型/Embedding Provider。产品必须提示用户不适合上传高度敏感资料。

HIGH-04 解决了“产品说明书把基础设置作为体验描述”和“需求文档把设置列为 P1”的范围差异：V1 不提供用户设置页，必要默认值保留为内部默认行为。

MEDIUM-04 只确认 API 风格和契约格式，不提前确定前后端框架、数据库、向量存储实现、流式传输或文件上传协议。

## 尚未升级的结论

- 未创建 ADR：当前决策仍需要在 G6/G8 结合 TECH-DECISION、数据和 Provider 约束复核。
- 未生成 API Contract：API_PATHS、API_FIELDS、STREAMING_PROTOCOL 继续为 TBD。
- 未生成数据库模型、向量库方案、部署架构或代码。
- WORKFLOW_BLUEPRINT 已确认；其内部 EXECUTION_FLOW FLOW-01 仍为 PROPOSED。
