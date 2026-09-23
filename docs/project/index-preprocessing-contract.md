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
