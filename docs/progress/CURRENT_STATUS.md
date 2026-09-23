# MindMate AI Current Status

## 基本信息

- 当前开发分支：`feat/v1-bootstrap`
- 当前远程提交：以 `git ls-remote --heads origin feat/v1-bootstrap` 为准；本文件随本批次收口提交推送
- 最后更新时间：`2026-09-23`
- 当前开发阶段：阶段 5 开发中，状态 `PARTIAL`
- 当前批次状态：第九批“知识库成员与持久准入任务闭环”结论 `PASS`；阶段 5 状态 `PARTIAL`

## 已完成阶段

- 阶段 0：工程基线，`114345c`
- 阶段 1：Windows AI/向量 Spike，`741ba6c`；干净 Windows 和正式安装包仍是发布缺口
- 阶段 2：安全本地应用壳，`0b19795`
- 阶段 3：数据、任务和备份基础，`02a32b8`
- 阶段 4：初始实现 `bc30e1f`，证据修订 `9e0174a`，收口修复 `3b29d22`，第四批交接 `0448d5b`；第五批完成数据模型、迁移、乐观锁、解析失败持久化与契约同步；第六批完成持久解析 Worker、原子领取/租约、重试恢复和 Windows Job Object；第七批补齐列表状态恢复并完成最终验收，状态 `PASS`
- 阶段 5：第八批完成空知识库持久化基础；第九批完成成员加入/移出、多库共享、批量准入、持久任务、取消/恢复和前端真实状态闭环；阶段整体仍为 `PARTIAL`

## 当前已实现能力

- 后端：5 类文件导入、托管复制、哈希去重、持久解析 Worker、隔离解析、搜索筛选、文件/文件夹/标签、批量操作、受控内容读取、回收站和永久删除；Folder/Tag 修改、删除与恢复使用数据库原子 `row_version` 乐观锁。
- 任务与资源安全：复用 `BackgroundTask` 实现文件导入/重新处理及知识库成员准入；解析 Worker 与成员 Worker 按任务类型隔离领取，均使用原子领取、租约、过期恢复、关闭中断与取消状态；Windows 解析子进程使用 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存上限，默认 `512 MiB`。
- 前端：真实 API 文件工作台、嵌套目录、筛选排序、导入与重复决策、详情编辑/预览、文件和文件夹回收站操作；列表查询参数、详情返回后的筛选/排序/滚动恢复；返回前刷新列表避免旧 `row_version` 竞态；版本冲突提示并引导重新加载，不自动覆盖。
- 数据库：SQLite/Alembic 核心实体、持久任务、内容对象引用计数和软删除字段；revision `9f3a1c7e2b40` 增加 Folder/Tag `row_version` 及 FileRecord 解析失败阶段、错误 ID、重试次数。
- 测试与工程：后端 42 tests、前端 13 tests、阶段 4/5 Playwright 生命周期、Ruff、Pyright、ESLint/oxlint、TypeScript、Vite build、OpenAPI 生成和迁移回归。
- 知识库：空库创建保持 `EMPTY`；名称/描述/颜色/图标编辑；回收站生命周期；已导入文件批量加入/移出、多库共享、幂等重加与逐项结果；成员准入完成后保持 `index_state=PENDING` 和知识库 `PREPARING`，不伪造可检索状态。
- 前端成员管理：真实文件选择、批量添加、任务轮询、逐项成功/失败、解析状态、待索引状态与移出；刷新后从数据库恢复成员；导入任务终态会再次刷新文件列表，避免异步完成后的旧缓存。

## 当前已知缺口

- 阶段 4 无未解决功能、安全、数据一致性或迁移阻塞项；需求追踪详见 `docs/test-reports/stage-4-file-management.md`。
- 发布候选保留：正式恶意文档集、真实资源耗尽边界、干净 Windows 安装/升级/卸载包，依据发布流程执行，不回填为阶段 4 已完成证据。
- 阶段 5 缺口：ChunkingConfig、EmbeddingConfig、IndexVersion、模型下载、ONNX Embedding、FTS5、sqlite-vec、增量/原子索引、混合检索、引用和 RAG 尚未实现；成员均不可检索。

## 测试状态

- 后端测试：`42 passed`（含成员混合批次、多库共享、幂等、移出重加、取消竞态和 Worker 类型隔离）
- 阶段 4 后端定向测试：`21 passed`
- 后端静态检查：Ruff 通过；Pyright `0 errors`
- 前端测试：`13 passed`
- 前端类型检查：通过
- 前端构建：通过
- 浏览器 E2E：阶段 5 知识库 `1 passed`；阶段 4 文件回归 `1 passed`
- OpenAPI 同步：OpenAPI 3.1，`33 schemas / 50 operations`
- 数据库迁移：revision `c7d5e8a1f204`；空库和已有数据升级、降级、再升级通过，`quick_check=ok`

## 本批次交接

- 第九批状态：`PASS`；阶段 5 仍为 `PARTIAL`。
- API：新增知识库成员列表、`202` 批量添加、移出、文件所属知识库查询及成员任务取消；逐项结果区分不存在、回收站、内容不可用、解析中/失败和已加入。
- 父任务语义：`COMPLETED` 只表示成员准入与关系持久化完成；响应、检查点和前端均明确“索引仍待建立”，成员 `index_state=PENDING`，知识库不进入 `READY`。
- Worker：独立 `KNOWLEDGE_MEMBERSHIP_ADD` Worker 按类型领取，保存成员/文件请求时间和逐项结果；租约过期可重新领取，关闭时转 `INTERRUPTED`，取消不会被最终完成覆盖。
- 数据：未新增迁移；现有唯一关系通过墓碑状态实现幂等、移出重加和多库共享，不复制文件或解析内容。

## 下一开发批次

- 阶段 5 下一个最小闭环：建立 ChunkingConfig/EmbeddingConfig/IndexVersion 与可恢复的索引构建任务骨架，仍不提前进入完整 RAG。

## 交接说明

- 新对话必须读取：`AGENTS.md`、`docs/project/requirements/v1/18_最终决策表.md`、`16_Codex开发任务书.md`、`05_知识库与RAG详细需求.md`、本文件、`v1-development-progress.md` 和阶段 5 测试报告。
- 从远程 `origin/feat/v1-bootstrap` 最新提交继续；先核对 `git status --short` 和本地/远程 SHA，不依赖旧对话。
