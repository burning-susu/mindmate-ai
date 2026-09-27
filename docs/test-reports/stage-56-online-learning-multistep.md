# 第五十六批：在线学习页面验收与逐题练习

日期：2026-09-27。进场分支 `feat/v1-bootstrap`，本地和 `origin/feat/v1-bootstrap` 起始 SHA 均为 `083073cff29ee1d6b92dc3ff472991d80faf4435`，工作区干净。

## 状态

| 项 | 本批状态 | 证据口径 |
| --- | --- | --- |
| `PROVIDER_TEST_FIXTURE` | `PASS` | 仅测试环境注入；真实学习 API 业务路径使用固定假响应完成 DeepSeek/OpenAI 各一题和点评 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | E2E 用例已建立，但 Chromium 无法启动，未实际点击页面 |
| `LEARNING_MULTISTEP` | `PENDING` | A 未通过，依提示词停止，B 未开始 |
| `DEMO_REGRESSION` | `PENDING` | 本批没有新的完整浏览器 Demo 证据；第五十五批 `PASS` 保留为历史值 |
| `OPENAI_LIVE_SMOKE` | `PENDING` | 没有真实 Key 或付费调用 |
| `DEEPSEEK_LIVE_SMOKE` | `PENDING` | 没有真实 Key 或付费调用 |
| `STAGE7_FULL_V1` | `PARTIAL` | 阶段 7 完整需求仍未满足 |
| `STAGE8_FULL_V1` | `PARTIAL` | 原有未关闭项不变 |

第四十二批 Demo `PASS`、第五十五批 Demo `PASS` 分别作为各自历史证据保留，不合并为本批结果。

## A. 在线页面验收

### 实现

- 新增 `learning_provider_fixture` 配置，默认关闭。只有 `env=test` 且显式开启时可启动；其他运行环境开启该标志会拒绝启动。
- 服务端 DeepSeek 与 OpenAI 固定适配器在夹具模式下使用 `httpx.MockTransport`，固定返回引用编号为 1 的合成题目/点评，且只记录固定 Provider Host、请求模型和请求类别。没有接受任意 Provider URL 的入口。
- 夹具模式使用 `InMemoryCredentialStore`。只在夹具模式注册 `/api/v1/testing/provider-fixture/calls`，只返回 Provider、Host、模型、题目/点评类别及 Authorization 是否存在，不返回 Key、提示正文或资料摘录。
- 新增隔离浏览器服务启动脚本和 Playwright 用例，覆盖设置页选择两家 Provider、Key 与分别同意、每次费用确认、页面出题/提交、服务端请求计数、切换 Provider 后旧会话保持原 Provider，以及刷新恢复。

### 阻断与现场

- Playwright 启动浏览器失败：`browserType.launch: spawn EPERM`，错误上下文记录在被忽略的 `frontend/test-results/` 下。用例在 19ms 时失败，发生于浏览器启动前，未进入 UI 操作。
- Codex 内嵌浏览器备用创建动作被自动审批服务拒绝，返回 `404 Not Found: Model "gpt-5.6-luna" is not supported by any configured account in this group`。动作没有执行；这不是安全策略拒绝。没有绕过审批。
- 隔离服务：数据根 `backend/build/mindmate-stage56-online-browser-data`；页面 `http://127.0.0.1:5180/settings`；API `http://127.0.0.1:8012`；合成知识库 `01a0e27e-fb0e-793c-9eeb-4d39c394c15a`。服务端夹具调用计数仍为 0，没有截图。
- 本机页面和服务端调用计数留作 A 的人工/工具恢复入口；在线会话尚未创建。

### 无外呼路径

第五十五批后端回归在隔离 API 环境下复测通过：未确认本次费用、缺少 Key、预算硬停止和恢复后需重新确认时 Provider 调用计数均为 0。它们是服务端门禁回归，不替代本批浏览器点击证据。

## B. 逐题练习

本批未开始 B。附件要求 A 通过后才能实施 1～5 题练习；当前 A 为 `PARTIAL`，因此不改题量、数据模型、会话状态机、API、迁移或页面功能。

## 验证

- 后端定向：新增夹具边界及业务路径测试 3 项；与 `test_stage55_learning_provider.py` 和 `test_stage7_learning_session.py` 合计 `12 passed`。TestClient 通过真实学习 API 分别触发 DeepSeek/OpenAI 出题与点评；确认账本 Provider 身份、题目未泄答案键、确定性评分、有效来源引用，以及服务端夹具每家 2 次请求（出题、点评）。改动文件 Ruff 通过、Pyright `0 errors`、Python compileall 通过。Alembic head `b55c0e1a8d27`，本批无迁移。只使用合成资料、测试凭据和 MockTransport。
- 前端：Vitest `61 passed`；`npm run typecheck`、`npm run lint`、`npm run build` 通过。build 提示主 JS chunk `502.02 kB`。
- Playwright：目标用例已写入，但被 Chromium `spawn EPERM` 阻止，未产生页面交互证据。
- 本批没有数据库迁移，没有生产 OpenAPI/前端 API 类型变化；当前 Alembic head 沿用 `b55c0e1a8d27`。
- 本批 Demo 浏览器回归和全量后端 pytest 尚未完成；浏览器阻断下未运行全量验收。
- 没有真实 DeepSeek/OpenAI 请求、真实凭据、付费外呼、默认个人数据根或私人资料。

## 下一步

恢复可用浏览器后，先完成 A：两家各自通过页面点击实际触发一题与点评，验证费用和授权门禁、服务端假 Provider 计数、答案隐藏、来源定位、刷新恢复及 Provider 冻结。A 通过后再按附件进入 B。完整阶段 7 和阶段 8 继续 `PARTIAL`。

## 第五十七批接续记录

第五十七批在同一工作区完成 1–5 题逐题练习；本报告中的第五十六批浏览器现场、未执行 B 的历史事实保持不变。接续时第五十六批文件仍是本地未提交改动。

第五十七批只做了一次新的隔离服务启动诊断：服务执行完数据库迁移并输出合成知识库 ID 后退出，未进入浏览器、未截图、未产生当前批浏览器点击证据。`LEARNING_ONLINE_BROWSER` 继续 `PARTIAL`。提交权限检查在 `.git/index.lock` 返回 `Permission denied`，第五十六批仍未提交或推送。当前批完整状态和自动化证据见 `docs/test-reports/stage-57-learning-multistep.md`。
