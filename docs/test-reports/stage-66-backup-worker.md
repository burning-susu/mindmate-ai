# 第六十六批：阶段 8 独立备份 Worker 与恢复回归

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场 HEAD：`a5f0cc7fa358983078cc09d9286f351e8bff9816`
- 进场远端：`origin/feat/v1-bootstrap` 与本地 HEAD 一致
- 项目阶段：阶段 8 开发中；阶段 5–7 与阶段 8 完整 V1 继续 `PARTIAL`

## 结论

| 验收项 | 状态 | 证据范围 |
| --- | --- | --- |
| `BACKUP_WORKER_CODE` | `PASS` | 持久任务、租约、单活动约束、跨进程接管、失败重试、归档校验和恢复回归自动化通过 |
| `BACKUP_WORKER_BROWSER` | `PASS` | 已安装 Windows Chrome 实际点击创建、刷新、下载；下载包与服务端归档逐字节相同并离线校验 |
| `BACKUP_RESTORE_REGRESSION` | `PASS` | 阶段 8 备份导出、完整恢复、通用任务与本批 Worker 组合 `22 passed` |
| `STAGE8_FULL_V1` | `PARTIAL` | 阶段 8 仍有日志保留、账单对账、诊断/历史页面人工验收等独立缺口 |
| 求职 Demo 可用性 | `PASS`（既有证据） | 沿用第四十二/六十四批 Demo 证据；本批未重跑完整求职 Demo |
| 完整 V1 | `PARTIAL` | 不由本批备份能力或求职 Demo 证据替代阶段 5–8 完整验收 |

真实 DeepSeek/OpenAI 请求、真实凭据和付费额度均未使用。默认 Provider 为 Mock。

## 实现

- `POST /api/v1/backups` 现在只持久化备份记录和 `BackgroundTask`，返回 `202`、备份 ID 与 `QUEUED` 初始状态。重复幂等键返回同一备份；已有活动任务时返回稳定 `409`，不会建立无界队列。
- 新增 SQLite 部分唯一索引，数据库层保证最多一个排队或运行中的备份。应用启动时启动 `BackupCreationWorker`，关闭时等待当前归档和租约心跳结束后再释放数据库 Engine。
- Worker 原子领取现有任务、续租并单并发运行。目标归档同时使用跨进程文件锁；失去租约时分块归档停止发布。空闲路径只读查询，不依赖请求生命周期或前端轮询维持任务。
- 归档文件名使用完整备份 ID。Worker 清理残留 `.partial`；重启后复核既有归档，并检查归档内 SQLite 快照包含相同备份 ID、任务 ID、状态和目标路径。已发布但数据库状态尚未提交的完整归档可安全补交；不完整或不匹配归档不会成为 `COMPLETED`。
- 设置页区分“排队中 / 正在创建 / 已完成 / 失败”。失败备份有明确的“重试备份”入口。创建与重试都有幂等键。
- 下载仍逐次校验格式 1 归档，并将 manifest 哈希与数据库记录核对。文件缺失、损坏或被另一份归档替换时，下载失败且备份记录转为不可下载的脱敏失败状态。
- 保留格式 1 manifest、白名单、哈希、数据库快照、排除 Key/向量、恢复双重确认、重启切换、回滚、恢复后 Mock 与索引待重建边界。恢复启动协调继续将快照中的进行中任务/备份安全关闭。

## 浏览器证据

- 浏览器：本机安装的 Google Chrome，使用本批隔离 profile；非用户默认 Chrome profile。
- API/Web：`127.0.0.1:8018` / `127.0.0.1:5186`，仅回环监听；验证结束后端口均已释放。
- 隔离数据根：`backend/build/stage66-backup-browser-data`；只含合成 16 MiB 配置文件、应用 SQLite 与本批归档。
- 在设置页点击“创建备份”，请求返回 `202`。刷新设置页后，列表仍显示同一备份并最终到达 `COMPLETED`；随后点击“下载备份包”。
- 下载归档 SHA-256 与服务端隔离目录中的归档一致。后端 `verify_backup_archive` 离线校验通过：`file_count=2`、`includes_secrets=false`、`includes_vectors=false`。
- 截图：`backend/build/stage66-backup-browser-artifacts-final/settings-backup-completed.png`。隔离服务使用 Mock，没有真实 Provider 请求。

## 自动化验证

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| Worker / 备份 / 恢复组合 | `python -m pytest --basetemp=build\pytest-stage66-final3 -p no:cacheprovider tests/test_stage66_backup_worker.py tests/test_stage8_backup_export.py tests/test_stage8_backup_restore.py tests/test_tasks_backups.py -q` | `22 passed` |
| 前端全量 Vitest | `npm.cmd run test -- --run` | `15 files / 69 tests passed` |
| TypeScript 与生产构建 | `npm.cmd run build` | 通过；既有压缩后 JS chunk `518.47 kB`，保留 Vite `500 kB` 提示 |
| 前端 lint | `npm.cmd run lint` | 通过 |
| Ruff | 本批修改的后端代码、迁移和测试 | 通过 |
| Pyright | Worker、备份应用、归档、API、`main.py` | `0 errors` |
| OpenAPI / 前端生成类型 | `python scripts/export_openapi.py`；`npm.cmd run api:generate` | OpenAPI 3.1，`110 schemas / 119 operations`；生成类型同步 |
| 迁移 | `python -m alembic heads`（`backend` 目录） | `7f39d81c0a64 (head)` |
| Diff | `git diff --check` | 通过 |

pytest 默认 `%TEMP%` 在本环境无法枚举，定向测试使用仓库内 `backend/build` 隔离 `basetemp`。测试有 Starlette/httpx、Alembic 配置和既有历史索引测试警告，均未导致最终组合失败。

最终组合前曾观察到 Windows 目录重命名释放句柄时的恢复用例波动。补齐父进程测试 Engine 显式释放，并让备份 Worker 等待租约心跳连接退出后，最终组合 `22 passed`；恢复目录切换算法本身未改动。此前同一恢复用例的隔离重跑也通过。

## 未完成项

- `LOG_RETENTION`、`BUDGET_RECONCILIATION` 继续 `PARTIAL`。
- `DIAGNOSTICS_PREVIEW_EXPORT`、`HISTORY_PURGE_BROWSER`、`HISTORY_MULTISTEP_BROWSER` 的第六十五批页面证据仍需普通浏览器操作者补齐。
- `LEARNING_ONLINE_BROWSER` 继续 `PARTIAL`；真实 DeepSeek/OpenAI 付费冒烟保持 `PENDING`。
- 阶段 5、6、7 完整 V1 及 `STAGE8_FULL_V1` 均未通过本批自动转为 `PASS`。
