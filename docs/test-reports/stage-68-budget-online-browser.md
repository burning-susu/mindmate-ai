# 第六十八批：阶段 8 本地预算核对与在线学习页面验收

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场 LOCAL：`b67c6ab20827ef9ce26393cefba02229e9a151e0`
- 进场 REMOTE：`49a3139ff591ee81f54121eb31e4a96eb27f5834`
- 第 67 批提交预推送：已尝试，命令退出码为 1 且无诊断文本；随后 `git ls-remote` 确认远端仍是进场 REMOTE。没有强推或改写历史。

## 验收状态

| 项目 | 状态 | 证据与边界 |
| --- | --- | --- |
| `LOCAL_BUDGET_RECONCILIATION` | `PASS` | SQLite 跨进程原子预留、请求阶段/费率快照、UTC 预算窗口、Chat/RAG/Learning 分组及未知用量守卫；33 项定向后端测试通过。只证明本地估算与守卫，不代表服务商账单。 |
| `PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未导入账单文件，也没有可用官方账单 API；页面明确显示“尚未与官方账单核对”。 |
| `LEARNING_ONLINE_CODE` | `PASS` | DeepSeek/OpenAI 使用仓库 `LearningProviderFixture` 与 `httpx.MockTransport` 执行真实学习业务路径；题目、点评、失败恢复和调用摘要测试通过。没有调用服务商网络。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 普通 Chrome 标签创建被自动审批层以 `404` 拒绝；Playwright Chromium 在创建页面前以 `spawn EPERM` 退出。没有页面点击、截图或在线学习会话，不能记为浏览器通过。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 没有真实 Key、真实 DeepSeek/OpenAI 请求或付费额度。 |
| 第六十七批页面遗留 | `PARTIAL` | `LOG_RETENTION_BROWSER`、`DIAGNOSTICS_PREVIEW_EXPORT_BROWSER`、`HISTORY_PURGE_BROWSER`、`HISTORY_MULTISTEP_BROWSER` 均保持原状态，本批未补普通浏览器证据。 |
| `STAGE8_FULL_V1` | `PARTIAL` | 仍有第六十七批页面验收、全局错误/离线体验与阶段 8 总验收矩阵未完成。 |
| 求职 Demo 可用性 | `PASS`（继承） | 沿用第四十二/六十四批既有证据；本批未重跑完整 Demo。 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 不用 Demo、MockTransport 或本批局部回归代替完整阶段验收。 |

## 本批实现

- Alembic `f78c9e8a1042` 在 `ai_operations` 与 `learning_provider_operations` 增加请求阶段、预留时间、可能外发时间、预留金额和价格快照。历史在线记录保留 tokens，但没有费率快照时按未知成本处理，不回填虚构费率。
- 预算预留在 SQLite `BEGIN IMMEDIATE` 写事务中，以唯一 `operation_id` 核算已知消费、未知外发和预留；跨进程并发不会重复看到同一笔余量。Chat/RAG 与学习出题/点评共用守卫。预算关闭时仍记录可得 tokens 和未知状态。
- 阶段区分 `NOT_SENT`、`RESERVED`、`POSSIBLY_SENT`、`USAGE_KNOWN` 和 `UNKNOWN`。响应 usage 与快照按单条操作结算；刷新/恢复不会重发已外发操作，也不会把未知 usage 归零。明确未发送的预留会释放。
- 周期支持滚动 30 天和 UTC 自然月；费用按 `request_sent_at` 归属，活动预留继续参与当前预算保护，历史查询使用半开 UTC 起止窗口。`GET /api/v1/system/ai-usage?start=...&end=...` 可查询旧窗口。
- 设置页分开显示已知费用估算、待发送预留、已外发未知预估、窗口、核对时间、未知用量策略、硬停止阻断原因，以及 DeepSeek/OpenAI 官方用量入口和带核对日期的价格来源。UTC 开始日与不包含结束日控件可查询历史窗口，不修改当前预算周期。计费仍由各 Provider 账户结算，估算不承诺费用上限。
- 测试专用 Provider fixture 增加一次性指定 Provider 出题失败路由，仅在 `learning_provider_fixture=True` 的测试运行时注册；响应不返回请求正文或凭据。测试覆盖失败不自动切换到另一 Provider。

## 自动化证据

| 门禁 | 命令或范围 | 结果 |
| --- | --- | --- |
| 后端预算/Provider/Chat/RAG | `pytest tests/test_stage8_settings_usage_budget.py tests/test_stage55_learning_provider.py tests/test_stage56_provider_fixture.py tests/test_stage6_knowledge_chat.py tests/test_stage6_chat_owner.py` | `33 passed`，使用仓库隔离 basetemp |
| Ruff | `ruff check src tests scripts` | 通过 |
| Pyright | 本批后端实现与定向回归文件 | `0 errors, 0 warnings, 0 informations` |
| Python 编译 | `compileall -q src tests migrations` | 通过 |
| Alembic | `heads` 与隔离浏览器数据根 `current` | 单一 head/current：`f78c9e8a1042` |
| 前端 | typecheck、lint、Vitest、build | `15 files / 72 tests passed`，其余三项通过 |
| OpenAPI / 生成类型 | `scripts/export_openapi.py`、`npm run api:generate` | OpenAPI 3.1，`111 schemas / 120 operations`；生成类型同步 |
| 差异检查 | `git diff --check` | 通过 |
| Playwright 页面验收尝试 | `stage56-online-learning.spec.ts` | 浏览器启动报 `spawn EPERM`，页面加载前退出；不是通过的页面证据 |

测试运行出现既有 Starlette/httpx 与 Alembic 配置弃用警告，不影响通过结果。Vite production build 保留 chunk-size 提示，主 JS chunk 为 `527.14 kB`。

## 浏览器隔离与阻断

- 核实 `backend/tests/stage56_online_browser_server.py`：强制 `env="test"`、使用 `InMemoryCredentialStore`，并为 DeepSeek/OpenAI 分别注入 `httpx.MockTransport`。fixture 调用摘要仅含 Provider、Host、请求模型、请求类别与授权头是否存在，不含正文或 Key。调用摘要里的官方 Host 是拦截前的请求目标，不表示发生了网络连接。
- 隔离数据根：`build/stage68-browser-isolated-2`；合成知识库 ID：`01a0e788-c4c1-797e-b744-e6c1c9895e2a`；测试 API/Web：`127.0.0.1:8028/5188`。health 返回 200，fixture calls 初始与结束均为 `{"calls":[]}`。验证后本批启动的 API/Vite 会话已停止，端口 8028/5188 已释放。发现 8018 上已有非 fixture 服务，未操作该服务。
- `cua.getState()` 只枚举出无标签的 Codex 内置浏览器，没有普通 Chrome/Edge。`cua.createBrowserTab("chrome", ...)` 在审批阶段返回 `404 Not Found`，提示当前模型账户不支持 `gpt-5.6-luna`；request id `0a19aac3-450a-4a04-b72c-b95abec366c6`，动作未执行。没有重复审批或绕过检查。
- Playwright Chromium 进程启动报 `spawn EPERM`，没有打开页面。没有截图、页面会话 ID 或浏览器调用计数，因此以上自动化 API/测试结果不冒充页面验收。
- 人工最短补验：使用 Chrome/Edge Guest profile 启动新的隔离 test-only 数据根并打开对应 Vite 页面；分别手动选择 DeepSeek 与 OpenAI，完成各一道在线出题和点评并刷新；再核对未同意、无 Key、预算阻断时 fixture count 不增加，及指定 Provider 故障不切换；保存页面截图、合成会话 ID 与 fixture 调用计数，不保存/提交合成凭据或截图。

## 保留事项

- `LOCAL_BUDGET_RECONCILIATION=PASS` 只表示本地预算估算和拦截规则有实现与隔离测试；实际账单仍以 DeepSeek/OpenAI 各自账户为准，官方对账保持 `PROVIDER_BILLING_RECONCILIATION=PENDING`。
- 下一批先补普通 Chrome/Edge 在线学习页面证据，再处理全局错误、离线体验与阶段 8 完整追踪矩阵。真实 Provider smoke 和阶段 8 完整 V1 不在本批通过范围内。
