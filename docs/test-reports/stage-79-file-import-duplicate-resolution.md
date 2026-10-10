# 第七十九批：文件重复导入决策与回收站复用修复

- 日期：2026-10-10
- 缺陷：同一内容曾导入后移入回收站，再次上传时进入“等待重复决策”；文件页点击重复决策后仍显示旧任务状态。
- 范围：文件重复决策 API、文件页任务状态和计数展示；无数据库迁移、OpenAPI 契约变化或真实 Provider 调用。

## 根因

1. 内容去重按 SHA-256 命中仍保留的托管内容对象，所以回收站中的文件内容仍会进入重复决策。这与内容对象在 30 天回收站期限内继续保留一致。
2. `REUSE_EXISTING` 原先只寻找 `deleted_at IS NULL` 的 FileRecord。匹配文件只有回收站记录时，API 仍将项目标为 `REUSED`，但 `file_id` 为空，不能重新出现在活动文件列表。
3. 文件页使用 `importTaskQuery.data ?? importResult`。首次读取到 `BLOCKED` 后，决策 mutation 虽更新 `importResult`，页面仍优先渲染旧查询缓存；决策接口错误也没有显示在导入结果区。
4. 旧计数只统计导入/复用与解析失败，没有把待决策项目计入未完成数，形成“0 个已加入，0 个未完成”的误导显示。

## 修复

- 用户选择“复用现有”且没有活动匹配记录时，后端恢复同一内容对象最近的一条回收站 FileRecord，清空软删除时间和期限、恢复解析状态并增加 `row_version`，再沿既有流程建立目标知识库成员关系。
- 重复决策成功后，前端立即更新 `['file-import', import_id]` 查询缓存；请求期间禁用决策按钮，失败时展示 API 错误。
- 导入摘要现在分开展示“已加入、待决策、失败”计数。

## 验证

| 检查 | 结果 |
| --- | --- |
| `backend/.venv/Scripts/python.exe -m pytest tests/test_stage4_files.py -q --basetemp=.pytest-duplicate-restore -p no:cacheprovider` | `7 passed` |
| `backend/.venv/Scripts/ruff.exe check src/mindmate/api/files.py tests/test_stage4_files.py` | 通过 |
| `frontend: npm test -- --run src/test/stage4-files.test.tsx` | `5 passed` |
| `frontend: npm run typecheck` | 通过 |
| `frontend: npm run lint` | 通过 |
| `frontend: npm run build` | 通过；保留既有主包体积提示 |
| `git diff --check` | 通过 |

未做普通 Chrome/Edge 的浏览器 Network 计数或截图验收；上述结果只证明自动化/API 与构建检查。Mock 演示未调用真实 DeepSeek。
