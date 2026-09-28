# 第六十九批：阶段 8 全局任务与离线容错收口

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场本地 HEAD：`c0875126e34b9445db025124f862d158358c41ab`
- 进场远端：`origin/feat/v1-bootstrap`，SHA 与本地一致
- 项目阶段：阶段 8 开发中；阶段 5–7 与阶段 8 完整 V1 继续 `PARTIAL`

## 结论

| 验收项 | 状态 | 证据范围 |
| --- | --- | --- |
| `GLOBAL_TASK_DRAWER_CODE` | `PASS` | 顶栏全局任务按钮、持久任务摘要、阶段/进度/终态/脱敏失败原因、Esc/关闭/焦点回归及受支持取消 API 已实现 |
| `LOCAL_BACKEND_UNAVAILABLE_CODE` | `PASS` | 只读 health 探测、本地服务全页阻断、重新连接和启动说明；网络失败分类回归通过 |
| `PARTIAL_FAILURE_CODE` | `PASS`（既有能力复用） | 首页和各页面继续保留局部失败与重试；全局任务读取失败不覆盖其他页面 |
| `OFFLINE_LOCAL_CODE` | `PASS` | 本地 API 使用继续由本地会话/路由承担；已知浏览器离线时 Chat/学习在线请求在外发前被禁用并显示原因 |
| `ONLINE_PROVIDER_DISABLED_WHEN_OFFLINE` | `PASS`（代码门禁） | DeepSeek/OpenAI 选择不因 `navigator.onLine=true` 被视为可用；离线仅作为保守阻断，Provider 实际错误仍由后端脱敏返回 |
| `ROUTE_RECOVERY_CODE` | `PASS`（代码门禁） | 知识库、学习会话和既有文件详情的 404 专用状态与返回入口；未删除资源仍提供重试 |
| `GLOBAL_TASK_DRAWER_BROWSER` | `BROWSER_PARTIAL` | 当前会话仅有无标签页的 Codex 内置浏览器，没有普通 Chrome/Edge 可绑定窗口；未将 API/自动化测试冒充点击证据 |
| `LOG_RETENTION_BROWSER` / `DIAGNOSTICS_PREVIEW_EXPORT_BROWSER` / `HISTORY_PURGE_BROWSER` / `HISTORY_MULTISTEP_BROWSER` | `PARTIAL`（继承） | 第 67 批页面缺口本批未能进入普通浏览器补验 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL`（继承） | 第 68 批 test-only Provider 页面缺口仍待普通浏览器走查 |
| `STAGE8_FULL_V1` | `PARTIAL` | 阶段 8 仍有普通浏览器证据和完整矩阵中的历史页面缺口；不因本批代码/自动化通过转为 `PASS` |
| 求职 Demo 可用性 | `PASS`（继承） | 沿用第四十二/六十四批 Demo 证据，本批未重跑整条 Demo |
| 完整 V1 | `PARTIAL` | 不用 Demo、MockTransport 或局部回归代替阶段 5–8 完整验收 |

真实 DeepSeek/OpenAI 请求、真实凭据、官方账单和付费额度均未使用。

## 实现

### 全局任务入口

- 新增 `frontend/src/components/GlobalTaskDrawer.tsx`，挂载到 `AppShell` 顶栏，不新增一级导航。所有路由都能打开同一入口；任务列表从持久化 `/api/v1/home/overview?task_limit=30` 读取，页面切换、刷新和应用重启不依赖进程内计时器恢复。
- 列表显示真实任务类型、状态、阶段、进度、最近更新时间、任务编号和后端已经脱敏的失败码/摘要。运行任务有持久状态轮询；关闭抽屉只关闭视图，不发送取消请求。
- 仅对后端已有且有明确路由的任务显示取消：`FILE_IMPORT` 调用 `/api/v1/file-imports/{id}/cancel`；索引、知识库成员和本地模型安装调用 `/api/v1/tasks/{id}/cancel`。文件重处理、聊天和学习任务没有被误显示为通用取消按钮。取消成功后同时刷新全局和首页摘要，组件内阻止重复取消。
- 抽屉支持关闭按钮、遮罩、Escape、Tab 可达和关闭后的焦点回归；错误原因只使用服务端安全投影，不渲染堆栈、原始异常、路径、Key 或请求正文。

### 本地服务、局部错误和离线

- `AppShell` 使用只读 `/api/v1/health` 直接探测本地服务，不把一次会话建立失败误判为服务健康失败。探测失败时显示全页阻断状态、重新连接按钮和 README/回环地址启动指引；恢复前不渲染会修改本地数据的路由操作。
- `frontend/src/api/client.ts` 增加 `LocalBackendUnavailableError` 和安全 ProblemDetail 解析：回环网络异常不泄露浏览器原始异常；后端只返回 `detail` 时保留既有脱敏提示，缺失字段使用固定安全默认值。
- `frontend/src/useNetworkStatus.ts` 只在浏览器明确处于离线时作为保守阻断信号，不把在线状态当成 Provider 可用证明。Chat、学习新建和学习会话的 DeepSeek/OpenAI 操作在离线时禁用发送/出题/点评，并说明恢复网络后由用户显式重试；Mock 和本地文件、知识库、历史路径不受该门禁影响。
- 知识库详情和学习会话详情对 404 显示“资源不存在/已进入回收站”的专用说明和返回入口；文件详情原有专用状态继续保留。

## 阶段 8 追踪矩阵

| 需求/AC | 代码位置 | 自动化证据 | 页面证据 | 当前状态 | 剩余动作 |
| --- | --- | --- | --- | --- | --- |
| `AC-GLOBAL-001` | `frontend/src/App.tsx` 导航与路由 | `src/test/smoke.test.tsx`、前端全量回归 | 第 67/68 批历史页面证据 | `PASS`（代码/自动化） | 普通浏览器补一次跨入口点击 |
| `AC-GLOBAL-002` | `frontend/src/pages/HomePage.tsx`、`api/home.ts` | `stage8-home-overview.test.tsx` 等既有回归 | 首页历史证据按报告继承 | `PASS`（代码/自动化） | 重新做一次合成数据首页点击记录 |
| `AC-GLOBAL-003` | `GlobalTaskDrawer.tsx`、`App.tsx`、`App.css` | `stage8-global-recovery.test.tsx`；全量 `75 passed` | 本批未能进入普通 Chrome/Edge | `BROWSER_PARTIAL` | 跨 `/files`、`/chat`、`/history` 切换，刷新后打开抽屉并核对取消一次 |
| `AC-GLOBAL-004` | `KnowledgeBaseDetailPage.tsx`、`LearningSessionPage.tsx`、既有 `FileDetailPage.tsx` | 代码分支已覆盖，未新增专用页面测试 | 本批无普通浏览器刷新证据 | `PASS`（代码）/`BROWSER_PARTIAL` | 用隔离不存在 ID 刷新并保留返回入口截图 |
| `AC-TASK-001` | 既有任务 Worker 与 `home_overview.py` | 第 68 批预算/任务组合；本批后端阶段 8 组合 `16 passed` | 无新增普通浏览器证据 | `PASS`（既有） | 完整阶段矩阵引用并补页面状态观察 |
| `AC-TASK-002` | 既有重试端点与本批安全取消入口 | `tests/test_tasks_backups.py`、阶段 5/8 任务测试 | 取消按钮待浏览器点击 | `PASS`（代码/自动化）/`BROWSER_PARTIAL` | 合成失败任务补一次重试/取消 Network 计数 |
| `AC-TASK-003` | 持久 `BackgroundTask`、Worker 租约和全局抽屉 | 阶段 5 Worker、备份恢复和本批前端回归 | 重启页面证据待补 | `PASS`（既有）/`BROWSER_PARTIAL` | 强制重启隔离服务后核对同一 task_id |
| `AC-TASK-004` | `task_retention` API/Worker 与首页清理控件 | `test_stage8_task_retention.py` 通过 | 第 67 批浏览器缺口继承 | `PASS`（代码/自动化）/`BROWSER_PARTIAL` | 普通浏览器确认词、取消和清理后计数 |
| `AC-PRIV-004` | `api/client.ts`、`useNetworkStatus.ts`、Chat/学习页面 | API 客户端网络异常、全量前端回归 | 本批无普通浏览器离线网络拦截证据 | `PASS`（代码）/`BROWSER_PARTIAL` | Guest profile 断网后核对本地列表可读、在线按钮阻断且无外发 |
| `AC-BACKUP-*` | 既有备份 Worker/恢复页面 | 第 66 批 `PASS` 证据继承 | 第 66 批页面证据继承 | `PASS`（继承） | 不重复写成本批亲测 |

## 自动化验证

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 前端全量 Vitest | `npm.cmd run test -- --run` | `16 files / 76 tests passed` |
| 新增全局恢复回归 | `npm.cmd run test -- --run src/test/stage8-global-recovery.test.tsx src/test/api-client.test.ts` | `2 files / 6 tests passed` |
| 前端 TypeScript | `npm.cmd run typecheck` | 通过 |
| 前端 lint | `npm.cmd run lint` | 通过 |
| 前端生产构建 | `npm.cmd run build` | 通过；Vite 保留既有主 chunk 超过 500 kB 提示，当前约 `538.70 kB` |
| 后端阶段 8/任务组合 | `backend\.venv\Scripts\python.exe -m pytest --basetemp .pytest-stage69 tests/test_stage8_task_retention.py tests/test_stage8_settings_usage_budget.py tests/test_tasks_backups.py` | `16 passed`；Starlette/httpx、Alembic 配置和 pytest cache 权限警告未影响结果 |
| Diff | `git diff --check` | 通过 |

默认系统 `%TEMP%` 下的 pytest 根目录无法被当前环境枚举；本批使用仓库内隔离 `backend/.pytest-stage69` 运行，目录只用于测试临时文件，不属于交付物。

## 浏览器证据与最短补验步骤

本批调用 `cua.getState()` 的结果只有 `Codex In-app Browser` 且无标签页；没有可绑定的普通 Chrome/Edge 窗口。没有重复此前被审批层拒绝的普通 Chrome 创建，也没有启动 Playwright（此前环境已记录 `spawn EPERM`）。因此本批没有截图、普通浏览器 URL、profile、页面会话、Network 计数或真实 Provider 调用摘要，`GLOBAL_TASK_DRAWER_BROWSER`、`OFFLINE_LOCAL_BROWSER` 和相关历史页面均不得写成 `PASS`。

在本机普通 Chrome/Edge Guest profile 中使用隔离合成数据根时，按以下最短步骤补验：

1. 启动隔离 Mock API/Web，打开 `/files`；确认顶栏“任务”按钮可达，创建或准备一个 `FILE_IMPORT`/索引任务。
2. 切到 `/chat`、`/history` 和 `/settings`，打开全局任务抽屉；核对同一 `task_id`、任务类型、阶段、进度和失败摘要。刷新页面后再次打开，不关闭任务。
3. 对隔离任务点击一次“取消任务”，记录 Network 只出现一次支持的取消 POST，等待终态 `CANCELLED`；按键盘 Escape 关闭并核对焦点回到顶栏按钮。
4. 停止本地 API，刷新任一路由，保存全页“本地服务不可用”截图；启动 API 后点击“重新连接”，确认原 URL 恢复。
5. 保持回环 API 正常但在隔离 profile 断开外网：文件、知识库、历史仍可读；选择 DeepSeek/OpenAI 时在线发送/出题按钮显示离线原因且不产生 Provider fixture call。恢复外网后只由用户显式重试。
6. 使用不存在的知识库/学习会话 ID 刷新，保存专用不存在状态与返回入口。日志、诊断 JSON、截图和合成数据根全部留在忽略目录，不提交。

## 交接

- 本批新增报告：`docs/test-reports/stage-69-global-recovery.md`。
- 本批只完成代码与自动化门禁，阶段 8 不标 `PASS`。下一批先完成上述普通浏览器页面证据，再处理矩阵列出的历史/诊断/在线 Provider 遗留项；真实 Provider smoke、官方账单对账和完整 V1 不在本批范围内。
- 本批代码已在本地使用中文提交信息 `完善：补齐全局任务与离线错误恢复体验`；`git push --verbose origin feat/v1-bootstrap` 返回退出码 `128` 且没有诊断文本，复核远端仍为进场 SHA `c0875126e34b9445db025124f862d158358c41ab`。本批未强推、不修改 `main`；需在普通 Windows VS Code 终端重试推送并核对本地/远端完整 SHA。
