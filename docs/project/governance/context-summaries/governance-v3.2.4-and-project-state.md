# V1 开发与治理状态摘要
> 摘要编号：CTX-SUMMARY-001
> 摘要版本：v2.0
> 生成时间：2026-09-22
> 状态：CURRENT
> 用途：任务前最小上下文复用

## 当前事实源

- `docs/project/requirements/v1/18_最终决策表.md`：最终冻结选择。
- `docs/project/requirements/v1/16_Codex开发任务书.md`：阶段 0–10、测试、停止条件和提交纪律。
- `docs/project/requirements/v1/00_需求规格总纲.md`：V1 总纲和范围。
- `docs/project/requirements/v1/15_技术架构与开发约束.md`：React/FastAPI/SQLite/sqlite-vec/ONNX/DeepSeek/打包和安全约束。
- `docs/project/requirements/v1/01–14`：专题需求、API、验收、UI 和测试场景。
- 当前代码、配置和测试证据：随开发阶段新增。
- `docs/archive/2026-09-22-pre-v1/`：旧项目治理文档，只用于历史追溯。

## 当前状态

```text
PROJECT_STAGE=DEVELOPMENT
CURRENT_STAGE=DEVELOPMENT
DEVELOPMENT_BRANCH=feat/v1-bootstrap
BASELINE_TAG=baseline/pre-v1-rebaseline-2026-09-22
CODE_BASELINE_MODE=V1_BOOTSTRAP
DEVELOPMENT_STATUS=IN_PROGRESS
PROVIDER_RUNTIME_MODE=MOCK_ONLY
REAL_PROVIDER_CALLS=DISABLED
```

## 冻结技术基线

- React 19 + TypeScript + Vite；React Router；TanStack Query；Zustand；Tailwind CSS + Radix UI。
- Python 3.12 + FastAPI + Pydantic 2；SQLAlchemy 2；Alembic；httpx。
- SQLite + WAL + FTS5 + sqlite-vec；本地嵌入式向量存储，经 Storage Adapter。
- 本地 ONNX Runtime CPU + `BAAI/bge-small-zh-v1.5`，512 维。
- DeepSeek API `deepseek-flash`，OpenAI-compatible Chat Completions，经本地后端 Adapter。
- SQLite 持久 BackgroundTask；SSE 可恢复；Mock Provider 贯穿开发测试。
- PyInstaller one-folder + Inno Setup；Windows 11 x64 正式支持。

## 开发边界

- 不重新讨论冻结的产品、Provider、Embedding、向量存储、技术栈、页面结构或部署方式。
- 不调用真实 Provider，不读取或验证 API Key，不上传用户文件，不提交凭据、用户数据、模型缓存、日志或构建产物。
- 阶段 0 先建立可重复工程基线；阶段 1 的 sqlite-vec、ONNX、Credential Manager、Mock SSE 和 PyInstaller Spike 已通过；阶段 2–4 已完成，当前继续文件解析器、知识库和 RAG 垂直闭环。
- Spike 失败、需求冲突、外部账号/费用权限或破坏性操作是停止询问条件。

## 历史边界

旧 G6 Provider/Guard/Decision 链已完整归档，不作为当前开发门禁。历史文件不得删除或改写；当前开发状态以本摘要和 00–18 规格为准。
