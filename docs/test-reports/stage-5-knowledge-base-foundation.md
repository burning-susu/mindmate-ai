# 阶段 5：知识库基础与成员准入测试报告

> 阶段：`5`
> 批次：`第八批至第二十八批`
> 验证日期：`2026-09-25`
> 第八批结论：`PASS`
> 第九批结论：`PASS`
> 第十批结论：`PASS`
> 第十一批结论：`PASS`
> 第十二批结论：`PASS`
> 第十三批结论：`PASS`
> 第十四批结论：`PASS`
> 第十五批结论：`PASS`
> 第十六批结论：`PASS`
> 第十七批结论：`PASS`
> 第十八批结论：`PASS`
> 第二十批结论：`PASS`
> 第二十一批结论：`PASS`
> 第二十二批结论：`BLOCKED`（真实 Chat/Learning owner 前置缺失，延期到阶段 6/7）
> 第二十三批结论：`PASS`
> 第二十四批结论：`PASS`
> 第二十七批结论：`PASS`
> 第二十八批结论：`PASS`
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

第八至第十六批完成知识库成员、索引预处理、Chunk、Embedding、FTS5、向量 Top-K 与双路候选基础；第十七批完成内部 RRF/多样性 Top 8；第十八批完成内部证据判定；第十九批完成产物完整性复核与原子激活；第二十批完成同一知识库增量构建；第二十一批建立未绑定服务端来源快照；第二十三批增加受本地会话保护的本地测试检索 API；第二十四批将该 API 接入知识库详情页高级诊断区域；第二十七批修复中文自然问句 FTS5 召回并加入困难负例回归。空库保持 `EMPTY`；此端点和页面不提供聊天答案或 Citation。

第十批 `INDEX_PREPROCESS` 的 `COMPLETED` 只证明输入快照与预处理结果已持久化；第十一批 `INDEX_CHUNK` 只证明切片阶段结束；第十三批 `INDEX_EMBED` 只证明向量已持久化；第十四批 `INDEX_FTS` 只证明 FTS5 投影已建立。第十五至十八批提供内部召回、排序与证据判定；`supported` 只表示候选可进入后续处理，不证明最终答案获事实支持。第十九批验证完整候选后才允许原子激活；第二十批增量候选沿用同一完整性复核；第二十一批从活动版本内部检索结果创建经服务端复核的未绑定来源快照。第二十二批因真实 owner 不存在而 `BLOCKED`，Citation 绑定延期至阶段 6/7；第二十三批只开放本地测试检索端点，第二十四批完成详情页诊断界面。阶段 5 仍为 `PARTIAL`：Citation 绑定、聊天/RAG 与验收集质量评估仍未完成。

## 实现范围

- 新增 `GET/POST /api/v1/knowledge-bases` 与 `GET/PATCH/DELETE /api/v1/knowledge-bases/{id}`。
- 新增 `GET /api/v1/trash/knowledge-bases`、`POST /api/v1/trash/knowledge-base/{id}/restore` 与 `DELETE /api/v1/trash/knowledge-base/{id}`。
- 新增 `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests`，仅用于受本地 Origin/Session 保护的只读检索调试。
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

## 第十五批：内部向量 Top-K 与范围过滤

### 交付范围

- 新增 `SqliteVecAdapter.search`，提供固定 512 维单位向量的只读 Top-K 查询，默认/最大 `k=30`，返回向量记录 ID、Chunk ID、hash 和 sqlite-vec 原始距离。
- 新增 `VectorTopKQuery` 与 `query_vector_top_k` 内部用例。调用方必须先确定知识库和 IndexVersion；用例验证知识库未回收、版本归属/`BUILDING`/sqlite-vec、固定 EmbeddingConfig 指纹与 512 维归一化余弦配置。
- 业务范围在 Top-K 之前生效：只把当前 `ACTIVE` 成员、快照 `added_at` 未变化、文件已解析且未回收、内容哈希/解析修订一致、Chunk 未失效、EmbeddingRecord 为 `READY` 且 config/hash 一致的记录交给 Adapter。成员移出/重加、知识库或文件回收站、版本失效、Chunk/记录失效均不能返回命中。
- sqlite-vec 当前每版本虚表没有动态成员分区列。为了避免先全局 Top-K 再过滤导致范围内近邻丢失，Adapter 读取该版本全部 KNN 行，先按允许记录集合过滤，再按距离和稳定记录 ID 排序并截断；该策略精确但查询成本为 O(N)，没有作为大规模性能证据。
- 现有存储使用默认 L2 距离；因为写入和查询向量都单位归一化，应用将 `d_l2²/2` 暴露为余弦距离，将 `1-distance` 暴露为相似度，距离升序与相似度降序一致。同分按 `vector_store_record_id` 稳定排序。

### 第十五批验收追踪

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B15-01 | 固定 512 维向量近邻排序、距离/相似度、同分稳定排序、`k` 大于候选数 | `tests/test_stage5_vector_search.py::test_vector_top_k_orders_scores_and_does_not_change_index_state`、`test_adapter_scope_ties_and_empty_vector_space_are_deterministic` | PASS |
| S5-B15-02 | 范围在 Top-K 前生效，范围外更近向量不挤出范围内候选 | `test_scope_is_applied_before_top_k_and_shared_file_is_independent` | PASS |
| S5-B15-03 | 同版本/同配置隔离，跨知识库共享文件仍按目标库返回，错误版本/配置不可查询 | 同上、`test_query_rejects_bad_vector_k_and_cross_scope_version` | PASS |
| S5-B15-04 | 成员移出重加、知识库/文件回收站、版本失效、Chunk/EmbeddingRecord 失效和永久清理后立即排除 | `test_scope_lifecycle_filters_trash_invalid_chunk_and_record`、`test_trashed_knowledge_base_and_invalidated_version_are_unavailable`、Adapter 删除版本断言 | PASS |
| S5-B15-05 | 坏维度、未归一化向量、`k` 越界、空库和向量库异常返回稳定错误或空结果 | `test_query_rejects_bad_vector_k_and_cross_scope_version`、`test_query_propagates_vector_store_failure` | PASS |
| S5-B15-06 | 查询只读，不修改 BUILDING/活动版本/可检索状态 | `test_vector_top_k_orders_scores_and_does_not_change_index_state` | PASS |
| S5-B15-07 | 本批不新增 API/OpenAPI/前端，不激活索引、不做融合/RRF/引用/RAG | Git diff、无路由变更、状态断言 | PASS |

### 第十五批实际验证

~~~text
backend> uv run --locked pytest
112 passed

backend> uv run --locked ruff check src tests
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests migrations
通过

repo> git diff --check
通过
~~~

本批未改数据库 schema、OpenAPI、前端或 Worker；没有真实模型下载、DeepSeek 请求、用户资料或付费接口调用。阶段 5 仍为 `PARTIAL`，内部 Top-K 不能等同知识库用户可用检索。

第十五批结论：`PASS`。其后续目标已由第十六批完成；第十六批继续不开放检索、不激活索引、不做引用或 RAG。

## 第十六批验收追踪：内部双路召回合并去重

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B16-01 | 同一 `IndexVersion` 内 FTS5 与 sqlite-vec 各取 Top 30，范围过滤后再限额 | `HybridCandidateQuery` 调用真实 `Fts5Projection.match_version` 与 `VectorTopKQuery`；两路范围指纹和现有 Top-K 集成 | PASS |
| S5-B16-02 | FTS5 查询规范化、安全 MATCH、真实 BM25、中文短词/英文/编号/特殊符号/空输入 | `test_fts5_is_versioned_chinese_short_query_bm25_and_rebuildable`；`normalize_query`/`match_expression`；未使用 `LIKE` | PASS |
| S5-B16-03 | 双路按 `chunk_id` 去重并保留 FTS rank/BM25、向量 rank/距离/相似度、文件和版本 | `test_hybrid_search_uses_real_fts_and_vector_scopes_and_deduplicates`、`test_merge_candidates_has_stable_order_and_no_fake_scores` | PASS |
| S5-B16-04 | FTS-only、Vector-only 单路命中不补造另一通道信号；相邻不同 Chunk 不误去重 | `test_hybrid_single_route_keeps_other_signal_empty`、稳定合并测试 | PASS |
| S5-B16-05 | 成员/版本/文件/Chunk/EmbeddingRecord 在双路之间变化时失败关闭 | `test_hybrid_scope_change_between_routes_fails_closed`；前后范围指纹比较返回 `RETRIEVAL_SCOPE_CHANGED` | PASS |
| S5-B16-06 | 单路故障不伪装双路成功，显式降级保留稳定错误码 | `test_hybrid_vector_failure_is_explicit_and_optional_degrade`；严格模式抛出 `VECTOR_STORE_UNAVAILABLE`，降级结果带 `vector_error` | PASS |
| S5-B16-07 | 本批不开放用户检索，不做 RRF/最终 Top 8/多样性/引用/RAG，不改迁移/API/OpenAPI/前端 | Git diff、状态断言、无路由与 schema 变化 | PASS |

### 第十六批实现与边界

- `backend/src/mindmate/application/hybrid_search.py` 新增内部候选收集、范围快照、按 Chunk ID 合并和显式故障/降级结果；`HybridCandidateQuery.search` 默认严格失败，`search_with_status(..., allow_degraded=True)` 才允许单路降级。
- `Fts5Projection.match_version` 保留旧调用兼容性，同时增加 NFKC/空白规范化、Top 30 上限、知识库范围条件、稳定 `chunk_id` 并列排序、`bm25` 别名和 `fts_rank`；未将用户文本直接交给 FTS5 解析器。
- 两路结果在合并前后对版本状态、知识库、成员快照、文件、Chunk 和 EmbeddingRecord 生成确定性范围指纹；检测到中途变化立即停止，不把旧候选重新混入。
- 向量 Top-K 仍使用第十五批现有全量 KNN 后范围过滤策略，查询成本为精确 O(N)；第十六批没有进行 10 万 Chunk 性能验收。

### 第十六批实际验证

~~~text
backend> uv run --locked pytest
117 passed

backend> uv run --locked ruff check src tests
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests migrations
通过

repo> git diff --check
通过
~~~

本批没有调用 DeepSeek、真实 Provider、真实凭据或用户资料；没有新增数据库迁移、公开 API、OpenAPI、前端、索引激活、RRF、引用或 RAG。阶段 5 仍为 `PARTIAL`。

本批结论：`PASS`。下一批唯一目标：实现候选集的 RRF 融合、精确命中奖励和确定性多样性排序；不激活索引、不开放用户检索、不做引用或 RAG。

## 第十七批验收追踪：内部 RRF 与多样性排序

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B17-01 | 仅用有效 FTS/vector rank 执行 RRF；缺失通道贡献为零且原 rank/score 保持 NULL | `test_rrf_fusion_only_uses_available_ranks_and_preserves_source_signals` | PASS |
| S5-B17-02 | NFKC、大小写、全半角及标点规则确定；完整编号/标题/正文命中可审计，短词子串不会被误认为完整词 | `test_exact_heading_match_normalizes_case_width_and_punctuation_with_bounded_bonus`、`test_short_ascii_term_requires_boundaries_and_never_overrides_stronger_rrf` | PASS |
| S5-B17-03 | 同文件分布与相邻高重叠 Chunk 采用有界软惩罚；不同来源优先；不硬删除重复附近的候选 | `test_diversity_softly_promotes_other_files_without_dropping_overlapping_chunks` | PASS |
| S5-B17-04 | 同分、输入顺序变化、空候选、Top 8 和排名理由可重复 | `test_ranking_is_input_order_independent_caps_at_eight_and_accepts_empty_input` | PASS |
| S5-B17-05 | 显式降级时只按可用 rank 排名，并保留失败通道、错误码及 degraded 标记；范围变化仍失败关闭 | `test_hybrid_vector_failure_is_explicit_and_optional_degrade`、`test_hybrid_scope_change_between_routes_fails_closed` | PASS |
| S5-B17-06 | 至少一条真实 SQLite FTS5 + sqlite-vec 内部端到端排序用例；原始信号保留且 IndexVersion 不激活 | `test_hybrid_search_uses_real_fts_and_vector_scopes_and_deduplicates` | PASS |
| S5-B17-07 | 不开放公开检索或 API；不修改 BUILDING/活动索引/可检索状态，不声称证据充分，不做引用/RAG | 代码差异、真实集成状态断言；无 API/OpenAPI/前端/迁移变更 | PASS |

### 第十七批算法与排序解释

- 算法版本为 `rrf-exact-diversity-v1`。默认 RRF 常量 `k=60`，融合分数是每个实际命中通道 `1 / (60 + rank)` 的和。分数只代表倒数排名融合量，不是概率，也不是 BM25 与余弦相似度的直接加和。缺失通道不产生贡献，原始 `NULL` rank 与分数不变。
- 查询、文件显示名、Chunk heading path 和正文以 NFKC、casefold 规范化；Unicode 标点、空白和符号统一成为分隔符。完整规范化查询短语（至少 4 个规范化字符）奖励 `0.002`，每个完整命中词项奖励 `0.0004`，总精确命中奖励封顶 `0.004`。ASCII 拉丁/数字词项要求 ASCII 词边界；长中文查询按三字片段检查，二字中文项按四分之一权重计分。结果保留命中词项、`file_title`/`heading`/`content` 字段、精确奖励分数和原因码。
- 多样性按确定性贪心顺序逐个选取：候选每次以 RRF + 精确奖励 - 当前多样性惩罚重新比较。同文件此前每选中一个候选扣 `0.001`，最多计两个；同文件 Chunk 序号差不超过 1 且归一化三元字符集合的重叠系数不低于 `0.6` 时再扣 `0.0025`；总惩罚封顶 `0.0035`。惩罚只会调整次序，不按文件或相似度直接丢弃候选。
- 并列排序依次比较：融合 RRF 分高者、精确奖励高者、最佳原始 rank 小者、双路命中者、FTS rank 小者、vector rank 小者、`file_id` 字典序、Chunk 序号、`chunk_id` 字典序。排序输出最多 8 个。
- `HybridSearchResult` 返回算法版本和有效配置；每个候选保留 FTS/vector rank、原始 BM25/距离/相似度、RRF 分、精确命中与字段、多样性调整与原因、最终分和最终名次。显式单路故障降级还保留通道错误码和 `degraded`。
- 范围指纹在双路前后检查，并在读取候选 Chunk 正文/标题/序号后再次复核；发现变化返回 `RETRIEVAL_SCOPE_CHANGED`。本批没有数据库迁移、公开检索、OpenAPI、前端、索引激活、证据阈值、引用或 RAG。固定样本不是最终 Recall@10 验收；向量过滤的 O(N) 性能限制不变。

### 第十七批实际验证

~~~text
backend> uv run --locked pytest
122 passed（串行运行）

backend> uv run --locked ruff check src tests
All checks passed

backend> uv run --locked pyright
0 errors, 0 warnings, 0 informations

backend> uv run --locked python -m compileall -q src tests migrations
通过

repo> git diff --check
通过
~~~

本批没有改前端或 API，因此没有运行阶段 4/5 UI E2E；真实 SQLite FTS5/sqlite-vec 的内部检索集成测试已纳入后端 pytest。没有调用 DeepSeek、真实凭据、付费服务或真实用户资料。第十七批结论 `PASS`；阶段 5 继续 `PARTIAL`。下一批唯一目标：对内部 Top 8 实现配置化的证据充分性阈值判定和严格拒答结果，仍不公开检索、不激活索引、不生成回答或引用。

## 第十八批验收追踪：内部证据充分性判定与严格拒答

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B18-01 | 内部 Top 8 后产生 `supported/insufficient/unavailable` 结构化判定，保留规则版本、原因和候选身份 | `test_stage5_evidence_gate.py`；`test_hybrid_search_assesses_scoped_top_eight_without_activating_index` | PASS |
| S5-B18-02 | 判定组合正文锚点/编号、经验证余弦相似度、原始排名、融合排名、来源数与问题类型 | 精确问题/改写/单文件、低相似度、短词、编号、数值及来源覆盖用例 | PASS |
| S5-B18-03 | 标题命中、精确奖励或高 RRF 排名不能绕过正文证据；短词、未知分数和缺失答案保守拒绝 | `test_high_similarity_does_not_support_a_missing_numeric_answer`、`test_short_terms_title_only_and_missing_identifier_are_not_support`、`test_weak_or_unverified_vector_signal_never_passes_the_gate` | PASS |
| S5-B18-04 | 空结果、单文件、重复切片、部分覆盖复合问题及冲突资料均有明确行为 | `test_empty_results_return_fixed_safe_message_and_validated_config`、`test_supports_exact_and_reasonably_rephrased_single_file_evidence`、`test_repeated_chunks_do_not_inflate_distinct_source_coverage`、`test_composite_questions_and_conflicting_sources_fail_closed` | PASS |
| S5-B18-05 | 未请求通道、通道失败、错误范围/版本或范围变化返回 `unavailable`，不显示资料不足文案 | `test_route_failures_are_unavailable_and_never_refusal_copy`、`test_assessment_keeps_missing_route_and_wrong_scope_out_of_insufficient`、`test_assessment_reports_scope_change_as_unavailable`、`test_hybrid_vector_failure_is_explicit_and_optional_degrade` | PASS |
| S5-B18-06 | 真实 SQLite FTS5 + sqlite-vec 内部链路运行到证据判定；没有范围外候选、活动版本变化或虚假引用 | `test_hybrid_search_assesses_scoped_top_eight_without_activating_index` | PASS |
| S5-B18-07 | 不调用模型，不生成答案/引用编号，不增加公开检索 API、迁移、OpenAPI 或 UI | 代码差异、集成状态断言与公开契约检查 | PASS |

### 第十八批规则与边界

- 规则版本为 `evidence-gate-v1`。默认配置：余弦相似度下限 `0.82`；最终排序不晚于第 `3` 位；FTS 与 vector 原始 rank 均不晚于 `5`；正文至少覆盖 `2` 个问题锚点且覆盖率至少 `0.60`，或包含至少 `5` 个规范化字符的完整查询短语；完整编号必须出现在正文；数值类问题必须在正文锚点 `48` 个字符范围内找到数值；默认最少独立支持来源为 `1`。
- 向量字段按既有 Adapter 语义解释：单位向量使用 sqlite-vec 默认 L2，余弦距离为 `d_l2² / 2`，相似度为 `1 - cosine_distance`。门控要求距离在 `[0,2]`、相似度在 `[-1,1]` 且两者误差不超过 `1e-5`；空值、非有限值或不一致按无效信号处理。
- RRF 分数、精确命中奖励和多样性惩罚只决定候选次序；门控只使用融合名次和原始路由 rank，不读取最终分数/奖励作为放行条件。关键词覆盖只在 Chunk 正文统计，文件标题和 heading 不算作答案证据。支持来源按 `file_id` 计数，重复 Chunk 不会增加来源数；最小来源默认 1，因此单文件有效证据不会因来源数量被拒绝。
- 复合/开放列举问题整体 `insufficient`，不尝试部分答案拆分；多个合格来源出现不同数值或相反肯定/否定标记时整体 `insufficient`。冲突与问题类型识别是简单本地规则，无法可靠分类时会偏向拒绝，不表示语义蕴含已经解决。
- `insufficient` 才带固定本地提示和补充/调整资料建议，不携带模型生成文本或伪引用。范围变化、活动/失效/未就绪版本、失败/降级通道、未请求向量路由返回 `unavailable` 和稳定原因码，不以拒答文案掩盖故障。`supported` 只表示候选可以进入后续服务端来源快照、引用绑定和生成流程，不宣称答案最终通过事实验证。
- 离线固定样本预期/实测：精确定义问题与保留核心实体的合理改写 `supported/supported`；语义相近但缺所问数值、高相似度但无答案、标题/错误编号/短词命中、向量弱或无效、同文件重复 Chunk、部分覆盖复合问题、数值/肯定否定冲突 `insufficient/insufficient`；单文件有效证据 `supported/supported`；空结果 `insufficient/insufficient`；未请求向量、通道故障、范围变化和错误知识库版本 `unavailable/unavailable`。固定样本共 8 个纯判定用例，另有真实 SQLite 集成覆盖，不含个人资料。
- `0.82` 等默认值是保守实现初值，不是基于标注数据集校准的最终阈值。固定样本通过不等价于最终 Recall@10、答案蕴含或知识问答质量验收。

### 第十八批实际验证

~~~text
backend> uv run pytest
133 passed（串行运行）

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations
通过

repo> git diff --check
通过
~~~

首次完整 pytest 运行曾有一次既有 `test_embedding_claim_releases_only_expired_singleton_lease` 失败；单项重跑通过，之后完整串行重跑 `133 passed`。额外运行的 `uv run ruff check .` 报告 14 条既有 Alembic migration lint 项；本批相关源码/测试范围 Ruff 通过，迁移文件未修改。未运行 UI E2E（无前端/API 变化），未调用 DeepSeek、真实凭据、付费接口或用户资料。第十八批结论 `PASS`；阶段 5 继续 `PARTIAL`。

下一开发批次唯一目标：为已完成索引版本实现产物完整性复核与原子激活，继续不开放用户检索。

## 第十九批验收追踪：索引产物完整性复核与原子激活

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B19-01 | 首次完整候选可激活，重复执行幂等返回；同一知识库仅一个版本为活动 `READY` | `test_first_activation_is_complete_and_idempotent` | PASS |
| S5-B19-02 | 新候选 `BUILDING` 不可读；切换后旧版 `RETIRED`，其 FTS/向量文件仍保留 | `test_atomic_switch_preserves_old_artifacts_and_rejects_building_candidate` | PASS |
| S5-B19-03 | Chunk 数、向量记录/维度/hash、FTS 映射任一不完整时拒绝；旧活动指针与旧产物不变 | `test_incomplete_artifacts_fail_candidate_and_keep_old_version` | PASS |
| S5-B19-04 | 任务未终结时等待；部分失败文件被排除并形成 `PARTIAL`；空库为 `EMPTY`、空文本无可用输入为 `FAILED` | `test_unfinished_task_waits_and_partial_files_activate_as_partial`、`test_empty_database_and_empty_text_have_distinct_terminal_states` | PASS |
| S5-B19-05 | 更新候选胜出；较旧候选晚到、成员快照变化均不能覆盖更新状态 | `test_newest_candidate_wins_and_older_late_completion_is_superseded`、`test_candidate_created_during_audit_blocks_late_activation`、`test_changed_membership_supersedes_candidate_without_replacing_old_active` | PASS |
| S5-B19-06 | 重复 Worker 并发只发布一次；进程中断可重跑；激活提交注入故障完整回滚 | `test_concurrent_activation_attempts_publish_exactly_once`、`test_activation_resumes_after_interruption_and_commit_failure_rolls_back` | PASS |
| S5-B19-07 | 应用层向量/混合查询仅接受活动 `READY` 版本；BUILDING 候选不经此边界开放；无公开检索 API/API schema/UI | `tests/test_stage5_vector_search.py` 活动版本回归、OpenAPI 未变、代码差异 | PASS |

### 第十九批完整性规则

- 激活扫描器只评估仍为 `BUILDING` 的候选。必须存在已完成的预处理、Chunk、Embedding、FTS 阶段任务；每阶段最新任务为 `COMPLETED`，无同版本 `QUEUED/RUNNING` 任务，配置 ID/fingerprint 与任务检查点一致。未终结阶段保持等待；新版本已出现时旧候选不能激活，待其任务链终结后标记 `SUPERSEDED`。临时回收站/解析处理中输入等待既有恢复或永久清理流程。
- `IndexVersionInput` 必须与当前 ACTIVE 成员集合、`membership_added_at`、内容哈希、解析修订和 `parse_revision_set_hash` 完全相符。Chunking/Embedding 配置从实际字段重算 fingerprint；候选任务检查点必须与当前版本和配置相符。
- 对每个已切片输入校验有效 Chunk 集、逐文件计数和 Chunk 正文 SHA-256；对账 EmbeddingRecord 的 Chunk/配置/向量 hash、向量库 identity、SQLite `quick_check`、元数据/向量 rowid 一致、维度 512、有限单位向量及完整输入所需记录；执行 FTS5 `integrity-check` 与映射/倒排行对账，并将版本映射精确匹配到预期 Chunk/文件/解析修订/配置/hash。全部高成本检查在激活事务外完成，不重新运行 Embedding。
- 空知识库零成员、零计数且无派生产物时终结为 `EMPTY`，清除旧活动指针并保留旧版本物理数据；输入中的 `FAILED/SKIPPED` 被排除检索，至少一个输入的 Chunk/Embedding/FTS 均完整才可激活，知识库标记 `PARTIAL`；没有完整可用输入则候选 `FAILED`。失败原因写入逐输入阶段状态或 `activation_error_code`，首次构建失败时知识库为 `FAILED`。

### 第十九批事务与恢复

- Chunk、Embedding、向量与 FTS 校验均在激活事务外完成，不重新推理。开始短事务后，先以 `KnowledgeBase.row_version` 和预期旧 `active_index_version_id` 做条件写入以取得 SQLite 写锁；锁内再次检查知识库未删除、候选仍最新且为 `BUILDING`、成员/解析快照/配置和最新任务检查点未变化。
- 成功时同一事务设置新版本 `READY + activated_at`、旧版本 `RETIRED + retired_at`、`KnowledgeBase.active_index_version_id`/状态及文件成员 `index_state`。唯一活动版本以知识库活动指针为准；冲突或任一步骤异常回滚整笔事务。失败候选记录 `activation_error_code`，无旧版时 KnowledgeBase=`FAILED`，有旧版时保留活动指针并按旧版当前有效范围恢复 `READY/PARTIAL/NEEDS_REBUILD`。
- `IndexActivationWorker` 启动后周期扫描未终态候选。审计期间进程退出时不会留下中间状态，重启会重新校验持久产物；提交发生在一次事务内，因此不会出现版本状态与活动指针半切换。活动版本已等于请求版本时重复激活直接幂等返回。旧版 FTS/向量文件和历史物理产物不会因切换被清理。
- 应用层 Vector Top-K/Hybrid 查询只接受 `status=READY` 且与知识库活动指针一致的版本，并只消费 `index_state=READY` 的成员。构建中的候选不能从应用查询层读取；本批仍无对用户开放的检索/聊天接口。

### 第十九批实际验证

~~~text
backend> uv run pytest
147 passed（串行运行）

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations
通过

backend> uv run alembic heads
e4a7810c9b62 (head)

backend> uv run ruff check .
14 条既有 Alembic migration lint 项；本批源码/测试范围无 lint 问题

repo> git diff --check
通过
~~~

全量测试包含迁移空库/既有数据升级回归。没有改前端或公开 API，未运行 UI E2E；未调用 DeepSeek、真实凭据、付费外部服务或真实用户文件。第十九批结论 `PASS`；阶段 5 继续 `PARTIAL`。下一批唯一目标：实现同一知识库的增量索引构建策略。

## 第二十批验收追踪：同一知识库增量索引构建

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B20-01 | 有活动版本时输出可审计的 `FULL/INCREMENTAL` 计划，区分新增、变更、未变、移除、待解析、失败及复用数量 | `test_incremental_add_reuses_unchanged_vectors_and_fts`、`test_incremental_removed_member_is_excluded_while_old_active_stays_readable` | PASS |
| S5-B20-02 | 新增文件只计算新增输入；未变文件复用 Chunk/Embedding/FTS，ONNX Mock 推理调用数不增加 | `test_incremental_add_reuses_unchanged_vectors_and_fts`（计数 Mock + 候选激活器完整性复核） | PASS |
| S5-B20-03 | 文件内容哈希/解析修订变化只重算该文件；候选 Chunk、Embedding/向量、FTS 均对账后才激活 | `test_incremental_replace_only_recomputes_changed_file` | PASS |
| S5-B20-04 | 成员移出立即被旧活动版本的当前范围过滤；新快照不含该成员，不删除旧文件/历史产物 | `test_incremental_removed_member_is_excluded_while_old_active_stays_readable` | PASS |
| S5-B20-05 | 相同文件可跨知识库复用兼容 Chunk/向量/FTS；配置/模型/维度不兼容强制全量重建、不复用旧向量 | `test_incremental_cross_kb_reuses_compatible_file_cache`、`test_incompatible_embedding_dimension_forces_full_rebuild_without_reuse` | PASS |
| S5-B20-06 | 重复提交相同输入返回既有候选；既有 Worker 重试、重启、失败回退和成员/快照竞态用例继续通过 | `test_incremental_duplicate_submission_reuses_building_candidate` 及既有阶段 5 Worker/激活测试 | PASS |

### 第二十批复用契约

- 目标输入快照仍包含 ACTIVE 成员身份、文件 ID、内容哈希、解析修订和加入时间；删除成员在生成计划时不进入新候选，活动版本检索的实时成员过滤继续生效。
- 文件级产物兼容键包含 `file_id + content_hash + parse_revision_id`。ChunkingConfig 指纹涵盖算法版本、度量单位、目标/最小/最大长度、重叠和结构规则；EmbeddingConfig 指纹涵盖 Provider、模型名与 revision、维度、归一化和距离度量。实际字段与保存指纹不一致也视为不兼容。
- 只从输入阶段状态完整、配置相同的版本复用。Chunk 保持文件级权威记录；EmbeddingRecord 按现有唯一映射复用，向量按 record ID/hash 复制到新 IndexVersion 专属向量空间；FTS 按源文件复制倒排字段和新版本映射。缺项或映射变化回退至现有 Worker 计算。复用标记和计划数量存于已有预处理任务检查点/输入原因字段，没有迁移。
- 候选创建与激活继续遵循第十九批：活动指针在新版本完整性复核和原子提交前不变；切换失败保留旧活动版本及旧引用所需产物。构建过程中快照变化时，较旧候选不能激活，可针对新快照创建候选并由激活器将旧候选标记 `SUPERSEDED`。
- 固定验证没有 10 万 Chunk 性能或最终 Recall@10 结论；未运行 UI E2E，没有调用 DeepSeek、真实凭据、付费接口或真实用户文件。

### 第二十批实际验证

~~~text
backend> uv run pytest
153 passed（串行运行）

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations
通过

backend> uv run alembic heads
e4a7810c9b62 (head)

backend> uv run ruff check .
14 条既有 Alembic migration lint 项；本批相关源码/测试范围无 lint 问题

repo> git diff --check
通过
~~~

第二十批结论 `PASS`；阶段 5 继续 `PARTIAL`。第二十一批来源快照与范围校验结果见下节。

## 第二十一批验收追踪：服务端来源快照与范围校验

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B21-01 | 当前活动 READY 索引的真实混合检索结果经 evidence gate 通过后，服务端创建持久快照并可在应用重启后读取 | `test_source_snapshot_uses_database_values_and_reloads_after_restart` | PASS |
| S5-B21-02 | 快照正文、文件名、版本和位置来自数据库；摘录长度受控，缺失定位不造值，重复创建幂等 | `test_source_snapshot_uses_database_values_and_reloads_after_restart`、`test_repeated_creation_is_idempotent_and_missing_location_stays_empty` | PASS |
| S5-B21-03 | 拒绝非 supported、任意 Chunk、错库、已移除成员、回收站文件和损坏 FTS 映射 | `test_non_supported_or_fabricated_candidate_cannot_create_snapshot`、`test_cross_scope_removed_member_trash_and_damaged_mapping_fail_closed` | PASS |
| S5-B21-04 | 文件版本变化、活动 IndexVersion 切换和成员移除使用不同失败状态；持久化边界重查并串行化竞态 | `test_changed_file_and_index_versions_are_reported_separately`、`test_transaction_rechecks_membership_after_acquiring_write_lock`、`test_transaction_rechecks_active_version_after_concurrent_activation` | PASS |
| S5-B21-05 | 重建索引后旧快照仍指向原版本；读取动态显示回收站/文件版本过期/索引退役、成员重加映射变化且不返回本地路径 | `test_read_marks_trash_stale_scope_and_preserves_original_index_identity`、`test_read_rejects_readded_member_mapping_for_an_older_active_snapshot` | PASS |
| S5-B21-06 | 文件永久删除清除摘录/正文哈希并断开文件/Chunk，数据库直接删除触发器同样净化；知识库永久删除清理未绑定快照 | `test_permanent_file_delete_clears_body_and_historical_kb_purge_removes_unbound_rows`、`test_database_file_delete_trigger_sanitizes_snapshot_even_without_service_helper` | PASS |

### 第二十一批数据与边界

- Alembic revision `6b3e91a0c4d7` 建立只允许 `UNBOUND` 的内部 `SourceSnapshot`。没有 owner 字段、公开 Citation 编号、Chat/Learning 消息或伪造生成结果。
- 创建只接受内部 `HybridAssessmentResult` 中受支持的 gate 候选，并在新的 SQLite 写事务中先取得写锁、再校验活动知识库/版本/成员/文件/IndexVersionInput/Chunk/FTS/EmbeddingRecord。范围、索引版本、文件源版本与来源失效分开报告。
- 快照字段从数据库现读值构建，包含版本身份、文件和解析版本、真实标题/位置、受控摘录、hash、时间与幂等键；读取不暴露绝对路径。重建索引不改写旧快照，文件软删除保留摘录并报告回收站状态，永久删除清理正文并保留允许的名称和位置说明。
- 本批没有公开 API/OpenAPI、前端、真实 Provider、真实凭据或付费请求。不代表最终回答事实正确，也未完成 AC-KB-003、Recall@10 或 10 万 Chunk 性能验收。

### 第二十一批实际验证

~~~text
backend> uv run pytest
164 passed, 131 warnings（串行运行；警告为既有依赖/Alembic 弃用提示）

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright src tests
0 errors, 0 warnings, 0 informations

backend> python -m compileall -q src tests migrations
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

repo> git diff --check
通过
~~~

没有前端/API/OpenAPI 改动，因此未重跑 UI E2E；未调用 DeepSeek、真实凭据、付费服务或真实用户资料。本批测试不覆盖 Citation owner 绑定或最终回答质量。

## 第二十二批：Citation 绑定依赖处理

- 结论：`BLOCKED`；阶段 5 保持 `PARTIAL`。本批没有代码、文档、测试或提交改动；起止本地/远端 SHA 均为 `e1766c3d173f4613e368bbb8988a343ca207738e`。
- 阻塞事实：ORM 模型、Alembic 迁移和后端实现都没有持久化 Chat/Learning owner 或其可验证知识库范围快照。`TaskAttempt` 属于后台 Worker，不能作为学习 owner；不能伪造测试 owner 或 Citation。
- 决策：Citation 绑定延期到阶段 6/7 建立真实 owner 后继续。本阻塞不影响无 owner 依赖的本地检索测试 API。

## 第二十三批验收追踪：知识库本地测试检索 API

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B23-01 | 请求问题有界且只允许 question；客户端不能指定活动版本、文件集、模型或路径 | `test_retrieval_test_rejects_invalid_id_question_and_client_scope_inputs` | PASS |
| S5-B23-02 | 只从当前活动 READY 版本返回真实 FTS5/sqlite-vec 候选；待索引成员与旧版本文件不进入结果 | `test_retrieval_test_uses_only_current_ready_version_with_pending_member` | PASS |
| S5-B23-03 | 活动索引候选包含数据库位置、受控片段与双路分数/排序解释 | `test_retrieval_test_returns_bounded_scoped_candidates_without_writes` | PASS |
| S5-B23-04 | 状态区分 `supported`、`insufficient` 与 `unavailable`；无活动索引/离线模型缺失不误报为资料不足 | `test_retrieval_test_reports_insufficient_without_creating_answer`、`test_retrieval_test_without_active_index_is_unavailable_and_skips_model`、`test_retrieval_test_missing_model_is_distinct_and_never_downloads` | PASS |
| S5-B23-05 | 查询范围仅限请求知识库，回收站排除；索引/成员在本地编码期间变化时失败关闭；FTS/vector 错误路由不同且无部分结果 | `test_retrieval_test_does_not_leak_similar_candidates_from_another_knowledge_base`、`test_retrieval_test_excludes_trashed_files_immediately`、两项 `fails_closed_if_*_changes_during_encoding`、`test_retrieval_test_marks_fts_and_vector_failures_as_unavailable` | PASS |
| S5-B23-06 | 继承 Origin/LocalSession 保护；检索路径不写库、不创建 SourceSnapshot/回答/Citation/后台任务 | `test_retrieval_test_preserves_origin_and_session_guards`、`test_retrieval_test_returns_bounded_scoped_candidates_without_writes` | PASS |
| S5-B23-07 | OpenAPI 与生成的前端类型/客户端同步；问题、候选数、摘录和 JSON 响应体均受限 | `docs/openapi/openapi.json`、`frontend/src/api/generated/openapi.ts` 与 API 集成断言 | PASS |

### 第二十三批接口与边界

- 新增 `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests`。请求只接受 1–2000 字符的 `question`；不接受客户端提供的索引版本、文件集合、Embedding 模型或绝对路径。沿用本地 Host、Origin、LocalSession Cookie 与 POST 幂等键中间件。
- 服务端先确认知识库未回收、当前活动 `IndexVersion` 为本库 `READY`、FTS/Embedding 阶段可读以及 EmbeddingConfig 符合冻结的本地模型配置。编码前捕获当前索引与成员/文件/Chunk/Embedding 范围签名，再交给既有混合查询复核；索引切换或范围变化显式返回 `unavailable/RETRIEVAL_SCOPE_CHANGED`，不返回陈旧候选。
- 复用既有 FTS5 Top 30、sqlite-vec Top 30、去重、RRF/规则重排 Top 8 与 `evidence-gate-v1`。路由故障使用严格双路语义：没有部分候选，返回 `unavailable`、错误路由与错误码。模型缺失或校验失败同样显式 `unavailable`，但归于 `embedding`，与 `insufficient` 分开。
- `LocalRetrievalQueryEncoder` 首次端点调用时才导入/初始化 ONNX Adapter；ModelManager 使用 `allow_download=false`。缺失模型不会建立 partial 安装目录，也不触网。无模型下载、DeepSeek/Provider 请求或真实用户资料。
- 响应包含 gate 状态、活动版本 ID、算法/规则版本、Chunk/File ID、文件名、真实页/幻灯片/行/heading 定位、最多 1200 字符 excerpt 和 FTS/vector rank/score、RRF/final rank 解释；最多 8 个候选，JSON 总长不超过 64 KiB。返回字段没有绝对路径、答案、Citation 编号或引用绑定。
- 本调用只读：不创建 `SourceSnapshot`、消息、Citation、后台任务或回答。没有页面变更；前端只增加 API 类型和请求 helper。

### 第二十三批实际验证

~~~text
backend> uv run pytest
176 passed, 143 warnings（最终串行全量；警告来自 Starlette/httpx、anyio 与 Alembic 弃用提示）

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright src tests
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0；38 schemas / 51 operations

frontend> npm run typecheck
通过

frontend> npm run lint
通过

frontend> npm run build
通过

repo> git diff --check
通过
~~~

此前完整运行分别观察到未修改的既有知识库 purge 用例发生异步 row-version `412`、Chunk 显式重试用例未恢复；两个用例单独重跑均通过，最终串行全量为 `176 passed`。本批没有修改这两个用例。没有 UI 页面变更，因此未跑 Playwright E2E；未调用 DeepSeek、真实凭据、付费服务或外部模型。

第二十三批结论：`PASS`；阶段 5 继续 `PARTIAL`。第二十二批 Citation owner 阻塞仍延期至阶段 6/7。下一批唯一目标：实现本地检索测试页面并调用本只读 API，不生成回答或 Citation。

## 第二十四批验收追踪：知识库详情本地测试检索页面

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B24-01 | 知识库详情页提供辅助测试检索入口，并持续显示标题、文件数和索引状态 | `KnowledgeBaseDetailPage` + `KnowledgeBaseRetrievalPanel`；真实浏览器打开 `/knowledge-bases/:id` | PASS |
| S5-B24-02 | 问题输入遵守 2000 字符上限，空/纯空白不提交，提交中防重复并显示加载状态 | `stage5-retrieval-test.test.tsx`：输入、加载和重复点击用例 | PASS |
| S5-B24-03 | 只通过现有客户端发送 `{ question }` 与路径知识库 ID，不持久化结果或触发其他任务 | 客户端请求断言、页面实现；无后端/迁移/OpenAPI schema 改动 | PASS |
| S5-B24-04 | 界面区分 `supported`、`insufficient`、`unavailable`，并区分空结果、无活动索引和模型不可用 | `stage5-retrieval-test.test.tsx` 状态矩阵；真实浏览器 `INDEX_VERSION_NOT_AVAILABLE` | PASS |
| S5-B24-05 | Top 8 候选显示真实定位、摘录、通道 rank/分数和排序解释，缺失信号显示“无” | 8 候选确定性 UI Mock；React 文本节点安全渲染断言 | PASS |
| S5-B24-06 | 错误重试保留输入；连续请求、切换问题、切换知识库和卸载时旧响应不覆盖当前结果 | `stage5-retrieval-test.test.tsx`：错误重试、问题/知识库 ID 竞态用例 | PASS |
| S5-B24-07 | 浏览器键盘流程和窄屏页面状态可感知 | 真实本地 FastAPI + Vite，`127.0.0.1:5173`；Tab/Enter 提交，`390x844` 无障碍树检查 | PASS |

### 第二十四批实现边界

- 页面入口为知识库详情 `/knowledge-bases/:id` 的辅助“测试检索”区域。面板展示知识库范围摘要、当前索引状态、问题输入、长度计数、加载/错误/重试状态和 API 返回的诊断结果。
- `supported` 只表示找到可能支持的候选资料；`insufficient` 只表示资料不足或空结果；`unavailable` 显示本地服务/索引/模型/通道/范围错误。页面不生成回答、不显示 `[1]` 引用编号、不创建 Citation 或来源快照。
- 文件名、标题路径和摘录作为不可信纯文本渲染；没有绝对路径、密钥、`dangerouslySetInnerHTML` 或浏览器持久历史。AbortController、序列号和知识库 ID 组件 key 处理旧响应竞态。

### 第二十四批实际验证

~~~text
frontend> npm test
Test Files 6 passed (6)
Tests 21 passed (21)

frontend> npm run typecheck
通过

frontend> npm run lint
通过

frontend> npm run build
通过（Vite production build）

repo> git diff --check
通过
~~~

真实浏览器使用本地 FastAPI + Vite，允许来源为 `http://127.0.0.1:5173`。创建本地空知识库并进入详情页后，测试检索入口、索引状态、问题输入和 2000 字符计数可见；用键盘 Tab/Enter 提交，真实 API 返回 `unavailable / INDEX_VERSION_NOT_AVAILABLE`，结果没有被显示为“资料不足”。在 `390x844` 窄屏视口读取无障碍树，输入、按钮和结果状态仍可感知。当前本地环境没有固定 READY 索引和可复现候选资料，Top 8、HTML 片段安全、连续请求和错误重试使用确定性 UI Mock 验证，未写成真实检索验收；截图接口不可用，因此没有记录截图证据。

本批未修改后端、数据库迁移或 OpenAPI schema，因此未重跑后端全量；第二十三批后端 API 证据仍为 `176 passed, 143 warnings`。未调用 DeepSeek、真实凭据、付费接口或私人资料。

第二十四批结论：`PASS`；阶段 5 继续 `PARTIAL`。第二十二批 Citation owner 绑定仍延期至阶段 6/7。下一批唯一目标：准备固定本地验收资料并建立可复现 READY 索引，为本地测试检索页面补充真实浏览器候选显示证据。

## 第二十五批验收追踪：固定资料 READY 索引与真实浏览器候选

| ID | 验收项 | 证据 | 结论 |
| --- | --- | --- | --- |
| S5-B25-01 | 固定样本公开、可复跑、重复执行不创建无界重复记录；数据根与默认用户数据隔离 | `docs/test-data/stage5-fixed-ready/`、`scripts/prepare_stage5_fixed_ready.py`；两轮后 3 files / 3 knowledge bases / 13 tasks，counts unchanged | PASS |
| S5-B25-02 | 固定模型来源/revision/hash 可校验；不下载、不调用 Provider、不使用 Mock 伪造 READY | `backend/model-cache/manager-validation` 离线 ModelManager 源缓存和隔离副本均 `READY`；report 中记录 BAAI/Xenova revision/fingerprint | PASS |
| S5-B25-03 | 文件导入、解析、成员、预处理、Chunk、真实 ONNX Embedding、FTS、产物复核和原子激活闭环 | 主库 2/2/2/2，干扰库 1/1/1/1（Chunk/Embedding/vector/FTS）；四阶段任务检查点 `COMPLETED`，主库与干扰库活动版本均 READY | PASS |
| S5-B25-04 | 检索仅返回当前知识库范围；回收站与其他库不泄漏；资料外问题不生成答案或伪引用 | 主库 API 返回主文件，干扰库 API 返回干扰文件；回收站文件名/ID/专属摘录未出现；资料外为 `insufficient` 且响应无 `answer`/`citations` 字段 | PASS |
| S5-B25-05 | 真实浏览器通过网络请求命中真实 API，桌面/窄屏和键盘均展示 READY 候选 | Playwright Chromium `1440x1000`、`390x844`，Tab 到按钮后 Enter；真实响应 ID/IndexVersion/文件名/摘录/行定位核对通过，`2 passed` | PASS |
| S5-B25-06 | 未建索引与模型不可用不误报成功；不为凑 `supported` 降低门槛 | 每次准备运行由独立空诊断库验证 `unavailable / INDEX_VERSION_NOT_AVAILABLE`；现有 `test_retrieval_test_missing_model_is_distinct_and_never_downloads` 覆盖离线模型缺失。目标/干扰候选实际 `insufficient / VECTOR_SIMILARITY_BELOW_THRESHOLD` 并保留原阈值 | PASS |

### 第二十五批固定资料与隔离范围

- 可复跑命令（PowerShell，从 `backend` 运行）：`uv run python scripts/prepare_stage5_fixed_ready.py --data-dir "$env:TEMP\mindmate-ai-stage5-fixed-ready"`。脚本在专用目录创建所有权标记；非空且无标记的目录拒绝接管。脚本只读取 Git 忽略的固定模型缓存并将经校验副本写入隔离 `models`，不会读写 `%LOCALAPPDATA%\MindMateAI`，也不执行清理。
- 三份无私人内容资料为 `服务超时策略.txt`（主库，30 秒）、`相似服务超时策略.txt`（独立干扰库，47 秒）与 `回收站范围验证.txt`（READY 后经文件回收站 API 软删除，专属标识 `TRASH-9274`）。另有一个空诊断知识库，每轮用于核验无活动索引失败状态。
- 使用本地固定 BGE：`BAAI/bge-small-zh-v1.5@7999e1d3359715c523056ef9478215996d62a620`，ONNX `Xenova/bge-small-zh-v1.5@75c43b069aac4d136ba6bc1122f995fedcfd2781`，MIT，manifest fingerprint `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，总大小 `95,291,718` 字节。源缓存和隔离副本均经过固定 manifest 大小/SHA-256/配置验证；本批没有联网或下载。
- 首次运行暴露各索引阶段是独立持久任务；仅完成 `INDEX_PREPROCESS` 不会自动入队后续任务。准备脚本按现有 enqueue 服务顺序启动 `INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS`，由现有 Workers 和 `IndexActivationWorker` 完成；不直接 SQL 写入业务状态或伪造 READY。
- 每次完整准备连续执行两遍。验证前后文件、知识库和任务总数一致：3 files、3 knowledge bases、13 tasks（3 FILE_IMPORT、2 KNOWLEDGE_MEMBERSHIP_ADD、2 INDEX_PREPROCESS、2 INDEX_CHUNK、2 INDEX_EMBED、2 INDEX_FTS）。逐输入状态为 `PREPARED/CHUNKED/EMBEDDED/INDEXED`。

### 第二十五批真实检索结果

- 主库当前活动版本：主库两个成员各 1 Chunk、1 EmbeddingRecord、1 sqlite-vec 向量和 1 FTS 映射；第二个回收站成员仍在版本物理快照中，但当前检索范围即时排除它。FTS5 `integrity_check`、版本一致性、向量 ID 集合、SHA-256、512 维、有限值与单位范数检查全部通过。两个知识库的 `INDEX_PREPROCESS/INDEX_CHUNK/INDEX_EMBED/INDEX_FTS` 任务均为 `COMPLETED`，IndexVersion 和知识库均为 `READY`。
- `API 单次请求超时时间是多少秒？` 返回 `服务超时策略.txt`、真实段落摘录和 `line_start=1`；当前实际 gate 状态是 `insufficient`，原因 `VECTOR_SIMILARITY_BELOW_THRESHOLD`，余弦相似度约 `0.5867`。干扰库问题返回另一库的 `相似服务超时策略.txt` 与 `47 秒`，余弦相似度约 `0.6568`，同样为 `insufficient`。按提示词要求保留既有 `0.82` 阈值，不改算法；页面如实显示“资料不足”，同时展示真实候选。
- 查询回收站专属标识没有返回回收站文件的 file ID、文件名或摘录。资料外问题 `南极冰芯中氮同位素的具体丰度百分比是多少？` 返回 `insufficient / NUMERIC_ANSWER_VALUE_NOT_FOUND`；检索响应可能保留主库内诊断候选，但没有生成 `answer` 或 `citations` 字段，UI 明确显示“资料不足”，不显示正式引用。未将候选诊断当成答案。
- E2E 截图：`%TEMP%\mindmate-ai-stage5-fixed-ready\evidence\retrieval-desktop.png`、`retrieval-narrow.png`、`retrieval-out-of-scope.png`。真实浏览器 API 请求为 `POST /api/v1/knowledge-bases/{id}/retrieval-tests`；Chromium 桌面 `1440x1000`、窄屏 `390x844` 页面无横向溢出，候选文件名、摘录和来源行号与网络 JSON 一致。键盘流程从问题文本框 Tab 到按钮，再按 Enter。

### 第二十五批实际验证

~~~text
backend> uv run python scripts/prepare_stage5_fixed_ready.py --data-dir "$env:TEMP\mindmate-ai-stage5-fixed-ready"
PASS；模型 READY；两个活动 IndexVersion READY；第二轮记录数不变；真实 API 范围/回收站/资料外检查通过

backend> uv run pytest
176 passed, 143 warnings（串行全量）

backend> uv run ruff check src tests scripts
All checks passed

backend> uv run pyright src tests scripts/prepare_stage5_fixed_ready.py
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations scripts
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

frontend> npm run typecheck
通过

frontend> npm run lint
通过

frontend> npm test -- --run
Test Files 6 passed; Tests 21 passed

frontend> npm run build
通过（Vite production build）

frontend> npm run test:e2e -- e2e/stage5-ready-retrieval.spec.ts
2 passed；Playwright Chromium + real local API

repo> git diff --check
通过
~~~

没有数据库迁移、公开 API/OpenAPI schema 或 Provider 改动；没有 DeepSeek、真实凭据、付费外部服务或个人资料。固定样本不等于 Recall@10、10 万 Chunk 性能、门控阈值校准或 AC-KB-* 全量验收。第二十五批 `PASS`；阶段 5 继续 `PARTIAL`；Citation owner 仍待阶段 6/7。下一批唯一目标：用固定真实 ONNX 中文查询样本评估现有 `evidence-gate-v1` 判定分布，不先调整阈值。

## 第二十六批评测追踪：真实 ONNX 证据门控基线

| 项目 | 证据与结果 |
| --- | --- |
| 批次/阶段状态 | 第二十六批 `PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `3ef9a33adcdae5adb06e6a6835d44fdbbf84ed3d`。 |
| 固定样本 | 31 条核心人工标注、2 条 `needs_review`；覆盖直问、改写、实体/编号、近似编号、错误数值、无答案、短词干扰、跨知识库、回收站、复合问题和显式冲突。真值在查询前写入 `docs/test-data/stage5-fixed-ready/evidence-gate-v1-queries.json`，不从 gate 输出反推。 |
| 真实模型与索引 | BAAI `7999e1d3359715c523056ef9478215996d62a620` + Xenova ONNX `75c43b069aac4d136ba6bc1122f995fedcfd2781`，manifest fingerprint `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。三个 READY 库使用实际 FTS5、sqlite-vec 和本地 ONNX；DeepSeek 未调用。 |
| 混淆表 | 核心样本 31：TP `0`、FN `16`、FP `0`、TN `15`；全部 33 个请求为 `insufficient`，`unavailable` 为 0。16 个 FN 均在 Top 8 找到标注支持文件，召回缺失型 FN `0`；假阳性为 0，跨范围候选为 0。 |
| FN 顶层原因 | `VECTOR_SIMILARITY_BELOW_THRESHOLD` 11 条；`NUMERIC_ANSWER_VALUE_NOT_FOUND` 3 条；`COMPOSITE_OR_OPEN_LIST_QUESTION` 2 条。冲突、无答案、错误编号、短词不足、跨库和回收站用例均正确拒答。 |
| Top 8 排名信号 | 共 101 条候选：Vector 101、FTS 2（全部同时命中 Vector）、Vector-only 99、FTS-only 0。两条 FTS 命中来自 `API?` / `ID?` 短词拒答。最终 rank、FTS/Vector 原始 rank、BM25 与余弦距离/相似度校验全部通过。 |
| 相似度 | Top 8 cosine similarity min/median/max：`0.3356 / 0.4835 / 0.7127`；可回答查询的标注证据 Top 8 覆盖 `16/16`。该 Top 8 指标不代表 Recall@10。 |
| 离线门槛敏感性 | 已观察 Top 8 候选上模拟 `0.65/0.70/0.75/0.82/0.85`，所有混淆表仍为 TP `0`、FN `16`、FP `0`、TN `15`。没有更改运行时 `0.82` 或其他 gate 参数；单独调低余弦阈值没有证据支持。 |
| 稳定性与写入 | 最终版本两次独立运行各含两次内部复跑；每次内部结果签名稳定，跨运行 SHA-256 签名同为 `c5d216439163910865464f3130edc1eafd18a445978c2d3ca42cafb0aabd4931`。检索前后均为 9 files / 4 knowledge bases / 24 tasks；查询没有写入数据。 |
| 隔离和报告 | 原 `%TEMP%\\mindmate-ai-stage5-fixed-ready` 正被本地浏览器验收服务使用；本批使用新所有权标记目录 `%TEMP%\\mindmate-ai-stage5-evidence-gate-v1`。真实 JSON 输出保存在隔离根 `stage5-evidence-gate-v1-report.json`，模型文件和临时数据库不进 Git。 |
| 下一步 | 单一最小目标：用人工查询集测量中文自然问句的 FTS5 命中与 hard-negative 分布，定位双路候选召回问题；不调整证据门槛。 |

### 第二十六批实际验证命令

~~~text
backend> uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1" --repeat 2
两次独立运行均 COMPLETED；每次 31 core + 2 needs_review；内部签名 stable=True

backend> uv run pytest tests/test_stage5_evidence_gate_eval.py
3 passed

backend> uv run pytest
179 passed, 143 warnings (串行全量，2:22)

backend> uv run ruff check scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py tests/test_stage5_evidence_gate_eval.py
All checks passed

backend> uv run pyright scripts/evaluate_stage5_evidence_gate.py scripts/prepare_stage5_fixed_ready.py tests/test_stage5_evidence_gate_eval.py
0 errors, 0 warnings, 0 informations

backend> uv run ruff check src tests scripts
All checks passed

backend> uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations scripts
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

repo> git diff --check
通过
~~~

这套小样本用于诊断现有证据门控，不宣称达到发布门槛 Recall@10 `>=0.85`、引用定位正确率、资料不足拒答召回率或最终回答质量。没有调整检索规则、索引架构或 Citation；没有 DeepSeek、真实凭据、付费 API 或个人资料。

## 第二十七批：中文 FTS 召回修复与困难负例回归

> 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。本节记录第二十六批基线之后的最小 FTS 查询修复与真实 ONNX 回归，不改变证据门控生产参数。

### 根因与修复

第二十六批已经证明 16 条 FN 的人工支持文件都在向量 Top 8，且没有召回缺失型 FN；但 101 条 Top 8 候选只有 2 条带 FTS 信号。复核真实 SQLite FTS5 行后确认，索引侧的连续汉字二元词投影是正确的，问题在查询侧：整段中文自然问句被拼成一个带空格的引号短语。FTS5 因而要求每个问句二元词连续且全部出现，原文没有“是多少/是否/等多久”等问句脚手架时整段失配。

修复位于 `backend/src/mindmate/infrastructure/fts5.py`：

- 保留 NFKC 规范化、SQLite 参数绑定和逐词引号转义；拉丁词项、数字和编号片段继续精确 `AND`，错误数字不会被中文 OR 组绕过。
- 连续中文段改为有界二元词 `OR` 组，句末语气词与问题脚手架只从 FTS fallback 中移除；原始问题仍传给排序和证据门控。
- MATCH 结果在 SQL 读取实际索引侧 token 后做确定性最低命中过滤：普通中文段至少命中 2 个二元词，含数字/编号的查询段至少命中 1 个；原始扩展最多为请求 Top-K 的四倍且不超过 120 行，最终仍返回 FTS Top 30。
- 没有新增 schema/Alembic 迁移；索引构建、`unicode61`、FTS 映射、旧 READY 索引读取和原子激活边界保持不变。

### 真实 FTS 前后数据

使用同一固定 READY 数据、同一真实本地 ONNX 模型和同一 `evidence-gate-v1` 配置，第二十六批基线与本批首轮 Top 8 对比如下：

| 指标 | 修复前 | 修复后 |
| --- | ---: | ---: |
| Top 8 候选总数 | 101 | 101 |
| 含 FTS 排名候选 | 2 | 20 |
| 双路命中 | 2 | 20 |
| Vector-only | 99 | 81 |
| FTS-only | 0 | 0 |
| 核心混淆表 TP/FN/FP/TN | 0/16/0/15 | 0/16/0/15 |

代表案例实际从 FTS5 返回正确范围候选：`API 单次请求超时时间是多少秒？` 返回主库 `服务超时策略.txt`；`演练系统 API 单次请求超时时间是多少秒？` 返回干扰库 `相似服务超时策略.txt`；`演示作业的编号是什么？` 和 `CACHE-PROXY-K3 指什么组件？` 返回对应评测文件。`31 秒`、`18 秒`、错误编号等近失配查询没有 FTS 命中。报告在隔离根 `%TEMP%\\mindmate-ai-stage5-evidence-gate-v1-r27\\stage5-evidence-gate-v1-report.json` 保存查询 token、实际 MATCH 表达式、实际存储 token、关键词排名、向量候选、最终 Top 8 和门控理由。

### 核心集与困难负例

- 旧 31 条核心人工标注保持 TP `0`、FN `16`、FP `0`、TN `15`。16 条 FN 都在 Top 8 找到标注支持文件，仍由严格 `evidence-gate-v1` 拒答；本批没有调低 `0.82` 向量阈值，也没有修改门控判定策略。两次独立运行各执行 `--repeat 2`，核心结果签名稳定。
- 新增 `docs/test-data/stage5-fixed-ready/evidence-gate-v1-hard-negatives.json`，7 条独立人工标注 hard negatives 覆盖同名跨库 `30/47 秒`、错误数字、相同术语但无事实、相反表述和回收站。独立混淆表 TN `7`、FP `0`，跨范围候选 `0`；所有 READY hard-negative 查询均为 `insufficient`，没有 `unavailable`。
- 失效索引安全检查不混入混淆表：空诊断库两轮均为 `unavailable / INDEX_VERSION_NOT_AVAILABLE`，候选数 `0`。

### 验收命令与结果

```text
backend> uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1-r27" --repeat 2
COMPLETED；核心 0/16/0/15；hard-negative TN 7 / FP 0；两套签名 stable=True；失效索引检查通过

backend> uv run pytest tests/test_stage5_fts_worker.py tests/test_stage5_evidence_gate_eval.py -q
通过

backend> uv run pytest
181 passed, 143 warnings（串行，约 2:26）

backend> uv run ruff check src tests scripts
All checks passed

backend> uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations scripts
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

repo> git diff --check
通过
```

首次尝试复用旧评测目录因其所有权标记已缺失而被保护逻辑拒绝，未接管、删除或覆盖旧数据；随后使用带新所有权标记的 `r27` 隔离根完成准备和评测。未改前端，因此未运行前端门禁；未调用 DeepSeek、真实凭据、付费 API 或私人资料。固定小集不替代 Recall@10、引用定位、10 万 Chunk 性能或 AC-KB-* 全量验收。

下一批唯一目标：在不放松证据门控、不引入 Provider 的前提下，针对仍保留的 16 条 FN 建立人工可解释的门控/答案质量校准方案；阶段 5 保持 `PARTIAL`。

## 第二十八批：证据门控规则校准与正负例回归

> 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。本节记录在第 27 批真实 ONNX/FTS 基线之上的门控校准，不改变知识库范围、索引架构、FTS 召回范围、公开 API、Provider 或数据库 schema。

### 进场与复核

- 分支：`feat/v1-bootstrap`；进场本地与 `origin/feat/v1-bootstrap` SHA 均为 `b2ddc62bade9517272e06d761fd5f30e392bee92`；工作区干净。
- 固定真值：保留原 `31` 条核心人工标注、`2` 条 `needs_review`、`7` 条独立 hard negatives；不根据本批输出改写标签。允许支持文件、事实、拒答理由仍来自 `docs/test-data/stage5-fixed-ready/evidence-gate-v1-queries.json` 和 `evidence-gate-v1-hard-negatives.json`。
- 基线复跑：在 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1-r28-baseline` 使用同一模型 manifest、真实 ONNX、READY 准备流程和 `--repeat 2` 复跑第 27 批结果，核心 `TP 0 / FN 16 / FP 0 / TN 15`，hard negatives `TN 7 / FP 0`。16 条 FN 均有允许支持文件在 Top 8；根因不是召回缺失。

### 规则修复

- 默认 `min_vector_similarity=0.82` 保留；新增集中校验参数 `min_fts_similarity=0.50`、`min_semantic_similarity=0.60`、语义锚点最小数量 `2`、覆盖率 `0.50`，仍属于 `evidence-gate-v1` 的可审计配置。
- FTS 例外只在候选同时具备 FTS/Vector 双路、原始 rank 不晚于 5、最终 rank 不晚于 3、正文至少两个问题锚点或完整短语、数值/单位/编号语境和候选身份均通过时放行；信号记录 `FTS_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD`，不是单独降低余弦门槛。
- Vector-only 例外要求相似度至少 `0.60`、至少两个去除问题脚手架后的语义锚点、覆盖率至少 `0.50`、数值/单位/编号语境通过；信号记录 `SEMANTIC_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD`。纯余弦、标题单独命中、同文件在 Top 8、任意两字词和无语境数字不能放行。
- 显式数字必须以相同单位在正文锚点附近出现；错误值/单位使用 `QUERY_NUMERIC_VALUE_NOT_FOUND`。完整编号缺失使用 `QUERY_IDENTIFIER_NOT_IN_BODY`。否定断言与正文肯定事实冲突使用 `QUERY_CLAIM_CONTRADICTED`；只有“不定义”而问题要求定义事实使用 `QUERY_NEGATIVE_FACT_ONLY`。复合问题按 `以及/并且/同时` 拆分，缺任一子句继续 `COMPOSITE_OR_OPEN_LIST_QUESTION`；多来源数值/极性矛盾继续 `CONFLICTING_EVIDENCE`。
- `evaluate_stage5_evidence_gate.py` 增加 `gate_signal_audit`：逐条保留候选身份、正文锚点、锚点覆盖率、FTS/Vector rank、相似度、编号命中、支持状态和 reason code；不扩大公开检索测试 DTO。

### 逐条 FN 证据

- `S5-EG-001`、`002`、`003`、`005`、`011`、`012`：`服务超时策略.txt` 行 `1-12`，FTS/Vector rank `1/1`，真实余弦 `0.5545–0.6213`，分别定位 30 秒、超时记录、后台任务排除和离线不外发片段；走 FTS 正文例外。
- `S5-EG-010`：同一文件行 `1-12`，同时命中普通请求 30 秒和后台任务不共用该值两个子句；通过完整复合子句检查。
- `S5-EG-013`：`相似服务超时策略.txt` 行 `1-9`，rank `1/1`，余弦 `0.6568`，正文明确演练系统 47 秒；走 FTS 正文例外。
- `S5-EG-014`：`相似服务超时策略.txt` 行 `1-9`，Vector rank `1`、无 FTS、余弦 `0.6013`，正文同时包含演练环境/API/47 秒事实；走 vector-only 语义例外。
- `S5-EG-016`、`018`、`020`、`029`：`阶段5评测_参数记录.txt` 行 `1-4`，正文定位 OPS-R7-204、17 秒和每批 6 个文件；`029` 两个子句均在同一 Chunk 中通过。
- `S5-EG-021`、`022`：`阶段5评测_组件记录.txt` 行 `1-3`，正文定位 `CACHE-PROXY-K3`、青栎缓存代理和 12 分钟诊断窗口；完整编号命中后走 FTS 正文例外。
- `S5-EG-028`：`阶段5评测_短词干扰.txt` 行 `1-2`，正文明确说明不定义 API 请求时限；问题询问文件是否说明该事实，因此通过 FTS 正文例外，不能推广为 API 时限事实。

### 真实前后结果

最终使用 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1-r28-final`，同一真实 ONNX manifest 和 `--repeat 2`：

| 数据集 | 校准前（r28-baseline） | 校准后（r28-final） |
| --- | ---: | ---: |
| 核心 31 条 TP/FN/FP/TN | `0/16/0/15` | `16/0/0/15` |
| hard negatives 7 条 TN/FP | `7/0` | `7/0` |
| needs_review | `2`（单列） | `2`（单列） |
| Top 8 候选总数 | `101` | `101` |
| FTS 命中/双路命中/Vector-only | `20/20/81` | `20/20/81` |
| 失效索引检查 | `unavailable`、0 候选 | `unavailable`、0 候选 |

两轮内部结果签名稳定，查询前后资源计数均为 `9 files / 4 knowledge bases / 24 tasks`；最终报告保存 `gate_signal_audit` 和全部候选摘录/定位，不进入 Git。固定合成样本不证明 Recall@10、引用定位正确率、资料不足拒答召回率或最终回答质量。

### 验收命令与结果

```text
backend> uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1-r28-final" --repeat 2
COMPLETED；两轮核心均 16/0/0/15；两轮 hard-negative 均 TN 7 / FP 0；stable=True；资源计数不变；失效索引检查通过

backend> uv run pytest tests/test_stage5_evidence_gate.py tests/test_stage5_evidence_gate_eval.py -q
18 passed

backend> uv run pytest
186 passed, 143 warnings（串行，142.37 秒）

backend> uv run ruff check src tests scripts
All checks passed

backend> uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src tests migrations scripts
通过

backend> uv run alembic heads
6b3e91a0c4d7 (head)

repo> git diff --check
通过
```

没有前端改动，因此未运行前端门禁；没有 DeepSeek、真实凭据、付费 API 或私人资料。下一批唯一目标：在真实 Chat/Learning owner 可核验后建立服务端 Citation 绑定准入，不生成模型回答、不伪造 owner；阶段 5 保持 `PARTIAL`。
