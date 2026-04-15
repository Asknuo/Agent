# 小智 AI 智能客服 — 项目文档

## 一、项目概述

基于 LangGraph 多 Agent 协作架构的智能客服系统。前端 React + TypeScript，后端 Python FastAPI，核心引擎使用 LangGraph 编排多个 AI Agent 协同工作，集成 RAG 知识库检索、情绪感知、意图识别、工具调用等能力。

## 二、核心设计思路

### 2.1 为什么用多 Agent 而不是单 Agent？

单 Agent 把所有职责塞进一个 prompt，容易出现：
- prompt 过长导致指令遵循能力下降
- 无法对不同环节做差异化调优（比如路由需要低温度高确定性，回复需要高温度有创造力）
- 没有质量把关环节

本项目采用 3-Agent 流水线，职责分离：

```
用户消息
    │
    ▼
┌──────────────┐
│  Supervisor   │  LLM 智能路由 + 情绪/意图分析
│  temp=0.0     │  决定走 Worker 还是直接转人工
└──────┬───────┘
       │
┌──────▼───────┐
│  Worker       │  干活 Agent，带 7 个工具（ReAct 循环）
│  temp=0.7     │  知识检索 / 订单查询 / 数据库查询 / 退款 / 工单 / 转人工
└──────┬───────┘
       │
┌──────▼───────┐
│  Reviewer     │  质检 Agent，审核回复质量
│  temp=0.3     │  情绪适配 / 合规检查 / 完整性
└──────┬───────┘
       │
       ▼
    最终回复
```

### 2.2 LangGraph 状态图

```
supervisor → route判断
               ├─ 转人工 → human_node → END
               └─ 正常   → worker_node ⇄ tool_node → worker_done → reviewer → END
```

- `supervisor`：用 LLM（temperature=0）做路由决策，同时完成情绪分析和意图识别
- `worker_node`：绑定了 7 个工具的 LLM，ReAct 模式自动推理调用
- `tool_node`：LangGraph 内置 ToolNode，执行工具后结果回到 worker 继续推理
- `reviewer`：独立 LLM 审核回复质量，可修正不当回复

### 2.3 RAG 知识库 — 三级检索策略

```
用户查询
    │
    ▼
┌─────────────────┐
│ 1. 外部 RAG API  │  你自己搭建的知识库（Dify/FastGPT/自建）
│    配了就优先用   │  通过 .env 配置 RAG_API_URL
└────────┬────────┘
         │ 失败或未配置
         ▼
┌─────────────────┐
│ 2. 内置 FAISS    │  本地向量检索（支持 OpenAI / 豆包多模态 Embedding）
│    启动时 embed   │  data/knowledge/ 目录文件自动切分向量化
└────────┬────────┘
         │ 失败
         ▼
┌─────────────────┐
│ 3. 关键词匹配    │  标签/标题/内容加权匹配
│    永远可用       │  兜底方案，不依赖任何外部服务
└─────────────────┘
```

### 2.4 情绪感知 & 自适应

每条用户消息实时分析 5 种情绪状态：
- positive（积极）/ neutral（中性）/ negative（消极）/ frustrated（焦躁）/ confused（困惑）

情绪信息注入到 LLM 上下文中，Agent 自动调整回复语气：
- 愤怒用户 → 先道歉安抚再解决问题
- 困惑用户 → 用更简单的语言，提供步骤指引
- 满意用户 → 轻松友好，推荐相关服务

## 三、技术架构

### 3.1 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | React 18 + TypeScript + Tailwind CSS | 聊天界面 + 实时元数据可视化 |
| 后端 | Python FastAPI + WebSocket | REST API + 实时通信 |
| Agent 引擎 | LangGraph + LangChain | 多 Agent 状态图编排 |
| LLM | OpenAI GPT-4o-mini（可替换） | 通过 base_url 兼容任意 LLM |
| 向量检索 | FAISS + OpenAI / 豆包 Embeddings | 本地向量库，支持增量更新，持久化到磁盘 |
| 数据库 | PostgreSQL + SQLAlchemy | 可选，Agent 自动生成 SQL 查询业务数据 |
| 外部 RAG | 可选，通过 HTTP API 对接 | 支持 Dify / FastGPT / 自建 |

### 3.2 项目结构

```
├── server/                  # Python 后端
│   ├── main.py              # FastAPI 入口 + SSE 流式 + WebSocket
│   ├── agent.py             # LangGraph 多 Agent 引擎（核心）
│   ├── tools.py             # LangChain @tool 工具集（7 个）
│   ├── knowledge_base.py    # RAG 三级检索系统
│   ├── database.py          # PostgreSQL 数据库接入层
│   ├── models.py            # Pydantic 数据模型
│   └── requirements.txt     # Python 依赖
├── src/                     # React 前端
│   ├── App.tsx              # 聊天界面主组件
│   ├── api.ts               # API 客户端（SSE 流式）
│   ├── main.tsx             # 入口
│   └── index.css            # 样式（Tailwind）
├── data/
│   ├── knowledge/           # 知识库文档目录（.txt/.md 自动加载）
│   └── faiss_index/         # FAISS 向量索引持久化目录（自动生成）
├── .env                     # 环境变量配置
└── package.json             # 前端依赖
```

### 3.3 Agent 工具集

| 工具 | 功能 | 触发场景 |
|------|------|----------|
| `search_knowledge_tool` | RAG 知识库检索 | 用户问政策/会员/支付等 |
| `query_order` | 查询订单状态（模拟数据） | 用户提供订单号 |
| `query_database` | 执行 SQL 查询 PostgreSQL | 查询真实业务数据（订单/用户/商品等） |
| `get_db_schema` | 获取数据库表结构 | 不确定表名或字段时先调用 |
| `calculate_refund` | 计算退款金额 | 用户申请退款 |
| `create_ticket` | 创建工单 | 复杂问题需人工跟进 |
| `escalate_to_human` | 转接人工客服 | 用户明确要求 |

## 四、核心亮点

1. **LangGraph 多 Agent 协作**：Supervisor-Worker-Reviewer 三级流水线，职责分离，每个 Agent 独立 prompt 和温度参数
2. **ReAct 工具循环**：Worker 和工具节点形成循环边，支持多步推理链（查知识库 → 查订单 → 计算退款）
3. **质检 Agent**：回复不直接返回用户，经过 Reviewer 审核情绪适配和合规性
4. **RAG 三级检索**：外部 RAG API → FAISS 向量检索 → 关键词匹配，层层降级
5. **FAISS 增量更新**：索引持久化到磁盘，文档新增时只对增量部分做 embedding，避免全量重建
6. **豆包多模态 Embedding 兼容**：自动识别豆包 ARK 端点，调用 `/embeddings/multimodal` 接口
7. **PostgreSQL 数据库查询**：Agent 自动生成 SQL 查询真实业务数据，内置只读模式 + 表白名单安全防护
8. **情绪感知**：实时分析 5 种情绪，注入 LLM 上下文，自适应回复风格
9. **SSE 流式输出**：前端通过 Server-Sent Events 逐块接收回复，模拟打字效果
10. **优雅降级**：LLM API 挂了根据意图+情绪给兜底回复，服务不中断
11. **LangChain @tool 装饰器**：零样板代码定义工具，自动生成 JSON schema
12. **前端元数据可视化**：每条消息展示情绪/意图/工具调用/响应耗时
13. **多语言支持**：自动检测中英文，匹配用户语言回复
14. **外部 RAG 对接**：通过 .env 配置即可对接 Dify/FastGPT/自建知识库

## 五、快速启动

```bash
# 1. 克隆项目
git clone <repo-url> && cd ai-smart-customer-service

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY

# 3. 安装后端依赖
pip install -r server/requirements.txt

# 4. 安装前端依赖
npm install

# 5. 启动后端（端口 8000）
python -m server.main

# 6. 启动前端（端口 3000，自动代理到后端）
npm run dev

# 7. 打开浏览器 http://localhost:3000
```

## 六、配置说明

### 6.1 基础配置（.env）

```env
OPENAI_API_KEY=sk-xxx          # 必填
OPENAI_BASE_URL=               # 可选，兼容其他 LLM 提供商（豆包/DeepSeek 等）
OPENAI_MODEL=gpt-4o-mini       # 可选，默认 gpt-4o-mini
EMBEDDING_MODEL=               # 可选，默认 text-embedding-3-small（豆包填 ep-xxx）
```

### 6.2 外部 RAG 知识库（可选）

```env
RAG_API_URL=http://your-rag/api/search   # 填了就优先用你的知识库
RAG_API_KEY=your-key                      # 鉴权 token
RAG_QUERY_FIELD=query                     # 请求体查询字段名
RAG_RESPONSE_PATH=data                    # 响应中结果数组路径
RAG_CONTENT_FIELD=content                 # 结果内容字段
RAG_TITLE_FIELD=title                     # 结果标题字段
```

### 6.3 PostgreSQL 数据库（可选）

```env
DB_URL=postgresql://user:pass@host:5432/dbname   # 填了就启用数据库查询工具
DB_ALLOWED_TABLES=orders,users,products           # 可选，限制可查询的表（逗号分隔）
DB_READONLY=true                                   # 可选，默认 true，只允许 SELECT
```

### 6.4 扩展知识库

往 `data/knowledge/` 目录放 `.txt` 或 `.md` 文件，启动时自动加载：

```
退换货流程.txt
├── 第1行：标题
├── 第2行：分类:标签1,标签2（可选）
└── 第3行起：正文内容
```

## 七、API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息，返回 AI 回复 + 元数据 |
| POST | `/api/chat/stream` | SSE 流式发送消息，逐块推送回复 |
| GET | `/api/sessions` | 获取所有会话列表 |
| GET | `/api/sessions/{id}` | 获取单个会话详情 |
| POST | `/api/sessions/{id}/rate` | 会话满意度评分（1-5） |
| GET | `/api/knowledge` | 获取知识库所有条目 |
| GET | `/api/tickets` | 获取所有工单 |
| GET | `/api/health` | 健康检查 |
| WS | `/ws` | WebSocket 实时通信 |
