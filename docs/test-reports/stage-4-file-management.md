# 阶段 4：文件管理收口审计报告

> 阶段：`4`
> 审计日期：`2026-09-23`
> 第七批结论：`PASS`
> 阶段 4 最终状态：`PASS`
> 分支：`feat/v1-bootstrap`
> 第五批起点：`0448d5bd8cf81609d48da228b1c45166f648c9d5`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 本批次结论

第五批数据模型与契约收口结果为 `PASS`，第六批持久解析 Worker、租约/恢复/重试和 Windows Job Object 资源安全收口结果为 `PASS`。第七批补齐列表状态恢复和返回前列表刷新，完成阶段 4 逐项追踪及最终门禁复核；阶段 4 必须项均有可重复证据，最终状态定版为 `PASS`。

## 第六批增量收口

- 导入和重新处理在文件记录与任务提交后立即返回，不再在 HTTP 请求内等待 PDF、DOCX、PPTX、TXT 或 Markdown 的完整解析。
- 复用现有 `BackgroundTask`，任务类型为 `FILE_IMPORT` / `FILE_REPROCESS`；任务状态使用 `QUEUED`、`RUNNING`、`INTERRUPTED`、`COMPLETED`、`FAILED`、`CANCELLED`，重复文件的导入决策继续使用 `BLOCKED`。
- `claim_task` 使用带状态和租约条件的单条原子 `UPDATE`；默认租约 60 秒，过期运行任务可恢复，Worker 退出时停止接单并中断自有运行任务。
- 同一文件存在 `BLOCKED/QUEUED/RUNNING/INTERRUPTED` 解析任务时不会重复排队；成功任务不会重新执行。结果发布前后校验文件未删除、内容对象仍为 `READY` 且 SHA-256 未变化，旧任务结果不会覆盖新状态。
- 默认最多 2 次解析重试；`PARSER_TIMEOUT`、`PARSER_FAILED`、`PARSER_OUTPUT_INVALID`、`PARSER_RESOURCE_LIMIT` 可有限重试，格式/编码等确定性错误不重试；`parse_retry_count` 只累计真实重试，成功后保留累计次数并清除失败字段。
- Windows 解析子进程使用 Job Object，设置 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` 和进程内存硬限制，默认 `512 MiB`；Handle 确定性关闭，创建/配置/分配失败映射为稳定 `PARSER_RESOURCE_LIMIT`。非 Windows 路径明确标记为兼容实现，不宣称硬限制。
- 新增 `GET /api/v1/tasks/{task_id}`；OpenAPI 3.1 和前端生成类型同步为 `25 schemas / 38 operations`，文件列表/详情对 `QUEUED/PARSING` 状态轮询。

## 已实现并验证

- 单文件和最多 20 文件的 multipart 导入；单文件 50 MB、单批 500 MB 边界；逐项失败不回滚合格文件。
- 扩展名、MIME、文件签名、Office 包结构和压缩包展开上限校验；文件名清理；受控 UUID 存储路径。
- SHA-256 精确重复识别；复用、独立逻辑记录和跳过；共享内容对象最后引用删除后才清理字节。
- TXT/Markdown 本地解析；PDF、DOCX、PPTX 在 `-I` 隔离 Python 子进程中解析，限制超时、页数、压缩包和输出大小，不访问文档外链。
- 空白/扫描 PDF 不伪装为解析成功，明确标记 `PARSE_FAILED` 和 OCR 不支持原因。
- 文件列表、名称/标签/解析正文搜索、文件夹/标签/类型/状态/知识库/导入时间筛选、排序和游标分页。
- 文件重命名/移动、标签绑定/解绑、批量移动/标签/重新处理/删除。
- 文件夹树、防自引用/子目录循环/损坏循环、最大 5 层、同级名称冲突，以及两种文件夹删除策略。
- 文件和多层文件夹递归软删除、整体恢复、永久删除；永久删除后详情返回 404；托管字节和解析文本同步清理。
- `..`、绝对路径、符号链接/重解析点和硬链接逃逸防护；受控内容读取设置 `nosniff`。当前环境对硬链接完成实测，符号链接分支在系统允许创建测试链接时执行。
- 前端 `/files`、`/files/:id`、`/trash` 使用真实 `/api/v1`；JSON 写请求设置 `Content-Type: application/json`，multipart 不手写 boundary。
- 文件工作台包含嵌套目录、筛选、排序、标签创建、批量操作、加载/错误/空状态；详情支持名称、文件夹和标签编辑；回收站支持文件及文件夹恢复/永久删除。
- Folder/Tag 使用真实数据库 `row_version`；修改、移动、删除、恢复通过单条带版本条件的 SQL 原子更新，版本冲突返回统一 `412 RESOURCE_VERSION_CONFLICT`，不存在记录返回 `404`。
- FileRecord 持久化 `parse_failure_stage`、`parse_error_id` 和 `parse_retry_count`；解析失败信息脱敏，成功重试清除失败状态但保留累计次数。
- 前端保存并传递 Folder/Tag 版本；成功后使用后端最新版本；收到 `412` 时提示重新加载且不自动覆盖。

## 第七批需求追踪与最终结论

阶段 4 必须验收项共 `19` 项，已通过 `19` 项，未通过 `0` 项。下表把需求/验收项、实现位置和可重复证据绑定在一起；发布候选门禁不计入阶段 4 未通过项，单独列于本报告末尾。

| ID | 验收项 | 实现位置 | 测试证据 | 结论 |
| --- | --- | --- | --- | --- |
| S4-01 | 五类格式导入、托管复制、异步任务 | `backend/src/mindmate/api/files.py`、`application/parser_worker.py` | `test_stage4_files.py`、后端 30 tests、Playwright | PASS |
| S4-02 | 50 MB/20 个/500 MB 限制与部分成功 | `backend/src/mindmate/api/files.py` | `test_stage4_files.py` 边界场景 | PASS |
| S4-03 | SHA-256 去重、三种决策与幂等 | `backend/src/mindmate/api/files.py` | `test_stage4_files.py` 重复/幂等场景 | PASS |
| S4-04 | 文件夹、标签、目录树和树约束 | `backend/src/mindmate/api/files.py`、`frontend/src/pages/FilesPage.tsx` | `test_stage4_files.py`、组件测试 | PASS |
| S4-05 | 搜索、筛选、排序、游标分页 | `backend/src/mindmate/api/files.py`、`FilesPage.tsx` | `test_stage4_files.py`、组件测试 | PASS |
| S4-06 | 详情返回保留筛选/排序/滚动状态 | `frontend/src/pages/FilesPage.tsx`、`FileDetailPage.tsx` | `stage4-files.test.tsx` 状态恢复回归 | PASS |
| S4-07 | 批量移动、标签、重新处理和删除 | `backend/src/mindmate/api/files.py`、`FilesPage.tsx` | `test_stage4_files.py` | PASS |
| S4-08 | 文件详情、解析文本预览和受控内容读取 | `FileDetailPage.tsx`、`backend/src/mindmate/api/files.py` | `test_stage4_files.py`、Playwright | PASS |
| S4-09 | 解析 Adapter、隔离子进程和限制 | `backend/src/mindmate/application/parser_worker.py`、`resource_limits.py` | `test_stage4_files.py`、Worker 专项 | PASS |
| S4-10 | 失败阶段、稳定错误 ID、重试次数 | `FileRecord`、`parser_worker.py`、`FileDetailPage.tsx` | `test_stage4_files.py`、组件测试 | PASS |
| S4-11 | 文件软删除、恢复和永久删除 | `backend/src/mindmate/api/files.py`、`TrashPage.tsx` | 文件生命周期测试、Playwright | PASS |
| S4-12 | 文件夹递归删除、恢复和永久删除 | `backend/src/mindmate/api/files.py` | `test_stage4_files.py` | PASS |
| S4-13 | `row_version`/412 乐观并发控制 | `backend/src/mindmate/api/files.py`、`files.ts` | `test_stage4_files.py`、组件冲突测试 | PASS |
| S4-14 | 持久任务、租约、重试、取消和重启恢复 | `application/tasks.py`、`parse_worker_service.py` | `test_stage6_parser_worker.py` | PASS |
| S4-15 | Windows Job Object、资源映射和确定性清理 | `backend/src/mindmate/application/resource_limits.py` | Worker/Job Object 专项冒烟 | PASS（受控边界） |
| S4-16 | 路径安全、外链不访问、日志脱敏、Mock Provider | `backend/src/mindmate/security`、解析器和配置 | 安全场景、Worker 错误脱敏测试 | PASS（受控边界） |
| S4-17 | OpenAPI 3.1 与前端生成类型无漂移 | `docs/openapi/openapi.json`、`frontend/src/api/generated/openapi.ts` | `generate-api.ps1`、25 schemas/38 operations | PASS |
| S4-18 | 空库/已有数据迁移往返与 SQLite 完整性 | `backend/migrations/versions/9f3a1c7e2b40*` | `test_stage4_migration.py`、`PRAGMA quick_check=ok` | PASS |
| S4-19 | 文件生命周期浏览器 E2E | `frontend/e2e/stage4-files.spec.ts` | Playwright `1 passed`（真实后端） | PASS |

阶段 4 不包含知识库 CRUD、FTS5、Embedding、向量索引或 RAG；“批量加入知识库”按 `16_Codex开发任务书.md` 的阶段 5 边界保留，不计入阶段 4 未通过项。

## 第五批基线自动化证据

```text
backend\> uv run pytest
23 passed

backend\> uv run pytest tests/test_stage4_files.py tests/test_stage4_migration.py -q
14 passed

backend\> uv run ruff check src tests
All checks passed

backend\> uv run pyright
0 errors, 0 warnings, 0 informations

backend\> uv run python -m compileall -q src
通过

frontend\> npm run lint
通过（ESLint + oxlint）

frontend\> npm run typecheck
通过（tsc -b）

frontend\> npm run test
4 test files, 7 tests passed

frontend\> npm run build
Vite production build succeeded

repo\> .\scripts\generate-api.ps1
OpenAPI 3.1.0 exported
Generated 25 schemas and 37 operations

空库 -> alembic upgrade head -> downgrade bc554b1b4366 -> upgrade head
已有数据 bc554b1b4366 -> 创建 Folder/Tag/FileRecord -> upgrade head -> downgrade -> upgrade
最终 revision 9f3a1c7e2b40；示例数据保留；新增默认值有效；PRAGMA quick_check = ok

repo\> git diff --check
通过

frontend\> npm run test:e2e -- --grep "stage 4 file lifecycle"
1 passed
```

## 第六批自动化证据

```text
backend> uv run pytest
30 passed

backend> uv run pytest tests/test_stage4_files.py tests/test_stage4_migration.py tests/test_stage6_parser_worker.py -q
21 passed

backend> uv run ruff check src tests
All checks passed

backend> uv run pyright
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src
通过

frontend> npm run lint
通过（ESLint + oxlint）

frontend> npm run typecheck
通过（tsc -b）

frontend> npm run test
4 test files, 7 tests passed

frontend> npm run build
Vite production build succeeded

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0 exported
Generated 25 schemas and 38 operations

backend> 空库/已有数据 Alembic upgrade、downgrade、再 upgrade + PRAGMA quick_check
通过；最终 revision 9f3a1c7e2b40，quick_check=ok

repo> git diff --check
通过
```

## 第七批最终验证证据

```text
backend> uv run pytest
30 passed（30 warnings，均为依赖弃用提示）

backend> uv run pytest tests/test_stage4_files.py tests/test_stage4_migration.py tests/test_stage6_parser_worker.py --disable-warnings -ra
21 passed, 24 warnings

backend> uv run ruff check src tests
All checks passed!

backend> uv run pyright
0 errors, 0 warnings, 0 informations

backend> uv run python -m compileall -q src
通过

frontend> npm run lint
通过（ESLint + oxlint）

frontend> npm run typecheck
通过（tsc -b）

frontend> npm run test
4 test files, 8 tests passed

frontend> npm run build
Vite production build succeeded

repo> .\scripts\generate-api.ps1
OpenAPI 3.1.0 exported；Generated 25 schemas and 38 operations

backend> 空库/已有数据 Alembic upgrade、downgrade、再 upgrade + PRAGMA quick_check
通过；最终 revision 9f3a1c7e2b40，quick_check=ok

frontend> npm run test:e2e -- --grep "stage 4 file lifecycle"
1 passed（真实 FastAPI 后端 + Vite 代理）

repo> git diff --check
通过
```

本批次新增的列表状态回归覆盖查询参数（搜索、排序）、详情返回和滚动位置；详情返回前刷新 `files` 查询，避免解析 Worker 更新 `row_version` 后使用旧缓存触发误报 412。OpenAPI 导出后重新生成前端类型，工作区未产生契约漂移。

Windows 当前运行平台为 Windows。Job Object 专项冒烟已实际创建 Job、设置 512 MiB 进程限制、分配受控子进程、终止并关闭 Handle；未通过真实大规模内存耗尽验证。Worker 专项测试覆盖请求提前返回、原子领取、租约恢复、健康检查不阻塞、有限重试、不可重试错误、删除/版本幂等和 Job Object 失败映射。

## 安全测试覆盖

- 伪装扩展名、冲突 MIME、不可读文本、损坏 Office 包。
- 单文件大小、21 文件、模拟批次总量边界和部分成功。
- 内容重复、独立记录和托管对象复用。
- 路径穿越、绝对路径、硬链接；符号链接/重解析点具备代码防护，测试在当前 Windows 允许创建链接时执行。
- 非法父目录、自引用、移动到子目录、数据库损坏循环。
- 多层目录递归删除/恢复/永久删除和永久删除后 404。
- 受控内容读取、JSON 请求头、multipart boundary。
- 浏览器真实目录创建、TXT 上传、详情预览、回收站和恢复。
- Folder/Tag 初始版本、更新递增、旧版本 `412`、最新数据不被覆盖、删除/恢复锁、`404/412` 区分。
- 解析失败阶段、稳定错误 ID、重试次数持久化；响应不包含本地路径或堆栈；成功重试清除失败字段。
- 空库和带现有 Folder/Tag/FileRecord 数据的上一 revision 升级、降级、再升级和 quick check。
- Worker 退出/恢复、活跃任务去重、旧任务结果不回写、解析错误脱敏、非 Windows 兼容能力和 Windows Job Object 资源释放。

## 发布候选阶段保留项

以下 `3` 项不是阶段 4 当前实现阻塞，而是依据需求基线应在发布候选流程执行的门禁：

1. **正式恶意文档集**：阶段 4 已通过伪装扩展、损坏 Office、外链、路径边界等受控场景；正式恶意样本集尚未导入，依据 `12_非功能与安全要求.md` 的 `NFR-ACC-008` 和威胁模型，在发布候选阶段执行。
2. **资源耗尽**：已通过超时、输出/压缩包上限、Job Object 创建/配置/进程内存上限/关闭清理和 `PARSER_RESOURCE_LIMIT` 映射验证；未进行可能拖垮开发机的真实大规模内存耗尽，依据 `15_技术架构与开发约束.md` 的发布流程在受控 Windows 发布环境执行。
3. **干净 Windows 安装包**：阶段 1 的 Spike 和开发态服务已验证；PyInstaller one-folder、Inno Setup、干净 Windows 11 安装/升级/卸载及 SHA-256 尚未执行，依据 `15_技术架构与开发约束.md` 第 24/25 节和 `12_非功能与安全要求.md` 的 `NFR-ACC-001`，归入发布候选门禁。

这些保留项不改变阶段 4 `PASS`，但在完整 V1 发布前必须关闭；`NFR-ACC-012` 仍需以发布候选证据为准。

## 下一阶段

阶段 4 已 `PASS`，可以新建对话进入阶段 5；本批次不启动阶段 5。

## 范围声明

本批次没有实现或调用真实 DeepSeek、Embedding、FTS5、sqlite-vec 索引、RAG、AI 对话或学习陪练；没有新增数据库迁移，继续使用 `9f3a1c7e2b40`。解析依赖严格使用 `15_技术架构与开发约束.md` 已冻结的 `pypdf`、`python-docx` 和 `python-pptx`。
