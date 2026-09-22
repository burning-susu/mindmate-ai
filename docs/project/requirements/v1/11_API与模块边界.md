# 11 API 与模块边界

## 1. 文档目的

本文档定义 MindMate AI V1 的前端、本地后端、业务模块、数据库、文件系统、后台任务、AI 能力和 Provider Adapter 边界，并给出 REST API、SSE 流式事件、错误对象、分页、幂等、并发控制、文件导入和 OpenAPI 契约要求。

本文件不冻结具体编程语言和 Web 框架。技术栈将在 15_技术架构与开发约束.md 确定，但开发实现必须遵守本文件的契约。

## 2. V1 接口基线

| 项目 | V1 基线 |
| --- | --- |
| API 风格 | REST |
| 根路径 | /api/v1 |
| API 文档 | OpenAPI 3.1 |
| JSON 命名 | snake_case |
| 流式输出 | SSE |
| 长任务 | 202 Accepted＋持久 BackgroundTask |
| AI 生成 | AI Operation＋可重连 SSE |
| 列表分页 | 游标分页 |
| 错误格式 | application/problem+json 扩展 |
| 幂等 | Idempotency-Key＋业务 request_id |
| 并发修改 | row_version 或 If-Match |
| 服务监听 | 仅本机回环地址 |
| 前端数据访问 | 只能访问本地后端 API |

## 3. 总体架构边界

~~~mermaid
flowchart TD
    UI["Web 前端"] --> API["本地 API 层"]
    API --> APP["应用服务层"]
    APP --> DOMAIN["领域模型与端口"]
    DOMAIN --> INFRA["本地基础设施适配器"]
    INFRA --> EXT["SQLite、文件、向量与 DeepSeek"]
~~~

依赖方向必须由外向内。领域层不得导入前端、Web 框架、DeepSeek SDK、SQLite 驱动或具体向量库。

## 4. 层级职责

### 4.1 Web 前端

负责：

- 页面与交互；
- 表单校验；
- 请求发起；
- SSE 事件消费；
- 视图状态；
- 乐观 UI；
- 用户可读错误；
- 无障碍与响应式。

不得：

- 直接读取 SQLite；
- 直接访问托管文件路径；
- 直接调用 DeepSeek；
- 保存 API Key；
- 自行判定业务状态；
- 自行计算掌握度；
- 自行发布索引；
- 根据模型输出执行命令。

### 4.2 API 层

负责：

- 路由；
- 请求解析；
- DTO 校验；
- 本地会话与来源校验；
- 调用应用用例；
- HTTP 状态码；
- SSE 格式；
- 错误映射；
- 请求 ID；
- OpenAPI。

不得包含核心业务规则。

### 4.3 应用服务层

负责：

- 编排领域用例；
- 事务边界；
- 权限和状态检查；
- 幂等；
- 调用端口；
- 创建后台任务；
- 创建 AI Operation；
- 将领域结果映射为 DTO。

### 4.4 领域层

负责：

- 文件、知识库、对话和学习规则；
- 状态机；
- 删除与恢复；
- 掌握度；
- 复习调度；
- 任务状态；
- 引用约束；
- 不变量与领域错误。

领域层不能依赖 HTTP。

### 4.5 基础设施层

负责实现端口：

- SQLite Repository；
- 托管文件；
- 文档解析；
- FTS5；
- VectorStore；
- Embedding；
- Reranker；
- DeepSeek Chat；
- 系统凭据；
- 后台任务调度；
- 时钟和 UUID。

## 5. 业务模块

### 5.1 System

负责：

- 健康检查；
- 应用版本；
- schema 版本；
- 能力状态；
- 磁盘与数据目录状态；
- 备份恢复；
- 本地会话安全。

### 5.2 Files

拥有：

- File；
- ContentObject；
- Folder；
- Tag；
- FileTag；
- ParseRevision；
- TextBlock；
- 文件导入与预览。

### 5.3 Knowledge

拥有：

- KnowledgeBase；
- KnowledgeBaseFile；
- Chunk；
- EmbeddingRecord；
- IndexVersion；
- RAG 检索；
- 引用证据构造。

只能通过 FilesReadPort 读取文件信息，不直接修改 Files 表。

### 5.4 AI

拥有：

- ProviderProfile；
- PromptTemplate；
- ChatProviderAdapter；
- EmbeddingAdapter；
- RerankerAdapter；
- 模型能力；
- Token 用量；
- AI Operation。

### 5.5 Chat

拥有：

- Conversation；
- ConversationScope；
- Message；
- AnswerVersion；
- ConversationEvent；
- ConversationSummary；
- Draft。

通过 RetrievalPort 和 ChatGenerationPort 使用知识与 AI。

### 5.6 Learning

拥有：

- LearningSession；
- LearningPlan；
- KnowledgePoint；
- LearningQuestion；
- LearningAttempt；
- LearningFeedback；
- MasteryRecord；
- ReviewSchedule；
- LearningSummary。

通过 RetrievalPort 和 LearningGenerationPort 使用知识与 AI。

### 5.7 History

提供对话和学习历史的查询投影，不拥有原始会话数据。

历史删除分别调用 Chat 和 Learning 的删除用例，不直接删除其表。

### 5.8 Tasks

拥有：

- BackgroundTask；
- TaskAttempt；
- TaskDependency；
- TaskEvent；
- 调度、取消、重试和重启恢复。

### 5.9 Search

维护：

- 文件搜索投影；
- 对话搜索投影；
- 学习搜索投影；
- 全局搜索聚合。

FTS 只是投影，业务数据仍由对应模块拥有。

### 5.10 Trash

编排软删除、恢复和到期清理。不得绕过各模块的删除端口直接级联数据库。

## 6. 模块依赖规则

允许的主要依赖：

~~~mermaid
flowchart TD
    CHAT["Chat"] --> KNOW["Knowledge"]
    LEARN["Learning"] --> KNOW
    CHAT --> AI["AI"]
    LEARN --> AI
    KNOW --> FILES["Files"]
    KNOW --> AI
~~~

Tasks 可以调用注册的任务处理器，但任务处理器仍属于目标业务模块。

History、Search 和 Trash 通过公开端口读取或编排，不直接写其他模块私有表。

禁止：

- Files 依赖 Chat；
- Knowledge 依赖页面；
- AI 依赖 Chat 或 Learning 业务实体；
- 基础设施反向调用 API Controller；
- 模块直接导入其他模块的 Repository；
- 循环依赖。

## 7. API 运行边界

### 7.1 本机监听

- 只绑定 127.0.0.1 和必要的 IPv6 回环；
- 不绑定 0.0.0.0；
- 默认不允许局域网访问；
- 端口可由应用安全选择；
- 不把端口暴露为公网服务。

### 7.2 前后端来源

优先由本地后端服务前端静态资源，保持同源。

如果开发模式前后端端口不同：

- CORS 只允许明确开发来源；
- 生产构建关闭宽泛 CORS；
- 不允许通配符来源；
- 不允许外部网站携带本地凭据访问。

### 7.3 本地会话

应用启动时建立随机本地会话：

- 使用内存随机令牌或 HttpOnly SameSite=Strict Cookie；
- 修改请求具有 CSRF 防护；
- 会话只对当前应用前端有效；
- 应用重启后失效；
- 不等同于用户登录系统。

### 7.4 Host 校验

只接受允许的本地主机 Host：

- localhost；
- 127.0.0.1；
- 必要的 IPv6 loopback；
- 打包运行时明确的应用来源。

防止外部域名通过 DNS rebinding 调用本地 API。

## 8. 通用请求规则

### 8.1 Content-Type

- JSON：application/json；
- 错误：application/problem+json；
- 文件导入：multipart/form-data；
- SSE：text/event-stream；
- 文件预览：安全的实际 MIME 类型。

### 8.2 请求 ID

每个请求具有 request_id：

- 前端可以发送 X-Request-ID；
- 缺失时后端生成 UUIDv7；
- 响应返回 X-Request-ID；
- 日志、任务和 AI Operation 使用该 ID 关联；
- 不把 request_id 当幂等键。

### 8.3 时间

API 时间统一使用 ISO 8601 UTC 字符串，例如：

~~~text
2026-09-21T10:30:00.000Z
~~~

本地日期字段单独使用 YYYY-MM-DD。

### 8.4 ID

ID 为不透明字符串。前端不得解析 UUID 时间或依赖长度。

### 8.5 布尔与空值

- 缺失表示未提供；
- null 表示明确清空，前提是字段允许；
- false 与缺失不能混用；
- PATCH 必须区分未修改和清空。

## 9. 成功响应

### 9.1 单个资源

直接返回资源 DTO，不额外套无意义的 data 层。

示例：

~~~json
{
  "file_id": "019...",
  "display_name": "学习资料.pdf",
  "status": "READY",
  "row_version": 4,
  "created_at": "2026-09-21T10:30:00.000Z"
}
~~~

### 9.2 列表

~~~json
{
  "items": [],
  "next_cursor": null,
  "has_more": false
}
~~~

### 9.3 异步接受

长任务返回 202：

~~~json
{
  "task_id": "019...",
  "status": "QUEUED",
  "resource_ids": [],
  "status_url": "/api/v1/tasks/019..."
}
~~~

AI 生成返回 AI Operation：

~~~json
{
  "operation_id": "019...",
  "status": "QUEUED",
  "events_url": "/api/v1/ai-operations/019.../events",
  "cancel_url": "/api/v1/ai-operations/019.../cancel"
}
~~~

## 10. 错误响应

### 10.1 格式

~~~json
{
  "type": "https://mindmate.local/problems/source-invalid",
  "title": "资料范围不可用",
  "status": 409,
  "code": "SOURCE_INVALID",
  "detail": "所选知识库的索引需要重建。",
  "instance": "/api/v1/conversations/019.../messages",
  "request_id": "019...",
  "retryable": false,
  "field_errors": [],
  "actions": [
    {
      "type": "OPEN_KNOWLEDGE_BASE",
      "resource_id": "019..."
    }
  ]
}
~~~

### 10.2 安全

错误不得包含：

- 堆栈；
- SQL；
- API Key；
- Authorization Header；
- 本地绝对路径；
- 完整 Prompt；
- 完整 Provider 响应；
- 整份文件正文。

### 10.3 HTTP 状态

| 状态 | 用途 |
| --- | --- |
| 200 | 成功读取或更新 |
| 201 | 同步创建完成 |
| 202 | 已接受异步处理 |
| 204 | 成功且无正文 |
| 400 | 无法解析的请求 |
| 401 | 本地会话无效 |
| 403 | 来源、CSRF 或操作不允许 |
| 404 | 资源不存在或不可见 |
| 409 | 业务状态冲突 |
| 412 | row_version 或 If-Match 不一致 |
| 413 | 文件或请求过大 |
| 415 | 不支持的媒体类型 |
| 422 | 字段或业务校验失败 |
| 429 | 本地或 Provider 限流 |
| 500 | 未知内部错误 |
| 502 | Provider 返回无效结果 |
| 503 | 依赖暂时不可用 |
| 504 | Provider 或处理超时 |

## 11. 字段校验

### 11.1 两层校验

API 层校验：

- 类型；
- 必填；
- 长度；
- 枚举；
- 格式；
- 文件数量与大小。

领域层校验：

- 状态是否允许；
- 关系是否存在；
- 范围是否有效；
- 删除与恢复规则；
- 学习和掌握度规则；
- 索引版本；
- Provider 能力。

### 11.2 FieldError

包含：

- field；
- code；
- message；
- rejected_value 仅在安全时返回。

不返回 API Key 等敏感 rejected_value。

## 12. 分页、筛选与排序

### 12.1 游标分页

列表参数：

- cursor，可选；
- limit，默认 30；
- 最大 100。

游标：

- 由后端生成；
- 对前端不透明；
- 包含排序位置和必要筛选哈希；
- 不包含敏感正文；
- 筛选变化后旧游标无效。

### 12.2 排序

使用：

~~~text
sort=updated_at:desc
~~~

每个端点只允许白名单字段。

### 12.3 筛选

筛选参数明确命名，例如：

- status；
- folder_id；
- tag_id；
- source_type；
- date_from；
- date_to；
- q。

不支持客户端提交任意 SQL 表达式。

## 13. 幂等

### 13.1 需要 Idempotency-Key

以下操作必须支持：

- 文件导入会话；
- 创建知识库；
- 添加知识库文件；
- 创建对话并发送第一条消息；
- 发送对话消息；
- 重新生成；
- 创建学习会话；
- 提交学习答案；
- 创建后台任务；
- 永久删除；
- 备份与恢复。

### 13.2 规则

- Key 由客户端生成；
- 同一业务操作重试复用 Key；
- 后端保存 Key、请求哈希和结果；
- 同 Key 同请求返回原结果；
- 同 Key 不同请求返回 409 IDEMPOTENCY_KEY_REUSED；
- 活动中的请求返回原 operation_id 或 task_id；
- 默认幂等记录至少保留 24 小时；
- 删除和迁移等高风险操作可以保留更久。

### 13.3 业务 request_id

AI 消息和学习 Attempt 同时保存业务 request_id，防止绕过 HTTP 层后重复创建。

## 14. 并发修改

### 14.1 Row Version

可编辑资源返回 row_version。

PATCH、DELETE、移动和恢复请求携带：

- If-Match Header；
- 或 expected_version 字段。

一个端点只能选择一种主方式，OpenAPI 中明确。

V1 推荐请求体 expected_version，便于本地客户端处理。

### 14.2 冲突

版本不一致返回 412：

- 当前 row_version；
- 可安全展示的当前资源摘要；
- 用户可以刷新后重试；
- 不自动覆盖。

### 14.3 列表状态

后台任务更新状态不要求用户编辑请求携带任务 row_version；任务动作由任务状态机原子判断。

## 15. SSE 通用规范

### 15.1 事件格式

~~~text
id: 12
event: text_delta
data: {"operation_id":"019...","delta":"内容"}

~~~

每个事件包含：

- event_id；
- operation_id 或 stream_scope；
- event_type；
- sequence_number；
- created_at；
- payload。

### 15.2 AI Operation 事件

- operation_started；
- retrieval_started；
- retrieval_completed；
- text_delta；
- structured_result；
- citation_result；
- usage；
- operation_completed；
- operation_cancelled；
- operation_failed；
- heartbeat。

不向前端发送内部思维链和完整 Prompt。

### 15.3 可重连

- GET 事件端点支持 Last-Event-ID；
- 后端在 Operation 完成后一段时间保留事件；
- 初始建议保留 30 分钟；
- 重连只补发缺失事件；
- 不重复写业务消息；
- 事件已过期时返回当前 Operation 快照。

### 15.4 心跳

空闲期间约每 15～30 秒发送 heartbeat，防止连接被误判为断开。

### 15.5 终态

收到 completed、cancelled 或 failed 后关闭流。

前端断开 SSE 不等于取消 Operation。取消必须调用 cancel 端点。

## 16. 全局事件流

建议提供：

~~~text
GET /api/v1/events
~~~

用于：

- 任务状态变化；
- 文件处理状态；
- 知识库索引状态；
- 回收站变化；
- Provider 配置状态；
- 复习到期数量变化。

全局流不发送 AI 正文 delta。AI 正文使用 Operation 专属流。

如果全局 SSE 实现推迟，V1 可以使用短轮询，但 API DTO 与状态语义保持一致。

## 17. System API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/system/health | 进程与数据库健康 |
| GET | /api/v1/system/readiness | 文件、模型、Provider 和任务就绪 |
| GET | /api/v1/system/capabilities | 当前功能能力 |
| GET | /api/v1/system/storage | 本地存储摘要 |
| POST | /api/v1/system/integrity-checks | 创建完整性检查任务 |
| GET | /api/v1/system/integrity-checks/{id} | 检查结果 |
| POST | /api/v1/backups | 创建备份任务 |
| GET | /api/v1/backups | 备份记录 |
| POST | /api/v1/restores | 创建恢复流程 |

健康检查不得返回 Key、路径和用户正文。

## 18. 文件导入 API

### 18.1 创建导入

~~~text
POST /api/v1/file-imports
Content-Type: multipart/form-data
~~~

字段：

- files，1～20；
- folder_id，可选；
- tag_ids，可选；
- knowledge_base_id，可选；
- idempotency_key Header。

限制：

- 单文件 50 MB；
- 单次总量 500 MB；
- 只允许 PDF、DOCX、PPTX、TXT、Markdown；
- 后端根据实际内容验证类型；
- 流式写入 staging，不把全部文件读入内存。

返回 202 与 import task。

### 18.2 导入状态

~~~text
GET /api/v1/file-imports/{import_id}
~~~

返回每个文件：

- 原显示名称；
- 上传状态；
- 哈希状态；
- 重复状态；
- file_id，可空；
- task_id；
- error。

### 18.3 重复决策

~~~text
POST /api/v1/file-imports/{import_id}/duplicate-decisions
~~~

每个重复项选择：

- REUSE_EXISTING；
- CREATE_SEPARATE_RECORD；
- SKIP。

决定后任务从 BLOCKED 恢复。

### 18.4 取消

~~~text
POST /api/v1/file-imports/{import_id}/cancel
~~~

取消遵循安全检查点，不删除已成功导入的其他文件。

## 19. Files API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/files | 文件列表、筛选和搜索 |
| GET | /api/v1/files/{file_id} | 文件详情 |
| PATCH | /api/v1/files/{file_id} | 重命名、移动和更新元数据 |
| DELETE | /api/v1/files/{file_id} | 移入回收站 |
| GET | /api/v1/files/{file_id}/content | 安全打开托管文件 |
| GET | /api/v1/files/{file_id}/preview | 预览 |
| GET | /api/v1/files/{file_id}/text | 按位置读取解析正文 |
| GET | /api/v1/files/{file_id}/knowledge-bases | 关联知识库 |
| POST | /api/v1/files/{file_id}/reprocess | 创建重新解析任务 |

content 与 preview：

- 校验 ID；
- 使用数据库解析路径；
- 不接受任意 path 参数；
- 设置 Content-Disposition；
- 设置 X-Content-Type-Options: nosniff；
- 不执行文件内脚本。

## 20. Folder 与 Tag API

### 20.1 Folder

| 方法 | 路径 |
| --- | --- |
| GET | /api/v1/folders |
| POST | /api/v1/folders |
| GET | /api/v1/folders/{folder_id} |
| PATCH | /api/v1/folders/{folder_id} |
| POST | /api/v1/folders/{folder_id}/move |
| DELETE | /api/v1/folders/{folder_id} |

删除非空文件夹需要显式 deletion_strategy。

### 20.2 Tag

| 方法 | 路径 |
| --- | --- |
| GET | /api/v1/tags |
| POST | /api/v1/tags |
| PATCH | /api/v1/tags/{tag_id} |
| DELETE | /api/v1/tags/{tag_id} |
| PUT | /api/v1/files/{file_id}/tags/{tag_id} |
| DELETE | /api/v1/files/{file_id}/tags/{tag_id} |

PUT 关联操作天然幂等。

## 21. Knowledge Base API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/knowledge-bases | 列表 |
| POST | /api/v1/knowledge-bases | 创建 |
| GET | /api/v1/knowledge-bases/{id} | 详情 |
| PATCH | /api/v1/knowledge-bases/{id} | 编辑 |
| DELETE | /api/v1/knowledge-bases/{id} | 移入回收站 |
| GET | /api/v1/knowledge-bases/{id}/files | 文件成员 |
| POST | /api/v1/knowledge-bases/{id}/files | 添加文件 |
| DELETE | /api/v1/knowledge-bases/{id}/files/{file_id} | 移除文件 |
| POST | /api/v1/knowledge-bases/{id}/rebuild | 整库重建 |
| GET | /api/v1/knowledge-bases/{id}/index-status | 索引状态 |
| POST | /api/v1/knowledge-bases/{id}/retrieval-tests | 本地检索测试 |

添加文件返回 202 和父任务；单文件失败不阻断其他项。

retrieval-tests 只返回本地候选和分数，不调用 DeepSeek，适合质量调试。

## 22. Scope API DTO

AI 对话和学习共用 SourceScopeInput：

~~~json
{
  "scope_type": "KNOWLEDGE_BASE",
  "knowledge_base_id": "019...",
  "file_ids": []
}
~~~

约束：

- KNOWLEDGE_BASE 时只允许一个 knowledge_base_id；
- FILES 时 knowledge_base_id 为空，file_ids 为 1～10；
- 不能混合；
- 文件必须已有兼容 RAG 索引；
- 后端创建不可变范围快照；
- 客户端不能提交 index_version 作为可信值。

## 23. Conversation API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/conversations | 会话列表 |
| POST | /api/v1/conversations | 首次发送时创建 |
| GET | /api/v1/conversations/{id} | 会话详情 |
| PATCH | /api/v1/conversations/{id} | 修改标题 |
| DELETE | /api/v1/conversations/{id} | 移入回收站 |
| GET | /api/v1/conversations/{id}/messages | 消息分页 |
| PUT | /api/v1/conversations/{id}/draft | 保存草稿 |
| GET | /api/v1/conversations/{id}/draft | 读取草稿 |
| POST | /api/v1/conversations/{id}/scope-changes | 切换资料范围 |
| POST | /api/v1/conversations/{id}/mode-changes | 切换模式 |

新建空白页面不调用 POST /conversations。第一条消息发送时以单个用例创建 Conversation、Scope 和 Message。

## 24. Chat Message 与 Generation API

### 24.1 发送消息

~~~text
POST /api/v1/conversations/{id}/messages
~~~

请求：

- content；
- client_request_id；
- idempotency key；
- expected conversation version。

返回：

- user_message；
- assistant_message placeholder；
- operation_id；
- events_url。

### 24.2 首条消息

POST /conversations 可以接受：

- mode；
- source_scope；
- first_message；
- client_request_id。

事务创建会话与第一条用户消息，然后创建 AI Operation。

### 24.3 停止

~~~text
POST /api/v1/ai-operations/{operation_id}/cancel
~~~

### 24.4 重新生成

~~~text
POST /api/v1/messages/{assistant_message_id}/regenerations
~~~

返回新 AnswerVersion 对应的 Operation。

### 24.5 编辑历史问题

~~~text
POST /api/v1/messages/{user_message_id}/revisions
~~~

请求包含：

- content；
- confirm_archive_following；
- expected conversation version；
- idempotency key。

后端归档后续路线并启动新 Generation。

### 24.6 继续生成

~~~text
POST /api/v1/messages/{assistant_message_id}/continuations
~~~

无法可靠续写时返回 409 CONTINUATION_NOT_SAFE，并提示重新生成。

## 25. AI Operation API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/ai-operations/{id} | 当前快照 |
| GET | /api/v1/ai-operations/{id}/events | SSE |
| POST | /api/v1/ai-operations/{id}/cancel | 取消 |
| POST | /api/v1/ai-operations/{id}/retry | 安全重试 |

AI Operation 状态：

- QUEUED；
- RUNNING；
- COMPLETED；
- FAILED；
- CANCELLED；
- INTERRUPTED。

AI Operation 不出现在全局任务抽屉。

## 26. Citation API

~~~text
GET /api/v1/citations/{citation_id}
~~~

返回：

- display_number；
- file_id，可空；
- file_name；
- title_path；
- page、slide 或 line；
- excerpt，可空；
- source_status；
- can_open_source；
- file_detail_url，可空。

不得由前端根据模型文字自行解析路径。

## 27. Learning API

### 27.1 会话

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/learning-sessions | 列表 |
| POST | /api/v1/learning-sessions | 创建与准备 |
| GET | /api/v1/learning-sessions/{id} | 详情 |
| POST | /api/v1/learning-sessions/{id}/start | 开始 |
| POST | /api/v1/learning-sessions/{id}/pause | 暂停 |
| POST | /api/v1/learning-sessions/{id}/resume | 继续 |
| POST | /api/v1/learning-sessions/{id}/end | 主动结束 |
| DELETE | /api/v1/learning-sessions/{id} | 移入回收站 |
| GET | /api/v1/learning-sessions/{id}/summary | 总结 |

创建返回 session 与用于生成计划的 AI Operation。

### 27.2 当前题目

~~~text
GET /api/v1/learning-sessions/{id}/current-question
~~~

提交前 DTO 不包含：

- answer_key；
- acceptable_points；
- grading_rule；
- 直接泄露答案的 evidence excerpt。

### 27.3 提示

~~~text
POST /api/v1/learning-questions/{question_id}/hints
~~~

请求包含 hint_level。后端保证按顺序获取，不允许跳过未授权层级直接伪造状态。

### 27.4 提交答案

~~~text
POST /api/v1/learning-questions/{question_id}/attempts
~~~

请求：

- answer_content 或 selected_option；
- client_request_id；
- idempotency key；
- question version。

返回 Attempt 与 Feedback AI Operation。

### 27.5 重试和下一题

| 方法 | 路径 |
| --- | --- |
| POST | /api/v1/learning-questions/{id}/retries |
| POST | /api/v1/learning-questions/{id}/skip |
| POST | /api/v1/learning-sessions/{id}/next-question |
| POST | /api/v1/learning-sessions/{id}/clarifications |

下一题和解释如果需要 AI，返回 AI Operation。

### 27.6 掌握与复习

| 方法 | 路径 |
| --- | --- |
| GET | /api/v1/mastery-records |
| GET | /api/v1/reviews/due |
| POST | /api/v1/review-sessions |
| POST | /api/v1/mastery-records/{id}/mark-unfamiliar |

前端不能直接把状态改为 MASTERED。

## 28. History API

| 方法 | 路径 |
| --- | --- |
| GET | /api/v1/history/conversations |
| GET | /api/v1/history/learning-sessions |

支持：

- q；
- status；
- mode 或 goal_type；
- source_status；
- date_from；
- date_to；
- sort；
- cursor；
- limit。

搜索结果包含 locations：

- message_id；
- question_id；
- attempt_id；
- summary section；
- snippet。

History API 是查询投影，不重复创建原始会话 DTO。

## 29. Global Search API

~~~text
GET /api/v1/search
~~~

参数：

- q；
- types；
- folder_id；
- tag_id；
- date range；
- cursor；
- limit。

返回按类型分组或统一排序的结果：

- FILE；
- KNOWLEDGE_BASE；
- CONVERSATION；
- LEARNING_SESSION。

默认排除回收站。

搜索只查询本地索引，不调用 DeepSeek。

## 30. Task API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/tasks | 列表 |
| GET | /api/v1/tasks/{id} | 详情 |
| GET | /api/v1/tasks/{id}/events | 任务事件 |
| POST | /api/v1/tasks/{id}/cancel | 取消 |
| POST | /api/v1/tasks/{id}/retry | 重试 |
| POST | /api/v1/tasks/{id}/resume | 继续暂停任务 |
| DELETE | /api/v1/tasks/{id} | 清除终态记录 |
| POST | /api/v1/tasks/clear-completed | 清理可清理记录 |

任务动作必须由 Tasks 状态机判断，前端传入目标状态无效。

## 31. Trash API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/trash | 回收站列表 |
| POST | /api/v1/trash/{object_type}/{object_id}/restore | 恢复 |
| DELETE | /api/v1/trash/{object_type}/{object_id} | 永久删除 |
| POST | /api/v1/trash/empty | 清空符合条件项 |

永久删除需要：

- expected_version；
- confirmation_token 或明确确认字段；
- Idempotency-Key。

confirmation_token 只证明用户完成当前操作确认，不是产品决策的二次确认。

## 32. Provider API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | /api/v1/ai/provider-profile | 非秘密配置与状态 |
| PUT | /api/v1/ai/provider-profile | 更新非秘密配置 |
| PUT | /api/v1/ai/provider-profile/api-key | 保存 Key 到安全存储 |
| DELETE | /api/v1/ai/provider-profile/api-key | 删除 Key |
| POST | /api/v1/ai/provider-profile/test | 最小连接测试 |
| GET | /api/v1/ai/provider-profile/capabilities | 能力探测 |
| GET | /api/v1/ai/usage | 本地 Token 用量 |
| PUT | /api/v1/ai/usage-limits | 本地预算 |

GET 不返回 Key、Key 前缀或可用于推断完整 Key 的值，只返回 has_api_key。

## 33. 文件与下载安全

### 33.1 禁止任意路径

API 不提供：

~~~text
GET /files?path=C:\...
~~~

所有文件操作以 file_id、backup_id 或受控 token 为目标。

### 33.2 文件名

- 去除控制字符；
- 不信任 Content-Type；
- 校验文件头；
- 显示名称与磁盘路径分离；
- Content-Disposition 正确转义；
- 不允许覆盖应用代码。

### 33.3 压缩包

备份恢复时防止：

- Zip Slip；
- 绝对路径；
- 父目录跳转；
- 符号链接逃逸；
- 解压炸弹；
- 超出 manifest 的文件。

## 34. Repository 端口

每个模块定义自己的 Repository 接口，例如：

- FileRepository；
- KnowledgeBaseRepository；
- ConversationRepository；
- LearningRepository；
- TaskRepository；
- ProviderProfileRepository。

规则：

- Repository 返回领域对象或专用投影；
- 不向其他模块暴露 ORM Session；
- 不允许 Controller 直接使用 Repository；
- 查询列表使用 Query Object；
- 事务由 UnitOfWork 或应用服务协调；
- 不跨模块直接 JOIN 后写入。

跨模块读模型可以由 History 或 Search 专用 Query Repository 实现。

## 35. 基础设施 Adapter

### 35.1 FileStorageAdapter

- stage；
- commit；
- open_read；
- verify_hash；
- move_to_trash；
- restore；
- purge；
- storage_usage。

### 35.2 DocumentParserAdapter

- supports；
- parse；
- cancel；
- health_check；
- parser_version。

输出统一 TextBlock，不把 PDF、DOCX 或 PPTX 库对象泄露给领域层。

### 35.3 FullTextSearchAdapter

- index；
- delete；
- search；
- rebuild；
- health_check。

### 35.4 VectorStoreAdapter

- create_version；
- upsert；
- search；
- delete；
- activate_version；
- retire_version；
- compact；
- health_check。

### 35.5 ChatProviderAdapter

遵循 10 文档，不暴露 DeepSeek SDK。

### 35.6 EmbeddingAdapter

遵循 10 文档，不暴露 Sentence Transformers 或 ONNX 类型。

### 35.7 RerankerAdapter

支持默认本地算法与未来本地模型实现。

### 35.8 SecretStoreAdapter

- put_secret；
- get_secret；
- delete_secret；
- has_secret；
- health_check。

不得提供“列出全部明文秘密”。

### 35.9 TaskSchedulerAdapter

- enqueue；
- cancel；
- resume；
- retry；
- recover_interrupted；
- get_capacity。

## 36. 应用端口

关键业务端口：

- FilesReadPort；
- FilesCommandPort；
- RetrievalPort；
- CitationPort；
- ChatGenerationPort；
- LearningGenerationPort；
- TaskCommandPort；
- TaskQueryPort；
- TrashPort；
- SearchPort；
- Clock；
- IdGenerator。

端口 DTO 不使用 HTTP Status、Request、Response、ORM 或 SDK 类型。

## 37. 事务与事件

### 37.1 领域事件

示例：

- FileImported；
- FileParsed；
- FileTrashed；
- KnowledgeBaseIndexActivated；
- ConversationUpdated；
- LearningAttemptReviewed；
- ReviewDueChanged；
- TaskStatusChanged。

### 37.2 事务后发布

数据库事务成功后才发布外部可见事件。

失败事务不得发送“已完成”事件。

### 37.3 Outbox

V1 本地应用可以使用 SQLite Outbox 保证：

- 状态提交与事件记录同事务；
- 启动后重放未处理事件；
- 不因应用崩溃丢失索引更新；
- 消费者幂等。

是否使用完整 Outbox 在 15 文档确定；等效的一致性机制是必须的。

## 38. DTO 隐私与最小化

### 38.1 永不返回前端

- API Key；
- Authorization Header；
- storage_relative_path；
- 数据库连接；
- 完整 Provider 原始响应；
- 完整系统 Prompt；
- 模型私有思维链；
- 学习题提交前的答案键；
- 任意内部清理路径。

### 38.2 按需返回

- 引用 excerpt；
- 解析正文；
- 用户答案；
- 错误详情；
- Token 用量。

页面不需要时不随列表批量返回。

## 39. 缓存

### 39.1 HTTP 缓存

包含私人数据的 API 默认：

~~~text
Cache-Control: no-store
~~~

静态前端资源可以使用内容哈希和长期缓存。

### 39.2 ETag

可对只读大资源使用 ETag。修改并发仍以 row_version 契约为准。

### 39.3 Service Worker

V1 不缓存 API 私人数据用于离线 PWA。无网络时由本地后端读取数据库，而不是浏览器持久化复制。

## 40. OpenAPI

### 40.1 权威契约

OpenAPI 3.1 文档必须包含：

- 路径；
- 方法；
- 参数；
- 请求体；
- 响应；
- schema；
- 枚举；
- 错误；
- 分页；
- 幂等要求；
- 示例；
- SSE 事件说明；
- 安全方案。

### 40.2 生成与校验

- CI 验证 OpenAPI；
- 前端类型由 OpenAPI 生成或校验；
- 禁止手写一套与后端不同的枚举；
- 破坏性变更必须升级 API 版本；
- 例子不得包含真实 Key 和用户数据。

### 40.3 SSE

OpenAPI 对 SSE 表达有限时，额外维护事件 schema 文件，但仍从统一类型定义生成。

## 41. API 版本

### 41.1 V1 路径

~~~text
/api/v1
~~~

### 41.2 兼容变更

可以：

- 增加可选字段；
- 增加新端点；
- 增加不影响旧客户端的枚举前提是客户端能容忍 UNKNOWN；
- 放宽限制。

### 41.3 破坏性变更

需要新版本：

- 删除字段；
- 修改字段语义；
- 改变类型；
- 改变默认安全行为；
- 改变状态机；
- 改变错误码含义。

本地前后端通常一起升级，但仍要保持清晰版本，方便迁移与测试。

## 42. Contract Test

### 42.1 API 契约

覆盖：

- 每个路由；
- 成功响应；
- 错误响应；
- 字段校验；
- 分页；
- 幂等；
- row_version 冲突；
- MIME 类型；
- CORS 和 Host；
- 回收站排除；
- 隐私字段。

### 42.2 SSE

覆盖：

- 事件顺序；
- sequence_number；
- 重连；
- Last-Event-ID；
- 心跳；
- 取消；
- 失败终态；
- 部分输出；
- 事件过期后的快照。

### 42.3 Adapter

每个 Adapter 具有共享契约测试：

- 正常路径；
- 空结果；
- 超时；
- 取消；
- 重试；
- 错误映射；
- 版本；
- 资源释放。

这样替换向量库、Embedding Runtime 或 Provider 时不改变业务行为。

## 43. 典型流程

### 43.1 文件加入知识库

~~~mermaid
sequenceDiagram
    participant UI as 前端
    participant API as 本地 API
    participant KB as Knowledge
    participant T as Tasks
    UI->>API: 添加文件
    API->>KB: 校验成员关系
    KB->>T: 创建索引任务
    API-->>UI: 202 与 task_id
    T-->>UI: 全局事件更新
~~~

### 43.2 知识库问答

~~~mermaid
sequenceDiagram
    participant UI as 前端
    participant C as Chat
    participant R as Retrieval
    participant AI as AI
    UI->>C: 发送问题
    C->>R: 混合检索
    R-->>C: 证据
    C->>AI: 创建 Operation
    C-->>UI: operation_id
    AI-->>UI: SSE 文本与终态
~~~

### 43.3 学习点评

~~~mermaid
sequenceDiagram
    participant UI as 前端
    participant L as Learning
    participant AI as AI
    participant DB as UnitOfWork
    UI->>L: 提交 Attempt
    L->>AI: 创建点评 Operation
    AI-->>L: 结构化点评
    L->>DB: 点评与掌握度同事务
    L-->>UI: SSE 完成
~~~

## 44. V1 不做

- GraphQL；
- 公网 API；
- 多用户鉴权；
- OAuth 登录；
- 第三方开放 API；
- WebSocket 作为主流式通道；
- 前端直连 DeepSeek；
- 前端直连 SQLite；
- 前端提交任意文件路径；
- 任意 SQL 查询 API；
- 模块共享同一个超大 Repository；
- 把所有 AI 操作作为后台任务；
- 自动生成工具调用并执行；
- Service Worker 持久缓存私人 API 数据；
- API 返回学习题隐藏答案；
- 公开下载原始日志；
- 无版本的接口变更。

## 45. 验收标准

### API-AC-01

所有业务 API 位于 /api/v1，并具有有效 OpenAPI 3.1 定义。

### API-AC-02

前端只访问本地后端，不直接访问 SQLite、文件系统、向量库和 DeepSeek。

### API-AC-03

本地后端只监听回环地址，生产环境不允许通配 CORS，并验证 Host 和本地会话。

### API-AC-04

成功资源、游标列表、异步任务和 AI Operation 使用本文定义的一致响应形式。

### API-AC-05

错误使用 problem+json 扩展，包含稳定 code、request_id 和 retryable，不包含堆栈、Key、路径和完整 Prompt。

### API-AC-06

文件列表、历史、任务和搜索使用游标分页，单页最大 100。

### API-AC-07

创建和高风险操作支持 Idempotency-Key；同 Key 不同请求返回 409。

### API-AC-08

编辑、移动、删除和恢复使用 row_version 并在冲突时返回 412，不静默覆盖。

### API-AC-09

文件导入支持 1～20 个文件、单文件 50 MB 和单次 500 MB，并在后端验证实际格式。

### API-AC-10

重复文件导入可以阻塞等待 REUSE、CREATE_SEPARATE_RECORD 或 SKIP 决策，不重复上传字节。

### API-AC-11

所有文件读取基于 file_id，不提供任意本地路径读取 API。

### API-AC-12

长文件与索引处理返回 202 与 BackgroundTask，AI 生成返回独立 AI Operation。

### API-AC-13

AI SSE 支持事件序号、心跳、Last-Event-ID、重连和明确终态。

### API-AC-14

前端断开 SSE 不取消生成；只有 cancel 端点可以取消 Operation。

### API-AC-15

编辑历史问题通过专用 revision 用例归档后续消息，不能由前端逐条删除。

### API-AC-16

Learning 当前题 DTO 在提交前不返回参考答案、评分要点和泄露答案的证据。

### API-AC-17

Learning 点评、掌握度和复习更新通过应用服务事务提交，前端不能直接设置 MASTERED。

### API-AC-18

任务取消、重试和恢复由任务状态机判断，前端不能直接修改任务状态。

### API-AC-19

回收站永久删除需要幂等键、版本检查和明确确认，不接受任意路径目标。

### API-AC-20

Provider GET 接口只返回 has_api_key，不返回 Key 或可推断 Key 的内容。

### API-AC-21

ChatProvider、Embedding、Reranker、VectorStore、Parser、SecretStore 和 FileStorage 均通过 Adapter 接口接入。

### API-AC-22

Controller 不直接访问 Repository，其他模块不直接访问目标模块私有 Repository。

### API-AC-23

事务成功后才发布全局事件；应用崩溃后未处理事件可以安全恢复或重建。

### API-AC-24

API 私人响应默认 no-store，前端 Service Worker 不持久缓存用户正文。

### API-AC-25

OpenAPI 类型与前端类型在 CI 中校验，枚举和错误码不存在两套手工定义。

### API-AC-26

Adapter 契约测试覆盖正常、超时、取消、错误映射、版本与资源释放。

## 46. 本部分冻结结论

- V1 使用 /api/v1 REST API；
- 使用 OpenAPI 3.1；
- JSON 字段采用 snake_case；
- 错误使用 problem+json 扩展；
- 列表使用游标分页；
- 创建与高风险操作支持 Idempotency-Key；
- 可编辑资源使用 row_version；
- 文件与索引长任务使用 BackgroundTask；
- 聊天和学习生成使用独立 AI Operation；
- AI 流式输出使用可重连 SSE；
- 前端断开 SSE 不等于取消；
- 全局任务与对象状态可以使用独立事件流；
- 本地后端只监听回环地址；
- 生产环境不使用通配 CORS；
- 前端不直接访问 SQLite、文件系统、向量库和 Provider；
- 文件导入通过 multipart 流式写入；
- 单文件限制 50 MB，单次 20 个、总量 500 MB；
- 文件读取只接受 file_id，不接受任意路径；
- 当前学习题 DTO 不返回隐藏答案；
- History 是查询投影，不拥有原始会话数据；
- Trash 通过各模块删除端口编排；
- Repository 不跨模块暴露；
- Chat、Embedding、Reranker、VectorStore、Parser 和 SecretStore 使用 Adapter；
- API 私人数据默认 no-store；
- OpenAPI、SSE 和 Adapter 都需要契约测试；
- V1 不做 GraphQL、公网 API、多用户登录和 WebSocket 主通道。

## 47. 下一部分

下一步进入 12_非功能与安全要求.md，重点确定：

1. Windows 本地兼容性；
2. 启动、页面、搜索、导入、检索和流式性能指标；
3. 文件数量、数据库、Chunk 和磁盘容量目标；
4. 稳定性、崩溃恢复和数据完整性；
5. 本地 API、文件解析、路径与压缩包安全；
6. Prompt Injection、Provider 和密钥安全；
7. 日志、隐私、数据清理和备份安全；
8. 无障碍、可用性和错误可恢复性；
9. 测试、质量门槛和发布阻断条件。
