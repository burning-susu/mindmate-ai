# 阶段 4：文件管理垂直切片测试报告

> 阶段：`4`
> 状态：`COMPLETED_WITH_PARSER_FOLLOW_UP`
> 目标提交：`feat: implement secure local file management`
> Provider：`MOCK_ONLY`
> 真实外部请求：`DISABLED`

## 完成范围

- 后端文件导入 API：multipart、多文件、幂等、staging 流式复制、50 MB/20 个/500 MB 限制。
- 支持格式校验：PDF 文件头、DOCX/PPTX Office 包结构、TXT/Markdown 可读性校验。
- 内容对象与逻辑文件记录：SHA-256 精确重复检测、同内容复用物理对象、独立逻辑记录、同名自动编号。
- TXT/Markdown 本地解析文本与元数据持久化；PDF/DOCX/PPTX 保留 `QUEUED/PARSER_PENDING` 任务边界，未伪装为解析完成。
- 文件列表、详情、受控内容读取、文本预览、重处理入口、文件夹/标签 CRUD 和关联。
- 文件软删除、30 天回收站、恢复、明确确认后的永久删除；共享内容对象只在最后一个逻辑引用删除后清理。
- React 文件工作台：目录树、搜索、筛选、拖放/多选导入、重复决策、任务反馈、详情和回收站页面。

## 验收证据

| 检查项 | 结果 |
| --- | --- |
| 支持格式导入与托管副本 | 通过 |
| 伪装扩展名/不可读文本拒绝 | 通过 |
| 单文件、单批次、文件数限制 | 通过；单文件超限由流式复制器在复制过程中拒绝 |
| 精确重复、复用、独立记录 | 通过；独立记录复用同一 ContentObject |
| 文件夹层级、标签上限、名称冲突 | 通过 |
| 文件列表、详情、搜索、受控内容读取 | 通过 |
| 软删除、恢复、永久删除、托管字节清理 | 通过 |
| 任意路径读取/路径穿越 | 未提供任意路径 API；存储路径始终由数据库相对路径经数据根约束解析 |
| 真实 Provider/API Key | 未调用、未读取、未写入 |

## 测试命令

```text
backend\.venv\Scripts\pytest.exe -q
14 passed

backend\.venv\Scripts\ruff.exe check src tests
All checks passed

backend\.venv\Scripts\pyright.exe src tests
0 errors, 0 warnings, 0 informations

frontend\> npm run lint
frontend\> npm run typecheck
frontend\> npm run test -- --run
1 test file, 1 test passed
frontend\> npm run build
Vite build succeeded

backend\.venv\Scripts\python.exe scripts/export_openapi.py
OpenAPI 3.1.0 exported

frontend\> node scripts/generate-api-types.mjs
Generated 13 schemas and 37 operations
```

## 浏览器验证

- `http://127.0.0.1:5173/files`：首屏非空，目录树、搜索、导入投放区、表格、回收站入口均渲染。
- 通过页面创建文件夹后，目录树和筛选菜单出现新文件夹；验证了 JSON 写请求的 `Content-Type` 修复。
- `/files/:id` 和 `/trash` 路由已接入；不可用文件详情显示专用错误状态，不出现白屏。
- 开发服务仅监听本地回环地址；未通过浏览器上传用户真实文件，导入边界由后端契约测试覆盖。

## 未完成与后续阶段

- PDF/DOCX/PPTX 解析 Adapter 与受限子进程尚未在本阶段安装/验证具体解析器，当前仅完成格式识别和安全任务边界。
- FTS5、知识库索引、Embedding、向量和引用将在阶段 5–6 实现。
- 干净 Windows 安装包、Inno Setup 和正式发布验证仍属于后续发布门禁。
