# 第五十九批：历史永久删除、多题定位与文件详情状态

日期：2026-09-27。开发分支：`feat/v1-bootstrap`。进场本地与远端 SHA：`82cb14dd4e0b440d05c1c3c5fe7dab5b06d79d81`。本报告记录本批代码、自动化证据和环境限制，不把附件提示词中的历史叙述伪造成当前用户消息。

## 范围与结论

本批只执行附件提示词中已经明确的三个收口点：

- 历史回收站中对话和学习记录的永久删除确认闭环；
- 1～5 题学习历史的题目级命中和反馈定位回归；
- 文件详情关联知识库状态显示缺陷。

阶段 7/8 的完整 V1 仍为 `PARTIAL`。独立备份 Worker、费用账单对账、真实 Provider、人工浏览器点击等其他未完成项没有因为本批自动测试通过而改变状态。

| 项目 | 本批状态 | 证据口径 |
| --- | --- | --- |
| `HISTORY_PURGE_UI` | `PASS`（代码/自动测） | 对话和学习回收站都要求输入“永久删除”，只用条目 `row_version` 发请求；取消、Escape、关闭和重复点击有前端断言。 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 本批没有重新调用第 58 批已记录的浏览器审批/EPERM 工具阻断；没有页面点击或截图。 |
| `LEARNING_MULTIQUESTION_HISTORY` | `PASS`（代码/回归测试） | 新增三题历史投影回归，确认每题的真实 `question_id` 可作为题目/反馈定位标识。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 没有真实页面点击；仍沿用第 56～58 批环境限制。 |
| `FILE_DETAIL_KB_STATUS` | `PASS`（契约/前端测试） | 关联知识库响应显式返回生成类型 `status`，页面显示“索引就绪”等状态，不出现 `undefined`。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 没有真实 Key、DeepSeek/OpenAI 请求或付费调用。 |
| `DEMO_REGRESSION_THIS_BATCH` | `PARTIAL` | 本批没有伪造完整浏览器 Demo 通过；第四十二批历史 Demo `PASS` 单独保留。 |

## 实现

### 历史永久删除

- `frontend/src/api/history.ts` 增加 `purgeConversation` 和 `purgeLearningSession`，复用既有 `DELETE /api/v1/conversations/{id}/permanent` 与 `DELETE /api/v1/learning-sessions/{id}/permanent`，发送 `expected_version` 和 `confirmed=true`。
- `HistoryPage.tsx` 只在回收站条目显示“永久删除”，正常历史列表仍保留移入回收站和恢复流程。
- 独立确认框显示对象类别、名称和真实影响，要求确认词精确等于“永久删除”。关闭按钮、取消和 Escape 不调用 API；提交期间按钮禁用，避免重复不可逆请求。
- `404/409/412` 以及网络/未知错误都会先重新读取当前回收站列表，并显示数据已经变化或结果未知；不会使用旧版本自动再次删除。成功后失效历史、回收站、首页摘要和最近记录查询。
- 服务端永久删除 API、owned-row 清理、共享文件/知识库保留和 FTS 清理逻辑沿用第五十一批既有实现，没有新增第二套删除 API。

### 多题历史定位

- 现有 `history_search_index.py` 已为每个题干、已提交答案和已发布反馈保存真实 `question_id`；本批没有建立第二套索引。
- 新增回归使用三道合成事实逐题生成、提交和搜索，检查三次命中的 `record_id` 分别对应三道题，并覆盖题目/反馈定位所需的章节。
- 未提交答案键、正确选项、私有证据摘录和未发布解释仍不会进入投影；既有单题泄露防护用例保持不变。
- 前端已有 `?question=<id>` 与 `?question=<id>&focus=feedback` 恢复逻辑，本批回归确认其输入仍来自真实题目 ID。

### 文件详情状态契约

- `GET /api/v1/files/{file_id}/knowledge-bases` 增加 `FileKnowledgeBaseResponse` / `FileKnowledgeBaseListResponse` 响应模型，返回知识库 `status` 和关系 `membership_status`。
- `docs/openapi/openapi.json` 与 `frontend/src/api/generated/openapi.ts` 同步到 `110 schemas / 116 operations`。
- `FileDetailPage.tsx` 改用生成的 `FileKnowledgeBaseResponse`，将 `EMPTY/PREPARING/READY/PARTIAL/FAILED/NEEDS_REBUILD/IN_TRASH` 转成可读状态；空列表、加载失败和未知状态不会拼出 `undefined`。

## 自动化验证

前端已执行：

- `npm.cmd run test`：`15 files passed, 66 tests passed`；
- `npm.cmd run typecheck`：通过；
- `npm.cmd run lint`：通过；
- `npm.cmd run build`：通过，保留既有主 JS 超过 500 kB 的 Vite warning；
- `git diff --check`：通过；
- OpenAPI JSON 解析、响应 `$ref` 和生成类型检查：通过。

后端已执行：

- `.venv\Scripts\ruff.exe check src\mindmate\api\files.py tests\test_stage8_history_purge.py tests\test_stage8_history_fulltext.py`：`All checks passed!`；
- bundled Python `compileall`：通过；
- 后端 pytest 目标：未能启动。仓库 `backend/.venv/Scripts/pytest.exe` 绑定 `C:\Users\15932\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe`，当前沙箱创建该解释器返回 `Unable to create process`。因此本批记为 `BACKEND_PYTEST=BLOCKED`，没有把 Ruff/compileall 当成 pytest 通过，也没有改 ACL、提权或替换生产 Provider。

新增后端用例仍应在可运行的 Windows Python 3.12 环境中执行：

- `test_manual_learning_permanent_delete_requires_confirmation_and_keeps_sources`；
- `test_multistep_learning_search_keeps_each_question_location`。

它们使用隔离 `tmp_path`、合成会话和现有 Mock/fixture，不读取个人历史或真实凭据。

## 浏览器与手工交接

本批没有重试第 58 批已经记录的 Chromium `spawn EPERM` 和 Codex 浏览器审批服务 `404`。没有截图、页面点击或伪造浏览器 PASS，因此：

- `HISTORY_PURGE_BROWSER=PARTIAL`；
- `LEARNING_ONLINE_BROWSER=PARTIAL`；
- `DEMO_REGRESSION_THIS_BATCH=PARTIAL`。

具备普通 Windows 浏览器环境后，应使用新的隔离数据根，创建一条合成对话和一条 3 题 Mock 学习记录：进入历史回收站，分别取消、Escape、输入错误确认词和正确确认词，核对只产生一次 DELETE；随后搜索三道题的题干、已提交选项与反馈并点击每个定位链接。不要使用个人默认库，不要输入真实 Key。

## Git 交接

本报告编写时工作区包含本批代码、测试、OpenAPI、生成类型和进度文档改动，状态为 `UNCOMMITTED / NOT_PUSHED`。本批执行 `git add` 时创建 `.git/index.lock` 返回 `Permission denied`；没有改 ACL、提权、替代 Git 目录或重复请求审批服务。提交前必须逐文件审阅并排除隔离数据库、日志、截图、Key 和构建产物；提交信息使用中文目的式一句话，例如：`完善：补齐历史永久删除与多题定位`。推送前核对本地 HEAD、`origin/feat/v1-bootstrap` 和 `git ls-remote` 完整 SHA；不改 `main`、不强推。

待环境恢复后的 VS Code 交接清单：

1. 在源代码管理面板逐文件确认本批 14 个文件，无隔离库、日志、截图、Key 或构建产物。
2. 暂存本批文件，确认暂存 diff 与 `git diff --check` 通过。
3. 使用中文提交信息 `完善：补齐历史永久删除与多题定位`，核对本地提交完整 SHA。
4. 推送 `feat/v1-bootstrap`，再执行 `git ls-remote --heads origin feat/v1-bootstrap`，把本地和远端完整 SHA 记录回本报告与进度文档。

