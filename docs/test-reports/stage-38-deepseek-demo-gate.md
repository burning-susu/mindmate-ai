# 第三十八批：真实 DeepSeek 演示门禁

## 结论

- 日期：2026-09-26。分支 `feat/v1-bootstrap`。进场本地与 `origin/feat/v1-bootstrap` 均为 `5dad7bff3f9561e92b552c2416052386ee015930`，工作区干净。
- Demo 可用性：默认 Mock 演示路径仍可启动，设置和聊天能区分 Mock 与在线模式。真实 DeepSeek：`PENDING`。
- 完整 V1：阶段 5、阶段 6 仍为 `PARTIAL`。本批不把 Demo 门禁写成阶段验收通过。
- 本批没有真实 Key、没有付费请求、没有私人文件。官方模型别名仍冻结为 `deepseek-flash`。2026-09-26 官方价格页显示该别名对应 DeepSeek-V4.1-Flash，OpenAI 兼容地址仍是 `https://api.deepseek.com`。高峰、缓存未命中单价为输入 0.30 美元/百万 Token、输出 1.20 美元/百万 Token。页面上的费用数字是用满本地上限的保守估算，不是严格美元限额。

## 模式与外发

- 默认生成模式是 Mock。`.\scripts\demo.ps1` 继续强制 `MINDMATE_PROVIDER_MODE=mock`，启动和进入页面不调用 DeepSeek。
- 设置页按钮 `POST /api/v1/ai/provider/generation-mode` 只写入 `app_settings`，不读取、不回传 Key，也不发网络请求。
- 在线模式文案：DeepSeek 在线生成、会外发当前问题与必要的少量证据。
- 未记录当前同意版本、系统凭据里没有 Key，或用户没有勾选费用估算时，后端拒绝且 Provider 调用为 0。聊天页同时禁用输入。
- 知识库在线请求：输出最多 256 Token；输入按每个字符 1 个 Token 估算，另有 2048 字符上限。外发证据最多 2 段，摘录先截短。放不进上限则拒绝，不调用 Provider。
- 资料不足仍走本地拒答，调用增量为 0，Citation 为 0。
- 在线回答没有命中已外发证据编号时，状态为失败，错误码 `CITATION_CONSTRAINT_FAILED`，不自动重试。
- 连接探测仍只在用户勾选确认后发送固定短文本，输出上限仍是 8 Token。

## 脚本退出

- 根因：等待循环把本批后端的任何退出都当成异常。第 37 批用 Stop-Process 结束后端，清理已经完成，脚本仍返回 1。
- 现在只跟踪本次启动的后端和前端。Ctrl+C，以及退出码 -1（Stop-Process / TerminateProcess(-1)），视为正常停止并返回 0。其他退出码仍返回失败，并清理本批进程。
- 不结束系统浏览器，不清理命令行不匹配的端口占用，不改 8000/5173 与数据根保护。
- 现场：隔离目录 `%TEMP%\mindmate-ai-stage38-ui` 上启动 `.\scripts\dev.ps1 -ApiPort 8001 -WebPort 5174`。结束 8001 上的本批后端后，脚本退出码为 0。定向自测 `RequestedStop` 退出码 0，`UnexpectedExit` 退出码 1，且不结束无关进程。
- 限制：进程若自己以退出码 -1 结束，与 Stop-Process 无法区分，会按正常停止处理。这是为了收口第 37 批的现场停止方式，不是把所有失败都改成成功。

## 浏览器

隔离服务 `http://127.0.0.1:5174`：

- 设置页默认显示生成模式 Mock，以及不会外发、不会产生费用。
- 切到在线模式后出现外发说明和“不是严格美元限额”。
- 未配置 Key 时，聊天页显示在线外发说明，消息框禁用。
- 切回 Mock 后，消息框恢复可输入，文案回到 Mock。
- 这次浏览器没有发送聊天问题，也没有点击连接探测。

## 本批门禁

- `python -m pytest tests/test_stage6_provider_configuration.py tests/test_stage6_chat_owner.py tests/test_stage6_knowledge_chat.py tests/test_local_runtime.py -q --disable-warnings`：退出码 0，39 项通过。
- 上述文件的 Ruff 通过，Pyright 0 errors。
- 前端 `src/test/stage6-provider.test.tsx`：4 项通过。`npm run typecheck`、`npm run lint`、`npm run build` 通过。
- OpenAPI 3.1：`64 schemas / 73 operations`。
- 没有重跑后端全量，也没有重跑第 37 批的 Windows 知识库正负例浏览器剧本。第 37 批成绩仍是历史记录。

## 真实 DeepSeek：待人工验证

精确阻碍：本批执行时，用户没有在应用里主动发起连接探测或知识库问题。自动化不能代为调用。

以后由用户在设置页自行完成，仍使用公开合成主库，最多两次真实请求，失败不自动重试、不升级模型：

1. 保存自己的 DeepSeek Key。页面不会回显完整 Key。
2. 确认当前外发说明版本。
3. 选择“使用 DeepSeek 在线生成”，阅读保守费用估算。
4. 如需连通性，勾选后点击一次“测试连接”。
5. 打开固定合成主库的知识库问答，勾选发送前确认，提一个资料内的短问题。刷新后核对正文和来源是否来自该合成资料。
6. 再用一个资料外问题确认本地拒答，且这次没有新的 Provider 调用。

若模型回答没有通过引用约束，不要把该次记为成功。

## 下一批唯一目标

做最小学习陪练的可演示主链路。继续默认 Mock。不要把本批未发生的真实调用写成已连通。
