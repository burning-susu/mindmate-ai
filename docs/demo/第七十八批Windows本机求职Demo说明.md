# Windows 本机求职 Demo 说明

本说明对应第七十八批的本机演示主链路。默认使用隔离数据根、固定本地 ONNX Embedding 和 Mock Provider；本机文件解析、索引、检索、引用和持久化恢复是真实流程，问答和出题的生成端是本地 Mock，不代表已经调用 DeepSeek 或 OpenAI。

## 前置与启动

- 在仓库根目录使用普通 Windows PowerShell。
- 已有 `backend\.venv`、前端依赖，以及已校验的 `backend\model-cache\manager-validation`。模型缓存缺失时停止，不临时下载模型。
- 不使用 `%LOCALAPPDATA%\MindMateAI`。下面的目录只属于这次演示，可在服务停止后删除。

```powershell
$data = Join-Path (Get-Location) 'build\mindmate-job-demo'
New-Item -ItemType Directory -Force -Path $data | Out-Null
.\scripts\demo.ps1 -DataDir $data -NoBrowser
```

脚本会先准备固定合成资料和 READY 索引，再打印实际的 `API`、`Web` 地址和主库 ID。把打印出的 Web 地址复制到普通 Chrome 或 Edge 的 Guest 窗口；脚本没有自动打开浏览器。端口被占用时停止占用进程后重试，不能把临时端口或默认用户目录混入演示。按 `Ctrl+C` 停止本次启动的后端和前端；恢复验证必须再次使用同一个 `$data`。

## 合成资料

- 已有资料：`docs\test-data\stage5-fixed-ready\服务超时策略.txt`。可回答的事实是“API 单次请求超时时间为 30 秒”，原文在第 3 行附近。
- 建库初始上传：`docs\test-data\stage78-demo\演示上传资料.md`。
- 详情页再次上传：`docs\test-data\stage78-demo\演示详情资料.txt`。

## 3–5 分钟点击顺序

1. 进入“知识库 → 新建知识库”，只填写名称创建一个空库。详情应显示 `EMPTY`、0 个文件。
2. 再新建一个库。在“初始资料”中勾选已有的 `服务超时策略.txt`，通过“选择文件”加入 `演示上传资料.md`，提交后应进入这个新库的详情页。成员任务、文件导入任务、文件名、任务 ID 和解析状态应可见；成员加入只表示待建立索引。
3. 在详情页上传 `演示详情资料.txt`，等待导入/解析完成后刷新。此前的成员和导入任务仍应从服务端读回，文件数量保持正确。
4. 在详情页上传 `服务超时策略.txt` 的重复内容，选择“复用现有”；刷新该任务后应显示 `REUSED`，成员列表不增加。再次上传同一内容并选择“跳过”；刷新后应显示 `SKIPPED`，也不增加成员。解析失败时停在失败原因和诊断 ID，不把上传成功说成可检索。
5. 在“索引状态与任务”区域启动受控重建。等待状态从待建立/构建中到 `READY`；模型缺失或离线时按页面提示停止，不自动下载。
6. 点击“基于此知识库提问”，提问“API 单次请求超时时间是多少秒？”。回答顶部应标明 Mock，来源可打开并显示 `服务超时策略.txt` 的定位和摘录。再问“南极冰芯中氮同位素的具体丰度百分比是多少？”，应明确拒答且没有引用。
7. 点击“基于此知识库学习”，保持 1 题，主题填“服务超时”，目标填“核对普通请求超时秒数”。选择“30 秒”并提交；反馈应为正确，引用仍可打开，页面显示 `live_model_called=false`。完成会话后打开总结。
8. 记下地址栏中的 `/learning/session/<id>`，刷新页面确认题目、作答、反馈、引用和总结仍在。停止脚本，再用同一个 `$data` 执行启动命令，打开同一地址；知识库、任务、对话和学习总结应继续可读。

## Mock 边界

默认 Provider 是 Mock，模型名会显示为 `mock-chat-v1` 或 `learning-demo-fixture-v1`。Mock 只用于演示生成，不证明真实外部模型质量；引用摘录和文件定位来自本地索引与证据门控。切换 DeepSeek/OpenAI 需要在设置中明确选择、配置系统凭据、同意外发并确认费用，本批不输入 Key、不发出外部请求、不做账单验收。

## 人工复核短卡

在普通 Chrome/Edge Guest 窗口逐项记 `通过/未通过`，同时记录地址栏、知识库 ID、导入任务 ID、索引版本 ID 和学习会话 ID：

- [ ] 空库创建：`EMPTY`、0 文件。
- [ ] 建库直接上传：已有文件 + `演示上传资料.md` 混合提交，进入正确详情。
- [ ] 成员与刷新：成员任务、解析状态、详情页第二次上传和刷新后任务均可读。
- [ ] 重复决策：复用刷新后 `REUSED` 且不增成员；跳过刷新后 `SKIPPED` 且不增成员。
- [ ] 索引与问答：`READY`、正例有 `服务超时策略.txt` 引用，资料外问题拒答无引用。
- [ ] 学习与重启：一题反馈、总结、同根重启后同一 `/learning/session/<id>` 可读。

代理无法绑定普通 Chrome/Edge 时，把结果记为 `READY_FOR_USER_BROWSER_CHECK`；不要把 API、Vitest、pytest 或内置浏览器观察写成 `BROWSER_PASS`。
