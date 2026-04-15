import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendMessageStream, rateSession, ChatMetadata } from './api';
import ReactMarkdown from 'react-markdown';
import { Tag, Rate, Tooltip, ConfigProvider } from 'antd';
import {
  SendOutlined, ReloadOutlined, ClockCircleOutlined, ToolOutlined,
} from '@ant-design/icons';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  metadata?: ChatMetadata;
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

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [rated, setRated] = useState(false);
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
    <ConfigProvider theme={{ token: { colorPrimary: '#6366f1', borderRadius: 10 } }}>
      <div className="app-bg">
        {/* 背景装饰 */}
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
                  <span>在线 · 通常秒回</span>
                </div>
              </div>
            </div>
            <Tooltip title="开始新对话" placement="bottomRight">
              <button className="header-btn" onClick={handleReset} aria-label="新对话">
                <ReloadOutlined />
              </button>
            </Tooltip>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="chat-messages chat-scroll">
            {messages.length === 0 ? (
              <div className="welcome">
                <div className="welcome-avatar">
                  <span className="welcome-emoji">🤖</span>
                </div>
                <h2 className="welcome-title">你好，我是小智</h2>
                <p className="welcome-desc">你的 AI 智能客服助手，有什么可以帮你的？</p>
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

                {/* Typing */}
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
    </ConfigProvider>
  );
}
