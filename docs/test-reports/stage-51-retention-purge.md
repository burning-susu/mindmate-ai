# 第五十一批：历史回收站到期清理与任务记录保留

- 进场：`feat/v1-bootstrap`，本地与 `origin/feat/v1-bootstrap` 均为 `efc8e3b34f1deee3cc7689595d38008fb94aef99`，工作区干净。
- 检查点 A：`9a4b485062cf87d92368d99afe8dc572aa6532d1`，`实现：历史回收站到期安全清理`。
- 检查点 B：`018135cd62442190b01fa18126742db6691acb20`，`实现：后台任务记录按期限安全清理`。
- 验证限定在 pytest 临时目录与公开合成内容；Mock Provider；未调用真实 DeepSeek；未触碰默认 `%LOCALAPPDATA%\MindMateAI`。

## A. 历史 30 天到期永久清理

| 项 | 结果 | 说明 |
| --- | --- | --- |
| 自动到期资格 | `PASS` | 仅 `deleted_at IS NOT NULL AND purge_after IS NOT NULL AND purge_after <= now`。空 `purge_after`、未满 30 天保留。 |
| 手动永久删除 API | `PASS` | `DELETE .../permanent?confirmed=true`；未确认返回 `PURGE_CONFIRMATION_REQUIRED`。 |
| 手动永久删除 UI | `PENDING` | 本批未加历史页“永久删除”按钮；不把 API 冒充浏览器确认 PASS。 |
| 会话独占子行 | `PASS` | 对话清理 Message/AnswerVersion/Citation/AiOperation/Scope；学习清理 Attempt/Feedback/Question/Plan/Scope。 |
| 共享数据保护 | `PASS` | 不删 File/KB/SourceSnapshot；共享 KnowledgePoint 保留。 |
| 软删→恢复→到期竞态 | `PASS` | 恢复后到期扫描跳过；重复清理幂等。 |
| FTS 清理 | `PASS` | 清理后原 ID 无搜索命中；同内容其他会话仍可命中；`quick_check=ok`。 |
| 列表不触发整库清理 | `PASS` | 读历史/回收站不执行 purge。 |
| 维护入口 | `PASS` | Worker（非 test 环境）+ `GET/POST /history/trash/purge-preview|purge-expired`。关闭应用即停止 Worker。 |
| 浏览器删除确认 UI | `PENDING` | 沿用第 50 批：安全检查可阻止确认点击；本批未强行宣称 UI PASS。 |
| 多题定位 | `PARTIAL` | 仍按第 50 批，本批未修。 |

定向测试：`tests/test_stage8_history_purge.py` 5 passed；回归 `test_stage8_history_query_trash.py` + `test_stage8_history_fulltext.py` 通过。

## B. 任务记录期限清理

| 项 | 结果 | 说明 |
| --- | --- | --- |
| 成功/取消 7 天 | `PASS` | `COMPLETED/SUCCEEDED/CANCELLED` 以 `completed_at` 起算。 |
| 失败类 30 天 | `PASS` | `FAILED/PARTIAL/INTERRUPTED` 以 `completed_at` 起算。 |
| 终态时间 | `PASS` | 不用 `updated_at`；缺 `completed_at` 的终态记录保留并计入 preview。 |
| 活动任务 | `PASS` | `QUEUED/RUNNING/BLOCKED/...` 不清理。 |
| 父子链 / AI Operation | `PASS` | 有 AiOperation、子任务、或活动父任务时 `SKIPPED_REFERENCED`。 |
| 业务无副作用 | `PASS` | 清理后 File/KB/Conversation/Learning 计数不变。 |
| 自动清理 | `PASS` | `TaskRetentionWorker`（非 test）；与手动共用 `purge_expired_tasks`。 |
| 手动清理面板 | `PASS`（自动测试） | 首页任务面板预览数量、确认对话框、禁用空态；Vitest 首页既有用例仍过。 |
| 真实浏览器点击确认 | `PENDING` | 本批未做隔离浏览器走查；不宣称浏览器 UI PASS。 |
| 面板与首页一致 | `PASS` | 清理后 `home/overview.tasks.total_count` 与 purged 对齐。 |

定向测试：`tests/test_stage8_task_retention.py` 3 passed；`test_stage8_home_overview.py` 2 passed。前端 `typecheck` 与 `stage8-home-overview` Vitest 3 passed。

## Demo 与完整 V1

- 求职 Demo：维持第四十二批 `PASS`（旧证据，本批未重跑）。
- 真实 DeepSeek：`PENDING`。
- 完整 V1：阶段 5、6、7、8 仍为 `PARTIAL`。设置、预算、备份/恢复、诊断、任务取消/重试不在本批范围。不能因清理逻辑实现宣告阶段 8 完成。

## 安全跳过 / 未完成

- 历史页手动永久删除 UI：`PENDING`。
- 浏览器侧历史删除确认与任务清理确认点击：`PENDING`（安全检查/时间）。
- 无法证明 ownership 的引用：按跳过并报告（任务侧 `skipped_referenced`）。
- 多题定位：仍 `PARTIAL`。
