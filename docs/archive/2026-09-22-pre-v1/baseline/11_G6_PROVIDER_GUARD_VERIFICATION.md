# Mindmate AI G6 Provider Guard Verification
> 文档编号：G6-PROVIDER-GUARD-VERIFICATION-001
> 文档版本：v1.0-Draft.1
> 文档类型：governance
> 文档状态：Historical / SUPERSEDED_NOT_CURRENT_PROVIDER
> 当前阶段：G6
> G6_EXIT：BLOCKED
> PROVIDER_DECISION_STATUS：HISTORICAL_APPLIED_CONDITIONAL
> 历史 Provider 基线：DEC-G6-002 / Alibaba Cloud Model Studio / qwen3.8-flash / text-embedding-v4
> 当前 Provider：DEC-G6-003 / DeepSeek API / deepseek-flash
> 访问日期：2026-09-21
> 关联 Evidence：EVID-029、EVID-030、EVID-032、EVID-033

> 本文件保留 Alibaba Guard 的完整历史核验和阻断证据。自 DEC-G6-003 生效后，Alibaba Guard 不再作为当前 Chat Provider 的 Guard，当前 Guard 见 `12_G6_DEEPSEEK_PROVIDER_GUARD_VERIFICATION.md`；原始 no-call 边界和 G6 阻断不变。

## 1. 本轮结论

本轮已核验公开官方页面并执行 G6 Exit Preflight。模型目录和价格资料可以部分证明公开候选与价格；数据处理、保留/训练、删除、子处理者、地区适用关系以及用户账号资格没有获得足够的一手证据。

结论：

```text
G6_EXIT=BLOCKED
G6_STATUS=BLOCKED
ARCHITECTURE_STATUS=DRAFT
OPEN-01=G6_EXIT_BLOCKER
G7_ENTRY_GATE=NOT_READY
G7_EXECUTION=NOT_STARTED
PROVIDER_RUNTIME_ENABLED=false
```

本轮没有调用 Chat、Embedding、文件上传或其他付费 Provider API，没有读取、创建或验证任何 API Key、AccessKey、Secret、Token、Cookie 或登录状态。

## 2. Guard Matrix

状态含义：PASS 只表示当前有足够的一手资料；PARTIAL_PUBLIC_ONLY 表示公开目录/价格可见，但不能证明用户账号、区域或全部条款；UNVERIFIED 表示页面壳、登录限制、内容缺失或官方资料没有直接证明；BLOCKED 表示该项阻断 G6 出口。

| Guard ID | 防护条件 | 状态 | 证据 / 官方定位 | 未确定点与影响 |
|---|---|---|---|---|
| GUARD-PUB-001 | API 输入、输出、文件和 Embedding 数据处理范围 | UNVERIFIED / BLOCKED | Alibaba Model Studio Data privacy 页面：https://www.alibabacloud.com/help/en/model-studio/data-privacy；访问 2026-09-21，仅返回页面壳，未取到正文 | 不能证明文件切片、Embedding 输入、Chat 输入和元数据的具体处理范围 |
| GUARD-PUB-002 | 数据保留期限、日志和监控保留 | UNVERIFIED / BLOCKED | Alibaba Data privacy 页面；当前响应无可读正文 | 不能证明保留期限、日志留存或例外 |
| GUARD-PUB-003 | 客户数据是否用于训练及适用条件 | UNVERIFIED / BLOCKED | Alibaba Data privacy / Terms 页面：https://www.alibabacloud.com/help/en/model-studio/terms-and-conditions；当前响应无可读正文 | 不能把营销页面或其他产品条款套用于 Model Studio API |
| GUARD-PUB-004 | 删除机制和删除时效 | UNVERIFIED / BLOCKED | Alibaba Data privacy 页面；正文未取到 | 不能确认删除请求、备份副本、日志副本和时效 |
| GUARD-PUB-005 | 子处理者、第三方处理和数据接收方 | UNVERIFIED / BLOCKED | Alibaba Terms 页面；当前响应无可读正文 | 不能确认 Provider 及其子处理者边界 |
| GUARD-PUB-006 | Singapore / International endpoint 和数据处理地域 | UNVERIFIED / BLOCKED | Alibaba Region support：https://www.alibabacloud.com/help/en/model-studio/region-support；访问 2026-09-21，仅返回页面壳 | 不能证明候选地区、存储地区、处理地区和跨区例外 |
| GUARD-PUB-007 | 两个目标模型在目标区域公开可用 | PARTIAL_PUBLIC_ONLY / BLOCKED | Models：https://www.alibabacloud.com/help/en/model-studio/models；页面列出 qwen3.8-flash、text-embedding-v4 | 公开目录不等于用户账号可见、已开通或可调用；区域映射未核实 |
| GUARD-PUB-008 | 计费单位、价格、免费额度、限流和配额 | PARTIAL_PUBLIC_ONLY / BLOCKED | Pricing：https://www.alibabacloud.com/help/en/model-studio/billing-for-model-studio；Singapore/International 行可见 qwen3.8-flash USD 0.15/0.47 per 1M、text-embedding-v4 USD 0.07/M | 单价和部分免费额度可见；账户配额、限流、免费额度资格和最终账单仍未核实 |
| GUARD-PUB-009 | 服务条款、隐私条款、DPA 或等价法律文件的适用关系 | UNVERIFIED / BLOCKED | Terms/Data privacy/Region 页面均未取得可读正文 | 不能证明 Model Studio API 条款覆盖当前账号、区域和两种模型 |
| GUARD-ACCOUNT-001 | Alibaba Cloud 账号可登录且已创建 | NOT_VERIFIED / BLOCKED | 只能由用户控制台核验；本轮不登录 | 账号资格未知 |
| GUARD-ACCOUNT-002 | Model Studio 在目标区域开通 | NOT_VERIFIED / BLOCKED | 用户控制台核验项 | 开通状态未知 |
| GUARD-ACCOUNT-003 | Singapore/International endpoint 对账号可用 | NOT_VERIFIED / BLOCKED | 用户控制台模型/Endpoint 列表核验项 | 公开目录不能替代账号资格 |
| GUARD-ACCOUNT-004 | 付款、充值、后付费、预算或配额能力可用 | NOT_VERIFIED / BLOCKED | Billing / Quota / Model Studio Usage 核验项 | 不得把 USD 5 软预算当成已实施限制 |
| GUARD-ACCOUNT-005 | 目标模型对账号可见、可申请或已授权 | NOT_VERIFIED / BLOCKED | Model Studio 模型权限核验项 | 公开模型目录不能证明账号可调用 |
| GUARD-COST-001 | USD 5/月软预算及 fail-closed 行为 | PROPOSED / NOT_APPLIED | DEC-G6-002 第 3 节；本轮没有用户新确认硬预算或代码实现 | 需要项目所有者确认；当前不是运行时硬限制 |
| GUARD-COST-002 | 80% 提醒、100% 停止、禁止自动充值/提额 | PROPOSED / NOT_APPLIED | 第十轮成本保护候选；尚无实施证据 | 需要 G8/G9 设计和所有者确认 |

## 3. 公开官方资料结果

### 3.1 可以证明的事实

- Alibaba 官方模型目录页面列出 qwen3.8-flash 和 text-embedding-v4。
- Alibaba 官方价格页显示 Singapore/International 价格表中的 qwen3.8-flash 输入/输出为 USD 0.15/0.47 每百万 Token，text-embedding-v4 输入为 USD 0.07 每百万 Token。
- 这些价格和目录事实只能支持“公开候选资料存在”，不能支持用户账户已开通、地区可用、条款已接受或运行时可调用。

### 3.2 不能通过的事实

本轮直接请求 Alibaba 官方 Region support、Data privacy 和 Terms and conditions URL，均返回 HTTP 200，但正文只呈现页面壳，未得到可引用的条款段落。因此下列内容均保持 UNVERIFIED：

- API 输入、输出、文件和 Embedding 内容如何处理；
- 数据保留、日志留存和删除时效；
- 训练用途、客户内容例外和适用产品；
- 子处理者、第三方接收方和跨区处理；
- Singapore/International 的存储与处理地域；
- 条款与当前账号、目标区域、qwen3.8-flash、text-embedding-v4 的适用关系。

## 4. 用户账户侧最小人工核验清单

用户只需观察控制台字段并返回脱敏文字结果或局部截图。不得发送任何 API Key、AccessKey、Secret、Token、Cookie、完整账单或个人敏感信息。

| 核验项 | 建议控制台入口/页面 | 需要观察的字段 | 合格证据 |
|---|---|---|---|
| 账号存在和主体 | Alibaba Cloud Console → Account / Account Center | 账号已登录、主体类型、主账号/项目标识脱敏末尾 | 截图仅保留页面标题和脱敏账号末尾 |
| Model Studio 开通 | Model Studio Console → Model Catalog / Workspace | Model Studio 服务状态、Workspace 和 Region | 页面标题、区域名称和服务状态；隐藏账号、Key、余额 |
| 地区/Endpoint | Model Studio Console → Model / Deployment / Endpoint | Singapore/International endpoint、区域、状态、权限 | 脱敏截图或文字列出区域、endpoint、模型状态 |
| 模型权限 | Model Studio Console → Model Catalog → qwen3.8-flash / text-embedding-v4 | 模型可见、可申请、可调用或配额状态 | 只提供模型名、区域、权限状态和配额类别，不提供 Key |
| 付款/额度 | Billing / Quota / Model Studio Usage | 付款状态、配额类别、是否可配置提醒/停用 | 只提供“可用/不可用”和额度类别，不提供完整账单、卡号或余额 |

用户核验结果也不能替代公开条款。即使控制台全部可用，Data privacy/Terms/Region 仍未取得足够正文时，OPEN-01 仍需保持 BLOCKED。

## 5. 成本防护决策包

当前不能把成本防护标为 Approved。候选默认如下：

- 月软预算：USD 5；
- 达到 USD 4（80%）提醒；
- 达到 USD 5（100%）停止新的 Provider 请求；
- 禁止自动提高额度、自动充值或绕过用户提示；
- 单次 Chat：最大输入/输出 Token、重试次数待 G8/G9 定义；
- 单文件：沿用 PRD 20MB 上限；页数、切片 Token、批量大小和索引重建频率待 G8/G9 定义；
- Embedding：用文件内容指纹 + Provider/模型版本去重，避免重复计费；
- 超限时显示可理解提示、保留本地数据、停止新请求；恢复需要用户明确动作；
- 统计按 Provider、模型、输入/输出 Token、估算费用、任务结果和本地时区记录，不记录正文或 Secret；
- 价格变更不静默接受；检测到价格或区域计费变化时暂停新请求并进入重新确认。

成本防护是当前 G6 的未决 guard。USD 5 及其提醒/停止规则尚未由用户以独立成本决策口令确认，也尚未由 G8/G9 实现。

## 6. G6 Exit Preflight

| 检查项 | 结果 | 说明 |
|---|---|---|
| DEC-G6-002 存在且关系正确 | PASS | 已创建，amends DEC-G6-001 |
| Provider / Chat / Embedding 基线记录 | PASS | A 已条件性应用 |
| no-call 保护与运行时禁用 | PASS | PROVIDER_RUNTIME_ENABLED=false |
| 公开数据处理/保留/训练条款 | BLOCKED | GUARD-PUB-001~005、009 UNVERIFIED |
| 公开地区和模型区域可用性 | BLOCKED | GUARD-PUB-006、007 只有公开目录/页面壳，无法形成完整证明 |
| 用户账户、权限和付款资格 | BLOCKED | GUARD-ACCOUNT-001~005 未有用户证据 |
| 成本防护 | BLOCKED | GUARD-COST-001/002 仍 PROPOSED/NOT_APPLIED |
| 架构 Adapter、安全、错误和禁用开关 | PASS_WITH_TBD | 架构已定义边界；具体实现留 G8/G9 |
| 状态、Evidence、Trace、Context Index 一致 | PASS_PENDING_FINAL_HASH | 本轮同步后重算 |

结论：G6_EXIT=BLOCKED。不能更新为 G6_STATUS=COMPLETED、ARCHITECTURE_STATUS=APPROVED、OPEN-01=RESOLVED 或 G7_ENTRY_GATE=READY。

## 7. 当前状态

```text
G6_EXIT=BLOCKED
G6_STATUS=BLOCKED
ARCHITECTURE_STATUS=DRAFT
OPEN-01=G6_EXIT_BLOCKER
G7_ENTRY_GATE=NOT_READY
G7_EXECUTION=NOT_STARTED
PROVIDER_RUNTIME_ENABLED=false
```

本轮不进入 G7、不调用 Provider、不创建测试/代码/DDL/OpenAPI、不安装依赖、不提交 Git。
