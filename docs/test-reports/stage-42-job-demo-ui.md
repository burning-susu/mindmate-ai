# 第四十二批：求职 Demo 全链路验收

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 进场 SHA：本地与 `origin/feat/v1-bootstrap` 均为 `72dabbe21aea12334d60599af3b5a85f07e344e1`，工作区干净。
- 求职 Demo：可以从网页完整演示，`PASS`。
- 完整 V1：阶段 5、6、7 仍为 `PARTIAL`。
- 真实 DeepSeek：`PENDING`。本批没有 Key，没有外发。

## 现场

- 数据根：`%TEMP%\mindmate-ai-stage42-ui-demo`。启动前没有 `database/mindmate.db`，只有从 `backend/model-cache/manager-validation` 复制并复验的 ONNX。复制结果 `state=READY`，指纹 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，`download_performed=false`。
- 启动命令：`.\scripts\dev.ps1 -DataDir "$env:TEMP\mindmate-ai-stage42-ui-demo" -ApiPort 8001 -WebPort 5174`。没有运行 `.\scripts\demo.ps1`，因此没有 API 预导入。
- 浏览器：本机 Chrome，经页面操作。截图在隔离根 `evidence/`，不入库。
- 资料：`docs/test-data/stage5-fixed-ready/服务超时策略.txt`。文件 `01a0dd96-7d52-7511-baa6-c7f1d3764778`，`PARSED`，创建于 `2026-09-26 12:00:22`。
- 知识库：`01a0dd98-92e3-71b8-8e49-cc259b4fc539`，名称“第四十二批服务超时演示库”，状态 `READY`。活动索引 `01a0dd98-9614-7a39-8c99-cbb1f59cfadb`。
- 任务：`FILE_IMPORT` 完成 1 条；`KNOWLEDGE_MEMBERSHIP_ADD`、`INDEX_PREPROCESS`、`INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 均为 `COMPLETED`。嵌入检查点记录真实模型 revision，向量数 1。预处理在点击重建后入队，嵌入于 `12:02:41` 完成，当时页面已经离开知识库。

走查脚本在文件列表还显示 0 时又提交了一次同一文件。服务把它记为 `FILE_IMPORT / BLOCKED / WAITING_DUPLICATE_DECISION`，没有第二条文件。正式操作应等第一行出现后再离开，不会产生这条待决定任务。

## 逐步结果

| 步骤 | 本批看到的结果 |
| --- | --- |
| 空库 | 文件页“全部文件 0”。 |
| 上传并离开 | 回到文件页后，`服务超时策略.txt` 为 TXT、已解析、1.1 KB。 |
| 建库并加入 | 成员“待建立索引”，索引活动版本暂无，模型区显示本地 Embedding 可用。 |
| 重建后离开 | 再打开详情时标题为“索引就绪”。索引状态接口 `status=READY`，四段索引任务完成，失败文件 0。 |
| 知识库提问 | 顶栏“Mock 生成，不会外发，也不会产生 DeepSeek 费用。”范围是该库。正文为 `Mock response: API 单次请求超时时间是多少秒？`，来源 `[1] 服务超时策略.txt`。 |
| 打开引用 | 文件详情解析文本含“API 单次请求超时时间为 30 秒。”引用行 `1–12`，`source_status=AVAILABLE`。 |
| 无证据 | “这套资料里的磁盘配额是多少 GB？”正文为“当前选择的资料不足以可靠回答这个问题。”来源按钮 0。 |
| 一题 | 会话 `01a0dda0-d500-7b56-a671-d69f141de1ad`。题目询问“单次请求超时时间”多少秒。选择“30 秒”，结果正确，来源同一文件。页眉 `learning-demo-fixture-v1`，`live_model_called=false`。 |
| 刷新 | 同一 URL 刷新后，题目、四个选项、所选“30 秒”、正确和引用仍在。 |

服务端模式：

- 正例 Operation `01a0dda0-c8f6-78a7-b51d-77dabdc3eba0`：`provider=MOCK`，`resolved_model=mock-chat-v1`，`COMPLETED`。
- 负例 Operation `01a0dda0-d200-7f75-a9eb-616cb528cf7f`：`provider=LOCAL_EVIDENCE_GATE`，`resolved_model` 为空，`error_code=EVIDENCE_INSUFFICIENT`。
- 学习会话：`provider=mock`，`live_model_called=0`，Attempt 1 条。
- 模型状态端点在走查结束时为 `READY`。同一次索引状态里的 `embedding_model_state` 曾为 `INSTALLING`，与既有“持锁时非阻塞状态显示安装中”一致，索引本身已是 `READY`。

## 验收矩阵

| 项 | 状态 | 证据 |
| --- | --- | --- |
| UI 上传 | `PASS` | 本批。空目录计数为 0 后，浏览器上传，文件 `01a0dd96-7d52-7511-baa6-c7f1d3764778` 为 `PARSED`。 |
| 知识库 READY | `PASS` | 本批。网页加入成员并重建；活动索引 `01a0dd98-9614-7a39-8c99-cbb1f59cfadb`；四段任务 `COMPLETED`。 |
| 聊天引用 | `PASS` | 本批。Mock 正例引用 `服务超时策略.txt` 行 1–12，文件详情可见“30 秒”。 |
| 无证据处理 | `PASS` | 本批。磁盘配额问题 `EVIDENCE_INSUFFICIENT`，引用 0，未调用 Mock 生成正文。 |
| 一题陪练 | `PASS` | 本批。会话 `01a0dda0-d500-7b56-a671-d69f141de1ad`，`learning-demo-fixture-v1`，`live_model_called=false`。 |
| 刷新 | `PASS` | 本批。同一学习 URL 刷新后作答和引用仍在。 |
| 后端进程重启 | 历史 `PASS`，本批未复测 | 第四十一批会话 `01a0dd85-4fe7-7d9c-b95b-e84b34e8a5ee`，见 `docs/test-reports/stage-41-learning-restart.md`。 |

## 未修并不阻断的显示

文件详情“所在知识库”使用 `index_state`，而 `GET /api/v1/files/{id}/knowledge-bases` 返回的是知识库 `status`。本批页面因此显示“第四十二批服务超时演示库（undefined）”。原文、解析状态和引用摘录不受影响。

## 可选精进

下一批不自动开工。若以后再做，一次只做一项：

1. 文件详情改读知识库 `status`，去掉 `undefined`。
2. 让 `.\scripts\demo.ps1` 能选择空库启动，避免和网页上传路径混用。
3. 真实 DeepSeek 仍须单独授权、同意、凭据和费用确认后再做一次冒烟。
4. 切块 Worker 领取时序仍是第三十九批留下的风险；本批单文件索引没有碰到它。
5. 多题、提示、掌握度、复习和完整阶段 5/6/7 验收仍不属于这条 Demo。

## 门禁

本批没有修改产品代码，没有新增测试，没有重跑后端或前端全量。停止演示进程后脚本退出码 0，`8001` 与 `5174` 不再监听。`git diff --check` 在提交前执行。
