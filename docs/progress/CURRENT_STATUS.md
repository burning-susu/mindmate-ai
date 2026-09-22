# MindMate AI Current Status

## 基本信息

- 当前开发分支：`feat/v1-bootstrap`
- 当前远程提交：以 `git ls-remote --heads origin feat/v1-bootstrap` 为准；本文件随本批次收口提交推送
- 最后更新时间：`2026-09-22`
- 当前开发阶段：阶段 4 文件管理收口
- 当前批次状态：第六批实现与自动化验证完成，批次结论 `PARTIAL`；阶段 4 仍为 `PARTIAL`，第七批最终验收尚未执行

## 已完成阶段

- 阶段 0：工程基线，`114345c`
- 阶段 1：Windows AI/向量 Spike，`741ba6c`；干净 Windows 和正式安装包仍是发布缺口
- 阶段 2：安全本地应用壳，`0b19795`
- 阶段 3：数据、任务和备份基础，`02a32b8`
- 阶段 4：初始实现 `bc30e1f`，证据修订 `9e0174a`，收口修复 `3b29d22`，第四批交接 `0448d5b`；第五批完成数据模型、迁移、乐观锁、解析失败持久化与契约同步；第六批完成持久解析 Worker、原子领取/租约、重试恢复和 Windows Job Object，阶段结论仍为 `PARTIAL`

## 当前已实现能力

- 后端：5 类文件导入、托管复制、哈希去重、持久解析 Worker、隔离解析、搜索筛选、文件/文件夹/标签、批量操作、受控内容读取、回收站和永久删除；Folder/Tag 修改、删除与恢复使用数据库原子 `row_version` 乐观锁。
- 任务与资源安全：复用 `BackgroundTask` 实现文件导入/重新处理的原子领取、租约、过期恢复、关闭中断和有限重试；Windows 解析子进程使用 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存上限，默认 `512 MiB`，非 Windows 明确走兼容路径。
- 前端：真实 API 文件工作台、嵌套目录、筛选排序、导入与重复决策、详情编辑/预览、文件和文件夹回收站操作；版本冲突提示并引导重新加载，不自动覆盖。
- 数据库：SQLite/Alembic 核心实体、持久任务、内容对象引用计数和软删除字段；revision `9f3a1c7e2b40` 增加 Folder/Tag `row_version` 及 FileRecord 解析失败阶段、错误 ID、重试次数。
- 测试与工程：后端 30 tests、前端 7 tests、Playwright 阶段 4 生命周期、Ruff、Pyright、ESLint/oxlint、TypeScript、Vite build、OpenAPI 生成和空库/已有数据迁移往返。

## 当前已知缺口

- 技术债：文件列表筛选/排序/滚动状态返回后未恢复。
- 发布/验收缺口：正式恶意文档集、资源耗尽发布级验收、干净 Windows 安装包和阶段 4 最终验收留给第七批。
- 后续依赖：批量加入知识库、FTS5、索引、Embedding、向量和 RAG 不在本批次实现。

## 测试状态

- 后端测试：`30 passed`（含第六批 Worker/资源安全专项）
- 阶段 4 后端定向测试：`21 passed`
- 后端静态检查：Ruff 通过；Pyright `0 errors`
- 前端测试：`7 passed`
- 前端类型检查：通过
- 前端构建：通过
- 浏览器 E2E：`1 passed`
- OpenAPI 同步：OpenAPI 3.1，`25 schemas / 38 operations`
- 数据库迁移：revision `9f3a1c7e2b40`；空库和已有数据升级、降级、再升级通过，`quick_check=ok`

## 本批次交接

- 第六批状态：`PARTIAL`（实现和自动化证据完成；不代表阶段 4 最终验收）
- Worker：应用 lifespan 启动单实例进程内 Worker，关闭时停止接单、终止解析子进程并把自有运行任务标为 `INTERRUPTED`。
- 任务：`QUEUED/RUNNING/INTERRUPTED/COMPLETED/FAILED/CANCELLED`；`RUNNING` 使用可配置 60 秒租约，解析失败默认最多 2 次重试；不可重试错误直接最终失败。
- 资源：Windows Job Object 默认进程内存上限 `512 MiB`，启用 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`；创建、配置、分配失败映射为稳定 `PARSER_RESOURCE_LIMIT`，不向前端暴露 Win32 细节。
- API/前端：导入和重新处理返回已持久化的排队状态；新增通用 `GET /api/v1/tasks/{task_id}`；OpenAPI 与生成类型已同步，文件列表/详情对 `QUEUED/PARSING` 自动轮询。

## 下一开发批次

- `第七批：阶段 4 最终验收与状态定版`

## 交接说明

- 新对话必须读取：`AGENTS.md`、`docs/project/requirements/v1/18_最终决策表.md`、`16_Codex开发任务书.md`、`04_文件管理详细需求.md`、本文件、`v1-development-progress.md` 和阶段 4 测试报告。
- 从远程 `origin/feat/v1-bootstrap` 最新提交继续；先核对 `git status --short` 和本地/远程 SHA，不依赖旧对话。
