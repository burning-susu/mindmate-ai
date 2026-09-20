# folder-structure
> 文档版本：V3.2-GENERIC
> 定位：通用项目文档结构

```text
project-root/
├─ AGENTS.md
├─ doc/
│  ├─ governance/
│  │  ├─ 通用文档提示词v3.2.md
│  │  ├─ 通用文档提示词v3.2完整使用说明.md
│  │  ├─ DOCS-SPEC.md
│  │  ├─ DOCS-UPDATE.md
│  │  ├─ DOCS-GIT.md
│  │  ├─ 执行校准清单.md
│  │  ├─ folder-structure.md
│  │  └─ adr/
│  ├─ rules/
│  │  ├─ core/
│  │  ├─ typescript/
│  │  ├─ backend/
│  │  ├─ testing/
│  │  ├─ performance/
│  │  └─ integration/
│  ├─ capabilities/
│  │  ├─ ui/
│  │  ├─ api/
│  │  ├─ testing/
│  │  └─ platform/
│  ├─ templates/
│  │  └─ requirements/
│  ├─ prompts/
│  ├─ tools/
│  └─ references/
│     └─ visual/
├─ src/
├─ public/
└─ tests/          # 若项目选择独立测试目录
```

## 目录职责

- `governance`：流程、状态、证据、变更和元规则；
- `rules`：可复用约束；
- `capabilities`：专项能力 SOP；
- `templates`：实例生成模板；
- `prompts`：可复用 Prompt；
- `tools`：机械化工具说明；
- `references`：不直接约束实现的参考资料。

项目源码目录由项目自身 Profile 决定，不在这里强制 `src/` 内的具体层级。
