# 求职 Demo：三分钟操作

第四十二批实测通过的路径。聊天和学习都是本地演示，没有调用真实 DeepSeek。

## 环境前提

- 已运行 `.\scripts\bootstrap.ps1`。
- `backend/model-cache/manager-validation` 已是校验过的本地 ONNX，状态 `READY`。没有这份缓存就不要开讲，也不要临时下载来充数。
- 端口 `8001` 和 `5174` 空闲。被占用时脚本会停，不会改端口。
- 使用独立数据根，不要指向 `%LOCALAPPDATA%\MindMateAI`。

## 启动

在仓库根目录执行。下面的命令只把已校验模型复制进新目录，不导入文件，不创建知识库。

```powershell
$data = Join-Path $env:TEMP 'mindmate-ai-job-demo-ui'
New-Item -ItemType Directory -Force -Path $data | Out-Null
backend\.venv\Scripts\python.exe -c "import importlib.util; from pathlib import Path; spec = importlib.util.spec_from_file_location('prep', r'backend\scripts\prepare_stage5_fixed_ready.py'); prep = importlib.util.module_from_spec(spec); spec.loader.exec_module(prep); print(prep._install_verified_model(Path(r'$data'), Path(r'backend\model-cache\manager-validation')))"
.\scripts\dev.ps1 -DataDir $data -ApiPort 8001 -WebPort 5174 -OpenBrowser
```

页面是 `http://127.0.0.1:5174/`。Provider 固定为 Mock。Ctrl+C 停止本次启动的后端和前端。

`.\scripts\demo.ps1` 会先用 API 导入固定样本。它适合打开现成知识库，并沿用第四十一批的重启恢复讲法。它不是这条从网页上传开始的路径。

## 点击顺序

资料用仓库里的公开合成文件 `docs/test-data/stage5-fixed-ready/服务超时策略.txt`。事实句是“API 单次请求超时时间为 30 秒。”

1. 打开“文件”。目录显示 0 个文件。点击“导入文件”，选择上面的 TXT。可以先去别的页面再回来。文件行应出现，状态变成“已解析”。解析失败会留在这一行，不要改数据库。
2. 打开“知识库”，创建知识库，名称可用“服务超时演示”。
3. 在详情页勾选 `服务超时策略.txt`，点击“加入”。成员状态先是“待建立索引”。页面写明成员加入不等于索引可用。
4. 确认“本地 Embedding 模型可用”，再点击“重建当前知识库索引”并确认。可以离开这个页面。回到详情后，标题状态应为“索引就绪”，成员可用。若停在失败原因，就停在这一步，不要把状态改成就绪。
5. 点击“基于此知识库提问”。顶栏应是“Mock 生成，不会外发，也不会产生 DeepSeek 费用。”范围是刚创建的库。提问：“API 单次请求超时时间是多少秒？”回答正文是 Mock 对问题的复述，不是模型算出的秒数。点击来源 `服务超时策略.txt`，再打开文件详情，原文里能看到“30 秒”。
6. 再从知识库进入一次提问，问：“这套资料里的磁盘配额是多少 GB？”页面应写出资料不足以可靠回答，并且没有来源按钮。
7. 回到知识库，点击“基于此知识库学习”。页面应写“本地规则模拟演示，未调用真实 DeepSeek。”主题填“服务超时”，目标填“核对普通请求超时秒数”，创建并开始。选择“30 秒”并提交。反馈为正确，来源仍是 `服务超时策略.txt`，页眉 `live_model_called=false`。刷新浏览器，同一 `/learning/session/<id>` 上的题目、所选答案、对错和引用还在。

## 可以讲的一点

文件离开页面后仍由持久任务解析；索引在点击重建后走本地 ONNX 嵌入和关键词投影，完成后才显示就绪。问答和学习的引用都能打开同一份原文。Mock 只负责把已通过证据门控的来源放进回答，资料不足时本地直接拒答，不编造引用。

## 不要这样讲

- 不要说聊天或题目是 DeepSeek 生成的。正例聊天模型是 `mock-chat-v1`。学习模型是 `learning-demo-fixture-v1`。
- 不要说 Mock 回答正文本身证明了“30 秒”。秒数在打开的文件和引用摘录里。
- 不要把第四十一批的后端重启说成这次又测过。那次证据仍然有效，这次只测了浏览器刷新。
- 文件详情“所在知识库”后面可能出现 `undefined`。原文和解析状态是准的，这个括号是页面读错了字段。

## 失败后怎么停

- 端口占用、模型缓存缺失：看脚本报错，不要换端口，不要下载模型。
- 索引导入失败：留在知识库详情的失败原因和诊断 ID，不要改数据库状态。
- 停止：在启动脚本窗口按 Ctrl+C。只结束这次启动的后端和前端。再用同一个 `-DataDir` 启动，已保存的学习和聊天还在这个目录里。
- 真实 DeepSeek 需要在设置里单独打开，并完成同意、系统凭据和发送前确认。这条演示不走那一步。
