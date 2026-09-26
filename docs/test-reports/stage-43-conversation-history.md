# 第四十三批：对话历史找回与只读恢复

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 进场 SHA：本地与 `origin/feat/v1-bootstrap` 均为 `32f4f7ecec0551497c4b7739ce81e8a4d6f0d454`，工作区干净。
- 本批历史切片：`PASS`
- 阶段 8：`PARTIAL`
- 求职 Demo：维持第四十二批 `PASS`。本批没有重跑空库上传、建库和一题学习。
- 真实 DeepSeek：`PENDING`。全程 Mock，没有 Key，没有外发。

## 交付

- `/history` 从侧栏辅助区和聊天页进入。列表读取 `GET /api/v1/history/conversations`。
- 列表字段是会话 ID、标题、最多 80 字摘要、普通/知识库模式、范围名、会话状态、来源状态、消息数和最近活动时间。不返回消息正文、模型名或密钥。
- 默认每页 30 条，最大 100 条。游标按 `last_active_at` 降序和会话 ID 降序，不透明且不含正文。
- 点击后进入原 `/chat/:conversationId`。消息和 Citation 仍走原读取接口。打开历史不创建会话，也不重新生成。
- 已软删除的会话不列出。知识库来源被回收、永久删除或索引不再就绪时，列表标为 `SOURCE_INVALID`，打开后仍可读历史正文。点击失效来源显示当前状态；历史摘录标明不能当作当前资料可用。
- Alembic `b4e1c8a09d27` 只为未回收会话增加 `(last_active_at, conversation_id)` 部分索引。没有新会话表。

## 自动化

- `uv run pytest tests/test_stage8_conversation_history.py`：`3 passed`。覆盖排序、分页、排除回收会话、长正文不进列表、重启同一数据根后消息 ID 和正文不变、索引不再就绪、回收站和永久删除。
- `npx vitest run src/test/stage8-history.test.tsx`：`3 passed`。覆盖空列表不创建会话、打开原会话并查看已删除来源、接口失败可重试。
- `uv run ruff check` 覆盖本批后端文件，通过。`uv run pyright` 覆盖历史模块和 `main.py`，`0 errors`。
- `npm run typecheck` 通过。本批前端 ESLint 无错误。
- 没有重跑后端全量 pytest。切块 Worker 领取时序问题本批没有碰到。

## 浏览器与重启

- 数据根：`%TEMP%\mindmate-ai-stage43-history`。准备脚本使用 `docs/test-data/stage5-fixed-ready/` 和已校验 ONNX，没有下载模型。主库 `01a0ddd1-f454-70e9-937d-104b8d73009f`，活动索引 `01a0ddd2-0058-795e-916b-69979cd7938f`，状态 `READY`。
- 服务：`.\scripts\dev.ps1 -DataDir ... -ApiPort 8002 -WebPort 5175`。Provider 固定 Mock。
- 建会话前，历史页文字是“还没有可阅读的对话。发送过的对话会保留在这里。”
- Chrome 先发送普通问题“请用一句话介绍本地知识助手。”，再从主库发送“API 单次请求超时时间是多少秒？”。回答为 `Mock response: ...`，页面标明 Mock、不外发。
- 历史最新两项依次是知识库会话 `01a0dde1-fe15-7a81-9966-e03920ce27d7` 和普通会话 `01a0dde1-fbd1-76f2-85ea-d240b2c051ba`。打开知识库项时，会话 POST 增量为 0。
- 引用面板在回收前展示 `服务超时策略.txt` 第 1–12 行，摘录含“API 单次请求超时时间为 30 秒。”，并有“打开文件详情”。点击后地址进入该文件。刷新后消息 ID 仍是 `01a0dde1-fe17-78f5-aa88-20472f1ae986`、`01a0dde1-fe18-7601-9deb-8853022ef445`。刷新前后正文一致；引用面板是否展开属于页面状态，刷新后默认收起。
- 文件 `01a0ddd1-f559-73b0-bf45-092cbda26cae` 进入回收站后，同一会话仍是这两条消息。面板写明“文件已在回收站。历史摘录不能当作当前资料仍可用。”列表来源状态为 `SOURCE_IN_TRASH`，会话状态为 `SOURCE_INVALID`。
- 重启：监听 PID `39524` 停止后，`dev.ps1` 正常退出并释放 8002/5175。同一数据根再次启动，新监听 PID `39068`。从历史再次打开同一会话，消息 ID 不变，会话 POST 仍为 0，Mock 提示仍在。验证后端口已释放。

## 未纳入本批

- 学习历史、继续学习、首页、设置、全局搜索、删除和恢复、任务抽屉、备份。
- 第四十二批网页上传全链路没有重跑。
- 文件详情页本次快照没有单独等到预览区渲染出“30 秒”；“30 秒”出现在引用摘录中。
