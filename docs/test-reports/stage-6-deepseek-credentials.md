# 阶段 6：DeepSeek 凭据配置与最小连接测试报告

> 批次：第三十一批
> 验证日期：`2026-09-25`
> 分支：`feat/v1-bootstrap`
> 起始本地/远端 SHA：`8fff8670d74784aee04eaa3a585a2f9f329050db`
> 本批状态：`PARTIAL`
> 阶段 5 状态：`PARTIAL`

## 结论

本批完成了 DeepSeek API Key 的本机安全凭据生命周期、显式外发同意记录、固定最小连接探测和设置页配置流程。Key 只进入 `CredentialStorePort` 的 Windows Credential Manager 实现；SQLite 只保留非秘密的 Provider profile `secret_reference`、同意版本和探测状态。前端不读取已保存 Key，提交后清空输入，不使用 LocalStorage 或全局状态保存明文。

本机 Windows Credential Manager 使用一次性 fixture 值完成写入、读取、存在性检查和删除；隔离内存凭据存储与本地 HTTP fixture 覆盖配置、覆盖、删除、失败保留 Key、幂等/锁保护、固定请求体和错误映射。没有真实 DeepSeek API Key、用户文件、检索片段或付费外部请求，因此不能宣称真实 Provider 已联通，也没有产生真实 API 费用。

## 官方资料复核

开发日通过官方文档复核：

- Chat Completions：<https://api-docs.deepseek.com/api/create-chat-completion>
- 模型与价格：<https://api-docs.deepseek.com/quick_start/pricing>

本次复核仍使用冻结值：`https://api.deepseek.com`、请求别名 `deepseek-flash`、OpenAI-compatible Chat Completions。价格和别名背后的实际模型属于易变外部信息，应用只保存每次探测返回的 `resolved_model`，不把价格写死在代码中。

## 实现范围

- `CredentialStorePort`、Windows Credential Manager 适配器和显式隔离 `InMemoryCredentialStore`；非 Windows 或非 Windows keyring 后端不会回退到明文文件。
- `DeepSeekChatProvider` 通过 `httpx` 发送固定探测：短文本 `请只回复：连接测试成功`、`max_tokens=8`、`temperature=0`、`stream=true`，不携带用户问题、文件、路径、知识库或会话。
- 统一映射鉴权、额度/余额、限流、5xx、连接/读取超时、网络和异常响应；失败不删除 Key，并只保存安全错误码和可读说明。
- `GET /api/v1/ai/provider`、`POST/DELETE /api/v1/ai/provider/key`、`POST /api/v1/ai/provider/test`、`GET/POST /api/v1/ai/consent`；同步 OpenAPI 与前端生成类型。
- 设置页提供 DeepSeek 固定 Provider、Key 显示/隐藏、保存/覆盖/删除、外发说明、官方 Key/价格入口、版本化同意和显式探测确认。配置状态、同意状态、探测状态分开显示。
- `keyring` 提升为运行时依赖，确保 one-folder/安装环境不会因仅存在开发依赖而无法访问系统凭据。

## 安全证据

- 数据库查询确认未写入 fixture Key；API 响应、ProblemDetail、前端状态和失败详情均不含 Key 或 Provider 原始错误正文。
- 连接探测必须带 `confirm_external_transfer=true`；设置页未勾选“固定测试文本和极小 API 用量”时按钮禁用，后端也拒绝绕过 UI 的未确认请求。
- 探测结果只记录 `checked_at`、请求别名、实际模型、流式/usage/结构化能力状态、可脱敏请求 ID和响应指纹；未可靠验证的能力为 `unknown`。
- 保存、删除、探测共用进程内 Provider 锁；应用仍由本地 Host/Origin/Session/幂等键中间件保护。
- Windows 实机一次性 fixture 验证 `set/get/has/delete`；真实用户 Key 未被请求、读取或展示。

## 测试与门禁

定向后端：

```text
uv run pytest tests/test_stage6_provider_configuration.py -q
12 passed
```

覆盖内容包括：配置→状态→覆盖→删除、无自动请求、固定请求体、显式外发确认、成功流式探测、usage token 记录、401 失败仍保留 Key、版本化同意、403/402/429/5xx/读取超时映射、并发重复配置幂等、响应/数据库/日志/备份秘密泄露检查以及 Windows Credential Manager 实际写读删。

后端静态检查：

```text
uv run ruff check src tests/test_stage6_provider_configuration.py
All checks passed

uv run pyright src tests/test_stage6_provider_configuration.py
0 errors

uv run python -m compileall -q src tests/test_stage6_provider_configuration.py
通过
```

前端定向检查：

```text
npm run test -- --run src/test/stage6-provider.test.tsx
2 tests passed

npm run typecheck
通过

npm run lint
通过
```

完整后端门禁：

```text
uv run pytest
206 passed, 158 warnings（209.06 秒）

uv run ruff check src tests scripts
All checks passed

uv run pyright src tests scripts
0 errors, 0 warnings, 0 informations

uv run python -m compileall -q src tests migrations scripts
通过

uv lock --check --offline
通过；Alembic head：6b3e91a0c4d7
```

前端全量门禁和浏览器流程：

```text
npm run test -- --run
25 passed（7 个 test files）

npm run lint
通过

npm run typecheck
通过

npm run build
通过

npm run test:e2e -- --workers=1 e2e/stage6-provider.spec.ts
1 passed（真实 Chromium、隔离后端和 Windows Credential Manager fixture）
```

OpenAPI 3.1 已重新导出并生成前端类型：`51 schemas / 62 operations`；`ApiKeyRequest.api_key` 为 `writeOnly/password`。本批未运行真实 DeepSeek、未请求真实用户 Key、未发送用户资料。

## 未完成与边界

- 阶段 6 仍为 `PARTIAL`：尚未实现普通聊天消息 owner、正式生成、SSE UI、RAG 回答、Citation 绑定、学习陪练、预算执行或自动回退。
- 本机 Credential Manager 已验证，但干净 Windows 安装包、升级/卸载保留数据和进程级重启后的凭据读取仍属于发布门禁，不在本批冒充完成。
- Provider 的流式能力只在 fixture 流事件中验证；真实 DeepSeek 的实际模型、usage 字段、价格、余额和服务条款没有通过真实调用确认。
- 阶段 5 的 Citation owner、发布级 Recall@10、10 万 Chunk 性能、最终答案质量和 AC-KB-* 全量验收继续保留为 `PARTIAL` 遗留项。

## 下一批唯一目标

在本批凭据和外发同意门禁之上，建立阶段 6 普通 Chat owner 的最小服务端生成边界；继续禁止 RAG/Citation、SSE UI、学习陪练和自动 Provider 切换。
