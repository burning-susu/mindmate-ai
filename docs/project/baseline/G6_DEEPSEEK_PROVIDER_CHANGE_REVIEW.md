# G6 DeepSeek Provider 变更评审
> 文档编号：G6-DEEPSEEK-PROVIDER-CHANGE-REVIEW-001
> 文档版本：v1.0
> 文档类型：governance / change review
> 关联对象：PROJECT mindmate-ai
> 状态：Draft / In Review
> 创建日期：2026-09-21
> 更新时间：2026-09-21
> 当前阶段：G6
> 关联决策：DEC-G6-001、DEC-G6-002、DEC-G6-003
> 关联证据：EVID-029、EVID-030、EVID-032、EVID-033

## 1. 变更结论

本轮将 Chat Provider 从 Alibaba Cloud Model Studio 修订为 DeepSeek API。DeepSeek 选择由本轮控制输入引用的所有者明确选择“我想用 DeepSeek API 解决”触发，按 `V3.2_IMMEDIATE_APPLY` 同轮应用为 `DEC-G6-003`。这是 Chat Provider 修订，不是 Embedding、成本、向量存储或运行时启用授权。

```text
CHAT_PROVIDER=DEEPSEEK_API
CHAT_MODEL=deepseek-flash
CHAT_MODEL_STATUS=OFFICIAL_CANDIDATE_NOT_USER_CONFIRMED
EMBEDDING_PROVIDER=TBD
PROVIDER_CHANGE_STATUS=APPLIED_CONDITIONAL
PROVIDER_RUNTIME_ENABLED=false
PROVIDER_GUARD_STATUS=BLOCKED
G6_STATUS=BLOCKED
```

## 2. 决策链

```text
DEC-G6-001
  └─ no-call / Provider 详情未决期间不发起真实请求（继续有效）
      └─ DEC-G6-002
          └─ Alibaba Chat + Embedding 条件性基线（Chat route 被 DEC-G6-003 取代）
              └─ DEC-G6-003
                  └─ DeepSeek Chat API 条件性基线；Embedding 仍 TBD
```

Alibaba 历史评审、Guard、价格、Evidence 和原始用户选择不删除；仅将 Alibaba Chat 路线标为 `SUPERSEDED_NOT_CURRENT_PROVIDER`。Alibaba 不是 DeepSeek 的自动回退。

## 3. DeepSeek 官方资料

本轮读取日期：2026-09-21。只读取官方 API 文档，不调用 API。

| 资料 | 当前核验事实 | 项目边界 |
|---|---|---|
| Models & Pricing | `deepseek-flash`，映射 DeepSeek-V4.1-Flash；1M 上下文；最大输出 384K；thinking/JSON/Tool Calls/Responses/Anthropic 功能公开 | 不证明账号、地区或条款 |
| Chat Completions | OpenAI 兼容 `https://api.deepseek.com`，`POST /chat/completions`；`stream=true` 提供部分消息增量/SSE | 项目正式流式、断线恢复和上传协议仍留 G9 |
| Thinking Mode | 默认 thinking，默认 effort high；支持 enabled/disabled 和 reasoning effort | 后续需定义模型参数和质量验收 |
| JSON Output / Tool Calls | 官方提供 JSON 和工具调用格式 | 需处理空内容、错误和失败恢复 |
| Rate Limit & Isolation | Flash 并发限制 2500；超限 HTTP 429；限制按账号计算 | 不代表用户账号配额已确认 |
| Pricing | 峰/非峰、缓存命中/未命中价格不同；费用从充值/赠送余额扣除，价格可调整 | 不代表 USD 5 预算已实现 |

当前未找到足以证明 API 数据处理、保留/训练、删除、子处理者、地域或用户账号资格的完整一手证据。消费者隐私政策不能替代开发者 API 条款。

## 4. 目标架构

```text
浏览器 Web UI
  ↓ 本机 REST/OpenAPI（方向）
本地后端 / Provider Adapter
  ↓ 读取本机 DEEPSEEK_API_KEY（运行时仍禁用）
DeepSeek API /chat/completions
```

- UI、Domain、RAG 和业务模块不直接依赖 DeepSeek SDK 或 Key。
- API Base URL、模型 ID、thinking、输出上限、预算和重试策略集中在配置层。
- API Key 只能由本地后端从环境变量或未提交 Secret 配置读取。
- 缺少 Key、余额不足、认证失败、429 或 Guard 未通过时安全失败，不自动切换、充值或重试绕过预算。
- 不上传完整原始文件或全部历史；只允许后续正式设计批准的必要问题、检索片段和有限上下文。

## 5. Guard 与状态

完整 Guard Matrix 见 [12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md](12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md)。

- 公开 API 文档：`PASS_PUBLIC_DOCS` / `PARTIAL_PUBLIC_ONLY`。
- API 数据处理、保留、训练、删除、地域：`UNVERIFIED / BLOCKED`。
- 账号、模型权限、余额：`NOT_VERIFIED / BLOCKED`。
- 成本保护：`PROPOSED_NOT_APPLIED / BLOCKED`。
- Provider runtime：`false`。
- G6 Exit：`BLOCKED`；G7：`NOT_READY`。

## 6. 剩余决策批次

上一轮集中展示了 Chat Model、Embedding、成本保护和本地向量存储 4 项。本轮用户已一次选择全部 A，应用结果由 `DEC-G6-004` 记录；以下选项说明保留为决策历史。

### `TECH-G6-CHAT-MODEL`

- A：`deepseek-flash`（官方当前低成本 Chat 候选，映射 DeepSeek-V4.1-Flash；推荐作为 V1 默认候选，但本轮尚未单独确认）。
- B：其它官方当前 DeepSeek Chat 模型（需重新比较价格、上下文、能力和账号可用性）。
- C：保持 TBD，暂不冻结模型 ID。

### `TECH-G6-EMBEDDING`

- A：本地 `BAAI/bge-small-zh-v1.5`（推荐：知识库切片不发送给外部 Embedding 服务；本机性能、质量和安装仍需后续验证）。
- B：其他外部 Embedding Provider（需重新核验条款、地域、成本和账号）。
- C：保持 TBD，G6 继续阻断。

DeepSeek 官方当前公开模型价格页未列 Embedding API；本轮不虚构 DeepSeek Embedding 选项。

### `COST-G6-PROVIDER`

- A：月软预算 USD 5；USD 4 提醒；USD 5 停止新调用；禁止自动充值/提额；手动恢复（推荐）。
- B：用户自定义预算、提醒和停止阈值。
- C：保持 TBD，Provider runtime 继续禁用。

### `TECH-G6-VECTOR-STORE`

- A：本地嵌入式向量存储，通过 `Storage Adapter` 与业务模块隔离（推荐方向；具体产品需 G8 Spike）。
- B：本地独立向量服务进程，通过本机接口访问（增加安装、启动和维护复杂度）。
- C：保持 TBD，暂不冻结产品/类别。

用户可一次回复：

```text
TECH-G6-EMBEDDING=A
COST-G6-PROVIDER=A
TECH-G6-VECTOR-STORE=A
TECH-G6-CHAT-MODEL=A
```

明确回复后按即时应用规则同轮应用；未回复项保持 `TBD/PENDING`，不要求二次确认。

## 7. 本轮四项选择的应用结果

- `TECH-G6-CHAT-MODEL=A`：`deepseek-flash` 已成为当前 Chat Model 条件性基线；账号、模型权限和 Provider guards 仍阻断运行时。
- `TECH-G6-EMBEDDING=A`：本地 `BAAI/bge-small-zh-v1.5` 方向已应用；不下载、不安装、不运行，CPU/GPU、质量和许可证 Spike 待后续阶段。
- `COST-G6-PROVIDER=A`：USD 5 月软预算、USD 4 提醒、USD 5 停止新调用、禁自动充值/提额和手动恢复策略已应用为政策；成本计数和运行时停止实现尚未完成。
- `TECH-G6-VECTOR-STORE=A`：本地嵌入式向量存储 + `Storage Adapter` 方向已应用；具体产品、物理共置、索引重建和失败恢复留 G8 Spike。

以上应用不解除 `OPEN-01`，不启用 Provider Runtime，不产生真实 API 费用，也不代表本地模型或向量产品已经安装或通过性能验收。
