# 第四十四批：学习历史列表与原会话恢复

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 进场 SHA：本地与 `origin/feat/v1-bootstrap` 均为 `e6f1b4cedef8527b10c77a836348b4424b78f0e7`，工作区干净。
- 本批学习历史切片：`PASS`
- 阶段 8：`PARTIAL`
- 求职 Demo：维持第四十二批 `PASS`。本批没有重跑空库上传、建库和全链路问答。
- 真实 DeepSeek：`PENDING`。学习出题标识为 `learning-demo-fixture-v1`，`live_model_called=false`。没有 Key，没有外发。

## 交付

- 学习页、`/learning/new` 和学习会话页进入 `/history?tab=learning`。`/history` 默认仍是对话历史，侧栏文案改为“历史记录”。
- 列表读取 `GET /api/v1/history/learning-sessions`。字段是会话 ID、已保存主题、目标类型、知识库名、范围内文件数、会话状态、来源状态、已作答数量、目标题量、创建时间和最近活动时间。
- 列表不读取题目正文、选项、答案键、反馈、证据摘录或密钥。未作答的 `answered_count` 为 0，不标成完成。没有掌握度、下次复习时间或多题总分。
- 默认每页 30 条，最大 100 条。游标按 `updated_at` 降序和会话 ID 降序。已软删除的会话不列出。
- 点击后进入原 `/learning/session/:id`。未作答展示原题和“提交答案”；已作答展示服务端原选择、对错、解释和可点来源。打开历史不新建会话，也不自动提交。
- 来源进入回收站时，列表标为 `SOURCE_INVALID / SOURCE_IN_TRASH`。已提交反馈仍可读，引用写明失效原因且不能打开文件。未提交会话显示“不能继续作答”，提交被 `SOURCE_INVALID` 拒绝。
- Alembic `c8d4f1a27b63` 只为未回收学习会话增加 `(updated_at, learning_session_id)` 部分索引。没有新学习表。

## 自动化

- `uv run pytest tests/test_stage8_learning_history.py tests/test_stage8_conversation_history.py`：`6 passed`。覆盖学习历史排序、分页、排除回收会话、列表不含答案和反馈、重启后题目与 Attempt 不变、来源回收后的已提交可读和未提交拒绝；对话历史 3 项仍通过。
- `npx vitest run src/test/stage8-history.test.tsx`：`7 passed`。覆盖学习页进入空列表且不创建会话、打开未作答不自动提交、打开已作答并查看来源、学习历史失败可重试，以及原有对话历史 3 项。
- `uv run ruff check` 覆盖本批后端文件，通过。`uv run pyright` 覆盖历史模块、`main.py` 和本批测试，`0 errors`。
- `npm run typecheck`、`npm run lint`、`npm run build` 通过。OpenAPI 3.1 为 `77 schemas / 79 operations`，前端生成类型已同步。Alembic head `c8d4f1a27b63`。
- 没有重跑后端全量 pytest。切块 Worker 领取时序问题本批没有碰到，也不算已修复。

## 浏览器与重启

- 数据根：`%TEMP%\mindmate-ai-stage44-learning-history`。准备脚本使用 `docs/test-data/stage5-fixed-ready/` 和已校验 ONNX，没有下载模型。主库 `01a0ddfd-32bb-7a0b-b0a9-3dfd8a990bfa`，活动索引 `01a0ddfd-4250-76f0-84d2-9866d650b6f7`，状态 `READY`。
- 服务：`.\scripts\dev.ps1 -DataDir ... -ApiPort 8003 -WebPort 5176`。Provider 固定 Mock。
- 建会话前，学习历史文字是“还没有可找回的学习会话。从知识库开始的一题会保留在这里。”
- 浏览器先创建未作答会话 `01a0ddff-f0b7-75c2-ad63-96beababab14`，再创建并提交 `01a0de00-99c8-7027-bbcb-e67c916eca75`。所选“30 秒”，结果正确，引用 `[1] 服务超时策略.txt`。页面标明本地 Mock 演示，不是在线模型生成。
- 历史按最近活动排序。打开已作答项后引用可点，刷新后 Attempt 仍是 `01a0de00-f21d-760c-8751-924da6ab0a2b`，没有“提交答案”。打开未作答项后原题仍在，从该页提交一次，Attempt 为 `01a0de0f-2560-7441-885e-c3c3f8d77bc6`，题目 ID 仍是 `01a0ddff-f3ad-7791-9db2-3814a1bc1de5`，提交后按钮消失。
- 另建未作答会话 `01a0de10-4b07-7575-84a9-3602defff507`，题目 `01a0de10-4b57-73b3-9594-4dae4c0f4862`，Attempt 为 0。
- 重启：监听 PID `28668` 停止后，脚本退出码 0，8003/5176 已释放。同一数据根再次启动，新监听 PID `29352`。三个会话的题目 ID、已作答数量和 Attempt ID 不变。
- 文件 `01a0ddfd-34ad-7470-8fa6-51c94818051c` 进入回收站后，三条学习历史都是“资料范围已失效 · 文件已在回收站”。未作答会话写明“学习范围的资料已失效，不能继续作答”，没有提交按钮，Attempt 仍为 0。已作答会话仍显示“结果：正确”和原 Attempt；引用面板写明“文件已在回收站。历史摘录不能当作当前资料仍可用。”没有“打开文件详情”。
- 对话历史页签仍显示“还没有可阅读的对话。发送过的对话会保留在这里。”
- 验证后再次停止，脚本退出码 0，8003/5176 已释放。

## 未纳入本批

- 首页、历史搜索和筛选、批量删除、任务抽屉、设置、备份和恢复。
- 第四十二批网页上传全链路没有重跑。
- 学习出题仍是本地规则 `learning-demo-fixture-v1`，不是在线模型生成。
