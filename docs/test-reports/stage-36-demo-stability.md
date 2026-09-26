# 第三十六批：求职 Demo 稳定启动与 `MODEL_UNAVAILABLE` 诊断

## 结论与边界

- 日期：2026-09-26。起点 `feat/v1-bootstrap`、`af8e9c7e7ad39e8ede68adcf45f01c6768fd17b5`。
- 本批把固定资料演示收成一条 Windows 命令，补上助手正文的浏览器断言，并修掉“模型锁被占用就被当成模型不可用”的确定路径。阶段 5、阶段 6 的完整 V1 仍为 `PARTIAL`。
- Embedding 仍是真实本地 ONNX 的设计；生成端仍是 Mock。没有真实 DeepSeek 请求、真实 Key、私人资料或付费调用。Mock 正文只证明页面、SSE、保存和引用，不证明资料事实已被模型答出。
- 用户界面上的文件上传和建库本批没有重验。脚本准备不能代替那条路径。
- 本环境是 Linux，仓库里没有 `backend/model-cache/manager-validation`。因此没有重跑 Windows `.\scripts\demo.ps1`，也没有重跑真实 ONNX 浏览器 E2E。下面把已执行的门禁和未执行的现场步骤分开写。

## 演示入口

在仓库根目录的 Windows PowerShell 中：

```powershell
.\scripts\demo.ps1
```

- 数据根默认是 `%TEMP%\mindmate-ai-stage36-job-demo`。系统可能清理 `%TEMP%`。准备脚本只接受空目录或带 `.mindmate-stage5-fixed-ready-owner` 标记的目录，不会清空 `%LOCALAPPDATA%\MindMateAI`。
- 准备步骤复用 `backend/scripts/prepare_stage5_fixed_ready.py`。模型只从已有固定缓存复制并再次校验 manifest；缓存不是 `READY` 时脚本停止，不下载、不换模型。
- 启动复用 `scripts/dev.ps1`。Demo 使用回环 `127.0.0.1:8001` 和 `127.0.0.1:5174`，普通开发默认仍是 `8000` / `5173`。端口已被占用时退出，不再悄悄改端口。
- 打开主库页面前，脚本查询运行中的 `/api/v1/embedding-model` 指纹和主库 index-status `READY`。Provider 环境固定为 `mock`。
- Ctrl+C 或异常退出时，`finally` 只结束本次启动的后端、前端及其进程树，并按命令行核对端口上的 `mindmate.main:app` 或 `--port` 监听。两份 PowerShell 文件带 UTF-8 BOM，供 Windows PowerShell 5.1 读取中文。
- 这条启动、停止、再次启动的现场循环还没有在 Windows 上重新跑完。暂停前的第一次准备、第一次浏览器 `1 passed` 和第二次独占失败仍以续接记录为准，不在本报告里改写成新的通过。

## 正例正文

`frontend/e2e/stage6-real-onnx-knowledge-chat.spec.ts` 现在检查助手消息区域 `[aria-label="AI 回答"]` 的可见文字。比较前按空行分段，并把每段空白收成单空格，再和 Operation 的助手正文、刷新后的持久消息逐字比较。刷新和重开同一会话后再次比较。来源面板里的 `30 秒` 不是这条断言的对象。

负例要求最后一条助手正文等于持久拒答，正文里包含“资料不足”，并且这条回答内部没有“打开引用”按钮。Citation 数量仍以 Operation 的 0 为准。Provider 调用增量为 0 的证据仍是第三十五批分开执行的受控 Mock 计数，不从 UI 推断。

SSE 只断言 HTTP 200。Operation 终态改为轮询，不再在导航后读取 SSE 响应体。

这个 spec 已随前端 lint 通过。没有固定 READY 知识库，所以本环境没有执行它。

## 模型不可用

`ModelManager.status()` 在拿不到模型锁时返回 `INSTALLING`，没有错误码。这个状态只表示锁正被占用，不表示磁盘上的模型缺失。查询编码器把非 `READY` 且没有错误码的预检映射成 `MODEL_UNAVAILABLE`。

状态接口和知识库页都会调用 `status()`。校验会在持锁期间核对 manifest，包括约 95MB 的 ONNX 文件。第一次提问时适配器还没缓存，编码器如果这时用非阻塞预检，就会在模型实际仍为 `READY` 时失败。状态接口随后仍可能自己拿到锁并返回 `READY`。这和“页面显示本地 Embedding 模型当前不可用，而模型文件及另一次独立推理正常”一致。

定向测试：

- 锁被持有时，非阻塞 `status()` 仍立刻返回 `INSTALLING`。
- `status(block=True)` 在锁释放前不返回，释放后得到真实的 `MISSING_OFFLINE`。
- 编码器在锁释放前不结束；释放后错误码是 `MODEL_MISSING_OFFLINE`，阶段是 `status_precheck`，不是 `MODEL_UNAVAILABLE`。
- 非阻塞结果会是 `INSTALLING`、阻塞结果是 `READY` 时，编码器会加载适配器并返回向量。

修复只让查询编码等待这把已有的锁，然后读取真实状态。没有增加超时重试，没有把 `unavailable` 改成 `insufficient`，也没有吞掉异常。状态接口仍使用非阻塞查询，避免页面被安装或校验堵住。

失败日志写到 `uvicorn.error`。Alembic 的 `fileConfig` 会关掉启动前已经创建的 logger，所以写入前如果该 logger 被关掉会重新打开。日志字段只有 Operation ID、request ID、索引版本、固定模型指纹、异常类型、`encoder_phase`、`model_state` 和安全错误码。定向测试确认问题正文、异常里的路径和 `secret` 不会出现。意外异常仍映射为 `MODEL_UNAVAILABLE`，阶段记为 `embed_query`。

尚未证实的部分：

- 第三十五批与全量后端测试并行时的那一次 `MODEL_UNAVAILABLE` 仍是历史证据。全量 pytest 使用各自的临时数据目录，不会写演示数据根；它不能代替那次现场。
- 暂停前第二次独占浏览器失败仍单独保留：Operation `01a0db04-bcbd-7687-ad8a-ab3e14be77bf`，request `01a0db04-bcaa-717f-bf8a-508f181ae279`，`FAILED / MODEL_UNAVAILABLE`。当时没有新的阶段日志。本批没有重放这个 Operation，所以不能说现场根因已经用同一次请求证实。上面的锁路径是能产生同一用户可见错误、且已有回归的确定缺陷。

## 本环境门禁

从 `backend/`：

```powershell
uv run python -m pytest -q --disable-warnings
uv run ruff check src tests scripts
uv run pyright
```

- pytest 退出码 0。227 项收集，225 通过，2 跳过：固定模型缓存不存在，以及 Windows Credential Manager。
- Ruff 通过。
- 本批改动文件的 Pyright 为 0 错误。Linux 全量 Pyright 对未修改的 `resource_limits.py` 报告 `ctypes.WinDLL` 不可用；这是 Windows API，本环境不能把它当成新的回归。
- 从 `frontend/`：`npm run test` 为 27 通过；`npm run lint`、`npm run typecheck`、`npm run build` 通过。
- `git diff --check` 通过。
- 没有 API 或数据库结构变化，没有重新生成 OpenAPI，没有迁移。

## 下一批唯一建议

在你当场确认后，对同一套固定合成资料做一次手动真实 DeepSeek 小范围验收。默认演示命令继续使用 Mock，不要把真实 Key 放进自动化或本批这种无人值守运行里。
