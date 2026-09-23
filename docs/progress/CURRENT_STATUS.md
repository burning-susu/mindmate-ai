# MindMate AI Current Status

## 基本信息

- 当前开发分支：`feat/v1-bootstrap`
- 当前远程提交：以 `git ls-remote --heads origin feat/v1-bootstrap` 为准；本文件随本批次收口提交推送
- 最后更新时间：`2026-09-23`
- 当前开发阶段：阶段 5 开发中，状态 `PARTIAL`
- 当前批次状态：第十四批“持久 FTS5 Chunk 投影与可恢复构建”结论 `PASS`；阶段 5 状态 `PARTIAL`

## 已完成阶段

- 阶段 0：工程基线，`114345c`
- 阶段 1：Windows AI/向量 Spike，`741ba6c`；干净 Windows 和正式安装包仍是发布缺口
- 阶段 2：安全本地应用壳，`0b19795`
- 阶段 3：数据、任务和备份基础，`02a32b8`
- 阶段 4：初始实现 `bc30e1f`，证据修订 `9e0174a`，收口修复 `3b29d22`，第四批交接 `0448d5b`；第五批完成数据模型、迁移、乐观锁、解析失败持久化与契约同步；第六批完成持久解析 Worker、原子领取/租约、重试恢复和 Windows Job Object；第七批补齐列表状态恢复并完成最终验收，状态 `PASS`
- 阶段 5：第八批完成空知识库持久化基础；第九批完成成员加入/移出、多库共享、批量准入、持久任务、取消/恢复和前端真实状态闭环；第十批完成索引配置、不可变版本输入快照与可恢复预处理 Worker；第十一批完成可复用版本化 Chunk 与独立可恢复切片任务；第十二批完成固定 ONNX 产物来源、哈希验证与本地 CPU Adapter；第十三批完成持久 EmbeddingRecord、单并发 Worker 与 sqlite-vec 向量写入；第十四批完成按 IndexVersion 隔离的持久 FTS5 投影与逐输入恢复；阶段整体仍为 `PARTIAL`

## 当前已实现能力

- 后端：5 类文件导入、托管复制、哈希去重、持久解析 Worker、隔离解析、搜索筛选、文件/文件夹/标签、批量操作、受控内容读取、回收站和永久删除；Folder/Tag 修改、删除与恢复使用数据库原子 `row_version` 乐观锁。
- 任务与资源安全：复用 `BackgroundTask` 实现文件导入/重新处理及知识库成员准入；解析 Worker 与成员 Worker 按任务类型隔离领取，均使用原子领取、租约、过期恢复、关闭中断与取消状态；Windows 解析子进程使用 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存上限，默认 `512 MiB`。
- 前端：真实 API 文件工作台、嵌套目录、筛选排序、导入与重复决策、详情编辑/预览、文件和文件夹回收站操作；列表查询参数、详情返回后的筛选/排序/滚动恢复；返回前刷新列表避免旧 `row_version` 竞态；版本冲突提示并引导重新加载，不自动覆盖。
- 数据库：SQLite/Alembic 核心实体、持久任务、内容对象引用计数和软删除字段；revision `d91f4a6b2c30` 增加 ChunkingConfig、EmbeddingConfig、IndexVersion 与逐文件输入快照；revision `f2c7a1d8e904` 增加文件级 Chunk 与切片检查点；revision `a81f3c6d2e90` 增加 EmbeddingRecord、逐输入 Embedding 检查点及 INDEX_EMBED 单运行租约约束；revision `d60f2e8a7c31` 增加逐输入 FTS 状态、映射表、FTS5 虚表和 INDEX_FTS 单运行租约约束。
- 测试与工程：第十四批后端全量 `105 passed`、Ruff、Pyright、compileall、FTS5 完整性/映射对账、空库及含 Chunk/EmbeddingRecord 数据的迁移回滚与重建回归；前端既有 13 tests 和阶段 4/5 Playwright 生命周期证据见测试状态。
- 知识库：空库创建保持 `EMPTY`；名称/描述/颜色/图标编辑；回收站生命周期；已导入文件批量加入/移出、多库共享、幂等重加与逐项结果；成员准入完成后保持 `index_state=PENDING` 和知识库 `PREPARING`，不伪造可检索状态。
- 索引预处理：独立 `INDEX_PREPROCESS` Worker 在请求生命周期外冻结活动成员、内容哈希、解析修订、配置指纹与集合指纹；逐文件记录 `PREPARED/SKIPPED/FAILED`，支持幂等、租约接管、检查点续跑、取消和完成前版本复核。预处理后 `IndexVersion.status=BUILDING`，不会写入 `active_index_version_id`。
- 版本化切片：独立 `INDEX_CHUNK` Worker 仅消费同版本 `PREPARED` 快照；Chunk 按文件/解析修订/切片配置复用，不与知识库绑定；文件级 Chunk 集、切片检查点和任务进度原子提交，支持取消、租约接管、关闭续跑、显式失败重试、多库复用与旧解析/配置版本共存。完成后仍为 `BUILDING` 且不可检索。
- 结构定位：Chunk 记录有效 Unicode 字符长度而不伪造 tokenizer token；保留解析器实际提供的标题路径、PDF 页、PPTX 幻灯片、TXT/Markdown 行及 DOCX 结构块类型。文件永久删除只清理对应 file_id 的 Chunk。
- 前端成员管理：真实文件选择、批量添加、任务轮询、逐项成功/失败、解析状态、待索引状态与移出；刷新后从数据库恢复成员；导入任务终态会再次刷新文件列表，避免异步完成后的旧缓存。
- 本地 Embedding 模型：固定 BAAI 与 Xenova revisions；显式调用时下载到 `.partial`，校验大小、SHA-256 和配置后原子发布；支持超时、并发、取消/重试和离线缺失。Adapter 只启用 CPU，应用启动不加载 ONNX Runtime；来源与 Windows 对照证据见 `docs/project/index-preprocessing-contract.md`。
- Embedding 配置：新默认配置已保存 BAAI 基础 revision、ONNX revision 与 artifact fingerprint 的复合 `model_revision`；既有 `NULL` 行保留用于历史追溯，没有新增数据库结构。
- 持久 Embedding：独立 `INDEX_EMBED` Worker 仅消费仍有效且已 `CHUNKED` 的版本输入；固定配置、模型与 tokenizer 指纹后懒加载现有本地 ONNX，文件级隔离失败、取消、租约续期和中断恢复；EmbeddingRecord 按 Chunk/EmbeddingConfig 跨库复用，sqlite-vec 物理向量按配置与 IndexVersion 隔离，ID/hash 幂等对账后才提交成功检查点。
- 向量 Adapter：在 Windows 文件 SQLite 中校验 512 维、有限单位向量、持久存在性、hash 对账、幂等 upsert 和按 ID/版本删除；扩展加载权限仅在加载期间开启。永久删除知识库只清理其版本向量，保留仍可复用的 Chunk/EmbeddingRecord；永久删除文件清理其向量映射、记录和 Chunk。
- 持久 FTS5：独立 `INDEX_FTS` Worker 只消费同版本有效的 `PREPARED + CHUNKED` 输入；以 `IndexVersion + Chunk` 映射隔离，逐文件 FTS5 行、映射、输入检查点和任务进度在同一主 SQLite 事务提交。支持租约接管、取消、幂等重建和显式失败重试，不修改 Chunk/Embedding 权威数据，也不激活版本。
- 中文关键词投影：FTS5 仍使用 `unicode61` 和 BM25；中文按连续汉字生成重叠二元词及单字辅助列，支持中文短查询；拉丁词项大小写折叠。没有接入公开 MATCH API、向量 Top-K、RRF 或前端搜索。

## 当前已知缺口

- 阶段 4 无未解决功能、安全、数据一致性或迁移阻塞项；需求追踪详见 `docs/test-reports/stage-4-file-management.md`。
- 发布候选保留：正式恶意文档集、真实资源耗尽边界、干净 Windows 安装/升级/卸载包，依据发布流程执行，不回填为阶段 4 已完成证据。
- 阶段 5 缺口：向量 Top-K 查询、增量/原子索引激活、混合检索、引用和 RAG 尚未实现；虽然 FTS5 投影已建立，本批未开放检索，Embedding 与 FTS 完成均不会使知识库可检索。

## 测试状态

- 后端测试：`105 passed`（含第十四批 FTS 中文/英文 MATCH 与 BM25、版本隔离、映射损坏重建、逐项失败重试、取消/租约接管、逐输入进度、成员移除/回收站/永久清理、多知识库共享，以及前批 Embedding/向量、解析和文件生命周期回归）
- 阶段 4 后端定向测试：`21 passed`
- 后端静态检查：Ruff 通过；Pyright `0 errors`
- 后端 compileall：通过
- 前端测试：`13 passed`
- 前端类型检查：通过
- 前端构建：通过
- 浏览器 E2E：阶段 4 文件回归与阶段 5 知识库共 `2 passed`（各 1 项），由隔离 SQLite、真实本地 FastAPI + Vite 代理运行
- OpenAPI 同步：OpenAPI 3.1，`34 schemas / 50 operations`；任务详情包含 `task_type` 和 `index_version_id`
- 数据库迁移：最新 revision `d60f2e8a7c31`；空库及既有 Chunk/EmbeddingRecord 数据升级通过；降级到 `a81f3c6d2e90` 仅移除可重建的 FTS 投影，再升级后可从 Chunk 重建；`PRAGMA quick_check=ok`

## 第十三批交接

- 本批状态：`PASS`；阶段 5 仍为 `PARTIAL`。
- 数据：Alembic `a81f3c6d2e90` 新增 `EmbeddingRecord` 与 `IndexVersionInput.embedding_status/embedding_reason_code/embedding_count/embedded_at`；每个记录保存稳定 Chunk/配置映射、配置指纹、向量记录 ID、SHA-256、状态和失效时间，不把原始向量写入业务表。
- Worker：新增独立 `INDEX_EMBED`，SQLite 部分唯一索引和原子租约将运行并发限制为 1；只消费 `PREPARED + CHUNKED` 输入，批量最多 16，按文件持久检查点；校验成员、回收站、内容哈希、解析修订、切片/Embedding 配置及模型/tokenizer 固定指纹。
- 一致性：先持久化预期向量 hash，再对配置/IndexVersion 隔离的 sqlite-vec 文件数据库做 ID 幂等 upsert，最后在事务中提交 `EmbeddingRecord.READY` 和输入检查点；重启可双向校验数据库映射与实际向量并恢复写后中断。逐文件失败可重试，取消/失效输入不发布成功状态。
- 复用与清理：共享 Chunk + EmbeddingConfig 的多个知识库不重复推理，但各 IndexVersion 分别持久化向量；删除一个知识库只删除其版本向量空间并保留共享记录，永久删除文件先清理其相关版本向量和 EmbeddingRecord 再删除 Chunk。
- 实际模型证据：读取并校验 Git 忽略的 `backend/model-cache/manager-validation` 固定 manifest 缓存为 `READY`，无网络、无下载地由本地 ONNX Worker 处理固定离线文件；实际持久输出为 512 维、有限且 L2 单位范数。缓存没有加入 Git 或被清理。
- 验收：后端全量 `97 passed`；Ruff、Pyright `0 errors`、compileall、离线 uv lock 校验通过；真实 FastAPI/Vite 阶段 4/5 Playwright `2 passed`；迁移往返与 SQLite `quick_check=ok`。任务完成后 `IndexVersion.status=BUILDING`、`active_index_version_id` 未变，`available_for_retrieval=false`。
- API/OpenAPI：没有增加路由或 schema，复用已有任务详情/取消契约（`34 schemas / 50 operations`）；无前端改动，不调用真实 Provider。

## 第十四批交接

- 本批状态：`PASS`；阶段 5 仍为 `PARTIAL`，知识库与 IndexVersion 均不可检索。
- 数据：Alembic `d60f2e8a7c31` 增加 `IndexVersion.fts_status`、`IndexVersionInput.fts_status/fts_reason_code/fts_count/fts_indexed_at`、按版本/文件/Chunk/解析修订/切片配置/内容哈希映射的 `fts_chunk_map`，以及 FTS5 虚表 `index_chunk_fts`；数据库部分唯一索引限制至多一个 `INDEX_FTS/RUNNING` 任务。
- Worker：新增独立持久 `INDEX_FTS`。只处理仍有效的 `PREPARED + CHUNKED` 输入；任务租约过期接管、应用关闭续跑、取消、逐文件失败与显式重试均保留检查点。每文件的虚表行、映射、输入状态和任务 JSON 检查点在同一业务 SQLite 事务提交。
- 投影：每个 FTS 行通过 `index_version_id + chunk_id` 唯一隔离并回溯文件、解析修订、切片配置和正文哈希；新 IndexVersion 不清空旧版本。基于 Chunk 可重建投影，映射对账与 FTS5 `integrity-check` 可分辨投影缺失/不一致与虚表内部损坏。
- 分词与生命周期：使用 `unicode61 remove_diacritics 2`；连续汉字建立重叠二元词和单字列，固定中文短查询及英文词样本通过。软删除/移出查询内部校验当前成员、回收站、内容哈希、解析修订和 FTS 状态。知识库永久删除只清其版本投影；文件永久删除清该文件的投影/输入并使仍有其他输入的未激活版本进入 `NEEDS_REBUILD`，保留其余文件 Chunk 与 FTS 映射。
- 迁移回退：降级只删除 FTS 虚表、映射及 FTS 检查点列；Chunk、EmbeddingRecord 和向量数据不删。再升级后 FTS 投影为空，可由 `INDEX_FTS` 的重建任务从 Chunk 恢复。
- 边界：不实现公开检索 API、向量 Top-K、RRF、混合检索、索引激活、引用、RAG、UI 或 API schema；OpenAPI 仍为 `34 schemas / 50 operations`，Provider 仍 Mock-only。
- 验收：后端 `105 passed`；Ruff、Pyright `0 errors`、compileall 通过。迁移空库/既有数据、允许范围内降级/再升级、SQLite quick/integrity/投影对账通过；第十四批不改变前端。

## 下一开发批次

- 阶段 5 下一个唯一目标：增加同一 `IndexVersion` 的内部 sqlite-vec Top-K 查询与版本/成员过滤测试；不激活索引、不开放 RAG。

## 交接说明

- 新对话必须读取：`AGENTS.md`、`docs/project/requirements/v1/18_最终决策表.md`、`16_Codex开发任务书.md`、`05_知识库与RAG详细需求.md`、本文件、`v1-development-progress.md` 和阶段 5 测试报告。
- 从远程 `origin/feat/v1-bootstrap` 最新提交继续；先核对 `git status --short` 和本地/远程 SHA，不依赖旧对话。
