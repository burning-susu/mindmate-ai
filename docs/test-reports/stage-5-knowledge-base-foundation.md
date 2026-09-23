# 阶段 5：知识库基础与成员准入测试报告

> 阶段：`5`
> 批次：`第八批 + 第九批`
> 验证日期：`2026-09-23`
> 第八批结论：`PASS`
> 第九批结论：`PASS`
> 阶段 5 状态：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 起始提交：`75a0653877b7f627bc254a859232689c19872777`
> 第九批起始提交：`6fd248978b84bcf96702eda081ed05469dab4bf2`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 结论

第八批“空知识库创建、编辑、列表、详情、回收站与恢复”闭环通过；第九批“已导入文件批量加入/移出知识库、持久成员准入任务和前端真实状态”闭环通过。空库保持 `EMPTY`；存在成员但未建立索引时为 `PREPARING`，成员保持 `index_state=PENDING`，可用文件数为 0。

第九批父任务的 `COMPLETED` 只证明成员准入、关系持久化和逐项结果已完成，不表示索引就绪。阶段 5 仍为 `PARTIAL`：Chunk、Embedding、FTS5、sqlite-vec、原子索引激活、混合检索、引用和 RAG 均未实现。

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
- 本批没有数据库结构变化，继续使用 Alembic revision `c7d5e8a1f204`；OpenAPI 3.1 与前端生成类型同步为 `33 schemas / 50 operations`。

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

## 自动化证据

```text
backend> uv run pytest
42 passed

backend> uv run pytest tests/test_stage5_knowledge_bases.py
11 passed

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
最终 revision c7d5e8a1f204；已有知识库数据保留；PRAGMA quick_check=ok

repo> git diff --check
通过
```

测试仅出现 Starlette/httpx 与 Alembic 配置的依赖弃用警告，无测试失败。没有调用 DeepSeek、上传用户资料或使用真实凭据。

## 未实现与下一批前置

- 已实现成员准入父任务，但未实现真正的索引构建 Worker；任务完成不代表索引完成。
- 未实现 ChunkingConfig、EmbeddingConfig、IndexVersion、ONNX Embedding、FTS5、sqlite-vec、RRF、测试检索和 RAG。
- 未宣称阶段 5 `PASS`，也未回填阶段 4 的发布候选遗留项。

下一批只建议一个最小闭环：ChunkingConfig/EmbeddingConfig/IndexVersion 与可恢复索引构建任务骨架。开始前需根据本批 `PENDING` 成员与任务检查点再次核对索引版本语义。
