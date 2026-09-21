# Mindmate AI G6 Provider / 模型 / Embedding 决策评审
> 文档编号：G6-PROVIDER-DECISION-REVIEW-001
> 文档版本：v1.0-Draft.1
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 文档状态：Draft / In Review
> 当前阶段：G6
> PROVIDER_DECISION_STATUS：APPLIED_CONDITIONAL
> 当前已应用边界：DEC-G6-003/DEC-G6-004（DeepSeek Chat + G6 residual decisions；amends current Chat route from DEC-G6-002）
> 历史 Alibaba 基线：DEC-G6-002（Chat route superseded; historical evidence retained）
> 当前 G6 出口阻断：OPEN-01
> 创建日期：2026-09-21
> 更新日期：2026-09-21
> 关联 Workflow：WF-MINDMATE-001 v0.1
> 关联 PRD：PRD-MINDMATE-V1 v1.0-Draft.3 Approved
> 关联 Evidence：EVID-018、EVID-021、EVID-024、EVID-025、EVID-026、EVID-027、EVID-028、EVID-029、EVID-030、EVID-032、EVID-033、EVID-034

## 1. 本轮范围与状态

本轮先依据第十轮 G6 提示词完成 Provider、Chat 模型、Embedding、地域、数据处理、成本和 Secret 边界的实时官方资料核验与候选比较；随后用户完成初选、二次确认和应用授权。本文件记录条件性应用结果，不代表 Provider runtime 已启用。

已确认并应用的 DEC-G6-001/C 继续生效：具体 Provider 详情核实前不发起真实外部请求。此规则不撤销 PRD 中的外部 Provider 方向，也不解除 OPEN-01。Provider 账户、Key、用户国家/地区、可用区和付款资格均未检查；本轮未读取或请求任何 Secret。

本项目可复用资料没有记录用户实际国家/地区。系统时区和 Windows 文件路径不是实际所在地证据，因此以下候选的用户所在地区可用性均为 NOT_CONFIRMED。

| 当前状态 | 值 |
|---|---|
| CURRENT_STAGE | G6 |
| G6_STATUS | BLOCKED |
| ARCHITECTURE_STATUS | DRAFT |
| OPEN-01 | G6_EXIT_BLOCKER |
| G7_ENTRY_GATE | NOT_READY |
| PROVIDER_DECISION_STATUS | APPLIED_CONDITIONAL |
| DEC-G6-002 | APPLIED_CONDITIONAL；amends DEC-G6-001 |
| 真实 API / Embedding 请求 | 未发起 |
| Git commit / tag / push | 未执行 |

## 2A. 用户第一次初选（未二次确认、未应用）

用户已在当前会话提交以下初选：

```text
TECH-DEC-004-V2=A
Provider=Alibaba Cloud Model Studio
Chat Model=qwen3.8-flash
Embedding=text-embedding-v4
Region=Singapore/International
Data Terms=待继续核验官方数据处理、保留和训练条款
Monthly Soft Budget=USD 5
限制条件：在数据条款、账号资格和地区可用性核验完成前，不发起真实外部请求，不解除OPEN-01
```

这只是第一次意向选择，不是 CONFIRMED 或 APPLIED。DEC-G6-001 不被覆盖，A 的具体 Provider 基线尚未成为项目正式决策。

初选后必须继续核验：

- Alibaba Model Studio API 的数据处理、保留、训练用途、删除和适用地域条款；
- 用户实际可用的 Alibaba Cloud 账号、Model Studio 开通状态、付款资格和 Singapore/International 端点资格；
- Singapore/International 的 qwen3.8-flash 与 text-embedding-v4 是否适用于用户实际地区和账户；
- USD 5/月软预算是否由用户正式接受；当前仍是候选保护参数；
- 全库 Embedding 可能使大量解析文本切片离开本地，不应误解为只发送问答命中片段；
- Provider/模型版本变化后的索引重建、失败状态、重试和回退行为。

在以上条件完成核验并重新通过 G6 Exit preflight 前，不启用 Provider runtime、不更新架构为 Approved、不解除 OPEN-01、不发起 API 请求。

## 2B. 用户正式二次确认（尚未应用）

用户已完成 A 方案的正式二次确认，并保留以下强制条件：

- 数据处理、保留和训练条款仍需继续核验；
- Alibaba Cloud 账号资格和 Model Studio 可用性仍需继续核验；
- Singapore/International 地区可用性仍需继续核验；
- 在上述核验完成前不发起真实外部请求；
- 不解除 OPEN-01。

该确认已由用户通过“应用并同步 TECH-DEC-004-V2”授权进入条件性应用，形成 DEC-G6-002。Provider 仍未启用，不代表 API Key 已验证，不代表数据条款已批准，也不代表 G6 已完成。

## 2C. 条件性应用结果

DEC-G6-002 已创建并声明 amends DEC-G6-001。A 方案作为 V1 Provider 候选基线写入架构和追踪；EVID-030 的 Guard Verification 仍为 BLOCKED，运行时状态保持 DISABLED_UNTIL_GUARDS_VERIFIED。

在数据处理/保留/训练条款、账号资格、Singapore/International 地区可用性和后续成本保护规则完成核验前：

- 不发起 Chat、Embedding 或文件内容请求；
- 不读取、验证或要求用户提供 API Key；
- 不解除 OPEN-01；
- 不把架构升级为 Approved/Baselined；
- 不进入 G7。

## 2. 项目约束

- 单用户、本地优先、桌面 Web + 同设备本地服务；没有远程业务服务器。
- 对话和 Embedding 的产品方向是外部 Provider + 本地后端 Adapter；原始文件、业务数据和向量默认本地。
- 用户已经确认只发送当前操作所需的最小文本/上下文；这不等于对某个服务、地域、保留条款或整份文件外发的确认。
- V1 文件范围含 PDF、DOCX、Markdown、TXT，单文件不超过 20MB、单次最多 5 个；目前没有实际文件样本 Token 统计。
- 模块化单体、内部异步任务；API 方向为 REST + OpenAPI。
- ChatGPT/Codex 开发执行模型和 Mindmate 运行时 Chat 模型/Embedding 是三类不同概念；当前开发订阅及执行环境不被记作应用 API 额度。

## 3. 实时官方来源

实际读取官方页面正文或模型卡，不使用搜索摘要作为事实。访问日期：2026-09-21。

| 来源 ID | 页面标题与 URL | 核实事实 | 产品范围 / 未决项 |
|---|---|---|---|
| WEB-001 | Alibaba Cloud, Supported Models and Capabilities Overview - Model Studio；https://www.alibabacloud.com/help/en/model-studio/models | 当前模型目录可见 qwen3.8-flash、text-embedding-v4 | Model Studio API 模型目录；不核验用户账户是否已开通 |
| WEB-002 | Alibaba Cloud Model Studio model pricing；https://www.alibabacloud.com/help/en/model-studio/billing-for-model-studio | Singapore 区域下 International qwen3.8-flash 输入/输出价为 USD 0.15/0.47 每百万 Token；text-embedding-v4 为 USD 0.07/M | 价格来源于 Singapore/International 行。页面列有受期限/资格约束的免费额度，估算不计免费额度；该页不确立用户数据驻留/保留条款 |
| WEB-003 | Alibaba Cloud, Region support；https://www.alibabacloud.com/help/en/model-studio/region-support | 请求返回 HTTP 200，但当前获取内容仅为页面壳，未获得可读条款正文 | 地区处理能力和用户账户地区资格 NOT_CONFIRMED，不据此做正面判断 |
| WEB-004 | Alibaba Cloud, Data privacy；https://www.alibabacloud.com/help/en/model-studio/data-privacy；Terms and conditions；https://www.alibabacloud.com/help/en/model-studio/terms-and-conditions | 两页当前获取内容仅为页面壳，未获得可读条款正文 | Model Studio API 的处理方、训练用途、保留期限、删除及适用地域 NOT_CONFIRMED |
| WEB-005 | DeepSeek API Docs, Models & Pricing；https://api-docs.deepseek.com/quick_start/pricing | API model name 为 deepseek-flash，官方映射模型版本为 DeepSeek-V4.1-Flash；官方价随峰/非峰和缓存命中变化 | API 模型/定价资料；用户账号与所在地访问资格未验证 |
| WEB-006 | DeepSeek Privacy Policy；https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html | 页面最近更新日期为 2026-02-10；明示开发者基于开放平台构建的下游应用终端用户数据不在该消费者隐私政策覆盖范围内 | 不能把消费者隐私政策当作 DeepSeek API 数据处理条款；API 具体保留/训练/地域仍 NOT_CONFIRMED |
| WEB-007 | BAAI/bge-small-zh-v1.5 model card；https://huggingface.co/BAAI/bge-small-zh-v1.5 | 发布方模型卡标示 24M 参数、MIT License | 本地模型候选；未安装，未在用户电脑做 CPU/GPU、耗时、内存或质量测试 |
| WEB-008 | GPT-5.6 Luna Model；https://developers.openai.com/api/docs/models/gpt-5.6-luna；text-embedding-3-small Model；https://developers.openai.com/api/docs/models/text-embedding-3-small | 官方模型页列出 gpt-5.6-luna 及 text-embedding-3-small；前者可经 Responses/Chat Completions，Embedding 使用单独端点 | OpenAI API 候选；用户 API 账户、付款、地区资格未验证 |
| WEB-009 | OpenAI API Pricing；https://developers.openai.com/api/docs/pricing | gpt-5.6-luna 标准短上下文输入/输出 USD 0.20/1.20/M；text-embedding-3-small USD 0.02/M | 按 API Token 计价；不把 ChatGPT/Codex 订阅记作 API 额度 |
| WEB-010 | Data controls in the OpenAI platform；https://developers.openai.com/api/docs/guides/your-data | API 内容默认不用于训练，除非客户 opt-in；默认 abuse monitoring logs 最长 30 天；ZDR/MAM 需要事先审批；驻留按组织、项目、端点、模型和地区配置 | 官方 API 控制，不等于默认零保留或所有处理都在指定地区 |
| WEB-011 | OpenAI API, Model guidance；https://developers.openai.com/api/docs/guides/latest-model | 当前官方指南将 GPT-6 Astra 描述为旗舰候选；本轮为成本比较同时读取低价 GPT-5.6 Luna 具体型号页 | 不将 Codex 开发模型当作应用运行时模型 |
| WEB-012 | OpenAI API, Production best practices；https://developers.openai.com/api/docs/guides/production-best-practices | API Key 应通过安全后端配置/环境变量或 Secret 管理，避免硬编码 | 与 DEC-BOOTSTRAP-001 的本地后端 Secret 边界一致 |

OpenAI 的数据驻留页当前列出美国、欧洲 EEA/瑞士、澳大利亚、加拿大、日本、印度、新加坡、韩国和英国等区域；该表将美国和欧洲标为支持 regional processing，其他多个地区仅支持 storage。表中没有中国大陆区域。该页也说明系统数据不一定随 Customer Content 驻留、使用驻留需组织符合资格，且符合条件的模型可能有 10% 价差。用户所在地未确认，故 OpenAI 可用性/驻留匹配仍为 NOT_CONFIRMED。

## 4. 候选方案

### A. Alibaba Cloud Model Studio 同一 Provider

- Chat：qwen3.8-flash。
- Embedding：text-embedding-v4。
- 优点：一个外部服务边界、一个后端 Adapter 家族；所查 Singapore/International 示例价格较低；无需将本地 Embedding runtime 引入 V1。
- 代价/隐私：为整库建索引时，全部可解析文本可能分批发送给外部 Embedding；问答还会发送必要问题与命中片段。Alibaba 官方模型和价格资料可读，但数据处理/保留/训练条款、精确驻留和用户账号资格本轮未能核实。
- 状态：PROPOSED，需用户地区/账户资格与官方数据条款核验；不得调用。

### B. DeepSeek 外部 Chat + 本地 Embedding

- Chat：DeepSeek API 当前文档使用 deepseek-flash，对应 DeepSeek-V4.1-Flash。
- Embedding：本地 BAAI/bge-small-zh-v1.5 候选，24M 参数、MIT License。
- 优点：文档切片在本地生成向量，不必为建索引把整库文本外发；只在问答/陪练时发送问题、必要历史与检索命中片段。
- 代价/隐私：仍有 Chat 数据外发；DeepSeek 消费者隐私政策不覆盖开发者开放平台下游用户数据，API 专属条款未确认。BGE 在用户 Windows 设备的资源占用、速度、中文检索质量、升级/重建成本未经测试。
- 状态：PROPOSED，需 API 条款、账户/地域和本地硬件验证；不得安装或调用。

### C. 延续 DEC-G6-001 / Provider 细节保持 TBD

- 不选择供应商、模型、Embedding、地域或条款；不发起外部请求。
- 不产生本轮 Provider API 费用，维持最小数据外发风险。
- 文件解析可按后续本地设计处理，但外部 Embedding 索引无法完成；自由对话、资料问答、陪练不能完成真实生成与验收，G6/G7 继续阻断。
- 状态：CONFIRMED/APPLIED，现行 no-call 边界；如选 C，不重复创建同内容 DEC。

### D. OpenAI API 同一 Provider

- Chat：gpt-5.6-luna；Embedding：text-embedding-3-small。
- 优点：模型、Embedding、价格、API 数据控制及 Secret 文档有可核验官方资料；单一 Provider 接入，避免两套账户和合同边界。
- 代价/隐私：Embedding 需要把文档文本切片发给外部服务；默认 API abuse monitoring logs 最长 30 天；ZDR/MAM 需要事先审批；驻留资格和区域受到端点/组织约束，当前页面没有中国大陆区域；用户 API 账户及适用地区未确认。
- 状态：PROPOSED，需确认用户实际地区、账号资格和可接受的数据驻留/保留条件；不得调用。

本轮不新增两个不同外部 Provider 分别承担 Chat 与 Embedding 的方案：这会增加一套外部接收方、密钥、合同、限流/失败组合和验收成本；当前未发现官方证据证明增加该复杂度优于 A、B 或 D。用户后续提出明确组合时可重开评审。

## 5. 数据出站矩阵

| 数据 | A：Alibaba Chat + Embedding | B：DeepSeek Chat + 本地 Embedding | C：维持 no-call | D：OpenAI Chat + Embedding |
|---|---|---|---|---|
| 原始文件二进制 | 不默认上传整件 | 不默认上传整件 | 留在本地 | 不默认上传整件 |
| 解析文本/切片 | 整库建 Embedding 时可分批发送全部可解析文本 | Embedding 过程留本地 | 留在本地 | 整库建 Embedding 时可分批发送全部可解析文本 |
| 用户问题/必要历史 | 用户触发 Chat 时发给候选 Provider；具体字段 TBD | 用户触发 Chat 时发给 DeepSeek；API 条款 TBD | 不发送 | 用户触发 Chat 时发给 OpenAI API |
| RAG 命中片段 | 仅本轮必要片段可发出；具体 prompt window TBD | 仅本轮必要片段可发出；这仍是文档内容外发 | 不发送 | 仅本轮必要片段可发出；这是外部数据处理 |
| 知识库名/文件名/其它元数据 | 默认不需要；传输字段尚未定义 | 默认不需要；传输字段尚未定义 | 不发送 | 默认不需要；传输字段尚未定义 |
| API Key | 仅后端对 Provider 认证，不放入请求正文/前端/日志 | 同左 | 不使用 Provider Key 调用 | 同左 |
| 备份/诊断日志 | 保持本地，不向 Provider 发送 | 保持本地，不向 Provider 发送 | 保持本地 | 保持本地，不向 Provider 发送 |

“只发送必要文本”不应误解为 Embedding 仅发送检索命中部分：为建立完整向量索引，输入可覆盖全部文档切片。实际 API payload 和用户提示必须在 G8/G9 设计，未经 Provider 数据条款确认及后续授权不得启用任何候选。

## 6. 成本场景估算

每个场景的 Token 量是为方案横向比较而设的假设，不是用户真实行为或项目承诺；单个 20MB 文件/批量文件的实际 Token 数由格式、内容、解析和切片决定，项目当前没有真实样本 Token Evidence。

```text
Embedding成本 = Embedding输入百万Token × 单价
Chat输入成本 = Chat输入百万Token × 单价
Chat输出成本 = Chat输出百万Token × 单价
预计月API成本 = Embedding成本 + Chat输入成本 + Chat输出成本
```

| 假设场景（每月） | Embedding 输入 | Chat 输入 | Chat 输出 | A：Qwen3.8 Flash + v4 | B：DeepSeek Flash 峰时 + 本地 BGE | C：不调用 | D：GPT-5.6 Luna + embedding-3-small |
|---|---:|---:|---:|---:|---:|---:|---:|
| 低频个人试用 | 0.1M | 0.3M | 0.06M | USD 0.0802 | USD 0.162 API；本地算力另计 | USD 0 API，AI 链路停用 | USD 0.134 |
| 中等个人使用 | 2M | 3M | 0.6M | USD 0.872 | USD 1.62 API；本地算力另计 | USD 0 API，AI 链路停用 | USD 1.36 |
| 异常使用/重复重建 | 10M | 30M | 6M | USD 8.02 | USD 16.20 API；本地算力另计 | USD 0 API，AI 链路停用 | USD 13.40 |

计算口径：

- A：按所查 Singapore/International 价格，Chat 输入/输出 USD 0.15/0.47/M，Embedding USD 0.07/M；不扣官方有限期免费额度，不计缓存/批处理折扣。
- B：按 DeepSeek Flash 峰时输入/输出 USD 0.30/1.20/M，假设无缓存命中；官方列出的非峰时价较低。Local BGE 无 API Embedding 费用，但不代表算力/集成零成本。
- D：按 OpenAI GPT-5.6 Luna 标准短上下文输入/输出 USD 0.20/1.20/M、Embedding USD 0.02/M；不计缓存折扣。长上下文价更高；符合驻留资格的部分区域端点可能另有价格上浮。
- API 定价为官方标价，不等于用户账户实际账单；用户国家、账号资格、税费、汇率和供应商折扣未验证。ChatGPT/Codex 订阅不计 API 余额。
- C 的零 API 成本对应不调用模型，不是具备了零成本 AI 功能。

### 6.1 成本保护建议

以下是候选默认，全部为 PROPOSED，不是正式预算或实现要求：

- 月 API 软预算候选：USD 5；80%（USD 4）时告警，达到 100% 停止新请求，不自动充值、扩额或绕过提示。
- 单次 Chat 输出上限候选：2,000 Token；实现前需以真实中文使用样例确认。
- 仅对明确可恢复的瞬时错误自动重试一次；预算不足、认证错误和限流不反复重试。
- 以本地文件内容指纹 + Embedding Provider/模型版本做重复入库去重，避免同一内容无意重复计费。
- 本地只计数 Provider、模型、输入/输出 Token、费用估值、任务结果；不记提示正文、检索片段或 Key。

## 7. Secret、账户和运行边界

- 项目已有决定要求 API Key 只在本地后端配置；不得放前端、浏览器存储、仓库、备份正文或普通日志。
- 本轮不问用户提供 Key，不检查现有环境变量，不登录任何 Provider 控制台，不试调用接口。
- OpenAI API 候选按 API Token 价格计算；不把 ChatGPT Plus/Pro、Codex 使用权限或当前 Codex 模型当成应用运行 API 额度。
- DeepSeek 消费者隐私政策不覆盖开发者开放平台下游应用终端数据，API 条款仍待正式来源。
- Alibaba 当前价格页只能支持候选价格/模型信息；已尝试的区域、隐私和条款 URL 未能获取可读条文，不从搜索摘要推断。
- 用户当前地区和 API 账号未提供，三家外部服务的实际访问资格均为 NOT_CONFIRMED。

## 8. 推荐与风险

**当前运行建议：继续执行 no-call guards。**A 已形成条件性 Provider 基线，但用户账号、地区资格和 Alibaba API 数据条款仍未核验；在 guards 完成前，DEC-G6-001 的 no-call 约束继续生效，不解除 OPEN-01。

**可供用户初选的未来候选：**

- 偏重部署简单与低外部 Token 成本：A；前提是用户实际区域/账户可用，且 Alibaba 官方处理/保留条款被核实并接受。Embedding 会让大量文档切片离开本地。
- 偏重文档切片留本地：B；前提是本机运行能力经后续验证、DeepSeek API 的正式数据条款获确认。Chat 问题与命中片段仍会出站。
- 偏重已有完整 OpenAI API 数据控制资料：D；前提是账户与适用区域符合用户要求，并接受默认最长 30 天 abuse log 和 ZDR 的审批门槛。没有用户实际区域时不能认定适用。

A/B/D 都只是 PROPOSED。无论用户初选哪项，都不能直接调用或解除 G6 阻断；若用户所在地、供应商 API 条款、保留/训练用途或成本上限仍影响隐私边界，则继续保持 G6 BLOCKED。

## 9. 决策流程与唯一初选口令

本轮先完成官方资料核验和候选包；用户随后完成 A 的初选、正式二次确认和应用授权，当前状态为 APPLIED_CONDITIONAL。DEC-G6-002 已承接 no-call guards；C 的保护边界继续有效，不自动启用运行时 Provider。

唯一初选口令模板：

```text
TECH-DEC-004-V2=<A|B|C|D>
```

选项映射：

- A：Alibaba Model Studio；Chat qwen3.8-flash；Embedding text-embedding-v4；地区/处理条款/账户资格仍待确认。
- B：DeepSeek API deepseek-flash（官方映射 DeepSeek-V4.1-Flash）；本地 Embedding BAAI/bge-small-zh-v1.5；API 条款/地区/账户和本机性能仍待确认。
- C：延续 DEC-G6-001 no-call，不新建重复 DEC；G6 继续阻断。
- D：OpenAI API gpt-5.6-luna + text-embedding-3-small；账户/地区条件需确认，并评估默认数据保留。

用户已完成第一次选择、正式二次确认和“应用并同步 TECH-DEC-004-V2”授权。下一步是完成 guards 核验并重新执行 G6 Exit preflight；在此之前不发起 Provider 调用、不解除 OPEN-01。

当前输出状态：

```text
PROVIDER_DECISION_STATUS=APPLIED_CONDITIONAL
CURRENT_STAGE=G6
G6_STATUS=BLOCKED
G7_ENTRY_GATE=NOT_READY
G7_EXECUTION=NOT_STARTED
TARGET_MODEL_ID=gpt-5.6-terra
TARGET_REASONING_LEVEL=HIGH
ACTUAL_MODEL_ID=TBD
MODEL_SWITCH_EXECUTED=false
```

## 10. DeepSeek Chat Provider 修订（当前）

本节是本文件当前 Chat Provider 状态；第 2～9 节中的 Alibaba 方案、候选比较、价格和 Guard 记录保留为历史评审，不删除、不改写。

本轮控制输入引用所有者明确选择“我想用 DeepSeek API 解决”。按照 `V3.2_IMMEDIATE_APPLY`，该选择已同轮写入 `DEC-G6-003`，不要求二次确认，不要求用户发送 `DECISION_APPLY`。

| 字段 | 当前值 |
|---|---|
| Chat Provider | DeepSeek API |
| Chat Model | `deepseek-flash`（DeepSeek-V4.1-Flash） |
| Base URL | `https://api.deepseek.com` |
| Chat API | OpenAI-compatible `POST /chat/completions` |
| Embedding | Local `BAAI/bge-small-zh-v1.5` direction via DEC-G6-004；本轮不下载/安装/运行，Spike required |
| Provider Runtime | DISABLED_UNTIL_GUARDS_VERIFIED |
| 当前决策 | DEC-G6-003 / APPLIED_CONDITIONAL |
| G6 | BLOCKED；OPEN-01 仍为 G6_EXIT_BLOCKER |

本轮读取 DeepSeek 官方 API 文档：Models & Pricing、Chat Completions、Thinking Mode、JSON Output、Tool Calls、Rate Limit & Isolation。公开资料支持 `deepseek-flash`、1M 上下文、最大 384K 输出、thinking/JSON/Tool Calls/Responses API、峰/非峰计价和并发/429 规则。DeepSeek API 数据处理、保留/训练、删除、子处理者、处理地域、账号资格和余额仍未取得足够证据，不能解除 OPEN-01。

Alibaba Cloud Model Studio 的 Chat 路线标记为 `SUPERSEDED_NOT_CURRENT_PROVIDER`；其历史 Guard 见 `11_G6_PROVIDER_GUARD_VERIFICATION.md`，当前 DeepSeek Guard 见 `12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md`。Alibaba 不是 DeepSeek 的自动回退。

本轮不调用 DeepSeek 或 Alibaba API，不登录 Provider 控制台，不创建、读取、验证或展示 API Key，不安装 Embedding 模型，不上传用户文件或知识库内容。

## 11. G6 剩余决策批量应用

用户随后一次选择以下 4 项 A，已由 `DEC-G6-004` 同轮应用：

- `TECH-G6-CHAT-MODEL=A`：`deepseek-flash` 成为当前 Chat Model 条件性基线。
- `TECH-G6-EMBEDDING=A`：本地 `BAAI/bge-small-zh-v1.5` 方向；不下载、不安装、不运行，Spike 待后续阶段。
- `COST-G6-PROVIDER=A`：USD 5 月软预算、USD 4 告警、USD 5 停止新调用、禁自动充值/提额、手动恢复；实现待后续阶段。
- `TECH-G6-VECTOR-STORE=A`：本地嵌入式向量存储 + `Storage Adapter`；具体产品和 Spike 留 G8。

这些选择不解除 DeepSeek API 数据/账号/地区 Guard，不启用 Provider Runtime，不产生真实 API 费用，也不代表本地模型或向量产品已安装和验收。
