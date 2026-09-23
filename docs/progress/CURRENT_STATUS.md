# MindMate AI Current Status

## 基本信息

- 当前开发分支：`feat/v1-bootstrap`
- 当前远程提交：以 `git ls-remote --heads origin feat/v1-bootstrap` 为准；本文件随本批次收口提交推送
- 最后更新时间：`2026-09-23`
- 当前开发阶段：阶段 5 开发中，状态 `PARTIAL`
- 当前批次状态：第十批“索引模型、迁移与可恢复预处理”结论 `PASS`；阶段 5 状态 `PARTIAL`

## 已完成阶段

- 阶段 0：工程基线，`114345c`
- 阶段 1：Windows AI/向量 Spike，`741ba6c`；干净 Windows 和正式安装包仍是发布缺口
- 阶段 2：安全本地应用壳，`0b19795`
- 阶段 3：数据、任务和备份基础，`02a32b8`
- 阶段 4：初始实现 `bc30e1f`，证据修订 `9e0174a`，收口修复 `3b29d22`，第四批交接 `0448d5b`；第五批完成数据模型、迁移、乐观锁、解析失败持久化与契约同步；第六批完成持久解析 Worker、原子领取/租约、重试恢复和 Windows Job Object；第七批补齐列表状态恢复并完成最终验收，状态 `PASS`
- 阶段 5：第八批完成空知识库持久化基础；第九批完成成员加入/移出、多库共享、批量准入、持久任务、取消/恢复和前端真实状态闭环；第十批完成索引配置、不可变版本输入快照与可恢复预处理 Worker；阶段整体仍为 `PARTIAL`

## 当前已实现能力

- 后端：5 类文件导入、托管复制、哈希去重、持久解析 Worker、隔离解析、搜索筛选、文件/文件夹/标签、批量操作、受控内容读取、回收站和永久删除；Folder/Tag 修改、删除与恢复使用数据库原子 `row_version` 乐观锁。
- 任务与资源安全：复用 `BackgroundTask` 实现文件导入/重新处理及知识库成员准入；解析 Worker 与成员 Worker 按任务类型隔离领取，均使用原子领取、租约、过期恢复、关闭中断与取消状态；Windows 解析子进程使用 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存上限，默认 `512 MiB`。
- 前端：真实 API 文件工作台、嵌套目录、筛选排序、导入与重复决策、详情编辑/预览、文件和文件夹回收站操作；列表查询参数、详情返回后的筛选/排序/滚动恢复；返回前刷新列表避免旧 `row_version` 竞态；版本冲突提示并引导重新加载，不自动覆盖。
- 数据库：SQLite/Alembic 核心实体、持久任务、内容对象引用计数和软删除字段；revision `d91f4a6b2c30` 增加字符单位的 ChunkingConfig、本地 ONNX EmbeddingConfig、IndexVersion 与逐文件输入快照，默认配置以 SHA-256 指纹去重。
- 测试与工程：后端 50 tests、前端 13 tests、阶段 4/5 Playwright 生命周期、Ruff、Pyright、ESLint/oxlint、TypeScript、Vite build、OpenAPI 生成和迁移回归。
- 知识库：空库创建保持 `EMPTY`；名称/描述/颜色/图标编辑；回收站生命周期；已导入文件批量加入/移出、多库共享、幂等重加与逐项结果；成员准入完成后保持 `index_state=PENDING` 和知识库 `PREPARING`，不伪造可检索状态。
- 索引预处理：独立 `INDEX_PREPROCESS` Worker 在请求生命周期外冻结活动成员、内容哈希、解析修订、配置指纹与集合指纹；逐文件记录 `PREPARED/SKIPPED/FAILED`，支持幂等、租约接管、检查点续跑、取消和完成前版本复核。预处理后 `IndexVersion.status=BUILDING`，不会写入 `active_index_version_id`。
- 前端成员管理：真实文件选择、批量添加、任务轮询、逐项成功/失败、解析状态、待索引状态与移出；刷新后从数据库恢复成员；导入任务终态会再次刷新文件列表，避免异步完成后的旧缓存。

## 当前已知缺口

- 阶段 4 无未解决功能、安全、数据一致性或迁移阻塞项；需求追踪详见 `docs/test-reports/stage-4-file-management.md`。
- 发布候选保留：正式恶意文档集、真实资源耗尽边界、干净 Windows 安装/升级/卸载包，依据发布流程执行，不回填为阶段 4 已完成证据。
- 阶段 5 缺口：正式 Chunk 生成与持久化、模型下载、ONNX Embedding、FTS5、sqlite-vec、增量/原子索引激活、混合检索、引用和 RAG 尚未实现；成员均不可检索。

## 测试状态

- 后端测试：`50 passed`（含配置单位/指纹、空库及第九批数据库迁移、输入混合结果、成员/解析竞态、幂等、取消、租约过期接管、永久删除清理与 Worker 类型隔离）
- 阶段 4 后端定向测试：`21 passed`
- 后端静态检查：Ruff 通过；Pyright `0 errors`
- 前端测试：`13 passed`
- 前端类型检查：通过
- 前端构建：通过
- 浏览器 E2E：阶段 5 知识库 `1 passed`；阶段 4 文件回归 `1 passed`
- OpenAPI 同步：OpenAPI 3.1，`33 schemas / 50 operations`
- 数据库迁移：revision `d91f4a6b2c30`；空库、早期数据和第九批知识库/成员/任务升级，允许的降级/再升级通过，`quick_check=ok`

## 本批次交接

- 第十批状态：`PASS`；阶段 5 仍为 `PARTIAL`。
- 数据：Alembic `d91f4a6b2c30` 新增 `chunking_configs`、`embedding_configs`、`index_versions`、`index_version_inputs`；500/80 的单位明确为 Unicode 字符，不沿用旧 `target_tokens` 含义；Embedding 只保存 512 维本地 ONNX 元数据，未下载模型。
- 任务语义：`INDEX_PREPROCESS` 的 `COMPLETED` 只表示输入、配置和逐项检查点已持久化；`summary.index_ready=false`，索引版本保持 `BUILDING`，知识库及成员仍不可检索。
- Worker：按独立任务类型原子领取，支持租约续期/过期接管、检查点续跑、取消、幂等和多 Worker 类型隔离；完成前再次校验成员、回收站、内容哈希和解析修订，旧任务不发布过期输入。
- 契约：没有新增 `/rebuild` 或 `index-status` API，OpenAPI 仍为 `33 schemas / 50 operations`；后续构建输入见 `docs/project/index-preprocessing-contract.md`。

## 下一开发批次

- 阶段 5 下一个单一最小闭环：基于 `PREPARED` 快照生成并持久化版本化 Chunk，支持取消/恢复和失效校验；仍不实现 ONNX、FTS、向量或检索。

## 交接说明

- 新对话必须读取：`AGENTS.md`、`docs/project/requirements/v1/18_最终决策表.md`、`16_Codex开发任务书.md`、`05_知识库与RAG详细需求.md`、本文件、`v1-development-progress.md` 和阶段 5 测试报告。
- 从远程 `origin/feat/v1-bootstrap` 最新提交继续；先核对 `git status --short` 和本地/远程 SHA，不依赖旧对话。
