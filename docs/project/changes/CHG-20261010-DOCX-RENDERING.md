# CHG-20261010-DOCX-RENDERING

状态：`LOCAL RENDER PASS / 旧版后端重启与浏览器验收待完成`

日期：2026-10-10

## 来源与问题

DOCX 详情原先把提取段落和表格重新排版。用户明确反馈这不是想要的效果；DOCX 详情应保留 Word 文档的真实页面分页、段落样式、图片和表格布局。

## 已批准方案

复用 `CHG-20261010-PPTX-RENDERING` 中已确认的本地 LibreOffice 运行时，使用 Writer 的 PDF 导出过滤器；不新增外部运行时或 Python/npm 依赖。

## 实施

- 新增只读 `GET /api/v1/files/{file_id}/docx-preview`，使用现有安全转换 Adapter 和内容哈希缓存，返回 PDF 原版式页面。
- DOCX 使用独立缓存命名空间，防止与同内容 PPTX 的转换结果冲突。
- 详情页优先显示本地 PDF 页面；解析文本收纳在“查看提取文本”折叠项；转换缺失/失败时显示明确错误并保留顶部“打开原文”。
- 继续使用独立 LibreOffice profile/workdir、Windows Job Object、单并发、转换超时、输入/输出大小及页数限制。
- DOCX 解析器没有可靠的页数元数据；转换 PDF 仍验证为有效且页数在上限内，不伪造页数一致性检查。

## 验收证据

自动化和真实文件验证见 `docs/test-reports/stage-89-docx-rendered-preview.md`。用户演示文件已转换为 23 页 PDF 并检查首页和末页。当前 MindMate 仍运行旧版 API，`/docx-preview` 请求返回 `404`；Codex 重启命令连续被自动审批 `429` 阻断、未执行，浏览器内详情页验收待重启服务后完成。
