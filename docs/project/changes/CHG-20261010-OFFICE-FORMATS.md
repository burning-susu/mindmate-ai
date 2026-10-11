# CHG-20261010-OFFICE-FORMATS

状态：`USER ISSUES FIXED / TABLE STYLE VERIFIED / AUTOMATED PASS / NEW SERVER RUNNING`

日期：2026-10-10

## 来源与范围

用户明确要求增加 `.ppt` 和 `.xlsx` 支持，并要求预览保留原版式。本变更扩展既有文件导入、隔离解析、搜索/知识库索引和 LibreOffice PDF 预览，不改变本地存储、单文件/批量限制或数据库结构。

## 变更对象

- `KEEP`：PDF、DOCX、PPTX、XMind、TXT、Markdown 的现有导入行为；DOCX/PPTX 继续使用既有 PDF 版式预览。
- `ADD`：旧版二进制 PPT 与以 `.ppt` 扩展名保存的 OOXML 演示文稿签名识别；PPT 通过本地 LibreOffice Impress 转 PDF 并以页码提取文本；XLSX 使用 Python 标准库解析共享字符串、工作表和单元格地址；Excel 详情使用 LibreOffice Calc 导出当前工作表的 HTML 表格视图。
- `REVALIDATE`：上传扩展名/MIME/文件签名、ZIP 条目/展开体积/压缩率、解析子进程超时/内存/输出、PPT/PDF 页数与大小、XLSX HTML 大小及主动内容拦截、缓存隔离。
- `NO CHANGE`：数据库 schema、导入 API 结构、Provider、Embedding、原文件字节和云端服务调用。

## 行为边界

1. `.ppt` 接受旧版 OLE Compound File 文件，也接受完整签名校验为 PPTX 的 OOXML ZIP 包；`.xlsx` 必须是含工作簿和 `xl/` 内容的有效 OOXML ZIP 包。
2. XLSX 解析只读取本地工作簿 XML，不解压到文件系统、不运行宏、不访问外链、不计算公式，仅索引文件中已有的公式缓存值。
3. XLSX 解析限制 ZIP 条目数、展开大小、压缩率、共享字符串数、单元格数和输出文本大小。
4. PPT 转换使用独立临时目录和 LibreOffice profile，继承受限解析 Job Object，设置超时；只提取生成 PDF 的页文本并记录幻灯片页码。
5. PPT 使用内容哈希隔离的 PDF 预览。XLSX 每个工作表分别转换为独立 HTML 缓存，按文件哈希和工作表编号隔离；页面以无脚本沙箱 iframe 呈现工作表表格并提供工作表切换。HTML 禁止脚本、事件属性和外部资源。
6. 浏览器和 OpenAPI 上传入口均加入 `.ppt`、`.xlsx`；文件列表接受全窗口拖放，并在详情页等路由拖入时跳转至文件列表完成导入。

## 验收证据

上一轮用户测试发现两项问题：拖放只在文件列表内容区生效；`.ppt` 扩展名下的 OOXML PPTX ZIP 包被 OLE-only 签名检查拒绝；XLSX 转 PDF 遵循纵向打印页设置，造成 50 页且列被拆分。已将应用内容区拖放路由到文件导入、放宽 PPT 签名到两种有效容器，并将 XLSX 改为逐工作表 HTML 视图；HTML 输出经过主动内容校验并由 CSP sandbox iframe 呈现。针对后续“表格也显示出来”的反馈，注入了明显的单元格边框和表头样式，并升级 HTML 缓存键使旧无样式缓存失效。后端 XLSX 预览专项 `9 passed`；前序 Office 回归后端 `33 passed`，前端全量 `18 files / 99 tests passed`；Ruff、Pyright、typecheck、lint、production build 通过。手工 API 中 `.ppt` 达到 `PARSED`；XLSX 工作表 API 返回 `200 text/html`（474 行、3318 个单元格），响应含边框/表头样式和 CSP sandbox。新实例运行于 `http://127.0.0.1:5175`，API `8002`，使用隔离数据目录 `build/mindmate-office-format-test`。状态不代表合并、发布或完整 V1 阶段验收通过。
