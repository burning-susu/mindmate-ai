# G2 冲突矩阵
> 文档编号：G2-CONFLICT-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 关联来源：SRC-002、SRC-003、SRC-004、SRC-005、SRC-006、SRC-007
> 关联决策：DEC-BOOTSTRAP-001

| 编号 | 冲突或差异 | 受影响对象 | 当前裁决 | 状态 |
|---|---|---|---|---|
| CONFLICT-01 | 产品说明书把基础设置描述为首版体验，需求表将设置列为 P1 | 首版范围、页面、验收 | 采用 HIGH-04：设置页延后，内部默认值保留 | RESOLVED_FOR_V1 |
| CONFLICT-02 | 第一轮方向只说本地/私有和外部 Provider，数据是否本地不够明确 | 隐私、部署、Provider | 采用 HIGH-02：原始文件、解析结果、业务数据和向量默认本地；必要文本可发送外部 Provider | RESOLVED_WITH_CONSTRAINT |
| CONFLICT-03 | 设计文件是智能体平台模板，需求要求个人知识学习助手 | UI范围、导航、页面 | 采用 MEDIUM-01 和 LOW-02：只参考结构和视觉，平台化功能不得进入 V1 | RESOLVED_FOR_V1 |
| CONFLICT-04 | 需求附录提到“五个一级页面”，页面清单又列出首页、对话、知识库列表、知识库详情、文件详情、历史会话、设置等层级 | 页面范围、UI Scope、验收 | V1 延后设置；其余页面层级需在 G3/G4 形成正式页面树 | OPEN_P1 |
| CONFLICT-05 | V1 暂不登录，但需求要求 userId 和资源归属校验 | 数据归属、安全 | 采用 HIGH-01：保留 userId 和服务层归属校验 | RESOLVED |
| CONFLICT-06 | 20MB 在原需求中是“建议”或默认值，强度不完全一致 | 文件校验、验收 | 采用 MEDIUM-02：V1 按 20MB 默认上限实现；若要改为软限制需走变更 | RESOLVED_WITH_REVALIDATION |
| CONFLICT-07 | 需求要求流式输出，但 API 协议未定义 | API、前端状态、测试 | 采用 MEDIUM-04 的 REST/OpenAPI 方向，STREAMING_PROTOCOL 保持 TBD | OPEN_HIGH |
| CONFLICT-08 | 需求提出向量检索和混合检索方向，但未指定向量库和重排实现 | 架构、数据、成本 | 只确认本地向量存储模式，具体实现留给 G6 TECH-DECISION | OPEN_HIGH |
| CONFLICT-09 | 产品说明书和需求文档都描述三种模式、引用和陪练闭环 | 核心范围 | 两份资料相互支持，以需求编号和验收表作为后续追踪入口 | ALIGNED |
| CONFLICT-10 | 设计工程可读取元数据和预览，但未完成全部画板和图层审计 | UI事实、素材清单 | 仅登记已验证的存在、页面/控件范围和预览边界 | OPEN_MEDIUM |

## 当前冲突结论

已经有用户决策的冲突可按上述裁决进入当前项目决策基线。CONFLICT-04、CONFLICT-07、CONFLICT-08、CONFLICT-10 仍需在 G3/G5.5/G6/G9.5 等相应阶段复核，不得被本轮的方向决策误写成已完成。

