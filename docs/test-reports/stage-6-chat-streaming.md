# 阶段 6 普通聊天流式与停止恢复测试报告

## 批次结论

- 批次：第三十三批，普通聊天（`GENERAL_CHAT`）流式前端、断线恢复与停止闭环。
- 结论：`PASS`（本批范围内）。阶段 6 继续 `PARTIAL`，阶段 5 继续 `PARTIAL`。
- 时间：2026-09-25。
- Provider 边界：默认 Mock Provider；DeepSeek 仅使用本地 HTTP fixture。没有真实 API Key、真实 DeepSeek 请求、付费调用或私人资料。

## 事件与状态契约

- 创建消息的 `POST /api/v1/conversations` 和 `POST /api/v1/conversations/{conversation_id}/messages` 仍快速返回持久 `conversation_id`、消息占位、`operation_id` 和 `events_url`；创建与订阅分离。
- `GET /api/v1/ai-operations/{operation_id}/events` 返回 `text/event-stream`。每个 TaskEvent 使用单调递增的 `id`，数据带 `operation_id`、`event_sequence`、文本 `content`、文本 `sequence`、状态和终态标识。`SNAPSHOT` 是完整文本快照，前端按事件序号替换，不追加分片。
- 订阅支持 `Last-Event-ID` 和 `after` 游标。断线、刷新或重复订阅只读取已有 TaskEvent，不重新调用 Provider。
- 状态为 `QUEUED → RUNNING → STOPPING → STOPPED` 或 `COMPLETED/FAILED/INTERRUPTED`。显式停止先持久化 `stop_requested`，Worker 在下一个快照边界或终态提交前用同一事务裁决；自然完成先提交时完成胜出，停止先提交时停止胜出。
- Task checkpoint 同时保存当前完整回答、文本序号、TaskEvent 序号和停止标记；助手消息与 AnswerVersion 保留已经生成的部分正文。
- `POST /api/v1/ai-operations/{operation_id}/stop` 幂等；重复停止返回最终状态。兼容别名 `.../cancel` 不新增另一套语义。

## 实现范围

- Provider：新增 provider-neutral `ChatStreamChunk`/`generate_stream`；Mock 以确定性分片输出，DeepSeek 解析 OpenAI-compatible SSE、多行 `data`、`[DONE]`、usage、模型和安全错误。
- Worker：沿用第三十二批 `ChatGenerationWorker` 与 SQLite `BackgroundTask` owner，分片持久化快照，显式停止不依赖 HTTP 连接生命周期；应用关闭仍将不确定的运行中外部请求收敛为 `INTERRUPTED`，不自动重发。
- API：新增 SSE 订阅、停止动作、活动 Operation 标识和快照/事件序号字段；OpenAPI 3.1 与前端生成类型同步。
- 前端：`/chat` 与 `/chat/:conversationId` 接入真实会话列表、消息历史、首次/继续发送、SSE 解析、有限次重连、断线提示、停止轮询和刷新恢复；页面只保存服务端 ID 与短暂 UI 状态，不保存 Provider Key。

## 验证证据

### 后端

- `uv run pytest -q --disable-warnings`：`217 passed`（最终输出 `100%`；包含阶段 4/5/6 全部回归）。
- `uv run pytest tests/test_stage6_chat_owner.py tests/test_stage6_provider_configuration.py -q`：`16 passed`。
- 新增服务端覆盖：快照 SSE 事件序号与完成事件、游标后重订阅不重复生成、停止与自然完成竞态、重复停止幂等、DeepSeek 本地 SSE fixture 增量分片。
- `uv run ruff check src/mindmate/ai/providers src/mindmate/application/chat_generation.py src/mindmate/api/chat.py`：通过。
- `uv run pyright src/mindmate/ai/providers src/mindmate/application/chat_generation.py src/mindmate/api/chat.py`：`0 errors`。
- `python -m compileall -q src`：通过。

### 前端与契约

- `uv run python ..\scripts\export_openapi.py`：OpenAPI 3.1 导出成功。
- `npm run api:generate`：生成 `60 schemas / 70 operations`，工作区生成文件与 OpenAPI 一致。
- `npm run typecheck`：通过。
- `npm run lint`：通过（无 error）。
- `npm test -- --run`：`8 test files / 27 tests passed`（包含分片/多行 SSE 解析回归）。
- `npm run build`：Vite 生产构建通过。

### 真实本地联调

- 使用独立临时数据目录和 Mock Provider，通过真实 FastAPI + Vite 代理完成：发送消息 → 返回 Operation → 多个 `SNAPSHOT` → `COMPLETED` → 页面显示持久回答；Provider 调用次数为 `1`。
- 使用延迟 Mock Provider 完成：发送消息 → 中途显式停止 → 保留已生成正文 → Operation/助手消息最终为 `STOPPED`；后续分片没有写入。
- 浏览器 `http://127.0.0.1:5174/chat` 实际发送普通聊天消息，页面显示会话列表、用户问题、流式完成回答和 `已完成`；浏览器错误日志为空。

## 未完成与边界

- 没有验证真实 DeepSeek 网络、账户余额、真实凭据或付费调用；DeepSeek 只通过本地 HTTP fixture 验证协议解析与错误边界。
- 本批不实现 RAG、知识库范围、Citation 绑定、学习陪练、重新生成/答案版本切换、预算执行或自动 Provider 切换。
- 断线重连使用有限次数前端重试和服务端快照补偿；长期离线、浏览器进程崩溃后的安装包级恢复仍需后续发布验证。
- 阶段 5 状态保持 `PARTIAL`；阶段 6 状态保持 `PARTIAL`，不能据此宣称最终产品验收或真实 Provider 已联通。

## 下一批唯一目标

在本批普通 Chat owner、事件快照和停止状态之上，完成普通聊天的重试/重新生成与答案版本切换契约；继续不打开 RAG、Citation、学习陪练或自动 Provider 切换。
