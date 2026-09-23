# 阶段 5：知识库基础与成员准入测试报告

> 阶段：`5`
> 批次：`第八批 + 第九批 + 第十批`
> 验证日期：`2026-09-23`
> 第八批结论：`PASS`
> 第九批结论：`PASS`
> 第十批结论：`PASS`
> 阶段 5 状态：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 起始提交：`75a0653877b7f627bc254a859232689c19872777`
> 第九批起始提交：`6fd248978b84bcf96702eda081ed05469dab4bf2`
> 第十批起始提交：`3025a5abc2a89cca97edd9cadfbeb87bccdc985f`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 结论

第八批“空知识库创建、编辑、列表、详情、回收站与恢复”闭环通过；第九批“已导入文件批量加入/移出知识库、持久成员准入任务和前端真实状态”闭环通过；第十批“索引配置、迁移与可恢复输入预处理”闭环通过。空库保持 `EMPTY`；存在成员但未建立索引时为 `PREPARING`，成员保持 `index_state=PENDING`，可用文件数为 0。

第十批 `INDEX_PREPROCESS` 的 `COMPLETED` 只证明输入快照、配置指纹与逐项检查点已持久化，不表示索引就绪。`IndexVersion` 保持 `BUILDING`，`active_index_version_id` 保持空。阶段 5 仍为 `PARTIAL`：正式 Chunk、Embedding、FTS5、sqlite-vec、原子索引激活、混合检索、引用和 RAG 均未实现。

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
- 默认 Embedding 配置只预留本地 ONNX `BAAI/bge-small-zh-v1.5`、512 维、归一化与余弦距离元数据；revision 保持空，不伪造模型已下载或可推理。
- 独立 `INDEX_PREPROCESS` Worker 冻结活动成员、内容哈希、解析修订、成员加入时间、配置指纹与集合指纹；逐项结果为 `PREPARED/SKIPPED/FAILED`，支持租约过期接管、检查点续跑、取消和幂等。
- 成员移出/重加、文件回收站、内容哈希或解析修订变化会产生稳定原因码；完成前二次校验，旧任务不会激活关系或发布过期可构建输入。
- 本批未开放 `/rebuild` 或 `index-status`，没有 API schema 变化；知识库永久删除会先清理对应预处理快照，但不删除原始文件。

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

## 自动化证据

```text
backend> uv run pytest
50 passed

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

frontend> MINDMATE_API_PORT=8012 MINDMATE_WEB_PORT=5174 npx playwright test e2e/stage5-knowledge-bases.spec.ts --reporter=line
1 passed（隔离数据目录、真实 FastAPI + Vite 代理）

frontend> npx playwright test e2e/stage4-files.spec.ts --reporter=line
1 passed（阶段 4 核心回归）

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0；Generated 33 schemas and 50 operations

backend> 空库/已有数据 upgrade -> downgrade 9f3a1c7e2b40 -> upgrade head
backend> 第九批数据库 c7d5e8a1f204 -> upgrade head
最终 revision d91f4a6b2c30；已有文件、知识库、成员和任务保留；PRAGMA quick_check=ok

repo> git diff --check
通过
```

测试仅出现 Starlette/httpx 与 Alembic 配置的依赖弃用警告，无测试失败。没有调用 DeepSeek、上传用户资料或使用真实凭据。

## 未实现与下一批前置

- 已实现索引输入预处理 Worker，但未生成正式 Chunk、Embedding、FTS 或向量产物；任务完成不代表索引完成。
- 未实现正式 Chunk、ONNX Embedding、FTS5、sqlite-vec、RRF、测试检索和 RAG。
- 未宣称阶段 5 `PASS`，也未回填阶段 4 的发布候选遗留项。

下一批只建议一个最小闭环：消费本批 `PREPARED` 快照，生成并持久化版本化 Chunk，支持取消、恢复和失效校验；不同时实现 Embedding、FTS、向量或检索。
