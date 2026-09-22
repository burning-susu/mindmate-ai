# G2 待确认事项
> 文档编号：G2-PENDING-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 关联来源：SRC-002、SRC-003、DEC-BOOTSTRAP-001

以下问题只保留会影响后续 Workflow、架构、数据隐私、首版范围、UI 实现或交付方式的事项。

| 编号 | 优先级 | 待确认事项 | 当前已知 | 临时值 | 最晚确认点 | 未确认影响 |
|---|---|---|---|---|---|---|
| OPEN-01 | HIGH | DeepSeek Chat Provider 的 API 条款/地域/账号/余额、Embedding 方案和成本边界 | Chat Provider 已由 DEC-G6-003 条件性应用为 DeepSeek API / `deepseek-flash`；Embedding 与 Guard TBD | 本地后端 Adapter，必要文本出站但 runtime 禁用 | G6 正式架构出口前 | 影响隐私、成本、延迟、数据出境和测试 |
| OPEN-02 | HIGH | 本地向量存储和文档解析实现 | DEC-G6-004 已确认本地嵌入式向量存储 + Storage Adapter 方向，具体产品/组件 TBD | 先做 G8 Spike | G8/G9 | 影响数据模型、引用质量和安装复杂度 |
| OPEN-03 | HIGH | AI 流式传输、文件上传和异步状态 API | REST/OpenAPI 已确认，协议 TBD | 作为独立 TECH-DECISION | G9 API 契约前 | 影响前端状态、断线恢复、契约和测试 |
| OPEN-04 | HIGH | 本地运行形态和支持的操作系统/启动方式 | 不需要云服务器，运行在用户电脑 | 具体打包方式 TBD | G6/G10 | 影响依赖分发、日志、更新和用户引导 |
| OPEN-05 | HIGH | 后端和前端技术栈 | 尚未选择 | TBD | G6/G9 | 影响 Rule、工程目录、测试工具和实施 Flow |
| OPEN-06 | MEDIUM | V1 页面树和一级导航口径 | 核心页面已知，附录存在五页与多层页面差异 | 延后设置，保留核心页面 | G3/G5.5 | 影响 UI Scope、批次和验收 |
| OPEN-07 | MEDIUM | 文件解析对复杂表格、代码块和 PDF 页码的处理 | 文本型四格式确认，复杂内容规则 TBD | 先限制并记录失败 | G8 | 影响引用定位和入库成功率 |
| OPEN-08 | MEDIUM | 轻量性能基线的具体阈值和测试环境 | 已确认轻量基线，NFR 有初始目标 | 沿用需求文档目标，待验证 | G3/G10 | 影响性能 Evidence 和发布门禁 |
| OPEN-09 | MEDIUM | 安全测试深度和是否需要专业渗透测试 | 基础安全检查已确认 | V1 基础安全 | G3/G11 | 公开部署或敏感数据会升级门禁 |
| OPEN-10 | LOW | 目标发布日期、负责人和可投入工时 | 未提供 | TBD | G10 计划前 | 影响排期和 Flow Estimate |

## G3 审计新增问题

| 编号 | 优先级 | 待确认事项 | 当前已知 | 建议 | 最晚确认点 | 状态 |
|---|---|---|---|---|---|---|
| G3-001 | HIGH | 一级页面与嵌套详情页的 V1 页面树 | 用户已确认五个一级页面壳，详情页嵌套，设置页已延后 | 采用 DEC-G3-001 写入 G4 PRD 和 UI Scope | G4 | APPLIED_DEC-G3-001 |
| G3-002 | MEDIUM | Provider 不可用、限流、Key 错误和 Embedding 失败语义 | 已有超时和网络失败处理，单 Provider Adapter 已确认 | V1 统一失败和有限重试，不做自动 Provider 切换 | G8/G9 | OPEN_MAJOR |
| G3-003 | MEDIUM | 本地数据备份、保留和恢复 | 本地保存、删除不可恢复已知，备份周期和恢复方式未知 | G6/G10 评估轻量本地备份 | G6 | OPEN_MAJOR |
| G3-004 | MEDIUM | AI 引用/拒答/陪练质量评测口径 | 已有指标定义和场景，缺固定评测集与阈值 | G4 建立小型固定资料集和人工评审表 | G4/G11 | OPEN_MAJOR |

## 暂不需要本轮确认

小程序、语音、OCR、联网搜索、多智能体、工作流编排、团队权限、复杂统计后台和长期学习计划均被当前 V1 决策延后或排除，不阻塞 G2；若未来进入范围，必须走变更和 Rebase。
