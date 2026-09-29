# 第七十三批：阶段 8 运行日志边界与设置验收收口

- 日期：2026-09-29
- 分支：`feat/v1-bootstrap`
- 进场 LOCAL / REMOTE：`f113518737b54e368151af420f2341dd99e282d5` / `f113518737b54e368151af420f2341dd99e282d5`
- 进场工作区：干净
- Provider：Mock；未读取真实 Key，未调用 DeepSeek/OpenAI，未产生费用

## 结论

| 门禁 | 状态 | 证据范围 |
| --- | --- | --- |
| `LOG_RETENTION_CODE` | `PASS` | 应用自有结构化事件有界保留；应用启动的 Uvicorn/Vite 输出不落盘，直出操作者终端；诱饵、导出脱敏、清理 API/UI 自动化和真实隔离启动均通过 |
| `LOG_RETENTION_BROWSER` | `BROWSER_PARTIAL` | 没有普通 Chrome/Edge 页面、点击或 Network 证据 |
| `PACKAGED_LAUNCHER` | `PACKAGED_LAUNCHER_PARTIAL` | `packaging/` 只有说明文件，没有可运行的打包启动器或安装包；运行时日志入口无法据此验收 |
| 设置现有数据目录搬迁 | `NOT_IMPLEMENTED` | 当前阶段 8 需求未把搬迁定义为验收项；Settings 保持不可用并明确区分 Schema 升级 |
| `STAGE8_FULL_V1` | `PARTIAL` | 普通宿主浏览器、打包启动器和其它历史页面门禁仍未完成 |
| 求职 Demo 可用性 | `PASS`（沿用第 42/64 批） | 本批仅重测启动、健康、停止和重启，没有重跑完整求职演示闭环 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 独立门禁未改变 |

## 输出所有权

| 输出来源 | 持久化与所有者 | 私密内容可能性 | 30 天 / 100 MiB 管理范围 |
| --- | --- | --- | --- |
| 应用结构化诊断事件 | 写入数据根 `logs/diagnostic-events` 的白名单 JSONL；由 `diagnostic_log_retention.py` 管理 | 只允许固定事件码、模块、级别、UTC 时间和经过格式校验的少量 ID/计数；不允许正文、Key、Cookie 或绝对路径 | 应用负责启动/周期检查、最早达到阈值清理及设置页清除；清理不可用时不转存原始输出 |
| `dev.ps1` 启动的 Uvicorn stdout/stderr | 不写文件；`Start-Process -NoNewWindow` 继承当前终端句柄，由 `dev.ps1` 持有进程并做健康检查、退出分类和清理 | `logger.exception` 或运行错误可能含异常上下文、路径；这些内容会在本地终端可见 | 不受应用日志保留/清除 API 管理；终端缓冲由宿主终端管理 |
| `dev.ps1` 启动的 Vite stdout/stderr | 不写文件；继承当前终端句柄，由 `dev.ps1` 持有进程并探测页面健康 | 构建/运行错误可能含本机项目路径 | 不受应用日志保留/清除 API 管理；终端缓冲由宿主终端管理 |
| 打包启动器及其子进程 | 仓库目前没有可执行 launcher / `.spec` / Inno Setup 脚本；仅有 `packaging/README.md` | 尚无可审计的打包输出路径 | `PACKAGED_LAUNCHER_PARTIAL`；发布入口实现后需要单独补验 |
| 用户手动运行的终端命令 | 由用户的 PowerShell/终端直接输出；不是应用启动或持有的进程 | 命令参数和命令错误可能含路径或其它本地文本 | 不纳入应用目录、导出、保留和清理范围 |
| Windows 系统日志 | 由操作系统事件日志服务持有和保留 | 事件可能包含本机诊断信息 | 应用无权管理，不纳入设置页的应用日志操作 |

解析 Worker 的独立解析器子进程使用 `stdout=DEVNULL`、`stderr=PIPE`；错误只经过解析失败映射，不转存原始堆栈。这与应用启动时的 Uvicorn/Vite 控制台输出是两条不同路径。

## 实现

- `scripts/dev.ps1` 启动的 Uvicorn 与 Vite 从隐藏窗口改为 `-NoNewWindow`，标准输出/错误直达启动它的终端，没有添加文本日志重定向。健康探测、异常退出分类、端口占用检查和本批进程树清理仍沿用现有实现。启动后会明确说明输出只到终端，不保存为应用日志。
- `scripts/demo.ps1` 仍通过 `dev.ps1` 启动；该入口在当前隔离环境用 `dev.ps1` 进行真实启动验证，没有运行依赖固定 ONNX 缓存的完整 `demo.ps1` 准备流程。
- `dev.ps1 -RuntimeOutputSelfTest` 注入假 Key、假正文、合成绝对路径和 Cookie 到 stdout/stderr。输出到测试调用端可见；隔离数据根、诊断 JSONL、诊断导出均未发现诱饵，根外哨兵文件保持原内容。
- `GET /api/v1/system/privacy` 与 Settings 文案现在明确：设置只管理应用白名单结构化诊断事件；Uvicorn/Vite 输出只显示于终端，手动命令和 Windows 系统日志不属于应用清理范围。诊断目录不可安全访问时仍不提供清理操作，也不以原始 stdout/stderr 作为后备文件。
- API 只调整已有状态消息文案，字段、状态码和数据结构未变；没有数据库 Schema、OpenAPI 或生成客户端类型变化。
- “清理可清理的诊断日志”改为应用内确认对话框，展示当前文件数和体积；支持取消、Escape、单次确认、请求期间防重复和安全失败提示。请求期间不能通过重复点击产生第二个清理 POST；成功后重新读取清理计数。
- `packaging/` 没有 launcher 可供修改或运行，打包入口覆盖保持 `PACKAGED_LAUNCHER_PARTIAL`。操作员复测方式：打包入口可运行后，以新的隔离数据根启动，向启动子进程 stdout/stderr 注入合成诱饵，检查终端显示、应用 JSONL/诊断导出不含诱饵，再核健康、停止、重启、端口释放和根外哨兵。

## 数据目录迁移范围

当前结论不是把 Schema 升级等同于搬迁：

- `docs/project/requirements/v1/09_数据模型与本地存储.md` §5.2 允许安装或首次启动选择数据目录，并明确更改已有数据目录属于迁移，不能只改配置字符串。
- `docs/project/requirements/v1/16_Codex开发任务书.md` §15.1 将“设置中的存储”列为阶段 8 任务，但没有规定现有数据目录搬迁流程或对应验收项；§15.2 列出的门禁也未定义搬迁验收。
- `docs/project/requirements/v1/18_最终决策表.md` `DEC-DATA-006` 冻结的是 Alembic 版本化前向 **数据库 Schema 迁移**，不是用户数据目录搬迁。
- 当前 Settings 只提供存储状态读取；没有数据目录选择/搬迁 API、停写复制、切换或回滚流程。将已有目录搬迁保留为后续发布规划，设置页明确当前不提供该操作。任何未来实现都必须另行满足原始数据目录迁移约束。

因此本批没有加入“迁移成功”按钮，也没有改动数据根、数据库 Schema 或迁移文件。

## 验证证据

- 真实隔离启动：使用 `%TEMP%` 下新建数据根，`dev.ps1` 启动 Uvicorn/Vite；`GET /api/v1/health` 为 `ok`，页面返回 HTTP 200。Alembic 与 Vite 输出可在当前终端看到，没有写入应用日志目录。
- 隔离数据根首次启动后诊断状态为 1 个文件 / 117 字节；对同一根停止后重启，健康仍为 `ok`，诊断日志为 1 个文件 / 234 字节。两个 JSONL 文件内容只有 `APPLICATION_STARTED` 事件字段，无假 Key、正文、绝对路径或 Cookie。
- 根外 `outside-sentinel.txt` 在启动/重启/停止前后内容均为 `stage73-sentinel`。应用启动后通过核对实际监听 PID 的 `Stop-Process` 走正常停止路径，监督脚本退出码为 0；端口释放。`test_local_runtime.py` 覆盖请求停止与异常退出分类。
- 本工具 PTY 发送的 Ctrl+C 只显示 `^C`，没有形成 `dev.ps1` 可读取的终端按键事件；故本批没有把 Ctrl+C 手工路径写成已验证。下一次普通 Windows 终端人工补测时复核一次 Ctrl+C。
- 最初复现 `test_local_runtime.py` 的 PowerShell stdout 问题时，断言遇到 `normal.stdout is None`。PowerShell 将中文 `Write-Host` 输出按当前宿主代码页写入，而 Python 测试宿主按 GBK 解码时产生 `UnicodeDecodeError`。测试输出标记改为 ASCII，并设置显式 UTF-8 容错解码后，停止分类断言正常通过；这属于测试宿主编码问题，不是 Uvicorn/Vite 启动失败。
- `backend/tests/test_local_runtime.py`：`10 passed`。
- `backend/tests/test_stage67_diagnostic_log_retention.py`：`11 passed, 1 skipped`；覆盖 30 天边界、100 MiB 容量、并发清理、目录安全和启动失败关闭。
- `backend/tests/test_stage65_diagnostics.py`：`4 passed`；诊断预览/导出诱饵扫描和失败安全通过。
- 前端全量 Vitest：`16 files / 79 tests passed`；设置 Provider 交互文件在最终修正后再次 `10 passed`，覆盖清除确认、取消、Escape、重复点击、失败和边界文案；记录的非会话写请求中清理端点恰好 1 个 POST。
- 前端 typecheck、lint、build 通过；后端定向 Ruff、Pyright（`0 errors`）、compileall 和 `git diff --check` 通过。Vite build 有既有 JS chunk > 500 kB 提示，本批没有调整分包范围。
- 普通 Chrome/Edge 没有可操作标签页，未记录浏览器 URL、对象 ID、Network 请求或截图，设置页继续 `BROWSER_PARTIAL`。
- 没有运行后端全量测试。第七十二批所列 Credential Manager、Provider fixture、备份目录句柄等既有全量问题不在本批处理范围；定向通过不代表全量通过。

## 设置页人工补测卡

复用第七十批设置矩阵，只补下面两步：

1. 打开 `/settings`，核对日志范围文案与 30 天/100 MiB 计数；打开清理对话框后分别按 Escape、点“取消”，Network 中 `/api/v1/system/diagnostics/logs/clear` 均为 0 次。
2. 再次确认清理，Network 中该端点为恰好 1 次 POST；核对计数刷新、业务对象仍存在，并主动导出诊断 JSON 扫描合成 Key、正文、绝对路径和 Cookie。记录 URL、请求次数和截图位置。

没有普通浏览器证据时保持 `BROWSER_PARTIAL`。

## 下一批浏览器优先级

1. **求职 Demo 回归**：文件上传/导入、索引就绪、带引用知识库问答、学习完成总结与历史定位、同一数据根下刷新和重启恢复。记录真实文件/知识库/会话 ID、URL、关键 Network 次数和截图位置。
2. **阶段 8 历史未验页面**：第七十批矩阵中的历史筛选与删除、任务抽屉/保留、设置日志和诊断导出、存储状态、备份坏包、首页统计，以及 test-only 在线学习 fixture。在线流程仅用 fixture，不用真实 Key。
3. 每条记录标明使用的隔离数据根、普通 Chrome/Edge profile、页面 URL、对象 ID、Network 次数和截图文件位置。若浏览器仍不可用，只保留自动化证据与待测清单，不更新为页面通过。

`HISTORY-AC-04/06` 继续 `CODE_PASS / BROWSER_PARTIAL`，`AC-LEARN-006` 继续 `PARTIAL`，第七十一批 `TASK-AC-05/12` 继续 `CODE_PASS / BROWSER_PARTIAL`。真实 Provider、官方账单与阶段 5–7 完整 V1 仍为独立门禁。

## Git 交付

- 中文提交信息：`完善：收口运行日志边界与设置验收范围`。
- 第一次普通推送尝试退出码 `1`，没有诊断文本。尝试时 LOCAL 为 `8cb905dbe8be4cd72cb5bc44521bc0ab11d03dd1`；随后 `git ls-remote --heads origin feat/v1-bootstrap` 确认 REMOTE 仍为进场 SHA `f113518737b54e368151af420f2341dd99e282d5`。没有强推或重复等待推送。
- 普通 Windows VS Code 终端手动推送及复核：

~~~powershell
git switch feat/v1-bootstrap
git push origin feat/v1-bootstrap
git rev-parse HEAD
git ls-remote --heads origin feat/v1-bootstrap
~~~

推送成功后，本地 HEAD 与 `refs/heads/feat/v1-bootstrap` 的远端完整 SHA 应一致。
