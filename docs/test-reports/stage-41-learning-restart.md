# 第四十一批：Windows 学习演示启动与重启恢复

- 日期：2026-09-26
- 分支：`feat/v1-bootstrap`
- 进场 SHA：本地与 `origin/feat/v1-bootstrap` 均为 `3c71745231fe06e2c679178611c9a02e68152234`，工作区干净。
- Demo 可用性：`PASS`。现有 Windows 演示入口可以完成一题，并在后端进程重启后恢复同一会话。
- 完整 V1：阶段 5、6、7 仍为 `PARTIAL`。
- 真实 DeepSeek：`PENDING`。成功路径使用 `learning-demo-fixture-v1`，`live_model_called=false`。

## 演示命令

```powershell
.\scripts\demo.ps1 -DataDir "$env:TEMP\mindmate-ai-stage41-learning-demo"
```

前提是已运行 `.\scripts\bootstrap.ps1`，并且 `backend/model-cache/manager-validation` 已是校验过的本地 ONNX。脚本不会下载模型，不会读取 Key，也不会使用 `%LOCALAPPDATA%\MindMateAI`。端口 `8001` 或 `5174` 被占用时会停止，不改换端口。

操作步骤：

1. 运行上面的命令。它准备 `docs/test-data/stage5-fixed-ready/` 的公开合成样本，并打开主库页面。
2. 点击“基于此知识库学习”。页面显示“本地规则模拟演示，未调用真实 DeepSeek”。
3. 主题填写“API 单次请求超时时间是多少秒？”，目标填写“记住资料中的唯一超时值”，创建并提交一题。
4. 记下 `/learning/session/<id>`。Ctrl+C 停止。
5. 用同一个 `-DataDir` 再运行 `.\scripts\demo.ps1`，然后打开这个地址。

自动化验收使用 `-NoBrowser` 和 `-PrepareOnly`，避免和 Playwright 抢浏览器。默认不带这两个开关时仍会打开系统浏览器。

## 隔离数据

- 数据根：`%TEMP%\mindmate-ai-stage41-learning-demo`。
- 主库：`01a0dd83-4e9c-7593-85bb-d416956cd860`。
- 活动索引：`01a0dd83-5d58-7169-9684-6a20e75c3390`。
- 准备报告：`provider_mode=mock`，`deepseek_called=false`，`real_model.state=READY`，主库检索 `supported`。
- 重复准备计数：文件 9、知识库 4、任务 24，`counts_unchanged=true`。
- 默认用户数据库 `MindMateAI\database\mindmate.db` 的最后写入时间是 `2026-09-26T16:59:04+08:00`，早于本批操作。

## 后端进程重启

第一次浏览器测试在前端保持运行时只替换后端：

- 旧监听 PID `1668` 被结束后，`127.0.0.1:8001` 不再监听，健康检查失败。
- 页面显示“学习会话暂时读不到。服务恢复后点“重新读取”，会回到同一题和已保存的反馈。”并提供“重新读取”。此时没有单选项。
- 新监听 PID `4692`，命令行是本机 Python 的 `uvicorn mindmate.main:app --host 127.0.0.1 --port 8001`。
- 点击“重新读取”后，题干、四个选项、所选“13 秒”、结果 `INCORRECT`、解释和引用摘录与重启前一致。
- 会话 `01a0dd85-4fe7-7d9c-b95b-e84b34e8a5ee`，题目 `01a0dd85-5419-70c5-8551-179bf8fcf513`，Attempt `01a0dd85-5510-76b6-aa5f-52a6cac73cd7`。
- 重启前后计数都是会话 1、Attempt 1、反馈 1。
- 引用打开 `服务超时策略.txt` 的文件详情，解析预览包含“30 秒”。
- 随后的南极冰芯主题返回 `FAILED / EVIDENCE_INSUFFICIENT`，`question` 为 `null`，页面没有单选项和作答反馈。数据库仍只有 1 道题和 1 次 Attempt，另有一条失败会话。

这次不是只刷新页面。Playwright：`npx playwright test e2e/stage7-learning-restart.spec.ts --reporter=line` 为 `1 passed`（13.9 秒）。

## 同一条演示命令再启动

停止上述进程后，在干净环境运行：

```powershell
.\scripts\demo.ps1 -DataDir "$env:TEMP\mindmate-ai-stage41-learning-demo" -NoBrowser
```

准备再次通过，主库和索引 ID 不变。API `127.0.0.1:8001` 的新监听 PID 是 `15796`，页面 `127.0.0.1:5174/knowledge-bases/01a0dd83-4e9c-7593-85bb-d416956cd860`。只打开已保存会话 URL 的 Playwright 为 `1 passed`（3.3 秒），仍能看到原题、不正确的反馈和 `服务超时策略.txt`。

结束 PID `15796` 后，脚本输出已正常停止，退出码 0。8001、5174、8000、5173 均已释放。

证据文件留在隔离根 `evidence/learning-restart.json` 和 `evidence/learning-restart-file.png`，不进入 Git。

## 定向测试

- `frontend/src/test/stage7-learning.test.tsx`：`8 passed`。新增覆盖服务暂时读不到、点击“重新读取”后回到已保存反馈，并且第二次才会重新建立本地会话。
- `npm run typecheck`、`npm run lint`、`npm run build` 通过。
- `git diff --check` 通过。
- 本批没有改后端，因此没有重跑 pytest、Ruff 或 Pyright，也没有重新导出 OpenAPI。

## 未验收与已知风险

- 界面上传和建库不是这条演示命令的验收范围。资料由准备脚本导入。
- 多题、提示、掌握度、间隔复习和真实在线学习生成都没有做。
- 第三十九批切块 Worker 领取时序用例的偶发失败没有在本批复现，也没有单独重跑。不能写成已经消除。

## 下一批

做整体求职 Demo 的最后一轮验收和交接。不自动展开阶段 7 的高级学习功能。
