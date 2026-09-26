# 第三十七批：Windows 求职 Demo 现场稳定性

## 结论与边界

- 日期：2026-09-26。分支 `feat/v1-bootstrap`。进场本地与 `origin/feat/v1-bootstrap` 均为 `9f68fe213df5b58abe7b37474d3bf7e08dde3d1e`，工作区干净。
- 本批结论：`PASS`。阶段 5、阶段 6 的完整 V1 仍为 `PARTIAL`。
- 现场使用 Windows PowerShell 5.1、仓库内 Python 3.12 虚拟环境和 Node 22。资料只来自 `docs/test-data/stage5-fixed-ready/` 的公开合成文本。数据根是 `%TEMP%\mindmate-ai-stage36-job-demo`，目录已有所有权标记，本批没有删除或重置它。生成端固定为 Mock。没有真实 DeepSeek、真实 Key、付费请求或私人文件。
- Mock 正文只证明页面、SSE、保存和引用。它不证明资料事实已被真实模型答出。用户界面上的文件上传和建库没有重验。

## 首启

命令是仓库根目录的 `.\scripts\demo.ps1`。

第一次按文档启动失败，退出码 1。准备脚本报 Alembic 找不到 `migrations`。原因是 `alembic.ini` 里的迁移目录相对当前工作目录，而演示命令的工作目录是仓库根，不是 `backend/`。配置已改为相对 `alembic.ini` 自身定位 `migrations` 和 `src`。回归是 `test_app_startup_migrates_outside_backend_working_directory`。

修复后的同一次命令完成准备并拉起服务：

- 准备结果 `PASS`，`second_pass=passed`，`counts_unchanged=true`。
- 计数：文件 9、知识库 4、任务 30。`FILE_IMPORT` 为 9。
- 主库 `01a0db00-7981-759a-9dc0-3f456f04ee5f`，活动索引 `01a0db00-8672-720e-a7ba-bed4fbfe4275`，两者都是 `READY`。
- 模型指纹 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，运行中复核为 `READY`。
- API `http://127.0.0.1:8001`，页面 `http://127.0.0.1:5174/knowledge-bases/<主库>`。
- 日志没有模型下载。固定缓存事先离线校验已是 `READY`。

## 浏览器正负例

服务器保持独占运行。在 `frontend/` 执行：

```powershell
$env:MINDMATE_WEB_PORT='5174'
$env:STAGE6_REAL_KB_ID='<准备报告中的主库>'
$env:STAGE6_REAL_INDEX_VERSION_ID='<准备报告中的活动索引>'
$env:STAGE6_REAL_EVIDENCE_DIR=Join-Path $env:TEMP 'mindmate-ai-stage36-job-demo\evidence'
npx playwright test e2e/stage6-real-onnx-knowledge-chat.spec.ts --reporter=line
```

退出码 0，`1 passed`（10.7 秒）。Playwright 使用本机已安装的 Chromium；本次没有与全量后端测试或其他浏览器任务并行。

| 场景 | 本次结果 |
| --- | --- |
| 正例 | Operation `COMPLETED`，错误码为空。助手区域可见正文与 Operation、刷新后的持久消息一致。点击引用后看到 `服务超时策略.txt`、`30 秒` 和第 1–12 行，来源 `AVAILABLE`。 |
| 再问一轮 | 仍为 `COMPLETED`，知识库模式仍在，引用按钮变为 2 个。 |
| 负例 | Operation `COMPLETED`，`EVIDENCE_INSUFFICIENT`。最后一条助手正文包含“资料不足”，该条没有“打开引用”。Citation 数为 0。 |

截图和 Operation 摘要留在临时证据目录，不进入 Git。上表不包含 Provider 调用次数。

## 受控 Mock 计数

浏览器结束后先停止演示进程，再从 `backend/` 单独运行：

```powershell
.\.venv\Scripts\python.exe scripts\verify_stage6_real_onnx_chat.py --data-dir "$env:TEMP\mindmate-ai-stage36-job-demo"
```

退出码 0。模型 `READY`，指纹与首启相同。正例检索 `supported / SUPPORTING_CANDIDATE_FOUND`，FTS rank 1、vector rank 1，Mock 调用计为 1，Citation 1。负例检索 `insufficient / NUMERIC_ANSWER_VALUE_NOT_FOUND`，Operation `EVIDENCE_INSUFFICIENT`，Citation 0，Mock 调用增量 0。计数来自注入的 `MockChatProvider.calls`，不是从页面外观推断的。

## 停止、二次启动与刷新

停止方式是结束本次 `demo.ps1` 启动的后端进程。`scripts/dev.ps1` 的清理随后释放 8001 和 5174。等待循环把后端退出看成异常，脚本退出码 1；8000 和 5173 在停止前后都是空闲，已打开的系统浏览器进程没有被结束。

再次运行 `.\scripts\demo.ps1`：

- `counts_unchanged=true`，文件仍是 9，知识库仍是 4。
- 同一主库和同一活动索引仍为 `READY`。
- 任务数从 30 变为 35。增加的是问答产生的 `AI_GENERATION`（6 变为 11）。`FILE_IMPORT` 仍是 9，四个索引阶段任务数仍各是 3。
- 没有自动下载，也没有更换 Provider。

二次启动后用 Chromium 重新打开首轮会话 `01a0dcd0-0cbe-7c32-bbf4-60403f7c9b3d` 并刷新。刷新前后可见正文一致，并与持久助手消息一致。页面上仍有 2 个“打开引用 1”按钮，对应两轮正例。数据库中该会话三条 Operation 都是 `COMPLETED`：前两条 Citation 各为 1，第三条错误码 `EVIDENCE_INSUFFICIENT`、Citation 0。

## 隔离并发对照

没有占用演示数据根，也没有在浏览器用例期间持有模型锁。

从 `backend/` 运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_stage36_query_encoder_lock.py -q --disable-warnings
```

退出码 0，`4 passed`。其中空目录用例在锁释放后得到 `MISSING_OFFLINE`，阶段是 `status_precheck`，不是 `MODEL_UNAVAILABLE`。

另外只读使用固定缓存 `backend/model-cache/manager-validation`：

- 锁被持有时，非阻塞 `status(offline=True)` 立即返回 `INSTALLING`，没有错误码。
- 另一线程的阻塞 `status` 在释放前不返回；释放后状态是 `READY`，错误码为空，等待约 0.4 秒。
- 查询编码在同一把锁被持有时不返回；释放后返回 512 维向量，没有抛出 `MODEL_UNAVAILABLE`。持锁约 0.4 秒，总耗时约 1.16 秒。

本批浏览器 Operation、受控审计和这次对照都没有新的 `MODEL_UNAVAILABLE`。第三十五批与全量测试并行的那次失败，以及 Operation `01a0db04-bcbd-7687-ad8a-ab3e14be77bf` / request `01a0db04-bcaa-717f-bf8a-508f181ae279`，本批没有按原请求重放。它们仍是历史记录，不能用这次锁对照改写成已经逐条证实。

## 本批门禁与未跑项

- 定向 `python -m pytest tests/test_local_runtime.py -q --disable-warnings`：退出码 0，`8 passed`。
- `ruff check tests/test_local_runtime.py`：通过。
- `pyright tests/test_local_runtime.py`：0 errors。
- 没有修改前端，因此没有重跑前端 lint、typecheck、Vitest 或 build。
- 没有重跑后端全量。第三十六批 `225 passed, 2 skipped` 是历史基线，不是本批新成绩。
- 没有 API 或数据库结构变化，没有重新生成 OpenAPI。
- 未跑：真实 DeepSeek、发布性能、10 万 Chunk、最终答案质量、用户界面上传建库、完整阶段 5/6 门禁。

## 下一批唯一目标

在获得明确授权和单次预算上限之后，用同一套公开合成资料做一次手动真实 DeepSeek 小型冒烟。未授权前，默认 `.\scripts\demo.ps1` 继续使用 Mock，不要把本批证据转写成真实模型验收。
