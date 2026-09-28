# 第六十五批：阶段 8 本地诊断与历史页面验收

日期：2026-09-28。分支：`feat/v1-bootstrap`。进场本地与远端 SHA：`381cfeb3c4fade829fb15d985d7db06dedd346b1`。

## 结论

本批完成了设置页安全诊断预览与主动导出代码、契约和自动化回归。导出只生成有限的本地 JSON 状态包，不读取原始日志、数据库快照、备份、文件正文、Prompt、问题/回答、模型原始响应、向量、Embedding、Cookie 或 Key。预览和导出共用同一份白名单投影，导出不写服务器临时文件。

历史永久删除和三题定位的页面验收没有取得新的普通 Chrome/Edge 点击证据。当前 Codex 内置浏览器在创建隔离标签页时被审批层返回 `404 Not Found`，错误内容为当前模型账户不支持 `gpt-5.6-luna`；遵照附件要求没有重复尝试同一审批，也没有把 API、pytest 或页面资源 `200` 说成浏览器通过。

## 本批实现

- 新增 `GET /api/v1/system/diagnostics/preview`：返回白名单类别、排除类别、时间范围、体积估计、任务计数和脱敏任务状态。
- 新增 `GET /api/v1/system/diagnostics/export`：以内存 JSON 响应下载，带 `Content-Disposition`、`nosniff` 和 `no-store`；不接受路径、字段选择或通配符。
- 两个接口都要求当前本地会话；Origin 继续由本地安全中间件校验。导出失败只返回 `DIAGNOSTICS_BUILD_FAILED`，不创建半成品。
- 设置页增加“预览诊断内容”“导出诊断包”和“取消预览”；页面明确显示包含/排除范围、任务摘要、预计体积和本机保存说明。`log_retention` 与 `storage_migration` 仍不可用。
- OpenAPI `3.1` 与前端生成类型已同步；没有新增数据库迁移、外部依赖、真实 Provider 调用或真实凭据。

## 自动化证据

| 门禁 | 命令/范围 | 结果 |
| --- | --- | --- |
| 诊断后端回归 | `backend\.venv\Scripts\python.exe -m pytest ... tests/test_stage65_diagnostics.py` | `4 passed` |
| 诊断安全覆盖 | 预览/导出一致、Key/Token/路径/正文诱饵不泄露、会话/Origin、失败清理 | 已覆盖 |
| 阶段 8 后端组合回归 | 设置、备份、历史、多题、任务保留及诊断文件 | 组合运行 `33 passed`，另有 1 个既有历史边界用例在组合顺序中波动；隔离重跑 `1 passed`。此前另一轮出现 FTS5 checksum 波动，隔离重跑同样通过 |
| 前端全量 Vitest | `npm.cmd run test -- --run` | `15 files / 68 tests passed` |
| 前端诊断交互 | stage6 provider fixture | 预览打开、白名单展示、取消预览通过 |
| 前端 TypeScript | `npm.cmd run typecheck` | 通过 |
| 前端 lint | `npm.cmd run lint` | 通过 |
| 前端构建 | `npm.cmd run build` | 通过；保留既有大 chunk 警告 |
| 后端 Ruff | 本批修改源文件与测试 | 通过 |
| OpenAPI/生成类型 | `backend\.venv\Scripts\python.exe scripts\export_openapi.py`、`npm.cmd run api:generate` | 新增 2 个 diagnostics operation，生成类型同步 |
| Diff | `git diff --check` | 通过 |

`scripts/demo.ps1 -PrepareOnly` 在隔离数据根 `build\stage65-browser-demo` 完成固定 Mock 数据准备；`scripts/dev.ps1` 以 API `8016`、Web `5184` 启动并核对主库 `01a0e648-fa5b-75ca-99ab-c09717f12410` 与索引 `01a0e649-0b6b-7949-bc57-9dd8645a17d2` 为 READY，随后已停止本次启动的进程。该启动证据不等于页面点击证据。

## 分项状态

| 验收项 | 状态 | 真实范围 |
| --- | --- | --- |
| `DIAGNOSTICS_PREVIEW_EXPORT` | `PARTIAL` | 后端 API、脱敏/失败安全和前端交互自动化通过；没有普通浏览器页面点击/下载证据 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 没有取消、Esc、错误确认词、正确永久删除和 Network DELETE 次数的页面证据 |
| `HISTORY_MULTISTEP_BROWSER` | `PARTIAL` | 没有三题题干/已提交选项/公开反馈逐条搜索与定位的页面证据 |
| `LOG_RETENTION` | `PARTIAL` | 日志保留/清理未实现，设置页保持不可用说明 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | test-only Provider 页面走查未执行；本批未调用真实 DeepSeek/OpenAI |
| `BACKUP_WORKER` | `PARTIAL` | 独立备份 Worker 仍是后续缺口；现有同步安全备份能力未冒充 Worker 完成 |
| `BUDGET_RECONCILIATION` | `PARTIAL` | 周期费用对账仍未实现，现有估算/硬停止边界未改变 |
| `DEMO_BROWSER` | `PASS（用户报告的既有证据）` | 沿用第六十四批用户报告；本批未重复旧 Demo |
| `STAGE8_FULL_V1` | `PARTIAL` | 不因诊断导出自动化通过而整体通过 |

## 浏览器阻断与最短交接清单

本批尝试打开 `http://127.0.0.1:5184/knowledge-bases/01a0e648-fa5b-75ca-99ab-c09717f12410`。`cua.getState()` 只显示无标签页的 Codex 内置浏览器；创建标签页时审批层返回 `404 Not Found`，未执行点击。

在普通 Windows Chrome/Edge 中使用已启动的隔离服务时，最短清单如下：

1. 打开 `http://127.0.0.1:5184/settings`，进入“日志与隐私”，点击“预览诊断内容”，确认包含/排除类别、预计体积、任务摘要和“保存在本机，不会自动上传”；点击“取消预览”后内容收起，再点击“导出诊断包”并确认浏览器保存的是 JSON。不要上传或分享导出文件。
2. 打开知识库历史入口，使用合成对话和学习记录分别走取消、Esc、错误确认词；只在用户明确确认永久删除后测试正确确认词。记录 Network 中 DELETE 次数和脱敏响应，确认共享文件、知识库、引用来源及另一会话仍在。
3. 在历史学习标签搜索三道合成题的题干、已提交选项和公开反馈，逐条打开定位结果，记录 `question_id` 与反馈区域；检查未作答正确答案和私有说明不出现在结果中。

上述操作产生页面截图、URL、合成 ID 和 Network 证据后，才能把前三项从 `PARTIAL` 改成页面级结论。永久删除属于不可逆本地操作，需在点击最终确认前由操作者确认；本代理没有执行该点击。

## 后续缺口

独立备份 Worker、周期费用对账、日志保留/清理、全局错误与离线页面、在线 test-only Provider 页面、历史永久删除/三题定位普通浏览器证据，以及需求追踪中尚未完成的完整阶段 8 项仍待后续批次处理。真实 DeepSeek/OpenAI 付费冒烟继续保持 `PENDING`。
