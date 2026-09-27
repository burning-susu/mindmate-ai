# CHG-20260927-LEARNING-ONLINE-TEST-FIXTURE

- 日期：2026-09-27
- 状态：测试设施已实现；在线页面验收 `PARTIAL`
- 来源：用户指示执行第五十六批提示词。
- 影响对象：测试环境配置、服务端 Provider 传输注入、测试调用计数端点和 Playwright 验收入口。

## 目的

为浏览器实际点击学习页面时提供受控、可计数的 DeepSeek/OpenAI 假响应，确保在线请求进入真实后端门禁与持久化路径，却不会发往官方服务。

## 边界

- 夹具默认关闭，只允许 `env=test` 下显式启用。
- Provider Base URL 和模型仍使用冻结的官方值；测试使用固定 `httpx.MockTransport`，不接收任意 URL。
- Key 使用 `InMemoryCredentialStore`，不落盘、不写数据库、不进报告。
- 测试计数端点只返回 Provider、Host、模型、操作类型和 Authorization 是否存在，并且仅在夹具模式注册。
- 不修改生产 API 契约、数据库结构、Provider 决策或学习业务范围；没有 Alembic migration。

## 状态与 Evidence

后端夹具边界及第五十五批 Provider/阶段 7 学习回归共 `12 passed`。TestClient 通过真实学习 API 使用固定夹具分别完成 DeepSeek/OpenAI 的出题和点评，账本与服务端调用计数均正确。浏览器测试尚未执行页面操作：Playwright Chromium `spawn EPERM`，Codex 内嵌浏览器创建动作因自动审批服务 `404` 未执行。A 保持 `PARTIAL`，B 未开始。详情见 `docs/test-reports/stage-56-online-learning-multistep.md`。

### 第五十七批接续

同一测试夹具现用于 DeepSeek/OpenAI 各两题的业务/API 回归，并可在测试内模拟第二题外发结果未知。夹具仍仅在 `MINDMATE_ENV=test` 且显式开启时注册；请求仍被 `httpx.MockTransport` 截获，不接真实 Provider。第五十七批后端/Stage 7/55/56 定向测试共 `22 passed`。在线浏览器仍 `PARTIAL`，该结果不替代页面点击；详见 `docs/test-reports/stage-57-learning-multistep.md`。
