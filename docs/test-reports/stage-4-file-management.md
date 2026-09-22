# 阶段 4：文件管理收口审计报告

> 阶段：`4`
> 审计日期：`2026-09-22`
> 结论：`PARTIAL`
> 分支：`feat/v1-bootstrap`
> 审计起点：`9e0174a`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 本批次结论

阶段 4 的文件管理垂直切片可以运行，关键安全与生命周期路径已补齐并形成自动化证据；但仍存在需要数据库迁移或任务架构变更的明确缺口，因此不得标记为完整验收通过。

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

## 自动化证据

```text
backend\.venv\Scripts\pytest.exe -q
19 passed

backend\.venv\Scripts\pytest.exe -q tests\test_stage4_files.py
10 passed

backend\.venv\Scripts\ruff.exe check src tests
All checks passed

backend\.venv\Scripts\pyright.exe src tests
0 errors, 0 warnings, 0 informations

frontend\> npm run lint
通过（ESLint + oxlint）

frontend\> npm run typecheck
通过（tsc -b）

frontend\> npm run test -- --run
3 test files, 4 tests passed

frontend\> npm run build
Vite production build succeeded

backend\.venv\Scripts\python.exe scripts/export_openapi.py
OpenAPI 3.1.0 exported

frontend\> node scripts/generate-api-types.mjs
Generated 13 schemas and 37 operations

alembic upgrade head -> downgrade base -> upgrade head
最终 revision bc554b1b4366；PRAGMA quick_check = ok

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

## 已知缺口与阻塞

1. `Folder` 和 `Tag` 数据表没有真实 `row_version`；文件夹接口当前只能兼容返回 `1`。修复需要数据库结构迁移和契约更新，必须进入已确认的变更链。
2. 文件解析失败原因只存在导入任务结果，`FileRecord` 没有持久错误阶段/错误 ID/重试计数字段。修复需要数据模型迁移。
3. 解析已在隔离子进程执行并有限时、页数和输出上限，但尚未通过 Windows Job Object 对子进程施加硬内存上限。
4. 导入和解析仍在请求生命周期内执行；持久任务记录存在，但尚未由可恢复 Worker 异步领取解析工作。该项属于阶段 4 任务架构收口，不得用文档将同步实现伪装成后台完成。
5. 文件列表状态（筛选、排序、滚动位置）在离开详情后尚未持久恢复。
6. “批量加入知识库”依赖阶段 5 的知识库管理闭环，本批次没有提前实现知识库、FTS5、Embedding、向量或 RAG。
7. 还未执行全部 `AC-FILE-*` 的正式发布级恶意文档集、资源耗尽和干净 Windows 安装包验收。

## 范围声明

本批次没有实现或调用真实 DeepSeek、Embedding、FTS5、sqlite-vec 索引、RAG、AI 对话或学习陪练。新增解析依赖严格使用 `15_技术架构与开发约束.md` 已冻结的 `pypdf`、`python-docx` 和 `python-pptx`。
