# 第六十一批：阶段 8 演示验收与交接

日期：2026-09-28。分支：`feat/v1-bootstrap`。本批进场本地 HEAD 与远端 `origin/feat/v1-bootstrap` 均为 `0b6fccef85dd83f6773a92dcddc66e004545882d`。

## 结论

| 验收项 | 状态 | 证据口径 |
| --- | --- | --- |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 未在普通 Windows 浏览器操作回收站；无截图、合成记录 ID 或 DELETE 次数。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 未在页面选择 DeepSeek/OpenAI test-only Provider；无费用确认页面或服务端 `calls` 计数。 |
| `DEMO_REGRESSION_THIS_BATCH` | `PARTIAL` | 本批未完成上传、索引 READY、来源问答、Mock 学习、刷新和重启的页面回归。 |
| 求职 Demo 可用性 | `PARTIAL` | 第四十二批 `PASS` 是历史证据；本批没有普通 Windows 页面复验。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 未输入真实凭据、访问官方 Provider 或产生付费调用。 |
| `STAGE7_FULL_V1` / `STAGE8_FULL_V1` | `PARTIAL` | 完整阶段需求仍有既有未完成项；本批宿主证据也未取得。 |
| 产品缺陷 | 未判定 | 未观察页面行为，不能据此认定有缺陷或没有缺陷。 |

历史第四十二批 Demo `PASS` 只保留为该批证据，不代表第六十一批或当前完整阶段验收通过。求职 Demo 的本批浏览器可用性仍待普通 Windows 页面走查确认。

## 本批准备与实际检查

- 已检查 `docs/demo/阶段60宿主验收入口.md`：复用现有 `scripts/demo.ps1`、`scripts/dev.ps1` 和 `backend/tests/stage56_online_browser_server.py`，包含隔离 Mock Demo、test-only Provider、停止方式、页面步骤和脱敏记录模板；未复制启动体系。
- 已检查 `docs/demo/求职Demo三分钟操作.md`：现有操作顺序覆盖合成 TXT 上传、知识库索引 READY、带来源问答、资料不足拒答和一题 Mock 学习。演示过程必须说明没有调用真实 DeepSeek。
- `git ls-remote --heads origin feat/v1-bootstrap`：返回 `0b6fccef85dd83f6773a92dcddc66e004545882d`，与本地 HEAD 和跟踪引用一致。第六十批中文提交为 `验收：补跑历史删除测试并建立本机演示入口`。
- `node --version`：`v22.22.2`；`npm --version`：`11.16.0`。
- `Test-Path .\backend\.venv\Scripts\python.exe` 与 `Test-Path .\backend\model-cache\manager-validation`：均为 `True`。
- `& '.\backend\.venv\Scripts\python.exe' --version`：未能启动，输出 `Unable to create process using 'C:\Users\15932\AppData\Roaming\uv\python\cpython-3.12.11-windows-x86_64-none\python.exe' --version`。因此本批没有运行 pytest、Alembic 或需要该 Python 解释器的服务。
- 第六十批 `29 passed`、Vitest `66 passed`、typecheck/lint/build 等均为上一批记录；本批没有重复运行。
- `git diff --check`、提交前 `git diff --cached --check`：通过；本批仅修改验收与进度文档。
- 浏览器检查：`cua.getState()` 返回的浏览器清单只有无标签页的 Codex 内置浏览器。随后 `cua.listBrowsers()` 被审批层拒绝：`404 Not Found`，审批服务不支持当前模型。本批依照提示词停止尝试，没有再次调用该受阻工具。

没有启动 Demo 服务或创建验收数据，没有页面请求、截图、调用摘要或产品缺陷复现。

## 页面验收记录表

所有页面数据必须使用新建的隔离数据根和合成资料。以下“实际”留待普通 Windows 浏览器操作后填写；不得用自动化测试、HTTP 请求或启动脚本输出替代页面证据。

| 操作步骤 | 预期结果 | 实际结果 | 脱敏证据 | 判定 / 阻断原因 |
| --- | --- | --- | --- | --- |
| 上传合成 TXT，创建知识库并建立索引；确认 `READY` 后提一个资料可回答的问题，再提资料不足问题。 | 文件解析完成；索引为 `READY`；首问显示绑定来源；资料不足时严格拒答且不显示伪引用。 | 未执行；未创建页面记录。 | 无截图、URL、会话 ID 或响应记录。 | `PARTIAL`；当前环境没有可用的普通 Windows Chrome/Edge 页面操作。 |
| Mock 默认一题和三题练习，逐题提交并结束；刷新页面并关闭/重启同一隔离 Demo。 | 题目、提交答案、反馈、来源及会话状态恢复；不重复计分或重复生成。 | 未执行；没有 Mock 学习会话。 | 无会话 ID、截图或重启前后对照。 | `PARTIAL`；等待普通 Windows 浏览器验收。 |
| 在合成历史/学习记录的回收站分别取消、按 Escape、输入错误确认词、正确确认永久删除；检查共享来源。 | 非确认路径不发 DELETE；确认路径仅删除目标历史一次；共享文件、知识库和来源仍可用。 | 未执行；没有删除请求。 | 无请求次数、目标 ID、共享对象状态或截图。 | `PARTIAL`；永久删除点击也必须由操作者在确认对话框前再次核验目标。 |
| 搜索三道题的题干、已提交选项和反馈，并逐条打开定位。 | 每个结果定位到对应 `question_id`；不泄露未提交答案键或私有解释。 | 未执行；没有三题会话。 | 无题目 ID 或定位截图。 | `PARTIAL`；等待普通 Windows 浏览器验收。 |
| 在 test-only fixture 下分别选择 DeepSeek 与 OpenAI，各完成一题和点评；查看调用计数并验证刷新恢复。 | 每次操作经过页面费用确认；固定 Host 的 MockTransport calls 与页面操作对应；响应不含 Key/正文。 | 未执行；没有 fixture 服务或 Provider 调用。 | 无费用确认截图、脱敏 `calls` 摘要或会话 ID。 | `PARTIAL`；不得改用真实 Provider；等待普通 Windows 页面证据。 |

## 三分钟演示顺序

引用既有 [求职 Demo 三分钟操作说明](../demo/求职Demo三分钟操作.md)，本批不增加第二套演示流程：

1. 文件页上传合成 TXT，创建知识库并等待索引 `READY`。
2. 问一个资料内问题，打开来源查看原文；再问资料未覆盖的问题，展示严格拒答。
3. 开始默认一题 Mock 学习，提交答案，展示反馈和同一来源；刷新后确认会话恢复。

全程声明 Mock 不会调用真实 DeepSeek。真实重启恢复属于本批完整页面走查项，三分钟演示中不能把历史批次证据说成刚刚复测。

## 宿主操作与回传

请在普通 Windows VS Code PowerShell 终端按 [阶段六十宿主验收入口](../demo/阶段60宿主验收入口.md) 操作：先执行第 0 节前置检查，再按第 2 节启动隔离 Mock Demo；依报告表完成第 1–4 项。第 5 项使用入口第 3 节 test-only Provider 夹具，只使用合成 Key，并在页面每次触发前完成费用确认。所有服务停止后，按入口中的脱敏模板回传报告表或失败截图。

回传至少包含：浏览器名称、使用的本地 URL/端口、隔离数据根标识、合成会话 ID、各步骤结果、刷新与服务重启结果、回收站 DELETE 次数、三题 `question_id` 定位结果，以及两家 fixture 的脱敏 `calls` 计数。删除或遮盖真实路径、Key、个人数据和请求正文。若某项失败，记录页面状态、响应码和脱敏错误，不要修改数据库来制造通过结果。

## Git 交接

第六十批已经推送到 `origin/feat/v1-bootstrap`，SHA 为 `0b6fccef85dd83f6773a92dcddc66e004545882d`。第六十一批文档已用中文提交 `验收：整理阶段八演示验收记录与宿主交接` 提交在本地；完整 SHA 在最终交付说明中列出。两次普通 `git push origin feat/v1-bootstrap` 尝试均长时间无输出，均已停止；之后 `git ls-remote` 仍返回第六十批 SHA，本地分支领先 1 个提交。推送原因未判定；没有强推。

在普通 Windows VS Code 终端完成远端交接：

```powershell
git push origin feat/v1-bootstrap
git rev-parse HEAD
git ls-remote --heads origin feat/v1-bootstrap
```

推送成功后，`rev-parse HEAD` 与 `ls-remote` 返回的完整 SHA 应一致。
