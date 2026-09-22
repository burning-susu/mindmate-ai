# 阶段 0 工程基线报告

> 日期：2026-09-22
> 阶段：0 / 工程基线
> 状态：PASSED

## 已完成

- React 19 + TypeScript + Vite 前端工作区和 `package-lock.json`。
- Python 3.12 + FastAPI 后端工作区和 `uv.lock`。
- React Router、TanStack Query、Zustand、Tailwind CSS、Radix Dialog、Vitest、Playwright 配置入口。
- FastAPI `/api/v1/health`、`/api/v1/ready`、`/api/v1/version` 和 OpenAPI 3.1。
- PowerShell `bootstrap.ps1`、`lint.ps1`、`typecheck.ps1`、`test.ps1`、`build.ps1`、`dev.ps1`。
- 最小 CI：前端 npm 检查和后端 uv 检查。
- `.editorconfig`、`.env.example` 和秘密/数据/模型/日志/构建产物忽略规则。

## 验收证据

| 检查 | 结果 |
| --- | --- |
| `scripts/bootstrap.ps1 -SkipInstall` | PASS |
| `scripts/lint.ps1` | PASS |
| `scripts/typecheck.ps1` | PASS |
| `scripts/test.ps1` | PASS；前端 1 passed，后端 2 passed |
| `scripts/build.ps1` | PASS |
| `GET /api/v1/health` | PASS；`status=ok` |
| `GET /api/v1/ready` | PASS；`status=ready` |
| `/openapi.json` | PASS；OpenAPI 3.1 |
| 浏览器首页 | PASS；应用壳和本地服务状态可见 |
| 浏览器 `/chat` | PASS；路由渲染正确 |

## 未覆盖

阶段 1 的 sqlite-vec、ONNX Runtime、Windows Credential Manager、Mock SSE、PyInstaller 和干净 Windows 启动 Spike 尚未执行。
