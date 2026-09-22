# V1 开发进度

## 阶段 0

- 状态：`COMPLETED`
- 基线提交：`bdf40c2 docs: establish v1 development baseline`
- 阶段提交：待创建 `chore: establish reproducible development baseline`
- 已完成：需求/归档切换、React/Vite 工作区、FastAPI health/ready/version、npm/uv lock、PowerShell 脚本、CI、基础测试与质量配置。
- 验收证据：前端 lint/typecheck/test/build 通过；后端 pytest（2 passed）、Ruff、Pyright、OpenAPI 3.1 检查通过；health/ready 实际返回 `ok/ready`；浏览器验证首页和 `/chat` 路由渲染。

## 阶段 1

- 状态：`COMPLETED_WITH_RELEASE_GAPS`
- 阶段提交：待创建 `chore: validate windows ai and vector runtime`
- 必须验证：sqlite-vec、ONNX、Credential Manager、随机回环端口、Mock SSE、PyInstaller 和干净 Windows 启动。
- 当前结果：前 7 项通过；干净 Windows 环境和正式 Inno Setup 尚未执行，详见 `docs/test-reports/stage-1-spike.md`。

## 进度口径

文件产出不等于测试通过；测试通过不等于 Spike 通过；Spike 通过不等于业务验收或发布完成。
