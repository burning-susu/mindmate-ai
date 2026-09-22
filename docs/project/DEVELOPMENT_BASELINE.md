# MindMate AI V1 开发基线
> 文档编号：DEVELOPMENT-BASELINE-MINDMATE-001
> 文档版本：v1.0
> 文档类型：development governance
> 状态：active
> 创建日期：2026-09-22

## 当前阶段

```text
PROJECT_STAGE=DEVELOPMENT
CURRENT_STAGE=DEVELOPMENT
BRANCH=feat/v1-bootstrap
BASELINE_TAG=baseline/pre-v1-rebaseline-2026-09-22
CODE_BASELINE_MODE=V1_BOOTSTRAP
```

## 当前事实源优先级

1. `docs/project/requirements/v1/18_最终决策表.md`
2. `docs/project/requirements/v1/16_Codex开发任务书.md`
3. `docs/project/requirements/v1/00_需求规格总纲.md`
4. `docs/project/requirements/v1/01–15` 专题需求文件
5. 当前代码、配置和测试证据
6. `docs/archive/2026-09-22-pre-v1/` 中的历史资料只用于追溯

本基线中的 00–18 文件是当前开发输入，不需要重新发起已冻结的产品、Provider、Embedding、向量存储、技术栈、页面结构或部署决策。

## 归档边界

历史项目级 `baseline`、`decisions`、`prd`、`architecture`、`acceptance` 和 `ui` 已完整移动到 `docs/archive/2026-09-22-pre-v1/`。原始业务资料 `项目业务资料/` 保持原位，Figma、Sketch 和 Word 文件不参与移动。

## 冻结实现基线

- React 19 + TypeScript + Vite
- Python 3.12 + FastAPI + Pydantic 2
- SQLite + WAL + FTS5 + sqlite-vec
- 本地 ONNX `BAAI/bge-small-zh-v1.5`，512 维
- DeepSeek API `deepseek-flash`，通过本地 httpx Adapter
- SQLite 持久 BackgroundTask，SSE 可恢复
- PyInstaller one-folder + Inno Setup

## 当前不宣称

本次基线切换只证明入口、分支、tag、归档和规格投放已建立，不证明代码、Spike、测试、打包、验收或发布完成。
