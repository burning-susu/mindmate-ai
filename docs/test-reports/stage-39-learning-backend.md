# 第三十九批：最小学习陪练服务端闭环

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 范围：后端学习会话、一题、一次作答、可追溯反馈。没有学习首页或会话页。
- Demo 可用性：后端闭环可用；前端学习页未接入，Windows 端到端学习演示仍缺。
- 完整 V1：阶段 5、6、7 均为 `PARTIAL`。
- 真实 DeepSeek：`PENDING`。本批成功路径也不调用聊天 Provider。

## 本批能做什么

已有 `READY` 知识库可以创建持久学习会话。创建同步完成，固定一题。公开合成资料 `服务超时策略.txt` 的唯一数值事实是 30 秒，题干不包含该数字。提交前响应没有 `answer_key`、评分规则或证据摘录。提交后保存原答案、对错、不同反馈和可点击来源快照，引用文件名是 `服务超时策略.txt`。

同一幂等键不重复计分。答案提交后锁定。刷新后题、尝试、反馈、范围和引用仍在。来源失效为 `SOURCE_INVALID`，文案说明不会改用普通聊天。永久删除后摘录清空。资料不足、索引不可用或出题冲突时保持失败，不调用 Provider。

## 证据与评分

出题只接受证据门控 `supported` 的已批准摘录。同一单位出现多个不同数值时拒绝出题。选项互斥，正确项由来源哈希确定性打乱。评分只比对服务端保存的选项标识。请求体拒绝伪造 `answer_key`、`evidence_id`、`file_id`。

反馈标明“本地 Mock 确定性演示，不是在线模型生成”。Provider 为 `mock`，模型为 `learning-demo-fixture-v1`，`live_model_called=false`。

## 迁移与 API

- Alembic head：`e8b2c41d7a90`，上一版本 `c3d4e5f6a7b8`。
- 改 `citations` 前先删除 `trg_citations_file_purge`，批量变更后再重建。否则 SQLite 在临时表重命名时触发器仍指向旧表。
- 新增 `POST/GET /api/v1/learning-sessions`、`GET .../current-question`、`POST /api/v1/learning-questions/{id}/attempts`。
- OpenAPI 3.1：73 schemas / 77 operations。前端生成类型与 `tsc -b` 通过。没有改学习页面。

## 测试

- 定向：`test_stage7_learning_session.py` 与阶段 4 迁移共 9 项通过。
- Ruff：`src tests` 通过。`migrations` 仍有既有旧迁移告警，本批新迁移未列入。
- Pyright：`src tests` 0 错误。
- `compileall` 通过。
- 全量 `python -m pytest -q --disable-warnings` 一轮：237 项中 236 通过、1 失败。失败项是既有 `test_chunk_worker_reuses_two_knowledge_bases_and_keeps_parse_versions`，断言领取到的任务编号与刚入队任务不同。单独重跑该项通过。本批没有改切块 Worker。全量没有再跑第二轮。
- 自动化没有 DeepSeek 请求，也没有读取 Key。

## 下一批

把本批学习 API 接到最小前端会话，并验证一题一反馈。
