# 第八十九批：DOCX 原版式预览

- 日期：2026-10-10
- 目标：DOCX 详情直接阅读 Word 原页面，而不是重新排版提取段落。
- 实现：复用本地 LibreOffice Writer 转 PDF；新增 `/api/v1/files/{file_id}/docx-preview`；DOCX/PPTX 独立按 SHA-256 缓存；前端复用浏览器 PDF 查看器，文本提取放在折叠项。
- 安全：继续使用独立 profile/workdir、Windows Job Object、单并发、180 秒转换超时、50 MiB 输入、200 MiB PDF 和 2000 页限制；失败显示错误，不退回伪造页面卡片。

## 验证

| 检查 | 结果 |
| --- | --- |
| Office 转换器单元测试 | `4 passed`，DOCX Writer 和 PPTX Impress 导出过滤器、缓存复用、超时、无效 PDF |
| `backend/tests/test_stage4_files.py` | `18 passed`，包含 DOCX/PPTX PDF 响应、页数不匹配和缺失运行时错误 |
| 前端 Vitest | `18 files / 96 tests passed`，覆盖 Word/PPTX 原版式 iframe、提取文本折叠和错误态 |
| Ruff / Pyright / compileall / typecheck / lint / build | 通过；Pyright 0 errors；build 保留既有主 JS 体积提示 |
| 真实演示 DOCX | LibreOffice 26.8.1.1 转为 23 页 PDF（991,564 字节）；Poppler 渲染检查首页和末页，非空且可读 |

当前 MindMate API 进程仍是旧版，DOCX preview 路由返回 `404`。重启命令连续两次被 Codex 自动审批 `429` 阻止、未执行；因此尚未在详情页完成浏览器人工验收。DOCX 的实际转换和生成页面已独立验证。
