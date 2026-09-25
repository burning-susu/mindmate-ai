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

## 第三十二批：普通 Chat 服务端会话与生成闭环

> 验证日期：`2026-09-25`
> 分支：`feat/v1-bootstrap`
> 起始本地/远端 SHA：`79207ccb6d92d1bc0e76deb87edf2e67d4323ed2`
> 本批状态：`PASS`
> 阶段 6 状态：`PARTIAL`

### 结论

本批在第三十一批的凭据、外发同意和 DeepSeek Adapter 边界之上，完成了普通 `GENERAL_CHAT` 的服务端最小闭环：首条发送事务性创建会话、范围快照、用户消息、助手占位、回答版本、AI Operation 和持久生成任务；后续消息复用同一会话；Mock Provider 生成后回答、状态、模型和 usage 可持久化读取。普通聊天不执行 RAG，不创建 Citation，不发送文件、知识库、向量、路径或完整 Prompt。

### 实现范围

- Alembic `a7c9e1f2b304` 新增 `conversations`、`conversation_scopes`、`messages`、`ai_operations` 和 `answer_versions`，当前 head 已更新为 `a7c9e1f2b304`。
- 新增 `GET/POST /api/v1/conversations`、`GET /api/v1/conversations/{id}`、`POST /api/v1/conversations/{id}/messages`、`GET /api/v1/conversations/{id}/messages` 和 `GET /api/v1/ai-operations/{id}`。
- `Idempotency-Key`、`client_request_id`、请求哈希和会话 `row_version` 参与提交边界；相同请求返回原消息/占位/Operation，不同正文返回 `IDEMPOTENCY_KEY_REUSED`，同一会话生成中拒绝并发发送。
- `ChatProviderPort` 扩展 provider-neutral `ChatRequest/ChatResponse` 和 `generate`；新增确定性 `MockChatProvider`；DeepSeek httpx Adapter 增加非流式生成和安全 JSON/usage 解析。
- `ChatGenerationWorker` 使用 SQLite 持久任务、原子领取、租约和 TaskEvent；启动发现 `RUNNING` Operation 时转为 `INTERRUPTED`，不自动重发不确定的外部 Provider 请求。
- 外部 Provider 仍要求版本化外发同意、有效系统凭据和本地输入/输出上限；门禁拒绝时 Provider 调用次数为 0。未添加停止、重试、重新生成、继续生成或 SSE 端点。

### 测试与证据

定向服务端回归：

```text
uv run pytest tests/test_stage6_chat_owner.py -q
8 passed
```

覆盖空白页面不落库、首条原子创建、后续顺序、同 Key 重复/冲突、同意/Key/输入上限门禁、Provider 失败、重启中断、注入 Provider 和 DeepSeek 本地 HTTP fixture 请求体。Fixture 检查请求只包含普通聊天必要上下文，并确认 API Key 不进入数据库。

后端全量门禁：

```text
uv run pytest
214 passed, 167 warnings（约 180 秒）

uv run ruff check src tests scripts
All checks passed

uv run pyright src tests scripts
0 errors, 0 warnings, 0 informations

uv run python -m compileall -q src tests migrations scripts
通过

uv run alembic current
a7c9e1f2b304 (head)
```

前端和契约门禁：

```text
npm run api:generate
Generated 60 schemas and 68 operations.

npm run test -- --run
25 passed（7 个 test files）

npm run lint
通过

npm run typecheck
通过

npm run build
通过
```

### 外部调用与未完成边界

Mock Provider 和本地 HTTP fixture 实际运行；没有真实 DeepSeek API Key、真实 DeepSeek 请求、付费 API、用户私人资料或模型外发，因此未验证真实外部联通、余额、价格或实际计费。阶段 6 仍为 `PARTIAL`：聊天前端、可恢复 SSE/停止、重试/重新生成、RAG/Citation、Learning owner、预算执行和自动 Provider 切换留待后续批次；阶段 5 的 Citation owner、用户级 RAG、质量/性能门禁继续保持 `PARTIAL`。

## 下一批唯一目标

在本批服务端普通 Chat owner 之上实现普通聊天前端与可恢复 SSE/停止闭环，继续禁止 RAG、Citation、学习陪练和自动 Provider 切换。
