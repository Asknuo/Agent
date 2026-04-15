# 小智 AI 智能客服

基于 LangGraph 多 Agent 协作架构的企业级智能客服系统。后端 Python FastAPI，前端 React + TypeScript，核心引擎使用 LangGraph 编排 3 个 AI Agent 协同工作，集成 RAG 知识库检索、情绪感知、意图识别、工具调用、链路追踪、Prometheus 监控等能力。

## 架构总览

```
用户消息
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI 中间件层                                      │
│  Trace(trace_id) → Auth(JWT) → RateLimit → Tenant    │
└──────────────────────┬───────────────────────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │           Supervisor (temp=0.0)      │
    │   LLM 智能路由 + 情绪/意图分析        │
    └──────┬──────────────────────────────┘
           │
    ┌──────▼──────────────────────────────┐
    │           Worker (temp=0.7)          │
    │   ReAct 工具循环 · 7 个工具           │
    │   知识检索 / 订单 / SQL / 退款 / 工单  │
    └──────┬──────────────────────────────┘
           │
    ┌──────▼──────────────────────────────┐
    │           Reviewer (temp=0.3)        │
    │   质检 · 情绪适配 · 合规 · 多语言      │
    └──────┬──────────────────────────────┘
           │
           ▼
       最终回复 (SSE 流式推送)
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Ant Design + Tailwind CSS |
| 后端 | Python FastAPI + WebSocket + SSE |
| Agent 引擎 | LangGraph + LangChain |
| LLM | OpenAI GPT-4o-mini（通过 `base_url` 兼容豆包/DeepSeek 等） |
| 向量检索 | FAISS + OpenAI / 豆包 Embeddings |
| 数据库 | PostgreSQL（可选，Agent 自动生成 SQL） |
| 监控 | Prometheus 指标 + 结构化 JSON 日志 + 链路追踪 |
| 配置 | YAML 集中配置 + 环境变量覆盖 |

## 项目结构

```
├── server/
│   ├── main.py              # FastAPI 入口 · SSE 流式 · WebSocket · /metrics
│   ├── agent.py             # LangGraph 3-Agent 引擎（Supervisor → Worker → Reviewer）
│   ├── tools.py             # 7 个 @tool 工具（知识检索/订单/SQL/退款/工单/转人工）
│   ├── knowledge_base.py    # RAG 三级检索（外部API → FAISS → 关键词）
│   ├── database.py          # PostgreSQL 接入层 · SQL 安全校验
│   ├── models.py            # Pydantic 数据模型
│   ├── config.py            # 集中式配置管理（YAML + ENV）
│   ├── logging_config.py    # 结构化 JSON 日志 · contextvars 链路关联
│   ├── tracing.py           # 链路追踪中间件 · Prometheus 指标 · timed_node 装饰器
│   └── tests/               # 属性测试（hypothesis）
├── src/
│   ├── App.tsx              # 聊天界面 · 元数据可视化
│   ├── api.ts               # SSE 流式客户端
│   └── index.css            # Tailwind 样式
├── data/
│   ├── knowledge/           # 知识库文档（.txt/.md 自动加载）
│   └── faiss_index/         # FAISS 向量索引（自动生成）
├── config.yaml              # 运行时配置（所有项均有默认值）
└── .env                     # 敏感配置（API Key 等）
```

## 快速启动

```bash
# 克隆 & 进入项目
git clone <repo-url> && cd ai-smart-customer-service

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 后端
pip install -r server/requirements.txt
python -m server.main          # 启动在 :8000

# 前端
npm install
npm run dev                    # 启动在 :3000，自动代理到后端
```

打开 http://localhost:3000 即可使用。

## 配置

所有配置集中在 `config.yaml`，环境变量可覆盖任意配置项（优先级：环境变量 > YAML > 默认值）。

### 必填

| 环境变量 | 说明 |
|----------|------|
| `OPENAI_API_KEY` | LLM API 密钥 |

### 常用可选

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `openai_base_url` | — | 自定义 LLM 端点（豆包/DeepSeek） |
| `openai_model` | `gpt-4o-mini` | 模型名称 |
| `log_level` | `INFO` | 日志级别 |
| `db_url` | — | PostgreSQL 连接串，填了启用 SQL 查询工具 |
| `db_allowed_tables` | `[]` | 限定可查询的表 |
| `auth_enabled` | `false` | JWT 认证开关 |
| `rate_limit_rpm` | `30` | 每分钟最大请求数 |
| `cache_ttl` | `300` | 知识库缓存过期秒数 |
| `max_concurrent_requests` | `20` | 最大并发 Agent 请求 |

### 外部 RAG 知识库（可选）

```env
RAG_API_URL=http://your-rag/api/search
RAG_API_KEY=your-key
```

配置后优先使用外部知识库，失败自动降级到本地 FAISS。

### 扩展知识库

往 `data/knowledge/` 放 `.txt` 或 `.md` 文件，启动时自动加载并向量化。格式：

```
第1行：标题
第2行：分类:标签1,标签2（可选）
第3行起：正文
```

## 核心能力

### 多 Agent 协作

Supervisor-Worker-Reviewer 三级流水线，每个 Agent 独立 prompt 和温度参数。Worker 通过 ReAct 循环自动推理调用工具，支持多步链（查知识库 → 查订单 → 计算退款）。Reviewer 审核回复的情绪适配和合规性。

### RAG 三级检索

外部 RAG API → 本地 FAISS 向量检索 → 关键词匹配，层层降级。FAISS 索引持久化到磁盘，文档新增时增量 embedding。

### 情绪感知

实时分析 5 种情绪（positive / neutral / negative / frustrated / confused），注入 LLM 上下文自适应回复风格。

### 可观测性

- 结构化 JSON 日志，每条包含 `trace_id`、`session_id`、`user_id`、`tenant_id`
- 链路追踪：每次请求生成唯一 `trace_id`，贯穿所有 Agent 节点
- Prometheus `/metrics` 端点：请求总数、延迟分布、活跃会话、工具调用次数、节点耗时

### 安全

- JWT 认证（可选开关）
- 速率限制（滑动窗口）
- SQL 注入防护（`sqlparse` AST 级校验，仅允许单条 SELECT，限制子查询深度）

### 容错

- LLM 调用指数退避重试
- 熔断器（连续失败自动降级）
- 基于意图+情绪的预定义降级回复，服务不中断

### 多语言

自动检测中英文，匹配用户语言回复。知识库内容为中文时，英文提问也会翻译后回复。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息，返回回复 + 元数据 |
| POST | `/api/chat/stream` | SSE 流式推送回复 |
| GET | `/api/sessions` | 会话列表 |
| GET | `/api/sessions/{id}` | 会话详情 |
| POST | `/api/sessions/{id}/rate` | 满意度评分（1-5） |
| GET | `/api/knowledge` | 知识库条目 |
| GET | `/api/tickets` | 工单列表 |
| GET | `/api/health` | 健康检查 |
| GET | `/metrics` | Prometheus 指标 |
| WS | `/ws` | WebSocket 实时通信 |

## 工具集

| 工具 | 功能 |
|------|------|
| `search_knowledge_tool` | RAG 知识库检索 |
| `query_order` | 查询订单状态 |
| `query_database` | SQL 查询 PostgreSQL |
| `get_db_schema` | 获取数据库表结构 |
| `calculate_refund` | 计算退款金额 |
| `create_ticket` | 创建工单 |
| `escalate_to_human` | 转接人工客服 |

## 测试

```bash
# 运行属性测试
python -m pytest server/tests/ -v
```

使用 [Hypothesis](https://hypothesis.readthedocs.io/) 进行属性测试，覆盖日志格式、配置校验、缓存、速率限制、熔断器等模块。

## License

MIT
