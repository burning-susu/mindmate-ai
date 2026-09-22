# 阶段 3 数据、任务与备份基础报告

> 日期：2026-09-22
> 阶段：3 / 数据模型、任务和备份基础
> 状态：`PASSED`

## 已完成

- 建立核心本地数据模型：ContentObject、File、Folder、Tag、KnowledgeBase、KnowledgeBaseFile、BackgroundTask、TaskAttempt、TaskEvent、AppSetting、ProviderProfile、Backup、BackupEntry。
- Alembic `0002` 自动迁移建立表、外键、唯一约束和任务/备份元数据。
- 任务服务支持幂等创建、lease 领取、checkpoint 版本、进度不可回退、取消和运行中任务恢复为 `INTERRUPTED`。
- 备份服务支持临时包、manifest、schema version、文件 SHA-256、原子重命名、跳过 runtime/logs/cache 和恢复前哈希验证。
- Provider Secret 不进入模型或备份；本阶段未实现真实 Provider 调用。

## 验收证据

| 检查 | 结果 |
| --- | --- |
| 空库 Alembic upgrade | PASS |
| `0002 -> 0001 -> 0002` 迁移往返 | PASS |
| 任务幂等/lease/checkpoint/取消/恢复 | PASS |
| 备份 manifest/hash/敏感目录排除 | PASS |
| Ruff | PASS |
| Pyright | PASS |
| pytest | PASS；9 passed |

## 未覆盖

阶段 4 文件导入、解析器、SHA-256 去重、回收站和文件 API 尚未实现；备份还原 UI 和生产级恢复编排留后续阶段。
