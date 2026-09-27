# 第五十二批：阶段 8 本机设置与可信备份导出

- 日期：2026-09-27
- 分支：`feat/v1-bootstrap`
- 进场 SHA：`338ca30e42db23954242cb5c1a6811ebf0812264`（与第 51 批 tip / `origin/feat/v1-bootstrap` 一致）
- 工作区进场状态：干净

## 范围

同一对话合并交付：

- **A**：完善 `/settings` 本机存储、Embedding 状态、AI 用量/预算、日志隐私说明；不触发真实 DeepSeek 探测。
- **B**：一致性本地备份创建、校验、会话保护下载；恢复 UI/API 保持禁用。

## A. 设置 / 存储 / 用量 / 预算

| 项 | 状态 | 证据 |
|----|------|------|
| 数据存储与空间只读分类统计 | `PASS` | `GET /api/v1/system/storage`；失败不显示为 0 |
| 本地 Embedding 状态复用 | `PASS` | 设置页调用既有 `GET /api/v1/embedding-model`；安装仍走知识库入口 |
| Provider / Key / 同意 / Mock·在线模式 | `PASS` | 沿用第 31/38 批门禁；未宣称真实 DeepSeek 联通 |
| 近 30 天用量（Mock/在线隔离） | `PASS` | `GET /api/v1/system/ai-usage`；未知 usage 不计为已计量 0 |
| 在线实际用量空态文案 | `PASS` | 无 DeepSeek 记录时返回“在线实际用量暂无记录” |
| 预算配置持久化 | `PASS` | `AppSetting` 键 `ai.budget.period`；默认关闭 |
| 硬停止后端外发前判定 | `PASS` | `assert_external_budget_allows` 接入 Chat 外发与连接探测；并发锁 |
| 未知 usage 保守拒绝 | `PASS` | `unknown_usage_policy=deny` |
| 周期硬限额完整产品验收 | `PARTIAL` | 估算基于本地费率快照，非官方实时余额；无真实 DeepSeek 周期账单对账 |
| 日志清理 / 诊断导出 / 存储迁移按钮 | `PENDING` | 仅说明，无假按钮 |
| Key 不进 SQLite/响应/备份 | `PASS` | 既有凭据隔离 + 本批响应审查 |

定向测试：`tests/test_stage8_settings_usage_budget.py`（4 passed）。

## B. 备份创建 / 校验 / 下载

| 项 | 状态 | 证据 |
|----|------|------|
| SQLite online backup + 显式清单 | `PASS` | `local_backup.py`；非整树无界 `rglob` |
| ContentObject / parsed / 非秘密 config | `PASS` | 冻结清单后写入同一归档 |
| 排除 Key / logs / models / vectors / WAL | `PASS` | manifest `rebuild_after_restore`；stage6 排除回归仍过 |
| `.partial` 原子发布 | `PASS` | 失败不留下可误认完成包 |
| ZIP 路径安全 / 校验 | `PASS` | 穿越/坏包拒绝 |
| 创建 + 列表 + 下载 API | `PASS` | `/api/v1/backups*`；会话保护 `FileResponse` |
| 设置页创建/下载与未加密提示 | `PASS` | Settings 备份区 |
| `BACKUP_CREATE` | `PASS` | 自动化矩阵通过 |
| `BACKUP_RESTORE` | `PENDING` | `POST .../restore` → 501；UI 禁用 |
| 独立 Worker 异步创建 | `PARTIAL` | 请求线程内同步锁创建，可轮询状态 |

定向测试：`tests/test_stage8_backup_export.py` + `test_tasks_backups.py` + stage6 排除用例（共 11 passed，与 A 合计相关 15 passed）。

## 未改写的既有状态

- 第 51 批：历史手动永久删除 UI、两类浏览器确认点击仍 `PENDING`；多题定位仍 `PARTIAL`。
- 第 42 批求职 Demo `PASS` 未因本批改写；真实 DeepSeek 仍 `PENDING`。
- 阶段 5～8 完整 V1 仍为 `PARTIAL`；阶段 8 不因备份导出标 `PASS`。

## 门禁

- 后端定向：settings 4 + backup 相关 11 = 15 passed
- `ruff check`（本批涉及路径）通过
- `pyright`（本批新增/改动模块）0 errors
- OpenAPI 3.1 已导出并 `npm run api:generate`
- 前端 `typecheck` / `lint` / `stage6-provider` Vitest / `build` 通过
- `git diff --check` 无空白错误
- 未跑真实 Key、未读默认用户库、未制作私人备份外发样本

## 版本边界

- 备份格式：`backup_format_version` 见实现；恢复兼容合同留给下一批。
- 预算币种：USD 估算；费率核对日沿用 `public_cost_estimate().checked_on`。

## 下一批建议（单一合并目标）

实现**本地备份完整恢复**（校验 → 原子切换数据根 → 重建向量/FTS → 强制重配 Key），或补齐第 51 批遗留的历史永久删除 UI 与浏览器确认点击；二者择一，不要并行扩大范围。
