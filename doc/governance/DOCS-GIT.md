# DOCS-GIT
> 文档版本：V3.2-GENERIC
> 定位：文档与 Git 联动规则

## 1. Commit 原则

Commit 应描述真实修改，不把治理动作伪装成业务完成。

推荐：
`type(scope): summary`

常见 type：`feat`、`fix`、`docs`、`refactor`、`test`、`chore`、`build`。

## 2. 提交前检查

- 修改是否在当前任务范围内；
- 事实源与代码是否一致；
- 是否需要更新测试/验收/Evidence；
- 是否产生新的 Decision / Change；
- 是否引入新依赖；
- 是否留下调试代码或真实凭据。

## 3. Tag 与回滚

对 L2/L3 或明确的发布候选版本，可创建项目定义的稳定 Tag。

回滚时同时检查：
`Code + Config + Data Migration + Docs + Evidence`

不得只回退代码而留下已失效的文档基线。

## 4. Git 不是唯一事实源

Git 记录“版本变化”；线上实际运行版本、服务器状态、数据库版本等属于运行证据。发布结论应同时引用 Git 证据和运行证据（如适用）。
