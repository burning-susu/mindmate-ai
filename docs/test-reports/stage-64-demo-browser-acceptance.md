# 第六十四批：求职 Demo 浏览器验收与缺陷收口

日期：2026-09-28。分支：`feat/v1-bootstrap`。

## 结论

本批收到了普通浏览器截图，前两步通过，第三步暴露了两个不同性质的问题：

1. 学习入口的空白主题/目标只把“创建并开始”置为禁用，没有字段级错误提示。
2. 填入“回收站 / 回收站学习”后创建出的会话没有题目。这是严格证据门禁的预期拒答，不是题目渲染丢失：该主题在当前活动资料中没有足够相似且可用的证据。

代码已完成定向收口，但截图对应的旧服务进程尚未重启，因此本批浏览器状态在修复后的正例回测完成前仍保持 `PARTIAL`。

## 浏览器证据

| 步骤 | 预期 | 实际 | 证据 | 判定 |
| --- | --- | --- | --- | --- |
| 知识库问答：API 超时时间 | 回答可见并能打开 `服务超时策略.txt` 来源 | 回答显示 Mock 响应，来源按钮可见 | 用户提供截图 `Snipaste_2026-09-28_10-35-40.jpg` | `PASS` |
| 资料外问题：磁盘配额 | 提示资料不足，不显示来源按钮 | 页面提示“当前选择的资料不足以可靠回答这个问题”，没有来源按钮 | 同上 | `PASS` |
| 新建学习会话空白表单 | 主题/目标缺失时有明确字段提示 | 按钮禁用，但没有红色字段提示 | 用户提供截图 `Snipaste_2026-09-28_10-37-12.jpg` | `FAIL`（已修复） |
| 新建学习会话：回收站主题 | 活动资料足够时生成第 1 题 | 会话 `01a0e5e2-7828-796c-8c8f-24e0f459f550` 为 `FAILED`，完成 `0/1`，无题 | 用户提供截图 `Snipaste_2026-09-28_10-40-15.jpg`、`Snipaste_2026-09-28_10-40-27.jpg` | `EXPECTED_REFUSAL` |

截图未提供浏览器名称、刷新后截图或服务重启后的新页面证据。

## 根因

### 空白字段没有错误提示

`frontend/src/pages/LearningNewPage.tsx` 原来只计算 `canSubmit` 并将按钮设置为 `disabled`。HTML 的 disabled 按钮不会触发表单提交或点击事件，页面也没有 `required`、`aria-invalid` 或错误文本，因此浏览器不会自动在输入框下显示提示。

### 0/1 没有题目

截图中的实际会话数据为：

- 主题：`回收站`
- 目标：`回收站学习`
- Provider：`mock`
- `failure_code`：`EVIDENCE_INSUFFICIENT`
- `failure_detail`：包含 `VECTOR_SIMILARITY_BELOW_THRESHOLD`
- 学习范围实际 `file_ids` 只包含活动的 `服务超时策略.txt`

`回收站范围验证.txt` 的文件状态是 `IN_TRASH`，检索会即时排除；它不能作为学习证据。活动的 `服务超时策略.txt` 只描述 API 请求超时，不支持“回收站”主题，所以检索证据门禁拒绝出题。Mock 出题器随后不会伪造选项，页面显示 `0/1` 是“计划了 1 题但第 1 题没有通过证据门禁”，不是前端漏掉一题。

## 本批修复

- 知识库 `available_file_count` 现在同时检查成员 ACTIVE、未移除、文件未进回收站、文件已解析和索引 READY；回收站文件不再计入可用数量。
- 学习范围保留成员列表，但对不可检索成员显示明确原因，例如“不可用：文件位于回收站”，避免把回收站文件误认为可学习资料。
- 学习主题和学习目标为空或超长时显示红色字段错误，并设置 `aria-invalid`/`aria-describedby`；原有按钮禁用和服务端校验保持不变。
- Mock 学习因证据不足失败时记录 `end_reason=EVIDENCE_EXHAUSTED`，结果页显示“资料不足，已提前结束”。
- 没有放宽 `VECTOR_SIMILARITY_BELOW_THRESHOLD`，没有生成无来源题目，也没有调用真实 Provider。

## 验证证据

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| 后端定向回归 | `backend\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .\build\stage64-targeted-pytest tests/test_stage5_knowledge_bases.py tests/test_stage7_learning_session.py` | `22 passed`；默认临时目录因 Windows 沙箱权限失败，改用仓库内 `basetemp` 后通过 |
| 前端全量测试 | `npm.cmd run test -- --run` | `15 files / 67 tests passed` |
| TypeScript | `npm.cmd run typecheck` | 通过 |
| 前端 lint | `npm.cmd run lint` | 通过 |
| 前端构建 | `npm.cmd run build` | 通过；保留既存 513.81 kB gzip chunk 警告 |
| 后端 Ruff | `python -m ruff check`（本批修改文件） | `All checks passed` |
| Diff 检查 | `git diff --check` | 通过 |

## 验收状态

| 验收项 | 状态 | 说明 |
| --- | --- | --- |
| `DEMO_BROWSER` | `PARTIAL` | 两个问答步骤有截图通过；修复后的学习正例尚未由普通浏览器重新点击取证 |
| `HISTORY_PURGE_BROWSER` | `PARTIAL` | 本批未走查回收站永久删除确认 |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` | 本批未走查 test-only Provider 页面流程 |
| `REAL_PROVIDER_SMOKE` | `PENDING` | 没有真实凭据或付费请求 |
| 求职三分钟 Mock Demo | `PARTIAL` | 使用“服务超时”主题和同一隔离数据根重启服务后需补一次学习正例点击证据 |
| `STAGE7_FULL_V1` / `STAGE8_FULL_V1` | `PARTIAL` | 不由本批 Mock 修复或两步问答截图自动通过 |

## Git 交付

- 本批代码与报告初始提交：`6fafe6e0b9b0995e6276b1909867846a3b13d60c`，信息为 `验收：收口求职Demo学习入口与证据提示`。
- 远端核验：`origin/feat/v1-bootstrap` 仍为 `ced681a11f85878d9f924abeb213d2fbee4435b0`。
- `git push origin feat/v1-bootstrap` 在当前环境无输出并以退出码 `1` 失败；没有宣称已推送。下一步应在可用的普通 Windows VS Code 终端重试并核对两边完整 SHA。

## 修复后回测入口

重启同一隔离数据根 `%TEMP%\mindmate-ai-stage63-isolated-demo-20260928` 后，进入同一知识库的“基于此知识库学习”，填写：

- 学习主题：`API 单次请求超时时间`
- 学习目标：`记住资料中的请求超时值`
- 题量：`1 题`

预期会创建第 1 题，题目和来源为 `服务超时策略.txt`。不要用“回收站”作为学习主题；回收站资料按设计不会参与检索。
