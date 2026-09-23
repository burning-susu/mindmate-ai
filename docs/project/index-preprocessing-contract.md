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
