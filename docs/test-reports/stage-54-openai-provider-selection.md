# 第五十四批：双 Provider 手动选择与 OpenAI 适配器

- 日期：2026-09-27
- 分支：`feat/v1-bootstrap`
- 进场 SHA：`d5b27a8c5a0c1618208c937d7ba568deb978e6a1`（与当时 `origin/feat/v1-bootstrap` 一致）
- 变更记录：`docs/project/changes/CHG-20260927-OPENAI-PROVIDER.md`
- 没有数据库迁移。冻结的服务、模型和费用确认写在生成任务检查点里。

## 状态

| 项 | 状态 | 说明 |
|----|------|------|
| `OPENAI_ADAPTER` | `PASS` | `OPENAI_ADAPTER_TESTED`。MockTransport 覆盖官方 Chat Completions 契约、错误映射和缺失 usage。不是 `OPENAI_LIVE_VERIFIED` |
| `SETTINGS_MANUAL_SELECTION` | `PASS` | 三个互斥选项、分家 Key/同意/探测；切换本身不发付费请求。浏览器与定向测试都核对过 |
| `CHAT_ROUTING` | `PASS` | 普通对话按当次冻结的服务走。知识库正例、缺引用失败和证据不足 0 次外发由 MockTransport 覆盖。隔离浏览器库没有 READY 索引，没有在浏览器里跑知识库问答 |
| `LEARNING_PROVIDER_GENERATION` | `PENDING` | 本批不把学习出题接到 GPT-6 Sol。一题生成和反馈仍是 `learning-demo-fixture-v1` |
| `OPENAI_LIVE_SMOKE` | `PENDING` | 没有官方 Key，没有真实 OpenAI 或 DeepSeek 请求 |
| 独立备份 Worker | `PARTIAL` | 本批未改 |
| 周期硬限额完整账单对账 | `PARTIAL` | 估算仍不能当作官方账单。用量按服务拆分，未知 usage 不当作已结算 0 |
| 第 51 批浏览器删除确认 / 手动永久删除 UI | `PENDING` | 本批未做 |
| 多题定位 | `PARTIAL` | 本批未做 |
| 第 53 批 `BACKUP_RESTORE` | `PASS` | 维持原证据。定向恢复测试仍通过 |
| 求职 Demo（第 42 批） | `PASS` | 维持原证据。本批只在空库复核了 Mock 普通对话，没有重跑整条 Demo |
| 阶段 5–8 完整 V1 | `PARTIAL` | 不因本批适配器通过而标成完成 |
| 真实 DeepSeek | `PENDING` | 未调用 |

## 产品边界

- 持久模式只接受 `mock`、`deepseek`、`openai_gpt6_sol`。损坏或旧配置读出非法值时，只在读取路径回到 Mock。在线失败不会改选另一家。
- OpenAI 生产地址只允许 `https://api.openai.com/v1`，请求模型固定 `gpt-6-sol`。界面不能填写 Base URL、网关或模型名。
- 请求使用 `max_completion_tokens` 和 `reasoning_effort=none`，流式带 `stream_options.include_usage`。不发送 `temperature`、`max_tokens` 或 tools。推理字段不写入回答正文。浏览器只收到既有任务事件，不收到原始 OpenAI SSE。
- 凭据引用分开：`provider/deepseek/api-key` 与 `provider/openai/api-key`。同意版本分开：`deepseek-external-ai-v1` 与 `openai-external-ai-v1`。
- 价格是带日期的估算。OpenAI 文本估算核对日 `2026-09-27`（输入 2、输出 10 美元 / 百万 token）。DeepSeek 估算仍核对于 `2026-09-26`。

## 自动化

- 定向 pytest：`tests/test_stage54_openai_provider.py`、`tests/test_stage6_provider_configuration.py`、`tests/test_stage6_knowledge_chat.py`、`tests/test_stage6_chat_owner.py`、`tests/test_stage8_settings_usage_budget.py`、`tests/test_stage7_learning_session.py`，`48 passed`。
- 另跑 `tests/test_stage54_openai_provider.py`、`tests/test_stage6_provider_configuration.py`、`tests/test_stage8_backup_restore.py`，`28 passed`。恢复闭环没有被 OpenAI 同意清理改坏。
- `uv run ruff check src tests scripts` 通过。
- 本批改动文件的 Pyright 为 `0 errors, 0 warnings, 0 informations`。全量 `pyright src tests` 仍有 43 条既有错误，位于历史清理 Worker、任务保留 Worker 和备份测试，不是本批新增。
- OpenAPI 3.1 导出后前端类型为 `104 schemas / 113 operations`，`generation_mode` 含 `openai_gpt6_sol`。
- 前端 `npm run test -- --run` 为 `61 passed`（15 个文件）。`typecheck`、`lint`、`build` 通过。`git diff --check` 通过。
- 全量 Vitest 首次在首页用例上超过 Testing Library 默认 1 秒等待。已把等待调到 4 秒、单测超时调到 15 秒，之后全量通过。
- 测试使用固定价格快照和注入的 httpx transport。没有公网付费请求，没有真实 Key。

## 浏览器

- 数据根：`%TEMP%\mindmate-ai-stage54-provider`。API `127.0.0.1:8024`，页面 `127.0.0.1:5184`。`MINDMATE_PROVIDER_MODE=mock`。没有使用默认个人数据库。
- 设置页同时看到 Mock、DeepSeek、OpenAI GPT-6 Sol。默认 Mock 按钮禁用。OpenAI 显示“未配置 / 不可用”。两家探测按钮在未确认前禁用。页面写明两套账户、Key 和账单，以及“模型选择目前适用于 AI 对话；学习出题仍是本地演示规则。”
- 点击“使用 OpenAI GPT-6 Sol”后横幅变为 OpenAI 在线说明，没有探测请求。无同意时创建对话，操作失败码 `EXTERNAL_AI_CONSENT_REQUIRED`，provider `OPENAI`，请求模型 `gpt-6-sol`。
- 只记录 `openai-external-ai-v1` 后再次发送，失败码 `PROVIDER_NOT_CONFIGURED`，详情写明尚未配置 OpenAI API Key，且未改用其他服务。
- 再切到 DeepSeek。OpenAI 同意仍在，DeepSeek 同意仍是待确认。无 Key 的 DeepSeek 对话失败码 `EXTERNAL_AI_CONSENT_REQUIRED`，provider `DEEPSEEK`，请求模型 `deepseek-flash`。
- 切回 Mock 后，页面发送“请用一句话回复：隔离演示”，回答为 `Mock response: 请用一句话回复：隔离演示`，状态已完成。刷新后同一会话仍在。
- 学习新建页状态为同一句本地演示规则，没有把 GPT-6 Sol 说成出题模型。
- 停掉本次 API 进程后脚本正常退出，再用同一数据根启动。设置仍是 Mock，OpenAI 同意版本仍在，DeepSeek 仍待确认，OpenAI 仍未配置。原 Mock 会话在重启后仍能打开。
- 生产适配器不允许改 Base URL，所以浏览器没有把成功的 OpenAI 流式回答打到本地夹具。成功流、错误码和 0 次外发由 MockTransport 测试负责。

## 未做

- 没有读取 Codex / ChatGPT 登录，也没有连接第三方网关。
- 没有自动探测、自动重试付费请求或自动换模型。
- 学习出题仍不走在线适配器。
