# CHG-20260927-LEARNING-MULTISTEP

- 日期：2026-09-27
- 状态：实现与自动化验证完成；提交待处理
- 来源：第五十七批接续提示词；实现范围受 `docs/project/requirements/v1/07_学习陪练详细需求.md` 约束
- 关联基线：题量默认 10、支持自定义 1–30；一次展示一道题；严格资料边界和引用；未完成计划可提前结束
- 本批 Demo 限定：开始页默认 1 题，可选 1–5 道有资料依据的单选题；不宣称完整阶段 7

## 变更对象

- Data：revision `d17a5e9c4b20` 在 `learning_sessions` 增加下一题请求 ID/摘要，在 `learning_questions` 增加生成请求摘要，并加会话内非空请求唯一索引。旧行字段保持 `NULL`，不重置用户库。
- API：开始请求接受 1–5 题；新增下一题和主动结束端点；响应增加有序题目历史和基于已保存反馈的结构化结果。
- UI：增加题数选择、显式下一题操作、逐题在线费用确认、来源反馈历史和本地结果摘要。
- Test：测试环境 Provider 传输夹具支持每家生成两条不同事实，并模拟未知外发结果；仍固定官方 Host，不接收任意 URL。

## 安全与行为

- Mock 路径保持本地确定性评分，无 Provider 调用。
- 每道在线新题重新检查 Provider 同意、系统凭据、预算和本次费用确认；已创建会话仍绑定创建时 Provider/模型。
- 作答前 API 不返回答案键；Attempt 和评分不可因重放或并发重复保存；未知付费结果不自动重发。
- 没有新证据、证据失效、重复事实、费用拒绝或生成失败时保留已完成记录，不切换 Provider、不补题。
- 完整阶段 7、阶段 8、真实 Provider 冒烟与真实浏览器验收没有随本变更升级状态。

## Evidence

- 后端 Stage 57 与 Stage 7/55/56 定向回归：`22 passed`。
- 前端 Stage 7 定向测试：`10 passed`；全量 Vitest：`63 passed`；typecheck、lint、build 通过。
- Alembic 旧行升级保留测试、Ruff、改动文件 Pyright `0 errors`、OpenAPI 3.1/生成类型同步通过。
- Chromium/浏览器没有进入页面操作；详见 `docs/test-reports/stage-57-learning-multistep.md`。
- Git 提交受当前执行沙箱 `.git/index.lock` 写入 `Permission denied` 阻断；工作区留作待提交交接，未推送。
