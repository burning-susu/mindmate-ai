# 第九十批：PPT 与 XLSX 文件支持验证

日期：2026-10-10

## 结果

- `CODE=PASS`：新增 `.ppt` 和 `.xlsx` 导入类型；PPT 由本地 LibreOffice Impress 转 PDF 并提取页文本，XLSX 由标准库解析工作表、共享字符串、单元格地址及缓存值。`.ppt` 可为 OLE 容器或经完整签名识别的 OOXML PPTX 包。
- `LAYOUT_PREVIEW=PASS`：DOCX/PPT/PPTX 保留 PDF 版式预览；XLSX 每个工作表由 LibreOffice 导出 HTML 表格并放入 CSP sandbox iframe，可切换多个工作表，不再遵循纵向打印分页。
- `GLOBAL_FILE_DROP=PASS`：文件列表内容区保留原拖放体验；应用内容区其他路由/区域收到文件拖放时跳转到文件列表并启动上传。前端回归覆盖从学习页拖入 `.ppt` 的状态迁移和单次上传。
- `BACKEND_AUTOMATED=PASS`：格式、签名、XLSX 解析/HTML 安全/缓存/API、Office 转换过滤器、现有阶段 4 文件导入组合测试 `33 passed`。
- `XLSX_TABLE_STYLE=PASS`：预览输出为单一 HTML 表格，单元格强制 1px 实线边框，首行使用表头底色/粗体/加粗底线；测试确认安全校验后写入样式，并通过不同缓存键避开旧版无边框结果。样本 API 响应为 474 行、3318 个单元格。
- `BACKEND_QUALITY=PASS`：Ruff、定向 Pyright `0 errors`、compileall。
- `FRONTEND_AUTOMATED=PASS`：Vitest `18 files / 99 tests passed`；typecheck、lint、production build 通过。Vite 有既有的大型 JS chunk 提醒。
- `API_CONTRACT=PASS`：OpenAPI 3.1 导出并生成前端类型；当前 `119 schemas / 128 operations`，新增 `.ppt`、XLSX 工作表 HTML 预览路由。
- `REAL_FILE_SMOKE=PASS`：本机 `.ppt` 扩展名的 OOXML PPT 样本通过导入并解析 `5` 张幻灯片；XLSX 样本解析为 `1` 个工作表、`3318` 个单元格，HTML 预览 API 返回 `200 text/html`、`474` 行表格和 CSP sandbox。只记录结构计数，不输出工作簿正文；源文件只读复制到工作区验证目录。

## 边界

本批未验证 Microsoft Office/WPS 与 LibreOffice 的像素级一致性。公式只读取文件中已有的缓存值，不运行公式或宏。新版实例已在 `http://127.0.0.1:5175` 启动，使用隔离目录 `build/mindmate-office-format-test`；API `8002` 健康检查为 `ok`。Windows Computer Use 初始化因自动审批服务返回 `429` 未运行；本批不包含浏览器截图验收。阶段 8 和完整 V1 继续为 `PARTIAL`。
