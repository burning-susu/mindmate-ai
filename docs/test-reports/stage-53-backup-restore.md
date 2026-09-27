# 第五十三批：阶段 8 本地备份完整恢复

- 日期：2026-09-27
- 分支：`feat/v1-bootstrap`
- 进场 SHA：`1bb767d2fbe7d4a4f94ab9005ac9900d9d467618`（与第 52 批 tip / `origin/feat/v1-bootstrap` 一致）
- 工作区进场状态：干净

## 范围

把第 52 批 `backup_format_version=1` 的本地备份包做成可操作的完整恢复：浏览器创建并下载、离线校验、另一隔离根预检、双重确认、进程重启后切换、核对旧数据保护与索引/Key 状态。

## 状态

| 项 | 状态 | 说明 |
|----|------|------|
| `BACKUP_CREATE` 浏览器创建与下载 | `PASS` | 根 A 点击“创建备份”，按钮经过“正在创建备份…”后出现“下载备份包”；再点击后经过“下载中…”回到“下载备份包”。离线校验的是这次创建落在隔离根 `backups/` 的同一归档。自动化浏览器没有把 blob 另存进用户下载目录 |
| `BACKUP_RESTORE` | `PASS` | 预检不改数据；勾选覆盖说明并输入确认语后才确认；确认后页面为“已确认，等待重启后切换”。退出后端进程再启动后，页面为“恢复完成 · 本机已保留恢复点” |
| 索引重建 | `NEEDS_REBUILD` | 没有在本批自动跑 ONNX/FTS 重建。备份中的 READY 版本会被收成 `NEEDS_REBUILD` 并清空活动指针；本批浏览器样本知识库本身是 `EMPTY`，恢复后仍是 `EMPTY`，状态字段 `index_outcome=NEEDS_REBUILD`。检索在真实重建并校验前不可用 |
| Key / 外发 | `PASS` | 未写入或读取真实 Key。恢复后生成模式为 Mock，同意被清空，重新确认前探测按钮保持禁用。页面点击“我已核对，保持 Mock 不外发”后仍是 Mock，在线操作为 0 |
| 独立备份 Worker | `PARTIAL` | 创建仍在请求线程内同步完成，本批没有改成独立 Worker |
| 周期硬限额完整账单对账 | `PARTIAL` | 本批未改，仍不是官方实时余额 |
| 第 51 批浏览器删除确认 / 手动永久删除 UI | `PENDING` | 本批未做 |
| 多题定位 | `PARTIAL` | 本批未做 |
| 阶段 8 整体 | `PARTIAL` | 恢复闭环不把阶段 8 标成完成 |
| 求职 Demo（第 42 批） | `PASS` | 维持原证据，本批未重跑整条 Demo |
| 真实 DeepSeek | `PENDING` | 未调用 |

## 隔离现场

- 根 A：`%TEMP%\mindmate-ai-stage53-a`。合成文件 `stage53-alpha.txt`（SHA-256 `72068ea90569f0d5bd5caf855bf92fe201a4eaaac4ec66b145588eafd086e255`）、知识库 `stage53-alpha-kb`、对话“stage53 alpha hello”、学习主题 `stage53-alpha-topic`。
- 根 B：`%TEMP%\mindmate-ai-stage53-b`。恢复前是 `stage53-beta-kb`、`stage53-beta.txt` 和 `vectors/old-generation.bin`。
- 根外哨兵：`%TEMP%\stage53-outside-sentinel.txt`，内容 `do-not-touch`，恢复后未变。根 A 数据库文件仍在。
- 进程：API `127.0.0.1:8013`，页面 `127.0.0.1:5183`，`MINDMATE_PROVIDER_MODE=mock`。没有使用默认个人数据根。
- 文件选择：页面文件输入收到这份归档并走同一套上传/预检。浏览器工具拒绝了系统文件对话框命令，所以没有弹出原生选择框。

## 归档校验

`verify_backup_archive` 通过。格式 `1`，schema `a50e7c1b9d44`，3 个文件，`includes_secrets=false`，`includes_vectors=false`，`encrypted=false`。包内数据库 `quick_check=ok`，含 1 个文件、1 个知识库、1 条对话、1 条学习记录。知识库名 `stage53-alpha-kb`，主题 `stage53-alpha-topic`。

## 恢复后核对

- 确认之后、重启之前：根 B 仍是 `stage53-beta-kb`，恢复点目录已存在，实时向量文件仍在。
- 重启之后：知识库 `stage53-alpha-kb`，文件 `stage53-alpha.txt`，学习主题 `stage53-alpha-topic`，对话 1 条。内容 SHA-256 与导入时一致。beta 不在活动对象里。
- 恢复点数据库仍是 `stage53-beta-kb`。旧向量在 `runtime/restore-control/aside/.../vectors/old-generation.bin`，活动 `vectors/` 中不再有该文件。
- 设置：`ai.chat.generation_mode=mock`，`restore.provider_reconfirm_required.required=true`，同意由 restore 清空。页面在线操作为 0。
- 文件页可见 `stage53-alpha.txt`，没有 beta。知识库页可见 `stage53-alpha-kb`。历史页可见“stage53 alpha hello”和 `stage53-alpha-topic`。
- 第一次恢复后，备份列表停在 `CREATING`，创建按钮被挡住。原因是在线备份快照发生在完成状态写入之前，而备份目录不随包恢复。已在切换后把 `CREATING/RUNNING/QUEUED` 收成 `FAILED`。同一归档再次确认并重启后，页面显示“失败”，创建按钮可点，下载按钮仍禁用（包内没有备份文件本体）。

## 失败与回滚

定向测试覆盖：取消确认、坏包、缺 ContentObject、过新 schema、磁盘空间、无写权限、预检后数据变化、数据库锁、切换中断后重启回滚、迁移失败在改名之前停止。失败后活动库仍可读。Windows 上目录改名在句柄刚释放时可能拒绝访问；短重试后仍失败则按数据库占用回滚，不再把未捕获异常留在启动流程里。

## 门禁

- `pytest tests/test_stage8_backup_restore.py tests/test_stage8_backup_export.py`：13 passed
- `ruff check`（本批涉及路径）通过
- `pyright`（`local_restore.py`、`api/backups.py`、`main.py`）0 errors
- Alembic head：`a50e7c1b9d44`
- OpenAPI 3.1 已导出，前端 `npm run api:generate` 为 103 schemas / 108 operations
- 前端 `typecheck`、`lint`、`stage8-backup-restore` 与 `stage6-provider` Vitest、`npm run build` 通过
- 按备份 ID 的 `POST /api/v1/backups/{id}/restore` 仍返回 `BACKUP_RESTORE_DISABLED`
- 未使用默认个人数据根，未读取真实 Key，未调用真实 DeepSeek

## 下一批

阶段 8 其余项另开对话，一次只做一项。不要把阶段 8 标成完成。
