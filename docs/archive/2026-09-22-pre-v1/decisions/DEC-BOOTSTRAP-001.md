# Mindmate AI 首版启动决策集
> 文档编号：DEC-BOOTSTRAP-001
> 文档版本：v1.0
> 文档类型：governance
> 关联对象：PROJECT mindmate-ai
> 状态：active
> 负责人：TBD
> 创建日期：2026-09-20
> 更新时间：2026-09-20
> 关联来源：SRC-002、SRC-003、SRC-004、SRC-005、SRC-007
> 关联证据：EVID-004
> 适用版本：V1.0 MVP
> 替代文档：NONE

## 决策证据

用户在当前会话中对 HIGH-01 至 LOW-02 逐项完成了影响复述后的二次确认，并明确使用“确认并应用”口令授权应用。第二轮提示词只是把已确认内容结构化，不作为独立确认人。

## HIGH-01 使用范围与用户模式

- 选择：A
- 结论：APPLICATION_USAGE_MODE=LOCAL_SINGLE_USER_MVP。
- V1 暂不实现真实注册和登录。
- 数据结构保留 userId 或等价资源归属字段。
- 服务层保留资源归属校验边界。
- 影响：不宣称公网多用户生产可用；后续增加登录或多用户时需复核认证、权限、部署和测试。
- TBD：未来认证方式、用户生命周期。
- 重评触发：公网部署、多用户、账号体系或真实数据共享。
- 状态：APPLIED

## HIGH-02 模型、Embedding 与向量处理

- 选择：A
- MODEL_PROVIDER_MODE=EXTERNAL_PROVIDER。
- EMBEDDING_PROVIDER_MODE=EXTERNAL_PROVIDER。
- PROVIDER_ACCESS_MODE=LOCAL_BACKEND_ADAPTER。
- VECTOR_STORE_MODE=LOCAL。
- APPLICATION_DEPLOYMENT_MODE=LOCAL_ONLY。
- CLOUD_SERVER_REQUIRED=NO。
- 原始文件、解析结果、业务数据和向量数据默认保存在本地。
- 只向外部 Provider 发送当前任务必要的问题、文本片段和上下文。
- API Key 只保存在本地环境变量，不进入前端、源码或 Git。
- V1 不实现完整多 Provider 动态路由，但保留 Provider 接口。
- 产品必须提示外部模型可能接收必要文本，不适合处理高度敏感资料。
- TBD：Provider 名称、模型版本、Embedding 模型、数据地域、保留策略、费用。
- 重评触发：Provider 条款不满足隐私边界、本地模型需求、成本或限流风险。
- 状态：APPLIED_WITH_TBD

## HIGH-03 总体架构形态

- 选择：A
- ARCHITECTURE_STYLE=MODULAR_MONOLITH。
- ASYNC_TASK_MODE=INTERNAL_ASYNC_TASK。
- MICROSERVICE_MODE=DISABLED_IN_V1。
- 文件解析、摘要、Embedding 和索引作为模块化单体内部异步任务。
- 影响：降低部署、调试、事务和回滚成本；不代表内部模块可以取消边界。
- TBD：模块边界、任务执行组件、并发和重试实现。
- 重评触发：任务积压、资源争用、公网多用户、多人并行或独立扩缩容。
- 状态：APPLIED_WITH_REVALIDATION

## HIGH-04 V1 交付范围

- 选择：A
- DELIVERY_SCOPE=CORE_CLOSED_LOOP_MVP。
- V1 包含知识库、文件、资料问答、真实引用、基础陪练和历史会话。
- SETTINGS_PAGE=DEFERRED。
- INDEPENDENT_WRONG_ANSWER_BOOK=DEFERRED。
- 陪练题目、回答、点评和会话结果仍可保存。
- 影响：优先验证文件入库、可信问答、陪练和历史恢复。
- TBD：V1.1 具体设置项和错题本形态。
- 重评触发：用户必须自定义默认值、跨会话复习错题或需要个性化学习。
- 状态：APPLIED

## MEDIUM-01 设计资料使用方式

- 选择：A
- DESIGN_USAGE_MODE=STRUCTURE_AND_VISUAL_REFERENCE。
- PIXEL_PERFECT_REPLICA=NO。
- PRODUCTIZATION_ADAPTATION=ALLOWED。
- Figma 和 Sketch 用于页面结构、视觉方向、控件和素材参考。
- 模板中的平台化功能、品牌、文案和颜色不自动进入 V1。
- TBD：页面树、视觉验收精度和最终 Design Token。
- 重评触发：高保真交付、品牌化、对外正式发布或像素级验收。
- 状态：APPLIED

## MEDIUM-02 文件支持范围

- 选择：A
- SUPPORTED_FILE_TYPES=TEXT_PDF,DOCX,MARKDOWN,TXT。
- OCR_ENABLED=NO。
- MAX_FILE_SIZE=20MB。
- MAX_FILES_PER_UPLOAD=5。
- V1 优先保证文本解析、处理状态和引用定位。
- TBD：复杂表格、代码块、特殊字体和解析器实现。
- 重评触发：扫描件占比高、文本解析不足或需要更多格式。
- 状态：APPLIED_WITH_REVALIDATION

## MEDIUM-03 测试范围

- 选择：A
- UNIT_TEST=ENABLED。
- API_CONTRACT_TEST=ENABLED。
- CORE_E2E_TEST=ENABLED。
- BASIC_SECURITY_CHECK=ENABLED。
- LIGHTWEIGHT_PERFORMANCE_BASELINE=ENABLED。
- FULL_SCALE_LOAD_TEST=DISABLED_IN_V1。
- 覆盖文件状态、引用、资源归属、删除、陪练、历史恢复和异常路径。
- TBD：测试框架、固定评测集、E2E 环境、专业渗透测试是否需要。
- 重评触发：公网、多用户、公开 SLA、高并发或敏感数据升级。
- 状态：APPLIED_WITH_SCOPE

## MEDIUM-04 API 方向

- 选择：A
- API_STYLE=REST。
- API_DOCUMENTATION=OPENAPI。
- API_PATHS=TBD。
- API_FIELDS=TBD。
- STREAMING_PROTOCOL=TBD。
- 鉴权、错误结构、分页、上传协议和流式传输需要在 G8/G9 形成正式契约。
- 状态：APPLIED_DIRECTION_ONLY

## LOW-01 日志与统计

- 选择：A
- KEY_EVENT_LOGGING=ENABLED。
- NECESSARY_RUNTIME_LOGGING=ENABLED。
- COMPLEX_ANALYTICS_BACKOFFICE=DISABLED_IN_V1。
- 日志不得包含完整文件正文、完整敏感对话或密钥。
- TBD：事件存储实现和后续统计方式。
- 重评触发：正式运营、用户增长分析或复杂质量看板需求。
- 状态：APPLIED

## LOW-02 视觉内容

- 选择：A
- COPY_STYLE=PRODUCT_NEUTRAL。
- TEMPLATE_STRUCTURE_REFERENCE=ALLOWED。
- TEMPLATE_BRAND_INHERITANCE=NO。
- TEMPLATE_COLOR_DIRECT_INHERITANCE=NO。
- 不把模板原有品牌、颜色和文案固化为 Mindmate 最终规范。
- TBD：品牌、配色、字体、间距和 Design Token。
- 重评触发：正式品牌化或高保真视觉交付。
- 状态：APPLIED

## 受控应用边界

本决策集不批准 PRD、总体架构、API Contract、数据库模型、代码、测试通过、发布或公网生产。后续文档只能在本决策集约束下继续分析，并在上游变化时执行 KEEP、REVALIDATE、INVALIDATE、ADD 或 REMOVE。

