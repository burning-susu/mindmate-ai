# 第八十八批：PPTX 原版式预览

- 日期：2026-10-10
- 目标：PPTX 详情显示真实幻灯片版面，不再把提取文本块当作视觉预览。
- 实现：本地 LibreOffice 转为 PDF；按源内容 SHA-256 缓存；原子发布；独立 profile/workdir；使用 Windows Job Object；限制单并发、180 秒超时、50 MiB 输入、200 MiB PDF、2000 页；输出页数与解析到的幻灯片数核对。前端使用 Blob iframe 和现有 PDF 阅读器，文本提取折叠显示。
- 运行时：新增 LibreOffice 定位与暂存脚本，记录版本、许可证路径及 `soffice.exe` SHA-256；不新增 Python/npm 依赖。

## 自动化验证

| 检查 | 结果 |
| --- | --- |
| `backend/tests/test_pptx_preview.py` | `3 passed`，覆盖缓存复用、超时终止、PDF 输出校验 |
| `backend/tests/test_stage4_files.py` | `18 passed`，包含 PDF API 响应、页数不匹配及无 LibreOffice 的 503 错误 |
| 前端 Vitest | `18 files / 96 tests passed` |
| Ruff / Pyright / compileall | 通过；Pyright 0 errors |
| typecheck / lint / build | 通过；build 保留既有主 JS 体积提示 |
| OpenAPI / 前端生成类型 | 已同步 `GET /api/v1/files/{file_id}/pptx-preview` |

## 运行验收

LibreOffice `26.8.1.1` 已暂存到 `build/runtime/libreoffice`；用户提供的 `01_springboot基础篇.pptx` 实际转换为 62 页、`2,493,325` 字节 PDF。Poppler 渲染的第 1 页显示 `SpringBoot3` 标题及上方图形，第 62 页显示品牌页内容，画面非空且布局可读。

MindMate API/Web 服务未重启，尚未完成浏览器内详情页人工验收。自动启动请求连续两次因 Codex 自动审批 `429` 失败，均未执行。正式 PyInstaller/Inno Setup 工程属于阶段 10，尚未生成最终安装包。
