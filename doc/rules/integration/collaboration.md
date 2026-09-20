# Engineering Collaboration Rules
> Rule ID：RULE-INTEGRATION-COLLABORATION
> 生效：CONDITIONAL
> 激活条件：存在前后端、多人、多仓库、AI 与人工协作
> 定位：从旧“global collaboration”规则中抽取的通用协作纪律

## 1. 单一协作契约

团队协作优先依赖项目正式事实源：

```text
Spec / API Contract / ADR / Architecture / Test / Acceptance
```

不要让聊天记录成为长期唯一依据。

## 2. 修改前确认影响面

涉及公共模块、接口、数据库、配置或共享组件时，先搜索消费者和依赖方。

最小检查：

- 调用方；
- 类型；
- 测试；
- 文档；
- 配置；
- 发布脚本（适用时）。

## 3. 前后端联调

联调需要明确：

```text
接口入口
环境
认证方式
请求示例
响应示例
错误场景
测试账号/数据（非敏感）
```

具体 Swagger/OpenAPI、GraphQL schema、Proto 等工具由项目决定，不写死某一工具。

## 4. 变更同步

接口、数据或业务规则发生变化时，不允许只改一侧：

```text
Backend change
    ↓
Contract
    ↓
Frontend / other consumers
    ↓
Test
    ↓
Evidence
```

如果变更只影响单侧实现，也应确认契约是否真的未变化。

## 5. Commit / PR

Commit 和 PR 描述至少应让审查者知道：

- 修改什么；
- 为什么改；
- 影响哪些范围；
- 是否需要特殊测试；
- 是否存在已知限制。

避免一个提交同时包含多个无关主题。

## 6. AI 协作

AI 执行代码前应获得：

- 当前任务 Scope；
- 相关 Spec / Contract；
- 当前代码事实；
- 必要 Capability / Rule。

AI 不能自行把未确认的信息写成正式事实。

## 7. Code Review

Review 不只看代码风格，应重点检查：

```text
需求一致性
契约一致性
影响面
正确性
安全
测试
可回滚
文档同步
```

## 8. 交接

任务交接至少说明：

- 已完成；
- 未完成；
- 已验证；
- 待验证；
- 已知风险；
- 下一步入口。

“代码已经改了”不能单独作为完成证据。
