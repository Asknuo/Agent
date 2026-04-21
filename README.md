# 小智 AI 智能客服

基于 LangGraph 多 Agent 协作架构的企业级智能客服系统。后端 Python FastAPI，前端 React + TypeScript，核心引擎使用 LangGraph 编排多个 AI Agent 协同工作，集成 RAG 知识库检索、情绪感知、意图识别、多轮澄清、用户画像、主动推荐、工具调用、链路追踪、Prometheus 监控等能力。

## 架构总览

```
用户消息
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI 中间件层                                              │
│  Trace(trace_id) → Auth(JWT) → RateLimit → Tenant            │
└──────────────────────────┬───────────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │           Supervisor (temp=0.0)              │
    │   LLM 智能路由 + 情绪/意图分析 + 置信度评估    │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │       Clarification Check                    │
    │   置信度 < 阈值 → 生成选项式澄清问题           │
    │   连续 2 轮失败 → 自动转人工                   │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │       Summary Check                          │
    │   消息数 > 阈值 → LLM 压缩历史为结构化摘要     │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │       Profile Load                           │
    │   加载用户画像 → 注入风格/主题/交互次数 Prompt  │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │           Worker (temp=0.7)                   │
    │   ReAct 工具循环 · 7 个工具                    │
    │   知识检索 / 订单 / SQL / 退款 / 工单           │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │       Recommendation                         │
    │   基于意图关联主题推送补充知识（去重 + 超时降级） │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │           Reviewer (temp=0.3)                │
    │   质检 · 情绪适配 · 合规 · 多语言 · 货币校验   │
    │   快速通道：正面/中性情绪跳过 LLM 审核          │
    └──────┬──────────────────────────────────────┘
           │
    ┌──────▼──────────────────────────────────────┐
    │       Profile Update                         │
    │   更新沟通风格 / 高频主题 / 满意度趋势          │
    └──────┬──────────────────────────────────────┘
           │
           ▼
       最终回复 (SSE 流式推送 + Agent 执行事件)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design 6 + Tailwind CSS |
| 构建工具 | Vite 5 |
| 后端 | Python FastAPI + WebSocket + SSE |
| Agent 引擎 | LangGraph + LangChain |
| LLM | OpenAI GPT-4o-mini（通过 `base_url` 兼容豆包/DeepSeek 等） |
| 向量检索 | FAISS + OpenAI / 豆包多模态 Embeddings |
| 数据库 | PostgreSQL（asyncpg 异步驱动 + SQLAlchemy） |
| 认证 | JWT（python-jose） |
| 监控 | Prometheus 指标 + 结构化 JSON 日志 + 链路追踪 |
| 测试 | Hypothesis（后端属性测试）+ Vitest + fast-check（前端属性测试） |
| 配置 | YAML 集中配置 + 环境变量覆盖 |

## 项目结构

```
├── server/                          # Python 后端
│   ├── main.py                      # FastAPI 入口 · SSE 流式 · WebSocket · /metrics
│   ├── core/                        # 基础设施
│   │   ├── config.py                # 集中式配置管理（YAML + ENV，Pydantic 校验）
│   │   ├── logging_config.py        # 结构化 JSON 日志 · contextvars 链路关联 · 按日期分目录
│   │   └── models.py                # Pydantic 数据模型 · 枚举 · API 请求/响应
│   ├── agent/                       # Agent 引擎
│   │   ├── engine.py                # LangGraph 多节点引擎（10 个节点的完整流水线）
│   │   ├── tools.py                 # 7 个 @tool 工具（知识检索/订单/SQL/退款/工单/转人工）
│   │   ├── clarification.py         # 多轮澄清检测与生成（意图模板 + 通用降级）
│   │   ├── summarizer.py            # 长会话摘要压缩（LLM 生成结构化摘要）
│   │   ├── recommendation.py        # 主动知识推荐引擎（意图关联 + 去重 + 超时降级）
│   │   └── profile_analyzer.py      # 用户画像分析（沟通风格/高频主题/满意度趋势）
│   ├── data/                        # 数据访问层
│   │   ├── knowledge_base.py        # RAG 三级检索（外部API → FAISS → 关键词）+ 批处理 Embedding
│   │   ├── database.py              # PostgreSQL 接入层 · SQL 安全校验
│   │   ├── session_store.py         # 会话持久化（PostgreSQL + 内存降级）
│   │   ├── profile_store.py         # 用户画像持久化（PostgreSQL + asyncpg）
│   │   └── sql_guard.py             # SQL 注入防护（sqlparse AST 级校验）
│   ├── middleware/                   # HTTP 中间件
│   │   ├── auth.py                  # JWT 认证 · 用户注册/登录 · PostgreSQL + 内存回退
│   │   ├── rate_limiter.py          # 滑动窗口速率限制（per-tenant + per-user）
│   │   ├── tracing.py               # 链路追踪 · Prometheus 指标 · timed_node 装饰器 · Agent 事件收集
│   │   └── tenant.py                # 多租户中间件（Header > JWT > 默认值）
│   ├── resilience/                   # 容错与性能控制
│   │   ├── cache.py                 # LRU 缓存（TTL + 模式失效 + 全量清除）
│   │   ├── circuit_breaker.py       # 熔断器（三态状态机：CLOSED → OPEN → HALF_OPEN）
│   │   ├── concurrency.py           # 并发控制（Semaphore + 等待队列 + 超时）
│   │   └── retry.py                 # 指数退避重试引擎
│   ├── migrations/                   # SQL 迁移脚本（6 个）
│   └── tests/                        # 属性测试（18 个测试文件）
├── src/                              # React 前端
│   ├── App.tsx                       # 聊天主界面 · 登录 · 监控面板 · 会话侧边栏
│   ├── api.ts                        # SSE 流式客户端 · JWT Token 管理 · 自动重连
│   ├── main.tsx                      # React 入口
│   ├── index.css                     # Tailwind + 自定义样式
│   ├── theme.ts                      # 主题配置（亮色/暗色/跟随系统）
│   ├── ThemeProvider.tsx             # 主题上下文 Provider
│   ├── i18n.ts                       # 国际化核心逻辑
│   ├── I18nProvider.tsx              # 国际化上下文 Provider
│   ├── search.ts                     # 消息搜索（关键词 + 角色过滤）
│   ├── export.ts                     # 对话导出（JSON / PDF）
│   ├── locales/                      # 语言包
│   │   ├── zh-CN.ts                  # 简体中文
│   │   └── en-US.ts                  # English
│   └── __tests__/                    # 前端属性测试（6 个测试文件）
├── data/
│   ├── knowledge/                    # 知识库文档（.txt/.md 自动加载并向量化）
│   └── faiss_index/                  # FAISS 向量索引（自动生成，持久化到磁盘）
├── config.yaml                       # 运行时配置（所有项均有默认值）
└── .env                              # 敏感配置（API Key、数据库连接串等）
```


## 快速启动

### 前置条件

- Python 3.11+
- Node.js 18+
- PostgreSQL（可选，不配置时会话存储自动降级为内存模式）

### 安装与运行

```bash
# 克隆 & 进入项目
git clone <repo-url> && cd ai-smart-customer-service

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY（必填）

# 后端
pip install -r server/requirements.txt
python -m server.main          # 启动在 :8000

# 前端
npm install
npm run dev                    # 启动在 :5173，Vite 自动代理到后端
```

打开 http://localhost:5173 即可使用。默认管理员账号：`admin / admin`。

### 数据库初始化（可选）

如需启用 PostgreSQL 持久化（会话存储、用户管理、画像存储），按顺序执行迁移脚本：

```bash
psql -d your_database -f server/migrations/001_create_sessions.sql
psql -d your_database -f server/migrations/002_create_tenant_configs.sql
psql -d your_database -f server/migrations/003_create_users.sql
psql -d your_database -f server/migrations/004_alter_users_add_id.sql
psql -d your_database -f server/migrations/005_create_user_profiles.sql
```

然后在 `.env` 中配置 `SESSION_DB_URL`。

## 配置

所有配置集中在 `config.yaml`，环境变量可覆盖任意配置项（优先级：环境变量 > YAML > 代码默认值）。配置由 Pydantic 模型校验，启动时自动检查必填项和格式。

### 必填

| 环境变量 | 说明 |
|----------|------|
| `OPENAI_API_KEY` | LLM API 密钥 |

### LLM 配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `openai_base_url` | — | 自定义 LLM 端点（豆包 ARK / DeepSeek 等） |
| `openai_model` | `gpt-4o-mini` | 模型名称 |
| `embedding_model` | `text-embedding-3-small` | Embedding 模型（支持豆包多模态端点） |

### 数据库

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `db_url` | — | 商品查询数据库连接串（远程 PostgreSQL） |
| `session_db_url` | — | 会话/用户持久化数据库连接串（本地 PostgreSQL） |
| `db_allowed_tables` | `[]` | 限定 Agent 可查询的表，空则允许所有 |
| `db_readonly` | `true` | 只读模式，仅允许 SELECT |
| `sql_max_rows` | `50` | 查询结果行数上限 |
| `sql_max_subquery_depth` | `2` | 子查询最大嵌套层数 |

### 安全与限流

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auth_enabled` | `false` | JWT 认证开关（开发环境默认关闭） |
| `jwt_secret` | 内置开发密钥 | JWT 签名密钥（生产环境必须修改） |
| `rate_limit_rpm` | `30` | 每分钟最大请求数（per-tenant:per-user） |
| `rate_limit_enabled` | `true` | 速率限制开关 |

### 缓存与性能

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `cache_ttl` | `300` | 知识库缓存过期秒数 |
| `cache_max_size` | `1000` | LRU 缓存最大条目数 |
| `max_concurrent_requests` | `20` | 最大并发 Agent 请求数 |
| `request_timeout` | `120` | 单次请求超时秒数 |
| `max_queue_size` | `50` | 等待队列最大长度 |

### 容错

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `circuit_breaker_threshold` | `5` | 连续失败次数触发熔断 |
| `circuit_breaker_recovery_s` | `60` | 熔断恢复探测间隔秒数 |
| `retry_max_attempts` | `3` | LLM 调用最大重试次数 |
| `retry_base_delay` | `1.0` | 重试基础延迟秒数（指数退避） |

### 智能化功能

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `summary_threshold` | `20` | 触发长会话摘要的消息数阈值 |
| `summary_recent_count` | `8` | 摘要后保留的最近消息数 |
| `profile_load_timeout` | `3` | 画像加载超时秒数（超时降级为默认画像） |
| `recommendation_enabled` | `true` | 主动推荐开关 |
| `recommendation_timeout` | `2` | 推荐检索超时秒数 |
| `clarification_confidence_threshold` | `0.4` | 触发多轮澄清的置信度阈值 |

### 外部 RAG 知识库（可选）

```env
RAG_API_URL=http://your-rag/api/search
RAG_API_KEY=your-key
```

配置后优先使用外部知识库，失败自动降级到本地 FAISS。

### Embedding 批处理

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `embedding_batch_size` | `32` | 每批文档数 |
| `embedding_batch_delay_ms` | `100` | 批间延迟毫秒数（避免 API 速率限制） |

### 扩展知识库

往 `data/knowledge/` 放 `.txt` 或 `.md` 文件，启动时自动加载、切分并向量化。文件格式：

```
第1行：标题
第2行：分类:标签1,标签2（可选）
第3行起：正文
```

文档切分策略：`chunk_size=500, overlap=80`，优先按 Markdown 标题、空行、句号等自然边界切分。FAISS 索引持久化到 `data/faiss_index/`，文档新增时增量 embedding，无需全量重建。

## 核心能力

### 多 Agent 协作流水线

LangGraph 编排的 10 节点流水线，每个节点独立职责：

1. **Supervisor** — LLM 智能路由 + 情绪/意图/置信度分析（关键词规则降级兜底）
2. **Clarification Check** — 低置信度时生成选项式澄清问题，连续 2 轮失败自动转人工
3. **Summary Check** — 消息数超阈值时 LLM 压缩历史为结构化摘要（含关键实体、未解决问题）
4. **Profile Load** — 加载用户画像（3 秒超时降级），注入沟通风格/高频主题 Prompt
5. **Worker** — ReAct 工具循环，自动推理调用 7 个工具，支持多步链
6. **Tool Node** — 工具执行层，结构化异常处理，失败返回 ToolMessage 让 Worker 选择替代方案
7. **Recommendation** — 基于意图关联主题推送补充知识，去重 + 超时降级
8. **Worker Done** — 提取 Worker 最终回复
9. **Reviewer** — 质检审核（情绪适配、合规、多语言、货币单位校验），正面/中性情绪快速通道跳过 LLM
10. **Profile Update** — 更新沟通风格、高频主题、满意度趋势并持久化

### RAG 三级检索

```
外部 RAG API → 本地 FAISS 向量检索 → 关键词匹配
```

- 层层降级，任一层命中即返回
- 检索结果 LRU 缓存（可配置 TTL + 模式失效）
- FAISS 索引持久化到磁盘，文档新增时增量 embedding
- 批处理 Embedding：分批发送 + 批间延迟 + 失败重试 + 跳过失败批次
- 支持豆包多模态 Embedding 端点（自动检测 `ep-` 前缀模型）

### 情绪感知

实时分析 5 种情绪（positive / neutral / negative / frustrated / confused）：
- LLM 分析为主，关键词规则为降级兜底
- 情绪注入 LLM 上下文，自适应回复风格
- Reviewer 审核情绪适配度（愤怒→安抚，困惑→耐心）

### 多轮澄清

- 意图置信度低于阈值时自动触发
- 基于意图模板生成选项式澄清问题（退款/订单/产品/技术/投诉各有专属选项）
- 澄清回复与原始消息合并后重新分类
- 连续 2 轮澄清失败自动转人工

### 用户画像

- 基于对话内容推断沟通风格（formal / casual / concise）
- 提取高频咨询主题
- 情绪→满意度分数映射，追踪满意度趋势
- 画像持久化到 PostgreSQL，首次对话使用默认画像
- 加载超时 3 秒自动降级，不阻塞回复

### 主动推荐

- 基于当前意图关联主题，从 RAG 管线额外检索补充知识
- 与主查询结果基于 ID 去重
- 超时自动放弃，功能可配置开关
- 推荐内容以"您可能还想了解"格式附加在主回复之后

### 长会话摘要

- 消息数超过可配置阈值时，LLM 将早期历史压缩为结构化摘要
- 摘要包含：摘要文本、关键实体、未解决问题、生成时间
- 摘要复用：消息数未重新超阈值时直接复用已有摘要
- LLM 失败时回退到最近 18 条消息
- 安全反序列化：非法 JSON 返回空摘要而不抛异常

### 可观测性

- **结构化 JSON 日志**：每条包含 `trace_id`、`session_id`、`user_id`、`tenant_id`
- **日志按日期分目录**：`logs/YYYY/MM/DD.log`，自动创建目录
- **链路追踪**：每次请求生成唯一 `trace_id`，贯穿所有 Agent 节点，响应头 `X-Trace-ID`
- **Prometheus `/metrics` 端点**：
  - `agent_requests_total` — 请求总数（按端点/方法/状态码）
  - `agent_request_duration_ms` — 请求延迟分布
  - `agent_tool_calls_total` — 工具调用次数（按工具名/状态）
  - `agent_node_duration_ms` — 节点执行耗时分布
  - `agent_active_sessions` — 活跃会话数
- **Agent 执行事件**：node_start / node_end / tool_call 事件通过 SSE 实时推送到前端

### 安全

- **JWT 认证**：可选开关，支持注册/登录，用户数据 PostgreSQL + 内存回退
- **速率限制**：滑动窗口算法，per-tenant:per-user 粒度，HTTP 429 + Retry-After
- **SQL 注入防护**：`sqlparse` AST 级校验，仅允许单条 SELECT，禁止 UNION，限制子查询深度，自动追加 LIMIT
- **数据库只读模式**：禁止 DROP/TRUNCATE/DELETE/ALTER 等危险操作
- **表白名单**：可限定 Agent 可查询的表

### 容错

- **LLM 调用指数退避重试**：`base_delay * 2^attempt`，可配置最大重试次数
- **熔断器**：三态状态机（CLOSED → OPEN → HALF_OPEN），连续失败自动降级
- **降级回复**：基于意图+情绪的预定义回复，LLM 不可用时服务不中断
- **并发控制**：Semaphore 限流 + 等待队列 + 请求超时（503/504）
- **会话存储降级**：PostgreSQL 不可用时自动回退内存存储
- **工具执行异常处理**：失败返回 ToolMessage，Worker 自动选择替代方案

### 多租户

- 从请求中提取 tenant_id（X-Tenant-ID Header > JWT > 默认值）
- 注入 contextvars 供日志和下游使用
- 支持租户级知识库目录（`data/knowledge/{tenant_id}/`）
- 速率限制 per-tenant 隔离

### 多语言

- 自动检测中英文（基于中文字符占比）
- 匹配用户语言回复，知识库内容为中文时英文提问也会翻译后回复
- 前端完整国际化（中文/英文），支持运行时切换

## 前端功能

- **聊天界面**：SSE 流式打字效果，Markdown 渲染，消息状态指示（发送中/已发送/失败）
- **Agent 执行可视化**：实时展示 Agent 流水线执行步骤和耗时
- **元数据展示**：情绪标签、意图分类、置信度、使用工具、响应时间、trace_id
- **会话管理**：侧边栏会话列表（按日期分组），支持切换历史会话
- **会话持久化**：localStorage 本地缓存 + 服务端 PostgreSQL 持久化
- **满意度评分**：1-5 星评分，评分后不可重复
- **快捷回复**：预设常见问题快捷按钮
- **消息搜索**：关键词搜索 + 角色过滤（用户/助手），高亮匹配文本
- **对话导出**：支持导出为 JSON 和 PDF 格式
- **暗色模式**：亮色/暗色/跟随系统三种模式，CSS 变量驱动
- **国际化**：中文/英文运行时切换
- **登录/注册**：JWT 认证，Token 自动管理，401 自动跳转登录
- **系统监控面板**：实时展示 Prometheus 指标（请求数、工具调用、节点耗时），支持自动刷新
- **SSE 自动重连**：最多 3 次重试，间隔 3 秒
- **失败重发**：消息发送失败后支持点击重发

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/register` | 用户注册 |
| POST | `/api/login` | 用户登录，返回 JWT Token |
| POST | `/api/chat` | 发送消息，返回回复 + 元数据 |
| POST | `/api/chat/stream` | SSE 流式推送回复 + Agent 执行事件 |
| GET | `/api/sessions` | 会话列表（按用户过滤） |
| GET | `/api/sessions/{id}` | 会话详情 |
| POST | `/api/sessions/{id}/rate` | 满意度评分（1-5） |
| GET | `/api/knowledge` | 知识库条目列表 |
| GET | `/api/tickets` | 工单列表 |
| GET | `/api/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标端点 |
| WS | `/ws` | WebSocket 实时通信（支持 JWT 认证） |

### SSE 事件类型

| type | 说明 |
|------|------|
| `session` | 会话 ID |
| `agent_event` | Agent 执行事件（node_start / node_end / tool_call） |
| `chunk` | 文本块（模拟打字效果） |
| `metadata` | 完整元数据（情绪/意图/工具/耗时等） |
| `done` | 流结束信号 |

## 工具集

| 工具 | 功能 |
|------|------|
| `search_knowledge_tool` | RAG 知识库检索（三级降级） |
| `query_order` | 查询订单状态（模拟数据） |
| `query_database` | SQL 查询 PostgreSQL（AST 级安全校验） |
| `get_db_schema` | 获取数据库表结构 |
| `calculate_refund` | 计算退款金额 |
| `create_ticket` | 创建工单 |
| `escalate_to_human` | 转接人工客服 |

## 数据库 Schema

项目使用两个 PostgreSQL 数据库（可以是同一个）：

- **商品查询数据库**（`DB_URL`）：Agent 通过 SQL 工具查询的业务数据
- **会话持久化数据库**（`SESSION_DB_URL`）：会话、用户、画像等系统数据

### 系统表

| 表名 | 说明 | 迁移脚本 |
|------|------|----------|
| `sessions` | 会话数据（消息 JSONB、上下文 JSONB、状态、评分） | 001 |
| `tenant_configs` | 租户配置（速率限制、知识库目录、自定义 Prompt） | 002 |
| `users` | 用户账号（用户名、密码哈希、角色） | 003, 004 |
| `user_profiles` | 用户画像（语言偏好、沟通风格、高频主题、满意度历史） | 005 |

## 测试

### 后端属性测试（Hypothesis）

```bash
python -m pytest server/tests/ -v
```

覆盖模块：
- 日志格式与结构化输出
- 配置校验与类型转换
- LRU 缓存（TTL、LRU 淘汰、模式失效）
- 速率限制（滑动窗口）
- 熔断器（状态转换）
- 重试引擎（指数退避）
- SQL 注入防护（AST 校验）
- 会话存储（序列化/反序列化）
- 并发控制
- 多轮澄清
- 用户画像分析
- 主动推荐（去重、超时）
- 长会话摘要（序列化安全）
- LLM 分析响应解析
- 多租户
- 批处理 Embedding
- 工具异常处理
- Agent 执行事件

### 前端属性测试（Vitest + fast-check）

```bash
npm run test
```

覆盖模块：
- 主题切换与解析
- 国际化翻译
- localStorage 持久化
- 消息搜索与过滤
- 对话导出
- Agent 事件渲染

## 中间件执行顺序

```
请求 → CORS → Auth(JWT) → RateLimit → Trace(trace_id) → Tenant → 路由处理
```

Starlette 按注册逆序处理，代码中注册顺序为 Tenant → Trace → RateLimit → Auth → CORS。

## License

MIT
