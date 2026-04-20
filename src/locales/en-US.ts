/**
 * English (US) translation resource.
 */
const enUS: Record<string, string> = {
  // ── Login Page ──
  'login.title': 'XiaoZhi AI Support',
  'login.desc.login': 'Sign in to start chatting',
  'login.desc.register': 'Create a new account',
  'login.placeholder.username': 'Username',
  'login.placeholder.password': 'Password',
  'login.error.empty': 'Please enter username and password',
  'login.error.passwordShort': 'Password must be at least 3 characters',
  'login.error.loginFailed': 'Login failed',
  'login.error.registerFailed': 'Registration failed',
  'login.btn.login': 'Sign In',
  'login.btn.register': 'Sign Up',
  'login.btn.loginLoading': 'Signing in...',
  'login.btn.registerLoading': 'Signing up...',
  'login.switch.hasAccount': 'Already have an account?',
  'login.switch.noAccount': "Don't have an account?",
  'login.switch.goLogin': 'Sign in',
  'login.switch.goRegister': 'Create account',
  'login.hint': 'Admin: admin / admin',

  // ── Chat Page - Header ──
  'chat.header.title': 'XiaoZhi AI Support',
  'chat.header.online': 'Online · {username}',
  'chat.header.tooltip.theme': 'Toggle theme',
  'chat.header.tooltip.metrics': 'System metrics',
  'chat.header.tooltip.reset': 'New conversation',
  'chat.header.tooltip.logout': 'Sign out',

  // ── Chat Page - Welcome ──
  'chat.welcome.title': 'Hello, {username}',
  'chat.welcome.desc': "I'm XiaoZhi, your AI support assistant. How can I help you?",

  // ── Chat Page - Quick Replies ──
  'chat.quick.orderQuery': 'Check order ORD-20240101',
  'chat.quick.refundPolicy': 'What is the refund policy?',
  'chat.quick.memberBenefits': 'What are the membership benefits?',
  'chat.quick.humanAgent': 'Transfer to a human agent',
  'chat.quick.paymentMethods': 'What payment methods?',

  // ── Chat Page - Messages ──
  'chat.msg.sendFailed': 'Failed to send',
  'chat.msg.retry': 'Retry',
  'chat.msg.serviceUnavailable': 'Sorry, the service is temporarily unavailable. Please try again later.',

  // ── Chat Page - Rating ──
  'chat.rating.ask': 'How was your experience?',
  'chat.rating.thanks': 'Thanks for your feedback ✨',

  // ── Chat Page - Input ──
  'chat.input.placeholder': 'Type your question...',
  'chat.input.hint': 'Enter to send · Shift+Enter for new line',

  // ── Theme Toggle ──
  'theme.light': 'Light mode',
  'theme.dark': 'Dark mode',
  'theme.system': 'System',
  'theme.toggle.ariaLabel': 'Toggle theme',

  // ── Metrics Panel ──
  'metrics.title': 'System Metrics',
  'metrics.autoRefresh': 'Auto refresh',
  'metrics.manualRefresh': 'Manual refresh',
  'metrics.loading': 'Loading...',
  'metrics.error': 'Failed to load',
  'metrics.totalRequests': 'Total Requests',
  'metrics.toolCalls': 'Tool Calls',
  'metrics.nodeExecutions': 'Node Executions',
  'metrics.section.toolCalls': '🔧 Tool Call Statistics',
  'metrics.table.toolName': 'Tool Name',
  'metrics.table.callCount': 'Call Count',
  'metrics.section.nodeDuration': '⏱ Node Duration',
  'metrics.table.node': 'Node',
  'metrics.table.execCount': 'Exec Count',
  'metrics.table.avgDuration': 'Avg Duration',
  'metrics.section.allMetrics': '📊 All Metrics',
  'metrics.raw.more': '... {count} more',

  // ── Agent Execution Panel ──
  'agent.toggle.ariaLabel': 'Toggle execution details',
  'agent.steps': 'Execution · {count} steps',
  'agent.node.supervisor': '🧭 Routing',
  'agent.node.worker': '⚙️ Task Execution',
  'agent.node.reviewer': '✅ Quality Review',
  'agent.node.tool': '🔧 Tool Call',

  // ── Sentiment Labels ──
  'sentiment.positive': '😊 Positive',
  'sentiment.neutral': '😐 Neutral',
  'sentiment.negative': '😠 Negative',
  'sentiment.frustrated': '😤 Frustrated',
  'sentiment.confused': '😕 Confused',

  // ── Intent Labels ──
  'intent.product_inquiry': '📦 Product Inquiry',
  'intent.order_status': '🚚 Order Status',
  'intent.refund_request': '💰 Refund Request',
  'intent.technical_support': '🔧 Technical Support',
  'intent.complaint': '📢 Complaint',
  'intent.general_chat': '💬 General Chat',
  'intent.human_handoff': '👤 Human Handoff',
  'intent.feedback': '📝 Feedback',

  // ── Search ──
  'search.placeholder': 'Search messages...',
  'search.roleFilter.all': 'All',
  'search.roleFilter.user': 'User',
  'search.roleFilter.assistant': 'Assistant',
  'search.resultCount': '{count} results found',
  'search.noResults': 'No results',
  'search.tooltip': 'Search messages',
  'search.close': 'Close search',

  // ── Export ──
  'export.button': 'Export',
  'export.pdf': 'Export as PDF',
  'export.json': 'Export as JSON',

  // ── Sidebar ──
  'sidebar.title': 'Conversations',
  'sidebar.empty': 'No conversations yet',
  'sidebar.newChat': 'New Chat',
  'sidebar.loading': 'Loading...',
  'sidebar.msgCount': '{count} messages',
  'sidebar.today': 'Today',
  'sidebar.yesterday': 'Yesterday',
  'sidebar.earlier': 'Earlier',
};

export default enUS;
