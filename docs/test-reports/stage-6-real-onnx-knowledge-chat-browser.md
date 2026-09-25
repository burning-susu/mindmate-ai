# 第三十五批：真实 ONNX 知识库问答浏览器验收

## 结论与边界

- 日期：2026-09-26。起点 `feat/v1-bootstrap`、`c5de7898a6fc4c03ad62a6fe4d0aacfbbbbc1f18`，本地与 `origin/feat/v1-bootstrap` 一致，进场工作区干净。
- 本批 Demo 主流程 `PASS`：固定真实本地 ONNX、真实 READY 索引、真实 FastAPI + Vite/Chromium、Mock Chat Provider。阶段 5、阶段 6 的完整 V1 仍为 `PARTIAL`。
- **未验证真实 DeepSeek 联通或最终答案事实正确性**。浏览器回答正文为 `Mock response: ...`，仅引用摘录包含资料中的 `30 秒`；不能将此 Mock 生成说成真实模型作答。没有真实 Key、付费调用、私人资料或外部 Provider 外发。
- Demo 数据以 `%TEMP%\mindmate-ai-stage35-knowledge-chat-demo` 为专用可复用目录；仅使用 `docs/test-data/stage5-fixed-ready/` 的公开合成 TXT。该目录与默认 `%LOCALAPPDATA%\MindMateAI` 用户数据隔离，运行时数据库、向量、模型和截图均未进入 Git。

## 模型与 READY 证据

- 第三十四批遗留隔离数据根是 `%TEMP%\mindmate-demo-batch34-3`，其模型目录是 `models/`；本批只读调用 ModelManager 确认该目录仍为 `MISSING_OFFLINE`。Git 忽略的独立缓存 `backend/model-cache/manager-validation` 则为 `READY`。现有准备脚本先校验源缓存，再复制到本批专用数据根并再次校验为 `READY`；未重新下载，也未复制未知模型。
- 固定基础 revision `7999e1d3359715c523056ef9478215996d62a620`，ONNX revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`，manifest 指纹 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，总大小 `95,291,718` 字节。ModelManager 按 manifest 对 ONNX/tokenizer/config 的大小、SHA-256 和配置逐项校验。运行中 `GET /api/v1/embedding-model` 也返回 `READY` 和相同指纹。
- `stage5-fixed-ready-report.json` 记录主库 ID `01a0d95b-adb6-7842-9b96-741e920a4aae`，活动 IndexVersion `01a0d95b-bba5-791c-a176-426d08e57765`，知识库与版本均为 `READY`；`INDEX_PREPROCESS`、`INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 均 `COMPLETED`。主库 2 个输入、2 个 Chunk、2 条 Embedding、2 条 sqlite-vec 向量、2 条 FTS 映射；FTS 完整性、范围一致性、向量维度/有限值/单位范数检查均通过。Alembic 为 `c3d4e5f6a7b8 (head)`。
- 准备脚本通过文件导入 API、知识库 API 和持久 Worker 链构建数据，第二轮复用检查为 `9 files / 4 knowledge bases / 24 tasks` 且记录数不变。**本批没有从用户 UI 执行文件上传与建库**；浏览器验证从已准备好的 READY 知识库详情开始，不能把脚本准备等同于完整 UI 导入验收。

## 浏览器主流程

在同一数据根启动真实 FastAPI 和 Vite，Playwright Chromium 从知识库详情点击“基于此知识库提问”。页面显示“知识库模式”和固定主库范围，未切换到普通聊天。

| 场景 | 浏览器/API 实测 |
| --- | --- |
| 正例：`API 单次请求超时时间是多少秒？` | Operation `COMPLETED`、SSE 含 `COMPLETED` 终态，回答出现可点击 `[1]`；Citation 绑定 AnswerVersion `01a0d969-86e0-7daf-8e8a-c234a0603c48`、真实文件 `服务超时策略.txt`、Chunk `01a0d95b-bc5d-773c-ab7c-5b25701de1ea` 和活动 IndexVersion。来源 `AVAILABLE`，摘录含 `30 秒`，定位第 1–12 行，“打开文件详情”链接指向同一 file ID。 |
| 刷新与重开 | 浏览器刷新、重开同一会话后仍显示引用；持久消息的正文和 Citation ID 与原 Operation 一致。再问一轮仍为知识库模式，Citation 仍绑定同一活动版本与来源。 |
| 负例：`南极冰芯中氮同位素的具体丰度百分比是多少？` | Operation `COMPLETED` + `EVIDENCE_INSUFFICIENT`，页面显示固定资料不足拒答，AnswerVersion/消息 Citation 均为 0；没有将其表示为 `unavailable`。 |

`%TEMP%\mindmate-ai-stage35-knowledge-chat-demo\evidence\browser-operations.json` 保存 Operation、AnswerVersion 与 Citation 证据；`positive-citation.png`、`negative-insufficient.png` 保存无本机路径的关键页面截图。页面临时端口仅供本次测试，不是永久演示地址。

受控独立审计在同一数据根用真实 `LocalRetrievalQueryEncoder`、FTS/sqlite-vec 和 `MockChatProvider.calls` 计数：正例 `supported / SUPPORTING_CANDIDATE_FOUND`，目标 Chunk 同时为 FTS rank 1、vector rank 1，Mock 调用从 0 到 1；负例虽有 vector rank 1 候选，门控因 `NUMERIC_ANSWER_VALUE_NOT_FOUND` 判 `insufficient`，Mock 调用仍为 1，因此负例增量 **0**，Citation 0。此计数来自受控 TestClient 观测，与上表浏览器会话是分开的执行；证据见同目录 `controlled-provider-audit.json`。本地 HTTP fixture 本批未用于浏览器生成，既有 fixture 只证明 Adapter 契约。

## 失败尝试与最小修复

- 首次准备专用数据根时，准备脚本读取 `INDEX_EMBED` 尚未存在后，运行时自动激活 Worker 抢先用相同幂等键创建任务，脚本 `INSERT` 命中 `UNIQUE constraint failed: background_tasks.idempotency_key`。原脚本复跑后 READY，但首次运行不稳定。现对该唯一键竞态回滚当前事务、核对任务类型及版本、复用运行时已创建的任务；不修改索引门槛或产品契约。定向回归 `test_stage5_prepare_race.py` 通过，全新 `%TEMP%\mindmate-ai-stage35-index-race-regression` 目录首次准备直接 `PASS`。
- 一次浏览器补强复核与完整后端测试并行时，问答 Operation 返回 `MODEL_UNAVAILABLE`，页面未显示引用；当时模型状态 API 仍为 `READY`。并行测试结束后在同一数据根独占复跑浏览器 `1 passed`。目前只有一次并发失败，**未证实根因**；不能据此宣称模型服务在所有并发负载下稳定。
- 沙箱内 Chromium 启动曾遇 `spawn EPERM`；获得本地浏览器执行权限后运行成功。受控审计脚本初次运行因服务仍独占该数据根、随后因缺少 API 幂等请求头失败；停止本轮服务并补齐请求头后通过。这些失败不计为验收 PASS。

## 执行命令与门禁

从 `backend/` 运行：

```powershell
.\.venv\Scripts\python.exe scripts\prepare_stage5_fixed_ready.py --data-dir "$env:TEMP\mindmate-ai-stage35-knowledge-chat-demo"
.\.venv\Scripts\python.exe scripts\verify_stage6_real_onnx_chat.py --data-dir "$env:TEMP\mindmate-ai-stage35-knowledge-chat-demo"
.\.venv\Scripts\python.exe -m pytest tests/test_stage5_prepare_race.py tests/test_stage6_knowledge_chat.py -q
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\pyright.exe
$env:MINDMATE_DATA_DIR=Join-Path $env:TEMP 'mindmate-ai-stage35-knowledge-chat-demo'; .\.venv\Scripts\alembic.exe current
```

后端定向 `4 passed`，全量 pytest 退出码 0，Ruff 全通过，Pyright `0 errors`，Alembic `head`。从 `frontend/` 运行 `npm run test` 为 `27 passed`，`npm run lint`、`npm run typecheck`、`npm run build` 均通过。带 `STAGE6_REAL_KB_ID`、`STAGE6_REAL_INDEX_VERSION_ID`、`STAGE6_REAL_EVIDENCE_DIR` 运行 `npm run test:e2e -- e2e/stage6-real-onnx-knowledge-chat.spec.ts --reporter=line`，独占复核 `1 passed`。`git diff --check` 通过。没有 API 契约变化，故未重新生成 OpenAPI 类型。

## 下一批唯一建议

对求职 Demo 最有价值的是把已验证的固定 READY 数据准备、启动和浏览器演示封装成一条可重复的本地演示入口，并对并发负载下出现的 `MODEL_UNAVAILABLE` 做可复现诊断；保持真实 DeepSeek 与私人资料排除在默认演示外。
