# 第八十五批：XMind 思维导图文件支持

- 日期：2026-10-10
- 变更：按用户明确请求新增 `.xmind` 本地导入、隔离解析、全文搜索/知识库索引文本和主题树预览。
- 变更记录：`docs/project/changes/CHG-20261010-XMIND-SUPPORT.md`（`IMPLEMENTED_LOCAL`）。

## 实现

- `.xmind` 进入 `SUPPORTED_DOCUMENTS`，允许 XMind 常见 MIME；识别 ZIP 根 `content.json` 或 `content.xml`，伪装普通 ZIP 在复制前拒绝。
- 解析器在既有受限子进程中读取现代 JSON sheet/rootTopic/attached/detached 和旧版 XML sheet/topic/attached topics；保留工作表、主题树和节点定位元数据，节点标题组成可检索文本。
- 文件工作台、建知识库、知识库详情上传、文件类型过滤均接受 XMind；详情页按工作表展示根主题和子主题树。
- 更新 DEC-FILE-002、文件管理、安全、验收、技术架构及变更记录。

## 安全边界

- 不解压成员到磁盘，不访问外链，不处理附件或宏。
- 上传签名校验和解析器都只认根 content 文件；解析器拒绝重复 ZIP 条目。
- 复用现有 10,000 ZIP 条目、200 MiB 解压体积、100:1 压缩比限制；XMind 主数据最多 20 MiB、深度最多 100、主题最多 200,000。仍受解析子进程 30 秒/512 MiB 和解析输出 20 MiB 上限约束。
- 未引入第三方依赖、数据库迁移或新 API shape；不支持版本的任务安全失败，不会标记解析成功。

## 验证

| 检查 | 结果 |
| --- | --- |
| 后端 `tests/test_stage4_files.py` | `14 passed` |
| 前端 document-preview + file workspace Vitest | `15 passed` |
| Ruff / Pyright / compileall | 通过 |
| 前端 typecheck / lint / build | 通过；build 保留既有 bundle-size 提示 |

没有第三方真实 `.xmind` 文件样本的普通浏览器验收。测试 fixture 覆盖 JSON、新旧 XML 结构及伪装 ZIP 签名拒绝。
