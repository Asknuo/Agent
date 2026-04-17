# Implementation Plan: Enterprise Agent Optimization

## Overview

Incrementally upgrade the "小智 AI 智能客服" system from prototype to enterprise-grade production. The implementation follows a layered approach: foundational infrastructure (config, logging, tracing) → security (auth, rate limiting, SQL guard) → resilience (retry, circuit breaker, concurrency) → performance (cache, embedding batch) → persistence (session store) → multi-tenancy → agent intelligence → frontend enhancements. Each module is self-contained and integrates via FastAPI middleware or dependency injection.

## Tasks

- [x] 1. Set up centralized configuration management (`server/config.py`)
  - [x] 1.1 Create `server/config.py` with `AppConfig` Pydantic model and `load_config()` function
    - Define all config fields with defaults: LLM, logging, auth, rate limiting, cache, concurrency, database, embedding, circuit breaker, multi-tenant
    - Implement YAML file loading with `pyyaml`
    - Implement environment variable override mapping (OPENAI_API_KEY, LOG_LEVEL, JWT_SECRET, DB_URL, etc.)
    - Add Pydantic validators for log_level, numeric ranges
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 1.2 Create `config.yaml` template at project root with documented defaults
    - _Requirements: 11.3_

  - [x] 1.3 Update `server/main.py` lifespan to load config and pass to modules
    - Replace scattered `os.getenv()` calls with config object references
    - Fail startup on missing required fields with clear error messages
    - _Requirements: 11.2, 11.4_

  - [ ]* 1.4 Write property tests for config validation (Property 16, Property 17)
    - **Property 16: Config validation** — invalid/missing fields raise specific errors
    - **Property 17: Env var override** — env vars take precedence over YAML values
    - **Validates: Requirements 11.1, 11.2, 11.4**

- [x] 2. Implement structured logging system (`server/logging_config.py`)
  - [x] 2.1 Create `server/logging_config.py` with `JSONFormatter` and `setup_logging()`
    - Implement `JSONFormatter` outputting single-line JSON with timestamp, level, module, message, trace_id, session_id, user_id, tenant_id
    - Use `contextvars` for trace context propagation (trace_id_var, session_id_var, user_id_var, tenant_id_var)
    - Support `extra_fields` via `extra` parameter for custom structured data
    - Implement exception formatting with type, message, and stack summary (last 3 frames)
    - Configure stdout + optional file handler based on config
    - _Requirements: 1.1, 1.3, 1.4, 1.5_

  - [x] 2.2 Integrate structured logging into `server/agent.py`
    - Replace all `print()` calls with `logger.info/warning/error`
    - Add node enter/exit logs with duration_ms, sentiment, intent in supervisor_node, worker_node, tool_node, reviewer_node
    - Set session_id_var and user_id_var in process_message
    - _Requirements: 1.2_

  - [x] 2.3 Replace `print()` calls in `server/knowledge_base.py`, `server/database.py`, `server/tools.py`, `server/main.py` with structured logger
    - _Requirements: 1.1, 1.2_

  - [x] 2.4 Write property tests for JSON log format (Property 1, Property 2)
    - **Property 1: JSON log format completeness** — all required fields present in output
    - **Property 2: Exception log structure** — exception entries contain type, stack_summary
    - **Validates: Requirements 1.1, 1.3**

- [x] 3. Implement tracing and Prometheus metrics (`server/tracing.py`)
  - [x] 3.1 Create `server/tracing.py` with trace middleware and Prometheus metrics
    - Implement `trace_middleware` that generates trace_id, sets contextvars, adds X-Trace-ID response header
    - Define Prometheus metrics: REQUEST_COUNT, REQUEST_LATENCY, ACTIVE_SESSIONS, TOOL_CALLS, NODE_DURATION
    - Implement `timed_node` decorator for wrapping agent graph nodes with timing
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.2 Register trace middleware in `server/main.py` and add `/metrics` endpoint
    - _Requirements: 2.3_

  - [x] 3.3 Apply `timed_node` decorator to supervisor_node, worker_node, tool_node, reviewer_node in `server/agent.py`
    - Record tool name, input summary, duration, and status for each tool call
    - _Requirements: 2.2, 2.4_

  - [x] 3.4 Write unit tests for trace middleware and metrics recording
    - Test trace_id generation and propagation
    - Test Prometheus metric increments
    - _Requirements: 2.1, 2.3_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement JWT authentication (`server/auth.py`)
  - [x] 5.1 Create `server/auth.py` with `AuthMiddleware` class
    - Implement Bearer token extraction and JWT decode with `python-jose`
    - Verify signature, expiration, and issuer fields
    - Exclude paths: /api/health, /metrics, /docs, /openapi.json
    - Set request.state.user_id and request.state.tenant_id from JWT payload
    - Support auth_enabled toggle from config (disabled by default for dev)
    - Log WARNING on auth failures
    - _Requirements: 4.1, 4.2, 4.3, 4.5_

  - [x] 5.2 Add WebSocket token verification in `server/main.py`
    - Accept token via query parameter on /ws endpoint
    - Reject connection on invalid token
    - _Requirements: 4.4_

  - [x] 5.3 Register AuthMiddleware in `server/main.py` middleware stack
    - _Requirements: 4.1_

  - [ ]* 5.4 Write property tests for JWT authentication (Property 5)
    - **Property 5: JWT authentication correctness** — accept valid tokens, reject invalid/expired/wrong-issuer
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [x] 6. Implement rate limiting (`server/rate_limiter.py`)
  - [x] 6.1 Create `server/rate_limiter.py` with `SlidingWindowRateLimiter` class
    - Implement sliding window algorithm with configurable max_requests and window_seconds
    - Support key-based limiting (IP or user_id)
    - Return (is_allowed, retry_after_seconds) tuple
    - _Requirements: 5.1, 5.2, 5.4_

  - [x] 6.2 Create rate limit middleware and register in `server/main.py`
    - Apply to /api/chat and /api/chat/stream endpoints
    - Return HTTP 429 with Retry-After header when exceeded
    - _Requirements: 5.1, 5.3_

  - [ ]* 6.3 Write property tests for sliding window rate limiter (Property 6)
    - **Property 6: Sliding window correctness** — at most max_requests allowed per window, positive Retry-After on rejection
    - **Validates: Requirements 5.1, 5.3, 5.4**

- [x] 7. Implement SQL injection guard (`server/sql_guard.py`)
  - [x] 7.1 Create `server/sql_guard.py` with `SQLGuard` class
    - Use `sqlparse` for AST-level SQL validation
    - Allow only single SELECT statements
    - Check subquery nesting depth (max 2)
    - Reject UNION keyword
    - Enforce result row limit (default 50, configurable)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 7.2 Integrate SQLGuard into `server/database.py` `execute_query()` function
    - Replace existing `_validate_sql` with SQLGuard validation
    - Apply row limit from config
    - _Requirements: 6.1, 6.2, 6.4_

  - [x] 7.3 Write property tests for SQL guard (Property 7)
    - **Property 7: SQL safety validation** — accept valid single SELECTs, reject non-SELECT/UNION/deep subqueries
    - **Validates: Requirements 6.2, 6.3**

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement retry engine and circuit breaker (`server/retry.py`, `server/circuit_breaker.py`)
  - [x] 9.1 Create `server/retry.py` with `RetryEngine` class
    - Implement exponential backoff: base_delay * 2^attempt (1s, 2s, 4s)
    - Configurable max_retries (default 3)
    - Log WARNING on each retry attempt
    - _Requirements: 7.1_

  - [x] 9.2 Create `server/circuit_breaker.py` with `CircuitBreaker` class
    - Implement three states: CLOSED, OPEN, HALF_OPEN
    - Transition CLOSED → OPEN after failure_threshold consecutive failures (default 5)
    - Transition OPEN → HALF_OPEN after recovery_timeout seconds (default 60)
    - Transition HALF_OPEN → CLOSED on successful call
    - Raise `CircuitOpenError` when circuit is open
    - _Requirements: 7.4, 7.5_

  - [x] 9.3 Integrate retry + circuit breaker into `server/agent.py` for LLM calls
    - Wrap `_worker_llm.invoke()` and `_supervisor_llm.invoke()` with retry + circuit breaker
    - On exhausted retries, return predefined fallback reply and log ERROR
    - _Requirements: 7.1, 7.3_

  - [x] 9.4 Add structured tool exception handling in `tool_node` in `server/agent.py`
    - Catch tool execution exceptions, return ToolMessage with error info to Worker
    - _Requirements: 7.2_

  - [x] 9.5 Write property tests for retry engine (Property 8) and circuit breaker (Property 10)
    - **Property 8: Exponential backoff** — N+1 attempts with correct delay pattern
    - **Property 10: Circuit breaker state transitions** — CLOSED→OPEN→HALF_OPEN→CLOSED
    - **Validates: Requirements 7.1, 7.4, 7.5**

  - [x] 9.6 Write property test for tool exception handling (Property 9)
    - **Property 9: Structured error on tool failure** — exceptions produce structured error messages
    - **Validates: Requirements 7.2**

- [x] 10. Implement cache layer (`server/cache.py`)
  - [x] 10.1 Create `server/cache.py` with `LRUCache` class
    - Implement OrderedDict-based LRU with configurable max_size and TTL
    - Implement get (with TTL check), put (with eviction), invalidate_pattern methods
    - Cache key generation via SHA256 hash of query text
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 10.2 Integrate cache into `server/knowledge_base.py` search functions
    - Cache knowledge search results with configurable TTL
    - Invalidate cache on knowledge base reload
    - _Requirements: 8.1, 8.3_

  - [x] 10.3 Write property tests for cache (Property 11, Property 12, Property 13)
    - **Property 11: Cache round trip + TTL** — get within TTL returns value, after TTL returns None
    - **Property 12: Pattern invalidation** — matching keys removed, non-matching preserved
    - **Property 13: LRU eviction** — size never exceeds max, LRU entry evicted
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [x] 11. Implement Embedding batch processing optimization
  - [x] 11.1 Refactor `server/knowledge_base.py` `_build_or_load_faiss` to use batch embedding
    - Implement `_batch_embed()` with configurable batch_size (default 32) and delay_ms (default 100)
    - Add retry logic per batch (max 2 retries), skip failed batches with WARNING log
    - Add inter-batch delay to avoid API rate limits
    - _Requirements: 9.1, 9.2, 9.3_

  - [x] 11.2 Write property test for batch splitting (Property 14)
    - **Property 14: Batch partitioning** — ⌈N/B⌉ batches, each ≤ B, union equals original
    - **Validates: Requirements 9.1**

- [x] 12. Implement concurrency control (`server/concurrency.py`)
  - [x] 12.1 Create `server/concurrency.py` with `ConcurrencyController` class
    - Implement asyncio.Semaphore-based concurrency limiting (default max 20)
    - Implement wait queue with configurable max size (default 50)
    - Return HTTP 503 when queue is full
    - Implement per-request timeout (default 120s), return HTTP 504 on timeout
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 12.2 Integrate ConcurrencyController into `server/main.py` chat endpoints
    - Wrap process_message calls with concurrency controller
    - _Requirements: 10.1, 10.2_

  - [x] 12.3 Write property test for concurrency control (Property 15)
    - **Property 15: Concurrency limit** — at most max_concurrent processing, 503 on overflow
    - **Validates: Requirements 10.1, 10.2**

- [x] 13. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. Implement session persistence (`server/session_store.py`)
  - [x] 14.1 Create `server/session_store.py` with `SessionStore` class
    - Implement async PostgreSQL operations using `asyncpg` connection pool
    - Implement `save()`, `load()`, `list_by_user()`, `upsert_messages()` methods
    - Serialize messages and context as JSONB
    - Fallback to in-memory dict on database write failure, log ERROR
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 14.2 Create database migration: sessions table with indexes
    - Create sessions table (id, user_id, tenant_id, messages JSONB, context JSONB, status, satisfaction, created_at, updated_at)
    - Add indexes on user_id, tenant_id, status, updated_at
    - _Requirements: 3.1_

  - [x] 14.3 Refactor `server/agent.py` to use SessionStore instead of in-memory `_sessions` dict
    - Replace `get_or_create_session`, `get_session`, `get_all_sessions`, `rate_session` with SessionStore calls
    - Update `process_message` to persist messages after each exchange
    - _Requirements: 3.2, 3.3_

  - [x] 14.4 Write property tests for session persistence (Property 3, Property 4)
    - **Property 3: Session round trip** — save then load produces equivalent session
    - **Property 4: User query completeness** — list_by_user returns all and only that user's sessions
    - **Validates: Requirements 3.3, 3.5**

- [x] 15. Implement multi-tenant support (`server/tenant.py`)
  - [x] 15.1 Create `server/tenant.py` with `TenantMiddleware`
    - Extract tenant_id from X-Tenant-ID header or JWT payload or default
    - Set tenant_id in contextvars and request.state
    - _Requirements: 13.1, 13.4_

  - [x] 15.2 Add tenant_id field to Session model in `server/models.py`
    - _Requirements: 13.1_

  - [x] 15.3 Update SessionStore queries to filter by tenant_id
    - Add WHERE tenant_id = $1 to all session queries
    - _Requirements: 13.2_

  - [x] 15.4 Update RAG pipeline to support per-tenant knowledge directories
    - Load knowledge from `data/knowledge/{tenant_id}/` when configured
    - Fall back to default `data/knowledge/` directory
    - _Requirements: 13.3_

  - [x] 15.5 Update rate limiter to use `{tenant_id}:{user_id}` as limiting key
    - Support per-tenant rate limit configuration via tenant_configs table
    - _Requirements: 13.5_

  - [x] 15.6 Create tenant_configs database table migration
    - _Requirements: 13.5_

  - [x] 15.7 Register TenantMiddleware in `server/main.py`
    - _Requirements: 13.1_

  - [x] 15.8 Write property tests for multi-tenant isolation (Property 19, Property 20)
    - **Property 19: Tenant session isolation** — sessions from tenant A not visible to tenant B
    - **Property 20: Tenant rate limit independence** — exhausting A's limit doesn't affect B
    - **Validates: Requirements 13.2, 13.5**

- [x] 16. Implement LLM-driven sentiment/intent analysis
  - [x] 16.1 Update Supervisor prompt and parsing in `server/agent.py`
    - Replace SUPERVISOR_PROMPT with SUPERVISOR_PROMPT_V2 that returns JSON with next, sentiment, intent, confidence
    - Parse LLM JSON response to extract all four fields in a single call
    - Fallback to existing keyword-based `_analyze_sentiment` and `_classify_intent` on LLM failure
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 16.2 Write property test for LLM analysis result parsing (Property 21)
    - **Property 21: Structured parsing** — valid JSON produces correct enum values, confidence clamped to [0,1]
    - **Validates: Requirements 14.1, 14.2, 14.5**

- [x] 17. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. Implement Agent execution visualization (backend SSE events)
  - [x] 18.1 Add AgentEvent model to `server/models.py`
    - Define event types: node_start, node_end, tool_call
    - Include node, tool, duration_ms, timestamp fields
    - Add agent_events list and trace_id to MessageMetadata
    - _Requirements: 15.1, 15.3_

  - [x] 18.2 Update `server/main.py` SSE stream to emit agent_event SSE messages
    - Collect agent events during graph execution
    - Push node_start, node_end, tool_call events via SSE before the text chunks
    - Include agent_events in metadata payload
    - _Requirements: 15.1, 15.3_

  - [ ]* 18.3 Write unit tests for SSE agent event emission
    - Verify event format and ordering
    - _Requirements: 15.1, 15.3_

- [x] 19. Implement frontend message reliability (`src/api.ts`, `src/App.tsx`)
  - [x] 19.1 Add message status tracking and retry logic in `src/App.tsx`
    - Add `status` field ('sending' | 'sent' | 'failed') to ChatMessage interface
    - Show failure indicator and retry button on failed messages
    - Implement retry handler that resends original message content
    - _Requirements: 12.1, 12.2_

  - [x] 19.2 Implement localStorage persistence in `src/App.tsx`
    - Save session messages to localStorage on each update
    - Restore messages from localStorage on page load
    - _Requirements: 12.3, 12.4_

  - [x] 19.3 Add SSE auto-reconnect logic in `src/api.ts`
    - Retry SSE connection on failure: 3 second delay, max 3 retries
    - _Requirements: 12.5_

  - [x] 19.4 Write property test for localStorage round trip (Property 18)
    - **Property 18: localStorage round trip** — save then load preserves all message fields
    - **Validates: Requirements 12.3**

- [x] 20. Implement Agent execution visualization (frontend)
  - [x] 20.1 Add AgentEvent TypeScript interface and update ChatMetadata in `src/api.ts`
    - Define AgentEvent interface with event, node, tool, duration_ms, timestamp
    - Add traceId and agentEvents to ChatMetadata
    - Parse agent_event SSE messages in sendMessageStream
    - _Requirements: 15.1, 15.2_

  - [x] 20.2 Create collapsible execution detail panel in `src/App.tsx`
    - Display agent execution steps (nodes, tools, durations) below assistant message bubbles
    - Default to collapsed state, toggle on click
    - _Requirements: 15.2, 15.4_

  - [x] 20.3 Write unit tests for agent event rendering
    - Test collapsed/expanded states
    - Test event display content
    - _Requirements: 15.2, 15.4_

- [x] 21. Update dependencies and wire everything together
  - [x] 21.1 Update `server/requirements.txt` with new dependencies
    - Add: prometheus_client, python-jose[cryptography], sqlparse, pyyaml, hypothesis
    - _Requirements: all_

  - [x] 21.2 Update `package.json` with frontend test dependency
    - Add: fast-check
    - _Requirements: all_

  - [x] 21.3 Register all middleware in correct order in `server/main.py`
    - Order: AuthMiddleware → RateLimitMiddleware → TraceMiddleware → TenantMiddleware
    - Add global exception handler
    - Wire ConcurrencyController into chat endpoints
    - _Requirements: all_

  - [x] 21.4 Extend `server/models.py` with all new data models
    - Add TenantConfig, TraceContext, NodeSpan, RequestTrace, AgentEvent, CircuitState, CacheEntry
    - Extend Session with tenant_id, extend MessageMetadata with trace_id and agent_events
    - _Requirements: all_

- [ ] 22. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation order ensures foundational modules (config, logging) are available for all subsequent modules
- All new modules follow the graceful degradation principle — failures fall back to existing behavior
