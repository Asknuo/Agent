# Requirements Document

## Introduction

本文档定义了将现有"小智 AI 智能客服"系统从原型级升级为企业级生产系统的需求。当前系统基于 LangGraph 3-Agent 协作架构（Supervisor → Worker → Reviewer），具备 RAG 三级检索、工具调用、SSE 流式输出等核心能力，但在可观测性、持久化、安全、容错、性能、测试、配置管理、前端体验、多租户和 Agent 智能化等方面存在明显短板。本需求文档覆盖上述十大优化方向，确保系统满足企业级生产环境的可靠性、安全性和可维护性要求。

## Glossary

- **Agent_Engine**: 基于 LangGraph 构建的 3-Agent 协作引擎，包含 Supervisor、Worker、Reviewer 三个节点
- **Supervisor_Node**: Agent 图中的路由节点，负责情绪分析、意图分类和消息路由
- **Worker_Node**: Agent 图中的执行节点，绑定工具集，通过 ReAct 循环完成任务
- **Reviewer_Node**: Agent 图中的质检节点，审核 Worker 回复的质量和情绪适配度
- **RAG_Pipeline**: 三级检索管线（外部 RAG API → 本地 FAISS 向量检索 → 关键词匹配）
- **Session_Store**: 会话存储组件，负责会话数据的持久化和检索
- **Auth_Module**: 认证鉴权模块，负责 API 访问控制和身份验证
- **Rate_Limiter**: 速率限制组件，控制 API 请求频率
- **Circuit_Breaker**: 熔断器组件，在下游服务故障时自动降级
- **Cache_Layer**: 缓存层，用于缓存知识库检索结果和 Embedding 计算结果
- **Observability_Stack**: 可观测性技术栈，包含结构化日志、链路追踪和指标监控
- **Tenant**: 租户，代表使用系统的独立企业或组织
- **Config_Manager**: 配置管理组件，集中管理所有运行时配置

## Requirements

### Requirement 1: 结构化日志系统

**User Story:** 作为运维工程师，我希望系统具备结构化日志能力，以便快速定位生产环境中的问题。

#### Acceptance Criteria

1. THE Observability_Stack SHALL 以 JSON 格式输出所有日志，每条日志包含 timestamp、level、module、message、trace_id 字段
2. WHEN Agent_Engine 处理一条用户消息时，THE Observability_Stack SHALL 记录完整的处理链路日志，包含 session_id、user_id、节点名称、耗时
3. WHEN 任意组件发生异常时，THE Observability_Stack SHALL 记录 ERROR 级别日志，包含异常类型、堆栈摘要和触发上下文
4. THE Observability_Stack SHALL 支持通过环境变量配置日志级别（DEBUG、INFO、WARNING、ERROR）
5. WHILE 系统运行时，THE Observability_Stack SHALL 将日志同时输出到 stdout 和可配置的日志文件路径

### Requirement 2: 链路追踪与指标监控

**User Story:** 作为运维工程师，我希望能追踪每条消息在 Agent 图中的完整执行路径，以便分析性能瓶颈和异常节点。

#### Acceptance Criteria

1. THE Observability_Stack SHALL 为每次用户请求生成唯一的 trace_id，并在 Agent_Engine 所有节点间传递
2. WHEN Agent_Engine 执行完一次请求时，THE Observability_Stack SHALL 记录每个节点（Supervisor、Worker、Tool、Reviewer）的执行耗时
3. THE Observability_Stack SHALL 暴露 Prometheus 兼容的 /metrics 端点，包含请求总数、请求延迟分布、活跃会话数、工具调用次数指标
4. WHEN Worker_Node 调用工具时，THE Observability_Stack SHALL 记录工具名称、输入参数摘要、执行耗时和返回状态

### Requirement 3: 会话持久化

**User Story:** 作为用户，我希望服务重启后历史对话不丢失，以便继续之前的咨询。

#### Acceptance Criteria

1. THE Session_Store SHALL 将会话数据持久化到 PostgreSQL 数据库，包含 messages、context、status、satisfaction 字段
2. WHEN 用户发送消息时，THE Session_Store SHALL 在生成回复后将用户消息和助手回复同步写入数据库
3. WHEN 用户通过已有 session_id 发起请求时，THE Session_Store SHALL 从数据库加载该会话的历史消息
4. IF 数据库写入失败，THEN THE Session_Store SHALL 回退到内存存储并记录 ERROR 日志
5. THE Session_Store SHALL 支持按 user_id 查询该用户的所有历史会话列表

### Requirement 4: API 认证与鉴权

**User Story:** 作为系统管理员，我希望 API 接口受到认证保护，以防止未授权访问。

#### Acceptance Criteria

1. THE Auth_Module SHALL 要求所有 /api/* 端点（除 /api/health 外）携带有效的 Bearer Token
2. WHEN 请求未携带 Token 或 Token 无效时，THE Auth_Module SHALL 返回 HTTP 401 状态码和错误描述
3. THE Auth_Module SHALL 支持基于 JWT 的 Token 验证，验证签名、过期时间和 issuer 字段
4. WHEN WebSocket 连接建立时，THE Auth_Module SHALL 在握手阶段验证 Token 有效性
5. IF Token 验证过程发生异常，THEN THE Auth_Module SHALL 拒绝请求并记录 WARNING 日志

### Requirement 5: 速率限制

**User Story:** 作为系统管理员，我希望对 API 请求进行速率限制，以保护系统免受滥用和过载。

#### Acceptance Criteria

1. THE Rate_Limiter SHALL 基于客户端 IP 或 user_id 对 /api/chat 和 /api/chat/stream 端点实施速率限制
2. THE Rate_Limiter SHALL 支持通过配置文件设定每分钟最大请求数，默认值为 30 次/分钟
3. WHEN 请求超过速率限制时，THE Rate_Limiter SHALL 返回 HTTP 429 状态码，响应头包含 Retry-After 字段
4. THE Rate_Limiter SHALL 使用滑动窗口算法计算请求频率

### Requirement 6: SQL 注入防护加固

**User Story:** 作为安全工程师，我希望数据库查询工具具备更强的 SQL 注入防护，以防止恶意输入造成数据泄露。

#### Acceptance Criteria

1. THE Agent_Engine SHALL 使用参数化查询执行所有 SQL 语句，禁止直接拼接用户输入
2. WHEN Worker_Node 生成 SQL 查询时，THE Agent_Engine SHALL 对 SQL 进行语法解析，仅允许单条 SELECT 语句通过
3. IF SQL 包含子查询嵌套超过 2 层或包含 UNION 关键字，THEN THE Agent_Engine SHALL 拒绝执行并返回安全提示
4. THE Agent_Engine SHALL 对查询结果行数设置上限（默认 50 行），超出时截断并提示用户缩小查询范围

### Requirement 7: Agent 异常处理与重试机制

**User Story:** 作为开发者，我希望 Agent 执行过程具备健壮的错误处理和自动重试能力，以提高系统可用性。

#### Acceptance Criteria

1. WHEN Worker_Node 调用 LLM 接口失败时，THE Agent_Engine SHALL 使用指数退避策略自动重试，最多重试 3 次
2. WHEN 工具调用抛出异常时，THE Agent_Engine SHALL 捕获异常，向 Worker_Node 返回结构化错误信息，允许 Worker 选择替代方案
3. IF Agent_Engine 在单次请求中重试次数耗尽仍失败，THEN THE Agent_Engine SHALL 返回预定义的降级回复并记录 ERROR 日志
4. THE Circuit_Breaker SHALL 在 LLM 接口连续失败 5 次后触发熔断，熔断期间直接返回降级回复
5. WHEN Circuit_Breaker 处于熔断状态时，THE Circuit_Breaker SHALL 每 60 秒尝试一次探测请求，成功后恢复正常调用

### Requirement 8: 缓存层

**User Story:** 作为开发者，我希望系统对高频查询结果进行缓存，以降低 LLM 调用成本和响应延迟。

#### Acceptance Criteria

1. THE Cache_Layer SHALL 对知识库检索结果进行缓存，相同查询在缓存有效期内直接返回缓存结果
2. THE Cache_Layer SHALL 支持配置缓存过期时间，默认为 300 秒
3. WHEN 知识库内容更新时，THE Cache_Layer SHALL 清除相关缓存条目
4. THE Cache_Layer SHALL 使用 LRU 淘汰策略，缓存条目上限默认为 1000 条

### Requirement 9: Embedding 批处理优化

**User Story:** 作为开发者，我希望 Embedding 调用支持批处理，以减少 API 调用次数和初始化耗时。

#### Acceptance Criteria

1. WHEN RAG_Pipeline 初始化构建 FAISS 索引时，THE RAG_Pipeline SHALL 将文档分批发送 Embedding 请求，每批最多 32 条
2. THE RAG_Pipeline SHALL 在批处理调用之间添加可配置的间隔时间，默认为 100 毫秒，以避免触发 API 速率限制
3. IF 某批 Embedding 请求失败，THEN THE RAG_Pipeline SHALL 对该批进行重试（最多 2 次），失败后跳过该批并记录 WARNING 日志

### Requirement 10: 并发控制

**User Story:** 作为运维工程师，我希望系统对并发请求进行控制，以防止资源耗尽导致服务不可用。

#### Acceptance Criteria

1. THE Agent_Engine SHALL 使用信号量限制同时处理的 Agent 请求数量，默认上限为 20
2. WHEN 并发请求数达到上限时，THE Agent_Engine SHALL 将新请求排入等待队列，队列满时返回 HTTP 503 状态码
3. THE Agent_Engine SHALL 为每次 Agent 执行设置超时时间，默认为 120 秒，超时后终止执行并返回超时提示

### Requirement 11: 集中式配置管理

**User Story:** 作为开发者，我希望所有配置项集中管理且有明确的默认值，以消除硬编码和环境变量散落问题。

#### Acceptance Criteria

1. THE Config_Manager SHALL 从 YAML 配置文件加载所有运行时配置，环境变量可覆盖配置文件中的值
2. THE Config_Manager SHALL 在启动时校验所有必填配置项，缺失时输出明确的错误提示并拒绝启动
3. THE Config_Manager SHALL 为所有可选配置项提供文档化的默认值
4. WHEN 配置项的值不符合预期格式时，THE Config_Manager SHALL 在启动时报告具体的校验错误

### Requirement 12: 前端消息可靠性

**User Story:** 作为用户，我希望在网络不稳定时消息不会丢失，并能重新发送失败的消息。

#### Acceptance Criteria

1. WHEN 消息发送失败时，THE 前端应用 SHALL 在对应消息气泡上显示发送失败标识和重发按钮
2. WHEN 用户点击重发按钮时，THE 前端应用 SHALL 使用原始消息内容重新发起请求
3. THE 前端应用 SHALL 将当前会话的消息历史持久化到浏览器 localStorage
4. WHEN 用户刷新页面时，THE 前端应用 SHALL 从 localStorage 恢复最近一次会话的消息记录
5. IF SSE 连接中断，THEN THE 前端应用 SHALL 在 3 秒后自动重试连接，最多重试 3 次

### Requirement 13: 多租户支持

**User Story:** 作为平台运营者，我希望系统支持多租户隔离，以便为不同企业客户提供独立的客服服务。

#### Acceptance Criteria

1. THE Agent_Engine SHALL 在所有 API 请求中接受 tenant_id 参数，用于标识租户归属
2. THE Session_Store SHALL 按 tenant_id 隔离会话数据，不同租户的会话数据互不可见
3. THE RAG_Pipeline SHALL 支持按 tenant_id 加载不同的知识库内容
4. WHEN 请求未携带 tenant_id 时，THE Agent_Engine SHALL 使用默认租户标识处理请求
5. THE Rate_Limiter SHALL 支持按租户配置独立的速率限制策略

### Requirement 14: LLM 驱动的情绪分析与意图分类

**User Story:** 作为产品经理，我希望情绪分析和意图分类由 LLM 驱动而非简单关键词匹配，以提高分类准确率。

#### Acceptance Criteria

1. THE Supervisor_Node SHALL 使用 LLM 对用户消息进行情绪分析，输出结果为 Sentiment 枚举值之一
2. THE Supervisor_Node SHALL 使用 LLM 对用户消息进行意图分类，输出结果为 IntentCategory 枚举值之一，并附带 0-1 之间的置信度分数
3. THE Supervisor_Node SHALL 在单次 LLM 调用中同时完成路由决策、情绪分析和意图分类，以减少 LLM 调用次数
4. IF LLM 情绪/意图分析调用失败，THEN THE Supervisor_Node SHALL 回退到现有的关键词规则分析方法
5. THE Supervisor_Node SHALL 将 LLM 分析结果以结构化 JSON 格式输出，包含 next、sentiment、intent、confidence 字段

### Requirement 15: Agent 执行过程可视化

**User Story:** 作为开发者，我希望能在前端看到 Agent 的执行过程（经过了哪些节点、调用了哪些工具），以便调试和优化。

#### Acceptance Criteria

1. WHEN Agent_Engine 执行请求时，THE Agent_Engine SHALL 通过 SSE 推送实时的节点执行事件，包含节点名称和状态（started、completed）
2. THE 前端应用 SHALL 在消息气泡下方展示 Agent 执行步骤的折叠面板，显示节点流转和工具调用详情
3. WHEN Worker_Node 调用工具时，THE Agent_Engine SHALL 通过 SSE 推送工具调用事件，包含工具名称和执行耗时
4. THE 前端应用 SHALL 支持展开/折叠 Agent 执行详情，默认为折叠状态
