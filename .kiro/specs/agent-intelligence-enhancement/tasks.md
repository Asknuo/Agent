# 实现计划：Agent 智能化提升

## 概述

基于设计文档，在现有 LangGraph 3-Agent 协作引擎上增量添加四项智能化能力：长会话摘要压缩、用户画像学习、主动知识推荐、多轮澄清机制。实现按数据模型 → 数据库 → 功能模块 → 引擎集成的顺序推进，每个模块独立可测试。

## Tasks

- [x] 1. 扩展数据模型与配置
  - [x] 1.1 在 `server/core/models.py` 中新增 `ConversationSummary`、`CommunicationStyle`、`UserProfile` 模型
    - 新增 `ConversationSummary` Pydantic 模型，包含 `summary_text`、`key_entities`、`unresolved_issues`、`generated_at` 字段，以及 `empty()` 类方法
    - 新增 `CommunicationStyle` 枚举（formal/casual/concise）
    - 新增 `UserProfile` 模型，包含 `user_id`、`preferred_language`、`communication_style`、`frequent_topics`、`satisfaction_history`、`interaction_count`、`created_at`、`updated_at` 字段，以及 `default(user_id)` 类方法
    - _需求: 1.1, 1.4, 2.1, 5.1, 5.4_

  - [x] 1.2 扩展 `SessionContext` 和 `MessageMetadata` 模型
    - 在 `SessionContext` 中新增 `conversation_summary: Optional[ConversationSummary]`、`pending_clarification: bool`、`clarification_round: int`、`original_ambiguous_message: Optional[str]` 字段
    - 在 `MessageMetadata` 中新增 `recommended_knowledge_ids: list[str]`、`clarification_triggered: bool`、`clarification_round: int` 字段
    - _需求: 1.4, 3.6, 4.4, 4.8_

  - [x] 1.3 扩展 `AppConfig` 和 `config.yaml` 配置项
    - 在 `AppConfig` 中新增 `summary_threshold`（默认 20）、`summary_recent_count`（默认 8）、`profile_load_timeout`（默认 3）、`recommendation_enabled`（默认 True）、`recommendation_timeout`（默认 2）、`clarification_confidence_threshold`（默认 0.4）字段
    - 在 `config.yaml` 中添加对应配置项及注释
    - 在 `_ENV_MAPPING`、`_INT_FIELDS`、`_FLOAT_FIELDS`、`_BOOL_FIELDS` 中注册新配置项的环境变量映射
    - _需求: 1.6, 2.6, 3.5, 3.7, 4.7_

  - [x] 1.4 编写属性测试：摘要序列化往返一致性
    - **Property 11: 摘要序列化往返一致性**
    - 使用 Hypothesis 生成随机 `ConversationSummary` 对象，验证 `model_dump(mode="json")` 后 `model_validate` 产生等价对象
    - 测试文件: `server/tests/test_summary_serialization_properties.py`
    - **验证: 需求 5.2**

  - [x] 1.5 编写属性测试：异常 JSON 反序列化容错
    - **Property 12: 异常 JSON 反序列化容错**
    - 使用 Hypothesis 生成随机非法 JSON 字符串（空字符串、截断 JSON、缺字段、类型错误），验证反序列化函数返回空摘要而不抛异常
    - 测试文件: `server/tests/test_summary_serialization_properties.py`
    - **验证: 需求 5.3**

- [x] 2. 数据库迁移：用户画像表
  - [x] 2.1 创建 `server/migrations/005_create_user_profiles.sql` 迁移文件
    - 创建 `user_profiles` 表，包含 `user_id`（主键）、`preferred_language`、`communication_style`、`frequent_topics`（JSONB）、`satisfaction_history`（JSONB）、`interaction_count`、`created_at`、`updated_at` 字段
    - 创建 `idx_profiles_updated` 索引
    - _需求: 2.3_

  - [x] 2.2 实现 `server/data/profile_store.py` 用户画像持久化模块
    - 实现 `ProfileStore` 类，包含 `init()`、`close()`、`load(user_id)`、`save(profile)` 方法
    - `load` 方法从 PostgreSQL 加载画像，支持超时降级返回 `None`
    - `save` 方法使用 UPSERT 语义，失败时记录日志但不阻塞
    - 参考 `server/data/session_store.py` 的 asyncpg 连接池模式
    - _需求: 2.3, 2.5, 2.6_

- [x] 3. 检查点 — 确保数据模型和存储层测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 4. 实现长会话摘要压缩模块
  - [x] 4.1 创建 `server/agent/summarizer.py`
    - 实现 `Summarizer` 类，包含 `check_and_summarize(session)`、`_generate_summary(messages)`、`_build_summary_prompt(messages)` 方法
    - 摘要触发条件：消息数 > `summary_threshold` 且无可复用摘要
    - 返回格式：`[SystemMessage(摘要)]` + 最近 N 条原始消息；失败时回退到最近 18 条
    - 实现 `safe_deserialize_summary(json_str)` 函数，非法 JSON 返回 `ConversationSummary.empty()` 而不抛异常
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 5.1, 5.3_

  - [x] 4.2 编写属性测试：摘要触发逻辑正确性
    - **Property 1: 摘要触发逻辑正确性**
    - 使用 Hypothesis 生成随机消息列表和随机阈值，验证摘要仅在消息数 > 阈值且无已有摘要时触发
    - 测试文件: `server/tests/test_summarizer_properties.py`
    - **验证: 需求 1.1, 1.7**

  - [x] 4.3 编写属性测试：摘要后消息列表结构正确性
    - **Property 2: 摘要后消息列表结构正确性**
    - 验证构建的 LLM 输入恰好包含 1 条摘要系统消息 + min(N, 实际消息数) 条最近原始消息，且顺序一致
    - 测试文件: `server/tests/test_summarizer_properties.py`
    - **验证: 需求 1.3**

- [x] 5. 实现用户画像学习模块
  - [x] 5.1 在 `server/agent/summarizer.py` 或新建 `server/agent/profile_analyzer.py` 中实现画像分析逻辑
    - 实现 `analyze_communication_style(messages)` 函数：基于平均消息长度、表情符号、正式用语推断风格
    - 实现 `extract_frequent_topics(messages, current_intent)` 函数：从历史意图提取高频主题
    - 实现 `update_satisfaction(profile, sentiment)` 函数：根据情绪更新满意度趋势
    - _需求: 2.1, 2.2, 2.7_

  - [x] 5.2 实现画像 Prompt 注入函数 `_build_profile_prompt_segment(profile)`
    - 根据 `communication_style` 生成风格提示文本
    - 包含 `frequent_topics` 前 3 个主题和 `interaction_count`
    - _需求: 2.4_

  - [x] 5.3 编写属性测试：沟通风格推断规则一致性
    - **Property 3: 沟通风格推断规则一致性**
    - 使用 Hypothesis 生成随机消息集合（变长、含/不含表情），验证推断结果符合设计文档中的规则
    - 测试文件: `server/tests/test_profile_properties.py`
    - **验证: 需求 2.7**

  - [x] 5.4 编写属性测试：画像 Prompt 注入完整性
    - **Property 4: 画像 Prompt 注入完整性**
    - 使用 Hypothesis 生成随机 `UserProfile`，验证 Prompt 片段包含风格提示、前 3 主题、交互次数
    - 测试文件: `server/tests/test_profile_properties.py`
    - **验证: 需求 2.4**

- [x] 6. 实现主动知识推荐引擎
  - [x] 6.1 创建 `server/agent/recommendation.py`
    - 实现 `RecommendationEngine` 类，包含 `get_recommendations(intent, main_results, session_context)` 和 `_deduplicate(candidates, main_results)` 方法
    - 定义 `INTENT_TOPIC_MAP` 意图到推荐查询词映射
    - 推荐最多 2 条，基于 ID 去重，超时 2 秒自动放弃返回空列表
    - 支持通过 `recommendation_enabled` 配置关闭
    - _需求: 3.1, 3.2, 3.3, 3.5, 3.7_

  - [x] 6.2 实现推荐内容格式化函数
    - 实现 `format_recommendations(main_reply, recommendations)` 函数
    - 非空推荐时附加"您可能还想了解"分隔标记；空推荐时返回原始回复
    - _需求: 3.4_

  - [x] 6.3 编写属性测试：推荐知识不变量
    - **Property 5: 推荐知识不变量**
    - 验证输出条目数 ≤ 2、无 ID 与主查询重复、每个 ID 都记录在 metadata 中
    - 测试文件: `server/tests/test_recommendation_properties.py`
    - **验证: 需求 3.1, 3.3, 3.6**

  - [x] 6.4 编写属性测试：推荐内容格式化正确性
    - **Property 6: 推荐内容格式化正确性**
    - 验证非空推荐时输出包含"您可能还想了解"和每条标题；空推荐时输出与原始回复相同
    - 测试文件: `server/tests/test_recommendation_properties.py`
    - **验证: 需求 3.4**

- [x] 7. 检查点 — 确保功能模块测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [-] 8. 实现多轮澄清机制
  - [x] 8.1 创建 `server/agent/clarification.py`
    - 实现 `ClarificationDetector` 类，包含 `should_clarify(confidence, session_context)`、`generate_clarification(intent, user_text)`、`should_escalate_to_human(session_context)` 方法
    - 定义 `CLARIFICATION_TEMPLATES` 意图到澄清选项模板映射
    - 置信度 < 阈值且轮次 < 2 时触发澄清；轮次 ≥ 2 时触发转人工
    - 模板缺失时生成通用澄清问题
    - _需求: 4.1, 4.2, 4.3, 4.6_

  - [x] 8.2 编写属性测试：澄清路由决策正确性
    - **Property 7: 澄清路由决策正确性**
    - 使用 Hypothesis 生成随机置信度、轮次、阈值，验证路由决策符合三条规则
    - 测试文件: `server/tests/test_clarification_properties.py`
    - **验证: 需求 4.1, 4.6**

  - [x] 8.3 编写属性测试：澄清问题选项生成
    - **Property 8: 澄清问题选项生成**
    - 验证有模板映射的意图生成的澄清问题包含所有模板选项文本，且以编号列表呈现
    - 测试文件: `server/tests/test_clarification_properties.py`
    - **验证: 需求 4.2, 4.3**

  - [x] 8.4 编写属性测试：澄清状态一致性
    - **Property 9: 澄清状态一致性**
    - 验证触发澄清后 `SessionContext.pending_clarification` 为 True、`original_ambiguous_message` 等于原始消息、`clarification_round` 递增 1，且 `MessageMetadata` 中字段一致
    - 测试文件: `server/tests/test_clarification_properties.py`
    - **验证: 需求 4.4, 4.8**

  - [x] 8.5 编写属性测试：澄清消息合并完整性
    - **Property 10: 澄清消息合并完整性**
    - 验证合并后的文本同时包含原始消息和澄清回复内容
    - 测试文件: `server/tests/test_clarification_properties.py`
    - **验证: 需求 4.5**

- [ ] 9. Engine 集成改造
  - [ ] 9.1 扩展 `AgentState` 类型定义
    - 在 `server/agent/engine.py` 的 `AgentState` 中新增 `user_profile`、`conversation_summary`、`recommendations`、`needs_clarification`、`clarification_message` 字段
    - _需求: 1.3, 2.4, 3.4, 4.1_

  - [ ] 9.2 实现新增 LangGraph 节点函数
    - 实现 `clarification_check_node`：调用 `ClarificationDetector.should_clarify()`，更新 `SessionContext` 澄清状态
    - 实现 `clarification_route`：根据澄清/转人工/继续三种情况路由
    - 实现 `summary_check_node`：调用 `Summarizer.check_and_summarize()`，替换 `state["messages"]` 中的历史消息
    - 实现 `profile_load_node`：调用 `ProfileStore.load()` 加载画像（3 秒超时降级），注入画像 Prompt 到 Worker 消息
    - 实现 `recommendation_node`：调用 `RecommendationEngine.get_recommendations()`，记录推荐 ID 到 metadata
    - 实现 `profile_update_node`：调用 `ProfileAnalyzer` 更新画像并持久化
    - _需求: 1.1, 1.3, 1.5, 2.2, 2.4, 2.5, 2.6, 3.1, 3.6, 4.1, 4.4, 4.5_

  - [ ] 9.3 改造 `_build_graph()` 图结构
    - 注册新节点：`clarification_check`、`summary_check`、`profile_load`、`recommend`、`profile_update`
    - 修改边连接：supervisor → clarification_check → (clarify→END / escalate→human_node / continue→summary_check) → profile_load → worker_node → ... → recommend → worker_done → reviewer → profile_update → END
    - 修改 `process_message()` 中的历史消息构建逻辑，移除硬编码的 `[-18:]` 截取
    - 在 `process_message()` 中初始化新增 `AgentState` 字段
    - _需求: 1.1, 1.3, 2.4, 3.4, 4.1, 4.5_

  - [ ] 9.4 集成澄清后重新分类逻辑
    - 在 `supervisor_node` 中检测 `pending_clarification` 状态，合并原始消息与澄清回复后重新分类
    - 澄清成功后清除 `pending_clarification` 状态
    - _需求: 4.5_

  - [ ]* 9.5 编写单元测试：Engine 集成关键路径
    - 测试摘要存储到 SessionContext（需求 1.4）
    - 测试 LLM 失败回退到 18 条（需求 1.5）
    - 测试首次对话使用默认画像（需求 2.5）
    - 测试画像加载超时降级（需求 2.6）
    - 测试推荐功能关闭时跳过（需求 3.5）
    - 测试推荐超时降级（需求 3.7）
    - 测试文件: `server/tests/test_engine_intelligence.py`
    - _需求: 1.4, 1.5, 2.5, 2.6, 3.5, 3.7_

- [ ] 10. 最终检查点 — 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的子任务为可选，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求条款，确保可追溯性
- 检查点任务用于阶段性验证，确保增量集成的正确性
- 属性测试验证设计文档中定义的 12 条正确性属性
- 单元测试验证具体的降级场景和边界条件
