# 索引预处理输入契约

## 目的

`INDEX_PREPROCESS` 是阶段 5 的内部持久任务。它只冻结知识库输入、配置和逐文件检查结果，为后续 Chunk、Embedding、FTS5 与 sqlite-vec 构建提供入口；任务完成不表示索引已建成或可检索。

## 配置语义

- `ChunkingConfig.measurement_unit=UNICODE_CHARACTER`，默认目标约 500 个字符、重叠约 80 个字符。通用 `target_size` 等字段不得解释为旧需求中的 token 数。
- `EmbeddingConfig` 预留本地 ONNX `BAAI/bge-small-zh-v1.5`、512 维、归一化与余弦距离元数据。`model_revision=NULL` 表示本批没有下载或验证模型，不得视为可推理。
- 两类配置都以规范 JSON 的 SHA-256 指纹去重；配置中不保存 API Key 或凭据引用。

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
