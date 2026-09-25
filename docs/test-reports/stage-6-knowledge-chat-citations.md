# 阶段 6 知识库问答与真实引用闭环测试报告

## 批次结论

- 批次：第三十四批，求职 Demo 的单知识库问答、证据门控、Citation 绑定与来源展示。
- Demo 结论：`PASS`（后端支持/资料不足/检索不可用三分支及前端契约已完成）。
- V1 结论：阶段 5、阶段 6 仍为 `PARTIAL`；本批不宣称完整 V1 验收、最终答案事实正确性或真实 Provider 联通。
- 时间：2026-09-25。

## 实现范围

- 首条知识库消息必须提交 `mode=KNOWLEDGE_CHAT` 和单个 `KNOWLEDGE_BASE` 范围。服务端验证知识库未删除、活动索引为 `READY` 且 FTS/向量阶段可用，在同一事务创建 Conversation、ConversationScope、用户消息、助手占位、AnswerVersion、AI Operation 和持久任务。
- 后续消息只读取服务端持久范围，不信任前端文件 ID、Chunk、索引版本、摘录或路径。活动索引原子切换后，同一知识库会话下一轮会创建新的范围版本并记录本轮 `index_version_id`。
- Chat Worker 复用 `HybridCandidateQuery`、本地查询向量、FTS5/sqlite-vec、RRF/多样性排序和 `evidence-gate-v1`。`supported` 才向 Provider 发送受限证据块；`insufficient` 保存固定本地拒答并且不调用 Provider；`unavailable`、索引错误和范围竞态以独立错误终止，不降级成普通聊天。
- 新增 Alembic `c3d4e5f6a7b8` 与 `Citation` 表。Citation 只由服务端批准的 `SourceSnapshot` 绑定，顺序与证据块编号稳定；来源读取动态标记可用、回收站、版本失效和永久删除，永久删除清空摘录与可导航关系但保留文件名/定位快照。
- `/api/v1/answer-versions/{answer_version_id}/citations`、`/api/v1/citations/{citation_id}` 和消息/Operation 返回 Citation。知识库回答会追加受控 `[n]` 来源标记，前端显示知识库模式、范围名称、可点击引用、定位、摘录和文件详情入口；普通聊天不返回 Citation。

## 验证证据

### 后端

- `uv run pytest -q --disable-warnings`：`220 passed`。
- `uv run pytest tests/test_stage6_knowledge_chat.py -q`：`3 passed`，覆盖支持回答并绑定真实来源、资料不足固定拒答/0 Provider/0 Citation、Embedding 不可用独立失败/0 Provider。
- `uv run pytest tests/test_stage4_migration.py tests/test_stage5_source_snapshots.py tests/test_stage6_chat_owner.py tests/test_stage6_knowledge_chat.py -q`：通过；空库升级、降级、再升级和历史数据兼容通过。
- `uv run ruff check src tests`：通过。
- `uv run pyright`：`0 errors, 0 warnings, 0 informations`。
- `uv run python -m compileall -q src tests migrations`：通过。
- `git diff --check`：通过。

### 前端与契约

- `uv run python ..\scripts\export_openapi.py`：OpenAPI 3.1 导出成功，包含 Citation schema、知识库范围字段和读取接口。
- `npm run api:generate`：前端生成类型与 OpenAPI 同步（`62 schemas / 72 operations`）。
- `npm run test`：`8 test files / 27 tests passed`。
- `npm run lint`、`npm run typecheck`、`npm run build`：全部通过。
- 前端实现了知识库详情“基于此知识库提问”入口、范围标识、不可用/资料不足提示、引用点击面板和刷新恢复所需的消息 Citation 字段；本批没有以无 READY 数据冒充浏览器级支持问答验收。
- 隔离后端 `8011` + Vite `5175` 浏览器验证：从 READY 结构的知识库详情进入 `/chat?knowledge_base_id=...`，页面显示知识库范围；提交问题后因本机模型缺失显示独立不可用提示且没有 Provider 请求。窄屏截图保存在 `%TEMP%\mindmate-batch34-chat-unavailable.png`，不进 Git。

## Provider 与模型边界

- 运行时和自动化测试只使用 Mock Provider 或本地可控 Provider/检索夹具；没有真实 DeepSeek API Key、真实 DeepSeek 请求、付费调用或私人资料外发。
- 本机固定 `BAAI/bge-small-zh-v1.5` ONNX 状态为 `MISSING_OFFLINE`。因此本批没有声称真实本地 ONNX 支持分支已经完成；缺失模型分支已验证会返回独立 `MODEL_MISSING_OFFLINE`/检索不可用错误且 Provider 调用数为 0。
- 支持分支夹具证明的是服务端范围校验、证据门控、来源快照绑定、Citation 持久化和刷新读取链路，不证明模型输出每句话都事实正确。

## 未完成与边界

- 未实现普通聊天重新生成/答案版本切换、历史编辑、学习陪练、文件范围、多范围切换或自动 Provider 切换。
- 未使用真实 ONNX 模型完成浏览器级 READY 知识库问答；需要模型安装后再做真实固定资料浏览器主流程、点击来源和刷新截图。
- 阶段 5/6 的完整 Recall@10、10 万 Chunk 性能、真实 DeepSeek 联通、完整发布门禁仍未验收。

## 下一批唯一目标

安装并验证固定本地 ONNX 模型后，使用真实 READY 知识库完成浏览器级知识库问答主流程和引用定位恢复；继续不扩展重新生成、学习陪练或自动 Provider 切换。
