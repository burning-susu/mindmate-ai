# 第五十八批：逐题练习稳定验收与第 56/57 批交付收口

日期：2026-09-27。分支 `feat/v1-bootstrap`。进场工作区干净；本地、远端跟踪分支和 `git ls-remote` SHA 均为 `057e0bbc2065480b7e5d17b6bc09411e0d9c32d1`。

## 验收结论

| 项目 | 状态 | 证据口径 |
| --- | --- | --- |
| 第 56/57 批本地提交与推送 | `PASS` | 代码已由提交 `057e0bbc2065480b7e5d17b6bc09411e0d9c32d1` 收口；本批进场时本地与远端完整 SHA 一致，工作区干净，不重复提交旧改动 |
| 全新隔离库迁移 | `PASS` | `backend/build/mindmate-stage58-fixture` 从空库升级至 Alembic `d17a5e9c4b20`；仅含合成资料 |
| 当前执行环境的应用启动诊断 | `PARTIAL` | FastAPI lifespan 的 TestClient 启停成功；现有 Stage 56 测试服务的 health 为 `ok`。仓库启动脚本指定的虚拟环境 Python 无法在当前沙箱创建进程，真实浏览器页面未能打开 |
| `LEARNING_MULTIQUESTION_API` | `PASS` | 第 55/56/57 批与阶段 7 核心后端回归，本次 `22 passed` |
| `BACKEND_FIXTURE` | `PASS` | 测试专用假传输的边界、Provider 题目/点评和调用计数测试通过；现有夹具计数读取为 0，没有真实外呼 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 本批没有实际页面点击、刷新恢复、截图或页面侧假 Provider 计数证据 |
| `DEMO_REGRESSION_THIS_BATCH` | `PARTIAL` | 未在浏览器重跑导入、建库、索引 READY、带来源问答/拒答及一题/三题 Mock 流程；不沿用历史 PASS 冒充本批通过 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 未使用真实 Key、未访问 DeepSeek/OpenAI、无费用请求 |
| `STAGE7_FULL_V1` / `STAGE8_FULL_V1` | `PARTIAL` | 完整阶段需求没有改变，也没有宣称验收完成 |

Demo 可用性与完整 V1 阶段状态分开记录。当前只证明逐题业务自动化回归和测试传输夹具通过，不代表真实页面或完整 Demo 通过。

## 第 56/57 批 Git 收口

- 第 56/57 批代码和报告已在进场前提交并推送。提交信息为 `实现：接续在线学习测试夹具并完成 1–5 题逐题练习`，完整 SHA 为 `057e0bbc2065480b7e5d17b6bc09411e0d9c32d1`。
- 本地 `HEAD`、`origin/feat/v1-bootstrap` 和远端 `git ls-remote` 返回同一完整 SHA。本批没有重写第 56/57 批文件或尝试重复提交、强推。
- 第 56/57 批原始报告保持不变；本报告仅新增本次收口证据。

## 本批文档 Git 交接

- 一次普通写入检查 `git update-index --refresh --really-refresh` 因创建 `.git/index.lock` 返回 `Permission denied`，退出码 1。本批没有再次尝试，没有改 ACL、提权、提交或推送。
- 本报告和进度更新当前为 `UNCOMMITTED / NOT_PUSHED`。工作区待提交文件仅为：
  - `docs/test-reports/stage-58-multistep-demo-acceptance.md`
  - `docs/progress/CURRENT_STATUS.md`
  - `docs/progress/v1-development-progress.md`
- 当前本地与远端仍在 `057e0bbc2065480b7e5d17b6bc09411e0d9c32d1`。VS Code 源代码管理审阅并暂存上述三份文档后，可用中文提交信息 `验收：记录第58批逐题练习稳定性结论`，再推送 `feat/v1-bootstrap`。没有提交成功前，不开始依赖远端状态的下一批。

## 启动与迁移诊断

- 隔离数据根为 `backend/build/mindmate-stage58-fixture`，未使用 `%LOCALAPPDATA%/MindMateAI`，没有个人文件或生产数据。空库完整升级至 `d17a5e9c4b20`；准备重跑期间只生成了合成知识库记录。
- `backend/.venv/Scripts/python.exe` 存在，但其 `pyvenv.cfg` 指向 `%APPDATA%/uv/python/cpython-3.12.11...`。直接运行被 Windows 返回“拒绝访问”，因此没有通过 `scripts/dev.ps1` 完成 Demo 服务启动。
- 使用工作区预装的 Python 3.12.14 加载仓库现有虚拟环境依赖后，Alembic 迁移和合成数据准备成功。前台 Uvicorn 在 `Waiting for application startup` 后以退出码 1 结束，控制台没有异常栈；对同一隔离库运行 TestClient lifespan 时，应用正常启动并关闭。`Host: testserver` 的 health 请求返回 `LOCAL_HOST_REQUIRED` 400，属于预期 Host 校验，不是 lifespan 失败。
- 复用的旧 Stage 56 测试服务曾正常返回 `/api/v1/health = ok`、测试专用 fixture calls 为空；报告中的合成知识库 `01a0e27e-fb0e-793c-9eeb-4d39c394c15a` 查询状态为 `READY`。这只是服务端证据，不等于页面证据。
- `scripts/dev.ps1` 的虚拟环境 Python 路径问题和当前沙箱的长驻进程托管差异没有证据表明是产品代码缺陷；本批未修改启动代码，也未触碰默认个人库。

## 页面验收阻断

- `5180` 上发现已有 Vite 页面进程；`8012` 测试专用端点和知识库状态与 Stage 56 报告吻合。页面标签页创建请求（Codex 内嵌浏览器及普通 Chrome）都被自动审批服务以 `404 Not Found: Model "gpt-5.6-luna" is not supported by any configured account in this group` 拒绝。工具明确说明动作没有执行，且这不是安全拒绝。
- 按提示词停止重试，没有修改审批配置，也没有改用真实 Provider URL、假前端响应或个人数据库。没有页面点击、截图或会话创建；因此 `LEARNING_ONLINE_BROWSER` 和本批 `DEMO_REGRESSION` 保持 `PARTIAL`。
- 检查时测试专用 Provider 调用计数为 0。没有使用真实 Key 或产生外部费用。

## 自动化验证

- 后端命令：`pytest -p no:cacheprovider --basetemp build/stage58-pytest-tmp tests/test_stage55_learning_provider.py tests/test_stage56_provider_fixture.py tests/test_stage57_learning_multistep.py tests/test_stage7_learning_session.py`；结果 `22 passed`。首轮 pytest 默认 `%TEMP%` 在沙箱中无法枚举，测试在 fixture setup 阶段失败；改用仓库内隔离 basetemp 后测试进入并全部通过。
- Ruff：第 56/57 批相关后端文件 `All checks passed`。
- Pyright：相关改动文件 `0 errors, 0 warnings, 0 informations`。
- 前端 Vitest：`15 files passed, 63 tests passed`。
- 前端 typecheck、`npm run lint`、production build 均通过。
- Production build 主 JS 为 `508.86 kB`，仍触发 Vite 既有 `500 kB` chunk 提示；与第 57 批记录一致，本批没有拆包重构。
- OpenAPI 声明 3.1.0；重新生成的前端类型为 `108 schemas / 116 operations`，与已提交类型无 diff。
- `git diff --check` 通过。没有真实 Provider 请求。

## 人工复现步骤

### 在线学习测试夹具页面

在普通本机 Windows PowerShell 中使用两个终端和新的测试数据根，端口选 `8013/5181`，避免覆盖其他本地服务：

```powershell
# 终端 1：在仓库 backend 目录
New-Item -ItemType Directory -Force .\build\mindmate-stage58-online-fixture | Out-Null
.\.venv\Scripts\python.exe -u .\tests\stage56_online_browser_server.py --data-dir .\build\mindmate-stage58-online-fixture --api-port 8013 --web-port 5181
```

```powershell
# 终端 2：在仓库 frontend 目录
$env:MINDMATE_API_PORT = '8013'
npm.cmd run dev -- --host 127.0.0.1 --port 5181 --strictPort
```

在普通浏览器打开 `http://127.0.0.1:5181/settings`。仅使用测试夹具内存凭据，例如 `stage56-deepseek-fixture-key` 和 `stage56-openai-fixture-key`；不要输入真实 Key。分别选择 DeepSeek 与 OpenAI，按页面完成测试授权、每次费用确认、题目生成、答案点评和刷新恢复。检查 `http://127.0.0.1:8013/api/v1/testing/provider-fixture/calls` 中每家各有一条 `question` 和一条 `feedback`，Host 分别为固定的 `api.deepseek.com` / `api.openai.com`，并确认页面资源请求没有访问厂商域名。对下一题先不确认费用，确认请求计数不变；确认后只产生一次请求。这个步骤验证的是固定 `MockTransport`，不是官方服务调用。

### 默认 Mock Demo

在可正常启动仓库虚拟环境的本机 Windows PowerShell 中，从仓库根目录为 Demo 使用新的隔离目录：

```powershell
New-Item -ItemType Directory -Force .\backend\build\mindmate-stage58-demo-data | Out-Null
.\scripts\dev.ps1 -ApiPort 8013 -WebPort 5181 -DataDir .\backend\build\mindmate-stage58-demo-data -OpenBrowser
```

保持 Provider 为脚本默认的 Mock。通过页面导入合成 TXT，确认索引 `READY`，再检查有出处问答和资料不足拒答；分别创建默认 1 题和 3 题学习会话，提交、显式点下一题、刷新并重启后核对结果与历史。三条合成事实可使用：`API请求超时为30 秒。`、`Worker租约时长为45 秒。`、`任务重试冷却间隔为12 秒。`。如果隔离数据根内固定 ONNX 模型未就绪，先按产品页面提供的显式本地模型安装流程处理；不要改用个人默认库。

真实页面步骤完成前，不得将本批 `LEARNING_ONLINE_BROWSER` 或 `DEMO_REGRESSION_THIS_BATCH` 改记为 `PASS`。真实 DeepSeek/OpenAI 请求仍单独保持 `PENDING`。
