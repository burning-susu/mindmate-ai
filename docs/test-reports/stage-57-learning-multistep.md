# 第五十七批：1–5 题逐题练习

日期：2026-09-27。分支 `feat/v1-bootstrap`。进场本地 HEAD 与 `origin/feat/v1-bootstrap` 均为 `083073cff29ee1d6b92dc3ff472991d80faf4435`；第五十六批工作区改动未提交。

## 状态

| 项 | 状态 | 证据与限制 |
| --- | --- | --- |
| `STAGE56_LOCAL_CHANGES_COMMITTED` | `PENDING` | 只读检查发现运行沙箱将仓库 `.git` 标记为只读；唯一一次普通 Git 写检查在创建 `.git/index.lock` 时 `Permission denied`。没有改 ACL、提权、提交或推送。 |
| `LEARNING_MULTIQUESTION_API` | `PASS` | 逐题业务/API、1/3/5 题、幂等/并发、来源和计分、早停、在线门禁及迁移回归通过。 |
| `LEARNING_MULTIQUESTION_UI` | `PASS` | 计划题数选择、逐题确认和旧会话恢复的前端测试通过；全量 Vitest、typecheck、lint、build 通过。 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 本批只做一次隔离后端启动诊断。迁移和合成知识库准备后服务进程退出，未打开浏览器页面、未点击、未截图；不把 API 用例记作浏览器通过。 |
| `DEMO_REGRESSION_THIS_BATCH` | `PARTIAL` | 后端 TestClient 验证了默认一题、作答和服务端重启恢复。浏览器不可用，未重跑网页上传、索引、聊天和完整 Demo 流程。第四十二、五十五批历史 `PASS` 分别保留。 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 只用固定 `httpx.MockTransport`；没有真实 Key、外呼或费用。 |
| `STAGE7_FULL_V1` | `PARTIAL` | 完整阶段 7 的提示、掌握度、自适应、间隔复习等仍未实现。 |
| `STAGE8_FULL_V1` | `PARTIAL` | 阶段 8 原未关闭项未改变。 |

Demo 可用性与完整 V1 阶段状态分开报告。本批只交付有资料依据的单选题 1–5 题闭环，开始页默认 1 题；不宣称阶段 7 或阶段 8 完成。

## Demo 可用性

`DEMO_REGRESSION_THIS_BATCH=PARTIAL`。后端 TestClient 覆盖了默认 Mock 单题创建、来源评分、刷新/后端重启恢复；浏览器服务未启动成功，因此本批没有重跑网页上传、索引、带来源问答和完整三分钟演示。

## 完整 V1 阶段状态

`STAGE7_FULL_V1=PARTIAL`，`STAGE8_FULL_V1=PARTIAL`。阶段 7 的提示、掌握度、自适应、复习计划等，以及阶段 8 的原有未关闭项，均不在本批验收范围。

## 实现

- 新增 Alembic revision `d17a5e9c4b20`：为学习会话保存下一题请求 ID/摘要，为已生成题保存请求摘要，并增加会话内非空生成请求唯一索引。迁移只加可空字段和索引，Stage 7 旧记录默认保持空值。
- 开始学习 API 校验 `target_question_count` 为 1–5，默认 1。题目沿用现有序号、Attempt、引用快照和 Provider 操作账本，不增加独立学习数据源。
- 新增 `POST /api/v1/learning-sessions/{id}/next-question` 和 `POST /api/v1/learning-sessions/{id}/finish`。下一题必须在已保存评分后由用户显式请求；CAS、稳定请求 ID、摘要和唯一索引阻止重放/并发生成重复序号。每个在线新题单独通过同意、凭据、预算和费用确认门禁。
- 会话响应继续返回兼容的 `question`，并增加按序 `questions` 和由已保存反馈汇总的 `result`。答题前响应不含答案键；提前结束、资料不足、无效来源和未知 Provider 结果保留已完成题目，不自动凑题或重发。
- Mock 仍由本地规则生成；DeepSeek/OpenAI 继续使用冻结的会话 Provider。假传输夹具可分别为两家提供两条不同合成事实，并能模拟下一题外发结果未知。
- 前端开始页提供 1–5 题选项、默认 1。会话页逐题提交、独立确认在线下一题费用、显示历史作答与可定位引用，并用本地结构化数据展示计划数/实际数/评分计数。未实现模型总结、掌握度或复习计划。

## 验证

- 后端：`test_stage57_learning_multistep.py` 与 Stage 7、55、56 相关测试联合运行，共 `22 passed`。覆盖 0/1/5/6 边界、三条独立合成事实、Attempt 只计一次、相同请求并发重放、不同知识库证据拒绝、重复事实早停、用户早停、旧行迁移保留、DeepSeek/OpenAI 各两题及反馈、下一题确认和未知结果不重发。
- Alembic：从 `b55c0e1a8d27` 升级到 `d17a5e9c4b20`，旧单题会话行和题目序号约束保留。
- 后端静态检查：Ruff 通过；Pyright 改动文件 `0 errors`；Python `compileall` 通过。
- API 契约：OpenAPI 3.1 导出 `108 schemas / 116 operations`，TypeScript 类型已重新生成。
- 前端：Stage 7 学习页定向 `10 passed`；全量 Vitest `63 passed`；typecheck 和 lint 通过。Production build 通过，主 JS `508.86 kB`，较第五十六批记录 `502.02 kB` 增加约 `6.8 kB`，仍触发 Vite 的 `500 kB` chunk 提示。本批未进行全站拆包重构。
- `git diff --check` 通过；密钥扫描只命中既有 Provider 代码中的匹配字符串，未在本批新增代码或文档中发现凭据。
- 浏览器：隔离服务启动没有进入 Playwright。第五十六批已记录的 Chromium `spawn EPERM` 和审批服务 `404` 事实保持不变；本批未重复发起备用浏览器审批。

## Git 与交接

- 当前 HEAD/远端分支仍为 `083073cff29ee1d6b92dc3ff472991d80faf4435`；所有第五十六、五十七批文件仍在同一工作区，未提交、未推送。
- `git update-index --refresh --really-refresh` 是本批唯一 Git 写权限检查，失败信息为 `fatal: Unable to create '.git/index.lock': Permission denied`。Windows ACL 显示本机账户有完全控制，但执行沙箱对 `.git` 只有读取权限。按提示词停止后续提交尝试；未改 ACL、未使用提权、替代 Git 目录或强推。
- 本地目录：`C:\Users\15932\Desktop\ai知识学习助手\mindmate-ai`。待提交文件以该工作区的 `git status --short` 为准，Stage 56 和 Stage 57 改动目前混在一起。
- 完整 V1 阶段 7、8 继续 `PARTIAL`；真实 Provider 与浏览器验收仍待后续环境具备后单独验证。
