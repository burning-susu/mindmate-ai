# CHG-20260927-OPENAI-PROVIDER

- 日期：2026-09-27
- 状态：已批准并在本批应用
- 来源：用户本轮直接指令（第五十四批执行提示词）。这是一次决策应用，不再作为待二次确认的阻塞项。
- 影响对象：`DEC-AI-001` 至 `DEC-AI-005`、`DEC-AI-011`、`DEC-AI-012`，设置页，Chat 路由，用量估算。`DEC-CHAT-008` 保持禁止自动切换。本地 Embedding、索引、无服务器决策保持。

## 旧基线

在线 Chat Provider 只有 DeepSeek API。默认模型别名 `deepseek-flash`，Base URL `https://api.deepseek.com`。凭据、外发同意和连接探测都以 DeepSeek 为中心。演示模式为 Mock。

## 新基线

| 模式 | 标识 | 角色 |
| --- | --- | --- |
| Mock | `mock` | 默认演示。启动、刷新、测试和未显式选择在线服务时不外发、不产生费用。 |
| DeepSeek 在线 | `deepseek` | 默认在线选项。官方 Base URL `https://api.deepseek.com`，请求别名 `deepseek-flash`。 |
| OpenAI GPT-6 Sol 在线 | `openai_gpt6_sol` | 用户可选在线选项。官方 Base URL 只允许 `https://api.openai.com/v1`，请求模型 ID 固定 `gpt-6-sol`。 |

两家都要各自的 API Key、外发同意版本、连接探测和单次费用确认。OpenAI 与 DeepSeek 是两套账户、两套 Key、两套账单。界面不能输入任意 Base URL、代理网关或模型名。

价格展示是带核对日期的估算，不是账单或严格金额承诺。DeepSeek 公开价核对日 `2026-09-26`；OpenAI `gpt-6-sol` 官方模型页核对日 `2026-09-27`（文本输入约 2 美元 / 百万 Token，输出约 10 美元 / 百万 Token；超长输入、区域处理和 Batch/Flex 等附加规则不在本估算内）。价格变化时回到未知并提示更新。预算无法与官方账单逐笔对账时继续标 `PARTIAL`。

## 选择与失败

- 持久设置只接受 `mock`、`deepseek`、`openai_gpt6_sol`。损坏或旧配置读出非法值时，仅在读取修复路径回退到 Mock。
- 在线请求失败（401/403/429/5xx、超时、断流）显示失败。不静默改到另一家，也不改到 Mock。
- 每条新 `AiOperation` 冻结当时的 Provider、模型别名、费用确认和范围。生成中途改设置不换模型、不串写 usage、不给旧对话改标。
- `requested_model` 使用固定请求别名；`resolved_model` 只记录响应里的真实模型，不接受客户端自报。
- usage 缺失记为未知，预算门禁按保守策略处理，不把未知记成已结算 0。旧 DeepSeek 记录不得归到 OpenAI。

## 凭据与同意

- DeepSeek：`provider/deepseek/api-key`，同意版本 `deepseek-external-ai-v1`。
- OpenAI：`provider/openai/api-key`，同意版本 `openai-external-ai-v1`。
- 密钥只进 Windows Credential Manager。不进 SQLite、日志、OpenAPI、Git、浏览器本地缓存或备份。删除或覆盖一家不影响另一家。
- 一家的同意不能代替另一家。恢复后两家都要重新核对同意和 Key 状态，生成模式回到 Mock。
- 探测只在用户显式点击，并确认这会发送一条测试请求且可能产生费用之后发生。没有 OpenAI Platform Key 时显示未配置/不可用。不借用 Codex、ChatGPT 登录态或第三方网关额度宣称已联通。

## 调用契约

OpenAI 适配器复用 `ChatProviderPort` 和 `httpx`，不新增 SDK。生产请求走 Chat Completions 文本流。按 2026-09-27 官方模型页与 Chat Completions 参考，本适配器发送 `model=gpt-6-sol`、`max_completion_tokens`、`reasoning_effort=none` 和流式 `stream_options.include_usage`。不发送 DeepSeek 的 `temperature` / `max_tokens`，不调用内建工具，不把推理字段写入正文。厂商 SSE 在适配器内转成现有文本增量，不透传给浏览器。严格 TLS、禁止重定向、有限超时、响应长度上限和取消保持。

## 本批范围

- 聊天：普通聊天和知识库聊天路由到用户选中的 Provider。证据不足和来源失效时两家都是 0 外呼。知识库回答仍要求正确引用编号，否则失败而不是伪成功。
- 学习：一题出题和反馈仍是 `learning-demo-fixture-v1` 本地规则。设置页和学习入口写明“模型选择目前适用于 AI 对话；学习出题仍是本地演示规则”。本批不把选中 GPT-6 Sol 显示成已由该模型出题，也不把未审查的模型输出写入 `Question` / `Feedback`。
- 下一目标（另批验收）：用已有适配器在学习会话做严格基于资料的模型出题和点评。那不是本批完成项，也不等于完整 V1 学习已经实现。

## 证据口径

`OPENAI_ADAPTER_TESTED` 只表示本地 MockTransport / fixture 通过。`OPENAI_LIVE_VERIFIED` 在没有用户授权的真实 OpenAI Platform 调用前保持 `PENDING`。模拟 200 不能写成真实联通。
