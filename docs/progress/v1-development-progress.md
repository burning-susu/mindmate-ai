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

- 状态：`PARTIAL`
- 阶段提交：`bc30e1f feat: implement secure local file management`
- 收口审计起点：`9e0174a docs: record stage 4 file management evidence`
- 收口修复提交：`3b29d22 fix: close stage 4 file management gaps`
- 已完成：文件夹、标签、文件 CRUD；multipart 导入校验；流式 staging；SHA-256 去重；同内容复用/独立记录；TXT/Markdown 解析；PDF/DOCX/PPTX 隔离子进程解析；正文搜索；受控内容读取；递归回收站恢复/永久删除；嵌套目录、筛选、批量操作、详情编辑和文件夹回收站前端。
- 验收证据：后端 `19 passed`（阶段 4 `10 passed`）、Ruff、Pyright；前端 lint/typecheck、Vitest `4 passed`、build；Playwright 生命周期 `1 passed`；OpenAPI 3.1 与前端类型同步；迁移往返和 SQLite quick check 通过。详见 `docs/test-reports/stage-4-file-management.md`。
- 阻塞：Folder/Tag 乐观锁和文件解析错误持久字段需要数据库迁移；解析子进程尚缺 Windows 硬内存限制，解析任务尚未由持久 Worker 异步领取；列表状态恢复和正式恶意文档/干净 Windows 验收未完成。
- 后续边界：FTS5、知识库索引、Embedding、向量与 RAG 仍属于阶段 5–6，本批次未提前实现。

## 进度口径

文件产出不等于测试通过；测试通过不等于 Spike 通过；Spike 通过不等于业务验收或发布完成。
