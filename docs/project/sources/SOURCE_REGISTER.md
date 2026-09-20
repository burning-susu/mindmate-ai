# Mindmate AI 来源总登记
> 文档编号：SRC-REGISTER-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 生效条件：G1/G2
> 创建日期：2026-09-20
> 更新时间：2026-09-20
> 关联来源：AGENTS.md、doc/governance/通用文档提示词v3.2.md
> 关联证据：EVID-001、EVID-002、EVID-003、EVID-004

## 登记规则

来源状态和项目事实状态分开记录。提示词是操作或决策输入，通用 doc/ 是方法来源，只有业务资料、设计资料和用户确认决策可以进入项目事实或项目决策链。

## 来源清单

| 编号 | 名称与路径 | 类型/版本 | 用途和适用范围 | 优先级 | 当前状态 | 可读性与边界 | 项目事实源 |
|---|---|---|---|---|---|---|---|
| SRC-001 | README.md | Markdown / 当前仓库版本 | 项目一句话定位和能力概览 | P2 | ACTIVE | 可读；粒度较粗，不含完整需求 | 部分事实 |
| SRC-002 | 项目业务资料/需求文档/个人AI知识学习助手产品说明书_V1.0.docx | DOCX / V1.0 | 产品定位、用户、价值、三种模式、首版边界和使用说明 | P1 | ACTIVE_CANDIDATE_BASELINE | 114 个非空段落、13 个表格；内容完整但未见 Approved/Baselined 证据 | 候选业务事实 |
| SRC-003 | 项目业务资料/需求文档/个人AI知识学习助手项目需求文档_V1.0.docx | DOCX / V1.0 | 功能编号、业务流程、状态、数据对象、非功能、安全和验收输入 | P1 | ACTIVE_CANDIDATE_BASELINE | 239 个非空段落、38 个表格；未见 Approved/Baselined 证据 | 候选业务事实 |
| SRC-004 | 项目业务资料/设计文件/Ai智能体B端模版.fig | Figma ZIP / 文件名版本未标注 | B 端布局、对话区、侧栏、卡片、表格和素材参考 | P1 | ACTIVE_REFERENCE | 32 个 ZIP 条目，含 canvas.fig、thumbnail.png、meta.json 和图片；本轮未读取全部画板文本 | 设计参考，不是最终 UI 事实 |
| SRC-005 | 项目业务资料/设计文件/Ai智能体B端模版.sketch | Sketch ZIP / meta version 143 | 页面、控件和视觉参考 | P1 | ACTIVE_REFERENCE | 36 个 ZIP 条目，3 个页面：页面 1、页面 2、控件；本轮读取工程元数据和预览，不将全部图层当作业务事实 | 设计参考，不是最终 UI 事实 |
| SRC-006 | C:/Users/15932/Desktop/mindmate-ai_第一轮启动提示词.md | Markdown / 外部控制输入 | 规定第一轮只读范围、输出顺序和分析边界 | P0 | CONTROL_INPUT | 可读；不是产品需求，也不是独立事实源 | 否 |
| SRC-007 | C:/Users/15932/Desktop/mindmate-ai_第二轮G2来源与决策基线提示词.md | Markdown / 外部控制输入 | 规定 G1/G2 任务、已确认决策的结构化值和本轮写入边界 | P0 | CONTROL_AND_DECISION_INPUT | 可读；操作要求与决策输入分开处理 | 否 |
| EVID-004 | 当前会话用户确认记录 | Conversation evidence / 2026-09-20 | 证明 HIGH-01 至 LOW-02 已完成二次确认和应用授权 | P0 | ACTIVE_EVIDENCE | 不在仓库文件中；引用需回到当前会话 | 决策证据，不是产品资料 |

## 文件校验

| 来源 | 文件大小 | SHA-256 |
|---|---:|---|
| SRC-001 | 146 bytes | AF9C46AAB68EF1D48B233A09EA0244ACE38812E58524B0CF0CB3B35E779611D6 |
| SRC-002 | 49,862 bytes | 654932274C802BA349E6DD110A3D2A68D7E5BC3301180402904592D87B6ED82F |
| SRC-003 | 64,179 bytes | 587D2BED9DA20BC9DF8F307D7718872E7BC802567410219734127AAC1799059D |
| SRC-004 | 26,236,963 bytes | B5B29676C6497712322F33F6FE1538F3E748BD352569765D250FCB6090D024EB |
| SRC-005 | 28,754,457 bytes | 1F8E5318463BB311922E3C75D16985003FE1B402DA342C0479A500BADD4A261A |

## 来源优先级和边界

1. 当前会话中用户已明确确认并授权应用的项目决策，优先约束项目配置和流程状态。
2. 项目需求文档和产品说明书提供候选业务事实，但在 PRD Approved/Baselined 前不能作为最终批准需求基线。
3. 设计文件仅证明可用的视觉参考和素材边界，不证明完整交互、权限、后端流程或未展示状态。
4. README 只提供项目概览。
5. 第一轮和第二轮提示词以及 doc/ 下通用文件属于控制输入和方法来源，不自动成为业务事实。

## G1 完整性结论

- 四份核心业务/设计资料已登记。
- README 已登记。
- 第一轮和第二轮控制输入已单独登记。
- DOCX 正文和表格已读取；设计文件完成格式、元数据和预览边界检查。
- 未发现仓库内重复的业务资料副本。
- G1 来源登记：COMPLETED。

