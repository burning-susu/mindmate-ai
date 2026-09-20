# DOCS-UPDATE
> 文档版本：V3.2-GENERIC
> 定位：文档联动更新规则
> 状态：通用基线

## 1. 核心原则

需求事实变化时，先更新事实源，再同步受影响的衍生文档和证据。

标准链：
`Change → Source of Truth → Impact Analysis → Derived Docs → Code → Verify → Evidence → Trace`

## 2. 影响分级

### L1：局部文字/参数
不改变边界、流程和接口契约。

至少确认：事实源、测试、验收、进度。

### L2：业务规则/局部接口/局部数据变化
改变局部实现逻辑或测试范围。

至少确认：事实源、计划、接口/数据、测试、验收、Evidence。

### L3：架构/数据模型/跨模块流程/公共契约变化
必须进行完整影响分析，并检查关联需求。

必要时新增 ADR，并进行 Workflow Rebase。

## 3. 影响对象

变更分析至少检查：

`PRD / Spec / Architecture / Module / API / Data / UI / Test / Acceptance / Release`

## 4. 禁止的同步方式

- 只修改代码，不改事实源；
- 只修改 Spec，不检查测试和验收；
- 修改接口后只改前端调用，不核对契约；
- 用“大段复制”制造多个看似一致的事实源。

## 5. Rebase

当变更导致当前 Workflow 或 Capability 不再适用时：

1. 更新 Assessment；
2. 生成 Change / Rebase 记录；
3. 标记 `KEEP / REVALIDATE / INVALIDATE / ADD / REMOVE`；
4. 更新 Workflow v2；
5. 重新计算当前阶段准入条件。
