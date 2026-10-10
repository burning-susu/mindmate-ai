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

## 未完成验收

当前 Windows 环境未检测到 LibreOffice、PowerPoint 或本地可校验的 LibreOffice 运行时目录。已验证无运行时接口安全返回 `PPTX_RENDERER_UNAVAILABLE`，但用户的 62 页 PPTX 尚未实际转换和目视比对；正式 one-folder 安装包也尚不存在（项目阶段 10）。因此本批状态为代码完成、运行时和真实视觉验收待补，不能宣称端到端预览可用。
