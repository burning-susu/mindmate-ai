# 第七十六批：阶段 8 人工验收回写与历史删除弹窗优化

- 日期：2026-09-29
- 进场分支：`feat/v1-bootstrap`
- 进场 LOCAL / REMOTE：`ca58c4e936196555e0a495dcfef84bd66dd1dbf6`
- 进场工作区：干净
- 变更记录：[CHG-20260929-HISTORY-DELETE-DIALOG](../project/changes/CHG-20260929-HISTORY-DELETE-DIALOG.md)

## 门禁状态

| 项目 | 状态 | 本批依据与边界 |
| --- | --- | --- |
| `DEMO_STABLE` | `PASS（沿用第42/64批页面证据；本批未复测 Demo 主链路）` | 用户回报第七十五批六步均完成且无功能问题；因没有逐项对象 ID、URL、Network 计数和可读取截图，仍只记作用户口述，不提升页面证据等级 |
| `STAGE8_FULL_V1` | `PARTIAL` | 阶段 8 页面、宿主恢复、Credential Manager、打包与其他门禁仍有独立未完成项 |
| 第七十五批人工卡 | `USER_REPORTED_PASS (1–6)` | 2026-09-29 用户报告六项已完成、未发现功能问题；唯一反馈为第 6 项确认界面体验。没有代理亲测或可核验的逐项材料 |
| `HISTORY-AC-08/09` | `CODE_PASS / BROWSER_PARTIAL` | 当前代码和测试回归通过；新模态的普通 Windows Chrome/Edge 页面证据未取得 |
| 新历史删除模态 | `VITEST_PASS / PLAYWRIGHT_BLOCKED` | Vitest 覆盖两类历史，含取消/关闭/Esc、无确认词、焦点返回、请求次数与错误恢复；Playwright 在 Chromium 启动前遇 `spawn EPERM` |
| Windows 备份恢复 | `OPEN` | 继续保留第七十五批 `WinError 5 / RESTORE_DATABASE_LOCKED`，根因未确认 |
| Credential Manager | `ENV_BLOCKED` | 继续保留第七十五批 `WinError 1312` |
| `PACKAGED_LAUNCHER` / `AC-LEARN-006` | `PACKAGED_LAUNCHER_PARTIAL` / `PARTIAL` | 未改变 |
| `REAL_PROVIDER_SMOKE` / `PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未使用真实 Key、真实 Provider 或账单 |

## 用户报告与证据边界

用户提供的第七十五批回报为“第 1–6 项均完成，未发现功能问题”；用户指出的唯一问题是历史操作确认界面仍出现在列表流中，且永久删除需要输入确认词。将其记录为 `USER_REPORTED_PASS`，不补造对象 ID、完整 URL、Network 次数、截图路径，也不标为代理浏览器亲测。用户报告不能单独关闭 `HISTORY-AC-08/09` 的普通浏览器验收缺口。

旧第七十批矩阵、阶段七十五报告和当时人工卡均保留原文。本报告及[修订人工卡](stage-70-stage8-browser-acceptance.md#第七十六批人工回写与第六项修订)只新增第七十六批结果和新弹窗复核步骤。

## 实现

- 对话历史和学习历史共用 Radix 居中模态和遮罩。组件测试断言弹窗打开后焦点进入模态、取消后回到触发按钮；Radix 负责模态焦点约束与背景交互隔离。Tab 循环和实际浏览器视口验证因 Chromium 无法启动而未执行。
- “移入回收站”和“永久删除”均显示对象名称与影响；软删除说明可在 30 天内恢复，永久删除说明不可恢复且只清除对应历史，不删除源文件或知识库。
- 移除永久删除确认词输入。取消、关闭按钮和 Escape 不发删除请求；忙碌时禁用确认/关闭并拦截 Escape 与遮罩关闭，双击重复确认受同步锁保护。
- 保留 API、`row_version`、恢复语义和安全刷新。服务端 `confirmed=true` 是既有必填布尔契约；用户点击具体危险按钮后继续传该字段，没有改后端或 OpenAPI。
- 历史删除不发后台任务取消请求；文件、知识库和任务行为未改动。

## 验证

| 检查 | 结果 |
| --- | --- |
| `npm.cmd test -- --reporter=dot src/test/stage8-history.test.tsx` | `1 file / 15 tests passed` |
| `npm.cmd run typecheck` | 通过 |
| `npm.cmd run lint` | 通过 |
| `npm.cmd run build` | 通过；Vite 主 JS `579.74 kB`，触发既有 500 kB chunk 警告 |
| `npm.cmd run test:e2e -- e2e/stage76-history-delete.spec.ts` | 未进入页面：两用例均在启动 Chromium 时返回 `spawn EPERM`。尝试以提权重跑但命令未执行，自动审批服务返回 `404 Not Found`；按工具要求没有绕过审批 |
| `git diff --check` | 通过 |

后端测试、OpenAPI 生成和迁移检查未运行：本批没有改 API、后端或数据库契约。普通 Chrome/Edge 当前不可绑定；本批没有新截图、页面 URL 或浏览器 Network 计数。E2E 文件保留，用于环境允许时重新执行，但其本批结果是阻断而不是通过。

## 下步优先项

用普通 Windows Chrome/Edge Guest profile 和合成对象执行修订卡第六项，为新模态记录对话/学习对象 ID、URL、每次操作的 Network DELETE 次数、任务状态对照及截图路径；在此证据到达前维持 `HISTORY-AC-08/09=BROWSER_PARTIAL` 和 `STAGE8_FULL_V1=PARTIAL`。
