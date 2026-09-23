# 阶段 5：知识库基础闭环测试报告

> 阶段：`5`
> 批次：`第八批`
> 验证日期：`2026-09-23`
> 第八批结论：`PASS`
> 阶段 5 状态：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 起始提交：`75a0653877b7f627bc254a859232689c19872777`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 结论

第八批“空知识库创建、编辑、列表、详情、回收站与恢复”本地持久化闭环通过。知识库创建后保持 `EMPTY`，文件数与可用文件数为 0；本批没有伪造 `READY`、索引任务或检索结果。

阶段 5 仍为 `PARTIAL`：成员关系管理、批量添加、持久索引任务、Chunk、Embedding、FTS5 知识库索引、sqlite-vec、混合检索、引用和 RAG 均未在本批实现。

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
- “添加文件与持久索引任务”明确显示为下一批开放，不提供假文件选择器、假 `202` 或假成功状态。
- OpenAPI 3.1 与前端生成类型同步为 `29 schemas / 46 operations`。

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

## 自动化证据

```text
backend> .\.venv\Scripts\python.exe -m pytest -q
38 passed

backend> .\.venv\Scripts\python.exe -m pytest tests\test_stage5_knowledge_bases.py tests\test_stage4_migration.py -q
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

frontend> npm test -- --run
5 files, 12 tests passed

frontend> npm run build
Vite production build succeeded

frontend> npx playwright test e2e/stage5-knowledge-bases.spec.ts --reporter=line
1 passed（真实 FastAPI + Vite 代理）

frontend> npx playwright test e2e/stage4-files.spec.ts --reporter=line
1 passed（阶段 4 核心回归）

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0；Generated 29 schemas and 46 operations

backend> 空库/已有数据 upgrade -> downgrade 9f3a1c7e2b40 -> upgrade head
最终 revision c7d5e8a1f204；已有知识库数据保留；PRAGMA quick_check=ok

repo> git diff --check
通过
```

测试仅出现 Starlette/httpx 与 Alembic 配置的依赖弃用警告，无测试失败。没有调用 DeepSeek、上传用户资料或使用真实凭据。

## 未实现与下一批前置

- 未实现文件加入/移出知识库及批量成员变更。
- 未实现父任务/子任务、持久索引 Worker、失败文件重试和任务进度。
- 未实现 ChunkingConfig、EmbeddingConfig、IndexVersion、ONNX Embedding、FTS5、sqlite-vec、RRF、测试检索和 RAG。
- 未宣称阶段 5 `PASS`，也未回填阶段 4 的发布候选遗留项。

下一批只建议一个最小闭环：成员关系、批量添加与持久索引任务的入口。开始前需根据本批实际 API 和冻结需求再次核对任务语义。
