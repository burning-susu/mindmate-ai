# 第八十二批：Markdown 文件阅读视图

- 日期：2026-10-10
- 现象：Markdown 文件详情的“解析文本”区域显示 Markdown 语法源码，而非排版后的可读文档。

## 实现

- 新增前端 `MarkdownPreview`，将标题、段落、粗体/斜体/删除线、行内代码、无序/有序列表、引用、表格、分隔线和围栏代码块映射为 React 元素。
- 文件详情只在 `document_type=MARKDOWN` 时使用阅读视图。其他类型沿用原始解析文本框；“打开原文”仍可查看原始文件。
- 使用 React 文本节点，不使用 `dangerouslySetInnerHTML`。原始 HTML 作为普通文本；Markdown 链接只呈现可见标签，不主动加载或导航外部资源。
- 未引入新依赖，没有后端、API 或存储格式变更。

## 验证

| 检查 | 结果 |
| --- | --- |
| Markdown 组件与文件详情定向 Vitest | `10 passed` |
| 前端 typecheck | 通过 |
| 前端 lint | 通过 |
| 前端 build | 通过；存在既有 500 kB 主包提示 |

未做普通 Chrome/Edge 浏览器截图验收。
