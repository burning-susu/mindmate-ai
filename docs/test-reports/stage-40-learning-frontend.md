# 第四十批：最小学习陪练前端与 Windows 演示

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 进场 SHA：本地与 `origin/feat/v1-bootstrap` 均为 `f3b001c6cc687e99ec979814b175397bc6b8f06c`，工作区干净。
- Demo 可用性：浏览器可以完成有来源的一题一反馈，并在刷新后恢复。
- 完整 V1：阶段 5、6、7 仍为 `PARTIAL`。
- 真实 DeepSeek：`PENDING`。成功路径使用 `learning-demo-fixture-v1`，`live_model_called=false`。

## 页面能走到哪一步

从已 `READY` 且有可用文件的知识库详情点击“基于此知识库学习”，进入 `/learning/new`。页面显示知识库名称、成员文件、主题和目标。题量固定为 1，没有可切换的难度、题型或题量。主题或目标为空白、知识库未就绪时，创建按钮不可用。只打开页面不会调用创建接口。

提交后进入 `/learning/session/:id`。页面显示服务端主题、目标和知识点标题，一次一题、四个选项。未选择不能提交。提交前页面没有证据摘录、点评或 `answer_key`。提交后锁定所选选项，展示服务端结果、解释和可点击引用。引用面板与聊天页共用。来源失效、资料不足、模型或索引不可用时显示服务端说明，并提供返回知识库或修改主题，不跳到普通聊天。

页眉固定为“本地规则模拟演示，未调用真实 DeepSeek”。聊天设置里的在线模式不参与学习出题。

## Windows 浏览器断言

- 数据根：`%TEMP%\mindmate-ai-stage40-learning-demo`。准备脚本使用固定公开样本和已校验 ONNX 缓存，`real_model.state=READY`，`provider_mode=mock`，`deepseek_called=false`，没有下载模型。
- 主库 `01a0dd5d-2799-7b49-ac34-67f401531422`，活动索引 `01a0dd5d-3473-78e6-9b4e-15f9bef50f85`，准备报告里的主库检索检查为 `supported`。
- 服务：FastAPI `127.0.0.1:8002`，Vite `127.0.0.1:5175`。验证后两个端口已释放。没有使用默认用户数据目录。
- Playwright：`e2e/stage7-learning-demo.spec.ts`，`1 passed`（6.8 秒）。
- 正例主题 `API 单次请求超时时间是多少秒？`：创建响应 `IN_PROGRESS`，提交前 `feedback` 为空，响应文本不含 `answer_key`。四个选项。提交前按钮禁用，选择后提交。可见结果和解释与接口正文一致。点击 `[1] 服务超时策略.txt` 后，来源面板包含该文件名和接口摘录。刷新后同一 `attempt_id` 和解释仍在。
- 负例主题 `南极冰芯中氮同位素的具体丰度百分比是多少？`：会话 `FAILED / EVIDENCE_INSUFFICIENT`，`question` 为 `null`，页面没有单选项，并显示“返回修改主题”。
- 截图：`%TEMP%\mindmate-ai-stage40-learning-demo\evidence\learning-feedback.png`。未入库。
- 这次浏览器验证不代表界面上传建库已验收。

## 定向测试

- `frontend/src/test/stage7-learning.test.tsx`：`7 passed`。覆盖空白页不创建、资料不可用、重复创建请求、知识库入口、提交前不泄答、重复提交、未知结果后用同一请求重试、刷新恢复、切换会话、资料不足、`SOURCE_INVALID` 和模型不可用。
- `npm run typecheck`、`npm run lint`、`npm run build` 通过。
- 本批没有改后端，因此没有重跑后端 pytest、Ruff 或 Pyright，也没有重新导出 OpenAPI。契约仍是第三十九批的 `73 schemas / 77 operations`，迁移 head 仍是 `e8b2c41d7a90`。

## 仍记录的 Worker 风险

第三十九批全量 pytest 一轮为 `236 passed / 1 failed`。失败项是未修改的切块 Worker 领取时序用例，单独重跑通过。本批没有改该 Worker，演示也没有领取切块任务。不能把单独重跑通过写成根因已经消失。

## 下一批

把这一题学习回合接到现有 Windows 演示启动，并在后端进程重启后复核同一 URL 的题目、作答和引用仍一致。不扩展多题、掌握度或真实 DeepSeek。
