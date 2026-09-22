# MindMate AI

个人本地 AI 知识学习助手 V1。产品目标是把文件整理、个人知识库、可溯源 AI 对话和逐题学习陪练连接成一个 Windows 本地闭环。

## 当前状态

- 阶段：`DEVELOPMENT`
- 分支：`feat/v1-bootstrap`
- 运行形态：Windows 本地 Web 应用；本地 FastAPI 服务 + 系统浏览器
- 当前规格：[`docs/project/requirements/v1/README.md`](docs/project/requirements/v1/README.md)
- 直接开发入口：[`18_最终决策表.md`](docs/project/requirements/v1/18_最终决策表.md)、[`16_Codex开发任务书.md`](docs/project/requirements/v1/16_Codex开发任务书.md)、[`15_技术架构与开发约束.md`](docs/project/requirements/v1/15_技术架构与开发约束.md)
- 历史治理归档：[`docs/archive/2026-09-22-pre-v1/`](docs/archive/2026-09-22-pre-v1/)

## 技术基线

- 前端：React 19、TypeScript、Vite、React Router、TanStack Query、Zustand、Tailwind CSS、Radix UI
- 后端：Python 3.12、FastAPI、Pydantic 2、SQLAlchemy 2、Alembic、httpx
- 本地数据：SQLite、WAL、FTS5、sqlite-vec
- Embedding：本地 ONNX Runtime CPU、`BAAI/bge-small-zh-v1.5`、512 维
- Chat：DeepSeek API `deepseek-flash`，仅由本地后端 Adapter 调用
- 测试：pytest、Vitest、Testing Library、Playwright
- 发布：PyInstaller one-folder、Inno Setup 当前用户级安装

## 开发约束

- 不提交 `.env`、API Key、Windows 凭据、用户文件、数据库、日志、模型缓存、备份或构建产物。
- 日常开发和自动化测试使用 Mock Provider，不调用真实付费 API。
- 前端不得直连 Provider、数据库或本地文件系统；本地 API 只监听回环地址。
- 不引入云服务器、Docker 必需依赖、Redis、Celery、独立向量服务或自动模型切换。
- 每完成一个任务阶段，运行对应测试并建立独立 Git 提交；提交前检查只包含本阶段文件。

## 开发命令

Windows PowerShell 等价脚本位于 `scripts/`。完成阶段 0 后使用：

```powershell
.\scripts\bootstrap.ps1
.\scripts\lint.ps1
.\scripts\typecheck.ps1
.\scripts\test.ps1
.\scripts\build.ps1
```

具体命令和阶段验收以 [`16_Codex开发任务书.md`](docs/project/requirements/v1/16_Codex开发任务书.md) 为准。
