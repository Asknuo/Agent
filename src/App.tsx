import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendMessageStream, rateSession, fetchMetrics, loginApi, registerApi, setToken, clearAuth, getToken, ChatMetadata, MetricEntry, AgentEvent, fetchSessions, fetchSessionDetail, SessionSummary } from './api';
import ReactMarkdown from 'react-markdown';
import { Tag, Rate, Tooltip, Dropdown, ConfigProvider, theme as antdTheme } from 'antd';
import {
  SendOutlined, ReloadOutlined, ClockCircleOutlined, ToolOutlined,
  DashboardOutlined, LogoutOutlined, UserOutlined, LockOutlined,
  ExclamationCircleOutlined, DownloadOutlined, FilePdfOutlined, FileTextOutlined,
  SearchOutlined, CloseOutlined, MessageOutlined, PlusOutlined, MenuOutlined,
} from '@ant-design/icons';
import { ThemeProvider, useTheme } from './ThemeProvider';
import { I18nProvider, useI18n } from './I18nProvider';
import { exportToJSON, exportToPDF, downloadBlob } from './export';
import type { ExportOptions } from './export';
import { useMessageSearch } from './search';
import type { SearchableMessage } from './search';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: ChatMetadata;
  status?: 'sending' | 'sent' | 'failed';
  agentEvents?: AgentEvent[];
}

// ── localStorage 持久化 ──────────────────────────────

const SESSION_STORAGE_KEY = 'xiaozhi_session';

function saveSessionToStorage(sessionId: string | undefined, messages: ChatMessage[]) {
  try {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ sessionId, messages }));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

function loadSessionFromStorage(): { sessionId: string | undefined; messages: ChatMessage[] } | null {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (parsed && Array.isArray(parsed.messages)) return parsed;
    return null;
  } catch {
    return null;
  }
}

function clearSessionStorage() {
  localStorage.removeItem(SESSION_STORAGE_KEY);
}

interface UserInfo {
  username: string;
  role: 'user' | 'admin';
}

const quickReplyKeys = [
  { icon: '📦', key: 'chat.quick.orderQuery' },
  { icon: '💰', key: 'chat.quick.refundPolicy' },
  { icon: '👑', key: 'chat.quick.memberBenefits' },
  { icon: '👤', key: 'chat.quick.humanAgent' },
  { icon: '🌐', key: 'chat.quick.paymentMethods' },
];

const sentimentKeys: Record<string, { color: string; key: string }> = {
  positive: { color: 'green', key: 'sentiment.positive' },
  neutral: { color: 'default', key: 'sentiment.neutral' },
  negative: { color: 'red', key: 'sentiment.negative' },
  frustrated: { color: 'orange', key: 'sentiment.frustrated' },
  confused: { color: 'gold', key: 'sentiment.confused' },
};

const intentKeys: Record<string, string> = {
  product_inquiry: 'intent.product_inquiry', order_status: 'intent.order_status',
  refund_request: 'intent.refund_request', technical_support: 'intent.technical_support',
  complaint: 'intent.complaint', general_chat: 'intent.general_chat',
  human_handoff: 'intent.human_handoff', feedback: 'intent.feedback',
};

// ── 主题切换按钮 ─────────────────────────────────────

function ThemeToggleButton() {
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();
  const icon = theme === 'dark' ? '🌙' : theme === 'system' ? '💻' : '☀️';
  const label = theme === 'dark' ? t('theme.dark') : theme === 'system' ? t('theme.system') : t('theme.light');
  return (
    <Tooltip title={label} placement="bottom">
      <button className="header-btn" onClick={toggleTheme} aria-label={t('theme.toggle.ariaLabel')}>
        <span style={{ fontSize: 16 }}>{icon}</span>
      </button>
    </Tooltip>
  );
}

// ── 登录页面 ─────────────────────────────────────────

function LoginPage({ onLogin }: { onLogin: (user: UserInfo) => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isRegister, setIsRegister] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError(t('login.error.empty'));
      return;
    }
    if (password.length < 3) {
      setError(t('login.error.passwordShort'));
      return;
    }
    setLoading(true);
    setError('');

    try {
      const res = isRegister
        ? await registerApi(username.trim(), password)
        : await loginApi(username.trim(), password);

      setToken(res.token);
      const user: UserInfo = { username: res.username, role: res.role };
      localStorage.setItem('xiaozhi_user', JSON.stringify(user));
      onLogin(user);
    } catch (err: any) {
      setError(err.message || (isRegister ? t('login.error.registerFailed') : t('login.error.loginFailed')));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-bg">
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-orb bg-orb-3" />
      <div style={{ position: 'absolute', top: 16, right: 16, zIndex: 10 }}>
        <ThemeToggleButton />
      </div>
      <div className="login-card">
        <div className="login-header">
          <div className="avatar-bot-lg">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="10" rx="2" />
              <circle cx="12" cy="5" r="2" />
              <path d="M12 7v4" />
            </svg>
          </div>
          <h2 className="login-title">{t('login.title')}</h2>
          <p className="login-desc">{isRegister ? t('login.desc.register') : t('login.desc.login')}</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <UserOutlined className="login-icon" />
            <input
              type="text"
              placeholder={t('login.placeholder.username')}
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="login-input"
              autoFocus
              aria-label={t('login.placeholder.username')}
            />
          </div>
          <div className="login-field">
            <LockOutlined className="login-icon" />
            <input
              type="password"
              placeholder={t('login.placeholder.password')}
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="login-input"
              aria-label={t('login.placeholder.password')}
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? (isRegister ? t('login.btn.registerLoading') : t('login.btn.loginLoading')) : (isRegister ? t('login.btn.register') : t('login.btn.login'))}
          </button>
          <div className="login-switch">
            {isRegister ? t('login.switch.hasAccount') : t('login.switch.noAccount')}
            <button type="button" className="login-switch-btn" onClick={() => { setIsRegister(!isRegister); setError(''); }}>
              {isRegister ? t('login.switch.goLogin') : t('login.switch.goRegister')}
            </button>
          </div>
          <div className="login-hint">{t('login.hint')}</div>
        </form>
      </div>
    </div>
  );
}

// ── Metrics 面板 ─────────────────────────────────────

function MetricsPanel({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const [metrics, setMetrics] = useState<MetricEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);

  const loadMetrics = useCallback(async () => {
    try {
      const data = await fetchMetrics();
      setMetrics(data);
      setError('');
    } catch (e: any) {
      setError(e.message || t('metrics.error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadMetrics();
    if (!autoRefresh) return;
    const timer = setInterval(loadMetrics, 5000);
    return () => clearInterval(timer);
  }, [loadMetrics, autoRefresh]);

  // 从 metrics 中提取关键数据
  const getCounterValue = (name: string, labels?: Record<string, string>): number => {
    const m = metrics.find(m => m.name === name);
    if (!m) return 0;
    if (!labels) return m.samples.reduce((sum, s) => sum + s.value, 0);
    return m.samples
      .filter(s => Object.entries(labels).every(([k, v]) => s.labels[k] === v))
      .reduce((sum, s) => sum + s.value, 0);
  };

  const getToolCallSamples = () => {
    const m = metrics.find(m => m.name === 'agent_tool_calls_total');
    if (!m) return [];
    const grouped: Record<string, number> = {};
    for (const s of m.samples) {
      const name = s.labels['tool_name'] || 'unknown';
      grouped[name] = (grouped[name] || 0) + s.value;
    }
    return Object.entries(grouped).sort((a, b) => b[1] - a[1]);
  };

  const getNodeDurationSamples = () => {
    const m = metrics.find(m => m.name === 'agent_node_duration_ms_count');
    const mSum = metrics.find(m => m.name === 'agent_node_duration_ms_sum');
    if (!m || !mSum) return [];
    const result: { node: string; count: number; avgMs: number }[] = [];
    for (const s of m.samples) {
      const node = s.labels['node'] || 'unknown';
      const sumSample = mSum.samples.find(ss => ss.labels['node'] === node);
      const avg = sumSample && s.value > 0 ? Math.round(sumSample.value / s.value) : 0;
      result.push({ node, count: s.value, avgMs: avg });
    }
    return result.sort((a, b) => b.count - a.count);
  };

  const totalRequests = getCounterValue('agent_requests_total');
  const toolCalls = getToolCallSamples();
  const nodeDurations = getNodeDurationSamples();

  return (
    <div className="metrics-overlay">
      <div className="metrics-panel">
        <div className="metrics-header">
          <div className="metrics-header-left">
            <DashboardOutlined style={{ fontSize: 18 }} />
            <span className="metrics-title">{t('metrics.title')}</span>
          </div>
          <div className="metrics-header-right">
            <label className="metrics-toggle">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
              />
              <span>{t('metrics.autoRefresh')}</span>
            </label>
            <button className="metrics-refresh-btn" onClick={loadMetrics} title={t('metrics.manualRefresh')}>↻</button>
            <button className="metrics-close-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        {loading && <div className="metrics-loading">{t('metrics.loading')}</div>}
        {error && <div className="metrics-error">⚠ {error}</div>}

        {!loading && !error && (
          <div className="metrics-body chat-scroll">
            {/* 概览卡片 */}
            <div className="metrics-cards">
              <div className="metric-card">
                <div className="metric-card-value">{totalRequests}</div>
                <div className="metric-card-label">{t('metrics.totalRequests')}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-value">{toolCalls.reduce((s, [, v]) => s + v, 0)}</div>
                <div className="metric-card-label">{t('metrics.toolCalls')}</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-value">{nodeDurations.reduce((s, d) => s + d.count, 0)}</div>
                <div className="metric-card-label">{t('metrics.nodeExecutions')}</div>
              </div>
            </div>

            {/* 工具调用统计 */}
            {toolCalls.length > 0 && (
              <div className="metrics-section">
                <h3 className="metrics-section-title">{t('metrics.section.toolCalls')}</h3>
                <div className="metrics-table">
                  <div className="metrics-table-header">
                    <span>{t('metrics.table.toolName')}</span><span>{t('metrics.table.callCount')}</span>
                  </div>
                  {toolCalls.map(([name, count]) => (
                    <div key={name} className="metrics-table-row">
                      <span className="metrics-tool-name">{name}</span>
                      <span className="metrics-tool-count">{count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 节点耗时 */}
            {nodeDurations.length > 0 && (
              <div className="metrics-section">
                <h3 className="metrics-section-title">{t('metrics.section.nodeDuration')}</h3>
                <div className="metrics-table">
                  <div className="metrics-table-header">
                    <span>{t('metrics.table.node')}</span><span>{t('metrics.table.execCount')}</span><span>{t('metrics.table.avgDuration')}</span>
                  </div>
                  {nodeDurations.map(d => (
                    <div key={d.node} className="metrics-table-row metrics-table-row-3">
                      <span className="metrics-node-name">{d.node}</span>
                      <span>{d.count}</span>
                      <span className="metrics-duration">{d.avgMs}ms</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 原始指标 */}
            <div className="metrics-section">
              <h3 className="metrics-section-title">{t('metrics.section.allMetrics')}</h3>
              <div className="metrics-raw">
                {metrics.map(m => (
                  <div key={m.name} className="metrics-raw-item">
                    <div className="metrics-raw-name">{m.name} <Tag>{m.type}</Tag></div>
                    <div className="metrics-raw-help">{m.help}</div>
                    {m.samples.slice(0, 10).map((s, i) => (
                      <div key={i} className="metrics-raw-sample">
                        {Object.keys(s.labels).length > 0 && (
                          <span className="metrics-raw-labels">
                            {Object.entries(s.labels).map(([k, v]) => `${k}="${v}"`).join(', ')}
                          </span>
                        )}
                        <span className="metrics-raw-value">{s.value}</span>
                      </div>
                    ))}
                    {m.samples.length > 10 && (
                      <div className="metrics-raw-more">{t('metrics.raw.more', { count: String(m.samples.length - 10) })}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Agent 执行可视化面板 ─────────────────────────────

const nodeKeys: Record<string, string> = {
  supervisor: 'agent.node.supervisor',
  worker: 'agent.node.worker',
  reviewer: 'agent.node.reviewer',
  tool: 'agent.node.tool',
};

function AgentExecutionPanel({ events }: { events: AgentEvent[] }) {
  const [expanded, setExpanded] = useState(false);
  const { t } = useI18n();

  if (!events || events.length === 0) return null;

  // Build a timeline of completed steps from node_end and tool_call events
  const steps: { labelKey?: string; rawLabel?: string; detail?: string; durationMs?: number }[] = [];
  for (const evt of events) {
    if (evt.event === 'node_end' && evt.node) {
      steps.push({
        labelKey: nodeKeys[evt.node],
        rawLabel: evt.node,
        durationMs: evt.duration_ms,
      });
    } else if (evt.event === 'tool_call' && evt.tool) {
      steps.push({
        rawLabel: '🔧 ' + evt.tool,
        durationMs: evt.duration_ms,
      });
    }
  }

  if (steps.length === 0) return null;

  return (
    <div className="agent-exec-panel">
      <button
        className="agent-exec-toggle"
        onClick={() => setExpanded(prev => !prev)}
        aria-expanded={expanded}
        aria-label={t('agent.toggle.ariaLabel')}
      >
        <span className="agent-exec-toggle-icon">{expanded ? '▾' : '▸'}</span>
        <span className="agent-exec-toggle-text">{t('agent.steps', { count: String(steps.length) })}</span>
      </button>
      {expanded && (
        <div className="agent-exec-steps">
          {steps.map((step, i) => (
            <div key={i} className="agent-exec-step">
              <span className="agent-exec-step-dot" />
              <span className="agent-exec-step-label">{step.labelKey ? t(step.labelKey) : step.rawLabel}</span>
              {step.durationMs != null && (
                <span className="agent-exec-step-duration">{step.durationMs}ms</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 聊天主界面 ───────────────────────────────────────

function ChatPage({ user, onLogout }: { user: UserInfo; onLogout: () => void }) {
  const { t, locale, setLocale } = useI18n();
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const saved = loadSessionFromStorage();
    return saved ? saved.messages : [];
  });
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(() => {
    const saved = loadSessionFromStorage();
    return saved?.sessionId;
  });
  const [rated, setRated] = useState(false);
  const [showMetrics, setShowMetrics] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Search hook
  const searchableMessages: SearchableMessage[] = messages.map(m => ({
    id: m.id,
    role: m.role,
    content: m.content,
    timestamp: m.timestamp,
    metadata: m.metadata as Record<string, unknown> | undefined,
  }));
  const { filters, setFilters, results, filteredMessages, isSearching } = useMessageSearch(searchableMessages);

  // Build highlight map: messageId -> matchPositions
  const highlightMap = new Map<string, [number, number][]>();
  for (const r of results) {
    if (r.matchPositions.length > 0) {
      highlightMap.set(r.messageId, r.matchPositions);
    }
  }

  const scrollToBottom = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }), 50);
  }, []);

  useEffect(scrollToBottom, [messages, loading, scrollToBottom]);

  // Persist messages to localStorage on every update
  useEffect(() => {
    saveSessionToStorage(sessionId, messages);
  }, [messages, sessionId]);

  // Load session list
  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const list = await fetchSessions();
      setSessions(list);
    } catch { /* ignore */ }
    setSessionsLoading(false);
  }, []);

  useEffect(() => { loadSessions(); }, [loadSessions]);

  // Reload session list when a new session is created or messages change
  useEffect(() => {
    if (sessionId && messages.length > 0 && !loading) {
      loadSessions();
    }
  }, [sessionId, loading, loadSessions, messages.length]);

  const handleLoadSession = async (sid: string) => {
    if (sid === sessionId) return;
    try {
      const detail = await fetchSessionDetail(sid);
      if (!detail || !detail.messages) return;
      const loaded: ChatMessage[] = detail.messages
        .filter((m: any) => m.role === 'user' || m.role === 'assistant')
        .map((m: any) => ({
          id: m.id || crypto.randomUUID(),
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: (m.timestamp || 0) * 1000,
          status: 'sent' as const,
          metadata: m.metadata,
        }));
      setMessages(loaded);
      setSessionId(sid);
      setRated(!!detail.satisfaction);
      saveSessionToStorage(sid, loaded);
    } catch { /* ignore */ }
  };

  const doSend = async (text: string, retryMsgId?: string) => {
    if (!text || loading) return;

    let userMsg: ChatMessage;
    if (retryMsgId) {
      // Retry: update existing user message status to sending
      setMessages(prev => prev.map(m => m.id === retryMsgId ? { ...m, status: 'sending' } : m));
      userMsg = messages.find(m => m.id === retryMsgId)!;
    } else {
      userMsg = { id: crypto.randomUUID(), role: 'user', content: text, timestamp: Date.now(), status: 'sending' };
      setMessages(prev => [...prev, userMsg]);
    }

    setInput('');
    setLoading(true);

    const botId = retryMsgId
      ? (() => {
          // Find the bot message right after the retried user message and remove it
          const idx = messages.findIndex(m => m.id === retryMsgId);
          const nextBot = idx >= 0 && idx + 1 < messages.length && messages[idx + 1].role === 'assistant'
            ? messages[idx + 1].id : null;
          if (nextBot) {
            setMessages(prev => prev.filter(m => m.id !== nextBot));
          }
          return crypto.randomUUID();
        })()
      : crypto.randomUUID();

    const botMsg: ChatMessage = { id: botId, role: 'assistant', content: '', timestamp: Date.now(), status: 'sending' };
    setMessages(prev => [...prev, botMsg]);

    try {
      await sendMessageStream(
        text, sessionId,
        sid => { if (!sessionId) setSessionId(sid); },
        chunk => setMessages(prev => prev.map(m => m.id === botId ? { ...m, content: m.content + chunk } : m)),
        meta => setMessages(prev => prev.map(m => m.id === botId ? { ...m, metadata: meta } : m)),
        () => {
          setMessages(prev => prev.map(m => {
            if (m.id === (retryMsgId || userMsg.id)) return { ...m, status: 'sent' as const };
            if (m.id === botId) return { ...m, status: 'sent' as const };
            return m;
          }));
          setLoading(false);
        },
        evt => setMessages(prev => prev.map(m => m.id === botId ? { ...m, agentEvents: [...(m.agentEvents || []), evt] } : m)),
      );
    } catch {
      setMessages(prev => prev.map(m => {
        if (m.id === (retryMsgId || userMsg.id)) return { ...m, status: 'failed' as const };
        if (m.id === botId) return { ...m, content: t('chat.msg.serviceUnavailable'), status: 'failed' as const };
        return m;
      }));
      setLoading(false);
    } finally {
      inputRef.current?.focus();
    }
  };

  const handleSend = async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    await doSend(msg);
  };

  const handleRetry = (msgId: string) => {
    const msg = messages.find(m => m.id === msgId);
    if (!msg || msg.role !== 'user' || loading) return;
    doSend(msg.content, msgId);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleRate = async (value: number) => {
    if (!sessionId || rated) return;
    await rateSession(sessionId, value);
    setRated(true);
  };

  const handleReset = () => {
    setMessages([]); setSessionId(undefined); setRated(false);
    clearSessionStorage();
    loadSessions();
  };

  const showRating = !loading && !rated && sessionId && messages.filter(m => m.role === 'user').length >= 2;

  // Highlight helper: wraps matched text segments with <mark> tags
  const renderHighlightedText = (text: string, positions: [number, number][]) => {
    if (!positions || positions.length === 0) return text;
    const parts: React.ReactNode[] = [];
    let lastIdx = 0;
    for (const [start, end] of positions) {
      if (start > lastIdx) {
        parts.push(text.slice(lastIdx, start));
      }
      parts.push(<mark key={`${start}-${end}`} className="search-highlight">{text.slice(start, end)}</mark>);
      lastIdx = end;
    }
    if (lastIdx < text.length) {
      parts.push(text.slice(lastIdx));
    }
    return <>{parts}</>;
  };

  // Helper: format session time for grouping
  const getSessionGroup = (ts: number): string => {
    const now = new Date();
    const d = new Date(ts * 1000);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 86400000);
    if (d >= today) return t('sidebar.today');
    if (d >= yesterday) return t('sidebar.yesterday');
    return t('sidebar.earlier');
  };

  // Helper: get preview text from session
  const getSessionPreview = (s: SessionSummary): string => {
    const userMsg = s.messages?.find((m: any) => m.role === 'user');
    if (userMsg) return userMsg.content.slice(0, 40) + (userMsg.content.length > 40 ? '...' : '');
    return '...';
  };

  // Group sessions by date
  const groupedSessions = sessions.reduce<Record<string, SessionSummary[]>>((acc, s) => {
    const group = getSessionGroup(s.updated_at);
    (acc[group] = acc[group] || []).push(s);
    return acc;
  }, {});

  return (
    <>
      <div className="app-bg">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />
        <div className="bg-orb bg-orb-3" />

        <div className="chat-layout">
          {/* Sidebar */}
          <div className={`chat-sidebar ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
            <div className="sidebar-header">
              <span className="sidebar-title">{t('sidebar.title')}</span>
              <button className="sidebar-new-btn" onClick={handleReset} aria-label={t('sidebar.newChat')}>
                <PlusOutlined />
              </button>
            </div>
            <div className="sidebar-list chat-scroll">
              {sessionsLoading && sessions.length === 0 ? (
                <div className="sidebar-empty">{t('sidebar.loading')}</div>
              ) : sessions.length === 0 ? (
                <div className="sidebar-empty">{t('sidebar.empty')}</div>
              ) : (
                Object.entries(groupedSessions).map(([group, items]) => (
                  <div key={group} className="sidebar-group">
                    <div className="sidebar-group-label">{group}</div>
                    {items.map(s => (
                      <button
                        key={s.id}
                        className={`sidebar-item ${s.id === sessionId ? 'sidebar-item-active' : ''}`}
                        onClick={() => handleLoadSession(s.id)}
                      >
                        <MessageOutlined className="sidebar-item-icon" />
                        <div className="sidebar-item-content">
                          <div className="sidebar-item-preview">{getSessionPreview(s)}</div>
                          <div className="sidebar-item-meta">
                            {t('sidebar.msgCount', { count: String(s.messages?.length || 0) })}
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="chat-container">
          {/* Header */}
          <div className="chat-header">
            <div className="header-left">
              <div className="avatar-bot-lg">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="10" rx="2" />
                  <circle cx="12" cy="5" r="2" />
                  <path d="M12 7v4" />
                  <line x1="8" y1="16" x2="8" y2="16" />
                  <line x1="16" y1="16" x2="16" y2="16" />
                </svg>
              </div>
              <div>
                <div className="header-title">{t('chat.header.title')}</div>
                <div className="header-status">
                  <span className="status-dot" />
                  <span>{t('chat.header.online', { username: user.username })}</span>
                </div>
              </div>
            </div>
            <div className="header-actions">
              <button
                className="header-btn"
                onClick={() => setSidebarOpen(v => !v)}
                aria-label="Toggle sidebar"
              >
                <MenuOutlined />
              </button>
              <ThemeToggleButton />
              <button
                className="header-btn"
                onClick={() => setLocale(locale === 'zh-CN' ? 'en-US' : 'zh-CN')}
                aria-label="Switch language"
                style={{ fontSize: 13, fontWeight: 600 }}
              >
                {locale === 'zh-CN' ? 'EN' : '中'}
              </button>
              <Tooltip title={t('search.tooltip')} placement="bottom">
                <button
                  className={`header-btn ${showSearch ? 'header-btn-active' : ''}`}
                  onClick={() => {
                    setShowSearch(v => !v);
                    if (showSearch) {
                      setFilters({ keyword: '', role: 'all' });
                    }
                  }}
                  aria-label={t('search.tooltip')}
                >
                  <SearchOutlined />
                </button>
              </Tooltip>
              <Dropdown
                menu={{
                  items: [
                    { key: 'pdf', icon: <FilePdfOutlined />, label: t('export.pdf') },
                    { key: 'json', icon: <FileTextOutlined />, label: t('export.json') },
                  ],
                  onClick: ({ key }) => {
                    const format = key as 'pdf' | 'json';
                    const options: ExportOptions = {
                      format,
                      includeMetadata: true,
                      includeAgentEvents: true,
                    };
                    if (format === 'json') {
                      const json = exportToJSON(messages, sessionId, options, locale);
                      downloadBlob(
                        new Blob([json], { type: 'application/json' }),
                        `chat-${sessionId?.slice(0, 8) ?? 'export'}.json`,
                      );
                    } else {
                      exportToPDF(messages, sessionId, options);
                    }
                  },
                }}
                disabled={messages.length === 0}
                trigger={['click']}
              >
                <Tooltip title={t('export.button')} placement="bottom">
                  <button className="header-btn" disabled={messages.length === 0} aria-label={t('export.button')}>
                    <DownloadOutlined />
                  </button>
                </Tooltip>
              </Dropdown>
              {user.role === 'admin' && (
                <Tooltip title={t('chat.header.tooltip.metrics')} placement="bottom">
                  <button className="header-btn" onClick={() => setShowMetrics(true)} aria-label={t('chat.header.tooltip.metrics')}>
                    <DashboardOutlined />
                  </button>
                </Tooltip>
              )}
              <Tooltip title={t('chat.header.tooltip.reset')} placement="bottom">
                <button className="header-btn" onClick={handleReset} aria-label={t('chat.header.tooltip.reset')}>
                  <ReloadOutlined />
                </button>
              </Tooltip>
              <Tooltip title={t('chat.header.tooltip.logout')} placement="bottomRight">
                <button className="header-btn" onClick={onLogout} aria-label={t('chat.header.tooltip.logout')}>
                  <LogoutOutlined />
                </button>
              </Tooltip>
            </div>
          </div>

          {/* Search Bar */}
          {showSearch && (
            <div className="search-bar">
              <div className="search-bar-inner">
                <SearchOutlined className="search-bar-icon" />
                <input
                  type="text"
                  className="search-input"
                  placeholder={t('search.placeholder')}
                  value={filters.keyword}
                  onChange={e => setFilters({ keyword: e.target.value })}
                  autoFocus
                  aria-label={t('search.placeholder')}
                />
                <select
                  className="search-role-select"
                  value={filters.role || 'all'}
                  onChange={e => setFilters({ role: e.target.value as 'user' | 'assistant' | 'all' })}
                  aria-label="Role filter"
                >
                  <option value="all">{t('search.roleFilter.all')}</option>
                  <option value="user">{t('search.roleFilter.user')}</option>
                  <option value="assistant">{t('search.roleFilter.assistant')}</option>
                </select>
                <span className="search-count">
                  {isSearching
                    ? (filteredMessages.length > 0
                        ? t('search.resultCount', { count: String(filteredMessages.length) })
                        : t('search.noResults'))
                    : ''}
                </span>
                <button
                  className="search-close-btn"
                  onClick={() => {
                    setShowSearch(false);
                    setFilters({ keyword: '', role: 'all' });
                  }}
                  aria-label={t('search.close')}
                >
                  <CloseOutlined />
                </button>
              </div>
            </div>
          )}

          {/* Messages */}
          <div ref={scrollRef} className="chat-messages chat-scroll">
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-avatar">
                  <span className="welcome-emoji">🤖</span>
                </div>
                <h2 className="welcome-title">{t('chat.welcome.title', { username: user.username })}</h2>
                <p className="welcome-desc">{t('chat.welcome.desc')}</p>
                <div className="quick-grid">
                  {quickReplyKeys.map(q => {
                    const text = t(q.key);
                    return (
                      <button key={q.key} className="quick-btn" onClick={() => handleSend(text)}>
                        <span className="quick-icon">{q.icon}</span>
                        <span className="quick-text">{text}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="msg-list">
                {(isSearching ? messages.filter(m => filteredMessages.some(fm => fm.id === m.id)) : messages).map(msg => {
                  if (msg.role === 'assistant' && !msg.content) return null;
                  const isUser = msg.role === 'user';

                  const botIcon = (
                    <div className="avatar-bot-sm">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="10" rx="2" />
                        <circle cx="12" cy="5" r="2" />
                        <path d="M12 7v4" />
                      </svg>
                    </div>
                  );

                  const userIcon = (
                    <div className="avatar-user-sm">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                        <circle cx="12" cy="7" r="4" />
                      </svg>
                    </div>
                  );

                  return (
                    <div key={msg.id} className={`msg-row ${isUser ? 'msg-row-user' : 'msg-row-bot'}`}>
                      {!isUser && botIcon}
                      <div className={`msg-col ${isUser ? 'msg-col-user' : ''}`}>
                        <div className={`msg-content ${isUser ? 'msg-user' : 'msg-bot'} ${msg.status === 'failed' ? 'msg-failed' : ''}`}>
                          {!isUser ? (
                            highlightMap.has(msg.id)
                              ? <div className="md-content">{renderHighlightedText(msg.content, highlightMap.get(msg.id)!)}</div>
                              : <ReactMarkdown className="md-content">{msg.content}</ReactMarkdown>
                          ) : (
                            highlightMap.has(msg.id)
                              ? renderHighlightedText(msg.content, highlightMap.get(msg.id)!)
                              : msg.content
                          )}
                        </div>
                        {isUser && msg.status === 'failed' && (
                          <div className="msg-fail-row">
                            <ExclamationCircleOutlined className="msg-fail-icon" />
                            <span className="msg-fail-text">{t('chat.msg.sendFailed')}</span>
                            <button
                              className="msg-retry-btn"
                              onClick={() => handleRetry(msg.id)}
                              disabled={loading}
                              aria-label={t('chat.msg.retry')}
                            >
                              <ReloadOutlined /> {t('chat.msg.retry')}
                            </button>
                          </div>
                        )}
                        {!isUser && msg.metadata && (
                          <div className="msg-meta">
                            {msg.metadata.sentiment && sentimentKeys[msg.metadata.sentiment] && (
                              <Tag color={sentimentKeys[msg.metadata.sentiment].color}>
                                {t(sentimentKeys[msg.metadata.sentiment].key)}
                              </Tag>
                            )}
                            {msg.metadata.intent && intentKeys[msg.metadata.intent] && (
                              <Tag>{t(intentKeys[msg.metadata.intent])}</Tag>
                            )}
                            {msg.metadata.toolsUsed && msg.metadata.toolsUsed.length > 0 && (
                              <Tag icon={<ToolOutlined />} color="purple">
                                {msg.metadata.toolsUsed.join(', ')}
                              </Tag>
                            )}
                            {msg.metadata.responseTimeMs && (
                              <Tag icon={<ClockCircleOutlined />}>
                                {msg.metadata.responseTimeMs}ms
                              </Tag>
                            )}
                          </div>
                        )}
                        {!isUser && msg.agentEvents && msg.agentEvents.length > 0 && (
                          <AgentExecutionPanel events={msg.agentEvents} />
                        )}
                      </div>
                      {isUser && userIcon}
                    </div>
                  );
                })}

                {loading && (messages.length === 0 || messages[messages.length - 1].content === '') && (
                  <div className="msg-row msg-row-bot">
                    <div className="avatar-bot-sm">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="3" y="11" width="18" height="10" rx="2" />
                        <circle cx="12" cy="5" r="2" />
                        <path d="M12 7v4" />
                      </svg>
                    </div>
                    <div className="msg-bot typing-bubble">
                      <span className="typing-dot" /><span className="typing-dot" /><span className="typing-dot" />
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Rating */}
          {showRating && (
            <div className="rating-bar">
              <span>{t('chat.rating.ask')}</span>
              <Rate allowHalf={false} onChange={handleRate} style={{ fontSize: 15 }} />
            </div>
          )}
          {rated && (
            <div className="rating-bar rated">{t('chat.rating.thanks')}</div>
          )}

          {/* Input */}
          <div className="chat-input-area">
            <div className="input-wrapper">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('chat.input.placeholder')}
                rows={1}
                className="chat-textarea"
                aria-label="消息输入框"
              />
              <button
                className={`send-btn ${(!input.trim() || loading) ? 'send-btn-disabled' : ''}`}
                onClick={() => handleSend()}
                disabled={!input.trim() || loading}
                aria-label="发送消息"
              >
                <SendOutlined />
              </button>
            </div>
            <div className="input-footer">
              <span>{t('chat.input.hint')}</span>
              {sessionId && <span>ID: {sessionId.slice(0, 8)}</span>}
            </div>
          </div>
        </div>
        {/* end chat-container */}
        </div>
        {/* end chat-layout */}
      </div>

      {showMetrics && <MetricsPanel onClose={() => setShowMetrics(false)} />}
    </>
  );
}

// ── 根组件（内层，消费 ThemeContext）────────────────────

function AppInner() {
  const { resolvedTheme } = useTheme();
  const { antdLocale } = useI18n();

  const [user, setUser] = useState<UserInfo | null>(() => {
    try {
      const saved = localStorage.getItem('xiaozhi_user');
      const token = getToken();
      if (saved && token) return JSON.parse(saved);
      if (saved && !token) localStorage.removeItem('xiaozhi_user');
      return null;
    } catch {
      return null;
    }
  });

  const handleLogout = () => {
    clearAuth();
    setUser(null);
  };

  return (
    <ConfigProvider
      locale={antdLocale}
      theme={{
        algorithm: resolvedTheme === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: { colorPrimary: '#6366f1', borderRadius: 10 },
      }}
    >
      {user ? (
        <ChatPage user={user} onLogout={handleLogout} />
      ) : (
        <LoginPage onLogin={setUser} />
      )}
    </ConfigProvider>
  );
}

// ── 根组件 ───────────────────────────────────────────

export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <AppInner />
      </I18nProvider>
    </ThemeProvider>
  );
}
