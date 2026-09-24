# V1 开发进度

## 阶段 0

- 状态：`COMPLETED`
- 基线提交：`bdf40c2 docs: establish v1 development baseline`
- 阶段提交：`114345c chore: establish reproducible development baseline`
- 已完成：需求/归档切换、React/Vite 工作区、FastAPI health/ready/version、npm/uv lock、PowerShell 脚本、CI、基础测试与质量配置。
- 验收证据：前端 lint/typecheck/test/build 通过；后端 pytest（2 passed）、Ruff、Pyright、OpenAPI 3.1 检查通过；health/ready 实际返回 `ok/ready`；浏览器验证首页和 `/chat` 路由渲染。

## 阶段 1

- 状态：`COMPLETED_WITH_RELEASE_GAPS`
- 阶段提交：`741ba6c chore: validate windows ai and vector runtime`
- 必须验证：sqlite-vec、ONNX、Credential Manager、随机回环端口、Mock SSE、PyInstaller 和干净 Windows 启动。
- 当前结果：前 7 项通过；干净 Windows 环境和正式 Inno Setup 尚未执行，详见 `docs/test-reports/stage-1-spike.md`。

## 阶段 2

- 状态：`COMPLETED`
- 阶段提交：`0b19795 feat: build secure local application shell`
- 已完成：本地数据目录、单实例锁、SQLite PRAGMA/Alembic、随机 HttpOnly 会话、Host/Origin 校验、Problem JSON、request ID、幂等头、系统端点、OpenAPI 导出、前端 API 客户端和路由应用壳。
- 验收证据：后端 7 tests、Ruff、Pyright；前端 lint/typecheck/test/build；浏览器验证首页和 `/chat` 路由；本地 Session/health/Problem JSON 联调通过。

## 阶段 3

- 状态：`COMPLETED`
- 阶段提交：`02a32b8 feat: add persistent data task and recovery foundation`
- 已完成：核心数据模型、Alembic 0002、BackgroundTask lease/checkpoint/恢复、备份 manifest/hash/敏感目录排除。
- 验收证据：迁移往返通过；后端 9 tests、Ruff、Pyright 通过；详见 `docs/test-reports/stage-3-data-task-backup.md`。
- 入口：SQLite 业务实体、持久 BackgroundTask、恢复检查点和备份 manifest。

## 阶段 4

- 状态：`PASS`
- 阶段提交：`bc30e1f feat: implement secure local file management`
- 收口审计起点：`9e0174a docs: record stage 4 file management evidence`
- 收口修复提交：`3b29d22 fix: close stage 4 file management gaps`
- 第四批交接提交：`0448d5b docs: establish stage 4 handoff baseline`
- 第五批：新增 Alembic revision `9f3a1c7e2b40`；Folder/Tag 持久 `row_version`；重命名、移动、删除、恢复和 Tag 修改/删除的原子乐观锁；FileRecord 解析失败阶段、稳定错误 ID、重试次数；OpenAPI 与前端生成类型和冲突交互同步。
- 第六批：复用 `BackgroundTask` 实现持久文件解析 Worker；导入/重新处理请求提交后立即返回排队状态；任务领取使用原子条件更新和租约，支持过期恢复、应用关闭中断、同文件活跃任务去重和有限重试；解析结果发布前校验文件存在、内容哈希和任务状态；Windows 解析子进程接入 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存硬上限，默认 `512 MiB`；新增 `GET /api/v1/tasks/{task_id}`，OpenAPI 3.1 同步为 `25 schemas / 38 operations`。
- 第七批：完成文件列表搜索/筛选/排序状态 URL 化，详情返回保留原查询串和滚动位置；返回前刷新列表查询，避免解析 Worker 更新 `row_version` 后旧缓存触发误报冲突；新增组件回归和稳定化的浏览器生命周期等待。
- 已完成：文件夹、标签、文件 CRUD；multipart 导入校验；流式 staging；SHA-256 去重；同内容复用/独立记录；TXT/Markdown 解析；PDF/DOCX/PPTX 隔离子进程解析；正文搜索；受控内容读取；递归回收站恢复/永久删除；嵌套目录、筛选、批量操作、详情编辑和文件夹回收站前端；详情返回状态恢复。
- 验收证据：后端 `30 passed`（阶段 4/迁移/Worker 定向 `21 passed`）、Ruff、Pyright、Python compileall；前端 lint/typecheck、Vitest `8 passed`、build；OpenAPI 3.1 `25 schemas / 38 operations` 与前端类型同步；空库和已有数据迁移往返、SQLite quick check 通过；真实 FastAPI 后端 + Vite 代理的阶段 4 Playwright `1 passed`；Windows Job Object 创建、配置、进程分配和清理受控冒烟通过。详见 `docs/test-reports/stage-4-file-management.md`。
- 阶段 4 最终追踪：`19/19` 必须项通过，`0` 项未通过；正式恶意文档集、资源耗尽和干净 Windows 安装包列为发布候选保留项，不回填为阶段 4 缺陷。
- 下一批次：阶段 5：知识库、Embedding 与 RAG；本批次不启动。
- 后续边界：FTS5、知识库索引、Embedding、向量与 RAG 仍属于阶段 5–6，本批次未提前实现。

## 阶段 5

- 状态：`PARTIAL`
- 第八批起点：`75a0653877b7f627bc254a859232689c19872777`
- 第九批起点：`6fd248978b84bcf96702eda081ed05469dab4bf2`
- 第十批起点：`3025a5abc2a89cca97edd9cadfbeb87bccdc985f`
- 已完成：空知识库创建、正常列表、详情、编辑和回收站；已导入文件批量加入/移出、多库共享、幂等重复提交、移出重加、逐项失败隔离与文件所属知识库查询。
- 数据与并发：Alembic revision `c7d5e8a1f204` 增加 `icon`/`color`；编辑、删除和恢复使用原子 `row_version` 条件更新，冲突返回 412。
- 任务：独立成员准入 Worker 复用 SQLite `BackgroundTask`、原子领取、租约、检查点、取消和关闭恢复；解析 Worker 与成员 Worker 按任务类型隔离。父任务完成只表示成员关系已持久化，不表示索引完成。
- 第十批数据：Alembic revision `d91f4a6b2c30` 增加版本化 ChunkingConfig、EmbeddingConfig、IndexVersion 和 IndexVersionInput；切片默认参数明确采用约 500/80 Unicode 字符，配置和解析集合均保存稳定 SHA-256 指纹。
- 第十批任务：新增独立 `INDEX_PREPROCESS` Worker，在请求外冻结一致输入快照并逐文件记录准备、跳过和失败；支持幂等、租约接管、检查点续跑、取消及成员/解析修订变化复核。预处理完成后仍为 `BUILDING`，不激活索引。
- 第十一批数据：Alembic revision `f2c7a1d8e904` 增加文件级版本化 `Chunk`，以文件、解析修订和切片配置形成唯一版本；保存标题路径、可用页/幻灯片/行定位、正文哈希和 Unicode 字符长度，真实 tokenizer 计数保持 NULL。Chunk 不与知识库绑定，满足版本条件时由多个知识库复用。
- 第十一批切片：新增结构优先字符切片器，目标约 500 字符、重叠约 80 字符；保护标题、段落、代码/表格、页和幻灯片边界，长结构块在自然边界拆分；DOCX v2 解析元数据标记真实可读出的标题、列表、段落、代码样式及表格行。
- 第十一批任务：新增独立 `INDEX_CHUNK` 持久 Worker，消费同一 `IndexVersion` 中 `PREPARED` 输入；逐文件 Chunk 集与检查点事务原子发布，支持取消检查、租约续期/过期接管、应用关闭续跑、显式失败重试及文件永久删除竞态。任务完成只代表切片阶段结束，索引保持 `BUILDING` 且不激活。
- 生命周期与契约：文件或递归文件夹永久删除时按准确 `file_id` 清理 Chunk；保留其他文件/知识库仍可复用的 Chunk。任务详情 OpenAPI 增加 `task_type`、`index_version_id`，生成契约为 34 schemas / 50 operations。
- 前端：知识库详情使用真实文件选择、成员列表、任务轮询、逐项结果和移出；解析中/失败、待索引与不可检索状态明确；刷新后恢复数据库状态。
- 验收证据：第十一批历史结论 `PASS`；当时后端 `60 passed`、真实阶段 4/5 Playwright 各 `1 passed`。完整历史与第十二批增量证据见 `docs/test-reports/stage-5-knowledge-base-foundation.md`。
- 阶段 5 初始未完成：FTS5、向量 Top-K 查询、增量/原子索引激活、混合检索、引用和 RAG；后续批次逐项补齐，阶段整体仍为 `PARTIAL`。

### 第十二批：固定 ONNX 模型来源与本地推理

- 固定上游模型 `BAAI/bge-small-zh-v1.5` revision `7999e1d3359715c523056ef9478215996d62a620`。上游固定 revision 没有 ONNX；本批选用 `Xenova/bge-small-zh-v1.5` revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`，并记录其上游 MIT 许可、第三方来源及 license metadata 缺失情况。各运行/参考文件 SHA-256 见模型来源契约。
- 新增本地模型管理器与 ONNX Adapter。管理器固定 URL/revision、大小和 SHA-256，使用 `.partial`、路径/跳转/超时限制、取消、错误恢复和原子发布；Adapter 固定查询前缀、masked mean pooling、L2 normalization、512 维、CPU、批量/CPU 上限，超限输入显式报错。失败 fixture 不下载在线模型，应用启动不加载运行时。
- 仅新建的默认 Embedding 配置写入复合 model revision/artifact fingerprint；历史 `model_revision=NULL` 行保留。没有创建迁移、EmbeddingRecord、持久 Embedding Worker，也没有接通索引激活/检索。
- Windows 11 x64、Python 3.12.11 实测：onnxruntime 1.30.0 CPU、tokenizers 0.23.2；与官方 safetensors 权重对照固定中文 query/document 输入，输出 `(3,512)`，最大绝对误差 `1.1175871e-7`、最小余弦相似度 `1.0`，四位小数全批向量哈希一致。真实固定 revision 下载/校验状态 `READY`，离线复用后 adapter 输出有限且单位范数。
- 验收：后端全量 `81 passed`、Ruff、Pyright `0 errors`、compileall；前端 lint/typecheck、Vitest `13 passed`、production build；阶段 4/5 真实后端 Playwright `2 passed`；OpenAPI 无变化。详细门禁与来源在阶段 5 测试报告和索引预处理契约。

### 第十三批：持久 Embedding 与向量写入

- 数据：Alembic revision `a81f3c6d2e90` 新增 `EmbeddingRecord`、`IndexVersion.embedding_status`、逐输入 Embedding 状态/失败原因/数量/时间检查点，并以 SQLite 部分唯一索引限制至多一个 `INDEX_EMBED` 任务处于有效运行租约。
- Worker：新增独立持久 `INDEX_EMBED`，只消费同版本仍有效的 `PREPARED + CHUNKED` 文件输入；每文件分批最多 16，支持租约续期/过期接管、取消、关闭中断恢复、逐文件失败与显式失败重试。只有固定 EmbeddingConfig、BAAI/Xenova revision 和 tokenizer/artifact 指纹完全匹配且本地模型文件 hash 校验通过，才懒加载 CPU ONNX；不会下载模型、切换模型或调用外部 API。
- 复用与持久性：EmbeddingRecord 以 `chunk_id + embedding_config_id` 唯一并跨知识库复用推理；sqlite-vec 文件按配置与 IndexVersion 隔离。先持久化向量 hash，再幂等 upsert 512 维实际向量，最后事务发布 READY 元数据和文件检查点。重启可按向量记录 ID、Chunk ID 与 hash 对账并补完写后中断，不重复推理或产生重复向量。
- 生命周期：成员、知识库/文件回收站、成员加入时间、内容 hash、解析修订、切片配置、Embedding 配置在推理前和发布前复核；失效结果不标成功。永久删除知识库清理仅属于该 IndexVersion 的向量空间并保留可复用 Chunk/EmbeddingRecord；文件永久删除清理对应向量映射、EmbeddingRecord 和 Chunk。
- 状态与边界：完成只表示“Embedding 已生成并持久化”。`IndexVersion.status=BUILDING`、`active_index_version_id` 不变，知识库成员仍 `available_for_retrieval=false`；本批未做 FTS5、向量 Top-K、激活、混合检索、引用或 RAG。无 API schema / 前端变化。
- 验收：后端 `97 passed`、Ruff、Pyright `0 errors`、compileall、离线锁文件校验、Alembic 往返与 `quick_check=ok`；真实 Windows sqlite-vec 文件写入/读取及现有固定本地 ONNX cache 的离线 Worker 集成通过；阶段 4/5 Playwright `2 passed`。详细证据见 `docs/test-reports/stage-5-knowledge-base-foundation.md` 和 `docs/project/index-preprocessing-contract.md`。
- 下一批唯一目标：为同一 `IndexVersion` 增加持久 FTS5 索引生成与逐输入检查点；不做 Top-K 查询、混合检索、索引激活、引用或 RAG。

### 第十四批：持久 FTS5 Chunk 投影

- 数据：Alembic revision `d60f2e8a7c31` 增加 IndexVersion/逐输入 FTS 状态与计数检查点、`fts_chunk_map` 版本映射、FTS5 `index_chunk_fts` 虚表和 INDEX_FTS 单运行租约约束。
- Worker：新增独立可恢复 `INDEX_FTS`；只消费仍有效的 `PREPARED + CHUNKED` 输入，验证知识库/成员、加入时间、文件回收站、内容哈希、解析修订、Chunk 集和切片配置。逐文件写入、映射、输入检查点和任务进度在同一 SQLite 事务内提交；支持租约过期接管、取消、单项稳定失败和显式失败重试。
- 版本及删除：FTS 按 `IndexVersion + Chunk` 映射隔离，不覆盖旧版本；知识库永久删除只清其版本映射，文件永久删除清目标文件映射/输入并将仍包含其他文件的未激活版本标记 `NEEDS_REBUILD`，不删除其他文件可复用 Chunk/EmbeddingRecord/向量。
- 分词与重建：虚表采用 `unicode61 remove_diacritics 2` 与 BM25；连续汉字另外生成重叠双字词和单字辅助列，固定中文长短查询与英文词通过。映射一致性检查及 FTS5 内部完整性检查分开；`rebuild=true` 清目标版本派生行并从权威 Chunk 重建。
- 状态边界：FTS 完成只表示关键词投影完成；`IndexVersion.status` 保持 `BUILDING`，活动版本不变，`available_for_retrieval=false`。没有公开搜索 API、向量 Top-K、RRF、激活、引用、RAG、OpenAPI 或前端变更。
- 验收：后端 `105 passed`；Ruff、Pyright `0 errors`、compileall 通过；空库和既有数据迁移、FTS-only 降级/再升级保留 Chunk/EmbeddingRecord、重建和 `quick_check=ok` 通过。
- 阶段结论：第十四批 `PASS`；阶段 5 继续 `PARTIAL`。下一批唯一目标为同一 `IndexVersion` 的内部 sqlite-vec Top-K 查询及版本/成员过滤测试，不激活索引或开放 RAG。

### 第十五批：内部向量 Top-K 与范围过滤

- Adapter：`SqliteVecAdapter.search` 新增只读内部查询，校验有限的 512 维单位查询向量和 `1..30` 的 `k`；读取同一 `embedding_config_id + index_version_id` 的全部 sqlite-vec KNN 行，在 Adapter 内先按允许的 `vector_store_record_id` 集合过滤，再按原始距离和稳定记录 ID 排序并截断。
- 应用用例：`VectorTopKQuery` 校验知识库未回收、版本归属/`BUILDING`/sqlite-vec、固定 EmbeddingConfig 指纹和余弦归一化约束；SQL 范围只接受当前 ACTIVE 成员、加入时间未变、文件已解析且未回收、Chunk 未失效、EmbeddingRecord 为 READY 且 hash/config 一致的记录，结果返回 Chunk/File/Version/Config、余弦距离、相似度、原始距离和 rank。
- 距离语义：现有虚表使用 sqlite-vec 默认 L2；单位向量的余弦距离为 `d_l2²/2`，相似度为 `1-distance`，等分按稳定 ID 排序。没有改变已有向量写入、删除或 Worker 完成语义。
- 生命周期证据：固定 512 维测试覆盖范围外更近向量、同分、`k` 大于候选数、版本/配置隔离、共享文件、成员移出重加、知识库/文件回收站、永久清理后的空库、失效 Chunk/EmbeddingRecord、坏维度/未归一化向量和向量库异常；查询后状态仍为 `BUILDING`，活动版本为空。
- 边界：现有向量表没有动态成员分区，查询采用全量 KNN + 先过滤后排序的精确 O(N) 策略；本批不宣称大规模性能，不新增迁移、API/OpenAPI、前端、公开检索、混合排序、索引激活、引用或 RAG。
- 验收：本批后端全量 `112 passed`；Ruff、Pyright `0 errors`、compileall、`git diff --check` 通过；阶段 5 结论仍为 `PARTIAL`。本批结论：`PASS`。
- 下一批唯一目标：实现同一 `IndexVersion` 内部 FTS5 与向量候选的合并去重，为后续 RRF 输入准备；不开放检索、不激活索引、不做引用或 RAG。

### 第十六批：内部双路召回合并去重

- FTS5：`Fts5Projection.match_version` 规范化 Unicode 查询，安全构造字段短语并丢弃未授权 FTS 运算符；真实 `bm25()` 按分数和 Chunk ID 稳定排序，过滤后限制为 Top 30，返回 `bm25` 与 `fts_rank`。中文单字/双字、英文、编号、空输入和特殊符号均有界且可解释。
- 双路范围：新增 `HybridCandidateQuery`，在同一 `IndexVersion` 内调用 FTS5 Top 30 与 `VectorTopKQuery` Top 30；两路均复核 ACTIVE 成员、成员加入时间、文件解析/回收站、内容哈希、Chunk 有效性，向量路额外复核 EmbeddingConfig、EmbeddingRecord 和向量 hash。
- 合并：新增 `merge_candidates`/`query_hybrid_candidates`，按 `chunk_id` 去重并保留 `fts_rank`/`bm25`、`vector_rank`/余弦距离/相似度、文件 ID、IndexVersion ID 和来源通道；单路字段保持 `NULL`，输出采用确定性排序，不执行 RRF、最终 Top 8、多样性或拒答。
- 竞态与故障：双路前后比较版本、成员、文件、Chunk、EmbeddingRecord 的范围指纹；中途变化返回 `RETRIEVAL_SCOPE_CHANGED`。单路故障默认显式失败，明确允许降级时返回单路候选和稳定错误码，不伪造双路成功。
- 边界：没有新增数据库迁移、公开 API、OpenAPI、前端或索引激活；向量路继续使用第十五批记录的精确 O(N) 过滤策略，未声明 10 万 Chunk 性能。
- 验收：后端全量 `117 passed`；Ruff、Pyright `0 errors`、compileall、`git diff --check` 通过；真实 SQLite FTS5/sqlite-vec 集成测试覆盖双路同 Chunk、单路命中、成员中途变化、路由故障、中文/英文/编号/特殊符号/空查询和稳定去重。第十六批结论 `PASS`，阶段 5 继续 `PARTIAL`。
- 下一批唯一目标：实现候选集 RRF 融合、精确命中奖励和确定性多样性排序；不激活索引、不开放用户检索、不做引用或 RAG。

### 第十七批：内部 RRF 与多样性排序

- 状态：本批 `PASS`；阶段 5 仍为 `PARTIAL`。
- 新增 `rank_candidates` 纯函数和 `HybridRankingConfig`。算法版本为 `rrf-exact-diversity-v1`，默认 RRF 常量 `60`；仅计算有效 FTS/vector rank 的 `1/(60 + rank)` 贡献，单路缺失仍保留原 `NULL` rank/分数。
- 精确匹配以 NFKC、casefold 和标点/空白/符号分隔规范化完整查询及文件显示名/heading/content；完整短语奖励 `0.002`，完整词项每项 `0.0004`，总奖励最多 `0.004`。拉丁/数字词项检查 ASCII 词边界；二字中文词项只给四分之一奖励。命中词、文件标题/Chunk 标题/正文位置和原因码均输出用于审计。
- 多样性采用确定性贪心排序：同文件候选按此前选中数量施加每项 `0.001` 的软惩罚（最多 2 项）；同文件相邻序号的三元字符集合重叠系数达到 `0.6` 时额外惩罚 `0.0025`；总惩罚封顶 `0.0035`。不按文件或重叠关系硬删除候选。
- 并列顺序依次按 RRF 分数、精确奖励、最佳原始 rank、双路命中优先、FTS rank、vector rank、`file_id`、Chunk 序号、`chunk_id` 决定；多样性每轮重新计算惩罚。最多输出 Top 8，并保留原始两路分数/rank、融合分、奖励、惩罚、原因和显式降级状态。
- 检索用例仅在复用既有范围校验后加载有效文件显示名、Chunk 正文、标题路径和序号，再核对版本/成员/文件/Chunk/EmbeddingRecord 指纹（含文件显示名）。发生范围变化仍直接返回 `RETRIEVAL_SCOPE_CHANGED`。不新增迁移、公开 API/OpenAPI、前端、索引激活、证据阈值、引用或 RAG。
- 固定离线样本覆盖 FTS-only、Vector-only、双路同 Chunk、跨文件覆盖、相邻高重叠 Chunk、完整编号和模糊短词、大小写/全半角/标点、同分与反转输入顺序、空输入、Top 8、显式单路故障降级及范围变化。真实 SQLite FTS5 + sqlite-vec 集成测试断言排序元数据及 BUILDING 状态不变；不将样本视作最终 Recall@10 验收。
- 验收：后端全量串行 `122 passed`；Ruff `All checks passed`；Pyright `0 errors, 0 warnings, 0 informations`；`python -m compileall -q src tests migrations` 通过；`git diff --check` 通过。未运行阶段 4/5 UI E2E（无前端/API 改动）；未调用 DeepSeek、真实凭据、付费外部调用或用户资料。
- 下一开发批次唯一目标：对内部 Top 8 实现配置化的证据充分性阈值判定和严格拒答结果；继续不公开检索、不激活索引、不生成回答或引用。

### 第十八批：内部证据充分性判定与严格拒答

- 状态：本批 `PASS`；阶段 5 仍为 `PARTIAL`。
- 实现：新增 `evidence-gate-v1` 配置化纯判定规则，并接入 `HybridCandidateQuery.search_and_assess_with_status`，在范围复核和内部 Top 8 排序后评估候选。结构化结果区分 `supported`、`insufficient`、`unavailable`，包含规则版本、问题类型、触发原因、Chunk/File/IndexVersion 身份和逐候选可审计信号。
- 放行条件：默认余弦相似度至少 `0.82` 且 `vector_score == 1 - vector_distance`（绝对误差不超过 `1e-5`）；融合排名不晚于 3、原始 FTS/vector rank 均不晚于 5；正文至少命中两个问题锚点且覆盖率至少 `0.60`，或正文含至少 5 个规范化字符的完整查询短语；包含编号时正文必须命中完整编号；数值问题还必须在正文锚点附近找到数值。标题、RRF 分、精确奖励和多样性调整不能绕过这些门槛。
- 来源与拒答：默认最少一个独立支持文件，重复 Chunk 按 `file_id` 去重，因此单文件有效证据可通过。同一问题存在多个子问题/开放列举或强候选出现数值/肯定否定冲突时整体 `insufficient`，不做部分回答。`insufficient` 仅产生固定本地提示和资料建议；路由错误/显式降级、未请求向量通道、索引未就绪、版本或范围变化为 `unavailable`，保留错误码，不返回资料不足文案。
- 语义边界：`supported` 只代表候选可进入后续来源快照、引用绑定和生成流程，不证明正文在语义上蕴含答案。规则阈值为保守开发初值；固定样本通过不代表阈值已由验收集校准，也不等同 Recall@10 或问答质量验收。
- 固定离线矩阵：精确定义问题与核心实体保留的合理改写预期并实测 `supported`；空结果、语义相近但缺少数值答案、弱/未知余弦值、标题命中、错误编号、高精确奖励、重复同文件切片、只覆盖部分子问题及多来源冲突预期并实测 `insufficient`；单文件有效证据预期并实测 `supported`；未请求向量通道、通道失败、跨库版本和检索中途范围变化预期并实测 `unavailable`。8 个纯离线用例均通过，不含私人资料。
- SQLite 集成：真实 SQLite FTS5 + sqlite-vec 路径从 Top 30 双路召回、范围校验、RRF/Top 8 到证据判定；实测支持结果只保留候选身份，不生成引用编号；所有候选文件属于当前范围；`IndexVersion` 仍为 `BUILDING` 且 `active_index_version_id` 为空。
- 边界：没有数据库迁移、公开检索/API、OpenAPI、前端、DeepSeek/真实模型调用或索引激活。阶段 5 仍需索引产物完整性复核与原子激活、服务端来源快照/引用绑定、公开检索/对话前端及基于验收集的阈值/质量评估。
- 验收：串行后端 `133 passed`；`uv run ruff check src tests` 通过；Pyright `0 errors, 0 warnings, 0 informations`；`uv run python -m compileall -q src tests migrations` 与 `git diff --check` 通过。额外 `uv run ruff check .` 检出 14 条未修改的 Alembic migration lint 项。全量测试曾有一次既有 Embedding Worker 互斥用例失败；单项重跑及随后全量串行重跑均通过，最终 `133 passed`。无前端/API 改动，未跑 UI E2E；未调用 DeepSeek、真实凭据、付费接口或真实用户资料。
- 下一开发批次唯一目标：为已完成索引版本实现产物完整性复核与原子激活，继续不开放用户检索。

### 第十九批：索引产物完整性复核与原子激活

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。Alembic 新增 `e4a7810c9b62`，只为 `IndexVersion` 增加内部 `activation_error_code`；没有公开 API/OpenAPI 或前端改动。
- 候选准入：`IndexActivationWorker` 扫描终态任务链候选；逐项核对知识库当前成员集合与冻结的 `IndexVersionInput`/解析快照、准备文件的解析状态/回收站/内容哈希/解析修订、Chunking/Embedding 配置重算指纹、阶段任务检查点和候选版本新旧顺序。存在新任务或尚未终结的阶段时等待；新版本已出现时旧候选不能激活，待其任务链终结后标为 `SUPERSEDED`。临时回收站/解析处理中输入等待既有恢复或永久清理流程。
- 产物规则：对每个已切片输入校验有效 Chunk 集和逐文件计数、Chunk 正文 SHA-256；对账 EmbeddingRecord 的 Chunk/配置/向量 hash、向量库 identity、SQLite `quick_check`、元数据/向量 rowid 一致、维度 512、有限单位向量及完整输入所需记录；执行 FTS5 `integrity-check` 与映射/倒排行对账，并将版本映射精确匹配到预期 Chunk/文件/解析修订/配置/hash。全部高成本检查在激活事务外完成，不重新运行 Embedding。
- 空库与部分失败：零成员、零计数且无派生产物的版本终结为 `EMPTY`，清除旧活动指针并保留旧版本物理数据；输入中的 `FAILED/SKIPPED` 被排除检索，至少一个输入的 Chunk/Embedding/FTS 均完整才可激活，知识库标记 `PARTIAL`；没有完整可用输入则候选 `FAILED`。失败原因写入逐输入阶段状态或 `activation_error_code`，首次构建失败时知识库为 `FAILED`。
- 原子切换：事务外对账后开始短事务，先按 `KnowledgeBase.row_version + active_index_version_id` CAS 占位并取得 SQLite 写锁，再复核活动/候选状态、最新版本、当前成员与输入指纹、任务检查点和配置指纹。成功时同一事务把新版本设为 `READY`/写入 `activated_at`，旧活动版本设为 `RETIRED`/写入 `retired_at`，切换活动指针、知识库/成员可用状态；失败或 CAS 变化回滚，不暴露半激活，不删除旧版向量或 FTS 产物。
- 恢复与可见性：应用启动后周期扫描 `BUILDING` 候选；在提交前崩溃会从持久状态重新复核，事务提交后的重复执行幂等返回。内部向量与混合查询只读取当前 `active_index_version_id` 指向的 `READY` 版本，FTS/向量均限制到完全可用成员；候选 `BUILDING`、非活动的 `RETIRED` 和 `FAILED/SUPERSEDED` 均不可通过应用查询层读取。没有公开检索 API。
- 固定离线验证覆盖首次成功、活动旧版与新候选隔离、切换后仅一个 `READY`、旧版物理产物保留、缺 Chunk/向量/FTS/错误维度拒绝、未终结任务等待、成员变化与新候选抢占、部分失败过滤、空知识库/空文本、重复恢复、并发重复激活、进程中断和提交故障回滚。所有用例使用 SQLite、固定 512 维向量和离线任务，不含用户文件。
- 验收：串行 `uv run pytest` 为 `147 passed`；`uv run ruff check src tests` 全过；Pyright `0 errors, 0 warnings, 0 informations`；`uv run python -m compileall -q src tests migrations`、`uv run alembic heads`（`e4a7810c9b62`）和 `git diff --check` 通过。`uv run ruff check .` 仍报 14 条既有 Alembic migration lint，未改旧迁移；没有 UI E2E、DeepSeek、真实凭据、付费服务或真实用户资料。
- 下一开发批次唯一目标：实现同一知识库的增量索引构建策略，保留本批快照校验与原子激活边界。

### 第二十批：同一知识库的增量索引构建

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。没有新增迁移或公开契约。
- 增量判定：`INDEX_PREPROCESS` 检查活动版本、当前成员快照、文件内容哈希、解析修订以及切片/Embedding 实际配置字段指纹。计划按 `NEW/CHANGED/UNCHANGED/REMOVED/PENDING/FAILED` 分类，并记录 `FULL/INCREMENTAL` 模式、复用来源和数量。成员加入时间仍参与目标快照校验，但不作为文件级 Chunk/Embedding 的复用键。
- 复用规则：只有来源输入阶段均完整，且 `file_id + content_hash + parse_revision_id`、ChunkingConfig、EmbeddingConfig（模型 revision、维度、归一化、距离等）与向量引擎兼容时才复用。已有 Chunk 直接引用；EmbeddingRecord 的向量从兼容 IndexVersion 的 sqlite-vec 空间按 ID/hash 对账并复制到新版本，不运行 ONNX；FTS 投影复制到新版本映射。缓存不存在、配置或产物对账不通过时回退到原 Chunk/Embedding/FTS 阶段。配置关键字段不兼容时对整个知识库执行完整重建，不复用旧向量。
- 范围与生命周期：候选仍冻结完整的当前成员快照；移出成员在当前查询的实时成员过滤中立即排除，候选中不包含已移出的成员。移除或切换不删除原文件、其他知识库共享的 EmbeddingRecord/Chunk 或历史版本 FTS/向量。构建期间旧活动版本保持可读；第十九批激活器继续完整核验候选并以原子事务切换。
- 幂等与竞态：重复提交相同知识库、输入快照和配置返回现有候选；快照变化可建立新候选，较旧候选由激活器标记 `SUPERSEDED`，不自动无限重试。Worker 重试及预处理恢复沿用持久任务/检查点；源缓存变化时清除复用标记并走正常阶段计算。
- 验收：新增 `tests/test_stage5_incremental_index.py` 覆盖新增文件、文件内容替换、成员移除、跨知识库兼容复用、Embedding 维度/配置不兼容全量重建、重复提交和完整候选原子激活。Embedding 调用计数 Mock 证明新增/变更文件外，未变文件不会再次推理；激活器对 Chunk、Embedding/向量与 FTS 全量复核通过后才切换。串行后端 `153 passed`；Ruff、Pyright、compileall、Alembic head `e4a7810c9b62`、`git diff --check` 通过。`ruff check .` 仍报告 14 条既有 Alembic migration lint。无真实 Provider、凭据、用户资料、UI E2E 或 OpenAPI 变更。
- 下一开发批次唯一目标：为活动索引建立持久化的服务端来源快照，并校验来源仍属于该知识库的活动版本范围。

### 第二十一批：服务端来源快照与范围校验

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。本地/远端起始 SHA 均为 `767d2859b7f16090167e3d8569652a7a2010a131`；结束 SHA 以批次提交推送结果为准。
- 数据：Alembic `6b3e91a0c4d7` 新增内部 `SourceSnapshot`，只允许 `UNBOUND`，保存知识库与 IndexVersion 快照、File/Chunk 可空关联、文件内容版本哈希、解析修订、真实 heading/page/slide/line 定位、最多 1200 Unicode 字符摘录、摘要/正文 SHA-256、创建时间和唯一幂等键。暂时没有真实消息或学习 owner，因此不造 Citation owner、消息或显示编号。
- 创建校验：只有 `HybridAssessmentResult.assessment.status=supported` 且 retrieval/gate 候选身份一致才可进入创建。独立写事务的首条语句取得 SQLite 写锁，随后复核活动 READY 版本/指针、未删除知识库、当前 ACTIVE/READY 成员、文件 PARSED/未回收、内容哈希/解析修订、IndexVersionInput 成员快照、Chunk 正文哈希与配置、版本内 FTS 映射及有效 EmbeddingRecord/配置指纹。范围变化返回 `RETRIEVAL_SCOPE_CHANGED`，活动版本变化返回 `INDEX_VERSION_CHANGED`，来源失效返回 `SOURCE_INVALID`，源文件版本变化返回 `SOURCE_VERSION_CHANGED`。
- 快照与读取：文件名、定位、内容和摘要均从数据库重读，不信任候选携带的名称、正文或任意 ID；同一知识库/版本/Chunk 的重复调用复用既有快照。读取动态计算可用、回收站、文件版本过期、范围退出和索引退役状态，不返回磁盘路径；重建索引不会改写历史快照的 IndexVersion/Chunk 身份。
- 删除净化：文件永久删除的服务路径先清空摘录、正文/文件版本哈希、解析修订并断开 File/Chunk 关系，只保留文件名和定位；SQLite BEFORE DELETE trigger 覆盖绕过服务 helper 的直接文件删除。知识库永久删除同时清理没有 owner 的待绑定快照。软删除保留历史摘录，但读取标记为回收站且不可打开。
- 验收：新增 `tests/test_stage5_source_snapshots.py` 10 项，覆盖真实内部 FTS5 + sqlite-vec→混合检索→证据门控→快照、应用重启读取、伪造文件名/Chunk、跨库、成员移除/重加、回收站、坏映射、活动指针/成员竞态、幂等、定位空值、重建后旧版本引用和永久删除净化。最终 `uv run pytest` 为 `164 passed`；`uv run ruff check src tests` 通过；Pyright `0 errors, 0 warnings, 0 informations`；compileall、Alembic heads（`6b3e91a0c4d7`）和 `git diff --check` 通过。
- 范围：没有公开检索/Citation API、OpenAPI/前端类型、Chat/Learning owner、对话或生成式回答；未调用 DeepSeek、真实凭据或付费外部服务。本批不构成最终答案事实正确性、AC-KB-003、Recall@10 或质量/性能验收证据。
- 下一开发批次唯一目标：定义并实现来源快照到真实 Chat/Learning owner 的服务端 Citation 绑定边界，暂不生成模型回答。

### 第二十二批：Citation 绑定依赖延期

- 状态：`BLOCKED`；没有代码、文档、测试或提交变更。进场与离场本地/远端 SHA 均为 `e1766c3d173f4613e368bbb8988a343ca207738e`，工作区保持干净。
- 阻塞事实：数据模型/迁移/源码没有真实持久化 Chat 或 Learning owner，也没有可核验的对应知识库范围快照；`TaskAttempt` 是后台任务尝试，不能充当学习 owner。为防止伪造 owner，Citation 绑定延期到阶段 6/7。
- 延期不会阻止第二十三批实现独立的本地检索测试端点；Owner 建立后再恢复服务端 Citation 绑定。

### 第二十三批：知识库本地测试检索 API

- 状态：`PASS`；阶段 5 继续 `PARTIAL`。进场本地/远端 SHA 为 `e1766c3d173f4613e368bbb8988a343ca207738e`。
- 新增只读 `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests`，仅接收 1–2000 字符问题并拒绝额外字段。后端根据路径知识库选择其当前活动 `READY` IndexVersion；调用方不能指定文件、索引版本、模型或路径，API 沿用 Host/Origin/LocalSession/Idempotency-Key 安全校验。
- 本地 BGE query encoder 首次调用时才校验并加载既有模型，明确禁止下载。活动索引前检查 EmbeddingConfig；本地模型缺失/损坏、FTS/vector 通道故障与资料不足返回不同状态/错误码。混合检索采用既有双路 Top 30、确定性融合/重排 Top 8 与 `evidence-gate-v1`；查询开始前和检索期间复核索引/成员/文件/Chunk/Embedding 范围，变化时无候选返回 `unavailable/RETRIEVAL_SCOPE_CHANGED`。
- 响应返回 gate 状态、索引/算法/规则版本、候选标识、数据库位置、受控摘录与双路排名/分数；最多 8 个候选、最多 1200 字符摘录、最大 JSON 体 64 KiB。不创建模型回答、对话、SourceSnapshot、Citation、后台任务或数据库写入，也不调用 Provider。
- 真实 SQLite FTS5 + sqlite-vec API 用例覆盖可支持问题/资料不足、空索引、离线模型缺失、输入与额外字段校验、本地 Origin/Session、跨知识库隔离、当前活动版本与同库待索引成员过滤、回收站排除、索引/成员并发变化、FTS/vector 失败路由和零写入。串行后端最终全量 `176 passed, 143 warnings`；Ruff、Pyright、compileall、Alembic head `6b3e91a0c4d7` 与 `git diff --check` 通过。此前完整运行分别观察到既有 purge 用例一次 row-version `412`、Chunk 显式重试用例一次未恢复；两个用例单独重跑通过，最终完整串行运行通过，未修改它们。前端 API 生成、typecheck、lint、build 通过；未跑 UI E2E（没有页面改动）。
- 第二十二批真实 owner/Citation 绑定仍待阶段 6/7；前端测试检索页面与验收集质量/性能校准仍未完成。下一批唯一目标：实现本地检索测试页面并调用该只读 API，不生成模型回答或 Citation。

### 第二十四批：知识库详情本地测试检索页面

- 状态：`PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `2ffe354b3efaa72e10c4d71a9978001750c35019`。
- 页面：在 `/knowledge-bases/:id` 详情页增加辅助“测试检索”区域，保持知识库标题、文件数和索引状态；输入遵守 1–2000 字符契约，空/纯空白不提交，提交中显示加载状态并防重复点击。
- API：复用现有生成类型和 `runKnowledgeBaseRetrievalTest`，只发送路径知识库 ID 与 `{ question }`；不写浏览器持久存储，不触发模型下载、Provider、索引任务、回答、SourceSnapshot 或 Citation。
- 展示：分别呈现 `supported`（找到可能支持的资料）、`insufficient`（资料不足）和 `unavailable`（检索暂不可用）；区分空结果、无活动索引、模型不可用、通道故障和范围变化。候选最多 8 条，显示纯文本文件名、受控摘录、真实标题/页/幻灯片/行定位、原始 rank/分数、RRF/排序说明和缺失信号“无”，不渲染回答或引用编号。
- 稳定性与安全：请求支持 AbortController、序列号和按知识库 ID 卸载，旧响应不会覆盖当前问题或知识库；错误保留输入并提供重试；摘录、文件名和定位均由 React 文本节点安全渲染，未使用 `dangerouslySetInnerHTML`。
- 验收：新增 `frontend/src/test/stage5-retrieval-test.test.tsx`，覆盖 Top 8/空结果、三种状态、无活动索引/模型、错误重试、防重复、问题/知识库切换竞态、无持久历史和 HTML 片段安全。前端 Vitest `21 passed`；typecheck、lint、build、`git diff --check` 通过。真实本地 FastAPI + Vite 浏览器验证空知识库键盘提交，返回 `unavailable / INDEX_VERSION_NOT_AVAILABLE`；没有固定 READY 资料，不把 Mock 候选显示写成真实检索证据。
- 本批无后端、迁移或 OpenAPI schema 变更；Citation owner 继续延期到阶段 6/7。下一开发批次唯一目标：准备固定本地验收资料并建立可复现 READY 索引，为该页面补充真实浏览器候选显示证据。

## 进度口径

文件产出不等于测试通过；测试通过不等于 Spike 通过；Spike 通过不等于业务验收或发布完成。
