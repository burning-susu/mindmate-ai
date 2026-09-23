# 阶段 5：知识库基础与成员准入测试报告

> 阶段：`5`
> 批次：`第八批 + 第九批 + 第十批 + 第十一批 + 第十二批 + 第十三批 + 第十四批`
> 验证日期：`2026-09-23`
> 第八批结论：`PASS`
> 第九批结论：`PASS`
> 第十批结论：`PASS`
> 第十一批结论：`PASS`
> 第十二批结论：`PASS`
> 第十三批结论：`PASS`
> 第十四批结论：`PASS`
> 阶段 5 状态：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 起始提交：`75a0653877b7f627bc254a859232689c19872777`
> 第九批起始提交：`6fd248978b84bcf96702eda081ed05469dab4bf2`
> 第十批起始提交：`3025a5abc2a89cca97edd9cadfbeb87bccdc985f`
> 第十一批起始提交：`59101d692db842a68496ff88219e40c7f0307afe`
> 第十二批起始提交：`b11fb76dec5de5581ec0e95594f577fd2d6310cd`
> Provider：`MOCK_ONLY`
> 真实 DeepSeek/付费 Provider 请求：`DISABLED`

## 结论

第八批“空知识库创建、编辑、列表、详情、回收站与恢复”闭环通过；第九批“已导入文件批量加入/移出知识库、持久成员准入任务和前端真实状态”闭环通过；第十批“索引配置、迁移与可恢复输入预处理”闭环通过；第十一批“结构优先版本化 Chunk 与可恢复切片”闭环通过；第十二批“可信固定 ONNX 产物获取、校验与独立 CPU Embedding Adapter”通过；第十三批“持久 EmbeddingRecord、单并发可恢复 Worker 与真实 sqlite-vec 向量写入”通过；第十四批“按 IndexVersion 隔离的持久 FTS5 Chunk 投影与可恢复构建”通过。空库保持 `EMPTY`；Embedding 与 FTS 生成完成的版本仍为 `BUILDING`，没有激活，不可检索。

第十批 `INDEX_PREPROCESS` 的 `COMPLETED` 只证明输入快照、配置指纹与逐项预处理结果已持久化。第十一批 `INDEX_CHUNK` 的 `COMPLETED` 只表示切片阶段结束。第十三批 `INDEX_EMBED` 的 `COMPLETED` 只表示向量与 `EmbeddingRecord` 已生成并持久化。第十四批 `INDEX_FTS` 的 `COMPLETED` 只表示 FTS5 投影已建立。以上都不表示索引就绪；`IndexVersion.status` 保持 `BUILDING`，`active_index_version_id` 不变，成员仍不可检索。阶段 5 仍为 `PARTIAL`：向量 Top-K 查询、原子索引激活、混合检索、引用和 RAG 尚未实现。

## 实现范围

- 新增 `GET/POST /api/v1/knowledge-bases` 与 `GET/PATCH/DELETE /api/v1/knowledge-bases/{id}`。
- 新增 `GET /api/v1/trash/knowledge-bases`、`POST /api/v1/trash/knowledge-base/{id}/restore` 与 `DELETE /api/v1/trash/knowledge-base/{id}`。
- 创建、列表和详情使用 SQLite 持久化；创建空知识库的状态固定为 `EMPTY`。
- 名称支持 1～100 字符；描述最多 2000 字符；同名允许但响应提供 `duplicate_name` 提示。
- 编辑名称、描述、图标与颜色；颜色只接受 `#RRGGBB`。
- 编辑、删除和恢复通过单条带 `row_version` 条件的 SQL 原子更新；冲突返回 `412 RESOURCE_VERSION_CONFLICT`。
- 移入回收站后正常列表和详情不可见，`purge_after` 为 30 天；恢复空库回到 `EMPTY`，存在成员时进入 `NEEDS_REBUILD`，不伪造旧索引有效。
- 永久删除知识库会删除成员关系，但不会删除 File、ContentObject 或托管原始文件。
- Alembic revision `c7d5e8a1f204` 为既有 `knowledge_bases` 表增加 `icon`、`color`，未重复建表。
- 前端新增 `/knowledge-bases`、`/knowledge-bases/new`、`/knowledge-bases/:id`，并在 `/trash` 接入知识库恢复和永久删除。
- 新增 `GET/POST /api/v1/knowledge-bases/{id}/files`、`DELETE /api/v1/knowledge-bases/{id}/files/{file_id}` 与 `GET /api/v1/files/{file_id}/knowledge-bases`。
- 批量添加返回 `202 + task_id`；任务逐项验证不存在、回收站、内容不可用和当前解析状态，单项失败不阻断其他文件。
- 新增独立 `KNOWLEDGE_MEMBERSHIP_ADD` Worker；任务类型过滤避免解析 Worker 误领，支持原子领取、租约过期重领、检查点、关闭中断与取消。
- 同一文件可加入多个知识库；重复提交幂等；移出保留 `REMOVED` 墓碑，重加恢复为 `ACTIVE/PENDING`；不复制原始文件或解析内容。
- 移出后立即不在成员列表与未来检索范围内；请求时间与移除时间防止旧任务在移出后复活成员。
- 前端接入真实文件选择、批量添加、任务轮询、逐项结果、成员状态与移出；刷新后从数据库恢复，明确显示解析失败/处理中、待索引和不可检索。
- 导入任务进入终态时再次失效文件列表，避免 Worker 完成后继续显示导入前缓存。
- 第九批没有数据库结构变化，当时继续使用 Alembic revision `c7d5e8a1f204`；OpenAPI 3.1 与前端生成类型同步为 `33 schemas / 50 operations`。
- 第十批 Alembic revision `d91f4a6b2c30` 新增 `ChunkingConfig`、`EmbeddingConfig`、`IndexVersion` 和逐文件 `IndexVersionInput`；默认切片参数为约 500/80 Unicode 字符，避免把旧 `target_tokens` 字段名误当最终单位。
- 第十批默认 Embedding 配置当时保持未验证；第十二批真实模型及 tokenizer 校验通过后，新默认配置保存复合 revision 与产物 fingerprint，历史 `NULL` 配置行保留。
- 独立 `INDEX_PREPROCESS` Worker 冻结活动成员、内容哈希、解析修订、成员加入时间、配置指纹与集合指纹；逐项结果为 `PREPARED/SKIPPED/FAILED`，支持租约过期接管、检查点续跑、取消和幂等。
- 成员移出/重加、文件回收站、内容哈希或解析修订变化会产生稳定原因码；完成前二次校验，旧任务不会激活关系或发布过期可构建输入。
- 本批未开放 `/rebuild` 或 `index-status`，没有 API schema 变化；知识库永久删除会先清理对应预处理快照，但不删除原始文件。
- 第十一批 Alembic revision `f2c7a1d8e904` 新增文件级 `chunks` 与 `IndexVersionInput` 切片检查点字段；Chunk 唯一版本由 `file_id + parse_revision_id + chunking_config_id + sequence_number` 确定，不绑定知识库，多库按文件版本与配置复用。
- 结构优先切片按 Unicode 字符计数，默认目标约 500、重叠约 80；标题路径、页、幻灯片、行和 DOCX 结构类型仅来自解析产物或可由原始 TXT/Markdown 正文精确确定的信息。`token_count` 保持 `NULL`，不把字符数伪装为 tokenizer token。
- 新增独立 `INDEX_CHUNK` Worker；Chunk 全集、单文件检查点和任务进度在同一事务提交。任务支持租约过期接管、进程关闭续跑、取消、幂等复用和显式失败重试；成员移出/重加、文件回收站、永久删除、哈希/解析修订或配置变化不会发布陈旧输入。
- 文件或递归文件夹永久删除时只清理对应逻辑文件的 Chunk。文件在切片计算期间永久删除会让任务以稳定错误终止并释放租约；不会删除其他文件或其他知识库仍可复用的 Chunk。
- `GET /api/v1/tasks/{task_id}` 增加正式响应契约字段 `task_type`、`index_version_id`；OpenAPI 3.1 和前端生成类型同步为 `34 schemas / 50 operations`。
- `/api/v1/tasks/{task_id}/cancel` 扩展支持 `INDEX_CHUNK` 与 `INDEX_PREPROCESS`；取消在处理中可被 Worker 观察，响应保留任务类型和索引版本。

- 第十二批固定基础模型 BAAI/bge-small-zh-v1.5 revision 7999e1d3359715c523056ef9478215996d62a620 与第三方 ONNX 仓库 Xenova/bge-small-zh-v1.5 revision 75c43b069aac4d136ba6bc1122f995fedcfd2781；该第三方卡片指向 BAAI base model，但未单独声明 license。许可、所有运行文件大小/SHA-256 与等价性细节详见 docs/project/index-preprocessing-contract.md。
- 新增内部 ModelManager：固定 HTTPS URL/revision、单文件大小/哈希、128 MiB 总量、10 秒连接/30 秒读取/15 分钟总超时、可信跳转域、路径保护、同进程并发锁、下载进度/取消、稳定错误码、离线缺失状态；完整校验 .partial 后原子发布。下载失败、校验失败及最后一块取消都不会发布不完整目录，失败文件保留供重试。
- 新增独立 OnnxEmbeddingAdapter：只启用 ONNX Runtime CPUExecutionProvider；查询加官方 BGE 中文指令，文档不加前缀；masked mean pooling + L2 normalization，输出 512 维。批量不超过 16，CPU 默认 2 线程且最多 4；输入字符超过 16,000 或 tokenizer 序列超过 512 时稳定失败，不截断正文。
- 应用启动模块导入不加载 ONNX Runtime 或 tokenizers；模型只在显式调用时下载/加载。旧 spike 下载入口已改为固定安装器。新默认 Embedding 配置只在完成真实验证后写入复合 model_revision；历史 NULL 行保留。未新增数据库迁移、API、Worker 或 UI。

## 验收追踪

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B08-01 | 空知识库创建、持久化和重启后可见 | `test_stage5_knowledge_bases.py` 重启测试 | PASS |
| S5-B08-02 | 名称/描述/颜色边界与同名提示 | 后端边界参数化测试、同名测试 | PASS |
| S5-B08-03 | 列表、详情和编辑来自真实 API | 后端专项、前端组件、Playwright | PASS |
| S5-B08-04 | 编辑、删除、恢复版本冲突不覆盖 | 原子更新与 `412` 专项测试 | PASS |
| S5-B08-05 | 正常列表排除回收站对象，详情返回 404 | 回收站生命周期测试 | PASS |
| S5-B08-06 | 恢复保留字段、成员并递增版本 | 回收站生命周期测试 | PASS |
| S5-B08-07 | 永久删除知识库不删除原始文件 | 导入文件后删除知识库专项测试 | PASS |
| S5-B08-08 | 空知识库不伪造索引/检索能力 | `EMPTY` 状态断言、前端未开放状态 | PASS |
| S5-B08-09 | 迁移空库/已有数据兼容与完整性 | `test_stage4_migration.py`，`quick_check=ok` | PASS |
| S5-B08-10 | 阶段 4 文件生命周期无回归 | 后端全量、前端全量、阶段 4 Playwright | PASS |
| S5-B09-01 | `202` 父任务持久化成员准入，且不误报索引完成 | 后端任务/API 测试、前端组件、Playwright | PASS |
| S5-B09-02 | 多库共享、混合合法/非法批次、重复提交与移出重加 | `test_stage5_knowledge_bases.py` | PASS |
| S5-B09-03 | 回收站文件拒绝加入，移出不删除原文件 | 后端专项与浏览器生命周期 | PASS |
| S5-B09-04 | Worker 类型隔离、取消竞态和租约恢复基础 | `test_tasks_backups.py`、取消竞态测试 | PASS |
| S5-B09-05 | 前端真实选择、进度、逐项结果、刷新恢复与移出 | Vitest + 真实后端 Playwright | PASS |
| S5-B09-06 | 无索引时始终不可检索 | API 成员状态、UI 状态与 E2E 断言 | PASS |
| S5-B10-01 | 字符单位配置、Embedding 元数据与稳定指纹 | 默认配置专项测试、迁移种子 | PASS |
| S5-B10-02 | 空库及第九批知识库/成员/任务无损迁移 | 迁移专项、`quick_check=ok` | PASS |
| S5-B10-03 | 一致输入快照与混合成功/跳过/失败 | 预处理专项测试 | PASS |
| S5-B10-04 | 移出、解析修订变化与回收站不发布过期结果 | 快照竞态与完成前复核测试 | PASS |
| S5-B10-05 | 幂等、租约过期接管、检查点续跑、取消与类型隔离 | Worker/任务专项测试 | PASS |
| S5-B10-06 | 预处理不激活索引、不改变可检索状态 | IndexVersion、知识库和成员断言 | PASS |
| S5-B11-01 | 结构优先、500/80 Unicode 字符目标、长内容上限、空内容与定位边界 | `test_stage5_chunking.py` 切片规则测试 | PASS |
| S5-B11-02 | 标题、页、幻灯片、行、列表、表格和代码块使用真实结构；不伪造 token 计数 | 固定本地解析结构、字符长度及来源位置断言 | PASS |
| S5-B11-03 | 同文件跨知识库复用；解析修订或切片配置变化后新旧 Chunk 共存 | Worker 集成测试与数据库唯一约束 | PASS |
| S5-B11-04 | 完整 Chunk 集和输入检查点原子提交；重复执行不重复写入 | Worker 重跑、内容哈希和计数断言 | PASS |
| S5-B11-05 | API 取消、租约过期、应用关闭检查点、显式失败重试和混合输入状态 | API/Worker/任务检查点集成测试 | PASS |
| S5-B11-06 | 成员变化、回收站、永久删除、哈希/解析修订和配置变化不会发布陈旧 Chunk | 发布前快照复核及永久删除竞态测试 | PASS |
| S5-B11-07 | 永久删除只清理当前逻辑文件 Chunk，不影响其他文件版本 | 文件回收站与 Chunk 集成测试 | PASS |
| S5-B11-08 | 切片结束不激活 IndexVersion，不改变 `active_index_version_id` 或可检索状态 | 数据库、任务摘要与 API 状态断言 | PASS |

## 第十二批验收追踪

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B12-01 | 基础模型/第三方 ONNX/tokenizer revision、许可说明与逐文件哈希固定 | manifest、Hugging Face revision API、实际文件 SHA-256、来源契约 | PASS |
| S5-B12-02 | 错误哈希、缺文件、部分响应、超时、取消/重试、末块取消、并发、离线、路径与跳转错误均失败关闭 | test_embedding_model_manager.py，离线 HTTP fixture | PASS |
| S5-B12-03 | Adapter 批量上限、CPU Provider、确定性、有限/非零、512 维、归一化、查询/文档规则与超长拒绝 | test_embedding_adapter.py 固定 tokenizer 和 fake ONNX session | PASS |
| S5-B12-04 | 应用启动导入不加载 ONNX Runtime/tokenizers | 隔离 Python 子进程导入 mindmate.main 回归 | PASS |
| S5-B12-05 | 实际 ONNX 与官方原始权重固定中文样本数值对齐 | Windows 11 x64 CPU；(3,512)、max abs error 1.1175871e-7、min cosine 1.0、round-4 batch digest 相等 | PASS |
| S5-B12-06 | 固定 revision 实际下载/校验/原子发布及离线再加载、CPU 推理成功 | 本地安装器状态 READY；输出 (2,512)，有限、L2 norm 约为 1 | PASS |
| S5-B12-07 | 阶段 4/5 浏览器关键生命周期无回归 | 隔离 SQLite + 真实 FastAPI/Vite；Playwright 2 passed | PASS |
| S5-B12-08 | 阶段 5 仍不可检索，不接 Embedding Worker/EmbeddingRecord/FTS/向量索引 | 实现范围、现有任务/状态契约和回归测试 | PASS |

## 自动化证据

```text
backend> uv run pytest
60 passed

backend> uv run pytest tests/test_stage5_chunking.py
10 passed

backend> uv run pytest tests/test_stage5_knowledge_bases.py
11 passed

backend> uv run pytest tests/test_stage4_migration.py tests/test_stage5_index_preprocessing.py
10 passed

backend> .\.venv\Scripts\python.exe -m ruff check src tests
All checks passed

backend> .\.venv\Scripts\pyright.exe
0 errors, 0 warnings, 0 informations

backend> .\.venv\Scripts\python.exe -m compileall -q src tests
通过

frontend> npm run lint
通过（ESLint + oxlint）

frontend> npm run typecheck
通过（tsc -b）

frontend> npm run test
5 files, 13 tests passed

frontend> npm run build
Vite production build succeeded

frontend> MINDMATE_API_PORT=8014 MINDMATE_WEB_PORT=5175 npx playwright test e2e/stage4-files.spec.ts e2e/stage5-knowledge-bases.spec.ts --reporter=line
2 passed（阶段 4 文件生命周期与阶段 5 知识库成员回归）

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0；Generated 34 schemas and 50 operations

backend> 空库及既有文件/知识库/成员/任务 upgrade -> downgrade -> upgrade head
最终 revision f2c7a1d8e904；PRAGMA quick_check=ok

repo> git diff --check
通过
```

测试仅出现 Starlette/httpx 与 Alembic 配置的依赖弃用警告，无测试失败。没有调用 DeepSeek、上传用户资料或使用真实凭据。

## 第十二批自动化与真实模型证据

~~~text
backend> uv run --locked pytest
81 passed

backend> uv run --locked ruff check src tests spikes
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests spikes
通过

backend> uv lock --check --offline
Resolved 75 packages; lock is current

frontend> npm run lint
通过（ESLint + oxlint）

frontend> npm run typecheck
通过（tsc -b）

frontend> npm run test
5 files, 13 tests passed

frontend> npm run build
Vite production build succeeded

frontend> npm run test:e2e -- e2e/stage4-files.spec.ts e2e/stage5-knowledge-bases.spec.ts --reporter=line --workers=1
2 passed（真实本地 FastAPI + Vite；临时 SQLite 和允许来源）

Windows 11 x64 / Python 3.12.11 / onnxruntime 1.30.0 / tokenizers 0.23.2
官方权重对照工具（非应用依赖）：torch 2.8.0+cpu / transformers 4.56.2
基础模型：BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620
ONNX：Xenova/bge-small-zh-v1.5@75c43b069aac4d136ba6bc1122f995fedcfd2781
产物指纹：4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5
来源文件 SHA-256、许可及 tokenizer 全文件哈希：见 docs/project/index-preprocessing-contract.md

固定 query（含官方 BGE 指令）+ 2 个中文 document：
shape=(3,512), max_abs_error=1.1175871e-7, min_cosine=1.0
np.round(vectors, 4).astype('<f4').tobytes(order='C') SHA-256:
eeb4b3cb2117502891e3af08e009d24aa733f3a4d65c7e4080827d407b3f0ac5（官方权重与 ONNX 相同）
真实固定源下载/校验后安装状态 READY；离线复用后 CPU adapter 输出有限、512 维且单位范数。
~~~

本批没有生成或提交模型文件、模型缓存、凭据或真实用户资料；真实模型验证资产位于 Git 忽略的本地目录。

## 第十三批验收追踪

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B13-01 | EmbeddingRecord 与逐输入状态迁移，配置指纹和固定 revision/tokenizer 约束 | `test_stage5_embedding_worker.py` + Alembic `a81f3c6d2e90` | PASS |
| S5-B13-02 | 同文件/配置跨知识库复用推理，同时按 IndexVersion 隔离持久向量 | 多库集成测试、EmbeddingRecord 唯一键、sqlite-vec identity | PASS |
| S5-B13-03 | sqlite-vec 文件库真实 512 维写入、hash/ID 存在性对账、幂等 upsert 和删除 | Windows 11 文件数据库测试 + Adapter 集成测试 | PASS |
| S5-B13-04 | 单并发领取、租约过期接管和重复任务无重复成功向量 | SQLite 部分唯一索引、任务租约测试 | PASS |
| S5-B13-05 | 写向量后进程中断，重启按已有向量映射恢复而不重复推理 | `test_vector_written_before_process_interruption_is_reconciled_without_reinference` | PASS |
| S5-B13-06 | 模型离线缺失带稳定可重试摘要、逐文件失败、取消/重启和成员移除、文件回收站、解析修订/配置变化竞态 | 固定离线 Fixture、Worker/任务回归 | PASS |
| S5-B13-07 | 删除知识库仅清理其版本向量，保留另一知识库复用的 Chunk/EmbeddingRecord；文件/版本永久删除竞态不遗留向量 | 回收站真实 API、注入版本删除 + 向量库/数据库断言 | PASS |
| S5-B13-08 | 实际固定本地 ONNX 模型经 Worker 生成归一化 512 维持久向量 | Windows 本地 `manager-validation` cache，offline only，`test_worker_uses_verified_local_onnx_model_without_network` | PASS |
| S5-B13-09 | Embedding 完成不激活索引、不变更活动版本或可检索状态 | IndexVersion、KnowledgeBase、任务 summary 断言 | PASS |

### 第十三批实际验证

~~~text
backend> uv run --locked pytest
97 passed

backend> uv run --locked ruff check src tests spikes
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests spikes
通过

backend> uv lock --check --offline
Resolved 75 packages; lock is current

backend> Alembic 空库/既有数据 upgrade -> downgrade -> upgrade head
revision a81f3c6d2e90；PRAGMA quick_check=ok

backend> sqlite-vec Windows 文件 SQLite 探测
写入/读取 float[512]，shape=(512,)，向量记录与 SHA-256 对账通过

backend> 已验证固定 manifest 的本地 ONNX Worker 集成
Git 忽略的 manager-validation cache 状态 READY；无网络、无下载；Worker 生成 512 维有限单位向量

frontend> Playwright stage4-files + stage5-knowledge-bases
2 passed（隔离 SQLite + 真实本地 FastAPI/Vite）

repo> git diff --check
通过
~~~

本批未改前端，前端 Vitest/lint/typecheck/build 沿用第十二批历史证据且未在本批重跑；本批浏览器关键回归已运行。真实模型与 ONNX 文件仅从现有忽略缓存读取，不下载、不移动、不清理、不提交；未调用 DeepSeek。

## 未实现与下一批前置

- Embedding 和 FTS5 投影已生成并持久化，但向量 Top-K、RRF、增量/原子索引激活、测试检索、引用和 RAG 未实现。
- 没有激活索引或开放检索；FTS5 投影不是公开关键词搜索能力。
- 未宣称阶段 5 `PASS`，也未回填阶段 4 的发布候选遗留项。

下一批唯一目标：增加同一 `IndexVersion` 的内部 sqlite-vec Top-K 查询与版本/成员过滤测试；不激活索引或开放 RAG。

## 第十四批验收追踪：持久 FTS5 Chunk 投影

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B14-01 | Alembic 增量增加 FTS5 虚表、版本映射、逐输入状态/原因/计数/时间与单运行租约约束 | `d60f2e8a7c31`；空库、既有库升级与 `quick_check=ok` | PASS |
| S5-B14-02 | 按 `IndexVersion + Chunk` 隔离；映射可回溯文件、解析修订、切片配置和正文 hash，新版本不覆盖旧版本 | `test_fts5_is_versioned_chinese_short_query_bm25_and_rebuildable` | PASS |
| S5-B14-03 | FTS5 MATCH/BM25 对固定中文、二字/单字短查询与英文词实际命中；不使用 LIKE | 同上；内部 `match_version` 查询与 BM25 排序 | PASS |
| S5-B14-04 | FTS 映射、虚表行、逐文件检查点和任务进度原子提交；重复构建幂等 | `test_task_progress_checkpoint_counts_each_committed_input`、逐项失败/重试与重建回归 | PASS |
| S5-B14-05 | 映射损坏可从权威 Chunk 重建，且 FTS5 内部完整性、映射/Chunk 一致性检查通过 | 损坏后删除目标版本派生投影并 rebuild；`integrity-check` 与 `consistency_check` | PASS |
| S5-B14-06 | 单项失败隔离、稳定原因、显式重试；取消、租约过期接管和重复领取可恢复 | `test_fts_input_failure_isolated_and_explicit_retry_recovers`、`test_expired_lease_resumes_running_input_without_duplicate_projection`、取消专项 | PASS |
| S5-B14-07 | 成员移出、文件回收站和版本变化立即排除旧 FTS 行；永久删除只清目标文件投影，知识库清理只影响本库版本 | 成员移除、文件回收站/永久删除、共享文件多知识库 purge 回归 | PASS |
| S5-B14-08 | FTS-only 降级/再升级不删除 Chunk、EmbeddingRecord 或向量数据；投影可再构建 | `test_fts_migration_rollback_preserves_chunks_and_embedding_records`，降级至 `a81f3c6d2e90` 后重升 head | PASS |
| S5-B14-09 | 本批不激活索引、不开放检索、Top-K、融合、引用或 RAG | `IndexVersion.status=BUILDING`、`active_index_version_id=NULL`、摘要 `available_for_retrieval=false` 断言；无 API/UI 变化 | PASS |

## 第十四批实际验证

~~~text
backend> uv run --locked pytest
105 passed

backend> uv run --locked ruff check src tests
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests migrations
通过

backend> 空库 / 既有数据库 Alembic upgrade head
revision d60f2e8a7c31；PRAGMA quick_check=ok

backend> FTS-only downgrade a81f3c6d2e90 -> upgrade head
Chunk 与 EmbeddingRecord 数量保持；FTS 投影按设计移除，再由 Chunk 重建；PRAGMA quick_check=ok

backend> uv run --locked uvicorn mindmate.main:app --host 127.0.0.1 --port 8014
MINDMATE_DATA_DIR 指向临时隔离目录；health 返回 ok，E2E 完成后停止服务

frontend> MINDMATE_API_PORT=8014 MINDMATE_WEB_PORT=5173 npm run test:e2e -- e2e/stage4-files.spec.ts e2e/stage5-knowledge-bases.spec.ts --reporter=line --workers=1
2 passed（隔离数据目录、真实 FastAPI + Vite；使用项目允许的 5173 Origin）

repo> git diff --check
通过
~~~

FTS5 采用 `unicode61 remove_diacritics 2`。拉丁/Unicode 词项按词匹配；连续汉字同时索引重叠二元词与单字辅助列，以支持短中文查询。此策略不是 ICU/Jieba 词典分词；连续汉字采用二元词召回，BM25 的最终相关性/Recall 尚未评估，且本批没有公开 MATCH API。

FTS 回退边界：只允许在需要撤销本批 schema 时从 `d60f2e8a7c31` 降级到 `a81f3c6d2e90`。该操作会删除可重建的 FTS5 虚表、映射和 FTS 检查点列，不修改 Chunk、EmbeddingRecord、向量数据库或原始资料；重新升级后映射为空，必须从 Chunk 重建。不得继续降级穿过之前批次的持久业务数据迁移。

本批结论：`PASS`；阶段 5 继续 `PARTIAL`。没有激活 `IndexVersion`，FTS 投影完成不等于关键词检索可用。未实现向量 Top-K、混合检索、原子激活、引用和 RAG。
