# 第七十八批：求职 Demo 最终走查与交付

- 日期：2026-09-30
- 分支：`feat/v1-bootstrap`
- 目标：收口本机隔离 Mock Demo 的最短可复现闭环，修复主链路中实际发现的阻断，并交付 Windows 人工复核说明。
- 数据根：`build/stage78-demo`（被 `.gitignore` 忽略，未提交；第 77 批 `build/stage77-demo` 未触碰）

## 门禁状态

| 项目 | 状态 | 证据边界 |
| --- | --- | --- |
| `STAGE78_DEMO_API_AUTOMATION` | `PASS` | 空库、混合建库、详情上传、重复决策、索引、检索、Mock Chat、学习、总结和同根重启均有 API/持久化证据 |
| `STAGE78_DUPLICATE_REFRESH_REGRESSION` | `PASS` | 修复后新建的复用/跳过任务在重新 GET 后分别保持 `REUSED`/`SKIPPED`，成员数不变；后端 13 个文件契约测试通过 |
| `STAGE78_DEMO_BROWSER` | `BROWSER_PARTIAL` | Web/API 可达；没有可绑定的普通 Chrome/Edge。内置浏览器标签页创建被自动审批层以 `404` 拒绝，未绕过或重复提权 |
| `DEMO_STABLE` | `PASS（沿用既有页面证据；本批新增页面范围待人工复核）` | 本批提升了代码/API 和自动化证据，不把 API 响应写成普通浏览器通过 |
| `STAGE8_FULL_V1` | `PARTIAL` | Windows 恢复偶发锁、Credential Manager 环境、打包入口、完整复习计划、真实 Provider smoke 和账单对账仍独立未完成 |

## 进场与运行

- 进场 `HEAD` 与 `origin/feat/v1-bootstrap` 均为 `e3d42d8e8dd08b1e6a8dfbf4f3f64a6132d355b0`，工作区干净；没有待补推送，不重置本地提交。
- 新建隔离根后运行 `scripts/demo.ps1 -DataDir build\stage78-demo -ApiPort 8018 -WebPort 5188 -NoBrowser`。固定模型离线校验为 `READY`，Provider 固定 `mock`，`deepseek_called=false`，没有真实 Key、外部请求、费用或模型下载。
- API `http://127.0.0.1:8018/api/v1/health` 返回 `ok`；Web `http://127.0.0.1:5188/` 返回 `200`。启动脚本重启前后均核对同一隔离根和模型指纹。

## 主链路证据

| 步骤 | 对象/任务 | 实际结果 |
| --- | --- | --- |
| 空库 | `KB=01a0edd1-0d86-7a77-859d-c6157cd82c1b` | `EMPTY`，0 文件，0 可用文件 |
| 混合库 | `KB=01a0edd1-0e59-7725-8dc2-c565ec19e56c` | 初始已有文件成员任务 `01a0edd1-0e6b-71d9-a612-1f4b0c0f7689` 完成；已有文件 `01a0edbd-6f2b-7e4b-b5e4-0b6c99149087`，最终 3 个成员 |
| 初始上传 | `FILE_IMPORT=01a0edd1-0f89-7940-8952-02b9009256d8` | `stage78-initial.md` 导入/解析完成 |
| 详情上传 | `FILE_IMPORT=01a0edd1-10cc-76df-974d-0794c74d3ff2` | `stage78-detail.txt` 导入/解析完成，刷新后仍可读 |
| 重复复用 | 修复回归任务 `01a0eddd-e9a7-7af8-81cb-8eb2a304dc81` | 决策和刷新均为 `REUSED`，复用原文件 ID，不增加成员 |
| 重复跳过 | 修复回归任务 `01a0eddd-e9ea-7050-8fac-4e736b0106ce` | 决策和刷新均为 `SKIPPED`，`file_id=null`，不增加成员 |
| 索引 | 重建任务 `01a0edd1-12dd-7f56-9e69-a3e0a4330d70`；活动版本 `01a0edd1-134b-716d-9ba8-10dcee4ed792` | 重启后仍 `READY`，3/3 文件可用，处理和失败计数均为 0 |
| 检索 | 主库 `01a0edd1-0e59-7725-8dc2-c565ec19e56c` | 正例 `supported`，候选含 `服务超时策略.txt`，有行号和摘录；资料外问题 `insufficient`，无引用 |
| 带引用 Chat | 会话 `01a0eddd-edad-7c27-b62d-82040b126bd3`；操作 `01a0eddd-edb4-766b-9bce-92c161cbfa66` | `COMPLETED`，Provider `MOCK`，1 条引用；不是 DeepSeek/OpenAI 结果 |
| 资料外 Chat | 操作 `01a0eddd-efd2-795a-b3c2-6a954f7c56dc` | `COMPLETED`，Provider `LOCAL_EVIDENCE_GATE`，明确拒答，0 引用 |
| 学习 | 会话 `01a0eddd-f119-7513-8d4c-b265d0a12fc3`；题目 `01a0eddd-f168-76fc-a55a-0682655a1f99` | 选择 `30 秒`，反馈 `CORRECT`，`learning-demo-fixture-v1`，`live_model_called=false`，完成后总结存在；引用 `01a0eddd-f1bd-753f-83c9-dd8b287e2988` |

机器证据完整 JSON 保留在被忽略的 `build/stage78-demo/stage78-api-evidence.json`，不进入 Git。首次走查中发现重复决策刷新字段未持久化；修复后通过新任务回归，旧任务记录保留原始故障证据，没有篡改历史数据。

## 本批修复

`backend/src/mindmate/api/files.py` 在重复决策时深拷贝 JSON 检查点中的上下文和 item，并递增检查点版本，避免原地修改导致 SQLAlchemy 认为新旧 JSON 相等而不写回。`backend/tests/test_stage4_files.py` 新增复用/跳过决策后的重新 GET 断言，并确认跳过不创建成员。

## 验证命令

- `frontend`: `npm.cmd test -- --run` → `16 files / 84 tests passed`
- `frontend`: `npm.cmd run typecheck` → 通过
- `frontend`: `npm.cmd run lint` → 通过
- `frontend`: `npm.cmd run build` → 通过；保留既有主 JS 大于 500 kB 的 Vite warning
- `backend`: `python -m pytest backend/tests/test_stage4_files.py -q --basetemp=backend/.pytest-stage78-final -p no:cacheprovider` → 13 个测试通过
- `backend`: Ruff、compileall、`git diff --check` → 通过
- 本批没有运行真实 Provider、真实凭据、付费请求或模型下载。

## 浏览器边界与人工交付

没有普通 Chrome/Edge 标签页、截图、页面 Network 计数或代理浏览器点击证据。请按[第七十八批 Windows 本机求职 Demo 说明](../demo/第七十八批Windows本机求职Demo说明.md)在 Guest 窗口执行短卡，记录 URL、知识库/任务/索引/学习 ID 和每项通过状态；在此之前门禁保持 `READY_FOR_USER_BROWSER_CHECK`，不写成 `BROWSER_PASS`。

## 完整 V1 限制

- Windows 数据库恢复仍可能遇到 `WinError 5 / RESTORE_DATABASE_LOCKED`；Credential Manager 仍有 `WinError 1312` 环境阻断。
- 安装包/打包入口、完整复习计划门禁、阶段 9/10 交付和完整 V1 发布验收未完成。
- 真实 DeepSeek/OpenAI smoke、官方费用和账单对账未执行；本批只验证默认 Mock。

## 结论

1. Demo 可以按文档演示：本机 API、Web 启动、文件导入、建库、索引、带来源问答、拒答、学习、总结和同根重启均已由隔离自动化证据验证；普通 Chrome/Edge 点击仍由用户短卡完成，当前标记 `READY_FOR_USER_BROWSER_CHECK`。
2. 完整 V1 仍保持 `PARTIAL`，限制见上，不把求职 Demo 证据写成阶段 8/9/10 全部通过。
3. 不需要第 79 批；唯一遗留是用户在普通 Windows Chrome/Edge Guest profile 完成人工短卡。若短卡发现真实阻断，再按该具体故障开回补批次。
