# 16 Codex 开发任务书

## 1. 任务目标

在 `burning-susu/mindmate-ai` 仓库中实现 MindMate AI V1：一个面向个人、在 Windows 本地运行的文件整理、知识库问答和学习陪练助手。

本文件是 Codex 的直接执行入口。开始开发后不要重新讨论已冻结的产品和技术选型；按本文阶段持续实现、测试和提交，直到 V1 发布候选标准满足或出现明确停止条件。

## 2. 权威输入读取顺序

开始前按以下顺序读取：

1. 仓库根目录 `AGENTS.md` 和现有 `README.md`；
2. `00_需求规格总纲.md`；
3. `18_最终决策表.md`；
4. 本文件；
5. `15_技术架构与开发约束.md`；
6. 与当前阶段直接相关的 01–14 文档；
7. 现有代码、测试、配置和 Git 状态。

文档优先级：用户最新明确指令 > 18 最终决策表 > 01–15 专题文档 > 总纲 > 旧提示词或历史阶段文档。

## 3. 开发前仓库审计

只读检查并记录：

- 当前分支、HEAD、远端和工作区状态；
- 未提交/未跟踪文件，视为用户资产，不覆盖、不删除；
- 已存在的前后端技术栈和目录；
- 现有设计资源、环境示例、测试和 CI；
- 是否已有数据库、迁移、API、Provider 或页面；
- 与 15 文档冲突的实现；
- 可复用代码和需要迁移的代码；
- 当前可运行命令及失败证据。

如果仓库为空，按 15 文档创建结构；如果已有代码，优先渐进迁移，不以“重建更方便”为由删除用户实现。

## 4. 不得重新决策的事项

- 单用户、Windows 本地、Web 优先；
- 不购买或部署云服务器；
- 前端 React 19＋TypeScript＋Vite；
- 后端 Python 3.12＋FastAPI；
- SQLite＋WAL＋FTS5；
- sqlite-vec 作为 VectorStoreAdapter 实现；
- DeepSeek API `deepseek-flash`；
- 本地 `BAAI/bge-small-zh-v1.5` ONNX Embedding，512 维；
- 本地规则混合重排，不加神经 Reranker；
- Windows Credential Manager 保存 Key；
- SQLite 持久任务，不用 Redis/Celery；
- PyInstaller one-folder＋Inno Setup；
- 五个一级入口及学习优先；
- 文件复制到托管目录；
- 30 天业务回收站；
- 知识库资料不足严格拒答；
- 不自动切换 Provider 或模型；
- 不提供模型工具执行、命令执行或网页访问。

## 5. 实施原则

1. 先验证最高风险技术，再扩展业务；
2. 每阶段交付一个可运行垂直切片；
3. 先后端领域与契约，再接页面；
4. 所有数据库变化带迁移；
5. 所有 API 变化带 OpenAPI/客户端同步；
6. 所有修复带回归测试；
7. 每阶段运行对应测试并形成独立 Git 提交；
8. 不修改与当前任务无关的用户文件；
9. 不用 TODO 伪装已完成功能；
10. 不调用真实付费 API 进行常规自动化测试。

## 6. 目标目录

采用 15 文档第 5 节目录。若现有仓库使用兼容名称，可保留名称，但必须清楚分离 frontend、backend、packaging、scripts、docs 和测试。

## 7. 阶段 0：建立可重复基线

### 7.1 任务

- 完成仓库审计；
- 补充根目录 README 开发说明；
- 建立 `.editorconfig`、`.gitignore` 和环境示例；
- 建立前端/后端工作区与锁文件；
- 建立统一 PowerShell 脚本和可选 Makefile；
- 建立格式化、lint、typecheck、test 命令；
- 建立最小 CI；
- 确保秘密、数据、模型、日志、备份和产物被忽略。

### 7.2 验收

- 新开发者按 README 可完成 bootstrap；
- 前后端 hello/health 可运行；
- lint、typecheck、test 在干净环境通过；
- Git diff 不包含用户数据或秘密。

### 7.3 建议提交

~~~text
chore: establish reproducible development baseline
~~~

## 8. 阶段 1：高风险技术 Spike

### 8.1 必做验证

1. sqlite-vec 在 Windows/Python 3.12 可安装和加载；
2. 512 维向量可写入、范围过滤、Top-K 查询和删除；
3. ONNX Runtime 加载固定 bge-small-zh-v1.5 模型并产生确定维度；
4. Windows Credential Manager Adapter 可写、读、删测试凭据；
5. FastAPI 随机回环端口＋本地会话校验；
6. Mock Chat Provider 流式输出经 SSE 到 React；
7. PyInstaller one-folder 能包含 sqlite-vec、ONNX Runtime 和前端资源；
8. 干净 Windows 环境能启动打包产物。

### 8.2 交付

- `docs/adr/` 中记录验证结果，不重新写选型论文；
- 自动化或最小集成测试保留在仓库；
- 删除一次性实验垃圾，保留可复用基础设施。

### 8.3 停止条件

若 sqlite-vec 或 ONNX 在 Windows 打包中无法稳定运行，在继续业务开发前报告：复现命令、错误、尝试、影响，以及唯一推荐替代方案。不得私自更换向量引擎或 Embedding。

### 8.4 建议提交

~~~text
chore: validate windows ai and vector runtime
~~~

## 9. 阶段 2：应用骨架与安全本地运行

### 9.1 后端

- 配置与数据目录；
- 日志和敏感字段脱敏；
- SQLAlchemy、SQLite PRAGMA、Alembic；
- `/api/v1/health`、`/ready`、`/version`；
- problem+json 错误、request_id、幂等中间件；
- Host/Origin/CORS/本地会话保护；
- 单实例、异常退出标记和安全关闭。

### 9.2 前端

- AppShell、五个一级导航、辅助入口；
- React Router；
- Query Client、统一 API 客户端和错误映射；
- 设计 Token、基础组件、加载/空/错误状态；
- 设置、任务抽屉和占位路由，但不伪造业务数据。

### 9.3 契约

- 输出 OpenAPI 3.1；
- 生成 TypeScript 客户端/类型；
- 加入规范差异检查。

### 9.4 验收

- 局域网访问失败；
- 非允许 Origin 写请求失败；
- 前端可打开并完成健康检查；
- 刷新任意已注册路由不白屏；
- CI 全绿。

### 9.5 建议提交

~~~text
feat: build secure local application shell
~~~

## 10. 阶段 3：数据模型、任务和备份基础

### 10.1 数据模型

实现 09 文档实体、枚举、外键、索引、时间和 `row_version`。UUIDv7 统一由后端生成。

### 10.2 任务系统

- 持久 BackgroundTask 表；
- lease、阶段、进度、取消、重试、检查点；
- 重任务 2、Embedding 1 的并发限制；
- SSE＋轮询恢复；
- 重启时将运行任务安全恢复为中断/待恢复。

### 10.3 备份框架

- manifest、schema_version、文件哈希；
- 不包含 Credential Manager Key；
- 隔离校验和原子恢复接口；
- 先完成测试级备份恢复，再接 UI。

### 10.4 验收

- 空库迁移和上一版本迁移测试；
- 外键、软删除、乐观并发通过；
- 任务强制结束后状态可恢复；
- 备份还原对象数量和哈希一致。

### 10.5 建议提交

~~~text
feat: add persistent data task and recovery foundation
~~~

## 11. 阶段 4：文件管理垂直切片

### 11.1 后端

- 文件夹、标签、文件 CRUD；
- 5 类文件验证、流式复制、SHA-256 和重复检测；
- 解析器 Adapter 与受限子进程；
- 解析文本、位置、状态和错误；
- 搜索、筛选、排序、游标分页；
- 批量移动/标签/删除；
- 回收站、恢复和永久删除；
- 依赖影响查询。

### 11.2 前端

- 文件列表、目录树、筛选和批量选择；
- 导入对话框、待导入清单、重复处理；
- 任务进度；
- 文件详情、元数据、解析文本与所在知识库；
- 回收站操作。

### 11.3 测试

- 格式/大小/批次边界；
- 同名、同内容、部分成功、幂等；
- 恶意文件名、路径穿越、外链和损坏文件；
- 删除恢复与托管字节清理；
- AC-FILE-* E2E。

### 11.4 建议提交

~~~text
feat: implement secure local file management
~~~

## 12. 阶段 5：知识库、Embedding 与 RAG

### 12.1 后端

- 知识库和成员管理；
- ChunkingConfig、EmbeddingConfig、IndexVersion；
- 固定模型下载、校验、进度和取消；
- ONNX 批量 Embedding；
- FTS5 和 sqlite-vec 索引；
- 增量构建、旧版本可用、原子激活；
- 混合检索、RRF、去重、多样性、阈值；
- 引用定位和来源快照；
- 测试检索接口。

### 12.2 前端

- 知识库列表、新建/编辑、文件选择；
- 详情、成员、索引状态、失败文件；
- 模型下载与索引进度；
- 重试、重建和测试检索；
- 开始对话/学习入口。

### 12.3 测试

- 固定向量和固定资料检索；
- 范围过滤、删除失效、增量更新；
- 构建失败不影响旧索引；
- 10 万 Chunk 性能样本；
- AC-KB-* 和 Recall@10。

### 12.4 建议提交

~~~text
feat: build local knowledge base and hybrid rag
~~~

## 13. 阶段 6：Provider、设置与 AI 对话

### 13.1 Provider

- `ChatProviderPort` 和 DeepSeek httpx Adapter；
- Credential Manager 配置/删除/测试；
- 首次外发同意；
- Token/预算记录；
- 超时、429、5xx、断流与有限重试；
- Mock Provider；
- 版本化 Prompt 和 Schema 校验。

### 13.2 对话

- 普通/知识库模式；
- 新建、列表、草稿、消息、范围快照；
- 每轮 RAG、严格拒答、引用；
- AI Operation、SSE、停止、重试、重新生成；
- 范围切换事件；
- 编辑历史问题并归档后续分支；
- 标题与摘要本地规则降级。

### 13.3 前端

- 对话两栏工作区；
- 模式选择和范围条；
- 安全 Markdown、引用抽屉；
- 输入、草稿、流式、停止和错误恢复；
- 设置页 Key 和预算状态。

### 13.4 测试

- 全部 Provider 错误映射；
- 不自动切换模型；
- 严格拒答和跨范围 0；
- XSS/Prompt Injection；
- AC-CHAT-*、AC-PRIV-*；
- 真实 DeepSeek 仅手动小型冒烟。

### 13.5 建议提交

~~~text
feat: add grounded streaming ai conversations
~~~

## 14. 阶段 7：学习陪练闭环

### 14.1 领域与应用

- 学习目标、计划、会话、步骤、题目、尝试、反馈；
- 讲解→练习→反馈→总结状态机；
- 题型、难度、题量和范围校验；
- 分级提示、重试、手动跳过；
- 自适应难度；
- 掌握度解释性计算；
- 1/3/7/14/30 天复习调度；
- 暂停、恢复、结束和总结；
- 出题/点评严格基于资料和引用。

### 14.2 前端

- 学习首页、今日复习、继续学习；
- 开始学习分步表单；
- 专注会话、讲解、题目、答题、提示、点评；
- 总结和复习计划；
- 历史恢复。

### 14.3 测试

- 状态机每条边；
- 连续正确/错误难度变化；
- 提示和多次尝试不覆盖；
- 暂停/强退恢复无重复计分；
- 资料不足不编题；
- AC-LEARN-* 和学习 AI 评测。

### 14.4 建议提交

~~~text
feat: complete grounded learning coach workflow
~~~

## 15. 阶段 8：首页、历史、设置和完整恢复

### 15.1 任务

- 首页真实统计、继续学习、快捷操作、最近活动；
- 对话/学习统一历史筛选；
- 设置中的存储、日志、模型、Provider、预算、备份；
- 业务对象回收站到期清理；
- 任务记录保留清理；
- 完整备份/恢复 UI；
- 诊断包预览和主动导出；
- 全局错误、离线和部分可用体验。

### 15.2 验收

- AC-GLOBAL-*、AC-HISTORY-*、AC-TASK-*、AC-BACKUP-*；
- 首页数据与数据库一致；
- 备份无 Key；
- 恢复后要求重新配置 Key；
- 日志不含正文和秘密。

### 15.3 建议提交

~~~text
feat: finish local history settings and recovery flows
~~~

## 16. 阶段 9：安全、性能和无障碍加固

### 16.1 安全

执行 12 文档全部安全清单：回环、Origin、DNS rebinding、路径、文件签名、解析隔离、CSP、Markdown、Key、备份、Prompt Injection、依赖和模型哈希。

### 16.2 性能

生成容量数据并测试启动、列表、搜索、RAG、历史和任务。优化必须基于测量，不牺牲数据正确性。

### 16.3 无障碍

键盘走完核心闭环；检查焦点、对比度、缩放、ARIA、减少动画和流式播报。

### 16.4 建议提交

~~~text
fix: harden security performance and accessibility
~~~

## 17. 阶段 10：Windows 安装包与发布候选

### 17.1 任务

- 构建前端并嵌入后端资源；
- PyInstaller one-folder；
- Inno Setup 当前用户安装包；
- 单实例和快捷方式；
- 默认保留数据卸载；
- 版本、许可证、SBOM、SHA-256；
- 干净 Windows 11 最低/推荐环境测试；
- 升级和迁移测试；
- 运行 13 文档核心 E2E；
- 生成版本说明、测试报告和已知问题。

### 17.2 建议提交

~~~text
build: prepare mindmate ai v1 release candidate
~~~

### 17.3 可选标签

全部门禁通过后由用户决定是否打：

~~~text
v1.0.0-rc.1
~~~

Codex 不自行推送远端或发布 Release，除非用户明确授权。

## 18. 全阶段验收命令

仓库必须提供稳定脚本完成：

~~~text
bootstrap
format-check
lint
typecheck
test-unit
test-integration
test-frontend
test-e2e
test-security
test-ai-eval
build
package-windows
verify-package
~~~

实际命令写入 README 和 CI。若某命令在当前阶段尚未适用，脚本应明确说明而不是假成功。

## 19. Git 提交节点

每完成阶段并通过对应测试后提交。提交前：

1. 查看 `git status`；
2. 确认只包含本阶段相关文件；
3. 运行阶段测试；
4. 检查无秘密、大文件模型和用户数据；
5. 写清晰 Conventional Commit；
6. 记录测试结果。

发现用户已有未提交修改时，不覆盖、不暂存无关文件；只提交 Codex 明确创建或修改的相关文件。未经授权不执行 reset、force push、rebase 共享分支或删除分支。

## 20. 允许自主处理的事项

Codex 可直接决定：

- 变量、函数、组件和测试名称；
- 同一框架内的小型库是否需要，前提是不改变架构且说明依赖；
- 文件拆分与内部私有接口；
- CSS 像素级微调；
- 纯实现型错误码补充；
- 测试夹具、Mock 和构建脚本细节；
- 不影响数据契约的性能优化。

这些事项不向用户发起决策。

## 21. 必须停止询问的条件

仅在以下情况停止：

1. 需求文档互相矛盾且不同选择会改变用户数据或核心体验；
2. 需要删除/覆盖用户未知文件或大范围重写现有实现；
3. sqlite-vec/ONNX/打包 Spike 证明冻结架构不可行；
4. 需要新的外部账号、付费、凭据或发布权限；
5. 发现密钥泄露、任意代码执行或不可逆数据损坏风险；
6. 必须进行破坏性 Git 操作；
7. 需要推送远端、创建发布或修改外部服务。

提问时只提供：阻塞证据、影响、推荐方案和最多两个备选。普通实现困难不是停止条件。

## 22. 完成报告格式

每个阶段完成后报告：

~~~markdown
## 阶段结果
- 完成范围：
- 关键实现：
- 数据/API/Prompt 变更：
- 测试命令与结果：
- Git 提交：
- 未完成或已知问题：
- 下一阶段：
~~~

V1 总完成报告额外列出：安装包、SHA-256、数据迁移版本、AI 评测指标、安全测试、性能结果、已知问题和与 18 决策表的一致性。

## 23. 完成定义

只有同时满足以下条件才可声明 V1 完成：

- 01–14 的 V1 MUST 需求已实现；
- 13 核心 E2E 全通过；
- 12 发布门禁全通过；
- AI/RAG 指标达到阈值；
- Windows 11 安装、升级、卸载、备份恢复通过；
- 无 Blocker/Critical；
- OpenAPI、迁移、README、版本说明和测试报告完整；
- 实现与 18 最终决策表一致；
- 工作区无意外未提交产物。

## 24. 最终执行口令

向 Codex 提供完整文档包后可直接使用：

~~~text
读取 00、18、16，并按 16_Codex开发任务书.md 从仓库审计开始连续开发。
不要重新发起已冻结决策；需要取舍的普通实现细节采用推荐最佳实践。
每个阶段完成后运行测试并建立独立 Git 提交；只有命中停止条件时才询问我。
~~~

## 25. 本部分冻结结论

Codex 按 0–10 阶段执行，先做 Windows 高风险 Spike，再按文件—知识库/RAG—对话—学习的垂直闭环推进。普通实现细节自主完成，冻结决策不重开；未经用户授权不推送远端或发布。

