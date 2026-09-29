# 第七十五批：阶段 8 Windows 恢复稳定性与浏览器交接

- 日期：2026-09-29
- 进场分支：`feat/v1-bootstrap`
- 进场 LOCAL / REMOTE：`1f80fddfb4c74639aabcc89d97af98bd190d9135`
- 进场工作区：干净
- 普通浏览器：本批 `cua.getState()` 只发现无标签的 Codex In-app Browser，`apps=[]`，没有普通 Chrome/Edge 可绑定
- 页面证据：无本批浏览器 URL、profile、Network 计数或截图；本机 Mock Web/API 已实际运行，交接卡见[第七十批浏览器验收文档](stage-70-stage8-browser-acceptance.md#第七十五批-windows-浏览器交接卡)
- 凭据与外部服务：没有读取、写入或输出真实 API Key；Demo Provider 为 Mock，`deepseek_called=false`，没有访问真实 Provider 或产生费用

## 门禁结论

| 门禁 | 状态 | 本批证据 |
| --- | --- | --- |
| `DEMO_STABLE` | `PASS（沿用第42/64批页面证据）` | 本批实际验证隔离 Mock 服务启动、健康、索引、引用问答、资料外拒答、学习总结及同根重启；没有浏览器页面验收 |
| `STAGE8_FULL_V1` | `PARTIAL` | 普通 Chrome/Edge 页面证据未取得；备份目录切换遇 Windows `WinError 5`，未证明组合回归稳定 |
| 备份恢复组合 | `OPEN` | 故障注入单项通过；受控组合后续复现 `RESTORE_DATABASE_LOCKED`，发生在第二次 `swap_tree` 注入前 |
| `test_windows_credential_manager_round_trip` | `ENV_BLOCKED` | 当前 Codex 执行环境实跑返回 `CredWrite WinError 1312`；测试未 skip；内存凭据端口契约通过 |
| `HISTORY-AC-04/06`、`TASK-AC-05/12` | `CODE_PASS / BROWSER_PARTIAL` | 沿用既有代码证据，本批无页面复测 |
| `LOG_RETENTION_CODE` / `LOG_RETENTION_BROWSER` | `PASS（沿用第73批）` / `BROWSER_PARTIAL` | 本批未做设置页点击或 Network 计数 |
| `PACKAGED_LAUNCHER`、`AC-LEARN-006` | `PACKAGED_LAUNCHER_PARTIAL`、`PARTIAL` | 打包入口及完整间隔复习计划仍未完成 |
| `REAL_PROVIDER_SMOKE`、`PROVIDER_BILLING_RECONCILIATION` | `PENDING` | 未使用真实凭据、服务或账单 |
| 完整 V1 阶段 5–7 | `PARTIAL` | 与 Demo 可用性分开追踪，本批不提升阶段状态 |

## A. Windows 恢复与凭据

### 备份恢复

在随机 `%TEMP%` basetemp 下单项复跑 `test_locked_database_and_interrupted_switch_keep_original`，显式 `BEGIN IMMEDIATE` 锁定阶段通过；释放并关闭 holder 后做新确认，`swap_tree` 第二次调用到达故障注入。增强断言确认注入后状态为 `ROLLED_BACK / RESTORE_SWITCH_CONFLICT`，原对象 SHA-256 不变，在线数据库 `PRAGMA quick_check=ok`，恢复点数据库及其对象文件可读；再次调用恢复入口状态不变、切换次数不增加，数据根外哨兵未变。最终定向命令的该项通过。

为区分 TestClient 清理与恢复逻辑，测试现在用线程 `join` 等待应用 Worker 结束，并断言 Engine 连接池 `checkedout()==0`。在后续失败的受控组合中，这个检查返回时没有应用 Worker 需要等待，池内 checked-out 数为 0；失败发生在 `database` 的 live→aside 第一次目录改名，Python 收到 `WinError 5`，`swap_tree` 注入计数为 1，第二次故障注入没有执行。状态文件只核对脱敏字段，结果为 `phase=ROLLED_BACK`、`error_code=RESTORE_DATABASE_LOCKED`，原数据哈希保持不变。

验证结果有波动：受控 `Chunking + 合法恢复 + 锁定/中断` 序列曾通过 `3 passed`，后续相同顺序运行时合法恢复和故障注入用例均在目录改名前后回滚；合法恢复单项随后也返回 `ROLLED_BACK / RESTORE_DATABASE_LOCKED`。后续 pair 组合分别为 `Chunking + 锁定/中断`、`合法恢复 + 锁定/中断`，都复现未到第二次注入。文件/目录 ACL 正常，合成 SQLite 目录在关闭连接后可移动；目前没有证据把 WinError 5 归因到某个应用 Worker、连接池或特定外部进程，故不将它写成夹具问题或产品根因已确认。

没有修改恢复生产逻辑、取消故障注入、延长固定等待或改动断言来绕过失败。当前结论是：单项故障回滚与恢复点保护有证据；Windows 同进程 TestClient 重启模拟中的目录交换仍有确定性未闭环问题，阶段 8 恢复门禁保持 `OPEN`。

### Windows Credential Manager

当前执行进程报告 `UserInteractive=True`、`SessionId=1`、`SESSIONNAME` 为空，`VaultSvc` 为 `Running`。真实 Windows Credential Manager 单项测试实际运行后在 `CredWrite` 返回 `WinError 1312`（“指定的登录会话不存在或可能已终止”）；未 skip、未输出凭据内容。测试使用 UUID 随机引用和合成值，写入失败后按 `finally` 清理随机引用，没有修改既有用户凭据。仅凭进程的 `UserInteractive` 标志不能证明它处于可用的用户凭据登录会话，因此保留 `ENV_BLOCKED`，不宣称 Credential Manager 通过。

新增 `test_fake_credential_port_replace_delete_and_restart_contract`，通过注入 `InMemoryCredentialStore` 验证保存、替换、重建 TestClient 后读取、删除及 SQLite 中不含合成 Key；该测试通过，Provider Mock 调用数为 0。

供用户在普通交互式 Windows VS Code PowerShell 运行的单项复核命令：

```powershell
Set-Location 'C:\Users\15932\Desktop\ai知识学习助手\mindmate-ai\backend'
$env:PYTHONPATH = (Resolve-Path '.\src').Path
.\.venv\Scripts\python.exe -m pytest tests\test_stage6_provider_configuration.py::test_windows_credential_manager_round_trip -p no:cacheprovider -ra --tb=short
```

测试只创建并删除带随机 UUID 的合成 Credential Manager 条目，不显示 Key。若在普通 Windows VS Code PowerShell 中通过，判定为当前 Codex 执行会话环境受限；若仍返回 `WinError 1312` 或其它 Win32 错误码，则需按该错误继续定位适配器/登录会话，不能改成无条件 skip。

### 自动化与静态验证

| 检查 | 结果 |
| --- | --- |
| 最终定向 pytest | `2 passed`：锁定/故障注入单项、内存凭据保存替换删除重启契约 |
| 故障注入单项 | `1 passed`；断言第二次 `swap_tree` 确实执行，恢复点、原数据、重放幂等与根外哨兵均已验证 |
| 受控组合回归 | 一次 `3 passed`；后续受控序列在 `RESTORE_DATABASE_LOCKED / WinError 5` 失败，详见备份恢复小节，未记为通过 |
| Credential Manager 集成实测 | `1 failed`，错误 `WinError 1312`；未 skip，标为 `ENV_BLOCKED` |
| Ruff（两份改动测试文件） | 通过 |
| compileall（后端 src/tests/migrations） | 通过 |
| 定向 Pyright（两份改动测试文件） | `35 errors`，均为既有 `TestClient.app.state` 动态属性与 `zipfile.crc32` 测试类型诊断；本批新加的可空状态诊断已补断言，没有新增诊断 |
| 全量 Pyright | 本批未重跑；沿用第74批 `59 errors` 证据，包含既有测试动态属性/`zipfile.crc32` 及两个历史 Worker 数值类型诊断，不记为通过 |
| Alembic | `h72a1b2c3d4e5 (head)` |
| 前端 | 本批未改动、未亲跑；沿用第74批结果并标明本批未重验 |
| 全量后端 | 本批未重跑；没有生产逻辑变更，避免无目的重复约16分钟全量 |
| API/OpenAPI | 本批没有 API/schema 变更，未重新生成 |
| `git diff --check` | 通过 |

## B. 隔离 Mock 服务实测

使用 `scripts/demo.ps1` 与新的所有权标记数据根 `%TEMP%\mindmate-ai-stage75-demo-mock-b3978231600c4a3c85f78bc426b9ada3`。模型源 `backend/model-cache/manager-validation` 离线状态为 `READY` 且 fingerprint 匹配；没有下载模型。准备脚本导入 9 份合成文件、建立 4 个库（含一个未就绪诊断库），三条物理索引的预处理/切片/Embedding/FTS 检查点均完成；重复准备计数不变。主库 ID 为 `01a0ec68-93f2-73a2-bb36-0b653cf9ea66`，活动 IndexVersion 为 `01a0ec68-a275-7aae-a239-b4f2ec18a9cd`。

API `/api/v1/health` 返回 `ok`，`/api/v1/embedding-model` 为 `READY` 且 fingerprint 与准备报告一致，主库 index-status 为 `READY`；前端 `http://127.0.0.1:5196/` 返回 HTTP `200`。Mock 知识库问答“API 单次请求超时时间是多少秒？”由 `MOCK` Provider 完成，引用为 `服务超时策略.txt` 第 1 行，摘录包含“API 单次请求超时时间为 30 秒”。资料外问题“玛雅文明使用几套历法？”由 `LOCAL_EVIDENCE_GATE` 拒答，回答为“当前选择的资料不足以可靠回答这个问题。请调整问题范围或补充相关资料。”，引用数为 0。

最小学习会话 ID `01a0ec6f-e97c-7185-af4a-eabff2e61544`，题目 ID `01a0ec6f-e9d9-7ee5-b34a-5561d237fb41`；一次作答结果 `CORRECT`，摘要版本 1，包含 1 条来源引用，`provider=mock` 且 `live_model_called=false`。按脚本停止后确认 API/Web 端口 `8045/5196` 均释放，再用同一根、端口和启动路径重启。重启后 health `ok`、Web HTTP `200`、模型仍 `READY`，同一个学习会话保持 `COMPLETED`，摘要版本和引用均可读。当前服务已重新启动并保留给浏览器人工验收使用。

该服务实测只覆盖本地 API/HTTP 和持久数据，不是浏览器页面验收。没有页面截图、Guest profile 或 Network 面板记录，不能据此更新任何 `BROWSER_PARTIAL` 行。

## C. 下一步人工交接

第七十批文档中的旧多窗口卡与第七十四批长卡已收敛为一张第七十五批六步优先卡：上传/索引 `READY` → 引用/拒答 → 学习总结/历史定位 → 刷新与同根重启 → 设置日志取消/Escape/确认 POST 次数 → 合成历史删除与任务状态。用户需要记录每步 URL、文件/知识库/会话/问题/任务 ID、Network 请求次数及截图路径；不需要重做完整追踪矩阵。

收到实际人工记录前，页面相关行保持 `BROWSER_PARTIAL`。如果用户回传，标记为“用户报告的人工复测”，只更新有证据的对应行。阶段 8 的备份恢复 WinError 5 和正常交互式 Credential Manager 单项复测仍是两个独立待闭环点。
