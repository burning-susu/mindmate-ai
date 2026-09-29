# 第七十批：阶段 8 宿主浏览器验收与需求追踪收口

- 日期：2026-09-28
- 分支：`feat/v1-bootstrap`
- 进场本地/远端 SHA：`ae4432ea38670fb0dac020c5c488ee4ad9d22102` / `ae4432ea38670fb0dac020c5c488ee4ad9d22102`
- 进场工作区：干净
- 本批真实浏览器：未取得普通 Chrome/Edge；`cua.getState()` 只返回无标签的 Codex In-app Browser，普通应用列表为空

## 结论

| 门禁 | 状态 | 证据范围 |
| --- | --- | --- |
| `STAGE8_FULL_V1` | `PARTIAL` | 普通 Chrome/Edge 页面证据未取得；学习总结、其它阶段 8 遗留项和日志服务不管理外部启动器/runtime stdout/stderr；第七十一批已补任务自动取消与并发下调的代码/自动化证据 |
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
| `HISTORY-AC-04` | `history_search_index.py` 的正文投影、总结字段、`question_id`/`focus=summary` 定位、HistoryPage 结果链接 | `test_stage8_history_fulltext.py` 延续题干/答案/反馈/多题 ID；`test_stage72_learning_summary.py` 覆盖总结关键词命中 `summary` 位置与持久回填 | 本批没有普通 Chrome/Edge 查询页面 | `CODE_PASS / BROWSER_PARTIAL` | 用人工卡搜索总结关键词，核对列表聚合、`?focus=summary`、刷新/重启后同一快照；继续逐题核对真实 `question_id` |
| `HISTORY-AC-05` | 类型/状态/来源/UTC 日期与关键词服务端交集过滤、游标分页 | `test_stage8_history_query_trash.py` | 第 49 批 Chrome 核过关键词 + 类型 + 日期组合，未覆盖所有字段同时组合 | `CODE_PASS / BROWSER_PARTIAL (沿用第 49 批部分组合)` | 在人工卡补齐状态和来源筛选，并确认回收站默认排除 |
| `HISTORY-AC-06` | HistoryPage 完成记录进入 `/learning/session/:id?focus=summary`；会话 API 返回版本化持久总结、题目记录和动态引用状态；未完成仍恢复当前题 | `test_stage8_learning_history.py`、`stage8-history.test.tsx`、`stage8-home-learning.test.tsx`、`test_stage72_learning_summary.py` | 第 49 批有已作答会话局部证据；本批没有普通浏览器完成/刷新/重启页面证据 | `CODE_PASS / BROWSER_PARTIAL` | 人工卡完成 0/1/多题会话，核总结字段、题目记录、刷新/后端重启一致、来源失效/恢复提示；未把 API 证据写成浏览器通过 |
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
| `TASK-AC-05` | Worker 固定并发领取边界：重任务最多 2、Embedding/vector 写最多 1 | 第七十一批 `test_stage71_trash_task_concurrency.py`：默认 `2/1`、持久下调 `1/1`、两个独立进程争抢、真实 Worker 领取；配置 API 与迁移证据见 `docs/test-reports/stage-71-trash-task-concurrency.md` | 没有并发浏览器证据 | `CODE_PASS / BROWSER_PARTIAL` | 普通 Chrome/Edge 设置页或接口走查，记录生效值与排队状态；阶段 8 仍不因代码证据整体通过 |
| `TASK-AC-06` | `/api/v1/tasks/{id}/cancel` 与取消检查点 | `test_tasks_backups.py`、`test_stage5_knowledge_bases.py` | 本批没有排队/运行任务取消和半成品检查 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 合成排队任务立即取消、运行任务在安全点取消，核无半成品发布 |
| `TASK-AC-07` | 阶段 Worker 检查点/幂等重试 | `test_stage5_chunking.py`、`test_stage5_index_activation.py`、`test_stage6_parser_worker.py` | 无本批重试页面证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 重试同一合成任务，核成功步骤与业务产物不重复 |
| `TASK-AC-08` | `parse_worker_service.py` 有界瞬态重试及不可重试错误分类 | `test_stage6_parser_worker.py::test_max_retries_and_non_retryable_failure_are_bounded` | 无本批错误分类页面证据 | `CODE_PASS (沿用) / BROWSER_PARTIAL` | 用失败任务核次数、错误码和不自动重试提示 |
| `TASK-AC-09` | 应用关闭/Worker lease/interruption recovery | `test_tasks_backups.py`、阶段 5/6 Worker tests | 第 69 批只测页面任务抽屉逻辑；未重启普通页面服务 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 人工卡停止/启动隔离 API，核安全检查点和同一任务 ID |
| `TASK-AC-10` | `local_restore.py` 校验、重启切换、回滚；不自动恢复不一致数据 | `test_stage8_backup_restore.py` 坏包/中断/迁移失败回归 | 第 53 批有效备份恢复有 Chrome 证据，本批未重做；不代表迁移失败人工场景 | `CODE_PASS / BROWSER_PARTIAL` | 只继承合法恢复页面证据；失败人工页保持原数据可读并保留恢复点 |
| `TASK-AC-11` | 文件/知识库/首页/抽屉读取同一 `BackgroundTask` 安全投影 | `home_overview.py`、`GlobalTaskDrawer.tsx`、对应前后端测试 | 第 48/50 批有首页局部任务页证据，缺本批跨页对照 | `CODE_PASS (自动化) / BROWSER_PARTIAL` | 同一 task id 在文件、知识库、首页与抽屉对照状态 |
| `TASK-AC-12` | 文件与知识库软删除接口写 `IN_TRASH`；Worker 对失效输入做范围复核 | 第七十一批新增 `cancel_tasks_for_targets()`、任务取消原因/事件、解析取消监视器、索引输入范围复核；阶段 71 专用测试 `7 passed`，详见 `docs/test-reports/stage-71-trash-task-concurrency.md` | 没有回收站页面点击、刷新或 Network 证据 | `CODE_PASS / BROWSER_PARTIAL` | 普通 Chrome/Edge 中核对单文件、递归文件夹、知识库回收站和任务抽屉同一 task 状态；混合批与共享旧索引按报告范围复验 |
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
| 设置-日志 | `GET /api/v1/system/privacy`、`POST /api/v1/system/diagnostics/logs/clear`；仅管理应用白名单结构化诊断事件 | `test_stage67_diagnostic_log_retention.py` 覆盖 30 天/100 MiB、路径/重解析点和清理边界；第 73 批 `test_local_runtime.py`、`test_stage65_diagnostics.py` 与设置交互覆盖终端诱饵不落盘、导出脱敏、取消/Esc/确认/重复/失败 | 仍无普通 Chrome/Edge 点击及 Network 计数 | `CODE_PASS / BROWSER_PARTIAL` | 用第 73 批补充卡亲测日志计数、取消/Esc 零 POST、确认恰一 POST 和诊断导出；未亲测前浏览器项保持 partial |
| 设置-诊断预览/导出 | `GET /api/v1/system/diagnostics/preview`、`.../export` | `test_stage65_diagnostics.py` 覆盖白名单、诱饵泄漏和失败安全 | 本批无预览/取消/JSON 下载、无文件扫描结果 | `CODE_PASS / BROWSER_PARTIAL` | 人工卡核预览和下载，扫描不含测试 Key、正文、绝对路径、Cookie/Token；文件只保留本机 |
| 设置-本地模型 | `/api/v1/embedding-model`、模型安装 Worker | `test_embedding_model_install.py`；第 52 批设置状态契约 | 第 54 批只说明本地模型/学习入口；本批未走模型状态页 | `CODE_PASS (自动化/继承) / BROWSER_PARTIAL` | 普通 Guest profile 核状态、固定来源/许可和无模型时的错误，不触发下载 |
| 设置-DeepSeek/OpenAI 选择 | `/api/v1/ai/provider`、凭据/同意分 Provider 保存 | `test_stage54_openai_provider.py`、`test_stage6_provider_configuration.py`、第 68 批 fixture tests | 第 54 批 Chrome 已核 Mock/DeepSeek/OpenAI 选择、独立同意和刷新后 Mock | `CODE_PASS / BROWSER_PASS (沿用第 54 批选择流程)` | 在线学习生成/反馈部分仍需单独执行下面 fixture 浏览器流程 |
| 设置-周期预算 | `usage_budget.py`、`GET /api/v1/system/ai-usage` | 第 68 批预算/Provider/Chat/RAG 组合 `33 passed`，覆盖两 Provider、UTC 窗口、预算阻断、恢复 | 本批无真实设置页、周期切换或历史窗口操作 | `LOCAL_BUDGET_RECONCILIATION=PASS / BROWSER_PARTIAL` | 人工卡核当前周期和历史窗口；官方账单核对仍 `PENDING`，本地估算不等同账单 |
| 设置-备份/恢复 | `backup_worker.py`、Settings 备份页、恢复 UI | `test_stage66_backup_worker.py`、`test_stage8_backup_restore.py` | 创建/下载继承第 66 批；完整恢复 UI 继承第 53 批 | `PASS (继承)` | 不重复已充分验收部分；仅坏包手动流程仍列为 `AC-BACKUP-003 BROWSER_PARTIAL` |
| 设置-存储迁移 | Settings 没有现有数据目录搬迁 API/操作；`09_数据模型与本地存储.md` §5.2 允许安装/首次启动选择目录，并规定改动已有目录属于迁移；`18_最终决策表.md` `DEC-DATA-006` 指 Alembic Schema 前向升级；`16_Codex开发任务书.md` §15.1 只要求设置中的存储，没有阶段 8 数据目录迁移验收 | 第 73 批核对需求原文、最终决策、API 与页面；无数据目录搬迁实现 | 无浏览器可操作项 | `NOT_IMPLEMENTED (现有数据目录搬迁未定义为阶段 8 验收；留作发布规划)` | 保持不可用；不要把 Alembic Schema 升级称为数据目录搬迁 |
| 业务回收站到期清理 | `history_purge.py`、`history_purge_worker.py`、purge preview/run APIs | `test_stage8_history_purge.py`、第 51 批 30 天边界及共享来源用例 | 无普通浏览器到期预览/清理及对象仍在页面对照 | `CODE_PASS / BROWSER_PARTIAL` | 用隔离合成对话/学习记录修改测试时间，核未满 30 天不删、到期删除且来源保留 |
| 任务记录保留清理 | `task_retention.py`、`task_retention_worker.py`、Home 任务面板 | `test_stage8_task_retention.py` 7/30 天、引用保护和计数一致 | 无普通浏览器确认词、取消、清理后页面计数 | `CODE_PASS / BROWSER_PARTIAL` | 在普通浏览器单独核 preview/取消/确认及业务对象仍存在 |
| 恢复后回到 Mock/重新确认两家 | `local_restore.py` Provider restore guard；设置页确认提示 | `test_stage8_backup_restore.py` 恢复阻断外发；第 53 批恢复测试 | 第 53 批 Chrome 重启后显示 Mock、同意清空、0 在线请求 | `PASS (继承第 53 批页面证据)` | 不重复真实服务测试；用户后续操作仍需分别确认 Provider |
| test-only 在线学习页面 | `stage56_online_browser_server.py`、`LearningProviderFixture`、`MockTransport` | `test_stage56_provider_fixture.py`、`test_stage55_learning_provider.py`、第 68 批 `33 passed` | 没有页面选择两 Provider、费用确认、出题/点评、刷新恢复和 calls 计数 | `CODE_PASS / BROWSER_PARTIAL` | 按人工卡两家各完成一题/点评；无同意/无 Key/预算阻断需 0 次；fixture 故障不得切换 Provider |

## 未完成项与阶段判定

以下状态按第七十四批证据校准；矩阵中的 `CODE_PASS` 不代替浏览器证据。

| 门禁 | 当前状态 | 证据与下步 |
| --- | --- | --- |
| `DEMO_STABLE` | `PASS（沿用第42/64批；本批未实测）` | 普通浏览器中按第七十四批手测卡重新走主链路 |
| `HISTORY-AC-04` | `CODE_PASS / BROWSER_PARTIAL` | 第72批总结搜索与定位自动化沿用；补普通浏览器搜索、`question_id` 与 Network 证据 |
| `HISTORY-AC-06` | `CODE_PASS / BROWSER_PARTIAL` | 第72批总结持久化和焦点导航自动化沿用；补刷新、后端重启后页面对照 |
| `TASK-AC-05` | `CODE_PASS / BROWSER_PARTIAL` | 第71批并发配置和 Worker 自动化沿用；补设置页生效值与排队状态 |
| `TASK-AC-12` | `CODE_PASS / BROWSER_PARTIAL` | 第71批回收站任务联动自动化沿用；补任务抽屉同一 `task_id` 页面证据 |
| `LOG_RETENTION_BROWSER` | `BROWSER_PARTIAL` | 第73批 `LOG_RETENTION_CODE=PASS` 沿用；设置清理确认和准确 POST 数仍需浏览器验收 |
| `PACKAGED_LAUNCHER` | `PACKAGED_LAUNCHER_PARTIAL` | 没有可运行打包启动器；不能据应用结构化日志自动清理推断宿主 stdout/stderr 或打包日志通过 |
| `AC-LEARN-006` | `PARTIAL` | 持久学习总结已具备代码证据；`1/3/7/14/30` 天复习计划未实现 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 未使用真实凭据或真实服务 |
| `PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未使用官方账单或用量接口 |
| `STAGE8_FULL_V1` | `PARTIAL` | 普通浏览器、打包启动器及其它页面/运行门禁仍不完整 |

存储目录搬迁在当前阶段没有验收定义，保持 `NOT_IMPLEMENTED`，不在本批重开范围。第53/66批合法备份创建/恢复页面证据按原范围继承。详细测试计数、失败隔离和浏览器缺口见[第七十四批报告](stage-74-demo-stage8-acceptance.md)。

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

本节原第七十批多窗口 fixture 卡已收敛。当前唯一执行卡见[第七十五批 Windows 浏览器交接卡](stage-70-stage8-browser-acceptance.md#第七十五批-windows-浏览器交接卡)，按六步顺序完成一次 Mock Guest profile 走查并记录 URL、对象 ID、Network 次数和截图路径。上方追踪矩阵保留历史状态；没有新增页面证据的行不更新。

## 第七十五批 Windows 浏览器交接卡

本会话只发现空的 Codex In-app Browser，没有普通 Chrome/Edge 标签页或可绑定 profile。隔离服务已在本机运行：Web `http://127.0.0.1:5196/`，API `http://127.0.0.1:8045/`；打开 Chrome/Edge Guest 时使用预置主库：`http://127.0.0.1:5196/knowledge-bases/01a0ec68-93f2-73a2-bb36-0b653cf9ea66`。Provider 固定 Mock；请勿填 Key、切在线 Provider 或确认付费请求。

如服务已停止，从仓库根目录在普通 Windows PowerShell 用同一隔离根重启。脚本会核对所有权标记、复用固定 ONNX 缓存并验证 Mock；缺模型会停止，不会下载或回退。

```powershell
Set-Location 'C:\Users\15932\Desktop\ai知识学习助手\mindmate-ai'
$dataDir = Join-Path $env:TEMP 'mindmate-ai-stage75-demo-mock-b3978231600c4a3c85f78bc426b9ada3'
& .\scripts\demo.ps1 -DataDir $dataDir -ApiPort 8045 -WebPort 5196 -NoBrowser
```

在 Guest profile 打开上述主库 URL，并在 Network 勾选 Preserve log。按以下顺序完成一次页面走查；截图留在 `%TEMP%\mindmate-ai-stage75-browser-evidence`，不要提交仓库。

| 顺序 | 操作 | 记录 |
| --- | --- | --- |
| 1. 上传和索引 | 文件页上传合成资料 `docs/test-data/stage5-fixed-ready/README.md`，新建知识库并加入该文件，等待索引 `READY` | URL、`file_id`、`knowledge_base_id`、`index_version_id`、导入/索引任务 ID、各请求次数、截图路径 |
| 2. 引用和拒答 | 在预置主库问“API 单次请求超时时间是多少秒？”，核对 `30 秒` 和真实引用；再问“玛雅文明使用几套历法？”，确认资料不足且无引用 | `conversation_id`、`operation_id`、引用文件/行号、零引用结果、请求次数、截图路径 |
| 3. 学习和历史 | 从预置主库开始一题、提交答案、结束会话；在历史按总结关键词定位总结，再用题干/答案/反馈分别核对真实 `question_id` | `learning_session_id`、`question_id`、总结 URL、Network 次数、截图路径 |
| 4. 刷新和重启 | 刷新总结页；在演示终端按 Ctrl+C 后，用同一命令重启，确认同一会话 ID、题目、总结和来源恢复 | 重启前/后 URL 与 ID、Network 次数、截图路径 |
| 5. 设置日志 | 设置页分别取消按钮和 Escape；各应为 0 个清理 POST；再确认一次，应恰为 1 个 POST | 取消/Escape/确认 POST 数、日志状态、截图路径 |
| 6. 历史删除和任务 | 只选本次合成历史记录，确认前取消/Escape/错误词均为 0 个 DELETE，正确确认恰为 1 个 DELETE；核对回收站关联任务 ID 与终态 | 历史/任务 ID、DELETE 次数、任务状态、URL、Network 次数、截图路径 |

回传日期、浏览器及 Guest profile、隔离根、各对象 ID、URL、Network 次数和本机截图目录。页面项在收到真实点击证据前一律保持 `BROWSER_PARTIAL`；用户回传只标注“用户报告的人工复测”，不记为代理亲测。其它追踪矩阵行不因本卡更新。

## 第七十四批自动化增量证据

- 后端全量一次：`335 passed, 9 failed, 1 skipped`。失败名称、隔离复跑、OpenAI 修复后的定向结果见[第七十四批报告](stage-74-demo-stage8-acceptance.md)；全量不记为通过。
- 修复后 `test_stage54_openai_provider.py`：`8 passed`；OpenAI 使用 MockTransport，未连真实服务。
- 前端：`16 files / 79 tests passed`；typecheck、lint、build 通过，Vite 有最大 JS `542.55 kB` 的既有 chunk 警告。
- Ruff、compileall、修复文件定向 Pyright、OpenAPI 生成类型一致性通过；全量 Pyright 有 `59 errors`，已在报告列明。Alembic head 为 `h72a1b2c3d4e5`。

## 第七十四批 Git 交付

- 本批提交包含修复、针对性测试、阶段报告、矩阵校准和两份进度文件；不提交浏览器截图、测试数据库、诊断下载或个人路径。
- 中文提交目的句：`验收：复核演示主链路与阶段八页面门禁`。
- 只推送 `feat/v1-bootstrap` 并核对完整本地/远端 SHA；不修改 `main`、不强推。
