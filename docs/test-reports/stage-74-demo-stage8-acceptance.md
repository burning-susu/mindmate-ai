# 第七十四批：Demo 与阶段 8 验收及回归收口

- 日期：2026-09-29
- 分支：`feat/v1-bootstrap`
- 进场 HEAD / 远端：`ae75945991a3890a6c5d2811e29ab70ca5432e7f` / `ae75945991a3890a6c5d2811e29ab70ca5432e7f`
- 进场工作区：干净
- 普通浏览器：本批唯一一次 `cua.getState()` 只发现空标签的 Codex In-app Browser；`apps=[]`，没有普通 Chrome/Edge 可绑定
- 旧预览端口：`5123`、`8123` 均无监听进程；本批没有启动 Web/API 演示服务
- 外部 Provider：只使用自动化测试中的 `httpx.MockTransport`；未读取真实 Key，未访问真实 DeepSeek/OpenAI，未产生费用

## 门禁结论

| 门禁 | 状态 | 本批证据与下一步 |
| --- | --- | --- |
| `DEMO_STABLE` | `PASS（沿用第42/64批；本批未实测）` | 没有普通浏览器，未重跑上传、建库、带来源问答、学习与重启闭环；按第七十四批手测卡补证 |
| `STAGE8_FULL_V1` | `PARTIAL` | 自动化覆盖不能替代普通浏览器页面证据；历史、任务、设置、恢复及运行门禁仍有缺口 |
| `HISTORY-AC-04` | `CODE_PASS / BROWSER_PARTIAL` | 总结全文投影与 `question_id` 定位代码证据沿用第72批；本批无页面查询、Network 或截图 |
| `HISTORY-AC-06` | `CODE_PASS / BROWSER_PARTIAL` | 持久总结、`?focus=summary` 与恢复代码证据沿用第72批；本批未浏览器实测刷新/后端重启 |
| `TASK-AC-05` | `CODE_PASS / BROWSER_PARTIAL` | 并发 `2/1` 与可下调 `1/1` 的代码/自动化证据沿用第71批；设置页证据待补 |
| `TASK-AC-12` | `CODE_PASS / BROWSER_PARTIAL` | 回收站任务联动及 Worker 输入复核代码/自动化证据沿用第71批；页面任务 ID 对照待补 |
| `LOG_RETENTION_CODE` | `PASS（沿用第73批）` | 只覆盖应用管理的结构化诊断日志；不证明宿主终端缓冲或未来打包进程输出可被清理 |
| `LOG_RETENTION_BROWSER` | `BROWSER_PARTIAL` | 没有普通浏览器清理确认操作或 Network 计数 |
| `PACKAGED_LAUNCHER` | `PACKAGED_LAUNCHER_PARTIAL` | 仓库没有可运行的打包启动器/安装包；不在本批实现 |
| `AC-LEARN-006` | `PARTIAL` | 持久总结代码沿用第72批；完整 `1/3/7/14/30` 天复习计划仍未实现 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 未使用真实 Key 或真实服务 |
| `PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未读取厂商账单或官方用量接口；本地预算估算不等于账单核对 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 与 Demo 状态分别追踪；本批不提升阶段结论 |

## 本批修复

- 修复 OpenAI 聊天的预算预留 Provider 标识：设置标识 `openai_gpt6_sol` 在预算边界映射为持久操作和价格目录使用的规范名 `OPENAI`。此前五个 OpenAI `MockTransport` 集成用例均在发送前以 `BUDGET_OPERATION_NOT_FOUND` 失败，修复后第54批 Provider 文件全量通过。
- 更正预算统计断言：没有 API Key 的操作保持 `NOT_SENT`，不增加未知 Provider usage 计数；用例仍断言没有 OpenAI 调用。
- 没有更改数据库、公开 API、Provider 外发策略、费用确认或证据门控。

## 回归结果

### 后端全量

本批按提示词仅运行一次全量后端集合，命令从 `backend/` 执行：

```powershell
$env:PYTHONPATH = (Resolve-Path 'src').Path
.\.venv\Scripts\python.exe -m pytest tests --basetemp .pytest-stage74 -ra --tb=short
```

结果：`335 passed, 9 failed, 1 skipped`，耗时 `960.93s`。跳过项是 `tests/test_stage67_diagnostic_log_retention.py:293`，当前 Windows 环境不能创建目录 junction。全量运行后按每个失败项做一次单项隔离复跑；OpenAI 修复后只重跑受影响的 Provider 文件，没有再次运行后端全量。

失败测试名称（全量运行时）：

- `tests/test_stage54_openai_provider.py::test_openai_chat_requires_its_own_consent_key_and_charge`
- `tests/test_stage54_openai_provider.py::test_inflight_operation_keeps_openai_after_switching_to_deepseek`
- `tests/test_stage54_openai_provider.py::test_openai_auth_failure_does_not_call_deepseek`
- `tests/test_stage54_openai_provider.py::test_budget_and_missing_key_make_zero_openai_calls`
- `tests/test_stage54_openai_provider.py::test_openai_knowledge_citation_failure_and_insufficient_are_not_false_success`
- `tests/test_stage5_chunking.py::test_chunk_worker_reuses_two_knowledge_bases_and_keeps_parse_versions`
- `tests/test_stage6_provider_configuration.py::test_windows_credential_manager_round_trip`
- `tests/test_stage8_backup_restore.py::test_restore_replaces_dataset_keeps_recovery_point_and_blocks_outbound`
- `tests/test_stage8_backup_restore.py::test_locked_database_and_interrupted_switch_keep_original`

| 全量失败组 | 单项隔离结果 | 归因 |
| --- | --- | --- |
| `test_stage54_openai_provider.py` 的五个 OpenAI 集成用例 | 修复前五项单独复跑仍失败；修复后该文件 `8 passed` | 可复现的 Provider 标识映射缺陷，已修复 |
| `test_stage5_chunking.py::test_chunk_worker_reuses_two_knowledge_bases_and_keeps_parse_versions` | `1 passed` | 组合运行波动；本次未复现，不改生产逻辑 |
| `test_stage6_provider_configuration.py::test_windows_credential_manager_round_trip` | 仍失败：Windows Credential Manager `WinError 1312` | 当前登录会话不支持该凭据写入；非 Mock 凭据用例，保留失败，不改真实系统凭据 |
| `test_stage8_backup_restore.py::test_restore_replaces_dataset_keeps_recovery_point_and_blocks_outbound` | `1 passed` | 组合运行波动；单项通过 |
| `test_stage8_backup_restore.py::test_locked_database_and_interrupted_switch_keep_original` | 仍失败：恢复进入 `RESTORE_DATABASE_LOCKED`，原数据字节保持不变，但没有到达测试注入的第二次目录切换 | 当前 Windows 数据库句柄使测试在故障注入前短路；保留失败，不改写断言掩盖未执行的切换场景 |

### 前端与静态门禁

| 命令 / 检查 | 结果 |
| --- | --- |
| `npm test -- --reporter=dot` | `16 files / 79 tests passed` |
| `npm run typecheck` | 通过 |
| `npm run lint` | 通过 |
| `npm run build` | 通过；既有 Vite chunk 警告，最大 JS `542.55 kB` |
| `ruff check src tests` | 通过 |
| `python -m compileall -q src tests migrations` | 通过 |
| 全量 `python -m pyright` | 未通过：`59 errors`，集中于现有动态 `TestClient.app.state`/`zipfile.crc32` 测试类型诊断及两个历史 Worker 的数值类型诊断 |
| 修复文件 Ruff / Pyright | Ruff 通过；定向 Pyright `0 errors, 0 warnings, 0 informations` |
| Alembic head | `h72a1b2c3d4e5 (head)` |
| OpenAPI / 前端生成类型 | OpenAPI `3.1.0`，`119 schemas / 122 operations`；生成后 `frontend/src/api/generated/openapi.ts` 无差异 |
| `git diff --cached --check` | 通过 |

## 浏览器与人工交接

本批没有页面、普通浏览器 profile、页面 URL、业务对象 ID、Network 请求次数或截图，因此没有任何本批代理亲测浏览器证据。第53/66批合法备份创建/恢复页面证据仍按原范围沿用；坏包拒绝、历史定位、回收站任务联动、日志清理设置、宿主恢复与其余未验页面保持各自 `BROWSER_PARTIAL`。

一页以内的 Windows 手测卡已补到[第七十批追踪矩阵与人工验收卡](stage-70-stage8-browser-acceptance.md#第七十四批最短人工复测卡)。回传结果时请提供隔离数据根、浏览器 profile、URL、文件/知识库/任务/会话 ID、每步相关 Network 次数和本机截图目录；在这些证据到达前不更新浏览器状态。

## 下一批最短缺口

- 用普通 Windows Chrome/Edge 在隔离 Mock 根走网页上传、解析、建库、索引 READY、带引用问答、无证据拒答、学习反馈、历史总结定位、刷新和后端重启恢复；再核五个核心入口及工作台状态。
- 手测历史总结搜索与真实 `question_id`、软删/恢复/永久删除确认词、文件/知识库回收时关联任务状态、设置日志取消/Escape 零 POST 和确认一次 POST。
- 处理 Credential Manager 当前登录会话前置条件；复核备份中断故障注入被 `RESTORE_DATABASE_LOCKED` 短路的 Windows 句柄时序。
- `AC-LEARN-006` 的长期复习计划、打包启动器、真实 Provider smoke 和官方账单核对继续独立待办；不把它们算作 Demo 失败或本批通过。
