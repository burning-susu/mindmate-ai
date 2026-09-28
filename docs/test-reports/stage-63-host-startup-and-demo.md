# 第六十三批：修复 Windows 运行环境并启动隔离 Demo

日期：2026-09-28。分支：`feat/v1-bootstrap`。本批进场本地 HEAD 与远端分支均为 `783fb21e576e7b265f2f854a4113bbaa36efb4ef`。

## 验收状态

| 验收项 | 状态 | 本批证据 |
| --- | --- | --- |
| `ENVIRONMENT_READY` | `PASS` | Python 3.12.14；`backend/.venv` 可启动；`mindmate` 导入成功；固定 ONNX 离线 manifest 为 `READY` 且指纹一致。 |
| `DEMO_STARTUP` | `PASS` | 隔离 Mock 数据准备为 READY；同一数据根完成重启；health/ready 和页面资源检查通过。 |
| `DEMO_BROWSER` | `PARTIAL` | 本批只做 HTTP 端点及页面资源检查，没有普通 Chrome/Edge 点击、刷新、截图或浏览器恢复证据。 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 未在页面操作回收站确认流程。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 未操作 test-only Provider 页面流程；没有费用确认截图或 `calls` 摘要。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 没有真实凭据、官方请求或付费调用。 |
| `STAGE7_FULL_V1` / `STAGE8_FULL_V1` | `PARTIAL` | 完整 V1 的其他阶段证据没有改变。 |

## Python 环境

原 `backend/.venv/pyvenv.cfg` 绑定到用户级 uv Python 3.12.11 路径，旧 `.venv/Scripts/python.exe --version` 无法启动。本次受限执行器下 `py` 和全局 `python` 命令不可用；用户级解释器目录返回“拒绝访问”。提升权限进行只读版本核验的请求在执行前被自动审批服务以 `404` 拒绝，原因是当前模型不受已配置审批账户支持；该操作没有执行，因此不宣称普通未受限终端中的全局 Python 已修复。

按项目 Python 约束使用 uv 安装 Python 3.12.14 到专用忽略目录 `backend/.uv-python/`，不写全局 PATH 或注册表；缓存位于 `backend/build/uv-cache/`。执行 `uv sync --frozen --dev --python <backend/.uv-python Python>`，同步 66 个锁定包且没有改写 `backend/uv.lock`。旧 `.venv` 未删除，原目录已移到被忽略的 `backend/build/venv-stage62-broken/` 留存；迁移过程中新建的临时环境也保留于 `backend/build/venv-stage63-build-python/`。

- `backend/.venv/Scripts/python.exe --version`：`Python 3.12.14`。
- `backend/.venv/Scripts/python.exe -m pytest --version`：`pytest 8.4.2`。
- `mindmate` 导入成功；模型 `ModelManager.status(offline=True)` 为 `READY`，固定 artifact fingerprint 为 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。
- 六个阶段八关键后端测试文件：`29 passed, 37 warnings in 75.63s`。
- 前端 Vitest：`15 files / 66 tests passed`；`npm run typecheck` 通过；`npm run build` 通过。
- Vite build 提示一个 513.14 kB gzip 前 chunk 超过 500 kB 门限；本批没有修改前端代码，也没有运行 lint。

后端测试命令：

```powershell
$env:PYTHONPATH = "$(Resolve-Path '.\src');$(Resolve-Path '.\.venv\Lib\site-packages')"
& '.\.venv\Scripts\python.exe' -m pytest -p no:cacheprovider `
  --basetemp '.\build\stage63-pytest-tmp' `
  tests/test_stage8_history_purge.py `
  tests/test_stage8_history_fulltext.py `
  tests/test_stage57_learning_multistep.py `
  tests/test_stage8_history_query_trash.py `
  tests/test_stage8_conversation_history.py `
  tests/test_stage8_learning_history.py
```

## 隔离 Demo

使用新的 `%TEMP%\mindmate-ai-stage63-isolated-demo-20260928` 数据根，通过 `scripts/demo.ps1` 的 `-ApiPort 8014 -WebPort 5182 -NoBrowser` 启动。准备报告确认 Provider 为 `mock`、`deepseek_called=false`、本地模型与主索引均为 `READY`。固定资料共 9 个文件、4 个知识库；重复准备后数据计数不变。主知识库 ID 为 `01a0e5b3-defc-7aff-972e-28e980580771`，索引版本为 `01a0e5b3-ee6e-7876-ae04-cb6df0faab9e`；隔离数据库 revision 为 `d17a5e9c4b20`。

同一 `%TEMP%` 数据根完成停止和重启；重启后知识库 ID、索引版本及准备计数保持一致。最终服务仍在运行：API health 为 `ok`，`/api/v1/ready` 返回 HTTP 200，知识库页面资源返回 HTTP 200 并包含 Vite React 根节点。最终启动 stderr 未发现 `Traceback`、`ERROR` 或异常；另有 Starlette/httpx 弃用提示和 Alembic 迁移 `INFO` 日志。
当前隐藏启动进程：API Python PID `37284`，Web 监听 Node PID `43868`，启动监控 PowerShell PID `42328`。这些 PID 只对当前运行实例有效；确认端口仍分别由 `37284` 和 `43868` 监听后，可在 PowerShell 执行 `Stop-Process -Id 37284,43868 -Force` 停止本次演示。由于启动窗口隐藏，不能在该窗口按 Ctrl+C。

首次重启时，沙箱限制导致 `Get-CimInstance` 无法读取子进程命令行，遗留的本批 Vite Node 子进程占用 `5182`。根据启动前端口为空、监听 PID 和启动时间确认后，只结束了本批子进程；之后同根重启成功，没有操作其他端口或用户进程。

## 等待浏览器走查

HTTP 200 只证明服务和页面资源可达，不代表页面验收。请用普通 Chrome/Edge 打开当前知识库页面；默认 Provider 为 Mock，不会调用真实 DeepSeek：

- 页面：`http://127.0.0.1:5182/knowledge-bases/01a0e5b3-defc-7aff-972e-28e980580771`
- API：`http://127.0.0.1:8014`
- 合成数据根标识：`%TEMP%\mindmate-ai-stage63-isolated-demo-20260928`
- 问资料内问题“API 单次请求超时时间是多少秒？”，打开 `服务超时策略.txt` 来源；再问“这套资料里的磁盘配额是多少 GB？”，确认资料不足且不显示来源按钮。
- 点击“基于此知识库学习”，用默认一题提交答案，检查反馈与来源；刷新后确认同一会话恢复。
- 按步骤记录预期/实际，可先回传第一处失败和脱敏截图。本批自动检查没有代替上述点击。

主链走查完成后，再做回收站永久删除的取消/确认与共享来源保护、三题定位及 test-only DeepSeek/OpenAI fixture。fixture 仅使用合成 Key 并遵循页面费用确认；真实 Provider 不执行。
