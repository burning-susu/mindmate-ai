# MindMate AI Current Status

## 基本信息

- 当前开发分支：`feat/v1-bootstrap`
- 当前远程提交：以 `git ls-remote --heads origin feat/v1-bootstrap` 为准；本文件随本批次收口提交推送
- 最后更新时间：`2026-09-25`
- 当前开发阶段：阶段 5 开发中，状态 `PARTIAL`
- 当前批次状态：第二十二批 Citation 绑定因无真实 Chat/Learning owner 而 `BLOCKED` 并延期到阶段 6/7；第二十三至第三十批均为 `PASS`；第三十批完成固定本地 ONNX 模型用户主动安装、可恢复进度/取消/重试与真实浏览器索引闭环；阶段 5 状态仍为 `PARTIAL`

## 已完成阶段

- 阶段 0：工程基线，`114345c`
- 阶段 1：Windows AI/向量 Spike，`741ba6c`；干净 Windows 和正式安装包仍是发布缺口
- 阶段 2：安全本地应用壳，`0b19795`
- 阶段 3：数据、任务和备份基础，`02a32b8`
- 阶段 4：初始实现 `bc30e1f`，证据修订 `9e0174a`，收口修复 `3b29d22`，第四批交接 `0448d5b`；第五批完成数据模型、迁移、乐观锁、解析失败持久化与契约同步；第六批完成持久解析 Worker、原子领取/租约、重试恢复和 Windows Job Object；第七批补齐列表状态恢复并完成最终验收，状态 `PASS`
- 阶段 5：第八批完成空知识库持久化基础；第九批完成成员加入/移出、多库共享、批量准入、持久任务、取消/恢复和前端真实状态闭环；第十批完成索引配置、不可变版本输入快照与可恢复预处理 Worker；第十一批完成可复用版本化 Chunk 与独立可恢复切片任务；第十二批完成固定 ONNX 产物来源、哈希验证与本地 CPU Adapter；第十三批完成持久 EmbeddingRecord、单并发 Worker 与 sqlite-vec 向量写入；第十四批完成按 IndexVersion 隔离的持久 FTS5 投影与逐输入恢复；第十五批完成内部向量 Top-K 与范围过滤；第十六批完成双路 Top 30 候选收集、稳定按 Chunk ID 去重与范围变化复核；第十七批完成内部 RRF、精确命中奖励和确定性多样性 Top 8；第十八批完成内部证据门控与结构化严格拒答；第十九批完成产物完整性复核与原子激活；第二十批完成同一知识库的增量差异计划、Chunk/Embedding/FTS 兼容复用并沿用原子激活；第二十一批完成受服务端范围校验的未绑定来源快照、删除净化和内部读取边界；第二十九批完成索引运维状态、失败诊断、持久重试/重建与浏览器重建；第三十批完成固定 ONNX 的显式安装/校验/恢复与浏览器真实索引；阶段整体仍为 `PARTIAL`

## 当前已实现能力

- 后端：5 类文件导入、托管复制、哈希去重、持久解析 Worker、隔离解析、搜索筛选、文件/文件夹/标签、批量操作、受控内容读取、回收站和永久删除；Folder/Tag 修改、删除与恢复使用数据库原子 `row_version` 乐观锁。
- 任务与资源安全：复用 `BackgroundTask` 实现文件导入/重新处理及知识库成员准入；解析 Worker 与成员 Worker 按任务类型隔离领取，均使用原子领取、租约、过期恢复、关闭中断与取消状态；Windows 解析子进程使用 Job Object 的 `KILL_ON_JOB_CLOSE` 与进程内存上限，默认 `512 MiB`。
- 前端：真实 API 文件工作台、嵌套目录、筛选排序、导入与重复决策、详情编辑/预览、文件和文件夹回收站操作；列表查询参数、详情返回后的筛选/排序/滚动恢复；返回前刷新列表避免旧 `row_version` 竞态；版本冲突提示并引导重新加载，不自动覆盖；第二十四批在知识库详情页增加高级“测试检索”区域，调用现有只读 API，展示三种判定、候选定位与排序信号。
- 模型安装：第三十批在知识库详情页增加固定 ONNX 安装入口，显示来源/许可依据/大小/revision/指纹、本机下载、持久真实进度、取消和重试；仅用户主动点击下载，刷新或应用重启后从持久任务恢复。
- 数据库：SQLite/Alembic 核心实体、持久任务、内容对象引用计数和软删除字段；revision `d91f4a6b2c30` 增加 ChunkingConfig、EmbeddingConfig、IndexVersion 与逐文件输入快照；revision `f2c7a1d8e904` 增加文件级 Chunk 与切片检查点；revision `a81f3c6d2e90` 增加 EmbeddingRecord、逐输入 Embedding 检查点及 INDEX_EMBED 单运行租约约束；revision `d60f2e8a7c31` 增加逐输入 FTS 状态、映射表、FTS5 虚表和 INDEX_FTS 单运行租约约束；revision `e4a7810c9b62` 增加索引激活失败原因码；revision `6b3e91a0c4d7` 增加内部未绑定来源快照和文件永久删除净化触发器。
- 测试与工程：第二十一批新增 10 项服务端快照生命周期/范围/删除用例；第二十四批补充知识库测试检索页面交互回归；完整串行测试与门禁结果见下方测试状态。前端 21 tests 和阶段 4/5 浏览器生命周期证据见测试状态。
- 知识库：空库创建保持 `EMPTY`；名称/描述/颜色/图标编辑；回收站生命周期；已导入文件批量加入/移出、多库共享、幂等重加与逐项结果；成员准入完成后保持 `index_state=PENDING` 和知识库 `PREPARING`，不伪造可检索状态。
- 索引预处理：独立 `INDEX_PREPROCESS` Worker 在请求生命周期外冻结活动成员、内容哈希、解析修订、配置指纹与集合指纹；逐文件记录 `PREPARED/SKIPPED/FAILED`，支持幂等、租约接管、检查点续跑、取消和完成前版本复核。预处理后 `IndexVersion.status=BUILDING`，不会写入 `active_index_version_id`。
- 版本化切片：独立 `INDEX_CHUNK` Worker 仅消费同版本 `PREPARED` 快照；Chunk 按文件/解析修订/切片配置复用，不与知识库绑定；文件级 Chunk 集、切片检查点和任务进度原子提交，支持取消、租约接管、关闭续跑、显式失败重试、多库复用与旧解析/配置版本共存。完成后仍为 `BUILDING` 且不可检索。
- 结构定位：Chunk 记录有效 Unicode 字符长度而不伪造 tokenizer token；保留解析器实际提供的标题路径、PDF 页、PPTX 幻灯片、TXT/Markdown 行及 DOCX 结构块类型。文件永久删除只清理对应 file_id 的 Chunk。
- 前端成员管理：真实文件选择、批量添加、任务轮询、逐项成功/失败、解析状态、待索引状态与移出；刷新后从数据库恢复成员；导入任务终态会再次刷新文件列表，避免异步完成后的旧缓存。
- 本地 Embedding 模型：固定 BAAI 与 Xenova revisions；显式调用时下载到 `.partial`，校验大小、SHA-256 和配置后原子发布；支持超时、并发、取消/重试和离线缺失。Adapter 只启用 CPU，应用启动不加载 ONNX Runtime；来源与 Windows 对照证据见 `docs/project/index-preprocessing-contract.md`。
- Embedding 配置：新默认配置已保存 BAAI 基础 revision、ONNX revision 与 artifact fingerprint 的复合 `model_revision`；既有 `NULL` 行保留用于历史追溯，没有新增数据库结构。
- 持久 Embedding：独立 `INDEX_EMBED` Worker 仅消费仍有效且已 `CHUNKED` 的版本输入；固定配置、模型与 tokenizer 指纹后懒加载现有本地 ONNX，文件级隔离失败、取消、租约续期和中断恢复；EmbeddingRecord 按 Chunk/EmbeddingConfig 跨库复用，sqlite-vec 物理向量按配置与 IndexVersion 隔离，ID/hash 幂等对账后才提交成功检查点。
- 向量 Adapter：在 Windows 文件 SQLite 中校验 512 维、有限单位向量、持久存在性、hash 对账、幂等 upsert 和按 ID/版本删除；扩展加载权限仅在加载期间开启。永久删除知识库只清理其版本向量，保留仍可复用的 Chunk/EmbeddingRecord；永久删除文件清理其向量映射、记录和 Chunk。
- 内部向量 Top-K：`SqliteVecAdapter.search` 校验 512 维单位查询向量和 `k<=30`，全量读取同版本 KNN 候选后先按业务范围过滤，再按距离与记录 ID 稳定排序；`VectorTopKQuery` 重新校验知识库、IndexVersion、成员加入时间、文件解析修订/回收站、Chunk 和 `EmbeddingRecord` 有效性，返回可追溯的 Chunk/File/Version/距离/相似度/rank。内部查询只读、不激活索引；第二十三批增加受本地会话保护的检索测试 API。
- 持久 FTS5：独立 `INDEX_FTS` Worker 只消费同版本有效的 `PREPARED + CHUNKED` 输入；以 `IndexVersion + Chunk` 映射隔离，逐文件 FTS5 行、映射、输入检查点和任务进度在同一主 SQLite 事务提交。支持租约接管、取消、幂等重建和显式失败重试，不修改 Chunk/Embedding 权威数据，也不激活版本。
- 中文关键词投影：FTS5 仍使用 `unicode61` 和 BM25；中文按连续汉字生成重叠二元词及单字辅助列，支持中文短查询；拉丁词项大小写折叠。没有公开 MATCH API 或前端搜索；向量 Top-K、RRF 和证据门控只存在于内部链路及用例。
- 内部检索排序：双路 Top 30 按 `chunk_id` 合并后使用 RRF 常量 `60`，分数为各有效通道 `1/(60 + rank)` 之和；NFKC/大小写折叠后的完整查询短语和精确词项获得最高 `0.004` 的局部奖励；相同来源及相邻高重叠 Chunk 接受有界软惩罚，确定性输出最多 Top 8。结果保留原始双路信号、排序版本/参数、精确命中字段、调整原因和显式降级状态。只读取当前活动 `READY` 版本；`BUILDING` 候选不可进入检索。第二十三批仅通过本地检索测试 API 暴露调试结果。
- 内部证据充分性判定：排序后最多 Top 8 使用版本化规则 `evidence-gate-v1`；要求有效双路排名、校验过的余弦相似度、正文精确术语/编号覆盖和靠前排名，记录问题类型、来源覆盖与触发原因。第二十八批在不改变默认 `0.82` 的前提下增加受 FTS 正文一致性和 vector-only 语义下限约束的可审计例外，并加入精确数值/单位、编号、否定断言和复合子句检查；标题、RRF 奖励、多样性分和纯余弦下降不能单独放行。冲突、缺失子句和无法定位的正文继续严格拒答。`insufficient` 只产生固定本地提示与建议；索引/范围/通道故障返回 `unavailable`，不伪装成资料不足。`supported` 只表示候选可进入后续处理，不是事实证明。检索测试 API 不生成模型回答、Citation 或持久数据。
- 索引激活：新候选只有在最新输入快照、Chunk、Embedding/向量及 FTS 映射/倒排结构对账通过，且任务检查点与配置一致后才能进入短事务切换。构建期间继续读取当前 `READY` 版本；失败不改活动指针，不清理旧版本产物。阶段失败、空库、部分失败和过期候选分别记录 `FAILED`、`EMPTY`、`PARTIAL`/`READY` 和 `SUPERSEDED` 语义。
- 增量索引：预处理任务持久保存 `FULL/INCREMENTAL` 计划与新增、变更、未变、移除、待解析、失败和复用数量。复用要求内容哈希、解析修订、切片配置指纹、Embedding 模型/版本/维度/归一化/距离配置和向量引擎兼容；未变 Chunk 不再解析切片，已有 EmbeddingRecord/向量按版本复制且不会调用 ONNX，FTS 投影复用后仍接受候选全量完整性复核。配置不兼容进入完整重建；复用源失效则回退到既有计算阶段。
- 服务端来源快照：只消费内部混合检索产生且证据门控为 `supported` 的候选身份；在 SQLite 写事务中先取得写锁，再重查活动 READY 索引、知识库成员、文件版本/解析修订、Chunk、FTS 映射和 EmbeddingRecord。快照只保存数据库来源名、真实定位、受控摘录与哈希，不接受请求侧路径/正文；按知识库/索引版本/Chunk 幂等。读取动态报告回收站、范围和旧索引状态，不返回磁盘路径；永久删除文件净化摘录/正文哈希并断开文件与 Chunk 关联。

## 当前已知缺口

- 阶段 4 无未解决功能、安全、数据一致性或迁移阻塞项；需求追踪详见 `docs/test-reports/stage-4-file-management.md`。
- 发布候选保留：正式恶意文档集、真实资源耗尽边界、干净 Windows 安装/升级/卸载包，依据发布流程执行，不回填为阶段 4 已完成证据。
- 阶段 5 缺口：来源快照 owner/Citation 绑定（延期到阶段 6/7）、用户级严格拒答/RAG 流程、固定样本之外的质量/性能评估仍未完成；第二十八批只完成固定 31+7 样本的门控校准回归。`supported` 不证明候选蕴含事实；本地调试端点和本批页面不构成 AC-KB-003、Recall@10 或聊天验收。

## 第十八批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。
- 实现：内部 Top 8 之后新增 `evidence-gate-v1`；保留 Chunk/File/IndexVersion 身份和可审计信号；错误/降级/不完整索引映射到 `unavailable`，只有资料不足返回固定本地提示。没有模型调用、回答生成、引用编号或公开 API。
- 验收：串行后端 `133 passed`；`ruff check src tests` 通过；Pyright `0 errors`；compileall 和 `git diff --check` 通过。全目录 `ruff check .` 另报 14 条既有 Alembic migration lint 问题，本批未修改迁移文件。
- 全量测试曾有一次既有 Embedding Worker 互斥用例失败；单项重跑和随后全量重跑均通过，最终全量为 `133 passed`。
- 下一开发批次唯一目标：为已完成索引版本实现产物完整性复核与原子激活，继续不开放用户检索。

## 第十九批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。
- 开工仓库证据：本地与 `origin/feat/v1-bootstrap` 起始 SHA 均为 `6a3c9976d6cd4531de661e2cc267d7ba655b3dc6`，工作区干净。
- 生命周期：有效输入快照、配置指纹和最新阶段任务链均复核后，才允许候选激活。所有 `PREPARED` 文件的 Chunk 正文/数量、EmbeddingRecord/向量 ID/hash/维度/范数、FTS5 完整性和版本映射逐项对账；空知识库落为 `EMPTY`，至少一个完整文件可用时支持 `PARTIAL`，没有完整可用文件时落为 `FAILED`，过期候选标记 `SUPERSEDED`。
- 原子切换：事务外做持久产物核验；短事务通过知识库 `row_version` 与预期活动指针 CAS，并再次校验输入、配置、任务终态和候选最新性，然后一次提交新版本 `READY`、旧版本 `RETIRED`、活动指针及成员可用状态。失败、抢占或测试注入事务错误均保留旧指针和旧产物。
- 可恢复性：应用启动后持久激活扫描器重复检查仍处于 `BUILDING` 的候选；提交前崩溃保持候选待检并可重跑；提交与指针切换处于同一 SQLite 事务；重复检查已激活版本幂等返回。软删除/解析中输入等待既有恢复或永久清理流程。
- 检索边界：内部向量与混合查询只接受知识库当前指向的 `READY` 版本和 `index_state=READY` 成员；构建候选不可读，部分失败文件不会进入有效查询范围。没有公开检索 API、OpenAPI 或前端变更。
- 验收：串行后端全量 `147 passed`；`ruff check src tests`、Pyright（0 errors）、compileall、Alembic head `e4a7810c9b62` 和 `git diff --check` 通过。`ruff check .` 仍有 14 条既有 Alembic lint 项，无本批新增。未运行 UI E2E、未调用 DeepSeek/真实凭据/付费服务或真实用户资料。
- 下一开发批次唯一目标：实现同一知识库的增量索引构建策略，继续保留版本快照及原子激活边界。

## 第二十批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。没有迁移、公开 API/OpenAPI、前端改动或外部模型请求。
- 判定键：成员范围和加入时间属于候选输入快照；文件产物复用要求 `file_id + content_hash + parse_revision_id`，再匹配 ChunkingConfig 全字段指纹、EmbeddingConfig（provider/model/model_revision/dimension/normalization/distance）全字段指纹和 sqlite-vec 引擎。指纹与实际配置字段不一致时按不兼容处理。
- 复用与重算：未变文件复用已存在 Chunk；逐文件 EmbeddingRecord/向量复用通过向量库哈希对账并写入新 IndexVersion 隔离空间，不调用 ONNX；FTS 从兼容完成版本复制映射/投影字段。新增/变更/缓存不可用文件仍走现有 `INDEX_CHUNK → INDEX_EMBED → INDEX_FTS`，失败使用原 `PARTIAL/FAILED` 状态和重试入口。移除成员不清理源文件、历史版本、其他成员可复用的 Chunk/Embedding；活动查询范围立即按当前成员过滤。
- 任务与故障：增量计划和逐输入复用来源写入现有任务检查点/输入原因字段，无新增 schema。相同输入和配置的重复提交返回原候选；输入快照变化时允许新候选排队，较旧候选沿用激活器的 `SUPERSEDED` 规则，避免自动无限重试。旧活动指针在候选校验和原子切换前保持不变。
- 验收：后端全量串行 `153 passed`；新增用例验证新增、文件内容替换、成员移除、跨知识库兼容复用、Embedding 维度/配置不兼容全量重建、重复候选幂等；未变文件 Embedding Mock 调用数不增加。Chunk、向量及 FTS 产物通过第十九批激活器复核后才切换。Ruff、Pyright、compileall、Alembic head `e4a7810c9b62` 与 `git diff --check` 通过；全目录 Ruff 仍有 14 条既有迁移 lint。未运行 UI E2E 或调用 DeepSeek/真实凭据/真实用户资料。
- 下一开发批次唯一目标：为活动索引建立持久化的服务端来源快照，并校验来源仍属于该知识库的活动版本范围。

## 第二十一批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。本地/远端起始 SHA：`767d2859b7f16090167e3d8569652a7a2010a131`。
- 数据：Alembic revision `6b3e91a0c4d7` 新增只允许 `UNBOUND` 的内部 `SourceSnapshot`，保存知识库/索引版本、文件版本与解析修订、可空 Chunk/File 关系、标题路径、实际页/幻灯片/行定位、最多 1200 字符的 Chunk 摘录、SHA-256 和创建时间；以知识库/索引版本/Chunk 的摘要键保证幂等。当前没有聊天/学习 owner，不生成伪 Citation owner 或显示编号。
- 创建范围：只接收内部 `HybridAssessmentResult` 且 evidence gate 为 `supported` 的检索候选；新 SQLite 写事务先串行化后再校验活动指针、READY 状态、当前 ACTIVE/READY 成员、文件内容哈希与解析修订、版本输入、Chunk 正文哈希、FTS 映射和有效 EmbeddingRecord/配置指纹。范围变化、索引版本变化和来源失效使用不同错误码；候选正文/文件名必须与数据库再读值一致，最终快照字段只从数据库生成。
- 读取与删除：内部读取动态判断文件回收站、版本变化、成员范围和活动索引状态；不返回本地路径。回收站可读历史摘录但不可打开；索引重建后快照继续指向原 IndexVersion。永久删除文件时服务和 SQLite 删除触发器都会清理摘录、正文哈希/版本和 File/Chunk 关系，保留文件名及定位；永久删除知识库清理尚未绑定 owner 的快照。
- 验收：新增 `tests/test_stage5_source_snapshots.py` 10 项，覆盖真实内部 FTS5+sqlite-vec→证据门控→持久化、应用重启读取、恶意路径/文件名和任意 Chunk ID、跨库/成员移除/重加/回收站/坏映射、活动指针与成员竞态、幂等、历史版本保留、定位空值和永久删除净化。全量测试和静态门禁结果见测试状态。
- 本批没有公开检索/Citation API、OpenAPI、前端、消息/学习 owner、DeepSeek 或其他真实外部调用；不代表最终答案事实正确，也不构成 AC-KB-003、Recall@10 或质量性能验收。
- 下一开发批次唯一目标：定义并实现来源快照到真实 Chat/Learning owner 的服务端 Citation 绑定边界，暂不生成模型回答。

## 第二十二批依赖处理

- 第二十二批 `BLOCKED`：当前没有持久化 Chat/Learning owner 与可验证知识库范围快照；不得用 `TaskAttempt` 冒充学习会话，也不得伪造 owner 或 Citation。
- 当时工作区保持干净，起止本地/远端 SHA 均为 `e1766c3d173f4613e368bbb8988a343ca207738e`，没有代码、文档、测试或提交变化。
- Citation 绑定依赖延期到阶段 6/7 建立真实 owner 后再做；不阻塞不依赖 owner 的第二十三批本地检索测试接口。

## 第二十三批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `e1766c3d173f4613e368bbb8988a343ca207738e`。
- 新增 `POST /api/v1/knowledge-bases/{knowledge_base_id}/retrieval-tests`。请求只接受经长度验证的问题，不接受调用方指定索引、文件集合、Embedding 模型或路径；继承本地 Host、Origin、本地会话与幂等键保护。
- 服务端固定读取当前活动 `READY` 索引，编码前捕获索引/成员/文件/Chunk/Embedding 范围指纹，并与检索阶段校验值比较。复用 FTS5/vector 双路 Top 30、RRF 与规则重排 Top 8、`evidence-gate-v1`；索引/范围变化与单路错误显式返回 `unavailable` 及原因码/路由。
- 本地模型只在端点调用时懒加载，读取固定安装路径并调用 `allow_download=false`。缺失/损坏与资料不足分开报告；不调用 DeepSeek/Provider，不创建任务、消息、来源快照、Citation 或回答。
- 候选输出文件/Chunk 身份、真实页/幻灯片/行/标题定位、受控片段和双路排名/分数；最多 8 个候选、每个摘录最多 1200 字符，完整响应不超过 64 KiB。同步 OpenAPI 3.1 与前端生成类型/客户端；没有新增页面或数据库迁移。
- 后端 API 集成矩阵覆盖 `supported/insufficient/unavailable`、空库、离线缺失模型、坏输入/越权范围字段、本地 Origin/Session 保护、跨知识库、当前活动版本与待索引成员、回收站、索引/成员竞态、FTS/vector 故障与无数据库写入。串行全量 `176 passed`；`uv run ruff check src tests`、Pyright（0 errors）、compileall、Alembic head `6b3e91a0c4d7` 均通过。前端 API 类型生成、typecheck、lint、build 通过；没有页面改动，未跑 UI E2E。
- 验收边界：第二十二批 owner/Citation 绑定仍延期到阶段 6/7；本地检索测试不是聊天/答案 API，也不代表 `AC-KB-003`、最终 Recall@10、阈值校准或性能验收通过。

## 测试状态

- 后端测试：`176 passed, 143 warnings`（最终串行全量，含第二十一批来源快照用例与第二十三批只读检索 API 集成矩阵）
- 阶段 4 后端定向测试：`21 passed`
- 后端静态检查：本批 `uv run ruff check src tests` 与 `uv run pyright src tests` 通过（Pyright `0 errors, 0 warnings, 0 informations`）。本批未运行 `ruff check .`；历史全目录扫描的既有 Alembic lint 项未修改。
- 后端 compileall：通过
- 前端测试：`13 passed`（第二十三批）
- 第二十四批前端测试：`21 passed`（6 个 Vitest 文件）
- 前端类型检查：通过
- 前端 lint：通过
- 前端构建：通过
- 浏览器 E2E：阶段 4 文件回归与阶段 5 知识库历史用例共 `2 passed`（各 1 项）；第二十五批新增真实 READY 检索浏览器用例 `2 passed`，使用固定 ONNX、隔离数据根目录和真实 FastAPI + Vite。
- 第二十四批浏览器证据：真实本地 FastAPI + Vite（允许来源 `127.0.0.1:5173`）创建空知识库后打开 `/knowledge-bases/:id`，页面显示测试检索入口、长度限制和“索引待开放”；用键盘 Tab/Enter 提交后真实 API 返回 `unavailable / INDEX_VERSION_NOT_AVAILABLE`，未误报为资料不足；`390x844` 窄屏无障碍树仍能读到输入、按钮和结果状态。没有可用 READY 固定资料，因此没有把 Vitest Mock 候选显示写成真实检索浏览器验收。
- 第二十五批浏览器证据：真实本地 FastAPI `127.0.0.1:8000` 与 Vite `127.0.0.1:5173`；Chromium 桌面 `1440x1000`、窄屏 `390x844` 均通过 Tab 到提交按钮再按 Enter 的真实网络请求；主库候选文件名、摘录与 API `line_start` 相符。目标问题与相似干扰库问题均如实标为 `insufficient`（余弦相似度分别 `0.5867`、`0.6568`，低于既有 `0.82` 阈值）；回收站样本未泄漏，资料外问题为 `insufficient / NUMERIC_ANSWER_VALUE_NOT_FOUND`，没有答案或 Citation 字段。截图位于 `%TEMP%\mindmate-ai-stage5-fixed-ready\evidence\`。
- OpenAPI 同步：OpenAPI 3.1，`38 schemas / 51 operations`；新增本地检索测试请求/响应类型与操作
- 数据库迁移：最新 revision `6b3e91a0c4d7`；空库升级/降级/重升级及阶段 5 既有数据迁移回归通过。

## 第二十四批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `2ffe354b3efaa72e10c4d71a9978001750c35019`。
- 页面入口：`/knowledge-bases/:id` 详情页底部的高级“测试检索”区域；知识库名称、文件数和当前索引状态仍在详情头部显示。问题框限制 2000 字符，空/纯空白问题不提交，提交中禁用按钮并提供可感知的加载状态。
- API 边界：通过现有 `runKnowledgeBaseRetrievalTest` 客户端只发送 `{ question }` 和路径中的知识库 ID；不保存问题或结果，不触发索引、模型下载、Provider、任务或 Citation。响应最多展示 8 个候选，使用纯文本渲染文件名、摘录、标题/页/幻灯片/行定位、通道 rank/分数和排序说明；缺失信号显示“无”，不显示引用编号或回答。
- 状态与竞态：分别呈现 `supported`、`insufficient`、`unavailable`；无活动索引、模型缺失、通道错误、范围变化和空结果保持不同文案；请求错误保留输入并可重试。AbortController、序列号和按知识库 ID 的组件卸载保证连续请求、切换问题、切换知识库和卸载后的旧响应不会覆盖当前结果。
- 验收证据：前端 Vitest `21 passed`；`npm run typecheck`、`npm run lint`、`npm run build`、`git diff --check` 均通过。真实浏览器仅验证空知识库和无活动索引状态，候选 Top 8/HTML 片段安全/错误重试等使用确定性 UI Mock 回归，不冒充真实索引验收。
- 本批没有后端改动、数据库迁移或 OpenAPI schema 变化；未为凑数重跑后端全量。第二十二批 Citation owner 绑定继续延期到阶段 6/7。

## 第二十五批交接

- 本批结论：`PASS`；阶段 5 继续 `PARTIAL`。起始本地/远端 SHA 均为 `63bca0d73d66ac0810ae394d8545cb19ce1110cb`。
- 固定资料与隔离：新增 `docs/test-data/stage5-fixed-ready/` 三份合成 TXT，准备脚本建立主库、相似干扰库和无索引诊断库。默认数据根为 `%TEMP%\mindmate-ai-stage5-fixed-ready`，所有权标记保护已有非空目录；重复两轮检查文件/库/任务数不变，结果为 3 个文件、3 个库、13 个任务。脚本不会清理该目录。
- 模型与 READY：`backend/model-cache/manager-validation` 的固定 BAAI/Xenova manifest 离线校验为 `READY`；revision、大小、SHA-256 和 fingerprint 复核后复制到隔离根并复验，无联网或下载。通过文件导入 API、知识库/成员 API 与 `INDEX_PREPROCESS → INDEX_CHUNK → INDEX_EMBED → INDEX_FTS → IndexActivationWorker` 建立真实本地 ONNX 索引；主库和干扰库均有活动 `READY` 版本。Chunk、EmbeddingRecord、sqlite-vec 向量和 FTS 映射数逐项相等，FTS integrity/consistency、向量 SHA-256/512 维/有限值/单位范数及持久任务检查点均通过。
- 检索结果：主库问题返回 `服务超时策略.txt` 的真实候选、原文 `30 秒` 和第 1 行起始定位；相似干扰库问题只返回其自身 `47 秒` 文件。证据门控均为 `insufficient / VECTOR_SIMILARITY_BELOW_THRESHOLD`，主库余弦相似度 `0.5867`、干扰库 `0.6568`；没有调整既有阈值。回收站专属文件、名称与摘录未泄漏。资料外问题返回 `insufficient / NUMERIC_ANSWER_VALUE_NOT_FOUND`，API/UI 未生成答案或正式引用。
- 验收：后端串行 `uv run pytest` 为 `176 passed, 143 warnings`；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py`（0 errors）、`uv run python -m compileall -q src tests migrations scripts`、`uv run alembic heads`（`6b3e91a0c4d7`）通过。前端 `npm run typecheck`、`npm run lint`、`npm test -- --run`（21 passed）、`npm run build` 通过；真实 Chromium Playwright `2 passed`；`git diff --check` 通过。浏览器截图保存在 `%TEMP%\mindmate-ai-stage5-fixed-ready\evidence\`。
- 未验证范围：固定样本只证明当前本地运行闭环，不替代 Recall@10、10 万 Chunk 性能、阈值校准或 AC-KB-* 全量验收。未调用 DeepSeek、真实凭据、付费服务或个人资料；Citation owner 仍延期到阶段 6/7。

## 第二十六批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`。起始本地与远端 SHA 均为 `3ef9a33adcdae5adb06e6a6835d44fdbbf84ed3d`。
- 评测集：31 条核心人工标注查询与 2 条 `needs_review`；标注独立于检索输出，覆盖直问、改写、编号/近似编号、错误数值、无答案、短词干扰、跨库、回收站、复合问题和显式冲突。评测语料仅为合成资料，隔离数据根为 `%TEMP%\mindmate-ai-stage5-evidence-gate-v1`。
- 真实检索结果：门控混淆表 TP `0`、FN `16`、FP `0`、TN `15`。16 个假阴性均在 Top 8 含标注支持文件；顶层原因 11 个 `VECTOR_SIMILARITY_BELOW_THRESHOLD`、3 个 `NUMERIC_ANSWER_VALUE_NOT_FOUND`、2 个复合问题拒绝。无召回缺失型假阴性、无假阳性、无跨范围候选。全部 33 次检索均 `insufficient`，没有 `unavailable`。
- 排名与分数：首轮 Top 8 共 101 条候选，Vector 命中 101、FTS 命中 2（均为双路命中），99 条 Vector-only、0 条 FTS-only；两条 FTS 命中来自短词拒答项。最终/原始排名和余弦一致性检查均通过。相似度 min/median/max 为 `0.3356/0.4835/0.7127`；16/16 可回答查询的人工标注文件出现在 Top 8。
- 规则敏感性：只在已观察 Top 8 候选上模拟 `0.65/0.70/0.75/0.82/0.85`，混淆表没有变化；未改生产 `evidence-gate-v1` 配置或 `0.82` 门槛。单独调低余弦下限不足以解决当前误拒。
- 复跑：最终脚本两次独立运行，每次 `--repeat 2`，每次内部签名稳定；两次独立报告签名均为 `c5d216439163910865464f3130edc1eafd18a445978c2d3ca42cafb0aabd4931`。查询前后计数均为 9 files / 4 knowledge bases / 24 tasks，没有评测写入。报告位于隔离根的 `stage5-evidence-gate-v1-report.json`。
- 验收：串行 `uv run pytest` `179 passed, 143 warnings`（2:22）；Ruff 全目录通过；Pyright `0 errors, 0 warnings, 0 informations`；compileall、Alembic head `6b3e91a0c4d7`、`git diff --check` 通过。未改前端，未运行前端门禁。
- 下一开发批次唯一目标：以固定人工查询集测量中文自然问句的 FTS5 命中与 hard-negative 分布，先定位 FTS 候选召回问题，不调整证据门槛。

## 第十三批交接

- 本批状态：`PASS`；阶段 5 仍为 `PARTIAL`。
- 数据：Alembic `a81f3c6d2e90` 新增 `EmbeddingRecord` 与 `IndexVersionInput.embedding_status/embedding_reason_code/embedding_count/embedded_at`；每个记录保存稳定 Chunk/配置映射、配置指纹、向量记录 ID、SHA-256、状态和失效时间，不把原始向量写入业务表。
- Worker：新增独立 `INDEX_EMBED`，SQLite 部分唯一索引和原子租约将运行并发限制为 1；只消费 `PREPARED + CHUNKED` 输入，批量最多 16，按文件持久检查点；校验成员、回收站、内容哈希、解析修订、切片/Embedding 配置及模型/tokenizer 固定指纹。
- 一致性：先持久化预期向量 hash，再对配置/IndexVersion 隔离的 sqlite-vec 文件数据库做 ID 幂等 upsert，最后在事务中提交 `EmbeddingRecord.READY` 和输入检查点；重启可双向校验数据库映射与实际向量并恢复写后中断。逐文件失败可重试，取消/失效输入不发布成功状态。
- 复用与清理：共享 Chunk + EmbeddingConfig 的多个知识库不重复推理，但各 IndexVersion 分别持久化向量；删除一个知识库只删除其版本向量空间并保留共享记录，永久删除文件先清理其相关版本向量和 EmbeddingRecord 再删除 Chunk。
- 实际模型证据：读取并校验 Git 忽略的 `backend/model-cache/manager-validation` 固定 manifest 缓存为 `READY`，无网络、无下载地由本地 ONNX Worker 处理固定离线文件；实际持久输出为 512 维、有限且 L2 单位范数。缓存没有加入 Git 或被清理。
- 验收：后端全量 `97 passed`；Ruff、Pyright `0 errors`、compileall、离线 uv lock 校验通过；真实 FastAPI/Vite 阶段 4/5 Playwright `2 passed`；迁移往返与 SQLite `quick_check=ok`。任务完成后 `IndexVersion.status=BUILDING`、`active_index_version_id` 未变，`available_for_retrieval=false`。
- API/OpenAPI：没有增加路由或 schema，复用已有任务详情/取消契约（`34 schemas / 50 operations`）；无前端改动，不调用真实 Provider。

## 第十四批交接

- 本批状态：`PASS`；阶段 5 仍为 `PARTIAL`，知识库与 IndexVersion 均不可检索。
- 数据：Alembic `d60f2e8a7c31` 增加 `IndexVersion.fts_status`、`IndexVersionInput.fts_status/fts_reason_code/fts_count/fts_indexed_at`、按版本/文件/Chunk/解析修订/切片配置/内容哈希映射的 `fts_chunk_map`，以及 FTS5 虚表 `index_chunk_fts`；数据库部分唯一索引限制至多一个 `INDEX_FTS/RUNNING` 任务。
- Worker：新增独立持久 `INDEX_FTS`。只处理仍有效的 `PREPARED + CHUNKED` 输入；任务租约过期接管、应用关闭续跑、取消、逐文件失败与显式重试均保留检查点。每文件的虚表行、映射、输入状态和任务 JSON 检查点在同一业务 SQLite 事务提交。
- 投影：每个 FTS 行通过 `index_version_id + chunk_id` 唯一隔离并回溯文件、解析修订、切片配置和正文哈希；新 IndexVersion 不清空旧版本。基于 Chunk 可重建投影，映射对账与 FTS5 `integrity-check` 可分辨投影缺失/不一致与虚表内部损坏。
- 分词与生命周期：使用 `unicode61 remove_diacritics 2`；连续汉字建立重叠二元词和单字列，固定中文短查询及英文词样本通过。软删除/移出查询内部校验当前成员、回收站、内容哈希、解析修订和 FTS 状态。知识库永久删除只清其版本投影；文件永久删除清该文件的投影/输入并使仍有其他输入的未激活版本进入 `NEEDS_REBUILD`，保留其余文件 Chunk 与 FTS 映射。
- 迁移回退：降级只删除 FTS 虚表、映射及 FTS 检查点列；Chunk、EmbeddingRecord 和向量数据不删。再升级后 FTS 投影为空，可由 `INDEX_FTS` 的重建任务从 Chunk 恢复。
- 边界：不实现公开检索 API、向量 Top-K、RRF、混合检索、索引激活、引用、RAG、UI 或 API schema；OpenAPI 仍为 `34 schemas / 50 operations`，Provider 仍 Mock-only。
- 验收：后端 `105 passed`；Ruff、Pyright `0 errors`、compileall 通过。迁移空库/既有数据、允许范围内降级/再升级、SQLite quick/integrity/投影对账通过；第十四批不改变前端。

## 第十五批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`，知识库仍不可检索。
- 代码：新增 `VectorTopKQuery` 内部用例和 `SqliteVecAdapter.search`；不新增迁移、API/OpenAPI、前端或 Worker。
- 范围：同一 `IndexVersion`、同一 EmbeddingConfig、当前 `ACTIVE` 成员、未回收文件、匹配解析修订/内容哈希、有效 Chunk 与 `EmbeddingRecord.READY` 才能进入候选；移出/重加、知识库或文件回收站、版本失效、Chunk/记录失效立即排除；共享文件在另一知识库的有效版本仍可查询。
- 排序：单位向量使用 sqlite-vec 默认 L2 距离，应用转换为余弦距离/相似度；等分按稳定 `vector_store_record_id` 排序；`k` 默认为并最大为 30。
- 证据：新增 `tests/test_stage5_vector_search.py`，固定 512 维向量验证近邻、范围外更近向量、同分、空结果、坏维度/归一化、配置/版本隔离、生命周期和向量库异常；查询后 `IndexVersion.status=BUILDING`、`active_index_version_id` 不变。
- 性能边界：因现有向量表没有动态成员分区，Adapter 读取全量 KNN 行后在排序前过滤，保证召回正确但查询成本为 O(N)；本批没有做 10 万 Chunk 性能声明。
- 验收：后端全量 `112 passed`；Ruff、Pyright、compileall、`git diff --check` 通过；未改前端、OpenAPI 或真实 Provider。

## 第十六批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`，知识库仍不可检索。
- 代码：新增 `HybridCandidateQuery`、`merge_candidates` 与 `query_hybrid_candidates` 内部用例；增强 FTS5 查询规范化、Top 30 限额、BM25/稳定 `fts_rank` 输出和知识库范围校验；不新增迁移、API/OpenAPI、前端或 Worker。
- 双路范围：同一 `IndexVersion` 内 FTS5 和 sqlite-vec 各自先校验当前成员、加入时间、知识库/文件回收站、解析修订、内容哈希、Chunk 有效性；向量路另校验 EmbeddingConfig、EmbeddingRecord 和向量 hash，再各取 Top 30。范围外高排名候选不会挤占范围内名额。
- 合并语义：按 `chunk_id` 去重，保留 `fts_rank`/`bm25` 与 `vector_rank`/距离/相似度，单路命中另一通道字段保持 `NULL`；保留文件 ID、IndexVersion ID 和来源通道，输出使用确定性排序，不执行 RRF、最终 Top 8 或多样性处理。
- 安全边界：双路前后生成版本、成员、文件、Chunk 和 EmbeddingRecord 范围指纹；中途变化返回 `RETRIEVAL_SCOPE_CHANGED`。路由故障默认显式失败；明确允许降级时返回可用单路和错误码，不把故障伪装成双路成功。
- 证据：`tests/test_stage5_vector_search.py` 使用真实 SQLite FTS5/sqlite-vec 夹具覆盖双路同 Chunk、FTS-only、Vector-only、成员中途移出、向量存储故障和稳定去重；FTS 测试覆盖中文短词、英文、编号、空输入和特殊符号。
- 性能边界：向量查询仍是第十五批记录的精确 O(N) 过滤策略；本批只增加候选合并，没有 10 万 Chunk 性能声明。
- 验收：后端全量 `117 passed`；Ruff、Pyright `0 errors`、compileall、`git diff --check` 通过；未改前端、OpenAPI、迁移或真实 Provider。

## 下一开发批次

- 阶段 5 下一个唯一目标：用固定人工查询集测量中文自然问句的 FTS5 命中与 hard-negative 分布，定位双路候选召回问题；不调整证据门槛。

## 交接说明

- 新对话必须读取：`AGENTS.md`、`docs/project/requirements/v1/18_最终决策表.md`、`16_Codex开发任务书.md`、`05_知识库与RAG详细需求.md`、本文件、`v1-development-progress.md` 和阶段 5 测试报告。
- 从远程 `origin/feat/v1-bootstrap` 最新提交继续；先核对 `git status --short` 和本地/远程 SHA，不依赖旧对话。

## 第二十七批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`。进场本地与 `origin/feat/v1-bootstrap` SHA 均为 `2f8025692580f69de4e3f57598efd39d8abc17de`，工作区干净；本批未改数据库 schema、公开 API、前端、证据门控阈值或 Provider。
- FTS 根因：索引侧已经把连续汉字投影为重叠二元词和单字辅助列，但查询侧把整段中文自然问句放进一个带空格的 FTS5 引号短语，要求所有二元词连续且全部存在。问句中的“是多少/是否/等多久”等不在原文时，精确标题、编号和关键中文词项因此全部失配；这与索引损坏、模型或版本不一致无关。
- 具体修复：`backend/src/mindmate/infrastructure/fts5.py` 保留 NFKC、SQLite 参数绑定和逐词引号转义；ASCII 词项/数字继续精确 `AND`，每段中文使用有界二元词 `OR` 组，去除仅用于 FTS fallback 的疑问脚手架和句末语气词；MATCH 后按每段至少 2 个中文二元词（含数字/编号时至少 1 个）过滤，再返回 FTS Top 30。原有 FTS5 表结构、`unicode61`、索引 Worker、映射和旧索引兼容路径无需迁移或重建。
- 真实前后对比：同一固定 READY 数据、同一真实本地 ONNX 与 `--repeat 2` 复跑，旧基线 Top 8 为 101 条候选、FTS 命中 2（Vector-only 99）；修复后仍为 101 条候选，FTS 命中 20、双路命中 20、Vector-only 81、FTS-only 0。`API 单次请求超时时间是多少秒？`、自然改写、演练库标题/编号、`CACHE-PROXY-K3` 均出现真实 FTS 候选；错误数字/错误编号仍无 FTS 命中。
- 旧核心集：31 条人工标注仍为 TP `0` / FN `16` / FP `0` / TN `15`；16 条 FN 均在 Top 8 找到标注支持文件，仍由现有严格 `evidence-gate-v1`（主要是 `VECTOR_SIMILARITY_BELOW_THRESHOLD`）拒答，没有把召回修复冒充成门控通过。两轮内部签名稳定，查询前后资源计数不变。
- 困难负例：新增 `docs/test-data/stage5-fixed-ready/evidence-gate-v1-hard-negatives.json`，独立人工标注 7 条，覆盖同名跨库 30/47 秒、错误数字、相同术语无事实、相反表述和回收站；混淆表 TN `7` / FP `0`，跨范围候选 `0`。失效索引另做两轮可用性检查，均为 `unavailable / INDEX_VERSION_NOT_AVAILABLE`、0 候选，不计入混淆表。
- 可复现评测：首次复用旧评测目录因所有权标记缺失被保护逻辑拒绝，未接管或清理旧数据；随后使用 `%TEMP%\\mindmate-ai-stage5-evidence-gate-v1-r27` 完成真实准备和评测。报告位于该隔离根的 `stage5-evidence-gate-v1-report.json`，记录查询 token、实际 MATCH 表达式、存储侧 token、关键词排名、向量候选、Top 8 和门控理由。
- 验收：`uv run pytest` `181 passed, 143 warnings`（串行，约 2:26）；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py`（0 errors）、`uv run python -m compileall -q src tests migrations scripts`、`uv run alembic heads`（`6b3e91a0c4d7`）和 `git diff --check` 通过。新增定向 FTS/评测测试均通过；未改前端，因此未运行前端门禁。
- 下一开发批次唯一目标：在不放松证据门控和不引入 Provider 的前提下，针对仍保留的 16 条 FN 建立人工可解释的门控/答案质量校准方案，并继续保持阶段 5 `PARTIAL`；不得重新调整 FTS 召回范围或生产阈值而不附新证据。

## 第二十八批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`。进场本地与 `origin/feat/v1-bootstrap` SHA 均为 `b2ddc62bade9517272e06d761fd5f30e392bee92`，工作区干净；本批未改数据库 schema、公开 API、前端、Provider 或 FTS 召回范围。
- 根因复核：第二十七批之后，16 条 FN 的允许支持文件全部仍在 Top 8。原门控误拒由 11 条默认向量相似度下限、3 条数值答案上下文误判和 2 条复合问题整体拒答组成；不是索引缺失。固定 READY 资料中的支持片段和定位被逐条保留在隔离报告中。
- 规则修复：保留默认 `min_vector_similarity=0.82`；仅当候选同时满足 FTS/向量原始 rank 不晚于 5、最终 rank 不晚于 3、正文至少两个查询锚点或完整短语、数值/单位/编号语境通过且相似度不低于 `min_fts_similarity=0.50` 时，记录 `FTS_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD` 并允许进入后续流程。FTS 缺失时只允许 `min_semantic_similarity=0.60` 以上、至少两个语义锚点且覆盖率不低于 `0.50` 的 vector-only 例外，记录 `SEMANTIC_EVIDENCE_VERIFIED_BELOW_VECTOR_THRESHOLD`。纯余弦下降、同文件 Top 8、标题单独命中、任意短词和无语境数字不能放行。
- 数值与语义边界：查询显式数字必须以相同单位在支持锚点附近出现；错误数值/单位返回 `QUERY_NUMERIC_VALUE_NOT_FOUND`。编号必须完整命中正文；否定断言与正文肯定事实冲突返回 `QUERY_CLAIM_CONTRADICTED`，仅有“不定义”而问题要求定义事实返回 `QUERY_NEGATIVE_FACT_ONLY`。复合问题按 `以及/并且/同时` 分解，只有每个子句均能在候选正文中定位时才支持，否则保持 `COMPOSITE_OR_OPEN_LIST_QUESTION`。冲突文件仍返回 `CONFLICTING_EVIDENCE`。
- 16 条 FN 逐项证据：`S5-EG-001/002/003/005/011/012` 均由 `服务超时策略.txt` 行 `1-12` 的 FTS+向量双路正文通过，实际余弦 `0.5545–0.6213`；`S5-EG-010` 同一片段同时覆盖普通请求时限和后台任务排除规则，通过完整复合子句检查；`S5-EG-013` 由 `相似服务超时策略.txt` 行 `1-9` 的 47 秒片段通过；`S5-EG-014` 由同文件 vector-only 语义路径通过，余弦 `0.6013`；`S5-EG-016/018/020/029` 由 `阶段5评测_参数记录.txt` 行 `1-4` 的 OPS-R7-204、17 秒和每批 6 个文件片段通过，其中 `S5-EG-029` 通过完整复合子句检查；`S5-EG-021/022` 由 `阶段5评测_组件记录.txt` 行 `1-3` 的完整编号、组件名和 12 分钟片段通过；`S5-EG-028` 由 `阶段5评测_短词干扰.txt` 行 `1-2` 的明确否定说明通过。每条候选的 Chunk/File/IndexVersion、FTS/向量 rank、余弦、锚点、数字/编号命中和门控 reason code 均在隔离 JSON 报告中保存。
- 真实前后混淆表：同一 manifest、同一真实 ONNX 与 READY 准备流程，第二十八批前基线（`r28-baseline`）核心 `TP 0 / FN 16 / FP 0 / TN 15`、hard negatives `TN 7 / FP 0`；校准后（`r28-final`）两轮核心均 `TP 16 / FN 0 / FP 0 / TN 15`，hard negatives 两轮均 `TN 7 / FP 0`。两轮内部结果签名稳定，评测前后资源计数均为 `9 files / 4 knowledge bases / 24 tasks`；失效索引检查两轮均为 `unavailable / INDEX_VERSION_NOT_AVAILABLE`、0 候选。该结果只证明固定合成样本回归，不代表 Recall@10、引用正确率或最终回答质量。
- 评测与报告：最终命令为 `uv run python scripts/evaluate_stage5_evidence_gate.py --data-dir "$env:TEMP\\mindmate-ai-stage5-evidence-gate-v1-r28-final" --repeat 2`；报告为 `%TEMP%\\mindmate-ai-stage5-evidence-gate-v1-r28-final\\stage5-evidence-gate-v1-report.json`，不入 Git，模型、临时数据库和评测输出不入 Git。
- 验收：定向门控/评测测试 `18 passed`；全量 `uv run pytest` `186 passed, 143 warnings`（142.37 秒）；`uv run ruff check src tests scripts`、`uv run pyright src tests scripts/prepare_stage5_fixed_ready.py scripts/evaluate_stage5_evidence_gate.py`（0 errors）、`uv run python -m compileall -q src tests migrations scripts`、`uv run alembic heads`（`6b3e91a0c4d7`）和 `git diff --check` 均通过。未改前端，未运行前端门禁；未调用 DeepSeek、真实凭据、付费服务或私人资料。
- 下一开发批次唯一目标：在不生成模型回答、不绑定虚构 Citation owner 的前提下，为已通过门控的候选建立真实 Chat/Learning owner 的服务端 Citation 绑定准入；阶段 5 继续 `PARTIAL`。

## 第二十九批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`。进场本地与远端 `origin/feat/v1-bootstrap` SHA 均为 `cf0853e3c80a71b64c65d60ae8b8fb4e0b057707`，工作区干净。
- 后端真实契约：新增 `GET /api/v1/knowledge-bases/{knowledge_base_id}/index-status`、`POST /api/v1/knowledge-bases/{knowledge_base_id}/index/retry-failed` 和 `POST /api/v1/knowledge-bases/{knowledge_base_id}/index/rebuild`。状态基于当前有效成员、活动/目标 `IndexVersion`、逐文件阶段检查点及 `BackgroundTask`；失败仅返回安全原因码、可读说明和诊断 ID。重试校验成员确属当前库、仍有效、已解析且当前确实失败；回收站文件、非成员和未知 ID 均拒绝。操作沿用持久 `INDEX_PREPROCESS` 任务和现有任务取消 API，无数据库迁移。
- Worker 接力：激活扫描器在上游阶段达到 `COMPLETED/PARTIAL` 检查点后幂等入队 `INDEX_CHUNK`，再并行入队 `INDEX_EMBED` 与 `INDEX_FTS`；现有激活器负责候选完整性复核与活动指针切换。固定 READY 准备脚本与运行时共用阶段幂等键，避免并发重复任务。
- 前端闭环：详情页新增索引运维工作台，保留“测试检索”；显示索引状态、活动/目标版本、成员计数、失败文件和安全原因码、真实任务阶段/进度/诊断 ID、本地模型可用性；支持重试失败文件、确认当前库重建和现有任务取消。状态查询按 KB ID 隔离，运行期间每 1.5 秒轮询，页面不可见时暂停，刷新后从 API 恢复；不触发模型下载、回答或 Citation。
- 浏览器证据：固定 READY 隔离根 `%TEMP%\mindmate-ai-stage5-r29-index-ops-e2e-02` 中，知识库 `01a0d6a1-583b-7360-b0bb-2546fc3f85ec` 活动版本由 `01a0d6b2-1b26-7afb-a599-0366cd1c8602` 切换为 `01a0d6c4-b88c-7a8f-b67d-bd64993daf9d`；新 `INDEX_PREPROCESS`、`INDEX_CHUNK`、`INDEX_EMBED`、`INDEX_FTS` 任务均为 `COMPLETED`，最终状态 `READY`。Playwright 在 390px 视口验证无水平溢出；截图 `evidence/index-operations-mobile.png` 留在临时根，不入 Git。模型来自已校验离线副本，未下载或调用外部 Provider。
- 验收：`uv run pytest` `191 passed, 148 warnings`（143.94 秒）；`uv run ruff check src tests scripts`、Pyright（0 errors）、compileall、Alembic head `6b3e91a0c4d7` 和 `git diff --check` 通过。前端 Vitest `22 passed`、`npm run lint`、`npm run build`、真实 API Playwright E2E `1 passed`。
- 边界：本批浏览器验证真实 READY 库重建成功；失败原因展示、失败文件范围校验和保留活动版本由 API/激活器测试覆盖，未宣称浏览器级模型缺失失败恢复。模型下载安装页面、Citation owner、10 万 Chunk 性能、Recall@10/最终问答质量和 AC-KB-* 全量验收仍未完成。
- 下一批唯一目标：真实 Chat/Learning owner 可核验后完成服务端 Citation 绑定准入；不伪造 owner 或模型答案。

## 第三十批交接

- 本批状态：`PASS`；阶段 5 继续 `PARTIAL`。起始本地 SHA 与 `origin/feat/v1-bootstrap` SHA 均为 `d8762e32a2d3db85cf2393f05a7d99d007f677b7`。
- 后端新增固定模型状态/安装 API 和持久 `EMBEDDING_MODEL_INSTALL` Worker，复用 `BackgroundTask` 检查点、通用任务取消端点与重启恢复，无数据库迁移。命令只使用固定 manifest；重复安装请求复用活动任务；取消不会发布半成品。
- 固定 BAAI revision `7999e1d3359715c523056ef9478215996d62a620`、Xenova ONNX revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`，manifest fingerprint `4d07bfc3eefa75de01924a4350eef08182c163b0060228410c3d882c9f07c6a5`，三个文件共 `95,291,718` 字节。真实公网下载、文件 SHA-256 校验和本机 ONNX 索引见第三十批详细交接。
- 浏览器证据：用户点击安装后展示真实非零字节进度；安装 READY 后点击重建，真实 `INDEX_PREPROCESS/CHUNK/EMBED/FTS` 均完成，活动索引 `READY`；390px 视口无水平溢出。截图留在隔离临时根，不进 Git。
- 下一批唯一目标：真实 Chat/Learning owner 可核验后建立服务端 Citation 绑定准入；阶段 5 继续 `PARTIAL`。
