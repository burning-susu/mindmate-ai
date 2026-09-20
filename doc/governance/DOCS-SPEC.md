# DOCS-SPEC
> 文档版本：V3.2-GENERIC
> 定位：文档编写与元数据规范
> 状态：通用基线

## 1. 目的

统一治理文档、需求文档、专项能力文档、规则文档和证据文档的元数据、引用和状态表达方式，避免同一事实散落在多份文档中。

## 2. 推荐头部

```text
# 文档名称
> 文档版本：Vx.y
> 文档类型：governance / requirement / architecture / rule / capability / template / evidence / reference
> 关联对象：PROJECT / REQ-XXX / CAP-XXX / RULE-XXX
> 状态：draft / approved / active / superseded / archived
> 生效条件：always / conditional / optional
```

## 3. Single Source of Truth

- 业务规则只在事实源中定义一次。
- `plan`、`test-cases`、`acceptance` 等衍生文档引用规则，不重复抄写整段业务逻辑。
- Rule 描述“如何做”；Capability 描述“什么时候启用以及怎么运行”；Spec 描述“这个项目/需求具体做什么”。

## 4. 引用规则

引用优先使用：

1. 文件路径 + 章节；
2. 稳定 ID；
3. Commit / Tag / 版本号；
4. 必要时补充变更编号。

避免引用易变化的自然语言摘要作为唯一依据。

## 5. 状态

- `draft`：尚未确认；
- `approved`：已确认且可作为事实源；
- `active`：当前生效；
- `superseded`：被新版本替代；
- `archived`：仅供历史追溯。

不得把 `draft` 文档作为当前批准基线。

## 6. 通用库与项目实例

通用文档中使用占位符：`{{project}}`、`{{req_id}}`、`{{stack}}`、`{{provider}}`。

项目事实应进入项目实例文档，而不是修改通用模板去适配某一个项目。

## 7. 证据字段

涉及“完成”的文档，优先包含：

- `evidence_type`；
- `evidence_ref`；
- `verified_at`；
- `verified_by`（如适用）；
- `scope`。

## 8. 归档

废弃文档不要直接删除。标记 `superseded / archived`，说明替代文档及生效时间。
