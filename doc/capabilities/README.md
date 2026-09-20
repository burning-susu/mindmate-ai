# v3.2 Capability 能力库

本目录存放可按项目 Profile / Assessment / Capability Activation 条件加载的专项能力文档。

## 使用原则

Capability 文档不是“删短后的规范摘要”，而是**完整的可执行知识包**：判断依据、操作步骤、反模式、示例、检查项、Evidence 与验收方式应尽量保留。

项目化时只做四件事：
1. 判断是否激活；
2. 将项目具体选择写入 Profile / Spec / ADR；
3. 将 Capability 规则映射到当前 Stage；
4. 将执行结果记录为 Evidence 与 Trace。

Capability 不应在自身内部再创建一套独立评分器、项目等级或事实源。

## 当前能力

### UI
- `设计稿转代码流程.md`
- `无设计稿单参考同源模式-实操SOP.md`
- `无设计稿双参考异源模式-实操SOP.md`
- `CSS方案选型与Tailwind规范.md`
- `响应式与浏览器兼容清单.md`
- `版心与网格规范.md`

### API
- `RESTful API设计规范.md`

### Testing
- `自动化测试选型与规范.md`
- `性能测试选型与规范.md`
- `安全测试选型与规范.md`
- `TEST-METHODOLOGY.md`

### Platform
- `小程序全栈开发与上线SOP.md`

## 与 Rules 的区别

- `doc/rules/`：稳定、较低歧义的工程规则；用于约束“怎么写”。
- `doc/capabilities/`：按场景激活的专业方法；用于判断“要不要做、怎么选、怎么做、怎么验收”。
- 项目 `Spec / ADR / Contract`：用于确定本项目到底采用哪一种方案。
