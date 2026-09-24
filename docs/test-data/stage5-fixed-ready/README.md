# 阶段 5 固定 READY 检索样本

本目录只包含可公开的合成中文资料，用于验证本地导入、知识库成员、持久索引任务、真实 ONNX Embedding、READY 激活和检索页面。不包含个人资料。

## 固定资料

| 文件 | 预期范围 | 关键内容与定位 | 检索可见性 |
| --- | --- | --- | --- |
| `服务超时策略.txt` | `第二十五批·固定资料主库` | `30 秒`；源文件第 3 行，解析定位为第 1-12 行段落 | READY 后可检索 |
| `相似服务超时策略.txt` | `第二十五批·相似干扰库` | `47 秒`；源文件第 3 行，解析定位为本文件段落 | 仅在相似干扰库可检索，主库不可见 |
| `回收站范围验证.txt` | 主库，索引 READY 后移入回收站 | `TRASH-9274`；源文件第 3 行 | 移入回收站后不可检索 |

主库问题：`API 单次请求超时时间是多少秒？`。资料外问题：`南极冰芯中氮同位素的具体丰度百分比是多少？`。

准备脚本还保留一个无成员、无活动索引的诊断知识库，用于每轮验证 API 明确返回 `unavailable / INDEX_VERSION_NOT_AVAILABLE`；它不含资料，也不会参加索引任务。

## 准备与复跑

在 PowerShell 中从 `backend` 目录执行。数据根目录位于 `%TEMP%`，与默认 `%LOCALAPPDATA%\MindMateAI` 完全分开：

```powershell
$data = Join-Path $env:TEMP 'mindmate-ai-stage5-fixed-ready'
uv run python scripts/prepare_stage5_fixed_ready.py --data-dir $data
```

脚本会在该目录创建所有权标记；已有非空目录若没有该标记会拒绝使用。重复运行会复用固定文件、三个知识库、成员、任务和活动索引，并在第二轮检查记录数不变。脚本只通过文件导入 API、知识库 API、成员任务和各阶段索引入队/激活服务创建数据；数据库读取仅用于状态和产物核验。脚本不清理目录。

固定模型来自 Git 忽略的 `backend/model-cache/manager-validation`。脚本先用项目 `ModelManager` 按 manifest 文件大小、SHA-256 和配置离线复验，再复制到临时数据根目录的 `models` 并再次验证。已验证时不联网、不下载；源缓存只读，模型文件不会进入 Git。缺失或校验失败时脚本明确终止，不会用 Mock 向量继续。

准备期间启动的 `TestClient` 使用与本地应用相同的持久 Worker 和服务链路。脚本会验证解析、`INDEX_PREPROCESS`、`INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 检查点、激活后的 Chunk/Embedding/向量/FTS 产物，以及真实只读检索 API。验证摘要写入数据根目录的 `stage5-fixed-ready-report.json`。

准备完成后，可启动真实 FastAPI 与 Vite，再运行实际 Chromium 浏览器检查：

```powershell
$data = Join-Path $env:TEMP 'mindmate-ai-stage5-fixed-ready'
$env:MINDMATE_DATA_DIR = $data
uv run uvicorn mindmate.main:app --host 127.0.0.1 --port 8000
```

另开终端从 `frontend` 运行：

```powershell
$report = Get-Content (Join-Path $env:TEMP 'mindmate-ai-stage5-fixed-ready/stage5-fixed-ready-report.json') -Raw | ConvertFrom-Json
$env:STAGE5_READY_KB_ID = $report.knowledge_bases.primary.knowledge_base_id
$env:STAGE5_READY_INDEX_VERSION_ID = $report.knowledge_bases.primary.index_version_id
$env:STAGE5_READY_EVIDENCE_DIR = Join-Path $env:TEMP 'mindmate-ai-stage5-fixed-ready/evidence'
npm run test:e2e -- e2e/stage5-ready-retrieval.spec.ts
```

Playwright 启动 Vite（默认 `127.0.0.1:5173`），测试通过页面键盘提交问题并核对真实 `retrieval-tests` 网络响应、候选文件名/摘录/行号和资料外拒答。证据门控可能将目标候选判为 `insufficient`；这时页面仍显示真实候选并显示“资料不足”，准备脚本与浏览器测试记录实际判定，不调整现有阈值。桌面及窄屏截图保存在临时数据根目录 `evidence` 中。若需清理，仅在应用进程停止后删除这个专用 `%TEMP%\mindmate-ai-stage5-fixed-ready` 目录；脚本不会接触其他数据根目录。

本样本只证明这几份资料的本地索引与浏览器呈现，不代替 Recall@10、10 万 Chunk 性能、阈值校准或 AC-KB-* 全量验收。全程不调用 DeepSeek、真实凭据或付费 Provider。
