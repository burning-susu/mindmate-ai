# 第六十七批：阶段 8 日志保留清理与历史、诊断浏览器验收

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场本地 HEAD：`49a3139ff591ee81f54121eb31e4a96eb27f5834`
- 进场远端：`origin/feat/v1-bootstrap`，SHA 与本地一致

## 结论

| 验收项 | 状态 | 证据范围 |
| --- | --- | --- |
| `LOG_RETENTION_CODE` | `PASS` | 应用白名单事件落盘、启动/周期维护、容量与时限收敛、用户清理 API、设置页交互自动化通过 |
| `LOG_RETENTION_BROWSER` | `PARTIAL` | 未能进入普通 Chrome/Edge；安全清理范围通过后端测试和前端交互测试核验 |
| `DIAGNOSTICS_PREVIEW_EXPORT_BROWSER` | `PARTIAL` | 页面预览/下载没有普通浏览器证据；导出白名单自动化通过 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 未完成合成对话/学习记录的取消、Esc、错误确认、正确确认及 Network DELETE 计数 |
| `HISTORY_MULTISTEP_BROWSER` | `PARTIAL` | 未完成三道合成题的页面搜索与 `question_id` 定位检查 |
| `STAGE8_FULL_V1` | `PARTIAL` | 账目对账、在线学习页面和本批浏览器证据仍缺 |
| 求职 Demo 可用性 | `PASS`（沿用既有证据） | 沿用第四十二/六十四批证据，本批没有重跑完整 Demo |
| 完整 V1 | `PARTIAL` | 不由 Demo 或本批代码测试替代阶段 5–8 验收 |
| `BACKUP_WORKER_CODE` / `BACKUP_WORKER_BROWSER` / `BACKUP_RESTORE_REGRESSION` | `PASS`（第六十六批） | 保留第六十六批原有证据 |

真实 DeepSeek/OpenAI 请求、真实凭据和付费额度均未使用。

## 实现

- 新增本地结构化事件存储，仅接受固定事件码，以及 UUID、已知任务类型/状态、非负耗时和尝试次数等受限字段。当前记录应用启动、停止、生命周期失败及日志维护失败；不从 Python、Uvicorn、第三方日志处理器复制原始异常。
- 日志文件固定在应用数据根 `logs/diagnostic-events`，采用严格文件名白名单。单文件轮转阈值为 10 MiB，总量最多 100 MiB，按 UTC 文件创建时间最多保留 30 天，先触发者生效。应用启动和隐私状态读取执行维护，非测试运行每 6 小时再检查一次。
- 写入和清理由线程互斥及跨进程文件锁串行化。写入句柄只在单次追加时打开；占用文件删除失败时保留并给出脱敏不完整状态。目录、日志条目遇到符号链接/重解析点或硬链接时停止处理，不跟随目标。
- 新增本地会话保护的 `POST /api/v1/system/diagnostics/logs/clear`。仅删除固定目录下符合名称白名单的日志文件，不接受前端路径、通配符或日志字段。Origin 校验由现有本地安全中间件执行。
- 设置页展示文件数、体积与 30 天/100 MB 上限；点击清理前要求确认，之后展示成功/占用/失败结果并刷新状态。清理测试确认任务、业务对象、备份、模型、索引及 `logs` 下其他文件仍在。
- 第六十五批安全诊断包保持独立有限 JSON 投影，不读取原始日志；回归测试确认其不包含新增结构化日志内容。
- 仅应用拥有的结构化事件处于本批保留服务控制之下。运行时及外部启动器的 stdout/stderr 没有受控落盘，仍是整体 `LOG_RETENTION` 的剩余缺口，因此不宣称日志整体验收通过。

## 自动化证据

| 门禁 | 命令/范围 | 结果 |
| --- | --- | --- |
| 后端定向回归 | `pytest tests/test_stage67_diagnostic_log_retention.py tests/test_stage65_diagnostics.py tests/test_stage8_settings_usage_budget.py` | `19 passed, 1 skipped` |
| 保留边界与并发 | 30 天边界、容量收敛、重复维护、并发轮转/清理、重复启动 | 通过；容量算法用较小测试阈值覆盖，同步断言默认上限为 100 MiB |
| Windows 文件占用 | 使用独占 Win32 文件句柄阻止删除，再释放后重试 | 通过；占用文件保留且不阻断业务 |
| 重解析点 | Windows 测试目录 junction 创建 | 跳过；当前环境创建 junction 失败，测试未跟随或改动外部目标 |
| 诊断安全 | 安全状态导出与日志记录诱饵 | 原始日志、Key、Token、路径和正文诱饵没有进入诊断导出或结构化日志 |
| 设置页交互 | Vitest：拒绝确认不发请求、确认清理、刷新计数、失败安全提示 | 通过 |
| Ruff / Pyright | 本批后端代码和测试 | 通过；Pyright `0 errors` |
| 前端 Vitest | `npm.cmd run test -- --run` | `15 files / 71 tests passed` |
| 前端质量 | typecheck、lint、build | 全部通过；Vite 保留既有 chunk-size 警告，最大 chunk `520.14 kB` |
| OpenAPI / 类型 | `scripts/export_openapi.py`；`npm.cmd run api:generate` | OpenAPI 3.1，`111 schemas / 120 operations`，生成类型同步 |
| Diff | `git diff --check` | 通过 |

后端运行时出现既有 Starlette/httpx 与 Alembic 配置弃用警告，未影响测试结果。

## 浏览器阻断与交接

- `cua.getState()` 只显示无标签页的 Codex 内置浏览器，没有可绑定的普通 Chrome/Edge 窗口。
- `cua.listWindows()` 在审批阶段返回 `404 Not Found`，错误指出当前模型账户不支持 `gpt-5.6-luna`；request id：`023bfe13-d0a2-4735-b0da-de80d2d1b305`。动作未执行，未重试审批或绕过该检查。
- 本批没有普通浏览器点击、页面刷新、Network 面板、文件下载、永久删除、截图或截图文件。pytest/API 状态不作为页面验收证据。
- 人工补验入口：在临时/Guest Chrome profile 打开本批隔离服务的 `http://127.0.0.1:5186/settings`。先确认“日志与隐私”中的文件数与上限，点“清理可清理的诊断日志”后取消确认并检查没有 POST，再确认一次，核对成功提示和刷新后的 0 文件；随后预览诊断、取消预览、下载 JSON 并确认不包含 Key/Token/完整路径/正文。下载文件留在本机，不上传或提交。
- 历史部分需在同一隔离数据根先创建合成对话与三题均已作答的学习会话，再按第六十五批报告中的步骤完成取消/Esc/错误确认词/正确确认词与 Network DELETE 次数，并搜索每道题的题干、提交选项、公开反馈核对 URL `question_id`。永久删除仅操作这些隔离合成记录；共享文件、知识库和其他会话保持存在。

## 后续缺口

- `BUDGET_RECONCILIATION` 仍需本地周期用量/预算账目核对。应用估算不得当成 DeepSeek/OpenAI 官方账单。
- `LEARNING_ONLINE_BROWSER` 仍需 test-only MockTransport 页面验收；不调用真实付费 Provider。
- 全局错误/离线验收及阶段 8 最终验收由后续批次处理。
