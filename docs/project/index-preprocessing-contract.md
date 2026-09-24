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
