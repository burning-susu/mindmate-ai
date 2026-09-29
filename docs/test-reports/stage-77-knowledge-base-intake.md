# 第七十七批：知识库内直接导入文件与建库闭环

- 日期：2026-09-29
- 分支：`feat/v1-bootstrap`
- 进场 LOCAL / REMOTE：`371243e065737f189075fc6c16cb0d09c416d197`
- 进场工作区：干净；第 76 批提交已存在于本地和远端，未按附件旧报告重置或强推
- 变更记录：[CHG-20260929-KNOWLEDGE-BASE-INTAKE](../project/changes/CHG-20260929-KNOWLEDGE-BASE-INTAKE.md)

## 门禁状态

| 项目 | 状态 | 本批依据与边界 |
| --- | --- | --- |
| `KNOWLEDGE_BASE_INTAKE_CODE` | `PASS` | 建库页混合输入、详情页上传、任务恢复和重复决策实现完成 |
| `KNOWLEDGE_BASE_INTAKE_FRONTEND` | `PASS` | 前端全量 `16 files / 84 tests passed`；新增场景覆盖空库、混合提交、双击、详情上传和复用决策 |
| `KNOWLEDGE_BASE_INTAKE_BACKEND` | `PASS` | 阶段 4 文件契约 `13 passed`；阶段 5 知识库契约 `13 passed`；新增复用成员关系集成用例通过 |
| `DEMO_STABLE` | `PASS（沿用第 42/64 批；本批未做普通浏览器主链路复测）` | 本批自动化证明代码和 API 契约，不提升页面证据等级 |
| `KNOWLEDGE_BASE_INTAKE_BROWSER` | `BROWSER_PARTIAL` | 当前会话没有可绑定的普通 Chrome/Edge 页面；无新 URL、截图或 Network 计数 |
| `STAGE8_FULL_V1` | `PARTIAL` | Windows 恢复锁、Credential Manager、打包启动器、完整学习计划、真实 Provider 和账单对账等独立门禁未改变 |

## 用户操作

1. 打开“知识库 → 新建知识库”，填写名称，可不选任何资料创建空库。
2. 在“初始资料”中勾选已导入文件，并通过“选择文件”加入本地文件；两种来源可以混合。解析失败或等待解析的已有文件保留真实状态，回收站和托管内容缺失记录不显示。
3. 点击“创建知识库”。系统只创建一个库，先提交已有文件成员任务，再提交带当前库 ID 的文件导入任务；随后进入详情页查看成员准入、导入任务、逐文件结果和索引状态。
4. 在知识库详情“资料成员”区域点击“上传新文件”。重复内容在当前库内选择“复用现有 / 另存记录 / 跳过”；上传结果按文件显示，刷新后已提交任务从服务端继续读取。
5. 成员加入不等于索引就绪。按详情页“索引状态与任务”区域的现有受控重建入口启动索引；模型缺失时页面保持离线安全提示，不自动下载或产生费用。

## 实现摘要

- `frontend/src/pages/KnowledgeBaseNewPage.tsx`：增加已有文件筛选、本地 File 选择、混合提交、提交锁、幂等键和任务交接。
- `frontend/src/pages/KnowledgeBaseDetailPage.tsx`：增加当前库上传、重复决策、逐文件结果、任务 ID 和刷新恢复。
- `frontend/src/api/client.ts`、`frontend/src/api/files.ts`、`frontend/src/api/knowledgeBases.ts`：复用现有 API，支持传递稳定 Idempotency-Key，并集中定义文件导入响应类型。
- `frontend/src/App.css`：增加初始资料和文件导入状态布局。
- `backend/src/mindmate/api/files.py`：校验知识库未在回收站；知识库上下文的复用已有文件会恢复/创建成员关系并标记 `PREPARING`。
- `frontend/src/test/stage5-knowledge-bases.test.tsx`：新增混合建库、双击保护和详情重复决策测试。
- `backend/tests/test_stage4_files.py`：新增源文件复用、当前库成员关系、直接导入和跨库复用回归测试。

## 自动化验证

| 命令 | 结果 |
| --- | --- |
| `frontend: npm.cmd test -- --run` | `16 files / 84 tests passed` |
| `frontend: npm.cmd run typecheck` | 通过 |
| `frontend: npm.cmd run lint` | 通过 |
| `frontend: npm.cmd run build` | 通过；主 JS `590.42 kB`，保留既有 500 kB chunk warning |
| `backend: .venv\Scripts\python.exe -m pytest tests/test_stage4_files.py -q --basetemp=.pytest-stage77b -p no:cacheprovider` | `13 passed` |
| `backend: .venv\Scripts\python.exe -m pytest tests/test_stage5_knowledge_bases.py -q --basetemp=.pytest-stage77-kb2 -p no:cacheprovider` | `13 passed` |
| `backend: .venv\Scripts\ruff.exe check src/mindmate/api/files.py tests/test_stage4_files.py` | 通过 |
| `backend: .venv\Scripts\python.exe -m compileall -q src tests/test_stage4_files.py` | 通过 |
| `git diff --check` | 通过 |

默认 pytest 临时根 `C:\Users\15932\AppData\Local\Temp\pytest-of-15932` 在当前执行环境存在 Windows 权限枚举错误；改用仓库内隔离 basetemp 后定向测试通过，没有修改权限或绕过审核。

## 浏览器与外部调用边界

本批没有普通 Chrome/Edge 标签页，未取得页面 URL、截图或 Network 请求计数；没有把 Vitest、pytest 或 API 响应写成浏览器验收。未使用真实 DeepSeek/OpenAI Key，未产生外部 Provider 或付费请求，也未自动下载 ONNX 模型。第 76 批历史删除弹窗的用户复测仍按原报告记录为用户口述，不在本批重复声明。

## 残余风险与阶段状态

- `DEMO_STABLE` 继续沿用既有第 42/64 批证据；本批代码补齐了知识库入口，但没有普通浏览器复测，因此 `KNOWLEDGE_BASE_INTAKE_BROWSER` 保持 `BROWSER_PARTIAL`。
- `STAGE8_FULL_V1` 继续 `PARTIAL`。第 75 批 Windows 恢复 `WinError 5 / RESTORE_DATABASE_LOCKED`、Credential Manager `WinError 1312`、`PACKAGED_LAUNCHER_PARTIAL`、`AC-LEARN-006=PARTIAL`、真实 Provider smoke 和账单核对均未改变。
- 索引仍由现有受控重建 API 启动，避免上传和成员任务各自重复入队；页面会显示成员已加入但索引待建立/构建中。

## Git 交接

本批代码和报告已完成验证，提交信息使用中文一句话：`完善：打通知识库建库与库内文件导入闭环`。本轮收尾后在 `feat/v1-bootstrap` 核对本地和 `origin/feat/v1-bootstrap` 完整 SHA；不强推、不修改 `main`。具体提交与远端 SHA 以最终交付命令结果为准，避免在提交前写入未发生事实。下一批唯一优先主题是普通 Windows Chrome/Edge Guest profile 复测建库混合导入、三种重复决策、刷新恢复和索引等待提示，并记录对象 ID、URL、任务 ID、请求次数和截图。
