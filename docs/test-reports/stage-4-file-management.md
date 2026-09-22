# 阶段 4：文件管理收口审计报告

> 阶段：`4`
> 审计日期：`2026-09-22`
> 结论：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 第五批起点：`0448d5bd8cf81609d48da228b1c45166f648c9d5`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 本批次结论

第五批数据模型与契约收口结果为 `PASS`：Folder/Tag 乐观锁、解析失败持久字段、Alembic 迁移、OpenAPI、前端类型与冲突交互均已实现并通过自动化验证。阶段 4 因持久解析 Worker、Windows Job Object 和最终验收尚未完成，继续保持 `PARTIAL`。

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

## 自动化证据

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

## 已知缺口与阻塞

1. 解析已在隔离子进程执行并有限时、页数和输出上限，但尚未通过 Windows Job Object 对子进程施加硬内存上限。
2. 导入和解析仍在请求生命周期内执行；持久任务记录存在，但尚未由可恢复 Worker 异步领取解析工作。该项留给第六批，不得用文档将同步实现伪装成后台完成。
3. 文件列表状态（筛选、排序、滚动位置）在离开详情后尚未持久恢复。
4. “批量加入知识库”依赖阶段 5 的知识库管理闭环，本批次没有提前实现知识库、FTS5、Embedding、向量或 RAG。
5. 还未执行全部 `AC-FILE-*` 的正式发布级恶意文档集、资源耗尽和干净 Windows 安装包验收；留给第七批最终验收。

## 下一批次

第六批：阶段 4 持久解析 Worker 与资源安全收口

## 范围声明

本批次没有实现或调用真实 DeepSeek、Embedding、FTS5、sqlite-vec 索引、RAG、AI 对话或学习陪练。新增解析依赖严格使用 `15_技术架构与开发约束.md` 已冻结的 `pypdf`、`python-docx` 和 `python-pptx`。
