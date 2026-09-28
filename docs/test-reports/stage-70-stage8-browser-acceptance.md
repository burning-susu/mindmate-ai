# 第七十批：阶段 8 宿主浏览器验收与需求追踪收口

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场本地/远端 SHA：`ae4432ea38670fb0dac020c5c488ee4ad9d22102` / `ae4432ea38670fb0dac020c5c488ee4ad9d22102`
- 进场工作区：干净
- 本批真实浏览器：未取得普通 Chrome/Edge；`cua.getState()` 只返回无标签的 Codex In-app Browser，普通应用列表为空

## 结论

| 门禁 | 状态 | 证据范围 |
| --- | --- | --- |
| `STAGE8_FULL_V1` | `PARTIAL` | 普通 Chrome/Edge 页面证据未取得；学习总结、任务自动取消和并发下调仍有明确缺口；日志服务不管理外部启动器/runtime stdout/stderr |
| `AC-GLOBAL-004` 代码回归 | `CODE_PASS` | 新增知识库与学习会话 404 直达用例；前端全量 `16 files / 78 tests passed` |
| `LOCAL_BUDGET_RECONCILIATION` | `PASS`（沿用第 68 批） | 本地估算、预留、硬停止与 MockTransport 自动化；不代表厂商账单 |
| `PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未取得官方账单或官方用量接口数据 |
| `LEARNING_ONLINE_CODE` | `PASS`（沿用第 68 批） | DeepSeek/OpenAI 固定 Host 的进程内 `httpx.MockTransport` 业务路径 |
| `LEARNING_ONLINE_BROWSER` | `BROWSER_PARTIAL` | 本批无可操作普通浏览器、页面截图或 fixture 调用计数 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 未使用真实 Key、未访问 DeepSeek/OpenAI 服务、未产生费用 |
| 求职 Demo 可用性 | `PASS`（沿用第 42/64 批） | 本批未重跑整条 Demo，不代表完整 V1 验收 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 独立于 Demo 与本批阶段 8 报告 |

浏览器环境按当前证据停止在可用性检查：没有重试第 67–69 批记录的浏览器审批，也没有重跑曾报 `spawn EPERM` 的 Playwright。没有页面会话、URL、截图或 Network 计数；所有无继承页面证据的 UI 项均保留 `BROWSER_PARTIAL`。

## 本批变更

- `frontend/src/test/stage8-global-recovery.test.tsx` 新增两条详情路由回归：知识库与学习会话返回 404 时保留专用说明和返回入口，不改 URL、不发业务写请求。
- `backend/tests/test_stage8_history_fulltext.py` 将迁移断言改为与 `ScriptDirectory` 读取的当前 head 对照，避免固定在已过期的 `d17a5e9c4b20`。
- `backend/tests/test_stage8_backup_restore.py` 在应用生命周期结束后释放测试 Engine，并在故障注入断言失败时包含恢复状态，减少 Windows SQLite 目录句柄竞争并改善诊断。
- 没有修改 Provider、数据库 schema、API 契约或生产恢复逻辑；没有使用真实数据、密钥或外部付费调用。

## 阶段 8 追踪矩阵

状态定义：`CODE_PASS` 表示有代码与自动化证据，不等同浏览器验收；`BROWSER_PARTIAL` 表示本次没有足够的普通宿主浏览器证据；`BROWSER_PASS (沿用)` 只适用于下表明确列出的历史截图/页面操作；`CODE_PARTIAL` 表示验收所需功能或证据缺少一部分。

### 全局与历史

| 需求 | 代码/接口 | 自动化证据 | 浏览器证据 | 状态 | 下一动作 |
| --- | --- | --- | --- | --- | --- |
| `AC-GLOBAL-001` | `frontend/src/App.tsx` 核心入口与路由 | `frontend/src/test/smoke.test.tsx`、前端全量 Vitest | 第 48/49/53/54 批覆盖首页、历史、恢复、设置等局部路由；本批未逐一跨五入口走查 | `CODE_PASS / BROWSER_PARTIAL` | Guest profile 逐点首页、学习、AI 对话、知识库、文件，记录标题和选中状态 |
| `AC-GLOBAL-002` | `backend/src/mindmate/application/home_overview.py`、`frontend/src/pages/HomePage.tsx` | `test_stage8_home_overview.py`、`stage8-home-overview/recent/learning.test.tsx` | 第 48 批核对空态和文件/知识库/对话计数；没有完整活跃学习记录及各类真实任务同屏证据 | `CODE_PASS / BROWSER_PARTIAL` | 用同一合成根建立四类对象及任务，核对数据库计数、最近活动、快捷入口和空/非空状态 |
| `AC-GLOBAL-003` | `frontend/src/components/GlobalTaskDrawer.tsx`、`GET /api/v1/home/overview?task_limit=30` | `stage8-global-recovery.test.tsx` 覆盖跨页任务和支持的取消仅发一次 | 第 69 批未取得普通浏览器截图、刷新/重启同 task id 或 Network 计数 | `CODE_PASS / BROWSER_PARTIAL` | 按人工卡跨 `/files`、`/chat`、`/history`、`/settings` 打开，验证关闭/Esc/焦点、刷新与取消请求次数 |
| `AC-GLOBAL-004` | `KnowledgeBaseDetailPage.tsx`、`LearningSessionPage.tsx`、`FileDetailPage.tsx` | 本批 `stage8-global-recovery.test.tsx` 新增知识库/学习会话 404 用例（5 passed）；`stage7-learning.test.tsx` 已覆盖有效知识库与学习会话详情渲染 | 本批没有实际刷新有效/无效详情页 | `CODE_PASS / BROWSER_PARTIAL` | 用隔离根先刷新有效知识库/学习会话/文件详情，再刷新不存在 UUID，记录恢复和专用返回状态 |
| `AC-HISTORY-001` | `HistoryPage.tsx` 两个标签和来源 query 参数 | `test_stage8_conversation_history.py`、`test_stage8_learning_history.py`、`stage8-history.test.tsx` | 第 49 批已有对话/学习查询与页面恢复片段；本批未重验进入来源对应标签 | `CODE_PASS / BROWSER_PARTIAL` | 从文件/学习/对话入口分别进入历史，记录初始标签与恢复 URL |
| `HISTORY-AC-01` | `/history`、`?tab=learning` | 历史前后端回归覆盖标签数据入口 | 第 49 批有历史页 Chrome 证据，但本批无当前页面截图 | `CODE_PASS / BROWSER_PARTIAL (沿用局部证据)` | 核对两个标签、从对应来源进入后的选中标签及 URL |
| `HISTORY-AC-02` | `conversation_history.py` 列表投影：标题、模式、资料摘要、更新时间、来源状态 | `test_stage8_conversation_history.py` | 第 49 批打开过合成对话，未逐字段保存当前版本截图 | `CODE_PASS / BROWSER_PARTIAL` | 在隔离对话中逐字段记录列表显示与来源失效状态 |
| `HISTORY-AC-03` | `learning_history.py` 主题、状态、题目进度、来源状态投影 | `test_stage8_learning_history.py` | 第 49 批查看过已作答及来源失效会话；本批未复验全部列表字段 | `CODE_PASS / BROWSER_PARTIAL (沿用局部证据)` | 建立未答/已答/完成会话，检查进度、状态、下次复习和来源 |
| `HISTORY-AC-04` | `history_search_index.py` 的正文投影、`question_id` 定位、HistoryPage 结果链接 | `test_stage8_history_fulltext.py` 覆盖对话、题干、已提交答案、公开反馈和多题 ID | 第 59 批未取得多题浏览器证据；本批没有查询页面 | `CODE_PARTIAL / BROWSER_PARTIAL` | 先处理学习总结缺口；随后逐题搜索题干/提交答案/公开反馈并核对 URL 的真实 `question_id` |
| `HISTORY-AC-05` | 类型/状态/来源/UTC 日期与关键词服务端交集过滤、游标分页 | `test_stage8_history_query_trash.py` | 第 49 批 Chrome 核过关键词 + 类型 + 日期组合，未覆盖所有字段同时组合 | `CODE_PASS / BROWSER_PARTIAL (沿用第 49 批部分组合)` | 在人工卡补齐状态和来源筛选，并确认回收站默认排除 |
| `HISTORY-AC-06` | HistoryPage 恢复 `/learning/session/:id`，当前题与已保存反馈由会话读取恢复 | `test_stage8_learning_history.py`、`stage8-history.test.tsx`、`stage8-home-learning.test.tsx` | 第 49 批实际打开过已作答会话；本批没有完成/总结页面证据 | `CODE_PARTIAL / BROWSER_PARTIAL` | 学习总结目前没有可持久化/展示的总结对象；下一批先治理确认其字段与行为，再实现后验收，不能标成本批通过 |
| `HISTORY-AC-07` | `learning_history.py` 来源状态投影，失效时阻止继续提交 | `test_stage8_learning_history.py`、`stage8-home-learning.test.tsx` | 第 49 批看到来源失效说明及未答会话无提交按钮 | `CODE_PASS / BROWSER_PASS (沿用第 49 批该路径证据)` | 无需重复代码；人工卡确认另一类失效来源和返回入口 |
| `HISTORY-AC-08` | `conversation_lifecycle.py`、`learning_sessions.py` 软删除/恢复与 30 天 `purge_after` | `test_stage8_history_query_trash.py`、`test_stage8_conversation_history.py`、`test_stage8_learning_history.py` | 第 49 批核了回收站显示/恢复；移入回收站确认操作当时未取得完整点击证据 | `CODE_PASS / BROWSER_PARTIAL (沿用部分恢复证据)` | 分别走取消、Esc、确认软删除、恢复并核对同一 ID/上下文 |
| `HISTORY-AC-09` | `history_purge.py` 仅清理会话自有行并保留共享来源 | `test_stage8_history_purge.py` 覆盖对话/学习保留文件、知识库、共享点 | 本批未点击永久删除或核 Network DELETE | `CODE_PASS / BROWSER_PARTIAL` | 仅用隔离合成记录做取消/Esc/错误词零请求，再由操作者确认正确词并核一次 DELETE |

### 任务与备份验收

| 需求 | 代码/接口 | 自动化证据 | 浏览器证据 | 状态 | 下一动作 |
| --- | --- | --- | --- | --- | --- |
| `AC-TASK-001` | `tasks.py` 原子任务领取与阶段 5 Worker 并发边界 | 阶段 5 Worker 回归；`test_tasks_backups.py` | 本批无 3 个重任务同时提交页面证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 隔离根提交 3 个任务，记录 2 个重任务/1 个 Embedding 上限与排队状态 |
| `AC-TASK-002` | `BackgroundTask` 重试端点及安全检查点 | `test_stage6_parser_worker.py`、阶段 5 Worker 回归、`test_tasks_backups.py` | 本批没有失败任务重试页面和请求次数 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 对合成失败任务修复夹具后重试，核起始检查点及没有重复副作用 |
| `AC-TASK-003` | 持久任务、租约恢复和 Provider request-stage 恢复 | `test_tasks_backups.py`、`test_stage8_backup_restore.py`、第 68 批预算/恢复组合 | 第 66 批备份刷新可见；未有本批一般任务重启浏览器证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 在普通浏览器服务重启前后记录同一 `task_id`、中断状态和进度；确认不会重发在线请求 |
| `AC-TASK-004` | `task_retention.py` 预览/确认、首页任务数刷新 | `test_stage8_task_retention.py` 7/30 天边界、引用保护、API 和首页一致 | 未在普通浏览器确认词清理任务记录 | `CODE_PASS / BROWSER_PARTIAL` | 用人工卡创建合成终态任务，分别取消清理/确认清理并核业务记录仍存在 |
| `TASK-AC-01` | 文件解析、索引、Embedding 与批量导入持久任务；全局任务抽屉 | `test_stage5_index_preprocessing.py`、`test_stage5_index_activation.py`、`test_tasks_backups.py`、本批前端回归 | 第 69 批只通过 Testing Library，未浏览器跨页面操作 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 建任务后离开发起页、在多个路由核同一 task id |
| `TASK-AC-02` | `GlobalTaskDrawer.tsx` 状态映射与安全摘要 | `test_stage8_global_recovery.test.tsx`、`test_stage8_home_overview.py` | 无普通浏览器任务状态全谱证据 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 覆盖排队、运行、阻塞、失败、部分成功、完成、取消的页面值与转态 |
| `TASK-AC-03` | `home_overview.py` 只对有检查点的运行任务显示百分比 | `test_stage8_home_overview.py`、`stage8-home-overview.test.tsx` | 第 50 批有排队/运行状态历史页面证据；本批未复验新抽屉 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 对已知和未知总量任务分别核阶段、进度和无伪百分比 |
| `TASK-AC-04` | 文件/知识库成员任务逐项结果和部分成功投影 | `test_stage4_files.py`、`test_stage5_knowledge_bases.py` | 本批没有混合成功/失败导入页面 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 合成批次一成功一失败，核父任务数量、失败不回滚成功项 |
| `TASK-AC-05` | Worker 固定并发领取边界：重任务最多 2、Embedding/vector 写最多 1 | 阶段 5 Worker 自动化（本批未重跑） | 没有并发浏览器证据；源码未找到可将并发数下调的设置/API | `CODE_PARTIAL / BROWSER_PARTIAL` | 确认可调低并发的需求实现边界，按变更治理补配置及测试 |
| `TASK-AC-06` | `/api/v1/tasks/{id}/cancel` 与取消检查点 | `test_tasks_backups.py`、`test_stage5_knowledge_bases.py` | 本批没有排队/运行任务取消和半成品检查 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 合成排队任务立即取消、运行任务在安全点取消，核无半成品发布 |
| `TASK-AC-07` | 阶段 Worker 检查点/幂等重试 | `test_stage5_chunking.py`、`test_stage5_index_activation.py`、`test_stage6_parser_worker.py` | 无本批重试页面证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 重试同一合成任务，核成功步骤与业务产物不重复 |
| `TASK-AC-08` | `parse_worker_service.py` 有界瞬态重试及不可重试错误分类 | `test_stage6_parser_worker.py::test_max_retries_and_non_retryable_failure_are_bounded` | 无本批错误分类页面证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 用失败任务核次数、错误码和不自动重试提示 |
| `TASK-AC-09` | 应用关闭/Worker lease/interruption recovery | `test_tasks_backups.py`、阶段 5/6 Worker tests | 第 69 批只测页面任务抽屉逻辑；未重启普通页面服务 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 人工卡停止/启动隔离 API，核安全检查点和同一任务 ID |
| `TASK-AC-10` | `local_restore.py` 校验、重启切换、回滚；不自动恢复不一致数据 | `test_stage8_backup_restore.py` 坏包/中断/迁移失败回归 | 第 53 批有效备份恢复有 Chrome 证据，本批未重做；不代表迁移失败人工场景 | `CODE_PASS / BROWSER_PARTIAL` | 只继承合法恢复页面证据；失败人工页保持原数据可读并保留恢复点 |
| `TASK-AC-11` | 文件/知识库/首页/抽屉读取同一 `BackgroundTask` 安全投影 | `home_overview.py`、`GlobalTaskDrawer.tsx`、对应前后端测试 | 第 48/50 批有首页局部任务页证据，缺本批跨页对照 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 同一 task id 在文件、知识库、首页与抽屉对照状态 |
| `TASK-AC-12` | 文件与知识库软删除接口写 `IN_TRASH`；Worker 对失效输入做范围复核 | `api/files.py`、`api/knowledge_bases.py`、阶段 5 Worker | 删除接口未调用 `cancel_task`；没有回收站后 QUEUED/RUNNING 任务状态的专用回归 | `CODE_PARTIAL / BROWSER_PARTIAL` | 下一批补自动化覆盖“目标进回收站”取消排队任务、运行任务安全停止及共享资源保留 |
| `TASK-AC-13` | `task_retention.py` 成功/取消 7 天、失败类 30 天规则 | `test_stage8_task_retention.py`、第 51 批边界测试 | 无普通浏览器保留期限页面证据 | `CODE_PASS / BROWSER_PARTIAL` | 用隔离的旧时间任务预览并清理，核阈值边界和实际计数 |
| `TASK-AC-14` | retention worker 避免删业务对象和仍引用的父子任务 | `test_stage8_task_retention.py::test_task_retention_skips_references_and_keeps_business_rows` | 无普通浏览器清理后资源对照 | `CODE_PASS / BROWSER_PARTIAL` | 清理后检查文件、知识库、索引、对话、学习记录仍在 |
| `TASK-AC-15` | AI 请求用 `AiOperation`/学习 Provider operation，非后台长任务 | 阶段 6 Chat、`test_stage55_learning_provider.py`、抽屉前端测试 | 第 54 批 Mock 切换有浏览器证据；本批没核 Drawer 排除 AI 操作 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 一次 Mock Chat/出题/点评时核 Drawer 不生成对应长任务 |
| `TASK-AC-16` | `diagnostic_log_retention.py`、diagnostics allowlist、任务错误摘要白名单 | `test_stage8_home_overview.py`、`test_stage65_diagnostics.py`、`test_stage67_diagnostic_log_retention.py` | 无诊断 JSON 页面下载及脱敏扫描 | `CODE_PASS / BROWSER_PARTIAL` | 导出合成诊断 JSON，记录白名单/排除范围并本地脱敏扫描 |
| `AC-BACKUP-001` | `backup_worker.py`、备份 manifest/哈希和下载接口 | `test_stage66_backup_worker.py`、`test_stage8_backup_export.py` | 第 66 批隔离 Windows Chrome 创建、刷新到完成、下载并 SHA-256 对比 | `CODE_PASS / BROWSER_PASS (沿用第 66 批)` | 沿用，不重复跑已验收备份创建；本批没有亲测 |
| `AC-BACKUP-002` | `local_restore.py` 双重确认、整库切换、恢复点、Mock 和重建状态 | `test_stage8_backup_restore.py`、`test_stage8_backup_export.py` | 第 53 批 Chrome 完成预检、确认、重启切换；恢复后 Mock、同意清空且 0 在线操作 | `CODE_PASS / BROWSER_PASS (沿用第 53 批)` | 沿用既有恢复证据；不把本批未执行的页面步骤写成本批亲测 |
| `AC-BACKUP-003` | 归档/manifest/schema/路径/哈希拒绝与失败不覆盖 live root | `test_stage8_backup_export.py`、`test_stage8_backup_restore.py` | 本批无损坏包浏览器操作 | `CODE_PASS / BROWSER_PARTIAL` | 只在隔离根上传合成坏包，核原数据不变和具体脱敏错误 |
| `AC-PRIV-004` | `api/client.ts`、`useNetworkStatus.ts`、Chat/学习离线守卫 | `stage8-global-recovery.test.tsx` 离线拒绝/本地服务不可用组合 | 没有仅断外网而保留 localhost 的实际网络面板证据 | `CODE_PASS / BROWSER_PARTIAL` | 按人工卡停回环 API 验全页阻断；再保持 API 可用，用 fixture 单次 Provider 失败模拟外部不可用，勿用 DevTools Offline 代替 |

### 阶段 8 页面与设置任务

| 任务 | 代码/接口 | 自动化证据 | 浏览器证据 | 状态 | 下一动作 |
| --- | --- | --- | --- | --- | --- |
| 首页统计/最近活动/快捷入口 | `home_overview.py`、HomePage 与对应 APIs | `test_stage8_home_overview.py`、`home-recent/home-shortcuts/home-learning` Vitest | 第 48 批只验证部分数量；没有同屏四类对象、任务摘要及有效学习统计 | `CODE_PASS / BROWSER_PARTIAL` | 人工卡内同根建四类对象，逐项核计数、最近项与导航 |
| 设置-存储状态 | `GET /api/v1/system/storage`、`systemSettings.ts` | `test_stage8_settings_usage_budget.py::test_storage_usage_budget_and_privacy_endpoints`、第 52 批 | 没有本批设置页容量分类/读取失败状态截图 | `CODE_PASS / BROWSER_PARTIAL` | 打开设置页核分类、体积单位与失败不是 0 |
| 设置-日志 | `GET /api/v1/system/privacy`、`POST /api/v1/system/diagnostics/logs/clear` | `test_stage67_diagnostic_log_retention.py`；上次定向 `19 passed, 1 skipped` | 第 67 批浏览器未进入；本批也未清理 | `CODE_PARTIAL / BROWSER_PARTIAL` | 人工卡核 30 天/100 MiB、预览清理范围、取消与确认；外部运行时 stdout/stderr 仍不受本服务控制，整体 `LOG_RETENTION` 不得记 `PASS` |
| 设置-诊断预览/导出 | `GET /api/v1/system/diagnostics/preview`、`.../export` | `test_stage65_diagnostics.py` 覆盖白名单、诱饵泄漏和失败安全 | 本批无预览/取消/JSON 下载、无文件扫描结果 | `CODE_PASS / BROWSER_PARTIAL` | 人工卡核预览和下载，扫描不含测试 Key、正文、绝对路径、Cookie/Token；文件只保留本机 |
| 设置-本地模型 | `/api/v1/embedding-model`、模型安装 Worker | `test_embedding_model_install.py`；第 52 批设置状态契约 | 第 54 批只说明本地模型/学习入口；本批未走模型状态页 | `CODE_PASS (自动化/继承) / BROWSER_PARTIAL` | 普通 Guest profile 核状态、固定来源/许可和无模型时的错误，不触发下载 |
| 设置-DeepSeek/OpenAI 选择 | `/api/v1/ai/provider`、凭据/同意分 Provider 保存 | `test_stage54_openai_provider.py`、`test_stage6_provider_configuration.py`、第 68 批 fixture tests | 第 54 批 Chrome 已核 Mock/DeepSeek/OpenAI 选择、独立同意和刷新后 Mock | `CODE_PASS / BROWSER_PASS (沿用第 54 批选择流程)` | 在线学习生成/反馈部分仍需单独执行下面 fixture 浏览器流程 |
| 设置-周期预算 | `usage_budget.py`、`GET /api/v1/system/ai-usage` | 第 68 批预算/Provider/Chat/RAG 组合 `33 passed`，覆盖两 Provider、UTC 窗口、预算阻断、恢复 | 本批无真实设置页、周期切换或历史窗口操作 | `LOCAL_BUDGET_RECONCILIATION=PASS / BROWSER_PARTIAL` | 人工卡核当前周期和历史窗口；官方账单核对仍 `PENDING`，本地估算不等同账单 |
| 设置-备份/恢复 | `backup_worker.py`、Settings 备份页、恢复 UI | `test_stage66_backup_worker.py`、`test_stage8_backup_restore.py` | 创建/下载继承第 66 批；完整恢复 UI 继承第 53 批 | `PASS (继承)` | 不重复已充分验收部分；仅坏包手动流程仍列为 `AC-BACKUP-003 BROWSER_PARTIAL` |
| 设置-存储迁移 | 当前 Settings 没有可用迁移操作；第 65 批明确仍显示不可用 | 未发现可执行存储迁移代码/测试 | 无浏览器可操作项 | `NOT_IMPLEMENTED (需确认是否属于本阶段已批准范围)` | 不伪造按钮；若 V1 阶段 8 确需迁移，先按变更治理确认范围再实施 |
| 业务回收站到期清理 | `history_purge.py`、`history_purge_worker.py`、purge preview/run APIs | `test_stage8_history_purge.py`、第 51 批 30 天边界及共享来源用例 | 无普通浏览器到期预览/清理及对象仍在页面对照 | `CODE_PASS / BROWSER_PARTIAL` | 用隔离合成对话/学习记录修改测试时间，核未满 30 天不删、到期删除且来源保留 |
| 任务记录保留清理 | `task_retention.py`、`task_retention_worker.py`、Home 任务面板 | `test_stage8_task_retention.py` 7/30 天、引用保护和计数一致 | 无普通浏览器确认词、取消、清理后页面计数 | `CODE_PASS / BROWSER_PARTIAL` | 在普通浏览器单独核 preview/取消/确认及业务对象仍存在 |
| 恢复后回到 Mock/重新确认两家 | `local_restore.py` Provider restore guard；设置页确认提示 | `test_stage8_backup_restore.py` 恢复阻断外发；第 53 批恢复测试 | 第 53 批 Chrome 重启后显示 Mock、同意清空、0 在线请求 | `PASS (继承第 53 批页面证据)` | 不重复真实服务测试；用户后续操作仍需分别确认 Provider |
| test-only 在线学习页面 | `stage56_online_browser_server.py`、`LearningProviderFixture`、`MockTransport` | `test_stage56_provider_fixture.py`、`test_stage55_learning_provider.py`、第 68 批 `33 passed` | 没有页面选择两 Provider、费用确认、出题/点评、刷新恢复和 calls 计数 | `CODE_PASS / BROWSER_PARTIAL` | 按人工卡两家各完成一题/点评；无同意/无 Key/预算阻断需 0 次；fixture 故障不得切换 Provider |

## 未完成项与阶段判定

以下是具体缺口，不用“待优化”代替：

1. 普通 Chrome/Edge 当前不可由本会话操作。全局任务、离线、历史永久删除、多题 `question_id` 定位、设置日志与诊断导出、首页全量统计、任务保留、双 Provider 学习页面均缺本批普通浏览器证据，状态按矩阵保留 `BROWSER_PARTIAL`。
2. 学习会话没有持久化的完成总结对象，也没有完成总结展示/全文检索路径；对应 `HISTORY-AC-04`、`HISTORY-AC-06` 为 `CODE_PARTIAL`。下一批先按变更治理明确总结字段和业务口径。
3. 文件和知识库软删除接口不调用 `cancel_task`；`TASK-AC-12` 尚无回收站后任务取消/安全停机专用回归。下一批需要以排队任务、运行任务和共享资源建立后端测试，再实现已批准语义。
4. `TASK-AC-05` 的固定并发边界有既有 Worker 证据，但源码没有找到“用户可配置下调”入口；此子项保留 `CODE_PARTIAL`。
5. 应用自有白名单诊断事件有 30 天/100 MiB 清理；外部启动器和 Python/Uvicorn stdout/stderr 不受该服务控制，所以整体 `LOG_RETENTION` 仍 `PARTIAL`。

`PROVIDER_BILLING_RECONCILIATION` 与 `REAL_PROVIDER_SMOKE` 单独保持 `PENDING`，不被本地预算测试或 MockTransport 覆盖。第 53/66 批的备份创建、恢复与恢复后 Mock 页面证据按原范围继承，不算成本批亲测。求职 Demo 可用性继续单独沿用 `PASS`，完整 V1 阶段 5–8 不因此通过。

## 自动化验证

| 门禁 | 本批亲跑命令/范围 | 结果 |
| --- | --- | --- |
| 前端全量 Vitest | `npm.cmd run test -- --run` | `16 files / 78 tests passed` |
| 404 路由回归 | `npm.cmd run test -- --run src/test/stage8-global-recovery.test.tsx` | `1 file / 5 tests passed` |
| 前端 TypeScript | `npm.cmd run typecheck` | 通过；OpenAPI 类型生成后再次通过 |
| 前端 lint | `npm.cmd run lint` | 通过 |
| 前端构建 | `npm.cmd run build` | 通过；既有 Vite chunk 警告，最大 JS `538.70 kB` |
| 阶段 8 后端组合初跑 | 16 个阶段 8/65/66/67/56/任务测试文件，仓库内隔离 basetemp | `74 passed, 1 skipped, 3 failed`；包含已修正的旧 head 断言、Windows 恢复交换时序及已知 FTS5 checksum 波动，不能记作全组通过 |
| 隔离重跑 | `test_stage8_backup_restore.py` 整文件 | 修正后 `6 passed` |
| 隔离重跑 | `test_history_projection_migration_is_reversible` | 修正后 `1 passed`，现对照 Alembic 当前 head |
| 隔离重跑 | `test_learning_purge_removes_owned_rows_keeps_shared_point` | `1 passed`；组合运行曾遇到 FTS5 checksum mismatch，本次单项通过 |
| 隔离重跑 | `test_locked_database_and_interrupted_switch_keep_original` | 通过；曾在组合运行中触发 Windows 目录句柄时序，报告保留该组合不稳定事实 |
| Ruff | `ruff check src tests scripts` | 通过 |
| 定向 Pyright | `pyright src/mindmate/application/local_restore.py tests/test_stage8_history_fulltext.py` | `0 errors, 0 warnings, 0 informations`；`test_stage8_backup_restore.py` 全文件检查仍有 TestClient 动态 `app.state` 与 `zipfile.crc32` 类型错误，本批未扩大修复范围 |
| OpenAPI / 生成类型 | `& '.\backend\.venv\Scripts\python.exe' scripts\export_openapi.py`；`npm.cmd run api:generate` | OpenAPI 3.1.0；`111 schemas / 120 operations`；生成类型完成且无契约变更 |
| Diff | `git diff --check` | 通过 |

后端 pytest 的默认 `%TEMP%` 根在本环境曾不可枚举；本批使用 `backend/build/stage70-*` 隔离 basetemp。第 67 批目录 junction 用例仍因当前环境无法创建 junction 而跳过。前端构建产物、pytest 数据均位于忽略目录，没有加入交付清单。

## Windows Chrome 人工验收卡（可打印）

本批未取得普通浏览器证据。由操作者在普通 Windows VS Code PowerShell 使用 Guest Chrome 完成后填写本卡；不要使用默认 MindMate 数据根。仅使用下列临时根、固定测试资料和 Mock/fixture，禁止真实 Key、真实 Provider 请求或上传诊断包。

```powershell
# 终端 A：仓库根目录，Mock Demo 独立数据根
$mockData = Join-Path $env:TEMP 'mindmate-ai-stage70-host-mock'
& '.\scripts\demo.ps1' -DataDir $mockData -ApiPort 8030 -WebPort 5190

# 另开终端 A：仓库根目录，test-only Provider fixture API
$fixtureData = Join-Path $env:TEMP 'mindmate-ai-stage70-provider-fixture'
Set-Location '.\backend'
& '.\.venv\Scripts\python.exe' -u '.\tests\stage56_online_browser_server.py' `
  --data-dir $fixtureData --api-port 8031 --web-port 5191

# 终端 B：仓库根目录，匹配的 fixture 前端
Set-Location '.\frontend'
npm.cmd run dev -- --host 127.0.0.1 --port 5191 --strictPort
```

在 **Chrome Guest** 打开 `http://127.0.0.1:5190/`。Provider fixture 另开 Guest 窗口打开 `http://127.0.0.1:5191/settings`。日志、截图与诊断下载留在 `%TEMP%\mindmate-ai-stage70-evidence`，不要提交。fixture 初始调用数应为零；摘要端点为 `http://127.0.0.1:8031/api/v1/testing/provider-fixture/calls`，仅返回 Provider、固定 Host、模型、请求类别和授权头是否存在。若需模拟外部 Provider 不可用，在 fixture 页面同源 DevTools Console 执行一次 `fetch('/api/v1/testing/provider-fixture/fail-next-question',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':crypto.randomUUID()},body:JSON.stringify({provider:'DEEPSEEK'})})`；这只安排 MockTransport 失败，不访问服务商网络。

| 操作 | 预期 | 实际/证据填写 |
| --- | --- | --- |
| 依次打开五个核心入口；首页建立文件、知识库、对话、学习和任务 | 导航/标题一致；计数和最近活动与合成数据相符 | 日期/浏览器：______；合成 ID：______；截图：______ |
| 在文件、对话、历史、学习、设置打开同一任务抽屉；关闭按钮/Esc；刷新并重启隔离 API | task id/阶段/真实进度一致；关闭不取消；焦点回归；重启后同一记录恢复 | task id：______；取消 POST 次数：______；Network 截图：______ |
| 停止本卡 API 后刷新，再启动并点“重新连接” | 全页本地服务阻断；重连后原 URL 恢复 | 阻断结果：______；恢复结果：______；截图：______ |
| API 保持可用时调用 fixture `/api/v1/testing/provider-fixture/fail-next-question` 安排某一 Provider 失败 | 本地文件/历史可读；在线操作失败且不切换/不自动重发；calls 与单次请求对应 | Provider：______；失败前后 calls：______；截图：______ |
| 设置页检查日志期限/体积，先取消再确认合成日志清理；预览诊断并下载 JSON | `30 天 / 100 MiB` 可见；取消不发请求；清理不删文件/备份；JSON 只含白名单且无 Key/正文/绝对路径/Token | DELETE/POST 次数：______；下载文件脱敏结果：______；证据路径：______ |
| 对话和学习历史分别组合关键词/类型/状态/日期/来源；打开原上下文；测试软删除恢复 | 条件交集正确；上下文不重生成；恢复同一 ID；确认前取消/Esc/错误词均零 DELETE | 结果：______；会话 ID：______；截图：______ |
| 仅对隔离回收站记录输入正确永久删除确认词；逐题搜索三题题干/已提交答案/公开反馈 | 正确确认仅一条 DELETE；文件/知识库/其他会话仍在；每条链接用真实 `question_id` 定位；私有答案键/说明不命中 | DELETE 次数：______；question_id：______；共享资源核对：______ |
| fixture Settings 分别选择 DeepSeek/OpenAI，各确认后完成一次出题和点评，刷新读取 | Host 分别固定 `api.deepseek.com` / `api.openai.com`；每次费用分别确认；无同意/Key/预算时 calls 为 0；fixture 失败不回退 | DEEPSEEK calls：______；OPENAI calls：______；费用确认截图：______ |
| 刷新有效知识库/学习会话/文件详情，再刷新不存在 UUID | 有效详情恢复；不存在资源显示专用状态和返回入口，无白屏或业务写入 | URL/ID：______；实际文案：______；Network/截图：______ |

实际执行人：______　日期：______　完整证据目录：______　未通过项与复现步骤：______

只有页面真实点击、刷新、Network 次数和本地截图/调用摘要齐全时，相关矩阵行才能改为浏览器 `PASS`。只有口头报告时标注“用户报告的人工复测”，不可写成代理亲测。备份创建/下载与有效恢复沿用第 66/53 批证据，不需重复跑。

## Git 交付

- 只提交本批 3 个回归测试文件、本报告及两份进度文档。
- 提交信息使用中文目的句：`验收：补齐阶段八需求追踪与路由回归`。
- 本报告不把旧第 69 批“未推送”文字当作当前事实；本批起始远端 SHA 以实际进场 `git ls-remote` 结果为准。
- 最终本地/远端完整 SHA、推送结果与分支由本批交付说明给出；不修改 `main`，不强推。
