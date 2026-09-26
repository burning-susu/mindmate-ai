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

阶段 0 的本地启动方式：

```powershell
.\scripts\dev.ps1
```

前端默认运行在 `http://127.0.0.1:5173`，本地 API 默认运行在 `http://127.0.0.1:8000`。阶段 0 只提供健康检查和应用壳，不代表业务闭环已完成。`.\scripts\dev.ps1` 使用这两个回环端口；端口已被占用时会停止并说明原因，不会悄悄换端口。Ctrl+C 会结束脚本本次启动的后端和前端进程。

## 求职 Demo

固定合成资料、真实本地 ONNX Embedding、Mock Chat Provider。这条入口不调用真实 DeepSeek，不读取真实 Key，也不使用默认用户数据目录。

```powershell
.\scripts\demo.ps1
```

默认数据根是 `%TEMP%\mindmate-ai-stage36-job-demo`。系统可能清理 `%TEMP%`；目录被清空后，脚本只在空目录或带所有权标记的目录里重新准备，不会接管或清空 `%LOCALAPPDATA%\MindMateAI`。API 是 `http://127.0.0.1:8001`，页面是 `http://127.0.0.1:5174/knowledge-bases/<固定主库>`。启动前会核对运行中的模型指纹和主库 `READY`。Ctrl+C 停止本次启动的进程。

端口被占用、固定模型缓存 `backend/model-cache/manager-validation` 缺失，或准备失败时，脚本会停下来说明原因，不会下载模型、更换模型或切换到真实 Provider。浏览器里的回答正文是 Mock 生成，用来证明检索、引用、保存和页面显示；它不证明 DeepSeek 已经答出资料事实。用户界面上的文件上传和建库不由这条命令代替。
