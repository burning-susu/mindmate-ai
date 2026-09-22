# 阶段 4：文件管理收口审计报告

> 阶段：`4`
> 审计日期：`2026-09-22`
> 结论：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 第五批起点：`0448d5bd8cf81609d48da228b1c45166f648c9d5`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 本批次结论

第五批数据模型与契约收口结果为 `PASS`：Folder/Tag 乐观锁、解析失败持久字段、Alembic 迁移、OpenAPI、前端类型与冲突交互均已实现并通过自动化验证。第六批已完成持久解析 Worker、租约/恢复/重试和 Windows Job Object 资源安全收口；阶段 4 最终验收尚未执行，因此阶段和第六批结论均保持 `PARTIAL`。

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

## 已知缺口与阻塞

1. 文件列表状态（筛选、排序、滚动位置）在离开详情后尚未持久恢复。
2. “批量加入知识库”依赖阶段 5 的知识库管理闭环，本批次没有提前实现知识库、FTS5、Embedding、向量或 RAG。
3. 还未执行全部 `AC-FILE-*` 的正式发布级恶意文档集、资源耗尽和干净 Windows 安装包验收；留给第七批最终验收。

## 下一批次

第七批：阶段 4 最终验收与状态定版

## 范围声明

本批次没有实现或调用真实 DeepSeek、Embedding、FTS5、sqlite-vec 索引、RAG、AI 对话或学习陪练；没有新增数据库迁移，继续使用 `9f3a1c7e2b40`。解析依赖严格使用 `15_技术架构与开发约束.md` 已冻结的 `pypdf`、`python-docx` 和 `python-pptx`。
