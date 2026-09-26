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

### 第二十五批：固定资料 READY 索引与真实浏览器候选验证

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `63bca0d73d66ac0810ae394d8545cb19ce1110cb`。
- 固定资料：`docs/test-data/stage5-fixed-ready/` 提供主库超时策略、相似干扰库策略和索引 READY 后移入回收站的范围验证资料；另有无成员诊断库验证未就绪错误。运行命令：`uv run python scripts/prepare_stage5_fixed_ready.py --data-dir "$env:TEMP\mindmate-ai-stage5-fixed-ready"`。数据根通过专用所有权标记保护；脚本两轮运行后仍是 3 文件、3 知识库、13 持久任务，没有新增重复记录。最终验证摘要在隔离根的 `stage5-fixed-ready-report.json`。
- 模型：离线复验并复制 Git 忽略缓存 `backend/model-cache/manager-validation` 的真实 `BAAI/bge-small-zh-v1.5`（base revision `7999e1d3359715c523056ef9478215996d62a620`）与 `Xenova/bge-small-zh-v1.5` ONNX revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`；manifest fingerprint `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。源与隔离副本的 manifest 大小/SHA-256 校验均为 `READY`；无联网、无下载、无 Mock 向量。
- 构建闭环：真实文件导入/解析、知识库成员任务和预处理服务后，准备脚本分别入队现有 `INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 持久 Worker，由激活 Worker 原子切换。主库与干扰库活动 IndexVersion 均为 `READY`。主库 2 输入产生 2 Chunk/2 Embedding/2 vector/2 FTS 映射；干扰库 1 输入各产物均为 1。任务检查点四阶段均 `COMPLETED`；FTS integrity/consistency 和向量 ID、哈希、512 维、有限值、单位范数核验通过。
- 检索与浏览器：真实 `POST /api/v1/knowledge-bases/{id}/retrieval-tests` 在主库返回 `服务超时策略.txt`、含 `30 秒` 的摘录与 `line_start=1`；相似库只返回 `相似服务超时策略.txt` 及 `47 秒`。两个目标查询的门控结果都是 `insufficient / VECTOR_SIMILARITY_BELOW_THRESHOLD`，余弦相似度 `0.5867/0.6568`，未调整既有 `0.82` 门槛。回收站内容没有泄漏；资料外问题返回 `insufficient / NUMERIC_ANSWER_VALUE_NOT_FOUND`，没有答案或正式 Citation 字段。Chromium `1440x1000` 与 `390x844` 真实浏览器均通过键盘 Tab/Enter 提交和候选显示；E2E `2 passed`。截图位于 `%TEMP%\mindmate-ai-stage5-fixed-ready\evidence\`。
- 验收：`uv run pytest` 为 `176 passed, 143 warnings`；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py`（0 errors）、`uv run python -m compileall -q src tests migrations scripts`、`uv run alembic heads`（`6b3e91a0c4d7`）通过。前端 `npm run typecheck`、`npm run lint`、`npm test -- --run`（21 passed）、`npm run build`、真实 Playwright E2E（2 passed）与 `git diff --check` 通过。
- 未验证：几份固定资料不替代 Recall@10、10 万 Chunk 性能、门控阈值校准或 AC-KB-* 全量验收。无 DeepSeek、真实凭据、付费服务或个人资料；Citation owner 仍延期到阶段 6/7。

### 第二十六批：真实 ONNX 证据门控基线评测

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。进场本地与 `origin/feat/v1-bootstrap` SHA 均为 `3ef9a33adcdae5adb06e6a6835d44fdbbf84ed3d`，工作区干净。
- 语料与标注：`docs/test-data/stage5-fixed-ready/evidence-gate-v1-queries.json` 保存独立人工真值，31 条核心样本及 2 条 `needs_review`。新增 6 份合成资料进入独立评测库；原第二十五批主库、相似库和浏览器数据保持独立。每项包含知识库范围、证据充分性、允许支持文件或拒答理由；复核项不进核心分母。
- 构建与模型：离线复制并验证 BAAI `7999e1d3359715c523056ef9478215996d62a620` 与 Xenova ONNX `75c43b069aac4d136ba6bc1122f995fedcfd2781`，fingerprint `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。通过现有导入、持久预处理/Chunk/Embedding/FTS Worker 和激活器建立 READY；无 Mock 向量、下载或 DeepSeek 调用。原固定 READY 根被运行中的本地验收服务使用，因此本批使用同样有所有权标记的新隔离根 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1`。
- 真实门控混淆表：TP `0`、FN `16`、FP `0`、TN `15`，核心样本共 `31`。16 个假阴性全部在 Top 8 找到允许支持文件，召回缺失型 FN `0`；顶层拒绝原因 `VECTOR_SIMILARITY_BELOW_THRESHOLD` 11 条、`NUMERIC_ANSWER_VALUE_NOT_FOUND` 3 条、复合问题拒绝 2 条。无资料不足放行或跨知识库候选；显式冲突 2 条、无答案 3 条、错误编号 1 条、回收站 2 条均正确拒答。2 条歧义项实际查询但从分母剔除。
- 候选信号：首轮 Top 8 候选 101 条，Vector 命中 101，FTS 命中 2（均双路），Vector-only 99，FTS-only 0；两条 FTS 命中来自 `API?` / `ID?` 短词拒答项。所有排名、BM25 与余弦距离/相似度一致性校验通过。Top 8 相似度 min/median/max `0.3356/0.4835/0.7127`，可回答问题标注证据覆盖 `16/16`。
- 离线敏感性：仅在已观察候选上模拟向量下限 `0.65`、`0.70`、`0.75`、`0.82`、`0.85`，混淆表均不变；不修改运行时 `0.82` 或其他规则。当前误拒没有证据支持仅靠调整余弦下限修复。
- 重复性与写入：最终代码连续独立执行两次，每次双轮结果签名内部相同，两次签名均为 `c5d216439163910865464f3130edc1eafd18a445978c2d3ca42cafb0aabd4931`。评测查询前后数据计数保持 9 files / 4 knowledge bases / 24 tasks。报告只写入隔离根，不纳入 Git。
- 命令：`uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1" --repeat 2`。脚本先运行 READY 准备流程，随后只通过本地只读检索 API 评测；任何 `unavailable`、模型离线校验失败、标注范围不符、资源计数变化或复跑不稳定均以失败退出。
- 验收：串行 `uv run pytest` `179 passed, 143 warnings`（2:22）；`uv run ruff check src tests scripts` 通过；`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py` 为 0 errors；compileall、Alembic head `6b3e91a0c4d7`、`git diff --check` 通过。没有前端改动，未运行前端门禁。
- 下一开发批次唯一目标：以固定人工查询集测量中文自然问句的 FTS5 命中与 hard-negative 分布，先定位 FTS 候选召回问题，不调整证据门槛。

## 进度口径

文件产出不等于测试通过；测试通过不等于 Spike 通过；Spike 通过不等于业务验收或发布完成。

## 第二十七批：中文 FTS 召回修复与困难负例回归

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。进场本地与远端 `origin/feat/v1-bootstrap` SHA 均为 `2f8025692580f69de4e3f57598efd39d8abc17de`，工作区干净；结束 SHA 以本批提交推送结果为准。
- 根因定位：真实 READY 索引中的 `han_bigrams/han_unigrams/terms` 投影与查询侧预处理一致，缺陷在 `match_expression` 将整段中文问句拼成完整引号短语。自然问句中存在原文没有的疑问脚手架词时，FTS5 要求所有二元词连续共现，导致标题、编号和关键中文词项全部失配。
- 最小修复：查询解析统一 NFKC、拉丁/数字精确 AND 和安全引号转义；每个连续汉字段使用有界二元词 OR 组，句末语气词与仅作问句脚手架的词不参与 fallback；SQL MATCH 后按每段至少两个二元词（含数字/编号的段至少一个）做确定性过滤，原始 FTS Top 30 仍有四倍以内的有界候选扩展。没有修改 FTS schema、索引 Worker、RRF、证据门控、生产阈值或迁移，因此 READY 旧索引可直接读取。
- 定向回归：`tests/test_stage5_fts_worker.py` 增加自然中文问句、自然改写、准确编号、错误编号和引号/通配符注入用例；`query_debug` 与评测脚本逐条记录查询 token、MATCH 表达式、存储侧 token、FTS 候选排名、向量候选、Top 8 和门控原因。
- 真实 FTS 对比：旧基线固定集 Top 8 共 101 条，FTS 命中 2、Vector-only 99；修复后 Top 8 仍 101 条，FTS 命中 20、双路命中 20、Vector-only 81、FTS-only 0。主库直问、中文自然改写、演练系统标题/编号和 `CACHE-PROXY-K3` 均有实际 FTS 候选；错误数字/编号没有被 FTS 命中。
- 核心集对照：31 条旧核心标注的 TP `0` / FN `16` / FP `0` / TN `15` 与第二十六批一致；16 条 FN 的人工支持文件均在 Top 8，仍被现有 `evidence-gate-v1` 严格拒答。两次独立真实 ONNX 运行各含两轮内部复跑，核心结果签名稳定。
- Hard negatives：新增 `docs/test-data/stage5-fixed-ready/evidence-gate-v1-hard-negatives.json`，独立人工标注 7 条，覆盖同名跨库 30/47 秒、错误数字、相同术语无事实、相反表述和回收站。新增集 TN `7` / FP `0`，跨范围候选 `0`；空诊断库的失效索引检查两轮均为 `unavailable / INDEX_VERSION_NOT_AVAILABLE`、0 候选，不计入混淆表。
- 复跑命令与隔离：`uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1-r27" --repeat 2`。旧评测目录因所有权标记缺失被拒绝接管，未删除或覆盖；新隔离根准备了真实 ONNX READY 数据并写出 `stage5-evidence-gate-v1-report.json`。报告不进入 Git，模型和临时数据库不提交。
- 质量门禁：串行 `uv run pytest` 为 `181 passed, 143 warnings`（约 2:26）；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py`（0 errors）、compileall、Alembic head `6b3e91a0c4d7`、`git diff --check` 全部通过。未改前端，未运行前端门禁；没有 DeepSeek、真实凭据、付费服务或私人资料。
- 下一开发批次唯一目标：针对仍保留的 16 条 FN 建立人工可解释的证据门控/答案质量校准方案，继续保持阶段 5 `PARTIAL`，不以调低拒答阈值或扩大 FTS 匹配范围换取表面通过。

### 第二十八批：证据门控规则校准与正负例回归

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。进场本地与 `origin/feat/v1-bootstrap` SHA 均为 `b2ddc62bade9517272e06d761fd5f30e392bee92`，工作区干净；未改 schema、公开 API、前端、Provider 或 FTS 召回范围。
- 基线复现：使用同一人工 manifest、固定 `evidence-gate-v1` 标注、同一真实本地 ONNX 和独立 READY 数据根 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1-r28-baseline` 复跑第 27 批基线，核心仍为 `TP 0 / FN 16 / FP 0 / TN 15`，hard negatives 为 `TN 7 / FP 0`。16 条 FN 的支持文件均在 Top 8，说明根因是门控误拒而非召回缺失。
- 逐条复核：`S5-EG-001/002/003/005/011/012` 使用 `服务超时策略.txt` 行 `1-12` 的 FTS+向量双路正文；`S5-EG-010` 同片段覆盖两个复合子句；`S5-EG-013/014` 使用 `相似服务超时策略.txt` 行 `1-9` 的 47 秒事实（`014` 为受 `0.60` 下限约束的 vector-only 语义例外）；`S5-EG-016/018/020/029` 使用 `阶段5评测_参数记录.txt` 行 `1-4` 的 OPS-R7-204、17 秒、6 个文件；`S5-EG-021/022` 使用 `阶段5评测_组件记录.txt` 行 `1-3` 的完整编号/组件/12 分钟事实；`S5-EG-028` 使用 `阶段5评测_短词干扰.txt` 行 `1-2` 的明确“不定义”说明。每条候选的实际 Chunk、FTS/向量 rank、重排 rank、余弦、正文锚点、数字/编号命中、支持路径和拒绝分支写入评测报告的 `gate_signal_audit`。
- 代码校准：默认 `min_vector_similarity=0.82` 保持不变。FTS 例外必须同时具备 FTS/向量 rank 不晚于 5、最终 rank 不晚于 3、双路信号、至少两个正文锚点或完整短语、数值/单位/编号语境通过及 `similarity >= 0.50`，记录 `FTS_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD`。无 FTS 时只能走 `similarity >= 0.60`、至少两个语义锚点且覆盖率 `>=0.50` 的 vector-only 路径，记录 `SEMANTIC_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD`。正文只命中标题、同文件在 Top 8、任意短词、纯余弦下降和无语境数字均不能放行。
- 数值/语义与复合边界：显式数值必须以相同单位在锚点附近出现，错误值/单位使用 `QUERY_NUMERIC_VALUE_NOT_FOUND`；完整编号缺失使用 `QUERY_IDENTIFIER_NOT_IN_BODY`；否定断言与正文肯定事实冲突使用 `QUERY_CLAIM_CONTRADICTED`；仅有“不定义”不能回答“定义事实”的问题使用 `QUERY_NEGATIVE_FACT_ONLY`；复合问题按 `以及/并且/同时` 分解，任一子句无法在候选正文定位即 `COMPOSITE_OR_OPEN_LIST_QUESTION`；多文件数字/极性矛盾仍为 `CONFLICTING_EVIDENCE`。
- 校准后真实结果：最终独立数据根 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1-r28-final` 两轮内部复跑均为核心 `TP 16 / FN 0 / FP 0 / TN 15`，hard negatives 两轮均为 `TN 7 / FP 0`；`needs_review=2` 单列不进分母。两轮签名稳定，查询前后均为 `9 files / 4 knowledge bases / 24 tasks`；失效索引安全检查两轮均 `unavailable / INDEX_VERSION_NOT_AVAILABLE`、0 候选。正例最低实际余弦约 `0.5437`（编号问句，FTS 正文通过），唯一 vector-only 放行样本余弦约 `0.6013`；这些只是固定合成样本证据，不代表发布级 Recall@10 或问答质量。
- 报告：`uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1-r28-final" --repeat 2`；JSON 报告在 `%TEMP%\\mindmate-ai-stage5-evidence-gate-v1-r28-final\\stage5-evidence-gate-v1-report.json`，不进入 Git。
- 验收：定向门控/评测测试 `18 passed`；全量 `uv run pytest` `186 passed, 143 warnings`（142.37 秒）；Ruff 全目录通过；Pyright `0 errors, 0 warnings, 0 informations`；compileall、Alembic head `6b3e91a0c4d7`、`git diff --check` 通过。未改前端，因此未运行前端门禁；未调用 DeepSeek、真实凭据、付费服务或私人资料。
- 下一开发批次唯一目标：等待真实 Chat/Learning owner 后建立服务端 Citation 绑定准入，继续不生成模型回答、不伪造 Citation owner；阶段 5 保持 `PARTIAL`。

### 第二十九批：知识库索引状态与失败重试工作台

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。进场本地与远端 SHA 均为 `cf0853e3c80a71b64c65d60ae8b8fb4e0b057707`，`feat/v1-bootstrap` 工作区干净，无分叉。
- 进场盘点：既有 API 可读知识库/成员和持久任务，也有预处理、切片、Embedding、FTS 入队函数与任务取消路由；但没有索引运维状态端点、重试/重建命令，生产运行时也没有从预处理检查点接力入队后续阶段。固定 READY 验证脚本会逐阶段手动入队。
- 新增契约：`GET /api/v1/knowledge-bases/{knowledge_base_id}/index-status` 返回当前状态、活动/目标版本、有效成员可用/处理中/失败数、逐文件安全原因、后台阶段/进度/诊断 ID 和本机 Embedding 模型状态；模型文件校验结果缓存于进程内，避免任务轮询重复哈希。`POST /api/v1/knowledge-bases/{knowledge_base_id}/index/retry-failed` 接收 `file_ids`，服务端重新验证失败与成员范围；`POST /api/v1/knowledge-bases/{knowledge_base_id}/index/rebuild` 建立 `FULL` 输入快照。更新 `docs/openapi/openapi.json` 与前端生成类型，无数据库迁移。
- 持久任务链：运维命令返回现有 `INDEX_PREPROCESS` 任务；`IndexActivationWorker` 根据持久阶段检查点接力入队 `INDEX_CHUNK`，再并行入队 `INDEX_EMBED` 与 `INDEX_FTS`，最后交给原子激活器。准备脚本与运行时共用阶段幂等键；完整重建构造 `FULL` 快照，活动旧版本在构建期间仍供检索。
- 前端闭环：详情页新增索引运维工作台，保留“测试检索”；显示索引状态、活动/目标版本、成员计数、失败文件和安全原因码、真实任务阶段/进度/诊断 ID、本地模型可用性；支持重试失败文件、确认当前库重建和现有任务取消。状态查询按 KB ID 隔离，运行期间每 1.5 秒轮询，页面不可见时暂停，刷新后从 API 恢复；不触发模型下载、回答或 Citation。
- READY 准备证据：`uv run python scripts/prepare_stage5_fixed_ready.py --data-dir "$env:TEMP\mindmate-ai-stage5-r29-index-ops-e2e-02" --model-cache model-cache/manager-validation` 返回 `PASS`；隔离数据 `9 files / 4 knowledge bases / 24 tasks`，向量与 FTS 完整性复核通过，无模型下载或外部 Provider 请求。
- 真实浏览器重建：Playwright 在独立 5174/8001 端口通过知识库 `01a0d6a1-583b-7360-b0bb-2546fc3f85ec` 重建；活动版本由 `01a0d6b2-1b26-7afb-a599-0366cd1c8602` 切换到 `01a0d6c4-b88c-7a8f-b67d-bd64993daf9d`，预处理/切片/Embedding/FTS 四个任务全部完成，状态 `READY`。Chromium 在 `390x844` 无水平溢出，截图位于隔离根 `evidence/index-operations-mobile.png`，不进 Git。
- 验收：`uv run pytest` `191 passed, 148 warnings`（143.94 秒）；Ruff 全目录通过；Pyright `0 errors, 0 warnings, 0 informations`；compileall、Alembic head `6b3e91a0c4d7`、`git diff --check` 通过。前端 Vitest `22 passed`、`npm run lint`、`npm run build`、真实 API Playwright E2E `1 passed`。API/激活器回归覆盖空库、失败范围、跨库/回收站拒绝、幂等重试/重建、失败候选保留活动版本和阶段接力；前端测试覆盖重试、取消和重建确认。
- 未完成/未宣称：本批浏览器验证真实 READY 库重建成功，不代表浏览器级模型缺失失败恢复；模型下载安装页面、Citation owner、10 万 Chunk 性能、Recall@10、最终问答质量和 AC-KB-* 全量验收仍未完成。阶段 5 保持 `PARTIAL`。
- 下一开发批次唯一目标：真实 Chat/Learning owner 在阶段 6/7 可核验后建立服务端 Citation 绑定准入；不生成模型回答、不伪造 owner。

### 第三十批：本地 Embedding 模型安装与进度闭环

- 状态：本批 `PASS`；阶段 5 继续 `PARTIAL`。起始本地与 `origin/feat/v1-bootstrap` SHA 均为 `d8762e32a2d3db85cf2393f05a7d99d007f677b7`，分支 `feat/v1-bootstrap`，工作区干净且无分叉。
- 固定来源复核：BAAI `bge-small-zh-v1.5` revision `7999e1d3359715c523056ef9478215996d62a620` 的模型卡声明 MIT；Xenova `bge-small-zh-v1.5` ONNX revision `75c43b069aac4d136ba6bc1122f995fedcfd2781` 公开、未 gated，模型卡 `base_model` 指向 BAAI。Xenova 未单独声明许可证，项目沿用索引契约中记录的上游 MIT 许可依据，不声称第三方转换仓库另行声明 MIT。
- 真实 manifest 下载：全新隔离数据根 `%TEMP%\mindmate-ai-stage5-model-install-r30b` 中由应用后端通过固定 HTTPS manifest 下载并安装 `onnx/model.onnx`、`tokenizer.json`、`config.json`，总计 `95,291,718` 字节；实际大小和 SHA-256 与模型仓库元数据/固定 manifest 一致：ONNX `94,851,877 / 69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a`，tokenizer `439,125 / 48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26`，config `716 / d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f`。复合 revision fingerprint 为 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。模型目录和证据截图均留在 `%TEMP%`，未进入 Git。
- 后端持久闭环：新增 `GET /api/v1/embedding-model` 与用户主动调用的 `POST /api/v1/embedding-model/install`；固定下载任务类型 `EMBEDDING_MODEL_INSTALL` 复用 SQLite `BackgroundTask`、检查点、诊断 ID、现有 `/api/v1/tasks/{task_id}/cancel` 和启动恢复，无 migration。字节/总字节、当前固定 manifest 文件及 `DOWNLOADING/VERIFYING` 阶段持久化；应用关闭将任务置 `INTERRUPTED`，新进程接续同一任务。重复提交返回活动 task，不并发重复下载；空闲 Worker 阻塞等候通知，不对任务表做周期写入。下载继续走现有 `.partial`、TLS、大小/超时限制、逐文件 SHA-256、配置校验和原子发布。
- 浏览器路径：隔离后端 `8001` 与 Vite `5174` 上，Playwright 创建真实测试知识库/文本文件；在详情页确认模型未安装后点击安装。浏览器页面显示真实进度截图（`0.1 MiB / 90.9 MiB`），下载结束 API 返回 `READY / 95,291,718 / 95,291,718`。之后由同一页面重建索引，固定 ONNX Runtime CPU 推理、`INDEX_PREPROCESS`、`INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 和原子激活均完成；知识库及活动版本最终 `READY`。390×844 视口无水平溢出，截图 `model-download-progress.png`、`model-index-ready-mobile.png` 位于隔离根 `evidence/`。
- 可控故障验证：本地 HTTP fixture 覆盖分块进度、重复安装去重、取消后 `.partial` 未发布、重试成功以及 app lifespan 重启后从持久任务恢复；既有 ModelManager 测试覆盖坏哈希、截断/缺失文件、离线/超时、危险重定向、配置错误、原子发布与并发安装。fixture 只测试安装状态机，不冒充真实模型；真实 manifest 与本机 ONNX 另由上述浏览器安装/索引证据验证。进程级 Windows 安装包重启尚未验收。
- 回归测试：新增后端安装 API/Worker 和前端显式安装/进度/取消/重试测试；另验证活动索引 READY 与模型 MISSING 可同时展示、校验忙碌时禁用重复安装。`uv run pytest` `194 passed, 152 warnings`（159.77 秒）；`uv run ruff check src tests scripts`、Pyright `0 errors`、compileall、Alembic head `6b3e91a0c4d7` 通过；OpenAPI 导出和 TypeScript 生成一致。前端 Vitest `23 passed`、lint、typecheck、build 通过；真实本地 API Playwright 首次模型安装 E2E `1 passed`，READY 模型复用/许可说明浏览器复核 `1 passed`；`git diff --check` 通过。
- 边界：没有 DeepSeek 请求、真实凭据、付费 API、用户私人资料或模型文件入 Git。已证明本机固定模型下载、校验和一次真实索引；未覆盖真实网络断开过程中的浏览器提示、Windows 安装包进程级终止/重启、10 万 Chunk 性能、Recall@10/最终回答质量、Citation owner 与 AC-KB-* 全量验收。阶段 5 继续 `PARTIAL`。
- 下一批唯一目标：真实 Chat/Learning owner 可核验后建立服务端 Citation 绑定准入；不生成模型答案、不伪造 owner。

## 第三十一批：阶段 6 DeepSeek 凭据配置与最小连接测试

- 状态：本批 `PARTIAL`；阶段 6 开始，阶段 5 继续 `PARTIAL`。进场分支为 `feat/v1-bootstrap`，本地与 `origin/feat/v1-bootstrap` 起始 SHA 均为 `8fff8670d74784aee04eaa3a585a2f9f329050db`，工作区进场干净。
- 官方资料复核：2026-09-25 复核 DeepSeek Chat Completions 文档和模型/价格页，`https://api.deepseek.com`、`deepseek-flash` 和 OpenAI-compatible Chat Completions 仍与冻结决策一致；价格和别名背后的实际模型不写死，探测结果保存 `resolved_model`。
- 凭据边界：新增 `CredentialStorePort`、Windows Credential Manager 实现和明确隔离的 `InMemoryCredentialStore`。非 Windows 或非 Windows keyring 后端直接报告不可用，不回退到明文磁盘；SQLite 只保存非秘密 `secret_reference`、外发同意版本和探测状态。`keyring` 从开发依赖提升为运行时依赖。
- Provider 边界：新增 `DeepSeekChatProvider`，固定请求别名、最短探测文本、`max_tokens=8`、`temperature=0` 和流式 Chat Completions；只在用户主动点击并提交 `confirm_external_transfer=true` 后读取 Key。统一映射 401/403、402、429、5xx、连接/读取超时、网络和异常响应；失败不删除 Key，不保存原始响应或正文。
- API/前端：新增 `/api/v1/ai/provider` 状态、`/key` 保存/删除、`/test` 连接探测和 `/ai/consent` 版本化同意 API；OpenAPI 3.1 导出 `51 schemas / 62 operations`，生成前端类型同步。`/settings` 页面分开显示 Key 配置、外发同意和探测结果；明文输入提交后清空，不写入 LocalStorage/全局状态。
- 测试证据：`uv run pytest tests/test_stage6_provider_configuration.py -q` 为 `12 passed`，覆盖配置/覆盖/删除、并发幂等/锁、固定请求体、无用户正文、失败保留 Key、错误映射、超时、usage token、同意版本、响应/数据库/日志/备份泄露和 Windows Credential Manager 实际 fixture；后端全量 `uv run pytest` 为 `206 passed, 158 warnings`；前端 `npm run test -- --run` 为 `25 passed`，真实 Chromium 设置流程 `1 passed`；Ruff、Pyright、compileall、typecheck、lint、build 均通过。
- 真实外部调用：没有真实 DeepSeek 请求、真实 Key、用户文件、检索片段或付费 API；不能称真实 Provider 已联通，成功 fixture 只证明 Adapter 和错误边界。
- 阶段遗留：阶段 5 Citation owner、用户级 RAG、Recall@10、10 万 Chunk 性能、最终答案质量和 AC-KB-* 全量验收继续保留；阶段 6 普通 Chat/Learning owner、正式生成、SSE UI、预算、自动回退和学习陪练尚未实现。详见 `docs/test-reports/stage-6-deepseek-credentials.md` 和阶段 5 报告新增遗留表。
- 下一开发批次唯一目标：建立阶段 6 普通 Chat owner 的最小服务端生成边界，继续沿用凭据/外发同意门禁，不打开 RAG/Citation/SSE UI。

### 第三十二批：阶段 6 普通 Chat 服务端会话与生成闭环

- 状态：本批 `PASS`；阶段 6 继续 `PARTIAL`，阶段 5 继续 `PARTIAL`。进场分支为 `feat/v1-bootstrap`，本地与 `origin/feat/v1-bootstrap` 起始 SHA 均为 `79207ccb6d92d1bc0e76deb87edf2e67d4323ed2`，工作区进场干净。
- 数据与迁移：新增 Alembic revision `a7c9e1f2b304`，持久化 `Conversation`、`ConversationScope`、`Message`、`AnswerVersion`、`AiOperation`；普通范围固定为 `GENERAL_CHAT/NONE`。首条提交在单事务中创建会话、范围、`SENT` 用户消息、`PENDING` 助手占位、`PENDING` AnswerVersion、AI Operation 和 `AI_GENERATION` 持久任务；空白页面不落库。
- API：新增 `GET/POST /api/v1/conversations`、`GET /api/v1/conversations/{id}`、`POST /api/v1/conversations/{id}/messages`、`GET /api/v1/conversations/{id}/messages` 和 `GET /api/v1/ai-operations/{id}`。返回会话、两条消息、Operation ID、状态 URL 和可轮询状态；列表、详情、消息分页和回答版本均可在刷新/重启后读取。未添加无实现的停止、重试、重新生成、继续生成或 SSE 端点。
- 幂等与并发：首条和后续消息保存 `Idempotency-Key`、`client_request_id`、请求哈希和 HTTP request ID；同 Key 同正文返回原资源，不追加消息或重复调用 Provider；同 Key 不同正文返回 `IDEMPOTENCY_KEY_REUSED`；同一会话有 `QUEUED/RUNNING` Operation 时拒绝后续发送；`expected_conversation_version` 冲突返回 `412`。
- Provider 与门禁：扩展 `ChatProviderPort` 的 provider-neutral `ChatRequest/ChatResponse` 和 `generate`；默认开发运行时使用确定性 `MockChatProvider`，DeepSeek Adapter 增加非流式 `generate` 和安全响应/usage 解析。外部 Provider 只有在版本化外发同意、凭据存储中有效 Key 和本地输入/输出上限均通过后才调用；无 Key、无同意、超限时 Provider 调用次数为 0；普通聊天不发送文件、知识库、向量、路径或完整 Prompt。
- Worker 与恢复：新增 `ChatGenerationWorker`，复用 SQLite `BackgroundTask` 的原子领取、租约、TaskEvent 和 AnswerVersion；Provider 调用与 HTTP 请求分离。成功写入回答、状态、模型和真实 usage（Mock usage 保持未知）；Provider 错误写入脱敏 error code/detail；启动发现 `RUNNING` Operation 时转为 `INTERRUPTED`，不自动重发不确定的外部请求。
- 测试证据：`tests/test_stage6_chat_owner.py` 8 项定向回归覆盖空白页、原子创建、顺序、幂等重复/冲突、外发门禁、Provider 失败、重启中断、注入 Provider 和 DeepSeek 本地 HTTP fixture 请求体。后端全量 `uv run pytest` 为 `214 passed, 167 warnings`（约 180 秒）；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts`、compileall、Alembic head `a7c9e1f2b304` 和 `git diff --check` 通过。
- 前端与契约：没有聊天页面改动；OpenAPI 3.1 重新导出为 `60 schemas / 68 operations`，生成 `frontend/src/api/generated/openapi.ts`；前端 `npm run test -- --run` 为 `25 passed`，lint、typecheck、build 通过。
- 外部调用边界：Mock Provider 和本地 HTTP fixture 均实际运行；没有真实 DeepSeek API Key、真实 DeepSeek 请求、付费 API、用户私人资料或模型外发，因此未验证实际外部联通、余额或价格。
- 未完成：阶段 5 来源快照 owner/Citation 绑定、用户级 RAG、发布级检索/质量/性能门禁仍为 `PARTIAL`；阶段 6 的聊天前端、SSE/停止、重试/重新生成、Learning owner、预算执行和自动回退不属于本批。
- 下一开发批次唯一目标：在本批服务端普通 Chat owner 之上实现普通聊天前端与可恢复 SSE/停止闭环，继续不打开 RAG、Citation、学习陪练或自动 Provider 切换。

### 第三十三批：阶段 6 普通 Chat 流式前端、断线恢复与停止闭环

- 状态：本批 `PASS`；阶段 6 继续 `PARTIAL`，阶段 5 继续 `PARTIAL`。进场分支为 `feat/v1-bootstrap`；第三十二批的普通 Chat owner、幂等键、`client_request_id`、会话版本和 Provider 外发门禁继续有效。
- 流式契约：创建消息与订阅分离；`GET /api/v1/ai-operations/{operation_id}/events` 使用持久 `TaskEvent.sequence` 作为 SSE `id`，`SNAPSHOT` 发送完整回答快照，前端按序号替换；支持 `Last-Event-ID`/`after`，重连不会重新调用 Provider。提交返回 `events_url`，Operation 查询返回 `stream_sequence`、`event_sequence`、`snapshot_content` 和 `stop_requested`。
- Provider：`ChatProviderPort` 新增 `ChatStreamChunk/generate_stream`。Mock 按确定性分片输出；DeepSeek 适配器解析本地 HTTP fixture 的多行 SSE、UTF-8 文本、`[DONE]`、usage、模型和安全错误。既有非流式 `generate` 和第三十二批注入 Provider 路径保持兼容。
- Worker 与停止：复用 `BackgroundTask`/`ChatGenerationWorker`，在检查点保存完整正文、文本序号、事件序号和停止标记；显式停止进入 `STOPPING`，由 Worker 在快照边界或完成提交前原子收敛为 `STOPPED`，重复停止幂等；自然完成与停止的先提交事务胜出。应用关闭/重启仍把不确定的运行中请求收敛为 `INTERRUPTED`，不自动重发。
- 前端：`/chat` 和 `/chat/:conversationId` 接入真实会话列表、历史消息、创建/继续消息、SSE 解析、有限次重连、断线提示、停止轮询和刷新恢复；空白新会话仍不落库；组件卸载/切换会中止读取并防止旧 Operation 事件写入新会话。未加入 RAG、Citation、学习 UI 或前端 API Key。
- 契约与测试：OpenAPI 3.1 导出 `60 schemas / 70 operations`，前端生成类型同步；新增服务端快照/重订阅/停止竞态/重复停止/DeepSeek SSE fixture 回归。后端全量 `217 passed`；阶段 6 定向 `16 passed`；Ruff、Pyright、compileall、`git diff --check` 通过；前端 Vitest `27 passed`、lint、typecheck、build 通过。
- 真实联调：独立临时数据目录中完成 Mock `创建 → 多个 SNAPSHOT → 完成 → 游标后重订阅`，Provider 调用 `1` 次；延迟 Mock 完成 `创建 → 中途停止` 并保留已生成正文；浏览器 `http://127.0.0.1:5174/chat` 实际发送并显示完成回答，页面错误日志为空。没有真实 DeepSeek Key、真实外部请求、付费调用或私人资料。
- 未完成：阶段 5 Citation owner/RAG 和发布级检索质量仍为 `PARTIAL`；阶段 6 的重试/重新生成与答案版本切换、Learning owner、预算执行和自动回退仍未实现。本批不宣称最终产品验收或真实 Provider 已联通。详见 `docs/test-reports/stage-6-chat-streaming.md`。
- 下一开发批次唯一目标：在本批普通 Chat owner、事件快照和停止状态之上完成重试/重新生成与答案版本切换契约，继续不打开 RAG、Citation、学习陪练或自动 Provider 切换。

### 第三十四批：求职 Demo 知识库问答与真实引用闭环

- 状态：`PASS`（求职 Demo 主流程）；阶段 5、阶段 6 继续 `PARTIAL`。本批不宣称完整 V1 阶段验收或模型回答事实正确性。
- 数据与范围：新增 Alembic revision `c3d4e5f6a7b8` 和 `Citation` 持久化表。首条知识库消息服务端验证活动 `READY` 索引并在同一事务创建 `KNOWLEDGE_CHAT/KNOWLEDGE_BASE` 范围快照；后续消息只读取服务端知识库范围。活动索引切换后，下一轮在同一知识库内创建新范围版本并记录本轮 `index_version_id`。普通聊天数据和行为保持兼容。
- RAG Worker：复用本地查询向量、FTS5/sqlite-vec、混合排序和 `evidence-gate-v1`。支持时只发送长度受限的服务端批准证据块；资料不足保存固定本地拒答、0 Provider 调用和 0 Citation；Embedding/索引/范围竞态单独返回不可用错误，不改走普通聊天。
- Citation：服务端从 gate-approved `HybridAssessmentResult` 创建 `SourceSnapshot`，再绑定真实 `AnswerVersion`，顺序稳定为 `[n]`；新增回答版本/消息/引用读取接口和动态来源状态。回收站、版本失效和永久删除会限制打开能力并清理永久删除摘录，不泄露绝对路径。
- 前端：知识库详情新增“基于此知识库提问”入口；聊天页显示知识库模式、范围名称、索引不可用/资料不足提示、回答内可点击引用、来源定位/摘录/文件详情入口；刷新通过持久消息和 Citation 恢复。普通聊天继续不显示知识库引用。
- 测试证据：后端全量 `220 passed`；新增 `tests/test_stage6_knowledge_chat.py` 3 项覆盖支持/不足/不可用三分支、真实 SourceSnapshot/Citation、刷新读取和 0 Provider 门禁；Ruff、Pyright、compileall、迁移往返、`git diff --check` 通过。前端 `27 tests passed`、lint、typecheck、build 通过；OpenAPI 同步为 `62 schemas / 72 operations`。
- Provider/模型边界：自动化只使用 Mock Provider 与本地可控检索夹具。当前本机固定 ONNX 模型状态为 `MISSING_OFFLINE`，因此没有冒充真实 ONNX 支持分支或真实 DeepSeek 联通；模型缺失分支已验证独立错误和 0 Provider 调用。详见 `docs/test-reports/stage-6-knowledge-chat-citations.md`。
- 下一开发批次唯一目标：安装并验证固定本地 ONNX 模型后，使用真实 READY 知识库完成浏览器级知识库问答、点击引用和刷新恢复；继续不扩展重新生成、学习陪练或自动 Provider 切换。

### 第三十五批：真实本地 ONNX 知识库问答浏览器验收

- 状态：本批求职 Demo 主流程 `PASS`；阶段 5/6 的完整 V1 仍为 `PARTIAL`。固定模型缓存与隔离 Demo 数据根经 ModelManager 离线校验均为 `READY`，没有模型下载、真实 DeepSeek 请求、真实 Key、私人资料或付费调用。
- 隔离目录 `%TEMP%\mindmate-ai-stage35-knowledge-chat-demo` 由现有准备脚本通过文件/知识库 API 与持久 Worker 建立，主库活动 IndexVersion 为 `01a0d95b-bba5-791c-a176-426d08e57765`，预处理、切片、真实 ONNX Embedding、FTS 与原子激活均完成；2 个 Chunk 对应 2 条向量和 2 条 FTS 映射，物理完整性通过。脚本第二轮检查数据计数不变。用户 UI 文件导入/建库未在本批重验。
- 真实 FastAPI + Vite/Chromium：从主库详情进入知识库模式，正例 `API 单次请求超时时间是多少秒？` 完成 SSE、AnswerVersion/Citation 绑定，点击 `[1]` 显示 `服务超时策略.txt` 第 1–12 行和含 `30 秒` 的摘录，刷新和重开会话后正文与 Citation ID 一致；第二轮仍在知识库模式。负例显示固定资料不足，Operation 为 `EVIDENCE_INSUFFICIENT`，Citation 0。
- 同一数据根的受控真实检索 + Mock Provider 审计：正例 FTS rank 1 / vector rank 1、`supported`、Provider 调用 1；负例 `insufficient`、Provider 调用增量 0、Citation 0。浏览器 UI 与受控计数为分别执行的证据；Mock 正文不证明最终答案事实正确性或真实 DeepSeek 联通。
- 首次准备遇到脚本与运行时自动索引接力争抢同一幂等键；已局部修复并补定向回归，全新隔离目录首次准备 `PASS`。另一次与全量测试并行的浏览器复核返回 `MODEL_UNAVAILABLE`，独占复跑 `1 passed`，根因未证实，已如实保留在报告。
- 门禁：后端定向 `4 passed`、全量 pytest 退出码 0、Ruff 全通过、Pyright 0 错误、Alembic `c3d4e5f6a7b8 (head)`；前端 `27 passed`、lint/typecheck/build 通过；浏览器 E2E 独占复核 `1 passed`，`git diff --check` 通过。详见 `docs/test-reports/stage-6-real-onnx-knowledge-chat-browser.md`。
- 下一批唯一建议：封装可重复的本地求职 Demo 演示入口，并针对并发下偶发的 `MODEL_UNAVAILABLE` 建立可复现诊断；不默认启用真实 DeepSeek 或私人资料。

### 第三十六批：求职 Demo 稳定启动与模型不可用诊断

- 状态：本批代码与定向回归 `PASS`；Windows 现场演示闭环未在本环境重跑。阶段 5、阶段 6 的完整 V1 仍为 `PARTIAL`。进场分支 `feat/v1-bootstrap`，起点 `af8e9c7`，与 `origin/feat/v1-bootstrap` 一致。用户本机暂停前的未提交改动不在远端，本批按续接记录重新落地，没有覆盖默认用户数据。
- 演示入口：新增 `scripts/demo.ps1`，复用 `prepare_stage5_fixed_ready.py` 和扩展后的 `scripts/dev.ps1`。默认数据根 `%TEMP%\mindmate-ai-stage36-job-demo`，API `127.0.0.1:8001`，页面 `127.0.0.1:5174`。Provider 固定 Mock。端口占用、固定模型缓存缺失或准备失败时停止，不换端口、不下载模型、不调用真实 DeepSeek。`%TEMP%` 可能被系统清理；所有权标记仍由准备脚本保护。
- 正例正文：浏览器 E2E 现在按段落渲染规范化空白后，把助手消息区域的可见正文与 Operation / 持久消息逐字比较，刷新和重开后再比一次。负例断言可见拒答正文且该条回答没有引用按钮。SSE 只检查 HTTP 200 和 Operation 终态，不再读取可能失效的响应体。
- `MODEL_UNAVAILABLE`：查询编码原先调用非阻塞 `ModelManager.status()`。锁被占用时状态是 `INSTALLING`，即使磁盘模型仍是 `READY`，编码器也会把它映射成 `MODEL_UNAVAILABLE`。知识库页会查询模型状态，而状态检查会在锁内校验约 95MB 模型，因此第一次提问可能撞上这把锁。定向测试让编码器在锁释放前保持等待，随后得到真实的 `MODEL_MISSING_OFFLINE`，不再得到 `MODEL_UNAVAILABLE`。修复是等待这把已有的锁，不是重试，也没有把不可用改成资料不足。
- 第三十五批与全量测试并行的那次失败，以及暂停前第二次独占浏览器失败（Operation `01a0db04-bcbd-7687-ad8a-ab3e14be77bf`，request `01a0db04-bcaa-717f-bf8a-508f181ae279`）仍然单独保留。本环境没有那次 Windows 进程，也没有固定模型缓存，不能把本批单测说成已经回放了那两个现场 Operation。意外异常仍记为 `MODEL_UNAVAILABLE`，并写入 `uvicorn.error` 的安全字段。
- 门禁：后端 `python -m pytest -q --disable-warnings` 退出码 0，227 项里 225 通过、2 跳过（固定模型缓存不存在、Windows Credential Manager）。Ruff 通过。本批改动的 Pyright 为 0 错误；Linux 全量 Pyright 仍有一处既有的 `ctypes.WinDLL` 报错，文件未改。前端 Vitest 27 通过，lint、typecheck、build 通过。`git diff --check` 通过。没有真实 ONNX 浏览器复跑，没有真实 Key 或付费调用。
- 下一批唯一建议：在你当场确认后，用固定合成资料做一次手动真实 DeepSeek 小范围验收。默认 `.\scripts\demo.ps1` 继续使用 Mock，不要把真实 Key 放进自动化。

### 第三十七批：Windows 求职 Demo 现场稳定性

- 状态：本批 `PASS`；阶段 5、阶段 6 的完整 V1 仍为 `PARTIAL`。进场分支 `feat/v1-bootstrap`，本地与远端 SHA 均为 `9f68fe213df5b58abe7b37474d3bf7e08dde3d1e`，工作区干净。环境为 Windows PowerShell 5.1、Python 3.12 虚拟环境、Node 22。只使用 `docs/test-data/stage5-fixed-ready/` 的公开合成资料、Mock Provider 和 `%TEMP%\mindmate-ai-stage36-job-demo`。
- 阻断修复：从仓库根目录运行 `.\scripts\demo.ps1` 时，应用启动按当前目录查找 `migrations`，准备失败并退出码 1。`backend/alembic.ini` 改为以配置文件所在目录定位迁移和 `src`。`tests/test_local_runtime.py` 增加工作目录不在 `backend/` 时的启动回归。修复后同一命令完成准备并启动。
- 首启：准备报告 `second_pass=passed`、`counts_unchanged=true`，文件 9、知识库 4、任务 30；主库与活动索引均为 `READY`，指纹 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`。运行中模型与索引复核通过。端口为 `127.0.0.1:8001` 和 `127.0.0.1:5174`。没有下载模型。
- 浏览器：`frontend/` 中设置 `MINDMATE_WEB_PORT=5174` 与固定主库、索引版本后，`npx playwright test e2e/stage6-real-onnx-knowledge-chat.spec.ts --reporter=line` 退出码 0，`1 passed`（10.7 秒）。正例 Operation `COMPLETED`，可见正文与持久消息一致，引用文件为 `服务超时策略.txt`，行 1–12，来源 `AVAILABLE`。负例 `EVIDENCE_INSUFFICIENT`，可见“资料不足”，Citation 0。这次浏览器证据不包含 Provider 调用次数。
- 受控计数：服务器停止后单独运行 `backend/scripts/verify_stage6_real_onnx_chat.py`，退出码 0。真实检索正例 `supported`，Mock 调用 1；负例 `insufficient`，Mock 调用增量 0，Citation 0。模型状态 `READY`。这与浏览器会话是分开的证据。
- 停止与二次启动：结束本批启动的后端后，8001/5174 释放，8000/5173 仍空闲，系统浏览器进程未被结束。脚本等待循环因此以退出码 1 离开，清理函数已执行。二次 `.\scripts\demo.ps1` 再次 `counts_unchanged=true`，文件仍为 9、知识库仍为 4，同一索引版本 `READY`；任务变为 35，只增加了问答产生的 `AI_GENERATION`，`FILE_IMPORT` 仍为 9。没有自动下载。
- 刷新恢复：二次启动后重新打开浏览器里的同一会话并刷新。可见正文在刷新前后一致，并与持久助手消息一致；两条正例回答各保留 1 条 Citation，资料不足 Operation 仍为 `COMPLETED / EVIDENCE_INSUFFICIENT` 且 Citation 0。
- 隔离锁对照：`pytest tests/test_stage36_query_encoder_lock.py` 为 `4 passed`。空目录在锁释放后是 `MISSING_OFFLINE`。固定模型缓存上，持锁时非阻塞状态为 `INSTALLING`，释放后阻塞查询为 `READY`（约 0.4 秒）；查询编码在持锁期间不返回，释放后得到 512 维向量，没有 `MODEL_UNAVAILABLE`。没有为了让演示 E2E 超时而长时间占锁。
- 本批浏览器、受控审计和锁对照都没有新的 `MODEL_UNAVAILABLE`。第三十五批并行失败和暂停前 Operation `01a0db04-bcbd-7687-ad8a-ab3e14be77bf` 没有按原请求重放，根因仍不能逐条改写。
- 门禁：定向 `tests/test_local_runtime.py` 为 `8 passed`；Ruff 与 Pyright 对该文件为 0 错误。没有改前端，没有重跑前端全量或后端全量。`git diff --check` 在提交前执行。没有真实 Key 或付费调用。
- 下一批唯一目标：在获得明确授权和单次预算上限之后，用同一套公开合成资料做一次手动真实 DeepSeek 小型冒烟；未授权前不要把本批 Mock 证据写成真实模型验收，默认演示命令继续使用 Mock。
