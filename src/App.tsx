import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendMessageStream, rateSession, fetchMetrics, loginApi, registerApi, setToken, clearAuth, getToken, ChatMetadata, MetricEntry } from './api';
import ReactMarkdown from 'react-markdown';
import { Tag, Rate, Tooltip, ConfigProvider } from 'antd';
import {
  SendOutlined, ReloadOutlined, ClockCircleOutlined, ToolOutlined,
  DashboardOutlined, LogoutOutlined, UserOutlined, LockOutlined,
} from '@ant-design/icons';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: ChatMetadata;
}

interface UserInfo {
  username: string;
  role: 'user' | 'admin';
}

const quickReplies = [
  { icon: '📦', text: '查询订单 ORD-20240101' },
  { icon: '💰', text: '退款政策是什么？' },
  { icon: '👑', text: '会员有什么权益？' },
  { icon: '👤', text: '帮我转人工客服' },
  { icon: '🌐', text: 'What payment methods?' },
];

const sentimentMap: Record<string, { color: string; label: string }> = {
  positive: { color: 'green', label: '😊 积极' },
  neutral: { color: 'default', label: '😐 中性' },
  negative: { color: 'red', label: '😠 消极' },
  frustrated: { color: 'orange', label: '😤 焦躁' },
  confused: { color: 'gold', label: '😕 困惑' },
};

const intentMap: Record<string, string> = {
  product_inquiry: '📦 产品咨询', order_status: '🚚 订单查询',
  refund_request: '💰 退款申请', technical_support: '🔧 技术支持',
  complaint: '📢 投诉', general_chat: '💬 闲聊',
  human_handoff: '👤 转人工', feedback: '📝 反馈',
};

// ── 登录页面 ─────────────────────────────────────────

function LoginPage({ onLogin }: { onLogin: (user: UserInfo) => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isRegister, setIsRegister] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('请输入用户名和密码');
      return;
    }
    if (password.length < 3) {
      setError('密码长度至少 3 位');
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
      setError(err.message || (isRegister ? '注册失败' : '登录失败'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-bg">
      <div className="bg-orb bg-orb-1" />
      <div className="bg-orb bg-orb-2" />
      <div className="bg-orb bg-orb-3" />
      <div className="login-card">
        <div className="login-header">
          <div className="avatar-bot-lg">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="10" rx="2" />
              <circle cx="12" cy="5" r="2" />
              <path d="M12 7v4" />
            </svg>
          </div>
          <h2 className="login-title">小智 AI 客服</h2>
          <p className="login-desc">{isRegister ? '创建新账号' : '登录后开始对话'}</p>
        </div>
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-field">
            <UserOutlined className="login-icon" />
            <input
              type="text"
              placeholder="用户名"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="login-input"
              autoFocus
              aria-label="用户名"
            />
          </div>
          <div className="login-field">
            <LockOutlined className="login-icon" />
            <input
              type="password"
              placeholder="密码"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="login-input"
              aria-label="密码"
            />
          </div>
          {error && <div className="login-error">{error}</div>}
          <button type="submit" className="login-btn" disabled={loading}>
            {loading ? (isRegister ? '注册中...' : '登录中...') : (isRegister ? '注 册' : '登 录')}
          </button>
          <div className="login-switch">
            {isRegister ? '已有账号？' : '没有账号？'}
            <button type="button" className="login-switch-btn" onClick={() => { setIsRegister(!isRegister); setError(''); }}>
              {isRegister ? '去登录' : '注册新账号'}
            </button>
          </div>
          <div className="login-hint">管理员: admin / admin</div>
        </form>
      </div>
    </div>
  );
}

// ── Metrics 面板 ─────────────────────────────────────

function MetricsPanel({ onClose }: { onClose: () => void }) {
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
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

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
            <span className="metrics-title">系统监控</span>
          </div>
          <div className="metrics-header-right">
            <label className="metrics-toggle">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={e => setAutoRefresh(e.target.checked)}
              />
              <span>自动刷新</span>
            </label>
            <button className="metrics-refresh-btn" onClick={loadMetrics} title="手动刷新">↻</button>
            <button className="metrics-close-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        {loading && <div className="metrics-loading">加载中...</div>}
        {error && <div className="metrics-error">⚠ {error}</div>}

        {!loading && !error && (
          <div className="metrics-body chat-scroll">
            {/* 概览卡片 */}
            <div className="metrics-cards">
              <div className="metric-card">
                <div className="metric-card-value">{totalRequests}</div>
                <div className="metric-card-label">总请求数</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-value">{toolCalls.reduce((s, [, v]) => s + v, 0)}</div>
                <div className="metric-card-label">工具调用</div>
              </div>
              <div className="metric-card">
                <div className="metric-card-value">{nodeDurations.reduce((s, d) => s + d.count, 0)}</div>
                <div className="metric-card-label">节点执行</div>
              </div>
            </div>

            {/* 工具调用统计 */}
            {toolCalls.length > 0 && (
              <div className="metrics-section">
                <h3 className="metrics-section-title">🔧 工具调用统计</h3>
                <div className="metrics-table">
                  <div className="metrics-table-header">
                    <span>工具名称</span><span>调用次数</span>
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
                <h3 className="metrics-section-title">⏱ 节点耗时</h3>
                <div className="metrics-table">
                  <div className="metrics-table-header">
                    <span>节点</span><span>执行次数</span><span>平均耗时</span>
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
              <h3 className="metrics-section-title">📊 全部指标</h3>
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
                      <div className="metrics-raw-more">... 还有 {m.samples.length - 10} 条</div>
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

// ── 聊天主界面 ───────────────────────────────────────

function ChatPage({ user, onLogout }: { user: UserInfo; onLogout: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [rated, setRated] = useState(false);
  const [showMetrics, setShowMetrics] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' }), 50);
  }, []);

  useEffect(scrollToBottom, [messages, loading, scrollToBottom]);

  const handleSend = async (text?: string) => {
    const msg = text || input.trim();
    if (!msg || loading) return;

    const userMsg: ChatMessage = { id: crypto.randomUUID(), role: 'user', content: msg, timestamp: Date.now() };
    const botId = crypto.randomUUID();
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    const botMsg: ChatMessage = { id: botId, role: 'assistant', content: '', timestamp: Date.now() };
    setMessages(prev => [...prev, botMsg]);

    try {
      await sendMessageStream(
        msg, sessionId,
        sid => { if (!sessionId) setSessionId(sid); },
        chunk => setMessages(prev => prev.map(m => m.id === botId ? { ...m, content: m.content + chunk } : m)),
        meta => setMessages(prev => prev.map(m => m.id === botId ? { ...m, metadata: meta } : m)),
        () => setLoading(false),
      );
    } catch {
      setMessages(prev => prev.map(m => m.id === botId ? { ...m, content: '抱歉，服务暂时不可用，请稍后再试。' } : m));
      setLoading(false);
    } finally {
      inputRef.current?.focus();
    }
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
  };

  const showRating = !loading && !rated && sessionId && messages.filter(m => m.role === 'user').length >= 2;

  return (
    <>
      <div className="app-bg">
        <div className="bg-orb bg-orb-1" />
        <div className="bg-orb bg-orb-2" />
        <div className="bg-orb bg-orb-3" />

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
                <div className="header-title">小智 AI 客服</div>
                <div className="header-status">
                  <span className="status-dot" />
                  <span>在线 · {user.username}</span>
                </div>
              </div>
            </div>
            <div className="header-actions">
              {user.role === 'admin' && (
                <Tooltip title="系统监控" placement="bottom">
                  <button className="header-btn" onClick={() => setShowMetrics(true)} aria-label="监控面板">
                    <DashboardOutlined />
                  </button>
                </Tooltip>
              )}
              <Tooltip title="开始新对话" placement="bottom">
                <button className="header-btn" onClick={handleReset} aria-label="新对话">
                  <ReloadOutlined />
                </button>
              </Tooltip>
              <Tooltip title="退出登录" placement="bottomRight">
                <button className="header-btn" onClick={onLogout} aria-label="退出">
                  <LogoutOutlined />
                </button>
              </Tooltip>
            </div>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="chat-messages chat-scroll">
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-avatar">
                  <span className="welcome-emoji">🤖</span>
                </div>
                <h2 className="welcome-title">你好，{user.username}</h2>
                <p className="welcome-desc">我是小智，你的 AI 智能客服助手，有什么可以帮你的？</p>
                <div className="quick-grid">
                  {quickReplies.map(q => (
                    <button key={q.text} className="quick-btn" onClick={() => handleSend(q.text)}>
                      <span className="quick-icon">{q.icon}</span>
                      <span className="quick-text">{q.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="msg-list">
                {messages.map(msg => {
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
                        <div className={`msg-content ${isUser ? 'msg-user' : 'msg-bot'}`}>
                          {!isUser ? (
                            <ReactMarkdown className="md-content">{msg.content}</ReactMarkdown>
                          ) : msg.content}
                        </div>
                        {!isUser && msg.metadata && (
                          <div className="msg-meta">
                            {msg.metadata.sentiment && sentimentMap[msg.metadata.sentiment] && (
                              <Tag color={sentimentMap[msg.metadata.sentiment].color}>
                                {sentimentMap[msg.metadata.sentiment].label}
                              </Tag>
                            )}
                            {msg.metadata.intent && intentMap[msg.metadata.intent] && (
                              <Tag>{intentMap[msg.metadata.intent]}</Tag>
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
              <span>对本次服务满意吗？</span>
              <Rate allowHalf={false} onChange={handleRate} style={{ fontSize: 15 }} />
            </div>
          )}
          {rated && (
            <div className="rating-bar rated">感谢您的评价 ✨</div>
          )}

          {/* Input */}
          <div className="chat-input-area">
            <div className="input-wrapper">
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入您的问题..."
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
              <span>Enter 发送 · Shift+Enter 换行</span>
              {sessionId && <span>ID: {sessionId.slice(0, 8)}</span>}
            </div>
          </div>
        </div>
      </div>

      {showMetrics && <MetricsPanel onClose={() => setShowMetrics(false)} />}
    </>
  );
}

// ── 根组件 ───────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState<UserInfo | null>(() => {
    try {
      const saved = localStorage.getItem('xiaozhi_user');
      const token = getToken();
      if (saved && token) return JSON.parse(saved);
      // 有用户信息但没 token，清除无效状态
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
    <ConfigProvider theme={{ token: { colorPrimary: '#6366f1', borderRadius: 10 } }}>
      {user ? (
        <ChatPage user={user} onLogout={handleLogout} />
      ) : (
        <LoginPage onLogin={setUser} />
      )}
    </ConfigProvider>
  );
}
