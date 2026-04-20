# 需求文档：Agent 智能化提升

## 简介

本需求旨在提升"小智 AI 智能客服"系统的 Agent 智能化水平。当前系统基于 LangGraph 3-Agent 协作引擎（Supervisor → Worker → Reviewer），已具备情绪分析（5 种）、意图分类（8 种）和 RAG 三级检索能力。但在长会话管理、用户个性化、主动推荐和多轮澄清方面存在不足。本次增强将围绕四个核心能力展开：长会话摘要压缩、用户画像学习、主动知识推荐、多轮澄清机制。

## 术语表

- **Engine**：基于 LangGraph 的 3-Agent 协作引擎，位于 `server/agent/engine.py`，负责消息处理的完整流程
- **Supervisor**：路由 Agent，负责情绪分析、意图分类和路由决策
- **Worker**：执行 Agent，带工具调用能力（ReAct 循环），负责实际回复生成
- **Reviewer**：质检 Agent，审核回复质量和情绪适配
- **Session**：会话对象，包含 messages 列表、context（SessionContext）和元数据，持久化到 PostgreSQL
- **SessionContext**：会话上下文，包含 user_name、language、sentiment_trend、current_intent、extracted_entities 等字段
- **Summarizer**：长会话摘要模块，负责将超长对话历史压缩为结构化摘要
- **UserProfile**：用户画像模型，记录用户的偏好、沟通风格和历史行为特征
- **RecommendationEngine**：主动推荐引擎，基于当前意图和上下文推送相关知识
- **ClarificationDetector**：澄清检测器，判断用户意图是否明确，决定是否需要追问
- **Context_Window**：LLM 的上下文窗口，当前硬编码取最近 18 条消息
- **RAG_Pipeline**：三级检索管线（外部 API → FAISS → 关键词），位于 `server/data/knowledge_base.py`

## 需求

### 需求 1：长会话摘要压缩

**用户故事：** 作为客服系统运维人员，我希望系统在对话超过一定轮数后自动压缩历史消息为摘要，以避免 Context Window 溢出并保留关键上下文信息。

#### 验收标准

1. WHEN 会话消息数量超过可配置的阈值（默认 20 条），THE Summarizer SHALL 将阈值之前的历史消息压缩为一条结构化摘要消息
2. THE Summarizer SHALL 在摘要中保留以下关键信息：用户核心诉求、已解决的问题、未解决的问题、提及的订单号或实体信息、情绪变化趋势
3. WHEN 摘要生成完成，THE Engine SHALL 使用"摘要 + 最近 N 条原始消息"替代完整历史消息列表传入 LLM，其中 N 为可配置参数（默认 8 条）
4. THE Summarizer SHALL 将生成的摘要存储到 SessionContext 中的新字段 conversation_summary，以便后续请求复用
5. IF 摘要生成过程中 LLM 调用失败，THEN THE Engine SHALL 回退到当前的截取最近 18 条消息策略，并记录警告日志
6. THE Engine SHALL 通过 config.yaml 提供 summary_threshold（触发摘要的消息数阈值）和 summary_recent_count（摘要后保留的最近消息数）两个配置项
7. WHEN 摘要已存在且新消息未超过阈值，THE Engine SHALL 直接复用已有摘要而非重新生成，以减少 LLM 调用次数

### 需求 2：用户画像学习

**用户故事：** 作为客服系统运维人员，我希望系统能根据历史对话自动学习用户偏好，以提供个性化的回复风格和更精准的服务。

#### 验收标准

1. THE UserProfile SHALL 包含以下维度：preferred_language（偏好语言）、communication_style（沟通风格：formal/casual/concise）、frequent_topics（高频咨询主题列表）、satisfaction_history（历史满意度趋势）、interaction_count（交互次数）
2. WHEN 每次对话结束，THE Engine SHALL 根据本次对话内容更新 UserProfile 中的相关维度
3. THE UserProfile SHALL 持久化存储到 PostgreSQL 数据库，与用户 ID 关联
4. WHEN Worker Agent 生成回复时，THE Engine SHALL 将 UserProfile 摘要注入到 Worker 的 System Prompt 中，指导回复风格适配
5. IF 用户为首次对话（无历史画像），THEN THE Engine SHALL 使用默认画像配置，不影响正常回复流程
6. WHILE 用户画像数据加载中，THE Engine SHALL 在 3 秒超时后使用默认画像继续处理，不阻塞回复生成
7. THE UserProfile 的 communication_style SHALL 基于用户消息的平均长度、是否使用表情符号、用语正式程度三个信号进行推断

### 需求 3：主动知识推荐

**用户故事：** 作为终端用户，我希望在咨询某个问题时，系统能主动推送相关的补充知识，以减少我的追问次数。

#### 验收标准

1. WHEN Worker Agent 完成主查询的知识检索后，THE RecommendationEngine SHALL 基于当前意图和检索结果，从 RAG_Pipeline 中额外检索最多 2 条相关知识条目
2. THE RecommendationEngine SHALL 使用意图到关联主题的映射规则确定推荐查询词，映射规则包括但不限于：refund_request 关联"退换货流程"、order_status 关联"配送时效"、product_inquiry 关联"回收价格标准"
3. WHEN 推荐知识条目与主查询结果重复时，THE RecommendationEngine SHALL 过滤掉重复条目，避免信息冗余
4. THE Worker Agent SHALL 将推荐知识以"您可能还想了解"的格式附加在主回复之后，与主回复内容明确分隔
5. WHERE 用户通过配置关闭主动推荐功能，THE RecommendationEngine SHALL 跳过推荐流程，仅返回主查询结果
6. THE RecommendationEngine SHALL 在 MessageMetadata 中记录推荐的知识条目 ID 列表，用于后续效果分析
7. IF 推荐知识检索耗时超过 2 秒，THEN THE Engine SHALL 放弃推荐结果，仅返回主查询回复，并记录超时日志

### 需求 4：多轮澄清机制

**用户故事：** 作为终端用户，我希望当我的问题表述不清时，系统能主动追问澄清，而非给出不相关的回答。

#### 验收标准

1. WHEN Supervisor 的意图分类置信度低于可配置阈值（默认 0.4），THE ClarificationDetector SHALL 标记该消息需要澄清
2. WHEN 消息被标记为需要澄清，THE Worker Agent SHALL 生成一条包含具体选项的澄清问题，而非直接尝试回答
3. THE ClarificationDetector SHALL 根据意图类型生成对应的澄清选项模板，例如：检测到可能是退款或订单查询时，提供"您是想查询退款进度还是申请新的退款？"
4. WHILE 处于澄清等待状态，THE Engine SHALL 在 SessionContext 中记录 pending_clarification 标记和原始模糊消息
5. WHEN 用户回复澄清问题后，THE Engine SHALL 将原始模糊消息与澄清回复合并，重新进行意图分类
6. IF 连续 2 轮澄清后意图仍不明确，THEN THE Engine SHALL 自动触发转人工流程，并在转接信息中包含完整的澄清对话记录
7. THE Engine SHALL 通过 config.yaml 提供 clarification_confidence_threshold（澄清触发的置信度阈值）配置项
8. THE ClarificationDetector SHALL 在 MessageMetadata 中记录 clarification_triggered（是否触发澄清）和 clarification_round（当前澄清轮次）字段

### 需求 5：摘要序列化与反序列化

**用户故事：** 作为开发人员，我希望会话摘要能正确地序列化存储和反序列化加载，以确保跨请求的摘要复用可靠。

#### 验收标准

1. THE Summarizer SHALL 将摘要输出为结构化 JSON 格式，包含 summary_text（摘要文本）、key_entities（关键实体列表）、unresolved_issues（未解决问题列表）、generated_at（生成时间戳）字段
2. FOR ALL 有效的摘要对象，序列化为 JSON 后再反序列化 SHALL 产生与原始对象等价的摘要对象（往返一致性）
3. IF 反序列化时遇到格式不合法的 JSON 数据，THEN THE Summarizer SHALL 返回空摘要并记录错误日志，不影响后续流程
4. THE Summarizer SHALL 使用 Pydantic 模型定义摘要结构，确保类型安全和字段校验
