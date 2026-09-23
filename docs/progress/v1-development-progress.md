# V1 开发进度

## 阶段 0

- 状态：`COMPLETED`
- 基线提交：`bdf40c2 docs: establish v1 development baseline`
- 阶段提交：`114345c chore: establish reproducible development baseline`
- 已完成：需求/归档切换、React/Vite 工作区、FastAPI health/ready/version、npm/uv lock、PowerShell 脚本、CI、基础测试与质量配置。
- 验收证据：前端 lint/typecheck/test/build 通过；后端 pytest（2 passed）、Ruff、Pyright、OpenAPI 3.1 检查通过；health/ready 实际返回 `ok/ready`；浏览器验证首页和 `/chat` 路由渲染。

## 阶段 1

- 状态：`COMPLETED_WITH_RELEASE_GAPS`
- 阶段提交：`741ba6c chore: validate windows ai and vector runtime`
- 必须验证：sqlite-vec、ONNX、Credential Manager、随机回环端口、Mock SSE、PyInstaller 和干净 Windows 启动。
- 当前结果：前 7 项通过；干净 Windows 环境和正式 Inno Setup 尚未执行，详见 `docs/test-reports/stage-1-spike.md`。

## 阶段 2

- 状态：`COMPLETED`
- 阶段提交：`0b19795 feat: build secure local application shell`
- 已完成：本地数据目录、单实例锁、SQLite PRAGMA/Alembic、随机 HttpOnly 会话、Host/Origin 校验、Problem JSON、request ID、幂等头、系统端点、OpenAPI 导出、前端 API 客户端和路由应用壳。
- 验收证据：后端 7 tests、Ruff、Pyright；前端 lint/typecheck/test/build；浏览器验证首页和 `/chat` 路由；本地 Session/health/Problem JSON 联调通过。

## 阶段 3

- 状态：`COMPLETED`
- 阶段提交：`02a32b8 feat: add persistent data task and recovery foundation`
- 已完成：核心数据模型、Alembic 0002、BackgroundTask lease/checkpoint/恢复、备份 manifest/hash/敏感目录排除。
- 验收证据：迁移往返通过；后端 9 tests、Ruff、Pyright 通过；详见 `docs/test-reports/stage-3-data-task-backup.md`。
- 入口：SQLite 业务实体、持久 BackgroundTask、恢复检查点和备份 manifest。

## 阶段 4

- 状态：`PASS`
- 阶段提交：`bc30e1f feat: implement secure local file management`
- 收口审计起点：`9e0174a docs: record stage 4 file management evidence`
- 收口修复提交：`3b29d22 fix: close stage 4 file management gaps`
- 第四批交接提交：`0448d5b docs: establish stage 4 handoff baseline`
- 第五批：新增 Alembic revision `9f3a1c7e2b40`；Folder/Tag 持久 `row_version`；重命名、移动、删除、恢复和 Tag 修改/删除的原子乐观锁；FileRecord 解析失败阶段、稳定错误 ID、重试次数；OpenAPI 与前端生成类型和冲突交互同步。
- 第六批：复用 `BackgroundTask` 实现持久文件解析 Worker；导入/重新处理请求提交后立即返回排队状态；任务领取使用原子条件更新和租约，支持过期恢复、应用关闭中断、同文件活跃任务去重和有限重试；解析结果发布前校验文件存在、内容哈希和任务状态；Windows 解析子进程接入 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存硬上限，默认 `512 MiB`；新增 `GET /api/v1/tasks/{task_id}`，OpenAPI 3.1 同步为 `25 schemas / 38 operations`。
- 第七批：完成文件列表搜索/筛选/排序状态 URL 化，详情返回保留原查询串和滚动位置；返回前刷新列表查询，避免解析 Worker 更新 `row_version` 后旧缓存触发误报冲突；新增组件回归和稳定化的浏览器生命周期等待。
- 已完成：文件夹、标签、文件 CRUD；multipart 导入校验；流式 staging；SHA-256 去重；同内容复用/独立记录；TXT/Markdown 解析；PDF/DOCX/PPTX 隔离子进程解析；正文搜索；受控内容读取；递归回收站恢复/永久删除；嵌套目录、筛选、批量操作、详情编辑和文件夹回收站前端；详情返回状态恢复。
- 验收证据：后端 `30 passed`（阶段 4/迁移/Worker 定向 `21 passed`）、Ruff、Pyright、Python compileall；前端 lint/typecheck、Vitest `8 passed`、build；OpenAPI 3.1 `25 schemas / 38 operations` 与前端类型同步；空库和已有数据迁移往返、SQLite quick check 通过；真实 FastAPI 后端 + Vite 代理的阶段 4 Playwright `1 passed`；Windows Job Object 创建、配置、进程分配和清理受控冒烟通过。详见 `docs/test-reports/stage-4-file-management.md`。
- 阶段 4 最终追踪：`19/19` 必须项通过，`0` 项未通过；正式恶意文档集、资源耗尽和干净 Windows 安装包列为发布候选保留项，不回填为阶段 4 缺陷。
- 下一批次：阶段 5：知识库、Embedding 与 RAG；本批次不启动。
- 后续边界：FTS5、知识库索引、Embedding、向量与 RAG 仍属于阶段 5–6，本批次未提前实现。

## 阶段 5

- 状态：`PARTIAL`
- 第八批起点：`75a0653877b7f627bc254a859232689c19872777`
- 第九批起点：`6fd248978b84bcf96702eda081ed05469dab4bf2`
- 第十批起点：`3025a5abc2a89cca97edd9cadfbeb87bccdc985f`
- 已完成：空知识库创建、正常列表、详情、编辑和回收站；已导入文件批量加入/移出、多库共享、幂等重复提交、移出重加、逐项失败隔离与文件所属知识库查询。
- 数据与并发：Alembic revision `c7d5e8a1f204` 增加 `icon`/`color`；编辑、删除和恢复使用原子 `row_version` 条件更新，冲突返回 412。
- 任务：独立成员准入 Worker 复用 SQLite `BackgroundTask`、原子领取、租约、检查点、取消和关闭恢复；解析 Worker 与成员 Worker 按任务类型隔离。父任务完成只表示成员关系已持久化，不表示索引完成。
- 第十批数据：Alembic revision `d91f4a6b2c30` 增加版本化 ChunkingConfig、EmbeddingConfig、IndexVersion 和 IndexVersionInput；切片默认参数明确采用约 500/80 Unicode 字符，配置和解析集合均保存稳定 SHA-256 指纹。
- 第十批任务：新增独立 `INDEX_PREPROCESS` Worker，在请求外冻结一致输入快照并逐文件记录准备、跳过和失败；支持幂等、租约接管、检查点续跑、取消及成员/解析修订变化复核。预处理完成后仍为 `BUILDING`，不激活索引。
- 第十一批数据：Alembic revision `f2c7a1d8e904` 增加文件级版本化 `Chunk`，以文件、解析修订和切片配置形成唯一版本；保存标题路径、可用页/幻灯片/行定位、正文哈希和 Unicode 字符长度，真实 tokenizer 计数保持 NULL。Chunk 不与知识库绑定，满足版本条件时由多个知识库复用。
- 第十一批切片：新增结构优先字符切片器，目标约 500 字符、重叠约 80 字符；保护标题、段落、代码/表格、页和幻灯片边界，长结构块在自然边界拆分；DOCX v2 解析元数据标记真实可读出的标题、列表、段落、代码样式及表格行。
- 第十一批任务：新增独立 `INDEX_CHUNK` 持久 Worker，消费同一 `IndexVersion` 中 `PREPARED` 输入；逐文件 Chunk 集与检查点事务原子发布，支持取消检查、租约续期/过期接管、应用关闭续跑、显式失败重试及文件永久删除竞态。任务完成只代表切片阶段结束，索引保持 `BUILDING` 且不激活。
- 生命周期与契约：文件或递归文件夹永久删除时按准确 `file_id` 清理 Chunk；保留其他文件/知识库仍可复用的 Chunk。任务详情 OpenAPI 增加 `task_type`、`index_version_id`，生成契约为 34 schemas / 50 operations。
- 前端：知识库详情使用真实文件选择、成员列表、任务轮询、逐项结果和移出；解析中/失败、待索引与不可检索状态明确；刷新后恢复数据库状态。
- 验收证据：第十一批结论 `PASS`；后端 `60 passed`、Ruff、Pyright、compileall；前端 lint/typecheck、Vitest `13 passed`、production build；真实本地后端阶段 5 Playwright `1 passed`、阶段 4 回归 `1 passed`；OpenAPI 3.1 `34 schemas / 50 operations`；空库、已有数据迁移、降级/再升级与 SQLite `quick_check=ok`。详见 `docs/test-reports/stage-5-knowledge-base-foundation.md`。
- 未完成：模型下载、ONNX Embedding、FTS5、sqlite-vec、增量/原子索引激活、混合检索、引用和 RAG。因此阶段 5 不标记为 `PASS`。
- 下一批次：以本批稳定 Chunk 为输入，单独实现本地 ONNX Embedding 生成、持久化与恢复；不提前进入 FTS、向量索引、激活或检索。

## 进度口径

文件产出不等于测试通过；测试通过不等于 Spike 通过；Spike 通过不等于业务验收或发布完成。
