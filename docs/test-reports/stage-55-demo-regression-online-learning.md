# 第五十五批：演示复测与一题在线学习

日期：2026-09-27。进场分支 `feat/v1-bootstrap`，进场本地与远端 SHA 均为 `f6f527c09073d5e7c962677bf443a5d53bf791a8`。

## 状态

| 项 | 状态 |
| --- | --- |
| `DEMO_REGRESSION` | `PASS` |
| `LEARNING_PROVIDER_QUESTION` | `PASS`（MockTransport，不是直播通） |
| `LEARNING_PROVIDER_FEEDBACK` | `PASS`（MockTransport，不是直播通） |
| `LEARNING_ONLINE_BROWSER` | `PARTIAL` |
| `OPENAI_LIVE_SMOKE` | `PENDING` |
| `DEEPSEEK_LIVE_SMOKE` | `PENDING` |
| `STAGE7_FULL_V1` | `PARTIAL` |

第五十三批 `BACKUP_RESTORE` 仍为 `PASS`。阶段 8 的删除确认、多题定位、独立备份 Worker 和周期账单对账按原状态保留。第四十二批历史 Demo `PASS` 不并入本批 `DEMO_REGRESSION`。

## A. 演示复测

隔离数据根：`C:\Users\15932\AppData\Local\Temp\mindmate-ai-stage55-demo`。启动前没有业务库。本地 ONNX 从已校验缓存复制，状态 `READY`，指纹 `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，`download_performed=false`。默认个人库 `C:\Users\15932\AppData\Local\MindMateAI\database\mindmate.db` 前后均为 `2026-09-26T08:59:04.0313752Z`，大小 479232。没有使用私人资料或真实 Key。

服务：`scripts/dev.ps1 -DataDir`，API `http://127.0.0.1:8001`，页面 `http://127.0.0.1:5174/`。资料是仓库内 `docs/test-data/stage5-fixed-ready/服务超时策略.txt`。生成模式为 Mock。

浏览器：

- 文件 `01a0e23b-d6aa-7d1f-8869-3b69a481fe83` 已解析。
- 知识库 `01a0e23c-8790-784a-b388-53f20cefc788`，活动索引 `01a0e23d-8fa8-756c-a92c-f7061d6522f6`，离开页面后任务完成且索引 `READY`。
- 正例对话 `01a0e23e-d8d2-7001-a622-ca3fca320105` 可打开 `[1] 服务超时策略.txt`，正文含“API 单次请求超时时间为 30 秒。”
- 负例“磁盘配额”为资料不足，页面没有来源按钮。
- 学习会话 `01a0e240-65f5-7555-b3c0-bd50b6673bf6` 提交“30 秒”后结果正确，来源抽屉可见。刷新和重启后同一会话、同一 Attempt `01a0e240-a6e0-7925-83bc-c86d799c3deb` 仍在，没有重复。
- 设置页默认 Mock，在线操作 0。切到 OpenAI 再切回 Mock，没有保存 Key，也没有外发。

文件详情“所在知识库（undefined）”是第四十二批已记录的旧问题，本批不修、不挡复测。没有发现需要先修的代码回归。

## B. 一题在线学习

新建学习会话读取当前 `mock` / `deepseek` / `openai_gpt6_sol`。Mock 仍走本地规则。在线会话在创建时冻结服务、请求模型和资料范围。已有会话不跟随后来的设置。创建失败不改用 Mock 或另一家。

出题和点评各自要求费用确认、恢复后重新确认、厂商同意、预算和 Key。未满足时外呼次数为 0。外发上限沿用聊天的 2048 字符，摘录最多 2 段。题目发布前由服务端校验四个互斥选项、唯一正确项、题干不含正确项，以及正确项能在所引原文中找到。提交前响应不含答案键、摘录和正确标记。对错由保存的正确选项决定，模型点评不能改判。点评校验失败时保留评分，并标明点评不可用。

付费调用先提交 `learning_provider_operations` 的 `DISPATCHED`。同一幂等键不会第二次外发。进程重启时仍为 `DISPATCHED` 的行标成 `INTERRUPTED`，不自动重发。用量记入对应 Provider；缺失 usage 按未知处理。

迁移 `b55c0e1a8d27` 增加学习会话的请求/返回模型、反馈的解释来源，以及独立的学习外发账本。不改聊天 `AiOperation` 的必填会话外键。

`LEARNING_ONLINE_BROWSER` 为 `PARTIAL`：DeepSeek 与 OpenAI 的成功出题、错误作答、无效输出、503 中断和重启恢复都由 `httpx.MockTransport` 覆盖，没有在浏览器里点通在线出题。生产页面不能填写任意 Base URL。没有真实 OpenAI 或 DeepSeek 请求。

完整阶段 7 仍缺多题、提示、掌握度和复习，因此 `STAGE7_FULL_V1` 保持 `PARTIAL`。
