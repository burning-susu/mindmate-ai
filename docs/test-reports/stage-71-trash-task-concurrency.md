# 第七十一批：阶段 8 回收站任务联动与并发配置

- 日期：2026-09-29
- 分支：`feat/v1-bootstrap`
- 进场本地/远端 SHA：`cea45860111391444120c8403a1b49a4e6b1a822` / `cea45860111391444120c8403a1b49a4e6b1a822`
- 进场工作区：干净
- 本批范围：`TASK-AC-12` 回收站目标与持久任务联动；`TASK-AC-05` 可下调的重任务/Embedding 并发上限
- 明确不在本批：学习完成总结、普通 Chrome/Edge 页面走查、真实 DeepSeek/OpenAI 请求、官方账单对账、日志外部 stdout/stderr 收口

## 结论

| 门禁 | 状态 | 证据范围 |
| --- | --- | --- |
| `TASK-AC-05` 代码与自动化 | `CODE_PASS` | 本地 `AppSetting` 配置、GET/PUT API、数据库领取边界、两个独立进程争抢、重启后重新读取；默认 `2/1`，可降为 `1/1` |
| `TASK-AC-12` 代码与自动化 | `CODE_PASS` | 文件、文件夹、知识库软删除与目标任务匹配；排队/运行任务取消原因、解析子进程安全点、索引输入/共享引用回归 |
| `TASK-AC-05` 普通浏览器 | `BROWSER_PARTIAL` | 当前会话没有可操作的普通 Chrome/Edge 标签页；没有页面截图或 Network 计数 |
| `TASK-AC-12` 普通浏览器 | `BROWSER_PARTIAL` | 当前会话没有可操作的普通 Chrome/Edge 标签页；没有页面回收站点击证据 |
| `STAGE8_FULL_V1` | `PARTIAL` | 本批只收口两个后端/配置缺口；学习总结、浏览器验收及其他阶段 8 遗留项继续保持原状态 |
| 求职 Demo 可用性 | `PASS`（沿用） | 沿用第四十二/六十四批证据，本批没有重跑整条 Demo |
| 完整 V1 阶段 5–7 | `PARTIAL` | 不因本批自动化通过而改变 |

## 最小影响表

| 目标/关系 | 任务类型 | 是否确实依赖目标 | 进入回收站后的处理 | 仍需保留的对象 |
| --- | --- | --- | --- | --- |
| 单文件 | `FILE_IMPORT`、`FILE_REPROCESS` | 任务上下文或条目包含该文件 | 同一事务写入 `cancel_requested_at`、`cancel_reason_code`，排队任务立即 `CANCELLED`；运行解析任务由取消监视器触发安全点 | 已复制的原文件、历史记录和旧已发布索引不删除 |
| 单文件被多个知识库引用 | 索引阶段 `INDEX_PREPROCESS/INDEX_CHUNK/INDEX_EMBED/INDEX_FTS` | 通过 `IndexVersionInput.file_id` 精确匹配 | 只取消包含失效输入的新索引版本；不删除其它知识库的旧 READY 索引、共享 Chunk 或 Embedding 产物 | 其它知识库的业务关系和已有可读索引 |
| 文件夹 `MOVE_CHILDREN` | 文件夹目标任务 | 仅导入任务的 `context.folder_id` 依赖已删除文件夹 | 取消指向已删除文件夹的导入目标；文件和子文件夹已搬到有效上级目录，不取消其解析/索引任务 | 搬移后的文件、子文件夹及其任务 |
| 文件夹 `TRASH_RECURSIVE` | 文件任务、索引阶段任务 | 递归文件 ID 或索引版本输入命中目标 | 递归文件进入回收站，同时取消真正依赖这些输入的任务；混合批任务只要仍有有效条目就不整批取消 | 不相关文件、共享旧索引、备份和恢复数据 |
| 知识库 | `KNOWLEDGE_MEMBERSHIP_ADD`、四个索引阶段 | 任务 checkpoint 的知识库 ID 或索引版本 scope 命中 | 同一软删除事务取消该知识库未完成任务；索引激活已有回收站复核，不发布失效版本 | 原始文件、其它知识库关系、共享文件级 Embedding |
| 成员关系批任务 | `KNOWLEDGE_MEMBERSHIP_ADD` | 每个条目的文件 ID 单独判断 | 混合有效/失效文件的批任务保留，Worker 逐项处理；全部条目失效时才取消父任务 | 其它有效成员项 |
| AI 付费请求、备份、恢复 | `AiOperation`、`BACKUP_CREATE`、恢复执行 | 不属于文件/知识库后台任务依赖 | 不因回收站联动取消，不触发外部 Provider 请求或备份删除 | Provider 操作、备份归档、恢复点 |

## 实现

### 回收站与任务原子联动

- `BackgroundTask` 新增 `cancel_requested_at`、`cancel_reason_code`，迁移为 `g1a2b3c4d5e6`。
- `cancel_tasks_for_targets()` 在文件、文件夹、知识库软删除事务内查询持久 checkpoint、索引版本 scope 和 `IndexVersionInput`，只取消真正命中的任务。
- 运行任务会记录 `CANCEL_REQUESTED`/`CANCELLED` 事件并结束当前 Attempt；任务列表和首页任务投影暴露脱敏 `cancel_reason_code`。
- 解析 Worker 为每个任务建立数据库取消监视器，将回收站取消传递给解析子进程；解析结果发布前仍复核任务状态、文件删除状态、内容状态和哈希。
- 恢复接口没有重放取消任务；`MOVE_CHILDREN` 不把搬移后的文件当作失效输入。索引激活路径继续复核知识库回收站状态和输入快照。

### 可下调并发

- 新增持久配置键 `tasks.concurrency`，默认重任务 `2`、向量写 `1`；有效范围只允许 `heavy_task_limit=1..2`、`vector_write_limit=1`。
- 新增 `GET/PUT /api/v1/system/task-concurrency`，返回默认值、当前生效值、来源和脱敏错误码；无效持久行 fail-closed 到 `1/1`，不会默默提高上限。
- 所有解析、成员、预处理、切片、Embedding、FTS、模型安装 Worker 领取时使用统一数据库并发条件；Embedding 同时受 `HEAVY` 与 `VECTOR_WRITE` 两组限制。
- 备份 Worker 保持原有独占约束，聊天/学习 Provider 请求不进入重任务计数。限制降低后不强杀已领取任务，后续领取在安全点等待。

## 自动化证据

- 阶段 71：`backend/tests/test_stage71_trash_task_concurrency.py`，`7 passed`。覆盖目标任务范围、索引输入匹配、混合批任务保留、默认 `2/1`、持久 `1/1`、Embedding Worker 领取、配置 API、非法值 fail-closed，以及两个独立进程争抢同一重任务。
- 受影响组合：`test_tasks_backups.py`、`test_stage6_parser_worker.py`、`test_stage5_index_preprocessing.py`、`test_stage5_embedding_worker.py`、`test_stage5_fts_worker.py`、`test_stage5_knowledge_bases.py`、阶段 5 Chunking 回收站竞态、`test_stage4_migration.py`，隔离 basetemp 下通过。
- 前端：Vitest `16 files / 78 tests passed`；TypeScript typecheck、ESLint/oxlint、production build 通过。构建保留既有主 chunk 超过 500 kB 的提示。
- 后端静态与契约：Ruff（受影响源码/测试，另有全量 `src tests scripts` 门禁记录）、compileall、OpenAPI 3.1 导出和生成类型同步、`git diff --check` 通过。OpenAPI 当前为 `113 schemas / 122 operations`。
- Alembic：head 为 `g1a2b3c4d5e6`；隔离空库升级、回退、重升级测试通过。没有操作默认用户数据库；默认数据库的现场 current 曾是旧 revision，未被本批迁移命令修改。

## 全量组合边界

本批另外亲跑了带 `PYTHONPATH=backend;backend/src` 的全后端集合，组合结果没有作为本批通过证据：仍有宿主 PowerShell 输出的 Windows `gbk` 解码失败、Windows Credential Manager 可用性、阶段 54 OpenAI Provider/budget 既有失败、Windows 目录句柄恢复竞态和 FTS5 checksum 波动。上述失败不影响本批定向组合；没有为此扩大 Provider、备份恢复或日志范围。

## 浏览器与费用边界

当前会话没有普通 Chrome/Edge 可绑定标签页；没有重试历史审批失败、没有 Playwright 绕过、没有截图/页面 URL/Network 计数。因此 `TASK-AC-05`、`TASK-AC-12` 的浏览器行保持 `BROWSER_PARTIAL`。本批没有使用真实 Key、没有访问 DeepSeek/OpenAI、没有产生付费调用。

## 交接

- 第七十二批目标：学习会话完成总结的持久化、展示和历史检索定位。
- 阶段 8 仍不得写成 `PASS`；下一批继续把 Demo 可用性与完整 V1 阶段状态分开记录。
