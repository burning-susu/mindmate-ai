# 第七十二批：阶段 8 学习总结与历史检索闭环

- 日期：2026-09-29
- 分支：`feat/v1-bootstrap`
- 进场本地 SHA：`3310a762d6d24f92f8ec7f2d13c2894e1f4e2439`
- 进场远端 `origin/feat/v1-bootstrap`：`3310a762d6d24f92f8ec7f2d13c2894e1f4e2439`
- 进场工作区：干净
- 本批真实浏览器：未取得普通 Chrome/Edge；未产生页面 URL、截图或 Network 计数

## 结论

| 门禁 | 状态 | 证据范围 |
| --- | --- | --- |
| `HISTORY-AC-04` | `CODE_PASS / BROWSER_PARTIAL` | 学习总结进入本地历史 FTS 投影，命中位置为 `summary`；题目/答案/反馈定位保持原有 `question_id`；没有普通浏览器页面证据 |
| `HISTORY-AC-06` | `CODE_PASS / BROWSER_PARTIAL` | 完成会话返回持久总结并从历史进入 `?focus=summary`；未完成会话仍读取当前题；没有普通浏览器刷新/重启证据 |
| `AC-LEARN-006` | `PARTIAL` | 完成度、结果计数、知识点、Citation 和下一步快照已持久化；1/3/7/14/30 天复习模型尚未实现，明确返回“未建立复习安排” |
| `STAGE8_FULL_V1` | `PARTIAL` | 本批总结闭环代码通过；普通宿主浏览器、日志 stdout/stderr、官方账单、真实 Provider 等阶段 8 门禁仍按原报告保持未完成 |
| 求职 Demo 可用性 | `PASS`（沿用） | 本批没有重跑完整 Demo；未使用真实 Key、真实 Provider 或私人资料 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 独立于本批，沿用各阶段自身门禁 |

## 字段与事实来源

| 总结字段 | 持久来源 | 当前可信范围 | 展示/搜索方式 |
| --- | --- | --- | --- |
| 主题、目标、目标类型 | `learning_sessions` | 用户提交的本地会话配置 | 总结标题、历史主题/目标投影 |
| 资料范围 | `learning_scopes`、`learning_scope_files`、知识库/文件当前状态 | 会话创建时的范围快照；文件回收站状态动态读取 | 总结显示知识库、文件名和来源状态 |
| 开始/结束时间、结束原因 | `learning_sessions.created_at/started_at/completed_at/end_reason` | 仅本地状态变更事实 | 总结元信息、历史记录 |
| 计划/完成数 | `target_question_count`、持久 `LearningQuestion`/`LearningAttempt` | 已保存题目和尝试数量；不补造缺失题目 | 总结统计；历史保留原进度 |
| 正确/部分正确/错误/跳过/无法判定/未作答 | `LearningFeedback.result`、`LearningAttempt.status`、题目数 | 只按已保存反馈和尝试计算；不把无反馈说成正确 | 总结统计，安全空态 |
| 提示/重试 | `LearningAttempt.hint_level_used/attempt_number` | 没有记录就返回 0，不推测历史提示 | 总结统计 |
| 可确认知识点 | `LearningQuestion.knowledge_point_id` → `KnowledgePoint` | 只展示本次题目覆盖的知识点；状态写成“本次正确/需要复习/暂无反馈”，不宣称长期掌握 | 总结知识点列表、总结搜索文本 |
| 关键引用 | 已绑定的真实 `Citation`/`SourceSnapshot` | 只展示真实 Citation；文件失效/回收站时动态标记不可打开 | 总结引用按钮；历史总结文本不写入摘录内部字段 |
| 复习安排/下一步 | 本地规则快照 | 当前没有可靠间隔复习实现，明确为“未建立复习安排” | 总结空态和下一步文案，未伪造日期 |

## 实现

- 新增 `learning_session_summaries` 一对一表和 Alembic revision `h72a1b2c3d4e5`。快照带 `summary_version=1`、稳定生成时间、幂等唯一会话键和 JSON 结构；只由本地数据库事实构建，不调用 Provider。
- 用户主动结束、达到题量自动完成、资料耗尽、资料失效、初始准备失败和在线点评完成路径都会在同一事务边界内生成快照。旧 `COMPLETED/FAILED/SOURCE_INVALID` 会话首次读取时按相同规则本地回填，不产生 AI Operation 或外发请求。
- 学习 API 的 `LearningSessionResponse` 新增结构化 `summary`；旧 `result` DTO 保持原字段形状，完整新统计放入总结，避免破坏已有客户端精确响应断言。
- 历史全文投影加入公开总结文本、下一步和知识点标题；命中定位使用 `section=summary`，前端跳转 `/learning/session/:id?focus=summary`。隐藏答案键、Prompt、路径、Key、错误堆栈不进入总结或投影。
- 总结引用通过已有 `Citation` 重新读取当前来源状态；回收站/失效来源仍可阅读历史总结，但显示不可打开。永久删除学习会话时同步删除自有总结和历史投影，文件、知识库和共享索引不受影响。
- 学习历史完成项显示“查看总结”；未完成项继续打开当前会话。总结区域支持 `tabIndex=-1`、焦点/滚动定位、题目记录和引用空态。
- `docs/openapi/openapi.json` 与 `frontend/src/api/generated/openapi.ts` 已重新生成。

## 自动化验证

- `backend/.venv/Scripts/python.exe -m pytest tests/test_stage72_learning_summary.py -q --basetemp <项目可写隔离目录>`：3 项通过。覆盖自动完成 1 题、主动结束 0 题、旧总结删除后的确定性回填、总结关键词历史命中、Citation 来源失效、软删除/恢复/永久删除和总结清理。
- `uv run --no-cache pytest tests/test_stage7_learning_session.py tests/test_stage8_learning_history.py tests/test_stage8_history_fulltext.py -q --basetemp <项目可写隔离目录>`：定向阶段 7/8 回归通过。
- `uv run --no-cache pytest tests/test_stage57_learning_multistep.py tests/test_stage72_learning_summary.py tests/test_stage4_migration.py -q --basetemp <项目可写隔离目录>`：多题、总结和迁移回归通过。
- `uv run --no-cache ruff check src tests/test_stage72_learning_summary.py tests/test_stage4_migration.py`：通过。
- 定向 Pyright（总结、学习 API、历史索引、学习会话和新测试）：`0 errors`。
- `uv run --no-cache python -m compileall -q src migrations`：通过。
- `npm run api:generate`、`npm run typecheck`、`npm run test -- --run`：前端 `16 files / 78 tests passed`，类型检查通过。
- `npm run lint`、`npm run build`：通过；构建仅保留既有主 JS chunk 大小提示。
- `git diff --check`：通过。
- Alembic 独立空库升级、降级到历史 revision、重新升级和新 head 断言：阶段迁移回归通过；旧会话总结通过本地回填测试。

## 全量集合边界

从仓库根目录显式设置 `PYTHONPATH` 后运行后端全量集合，最终集合包含既有环境/历史失败，不能写成全量通过：

- `test_local_runtime.py`：Windows PowerShell 自测的 `stdout` 为 `None`，与第 71 批已记录的宿主输出问题一致。
- `test_stage54_openai_provider.py`：Mock OpenAI fixture 在全量顺序中返回 `FAILED`，隔离 Provider 测试不属于本批修改范围。
- `test_stage6_provider_configuration.py::test_windows_credential_manager_round_trip`：当前登录会话返回 Windows Credential Manager `WinError 1312`。
- `test_stage8_backup_restore.py`：目录/句柄切换注入在全量组合中未进入第二次交换，属于既有 Windows 句柄时序边界。
- 其余全量失败中，迁移 head 与旧多题精确响应断言已因本批契约变更修正并隔离通过；没有把局部定向通过替代全量通过。

## 浏览器人工复测卡

当前没有普通 Chrome/Edge 页面，状态保留 `BROWSER_PARTIAL`。下一次可用宿主浏览器时，使用同一隔离数据根和合成资料记录：

1. 创建 0 题主动结束、1 题自动完成和 3 题多题会话，记录会话 ID、完成前后题数、结束原因、正确/部分正确/错误/跳过/无法判定、提示/重试、知识点和引用状态。
2. 从 `/history?tab=learning` 打开已完成项，确认列表显示“查看总结”、URL 带 `focus=summary`、总结区域获得焦点，题目记录与总结统计一致。
3. 搜索总结中的合成关键词，确认列表只聚合一个学习对象，命中位置写成“学习总结”，点击后定位总结；再搜索题干/答案/反馈，确认仍指向真实 `question_id`，不退化到第一题。
4. 刷新页面并重启后端，确认同一会话 ID 的总结文本、计数、知识点和引用不变；不出现新的题目、Attempt、AI Operation 或在线请求。
5. 将引用文件移入回收站、恢复，再永久删除学习会话，分别记录历史总结可读、引用不可打开、恢复保留原总结、永久删除只清理会话自有总结/搜索项。

## 交接

- `AC-LEARN-006` 的持久总结部分已具备代码证据；1/3/7/14/30 天复习模型仍是下一阶段 V1 工作，不因本批完成而宣布完整验收。
- 阶段 8 的设置存储迁移、外部 stdout/stderr 日志、官方 Provider 账单、真实 Provider smoke、普通浏览器页面和其它历史浏览器门禁继续按各自报告独立追踪。
- 下一批建议：使用普通 Chrome/Edge 完成上述人工卡，并单独治理 AC-LEARN-006 的复习数据模型；不要把本地总结快照当作长期掌握度或完整复习系统。
