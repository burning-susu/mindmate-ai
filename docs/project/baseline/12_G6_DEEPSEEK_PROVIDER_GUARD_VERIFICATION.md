# Mindmate AI G6 DeepSeek Provider Guard Verification
> 文档编号：G6-DEEPSEEK-PROVIDER-GUARD-VERIFICATION-001
> 文档版本：v1.0-Draft.1
> 文档类型：governance / provider guard
> 文档状态：Draft / In Review
> 当前阶段：G6
> 当前 Chat Provider：DeepSeek API / `deepseek-flash`
> G6_EXIT：BLOCKED
> PROVIDER_DECISION_STATUS：APPLIED_CONDITIONAL
> PROVIDER_RUNTIME_ENABLED：false
> 访问日期：2026-09-21
> 关联决策：DEC-G6-001、DEC-G6-003
> 关联决策：DEC-G6-001、DEC-G6-003、DEC-G6-004
> 关联证据：EVID-032、EVID-033、EVID-034

## 1. 本轮结论

本轮读取 DeepSeek 官方 API 文档的公开模型、接口、thinking、JSON、Tool Calls、限流和价格信息。没有调用 DeepSeek API，没有登录平台，没有创建、读取或验证 API Key，也没有上传用户文件或知识库内容。

公开 API 功能和价格资料可以证明候选接口的公开文档状态，但不能证明项目用户的账号资格、余额、地区适用性或数据处理条款。DeepSeek 消费者产品隐私政策不能自动替代开发者 API 平台条款；API 数据处理、保留、训练、删除、地域和子处理者证据仍不足。

```text
PROVIDER_DECISION_STATUS=APPLIED_CONDITIONAL
PROVIDER_GUARD_STATUS=BLOCKED
PROVIDER_RUNTIME_ENABLED=false
G6_EXIT=BLOCKED
G6_STATUS=BLOCKED
ARCHITECTURE_STATUS=DRAFT
OPEN-01=G6_EXIT_BLOCKER
G7_ENTRY_GATE=NOT_READY
G7_EXECUTION=NOT_STARTED
```

DEC-G6-004 已应用 `deepseek-flash`、本地 BGE Embedding 方向、本地嵌入式向量存储方向和 USD 5 成本政策；这些应用不等于本地 Spike、成本实现或 Provider Guard 已通过。

## 2. DeepSeek Guard Matrix

状态含义：`PASS_PUBLIC_DOCS` 只代表官方公开文档可读；不代表用户账号或运行时已通过。`PARTIAL_PUBLIC_ONLY` 代表公开目录/价格可见但关键条件缺失；`UNVERIFIED`/`NOT_VERIFIED`/`PROPOSED_NOT_APPLIED` 均不得推断为通过。

| Guard ID | 防护条件 | 状态 | 官方证据 / 定位 | 未确定点与影响 |
|---|---|---|---|---|
| GUARD-DS-PUB-001 | API 输入、输出、对话上下文和必要检索片段的处理范围 | UNVERIFIED / BLOCKED | DeepSeek Chat Completions 与 Models & Pricing 文档说明请求/响应结构 | 未证明内容处理、日志关联和下游数据范围；不能据此授权真实业务数据 |
| GUARD-DS-PUB-002 | 数据保留期限、日志和监控保留 | UNVERIFIED / BLOCKED | 当前读取的 API 文档未给出可适用的保留期限 | 不能证明 API 输入、输出、错误和监控日志的保存时长 |
| GUARD-DS-PUB-003 | API 客户数据是否用于训练及例外 | UNVERIFIED / BLOCKED | DeepSeek 消费者隐私政策明确不自动覆盖开发者开放平台下游数据 | 必须取得适用于 API 的官方条款，不能用消费者政策替代 |
| GUARD-DS-PUB-004 | 删除机制、备份副本和删除时效 | UNVERIFIED / BLOCKED | 当前官方 API 文档未提供适用的删除承诺 | 无法向用户承诺删除、备份和日志副本清理 |
| GUARD-DS-PUB-005 | 子处理者、第三方处理和数据接收方 | UNVERIFIED / BLOCKED | 当前 API 文档未提供完整处理者/子处理者矩阵 | 外部数据边界和责任链不完整 |
| GUARD-DS-PUB-006 | 数据处理地域、跨境传输和地区适用性 | UNVERIFIED / BLOCKED | 当前官方 API 文档未为本项目用户地区提供可核验结论 | 不能推断新加坡、国际或中国大陆等地区的可用性/驻留 |
| GUARD-DS-PUB-007 | OpenAI 兼容 Base URL、Chat Completions、模型和公开功能 | PASS_PUBLIC_DOCS | `https://api-docs.deepseek.com/quick_start/pricing`、`/api/create-chat-completion`、`/guides/thinking_mode`、`/guides/json_mode`、`/guides/tool_calls` | 公开文档不等于账号可用或项目运行时已授权 |
| GUARD-DS-PUB-008 | 当前模型、上下文、最大输出、价格和并发 | PARTIAL_PUBLIC_ONLY | Models & Pricing：`deepseek-flash`、1M context、最大 384K、峰/非峰和缓存价；Rate Limit：并发 2500、超限 HTTP 429 | 价格可调整；账户实际额度、计费、余额和模型权限未核验 |
| GUARD-DS-ACCOUNT-001 | DeepSeek API 开放平台账号可用 | NOT_VERIFIED / BLOCKED | 需要用户控制台核验；本轮不登录 | 账号资格未知 |
| GUARD-DS-ACCOUNT-002 | API 服务和当前模型已对账号开通 | NOT_VERIFIED / BLOCKED | 需要用户账户/模型列表核验；本轮不操作 | 模型可见性和调用权限未知 |
| GUARD-DS-ACCOUNT-003 | 余额、充值/付费能力和余额查看可用 | NOT_VERIFIED / BLOCKED | 官方价格页说明从充值或赠送余额扣费，但不证明用户余额 | 不得宣称 USD 5 停止策略已执行 |
| GUARD-DS-ACCOUNT-004 | API Key 后续由用户配置且不进入前端/仓库 | PASS_DESIGN_ONLY | DEC-G6-003 本地后端 Secret 边界 | 本轮没有创建、读取或验证 Key |
| GUARD-DS-COST-001 | 月预算、提醒、停止新调用、禁自动充值/提额 | PROPOSED_NOT_APPLIED / BLOCKED | 成本决策尚未由用户选择，官方价格存在峰/非峰和缓存差异 | 运行时不能声称具备预算阻断 |
| GUARD-DS-COST-002 | 单次输出、重试、429 和余额不足策略 | PROPOSED_NOT_APPLIED / BLOCKED | 官方文档提供功能/429信息，项目策略尚未设计并实现 | 不得自动重试、充值或绕过预算 |
| GUARD-DS-RUNTIME-001 | Provider Runtime 安全开关和 no-call | PASS_DESIGN_ONLY | DEC-G6-001、DEC-G6-003、Runtime Context | 运行时仍禁用，未进行真实请求 |

## 3. Secret 与调用边界

- 前端和浏览器永远不持有 `DEEPSEEK_API_KEY`。
- 只有本地后端 Provider Adapter 读取本机环境变量或未提交 Secret 配置。
- `.env`、`.env.local`、密钥文件和敏感日志必须被 `.gitignore` 排除；`.env.example` 只能放空占位符。
- 缺少 Key、余额不足、认证失败、429、条款/账号/地区 Guard 未通过时安全失败，保持 Provider 禁用。
- 不在 DEC、Evidence、日志、截图、备份正文或测试夹具中写入真实 Key。
- 本轮不读取、不验证、不展示、不创建、不测试 Key，不发送任何用户文件或知识库内容。

## 4. Alibaba Guard 的历史关系

原 [11_G6_PROVIDER_GUARD_VERIFICATION.md](11_G6_PROVIDER_GUARD_VERIFICATION.md) 保留 Alibaba 的完整历史核验、页面访问限制和阻断证据，并标记为 `SUPERSEDED_NOT_CURRENT_PROVIDER`。它不再作为当前 Chat Provider 的 Guard，但其审计记录、EVID-030 和 no-call 结论不删除。

## 5. G6 Exit Preflight

| 检查项 | 结果 | 说明 |
|---|---|---|
| DEC-G6-003 存在且修订关系正确 | PASS | supersedes DEC-G6-002 的 Chat route；保留 DEC-G6-001 no-call |
| DeepSeek 公开模型/API/功能资料 | PASS_PUBLIC_DOCS | 公开文档可读，但不等于账号授权 |
| DeepSeek 数据处理/保留/训练/删除/地域 | BLOCKED | GUARD-DS-PUB-001~006 UNVERIFIED |
| DeepSeek 账号、模型权限、余额 | BLOCKED | GUARD-DS-ACCOUNT-001~003 NOT_VERIFIED |
| Embedding 方案 | BLOCKED_FOR_FULL_G6 | 尚未用户选择，不能把 DeepSeek 视为 Embedding Provider |
| 成本保护 | BLOCKED | GUARD-DS-COST-001/002 PROPOSED_NOT_APPLIED |
| Secret 和 no-call 设计 | PASS_DESIGN_ONLY | Provider runtime 仍 false，未调用 |
| G6/G7 门禁 | BLOCKED / NOT_READY | G6 不完成，G7 不开始 |

结论：不能更新为 `G6_STATUS=COMPLETED`、`ARCHITECTURE_STATUS=APPROVED`、`OPEN-01=RESOLVED` 或 `G7_ENTRY_GATE=READY`。
