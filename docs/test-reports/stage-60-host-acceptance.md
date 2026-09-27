# 第六十批：宿主验收入口与阶段 8 Demo 证据收口

日期：2026-09-28。分支：`feat/v1-bootstrap`。进场本地与远端 SHA：`16e3316be62768b6ab73695db872bcb9fddc721d`。

本批目标是补跑第 59 批后端关键回归，并提供普通 Windows PowerShell 与浏览器可执行的隔离验收入口。沙箱没有观察到真实浏览器页面点击、刷新或重启，因此不把脚本、自动化测试或运行环境可达性写成浏览器 `PASS`。

## 结论

| 项目 | 本批状态 | 证据口径 |
| --- | --- | --- |
| `BACKEND_PYTEST` | `PASS` | 使用预装 Python 3.12.14 加载仓库 `.venv/Lib/site-packages`，仓库内隔离 `basetemp`，6 个关键回归文件共 `29 passed`。 |
| `FRONTEND_REGRESSION` | `PASS` | Vitest `15 files / 66 tests`、typecheck、ESLint/Oxlint、production build 均通过。 |
| `RUFF_TARGETED` | `PASS` | `ruff check src tests` 通过。 |
| `PYRIGHT_TARGETED` | `PASS` | 预装 Python 运行 `pyright`，本批修改的源文件和回归文件 `0 errors`。全目录仍有既有 Worker/备份测试类型问题，本批未扩大修复范围。 |
| `ALEMBIC_HEAD` | `PASS` | `alembic heads` 为 `d17a5e9c4b20 (head)`；最终 pytest 隔离库查询到同一 revision。 |
| `HOST_ACCEPTANCE_ENTRY` | `PASS` | 新增 `docs/demo/阶段60宿主验收入口.md`，复用现有 Demo 和 test-only Provider 夹具，包含命令、端口、停止方式、走查清单和脱敏报告模板。 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 本批没有真实浏览器点击或截图；后端永久删除确认、共享来源和 FTS 清理已由 pytest 覆盖。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | test-only Provider 的服务端业务路径由后端测试覆盖，页面选择、费用确认、刷新和浏览器计数尚未观察。 |
| `DEMO_REGRESSION_THIS_BATCH` | `PARTIAL` | 提供可复用的隔离 Mock Demo 命令，但未在当前沙箱完成完整页面走查。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 没有真实 Key、DeepSeek/OpenAI 请求或付费调用。 |
| `STAGE7_FULL_V1` / `STAGE8_FULL_V1` | `PARTIAL` | 完整阶段需求、独立备份 Worker、费用对账和浏览器证据仍未全部完成。 |

## 环境与命令

### 后端运行时

仓库 `backend\.venv\Scripts\python.exe` 绑定到当前沙箱不可访问的 `C:\Users\15932\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe`，直接执行会返回 `Unable to create process`。本批没有改 ACL、提权、安装未知包或替换生产凭据。

本批使用 Codex 工作区预装的 Python 3.12.14，并临时加入仓库 `.venv\Lib\site-packages` 与 `backend\src`：

```powershell
$env:PYTHONPATH = "$(Resolve-Path '.\src');$(Resolve-Path '.\.venv\Lib\site-packages')"
& 'C:\Users\15932\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -p no:cacheprovider `
  --basetemp '.\build\stage60-pytest-tmp-final' `
  tests/test_stage8_history_purge.py `
  tests/test_stage8_history_fulltext.py `
  tests/test_stage57_learning_multistep.py `
  tests/test_stage8_history_query_trash.py `
  tests/test_stage8_conversation_history.py `
  tests/test_stage8_learning_history.py
```

结果：`29 passed, 37 warnings`，耗时约 1 分 55 秒。Warnings 为仓库依赖的 Starlette/httpx 与 Alembic 配置弃用提示，没有失败。

### 前端门禁

在 `frontend` 目录执行：

```text
npm.cmd run test       -> 15 files / 66 tests passed
npm.cmd run typecheck  -> passed
npm.cmd run lint       -> passed
npm.cmd run build      -> passed
```

Build 只有既有主 JS chunk 大于 500 kB 的 Vite 提示，没有把它当作失败。

### 其他检查

- `ruff check src tests`：通过。
- 定向 Pyright：本批修改文件 `0 errors, 0 warnings, 0 informations`。
- `compileall`：通过。
- `alembic heads`：`d17a5e9c4b20 (head)`。
- pytest 隔离库 `alembic_version`：`d17a5e9c4b20`。
- `git diff --check`：通过；只有 Git 的 LF/CRLF 转换提示。
- `scripts/dev.ps1`、`scripts/demo.ps1` PowerShell AST 解析：通过。
- `scripts/dev.ps1 -LifecycleSelfTest RequestedStop`：通过，未结束无关进程。

全目录 Pyright 仍报告 43 条既有类型问题，集中在 `history_purge_worker.py`、`task_retention_worker.py` 和备份测试的 TestClient 类型推断；不属于本批修改文件，因此没有借本批扩大修复范围。

## 本批修复

1. `learning_sessions.py`：同一 `next-question` 请求并发时，若 SQLite 事务快照导致第一次幂等查询未看到已提交题目，CAS 失败路径会重新查询 `generated_request_id`；哈希一致则返回已持久化结果，避免错误的 412。
2. `db.py`：`PRAGMA quick_check` 允许返回多行；聚合结果后只有全部为 `ok` 才返回健康状态，避免 `scalar_one()` 将健康库误报为 `MultipleResultsFound`。
3. 回归夹具校准：修正第 59 批三题测试的本地会话 Origin、固定来源文件名、Alembic head 断言、未引用知识点清理断言和一题完成状态；历史筛选测试使用三题会话保持 `IN_PROGRESS`。没有放宽来源校验、删除保护或 Provider 门禁。

## 宿主入口与浏览器证据

入口文件为 `docs/demo/阶段60宿主验收入口.md`，复用：

- `scripts/demo.ps1` + `scripts/dev.ps1`：隔离 Mock Demo，默认 API `8014`、Web `5182`，可按端口占用替换；
- `backend/tests/stage56_online_browser_server.py`：隔离 test-only Provider 夹具，默认 API `8015`、Web `5183`；假传输在后端进程内，不访问官方域名；
- `backend` 关键 pytest 命令、health/ready、Alembic head、停止方式和脱敏报告模板。

本批没有点击浏览器，因此以下状态保持不变：

- `HISTORY_PURGE_BROWSER=PARTIAL`；
- `LEARNING_ONLINE_BROWSER=PARTIAL`；
- `DEMO_REGRESSION_THIS_BATCH=PARTIAL`；
- `REAL_PROVIDER_SMOKE=PENDING`。

宿主完成后需要回传脱敏截图、页面 URL、合成会话 ID、响应状态、假 Provider calls 计数和刷新/重启结果；在此之前不能把上述项目改为浏览器 `PASS`。

## Git 与交接

第 59 批代码已由进场远端 SHA `16e3316be62768b6ab73695db872bcb9fddc721d` 收口，本批不重复提交旧代码。第 59 批历史报告仍保留当时确实存在的 `UNCOMMITTED / NOT_PUSHED` 原始记录；当前状态文档和变更记录已校准为第 59 批已推送事实。

本批在执行 `git add` 时再次遇到：

```text
fatal: Unable to create '.../mindmate-ai/.git/index.lock': Permission denied
```

因此第六十批当前明确为 `UNCOMMITTED / NOT_PUSHED`。没有改 ACL、提权、替换 Git 目录、强推或修改 `main`。本批已完成的文件清单如下，用户可在普通 VS Code 源代码管理面板逐项审阅后暂存、提交和推送：

```text
backend/src/mindmate/application/learning_sessions.py
backend/src/mindmate/infrastructure/db.py
backend/tests/test_stage8_history_fulltext.py
backend/tests/test_stage8_history_purge.py
backend/tests/test_stage8_history_query_trash.py
backend/tests/test_stage8_learning_history.py
docs/progress/CURRENT_STATUS.md
docs/progress/v1-development-progress.md
docs/project/changes/CHG-20260927-HISTORY-ACTIONS-MULTIQUESTION.md
docs/demo/阶段60宿主验收入口.md
docs/test-reports/stage-60-host-acceptance.md
```

在确认工作区没有隔离数据库、向量库、日志、构建产物、截图和真实凭据后，使用中文目的式提交信息，例如 `验收：补跑历史删除测试并建立本机演示入口`，推送 `feat/v1-bootstrap`，再核对：

```powershell
git rev-parse HEAD
git ls-remote --heads origin feat/v1-bootstrap
```

推送后的完整 SHA 需要回填到交付说明；在用户完成这一步前，不把第六十批写成已提交或已推送。
