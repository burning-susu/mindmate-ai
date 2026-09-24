# 索引预处理输入契约

## 目的

`INDEX_PREPROCESS` 是阶段 5 的内部持久任务。它只冻结知识库输入、配置和逐文件检查结果，为后续 Chunk、Embedding、FTS5 与 sqlite-vec 构建提供入口；任务完成不表示索引已建成或可检索。

## 配置语义

- `ChunkingConfig.measurement_unit=UNICODE_CHARACTER`，默认目标约 500 个字符、重叠约 80 个字符。通用 `target_size` 等字段不得解释为旧需求中的 token 数。
- `EmbeddingConfig` 使用本地 ONNX `BAAI/bge-small-zh-v1.5`、512 维、归一化与余弦距离。历史 `model_revision=NULL` 行表示当时尚未验证；第十二批验证通过后新建的默认配置保存复合模型 revision 与产物指纹。
- 两类配置都以规范 JSON 的 SHA-256 指纹去重；配置中不保存 API Key 或凭据引用。

## 固定 ONNX 来源与校验（第十二批）

固定基础模型为 `BAAI/bge-small-zh-v1.5`，revision `7999e1d3359715c523056ef9478215996d62a620`。官方模型卡标记 MIT 许可，并列出 safetensors 权重与 tokenizer；该 revision 没有 ONNX 文件。本项目不把模型 ID 当成 ONNX 下载地址，也不在应用端安装或加载 PyTorch。

运行时采用第三方仓库 `Xenova/bge-small-zh-v1.5` 的不可变 revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`。其模型卡 `base_model` 指向固定的 BAAI 模型。该第三方卡片没有单独填写 license 字段；来源许可依据 BAAI 上游 MIT 声明，归属与第三方未单独声明事项保留在本契约中。本项目没有自行导出 ONNX，因此不宣称该仓库提供了导出器版本；第三方 revision、逐文件 SHA-256 和原模型输出等价性是本产物的固定证据。

| 用途 | 固定文件 | 字节数 | SHA-256 |
| --- | --- | ---: | --- |
| 上游 BAAI 权重参考 | `model.safetensors` | 95,827,648 | `354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026` |
| 上游 BAAI 模型配置 | `config.json` | 776 | `3853a7979202c348751b753e36f579c41d8da7d36af617d3d907e1fc9b441f2a` |
| 上游 tokenizer | `tokenizer.json` | 439,125 | `48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26` |
| 上游 tokenizer | `tokenizer_config.json` | 367 | `e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a` |
| 上游 tokenizer | `special_tokens_map.json` | 125 | `b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3` |
| 上游 tokenizer | `vocab.txt` | 109,540 | `45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c` |
| 安装 ONNX | `onnx/model.onnx` | 94,851,877 | `69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a` |
| 安装 tokenizer | `tokenizer.json` | 439,125 | `48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26` |
| 安装模型配置 | `config.json` | 716 | `d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f` |

官方 `model.safetensors` 的本地 SHA-256 与 Hugging Face LFS 元数据一致；Xenova tokenizer 文件与 BAAI 固定 revision 的 tokenizer 字节完全一致。应用只下载表中 3 个运行时必要文件，总计 95,291,718 字节；模型权重不进入 Git、安装包或测试 fixture。

安装位置为应用数据目录 `models/bge-small-zh-v1.5/<artifact-fingerprint>/`。安装器只访问固定的 HTTPS Hugging Face revision，限制跳转域、10 秒连接/30 秒读取/15 分钟总超时、128 MiB 总量、路径和并发；写入同卷 `<fingerprint>.partial`，校验每个文件大小与 SHA-256、模型配置后再原子发布。失败保留 partial 文件和稳定错误码，可取消后重试；离线缺失状态明确为 `MODEL_MISSING_OFFLINE`。TLS 校验保持开启，不运行 remote code，不记录文件正文或凭据。应用启动只创建本地目录，不下载或加载 ONNX；调用方必须在明确需要时使用 `ModelManager`，随后显式创建 `OnnxEmbeddingAdapter`。

校验后的复合 `EmbeddingConfig.model_revision` 为：

~~~text
7999e1d3359715c523056ef9478215996d62a620;75c43b069aac4d136ba6bc1122f995fedcfd2781;4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5
~~~

三段依次是 BAAI 基础 revision、Xenova ONNX revision、包含来源/版本/文件哈希/推理规则的 artifact fingerprint。旧的 `model_revision=NULL` 配置行保留用于历史追溯；新默认配置以此复合值参与配置指纹。

适配器使用 `tokenizers` 本地解析固定 `tokenizer.json`，ONNX Runtime 只启用 `CPUExecutionProvider`。输入规则为查询前缀 `为这个句子生成表示以用于检索相关文章：`，文档正文不加前缀；取 `last_hidden_state` 按 `attention_mask` 做 mean pooling，再做 L2 归一化。单次批量上限 16、CPU 线程默认 2 且最多 4、最大序列 512 个 WordPiece。单条预处理字符数超过 16,000 或 token 数超过 512 时返回稳定错误，不截断、不静默丢正文；上游切片目标仍为约 500 个 Unicode 字符。

Windows 11 x64 / Python 3.12.11 实际 CPU 验证使用 ONNX Runtime 1.30.0、tokenizers 0.23.2；对照环境的 PyTorch 2.8.0+cpu 与 Transformers 4.56.2 仅用于验证，不是应用依赖。固定样本为带查询前缀的“什么是向量数据库？”及两个中文文档。原始权重与 ONNX 产物使用相同 tokenizer ID、mean pooling 和 L2 normalization，输出 `(3, 512)`，最大绝对误差 `1.1175871e-7`、最小余弦相似度 `1.0`。两侧将整批向量 `np.round(vectors, 4).astype('<f4').tobytes(order='C')` 后的 SHA-256 均为 `eeb4b3cb2117502891e3af08e009d24aa733f3a4d65c7e4080827d407b3f0ac5`。本机安装器实测状态 `READY`，CPU 输出有限且范数为 1。

本批只交付模型获取/校验和独立 Adapter。没有将 Adapter 接入 `INDEX_CHUNK` 后的 Worker，没有 `EmbeddingRecord`、FTS5、sqlite-vec、索引激活或检索；IndexVersion 继续为 `BUILDING`，知识库仍不可检索。

## 版本与输入

- 每次非幂等的新任务创建新的 `IndexVersion`，旧版本不覆盖。
- `parse_revision_set_hash` 对按成员 ID 排序的文件 ID、内容哈希、解析修订和成员加入时间求规范指纹。
- `IndexVersionInput` 保存每个活动成员的不可变快照；结果为 `PREPARED`、`SKIPPED` 或 `FAILED`，并保存稳定原因码。
- Worker 在完成前重新校验已准备输入。成员移出/重加、文件进入回收站、内容哈希或解析修订变化时，旧快照不会重新激活成员，也不会被后续构建直接采用。

## 恢复与后续消费

- `BackgroundTask.checkpoint_json` 保存 `index_version_id`、配置指纹、集合指纹、逐项结果和下一序号；租约过期或应用重启后，Worker 从仍为 `PENDING` 的输入继续。
- 任务终态 `COMPLETED` 只表示预处理已结束；`summary.index_ready` 始终为 `false`。
- 本批 `IndexVersion.status` 始终停留在 `BUILDING`，并用 `preprocessing_status` 区分 `COMPLETED/PARTIAL/FAILED/CANCELLED`。
- 后续构建 Worker 只能消费同一 `IndexVersion` 中仍为 `PREPARED` 且再次通过版本校验的输入。只有 Chunk、FTS、Embedding 与向量产物全部验证通过后，后续批次才可在单一事务中设置 `READY` 和 `active_index_version_id`。
- 本批没有公开 `/rebuild` 或 `index-status` API；前端继续显示“索引待建立”，不可开放对话或学习入口。

## Chunk 消费阶段（第十一批）

- `INDEX_CHUNK` 是独立于 `INDEX_PREPROCESS` 的持久任务。它只能消费同一 `IndexVersion` 中状态为 `PREPARED` 的输入；`SKIPPED/FAILED` 输入不会被误切片。
- `/api/v1/tasks/{task_id}/cancel` 接受 `INDEX_CHUNK` 和 `INDEX_PREPROCESS` 任务；取消请求设置持久任务终态，Worker 在切片块边界及发布前检查该状态。
- Worker 每次只处理一个文件；解析结果沿用解析层的 20 MiB 序列化输出上限，长文本切片在事务外计算，最终每文件一个短事务写入，不跨文件累积待写 Chunk。
- Chunk 是文件级派生数据，唯一范围为 `file_id + parse_revision_id + chunking_config_id + sequence_number`，不绑定某个知识库。相同文件版本和配置被多个知识库引用时复用同一组 Chunk。
- `IndexVersionInput.chunk_status` 保存逐文件 `PENDING/RUNNING/CHUNKED/SKIPPED/FAILED` 检查点；一份文件的 Chunk 集、检查点和任务进度在同一短事务中发布。租约过期、进程关闭或取消后，未发布的 `RUNNING` 输入会回到 `PENDING`，不会留下半套结果。
- 切片只保存解析产物真实提供的定位字段：PDF 的页码、PPTX 的幻灯片号、文本可确定的行号以及解析器提供的标题路径；没有真实分词器时 `token_count=NULL`，有效长度通过 `length_unit=UNICODE_CHARACTER` 与 `length_value` 表达。
- DOCX v2 解析产物显式标记可从样式识别的标题、列表、普通段落和代码样式；表格仍以解析器提供的表号/行号保留为结构块。没有段落样式元数据的既有解析结果不会被推测补标签。
- Chunk 阶段完成只表示文件级切片已生成或已记录稳定失败原因。`IndexVersion.status` 仍为 `BUILDING`，`chunking_status` 只反映 `COMPLETED/PARTIAL/FAILED/CANCELLED`，不会设置 `active_index_version_id`，成员仍不可检索。
- 后续 Embedding/FTS5/sqlite-vec Worker 必须再次校验成员、回收站状态、文件内容哈希、解析修订和切片配置指纹后，才能消费这些 Chunk；本批不下载模型、不写 Embedding、不激活索引。
- 文件或递归文件夹永久删除时按明确 `file_id` 清理其 Chunk；其他 File 记录的版本不受影响。知识库删除只删该库成员关系和索引快照，不删文件级 Chunk，因为其他知识库仍可能复用。

## 持久 Embedding 阶段（第十三批）

- `INDEX_EMBED` 是独立 SQLite 持久 Worker，只接受仍为 `BUILDING` 且已完成预处理/切片的 `IndexVersion`，逐文件消费同版本 `PREPARED + CHUNKED` 输入。每个输入保留 `PENDING/RUNNING/EMBEDDED/SKIPPED/FAILED` 状态、稳定失败原因、向量数量和完成时间；任务 JSON 保存 IndexVersion、EmbeddingConfig fingerprint、固定 model revision、包含 tokenizer 的 artifact fingerprint、进度与逐文件结果。
- Embedding/向量写全局并发最多 1。SQLite 部分唯一索引约束最多一个 `INDEX_EMBED/RUNNING` 任务，原子领取使用 lease；过期 lease 先转中断再接管，Worker 关闭释放自己的任务租约，`RUNNING` 文件输入在恢复时回退到 `PENDING`。
- 默认配置必须匹配 `BAAI/bge-small-zh-v1.5` 复合 revision、`LOCAL_ONNX`、512 维、L2 normalization、余弦距离及稳定配置指纹。模型仅通过 `ModelManager.ensure_installed(allow_download=False)` 离线校验后懒加载；文件缺失/损坏或 runtime 校验失败产生持久稳定错误并可显式重试，不下载、不切换模型、不访问外部 Embedding API。
- `EmbeddingRecord` 唯一键为 `chunk_id + embedding_config_id`，保存向量记录 ID、配置 fingerprint、向量 SHA-256、`PENDING/READY/INVALIDATED` 状态和失效时间，不存原始向量。相同文件解析修订、Chunk 配置和 Embedding 配置在多个知识库中共享一次推理与映射记录。
- 实际向量由 `SqliteVecAdapter` 写到本地 sqlite-vec SQLite 文件；每个 `embedding_config_id + index_version_id` 单独数据库，并在旁表保存 UUID 映射、Chunk ID 和 SHA-256。Adapter 验证 512 维、有限值、单位范数、扩展版本与存储 identity，提供幂等 upsert、按 ID 读取/存在性/hash 对账、按 ID 删除和按 IndexVersion 清理。扩展加载权限仅在 `sqlite_vec.load` 调用期间开启。
- 跨 SQLite 数据库事务采用恢复协议：数据库事务先建立/确认 EmbeddingRecord 并记录预期向量 hash；向量库按稳定 ID 幂等写入；最后在业务数据库短事务中复核当前任务租约、成员、回收站、成员加入时间、内容 hash、解析修订、Chunk 集和配置 fingerprint，再同时将记录标为 `READY`、输入标为 `EMBEDDED` 并提交任务检查点。若向量已写但最终事务未提交，重启时由 ID/hash 读取已有向量并补完成功标记；向量内容或 Chunk ID 不符时失败关闭，不报告成功。
- 文件级失败不阻断同版本其他文件；显式 `retry_failed` 将失败输入恢复到 `PENDING`，已存在且验证一致的向量不会重复推理。任务摘要暴露 `retryable` 与稳定 `error_code`，模型缺失错误可在固定模型变为可用后重试。取消、租约失效、知识库/成员移除和输入修订变化不会将过期输入标为成功；失败、模型缺失及向量写入错误保留稳定原因供重试。
- 永久删除知识库只删除该知识库 `IndexVersion` 的向量数据库与版本快照，不删除其他知识库可能复用的文件级 Chunk/EmbeddingRecord。文件永久删除清理目标文件在相关 IndexVersion 中的向量记录，再删除该文件 EmbeddingRecord 与 Chunk；清理失败时业务行仍保留并返回可重试错误。
- `INDEX_EMBED` 成功只表示“Embedding 已生成并持久化”。`IndexVersion.status` 继续为 `BUILDING`，`active_index_version_id` 不变，知识库成员 `index_state` 不变且 `available_for_retrieval=false`；本批没有 FTS5、向量 Top-K、索引激活、混合检索、引用或 RAG，也没有新 API 路由和 UI 页面。
- Windows 11 / Python 3.12 的本批证据包括真实文件 sqlite-vec 512 维持久写入、重启双向映射对账，以及使用 Git 忽略的固定 `manager-validation` 模型缓存离线执行真实 ONNX Worker。缓存既不生成也不修改、不清理、不提交；若目标环境没有匹配缓存，仅以固定离线 Fixture 测试，不能宣称该环境完成了真实模型 Worker 冒烟。

## 持久 FTS5 投影阶段（第十四批）

- `INDEX_FTS` 是独立 SQLite 持久任务，只处理同一 `IndexVersion` 中仍为 `PREPARED + CHUNKED` 的输入；再次校验知识库未软删除、成员仍为 ACTIVE 且 `added_at` 与快照相同、文件未进回收站、内容 hash/解析修订一致、Chunk 集完整且属于该切片配置。
- Alembic revision `d60f2e8a7c31` 增加 `IndexVersion.fts_status` 和 `IndexVersionInput.fts_status/fts_reason_code/fts_count/fts_indexed_at`，以及 `fts_chunk_map`。映射唯一键是 `index_version_id + chunk_id`，外键约束到 IndexVersion、Chunk、File 和 ChunkingConfig，并记录 `file_id`、`parse_revision_id`、`chunking_config_id` 和 Chunk 正文 `content_hash`；FTS 虚表 `index_chunk_fts` 的 rowid 对应映射主键。IndexVersion 是隔离边界，新版本构建不会清空旧版本。
- 虚表只存派生的 Chunk 正文投影，不替代 `Chunk`。同一 SQLite 事务内替换该文件当前版本映射/FTS 行、更新逐输入结果和任务 JSON 检查点；崩溃只可能看到旧投影或新投影，不会看到半套。失败文件不阻断同版本其他文件；租约过期接管会把 RUNNING 输入复位为 PENDING，显式 `retry_failed` 可重试失败项；`rebuild=true` 可先清单个 IndexVersion 的派生行，再从权威 Chunk 重建。
- 单运行约束使用 `INDEX_FTS + RUNNING` SQLite 部分唯一索引。Worker 支持关闭中断、任务取消和租约续期；任务摘要将索引状态固定为 `BUILDING`/`available_for_retrieval=false`，不设置 `active_index_version_id`。
- FTS5 列为不索引的原文 `content`、`han_bigrams`、`han_unigrams` 和 `terms`，tokenizer 为 `unicode61 remove_diacritics 2`。连续汉字额外生成重叠二元词与单字辅助词，二字及单字短中文查询可匹配；拉丁/Unicode 非汉字词项按词并大小写折叠。当前未依赖 ICU/Jieba，英语支持词项检索但不承诺词干/同义词；BM25 可用于后续排序，本批不评估最终相关性、Recall 或公开查询 API。
- 内部 MATCH/BM25 校验必须通过 `fts_chunk_map` 限定 IndexVersion，并 join 当前 `IndexVersionInput`、KnowledgeBaseFile、KnowledgeBase、FileRecord 和 Chunk，确认输入仍已索引、成员仍 ACTIVE 且加入时间未变、知识库/文件未删除、文件 hash/解析修订和 Chunk hash/配置仍一致、版本仍为 BUILDING。软删除或移出即使暂留历史 FTS 行也会被过滤；此内部校验不是公开检索端点。
- FTS5 内部 `integrity-check` 验证虚表倒排结构；`consistency_check` 另验证映射、FTS row、当前 Chunk 正文/哈希/版本字段双向一致。两类检查不可互相替代。损坏时仅删除对应版本派生投影并从 Chunk 重建，不需要重跑解析、切片或 Embedding。
- 永久删除知识库时只删除它的 IndexVersion FTS 映射/虚表行与版本向量空间，不删除其他知识库可复用的文件级 Chunk/EmbeddingRecord。永久删除文件时删除该源文件在相关版本中的 FTS 行与输入快照，同时清理该源文件自己的 Chunk/Embedding/向量；若未激活版本还有其他输入，则仅移除目标输入、保留其他文件映射并将该版本标记 `NEEDS_REBUILD`/`fts_status=INVALIDATED`，使旧版本不能继续被内部 MATCH 使用。版本不再含任何输入时才整体删除。
- FTS-only 降级边界是从 `d60f2e8a7c31` 回退到 `a81f3c6d2e90`：删除 FTS 虚表、映射和 FTS 检查点列，即丢弃可重建衍生数据；不触碰 Chunk、EmbeddingRecord、sqlite-vec 文件、原始文件或其他业务表。重新升级后 FTS 为空，必须显式重建。禁止以此证据推导允许降级穿过此前包含持久用户数据的迁移。
- 第十四批验证：后端 `105 passed`；Ruff、Pyright `0 errors`、compileall 通过；空库和已有数据升级、FTS-only downgrade/re-upgrade 后 Chunk/EmbeddingRecord 数量保持且可重建；固定中文/英文 MATCH、BM25、逐输入进度、租约接管、取消、逐项失败/重试、损坏恢复、成员移除、文件回收站/永久删除、共享 Chunk 和知识库定向清理均通过。该阶段没有新增公开 API、OpenAPI schema 或前端改动。

## 内部向量 Top-K 查询阶段（第十五批）

- `SqliteVecAdapter.search` 是只读的内部 Adapter 查询，输入固定 `512` 维、有限、L2 单位归一化查询向量，以及 `1..30` 的 `k`；默认和最大候选数均为 `Top 30`。查询向量维度、有限值、单位范数和 `k` 越界分别返回稳定错误码，不静默截断或补齐。
- `VectorTopKQuery` 只接受内部已选择的 `knowledge_base_id + index_version_id`，并验证版本属于该知识库、仍为 `BUILDING`、使用 `sqlite-vec`，EmbeddingConfig 与固定 `LOCAL_ONNX`/`BAAI/bge-small-zh-v1.5`/512 维/归一化余弦配置和指纹一致。没有公开路由，前端不能提交任意版本 ID。
- 范围在 Top-K 前生效：业务 SQLite 先限定 `IndexVersionInput` 为 `PREPARED + CHUNKED + EMBEDDED`，当前成员为 `ACTIVE` 且 `added_at` 与输入快照一致，知识库和文件未软删除，文件仍为 `PARSED` 且内容哈希/解析修订一致，Chunk 未失效且属于该切片配置，EmbeddingRecord 为 `READY`、未失效、配置指纹和向量 hash 一致；只把这些记录的 `vector_store_record_id` 交给 Adapter。
- 现有每版本 sqlite-vec 虚表没有动态成员分区列，不能使用 `k` 较小的 KNN 结果再做 SQL JOIN 过滤，否则范围外近邻会挤掉范围内候选。Adapter 因此读取当前版本全部 KNN 行（`k = 向量总数`），在 Adapter 内先按允许记录集合过滤，再按原始距离和稳定 `vector_store_record_id` 排序并截断；这是精确的两阶段策略，查询成本为 O(N)，后续大规模检索需要专门的分区/候选索引设计，不能把本实现当成 10 万 Chunk 性能证据。
- sqlite-vec 当前虚表使用默认 L2 距离；在存储向量和查询向量均为单位范数时，应用结果的余弦距离固定为 `d_l2² / 2`，相似度为 `1 - cosine_distance`，距离升序与相似度降序等价。等分时按 `vector_store_record_id` 升序，返回 `chunk_id`、`file_id`、`index_version_id`、配置 ID、记录 ID、距离、相似度、原始 sqlite-vec 距离和稳定 rank。
- 空库、没有向量或有效范围为空返回空结果；版本/知识库/配置不匹配、向量库文件不可用或 ID/hash/维度不一致返回明确内部错误。查询不写业务 SQLite 或向量库，不改变 `IndexVersion.status=BUILDING`、`active_index_version_id`、成员 `index_state` 或 `available_for_retrieval=false`。
- 第十五批不新增 Alembic、API/OpenAPI、前端或 Worker；FTS5 投影、Embedding 生成和已有删除/清理语义保持不变。内部 Top-K 通过不等同知识库公开检索，不实现 FTS/向量融合、RRF、阈值、重排、引用、索引激活或 RAG。

## 内部双路候选阶段（第十六批）

- `Fts5Projection.match_version` 是内部关键词候选入口。查询先做 NFKC 和空白规范化，再将汉字连续串转换为重叠二元词/单字辅助字段，将非汉字字母和数字转换为大小写折叠词项；引号、布尔运算符、通配符等符号不会作为 FTS5 表达式执行。空输入或只含符号返回空结果，输入 `limit` 固定在 `1..30`。
- FTS SQL 使用真实 `MATCH` 与 `bm25()`，先连接并校验 `IndexVersionInput`、成员、知识库、文件、Chunk 和投影映射，再按 BM25 升序及 `chunk_id` 稳定排序和 Top 30 截断。输出保留 `score`/`bm25`、`fts_rank`、`file_id`、`index_version_id`、解析修订和 Chunk 配置，不使用 `LIKE`。
- `HybridCandidateQuery` 在同一 `knowledge_base_id + index_version_id` 下分别调用 FTS5 Top 30 与 `VectorTopKQuery` Top 30。两路都重新校验 ACTIVE 成员、快照加入时间、文件解析状态/回收站、内容 hash、解析修订和有效 Chunk；向量路另外校验固定 EmbeddingConfig、`EmbeddingRecord.READY`、配置指纹、向量 hash 和 sqlite-vec 记录一致性。每路先过滤再截断，范围外候选不会挤占名额。
- `merge_candidates` 只按 `chunk_id` 合并，不按相邻位置或文件名去重；它保留两路原始 rank/分数、来源文件、IndexVersion 和来源通道。单路命中时另一组字段为 `NULL`，不写入零分、伪排名或补造向量；结果使用首个通道 rank、双路命中优先和 Chunk ID 的确定性顺序，仅作为下一批 RRF 输入。
- 双路开始和合并前分别计算版本、成员、文件、Chunk 与 EmbeddingRecord 的范围指纹。若成员移出/重加、回收站、解析修订、Chunk/EmbeddingRecord 失效或版本状态在两路间变化，返回 `RETRIEVAL_SCOPE_CHANGED`，不发布旧候选。路由异常默认保留原错误语义并失败关闭；调用方显式允许降级时，结果带 `fts_error`/`vector_error`，不得伪装成完整双路成功。
- 第十六批没有新增迁移、公开 API、OpenAPI、前端、索引激活、RRF、重排、引用或 RAG。向量路仍使用第十五批记录的精确 O(N) 范围过滤策略；本批没有 10 万 Chunk 性能验收。
- 第十六批验证：后端 `117 passed`；真实 SQLite FTS5/sqlite-vec 夹具覆盖 FTS-only、Vector-only、双路同 Chunk、不同 Chunk、中文短词/英文/编号/特殊符号/空输入、范围外高排名、成员中途变化、版本/配置隔离和单路故障；Ruff、Pyright、compileall、`git diff --check` 通过。第十六批结论 `PASS`，阶段 5 仍为 `PARTIAL`。

## 内部 RRF 与多样性排序阶段（第十七批）

- 在已按当前版本/知识库范围验证并按 `chunk_id` 去重的候选集上调用纯函数 `rank_candidates`；该函数不访问数据库或外部服务。`HybridCandidateQuery` 只负责双路收集、合并、加载有效文件显示名、Chunk 正文/标题路径/序号、复核范围指纹，再调用排序并截断 Top 8。无公开检索/API 路由。
- 排序版本为 `rrf-exact-diversity-v1`。配置默认 `rank_constant=60`、`final_top_k=8`。RRF 分数为 `sum(1 / (60 + rank))`，只累加非 NULL 的 `fts_rank` 和 `vector_rank`；缺失通道贡献为 0，但源字段仍保持 NULL。RRF 分数是倒数排名融合量，不是概率，也不把 BM25 和余弦分数相加。
- 精确奖励证据使用当前命中 Chunk 对应的文件显示名、heading path 和 body。三者统一做 NFKC、casefold；Unicode 标点、空白及符号变为空格分隔。完整规范化查询短语（至少 4 个规范化字符）奖励 `0.002`；每个精确词项奖励 `0.0004`，单候选总奖励最多 `0.004`。ASCII 拉丁词/编号要求 ASCII 字母数字/下划线边界，避免 `AI` 命中 `PRAIRIE` 子串；长中文连续查询以重叠三字片段检查，二字词项只按四分之一权重。评分记录命中项、`file_title`/`heading`/`content` 字段、奖励及 `EXACT_PHRASE`/`EXACT_TERM` 原因码。短词奖励受总上限约束，不替代后续证据阈值。
- 多样性使用有界贪心重排，不硬删除候选。对已选择集中每个相同 `file_id` 候选施加 `0.001` 惩罚，最多累计两项；若 Chunk 序号距离不超过 1 且 NFKC/casefold 文本的三元字符集合重叠系数达到 `0.6`，另加 `0.0025` 惩罚。单候选总多样性惩罚最多 `0.0035`。每轮从 `RRF + 精确奖励 - 当前惩罚` 最高项选择，其他唯一候选仍保留在排序池。
- 确定性并列键依次为：RRF 降序、精确奖励降序、最佳原始 rank 升序、双路命中优先、FTS rank 升序、vector rank 升序、`file_id` 字典序、Chunk 序号升序、`chunk_id` 字典序。重排后名次是 1-based，最多返回配置的 8 个候选。每项可审计字段包括原始两路 rank/分数、RRF 分、命中词与字段、精确奖励、惩罚/原因、最终分/名次和算法版本；显式故障降级另保留失败通道、错误码及 `degraded` 标记。
- 双路前后范围指纹逻辑保持不变，读取候选文件标题和 Chunk 上下文后再做一次范围复核；文件显示名也纳入范围指纹，避免标题变化期间使用不一致的精确匹配上下文。任何版本、成员、文件、Chunk 或 EmbeddingRecord 范围变化仍返回 `RETRIEVAL_SCOPE_CHANGED`。不改变 `IndexVersion.status=BUILDING`、`active_index_version_id` 或 `available_for_retrieval=false`。
- 固定离线样本覆盖 FTS-only、Vector-only、双路同 Chunk、两个文件相关性相近、相邻高重叠片段、完整编号/标题与模糊短词、大小写/全半角/标点、同分与反转输入顺序、空候选、Top 8、单路显式降级和范围变化。真实 SQLite FTS5 + sqlite-vec 集成测试验证排序信号。该固定样本不等价于最终 Recall@10 验收。
- 第十七批验证：后端 `122 passed` 串行；Ruff 全量通过；Pyright `0 errors, 0 warnings, 0 informations`；compileall 与 `git diff --check` 通过。没有前端/API 改动，未运行 UI E2E；没有 DeepSeek/真实凭据/付费服务调用或真实用户资料。第十七批 `PASS`；阶段 5 仍 `PARTIAL`，证据阈值、严格拒答、引用、RAG 与索引激活仍未完成。

## 内部证据充分性判定阶段（第十八批）

- `HybridCandidateQuery.search_and_assess_with_status` 在既有知识库/`IndexVersion` 校验、双路范围指纹复核、按 `chunk_id` 合并及 RRF/多样性 Top 8 后调用本地门控。判定器不访问数据库、模型或外部服务；`IndexVersion` 必须仍为 `BUILDING` 且内部 FTS/Embedding 状态可用。版本不在范围、失效/回收站、未就绪或检索过程中范围变化不会被转成“资料不足”。
- 门控规则版本为 `evidence-gate-v1`，参数由 `EvidenceSufficiencyConfig` 集中管理并在创建时校验：`min_vector_similarity=0.82`、`max_candidate_rank=3`、`max_original_rank=5`、`minimum_anchor_count=2`、`minimum_anchor_coverage=0.60`、`minimum_phrase_characters=5`、`minimum_distinct_sources=1`、`numeric_context_characters=48`。规则版本当前固定为 `evidence-gate-v1`，未知版本及越界/非有限参数被拒绝。
- 向量相似度沿用第十五批语义：sqlite-vec 默认 L2 距离，输入和存储向量均单位归一化，因此 `cosine_distance=d_l2²/2`、`vector_similarity=1-cosine_distance`。只接受有限 `vector_distance∈[0,2]`、`vector_score∈[-1,1]`，并要求 `vector_score` 与 `1-vector_distance` 差不超过 `1e-5`；空值、异常或未知量纲不参与放行。
- 每个支持候选必须有 FTS 与 vector 原始 rank，二者均不晚于 5，融合后名次不晚于 3；正文需覆盖至少两个查询锚点且覆盖率不低于 0.60，或包含至少五个规范化字符的完整查询短语。查询中的编号必须在正文出现；数值问题还要求某个匹配锚点附近 48 个规范化字符内存在数值。文件名和 heading 不计正文覆盖；RRF/精确奖励/多样性分不作为证据门槛，不能单独绕过门控。
- 来源数按符合门槛候选的 distinct `file_id` 计算，默认至少 1；重复 Chunk 不会制造额外来源，单文件有效证据可以通过。简单本地问题分类将多子问/开放列举视为整体不足；两个以上支持来源出现不同数值或明确相反肯定/否定标记时整体拒绝。本批不做可回答子问题拆分；问题类型与冲突启发式有边界，规则无法确认时按不足处理。
- 结构化结果状态为 `supported`、`insufficient`、`unavailable`，包含规则版本、问题类型、原因码、候选的 Chunk/File/IndexVersion 身份及原始 rank/相似度/锚点等信号。`insufficient` 只带固定本地提示和补充/调整资料建议，不输出候选正文，不调用模型、不拼引用；`unavailable` 不带拒答提示，保留索引、范围或通道错误原因；`supported` 仅表示候选可进入后续服务端来源快照、引用绑定和生成流程，不代表事实蕴含或最终答案验证通过。
- 第十八批固定离线样本覆盖：精确问题与核心实体改写、无结果、相似但缺少所问数值、短词误命中、标题/编号假阳性、低/空/不一致余弦信号、奖励分不能绕过、重复位置切片、单文件证据、部分覆盖复合问题、数值和极性冲突、单路未请求/显式故障、跨范围版本及范围变化。8 个纯判定样本通过；另有真实 SQLite FTS5 + sqlite-vec 链路确认候选全在范围内、门控在 Top 8 后运行、无引用编号、版本仍 `BUILDING` 且活动版本为空。样本不包含私人文件，不等价于最终 Recall@10 或问答质量验收。
- 第十八批验证：后端串行 `133 passed`；`uv run ruff check src tests`、Pyright、`python -m compileall -q src tests migrations`、`git diff --check` 通过。测试曾有一次既有 Embedding Worker 互斥用例失败，单测重跑及后续全量重跑通过。额外 `ruff check .` 报 14 条未修改的既有 Alembic migration lint 问题；本批 `src`/`tests` lint 通过。没有 OpenAPI、前端、API 或迁移改动；没有 UI E2E、DeepSeek、真实凭据、付费服务或用户资料。阶段 5 仍为 `PARTIAL`。

## 索引完整性复核与原子激活阶段（第十九批）

- `IndexActivationWorker` 在应用生命周期内周期扫描仍处于 `BUILDING` 的版本。它不产生公开路由，也不引入新的 `BackgroundTask` 类型；已有预处理、Chunk、Embedding 和 FTS 任务的持久状态/检查点是准入证据，`IndexVersion.activation_error_code` 记录终结失败或过期原因。应用重启后扫描器从数据库重新发现候选并重复核验。
- 候选必须属于未删除知识库，并且是最新创建的 `IndexVersion`。尚有阶段未终结或同版本任务 `QUEUED/RUNNING` 时等待；最新阶段任务必须成功结束，版本阶段状态必须为 `COMPLETED/PARTIAL`。旧候选在自身任务链未终结时保持 `BUILDING`，但不能越过更新版本激活；任务链结束后转为 `SUPERSEDED`。同版本重试任务开始运行时扫描器继续等待；成功重试后再复核最新任务检查点。
- 输入集合以当前知识库 ACTIVE 成员与不可变 `IndexVersionInput` 快照逐项相等为准，并同时复算 `parse_revision_set_hash`。有效 PREPARED 来源还须保持文件 `PARSED`、未永久清理、内容哈希和解析修订匹配；临时回收站或解析处理中状态等待现有恢复/清理流程，不能激活旧正文。成员移出/重加、快照变化和更新候选使旧版本无法覆盖新范围。
- Chunk 检查只读取持久 Chunk，不重跑切片或 Embedding；校验 ChunkingConfig 和 EmbeddingConfig 的配置 ID、按实际字段重算 fingerprint 与最新任务 checkpoint。每个 `CHUNKED` 文件的有效 Chunk 数必须等于持久 `chunk_count`，Chunk 正文 UTF-8 SHA-256 必须等于 Chunk 行内容哈希。失败/跳过输入不进入可用范围。
- Embedding 检查使用固定有效的本地 ONNX 配置和 512 维；每个 `EMBEDDED` 输入要求逐 Chunk 的 `EmbeddingRecord.READY` 数与 `embedding_count` 一致，校验 EmbeddingConfig fingerprint、vector ID、Chunk ID 和业务行 vector hash。对应每版本 sqlite-vec 文件再检查配置/IndexVersion/引擎 identity、SQLite `quick_check`、元数据和向量行 rowid 一一对应、向量维度 512、有限值、单位范数、实际字节 SHA-256，以及已完成输入要求的向量记录集合。复核不重新推理，也不修改旧版本向量库。
- FTS 检查分别执行 FTS5 `integrity-check` 和版本范围 `consistency_check`；虚表每个 rowid 必须对应唯一 `fts_chunk_map` 行，映射字段、Chunk 正文、文件/解析修订/配置/hash 必须相符，并且整个版本映射集合精确等于各成功输入的 Chunk 集。空表存在、单向映射存在或单独计数相等都不能代替双向完整性复核。
- 文件策略：输入快照为零且没有 FTS/向量产物时版本以 `EMPTY` 结束，知识库回到 `EMPTY` 并清空活动指针；输入失败或跳过时逐项原因保留。至少一个文件的 Chunk、Embedding 和 FTS 都完整时允许候选以 `READY` 激活，知识库标记 `PARTIAL`，仅这些成员设置 `index_state=READY`；不存在完整可用文件时新候选为 `FAILED`。首次失败且无旧版时知识库=`FAILED`；有旧活动版时指针不变并继续由旧版提供当前范围内结果，知识库状态根据旧版当前有效范围恢复为 `READY/PARTIAL/NEEDS_REBUILD`。
- 激活事务边界：产物/文件复核全部在事务外做。提交时以知识库 `row_version` 和预期旧活动指针的条件 UPDATE 取得 SQLite 写锁，再于同一事务重新校验当前候选、最新版本、活动版本、成员/来源快照、配置及任务检查点。成功时原子设置新版本 `READY/activated_at`、旧版本 `RETIRED/retired_at`、`active_index_version_id`、知识库和成员状态；事务异常或 CAS 失败回滚，不会暴露空窗或新旧版本混读。物理回收不属于此批，旧版和历史引用所需产物保持。
- 恢复语义：事务外复核期间进程退出不修改版本；重启后从 `BUILDING` 重做核验。激活状态、旧版本退役状态与知识库指针在同一业务 SQLite 事务提交；重复扫描已由活动指针指向的 `READY` 版本直接幂等返回。
- 检索边界：应用层 Vector Top-K 和 Hybrid Query 只接受 `status=READY` 且等于知识库当前 `active_index_version_id` 的版本，并仅消费 `index_state=READY` 成员；FTS 应用查询同时限定活动版本和已完成 Embedding 输入。内部基础投影/固定用例不构成用户 API；本批没有公开检索、聊天或测试检索路由。
- 第十九批固定离线验证覆盖首次成功、构建期旧版可读/新 `BUILDING` 不可读、原子切换、旧版产物保留、缺 Chunk/向量/FTS/维度、任务未完成、更新成员/候选竞争、空库/空文本/部分失败、重复激活/重启恢复、并发重复激活与最终提交错误回滚。串行全量后端 `147 passed`；`ruff check src tests`、Pyright、compileall、Alembic head 和 `git diff --check` 通过。额外 `ruff check .` 仍报 14 条既有 Alembic lint；未改旧迁移。没有 DeepSeek/真实凭据/真实用户资料，也没有前端/API/E2E 变更。

## 同一知识库增量构建阶段（第二十批）

- `INDEX_PREPROCESS` 对活动版本和当前 ACTIVE 成员快照做差异计划。输入身份含成员 ID、`file_id`、内容 SHA-256、解析修订和 `membership_added_at`；逐项分类为 `NEW`、`CHANGED`、`UNCHANGED`、`PENDING`、`FAILED`，另统计从活动输入中移除的成员。预处理任务检查点保存 `FULL/INCREMENTAL`、基线版本、分类数量、逐文件复用来源及配置不兼容原因，供审计和重启恢复。没有活动 `READY` 版本按首次 `FULL` 构建处理。
- 文件级复用至少要求 `file_id + content_hash + parse_revision_id` 一致。ChunkingConfig 指纹涵盖配置版本、切片算法、Unicode 字符度量单位、目标/最小/最大长度、重叠长度和结构规则 hash。EmbeddingConfig 指纹涵盖 Provider、模型名与完整 revision、维度、归一化及距离度量。指纹必须能由当前实际配置字段重算；向量引擎不兼容、模型/维度/规范化/Chunk 配置差异或指纹不一致时明确选择 `FULL`，不复用旧向量。
- 新知识库可以复用其他知识库已完成且兼容的文件级缓存，但目标成员、加入时间、回收站、内容 hash 和解析修订仍由目标版本每一阶段重新验证。来源输入须有完整 Chunk、Embedding 和 FTS 检查点；共享文件不共享知识库范围映射。
- 兼容的未变文件复用既有 Chunk 集，不再读取解析正文或运行切片算法。EmbeddingWorker 复用 Chunk/EmbeddingConfig 唯一映射和持久向量，通过向量 ID、Chunk ID、向量 hash 读写目标 IndexVersion 专属向量空间；目标空间缺向量时复制已存在单位向量，不调用 ONNX。来源产物缺失或验证失败时清除复用标记并走正常 `INDEX_CHUNK → INDEX_EMBED → INDEX_FTS`。FTS Worker 复制来源版本对应文件的 FTS 字段和映射至新版本；候选仍必须通过第十九批 FTS5 integrity-check、映射集合、向量/EmbeddingRecord、Chunk 与任务链完整性复核后激活。
- 删除成员立即由当前知识库成员范围过滤从旧活动索引排除；新候选快照不含该成员。构建/校验期间旧活动指针与旧版本保持不变。移出一个成员不会删除源文件、被其他知识库引用的 Chunk/EmbeddingRecord、旧 IndexVersion 或旧 FTS/向量历史。候选切换仍复用第十九批唯一激活器和短事务 CAS。
- 相同知识库当前输入快照与配置的重复提交返回现有任务/候选，不创建竞争版本。已有快照任务发现输入或配置变化时，允许创建新任务/候选；较旧候选通过最新版本/输入哈希复核后标记 `SUPERSEDED`，失败使用原 `PARTIAL/FAILED` 语义，不自动无限重试。Worker 重启仍依靠任务检查点、逐文件输入状态和现有租约恢复。
- 第二十批无数据库迁移、公开检索/问答 API、OpenAPI、前端或 Provider 调用。离线回归覆盖增量新增、内容替换、移除成员即时过滤、跨知识库兼容缓存、Embedding 维度配置不兼容、重复任务、候选完整性审计及原子激活；ONNX 计数 Mock 证明未变文件不重复推理。后端串行 `153 passed`；Ruff、Pyright、compileall、Alembic head `e4a7810c9b62` 和 `git diff --check` 通过。`ruff check .` 仍有 14 条既有 Alembic migration lint。没有 10 万 Chunk 或最终 Recall@10 验收结论。

## 服务端来源快照阶段（第二十一批）

- 快照只由内部 `HybridAssessmentResult` 输入；要求 evidence gate 为 `supported`，且每个支持 signal 的 Chunk/File/IndexVersion 身份必须与同一 retrieval result 候选一致。客户端不能提交候选、文件名、摘录、路径、页码或任意 Chunk ID，没有 HTTP 路由。
- 新建快照使用独立 SQLite Session/事务，以知识库 no-op UPDATE 作为首条语句取得 SQLite 写锁；随后再读活动指针、知识库/IndexVersion 状态、成员及加入时间、文件回收站/状态/hash/解析修订、IndexVersionInput、Chunk、FTS 映射、EmbeddingRecord 和 EmbeddingConfig 指纹。任何激活、成员移除或 purge 写入只能在该事务前或后提交，不能跨过检查与插入之间。
- 新 Alembic revision `6b3e91a0c4d7` 的 `SourceSnapshot` 保持内部 `UNBOUND`，没有 `owner_type/owner_id`，不得创建 Chat/Learning owner、Citation 编号或模型消息。字段包括知识库/索引版本、可空文件/Chunk 关联、文件名、内容版本 hash/解析修订、heading path、页/幻灯片/行定位、最多 1200 Unicode 字符摘录、Chunk/摘录 SHA-256、幂等键和时间。相同知识库/IndexVersion/Chunk 只保存一次。
- 创建只信数据库重新加载的 Chunk 正文、FileRecord 显示名和真实定位；候选携带正文/标题若与数据库不一致就拒绝。软删除读取为 `SOURCE_IN_TRASH` 且 `can_open_source=false`，但保留历史摘录；文件版本变化为 `SOURCE_VERSION_STALE`；成员退出为 `SOURCE_OUT_OF_SCOPE`；活动索引重建为 `INDEX_VERSION_RETIRED`，旧快照仍指向原版本。读取返回 typed view，不含本地绝对路径。
- 文件永久删除 helper 与 `trg_source_snapshots_file_purge` SQLite BEFORE DELETE trigger 清空摘录、正文/文件版本 hash、解析修订及 File/Chunk 关系，同时保留文件名和定位说明；知识库永久删除清理无 owner 的 pending snapshots。文件永久删除后读取为 `SOURCE_DELETED`，不再提供正文。
- 本批无公开 Citation/检索 API、OpenAPI、前端、Provider 请求或 owner 模型。`tests/test_stage5_source_snapshots.py` 用离线 FTS5/sqlite-vec 搜索和证据门控验证合法快照，并覆盖重启、伪造输入、跨库/版本/成员/文件错误、写事务竞态、幂等、定位空值、索引重建历史和删除净化。最终串行后端 `164 passed`，Ruff、Pyright、compileall、`git diff --check` 通过，Alembic head 为 `6b3e91a0c4d7`；未完成 Citation owner、AC-KB-003、Recall@10 或质量性能验收。

## 本地测试检索 API 阶段（第二十三批）

- `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests` 只接受 JSON `question`，去除首尾空白后长度为 1–2000 字符；额外字段一律拒绝。客户端不能指定 `index_version_id`、文件集合、Embedding 模型或系统路径。路由沿用全局本地 Host、Origin、会话 Cookie 和 POST 幂等键校验。
- 服务端只读取路径知识库当前活动的 `READY` `IndexVersion`，并检查知识库未回收、索引范围/向量引擎、FTS/Embedding 状态和固定 `LOCAL_ONNX` Embedding 配置。无活动索引或无可用本地模型返回显式 `unavailable` 状态及稳定错误码；查询模型只校验已安装的固定 BGE ONNX 产物并使用 `allow_download=false`，此端点不下载模型。
- 双路行为复用既有 FTS5 Top 30、sqlite-vec Top 30、Chunk 去重、`rrf-exact-diversity-v1` Top 8 和 `evidence-gate-v1`。开始本地问题向量计算前捕获活动索引/成员/文件/Chunk/Embedding 范围指纹，计算和检索期间再次核对；索引或范围变化返回 `unavailable`/`RETRIEVAL_SCOPE_CHANGED`，不返回部分旧结果。FTS 或向量单路故障采用严格失败语义，并返回 `unavailable`、错误路由和原因码，不伪装成完整双路结果。
- 响应包含 `supported`/`insufficient`/`unavailable`、索引与算法/证据规则版本、候选 Chunk/File ID、文件名、数据库真实页/幻灯片/行/标题定位、最多 1200 字符摘录、FTS/vector 双路 rank/score 与融合解释；最多 8 个候选，完整 JSON 响应限制为 64 KiB。不得把调试候选转换为 Citation 编号或 `[1]`。
- 接口只读：不创建消息、Chat/Learning owner、来源快照、Citation、后台任务或回答，不调用 DeepSeek/Provider，也不把问题写入敏感日志。此本地测试端点不等同公开聊天检索、AC-KB-003、Recall@10 或质量/性能验收；前端检索测试页面仍待后续实现。
