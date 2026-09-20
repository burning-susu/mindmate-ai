# v3.2 Rules Library

本目录是 v3.2 的**通用执行规则库**。

## Rule 与 Capability 的边界

```text
Rule
= AI 执行时必须/应该遵守的约束
= 短、明确、可判定、可触发

Capability
= 某专业领域完整的做法
= 判断依据 + 方法论 + 操作步骤 + 示例 + 反模式 + 验收
```

因此 Rule 不复制 Capability 的完整内容，而是指向对应 Capability。

## 目录

```text
rules/
├─ core/
│  ├─ CODE-STANDARDS.md
│  ├─ engineering-principles.md
│  └─ userrules.generic.md
├─ frontend/
│  └─ frontend.md
├─ typescript/
│  └─ typescript.md
├─ backend/
│  └─ java-spring.md
├─ testing/
│  └─ testing.md
├─ performance/
│  └─ performance.md
└─ integration/
   ├─ api-contract.md
   ├─ collaboration.md
   └─ exception-handling.md
```

## 激活原则

- `core/*`：默认基础层；
- `frontend/*`：检测到前端范围时激活；
- `typescript/*`：项目使用 TypeScript 时激活；
- `backend/java-spring.md`：项目使用 Java/Spring 时激活；
- `testing/*`：发生测试活动或测试 Capability 激活时加载；
- `performance/*`：存在性能关注点时加载；
- `integration/*`：存在跨端契约、异常或协作场景时加载。

不要一次把整个目录全部塞给 AI。v3.2 的 `CAPABILITY ACTIVATION` 和 Runtime Context 负责按需加载。

## 与 .cursor/rules 的关系

```text
 doc/rules
   = 通用治理源库

 .cursor/rules
   = 当前项目的运行时适配层
```

项目可以从这里选择、裁剪、参数化，再生成当前项目真正启用的 `.mdc` 规则。

## 项目专属规则

旧的：

- 固定项目目录结构；
- 当前仓库真实 API；
- Cesium/Mars3D/MQTT 等具体依赖；
- 当前项目脚本；
- 当前源码事实；

不应直接进入本目录。它们应该留在项目实例层或专属 Rule 中。
