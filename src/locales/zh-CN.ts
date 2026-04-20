/**
 * Chinese (Simplified) translation resource.
 */
const zhCN: Record<string, string> = {
  // ── Login Page ──
  'login.title': '小智 AI 客服',
  'login.desc.login': '登录后开始对话',
  'login.desc.register': '创建新账号',
  'login.placeholder.username': '用户名',
  'login.placeholder.password': '密码',
  'login.error.empty': '请输入用户名和密码',
  'login.error.passwordShort': '密码长度至少 3 位',
  'login.error.loginFailed': '登录失败',
  'login.error.registerFailed': '注册失败',
  'login.btn.login': '登 录',
  'login.btn.register': '注 册',
  'login.btn.loginLoading': '登录中...',
  'login.btn.registerLoading': '注册中...',
  'login.switch.hasAccount': '已有账号？',
  'login.switch.noAccount': '没有账号？',
  'login.switch.goLogin': '去登录',
  'login.switch.goRegister': '注册新账号',
  'login.hint': '管理员: admin / admin',

  // ── Chat Page - Header ──
  'chat.header.title': '小智 AI 客服',
  'chat.header.online': '在线 · {username}',
  'chat.header.tooltip.theme': '切换主题',
  'chat.header.tooltip.metrics': '系统监控',
  'chat.header.tooltip.reset': '开始新对话',
  'chat.header.tooltip.logout': '退出登录',

  // ── Chat Page - Welcome ──
  'chat.welcome.title': '你好，{username}',
  'chat.welcome.desc': '我是小智，你的 AI 智能客服助手，有什么可以帮你的？',

  // ── Chat Page - Quick Replies ──
  'chat.quick.orderQuery': '查询订单 ORD-20240101',
  'chat.quick.refundPolicy': '退款政策是什么？',
  'chat.quick.memberBenefits': '会员有什么权益？',
  'chat.quick.humanAgent': '帮我转人工客服',
  'chat.quick.paymentMethods': 'What payment methods?',

  // ── Chat Page - Messages ──
  'chat.msg.sendFailed': '发送失败',
  'chat.msg.retry': '重发',
  'chat.msg.serviceUnavailable': '抱歉，服务暂时不可用，请稍后再试。',

  // ── Chat Page - Rating ──
  'chat.rating.ask': '对本次服务满意吗？',
  'chat.rating.thanks': '感谢您的评价 ✨',

  // ── Chat Page - Input ──
  'chat.input.placeholder': '输入您的问题...',
  'chat.input.hint': 'Enter 发送 · Shift+Enter 换行',

  // ── Theme Toggle ──
  'theme.light': '亮色模式',
  'theme.dark': '暗色模式',
  'theme.system': '跟随系统',
  'theme.toggle.ariaLabel': '切换主题',

  // ── Metrics Panel ──
  'metrics.title': '系统监控',
  'metrics.autoRefresh': '自动刷新',
  'metrics.manualRefresh': '手动刷新',
  'metrics.loading': '加载中...',
  'metrics.error': '加载失败',
  'metrics.totalRequests': '总请求数',
  'metrics.toolCalls': '工具调用',
  'metrics.nodeExecutions': '节点执行',
  'metrics.section.toolCalls': '🔧 工具调用统计',
  'metrics.table.toolName': '工具名称',
  'metrics.table.callCount': '调用次数',
  'metrics.section.nodeDuration': '⏱ 节点耗时',
  'metrics.table.node': '节点',
  'metrics.table.execCount': '执行次数',
  'metrics.table.avgDuration': '平均耗时',
  'metrics.section.allMetrics': '📊 全部指标',
  'metrics.raw.more': '... 还有 {count} 条',

  // ── Agent Execution Panel ──
  'agent.toggle.ariaLabel': '展开/折叠执行详情',
  'agent.steps': '执行过程 · {count} 步',
  'agent.node.supervisor': '🧭 路由决策',
  'agent.node.worker': '⚙️ 任务执行',
  'agent.node.reviewer': '✅ 质量审核',
  'agent.node.tool': '🔧 工具调用',

  // ── Sentiment Labels ──
  'sentiment.positive': '😊 积极',
  'sentiment.neutral': '😐 中性',
  'sentiment.negative': '😠 消极',
  'sentiment.frustrated': '😤 焦躁',
  'sentiment.confused': '😕 困惑',

  // ── Intent Labels ──
  'intent.product_inquiry': '📦 产品咨询',
  'intent.order_status': '🚚 订单查询',
  'intent.refund_request': '💰 退款申请',
  'intent.technical_support': '🔧 技术支持',
  'intent.complaint': '📢 投诉',
  'intent.general_chat': '💬 闲聊',
  'intent.human_handoff': '👤 转人工',
  'intent.feedback': '📝 反馈',

  // ── Search ──
  'search.placeholder': '搜索消息...',
  'search.roleFilter.all': '全部',
  'search.roleFilter.user': '用户',
  'search.roleFilter.assistant': '助手',
  'search.resultCount': '找到 {count} 条结果',
  'search.noResults': '无匹配结果',
  'search.tooltip': '搜索消息',
  'search.close': '关闭搜索',

  // ── Export ──
  'export.button': '导出对话',
  'export.pdf': '导出为 PDF',
  'export.json': '导出为 JSON',

  // ── Sidebar ──
  'sidebar.title': '对话记录',
  'sidebar.empty': '暂无对话记录',
  'sidebar.newChat': '新对话',
  'sidebar.loading': '加载中...',
  'sidebar.msgCount': '{count} 条消息',
  'sidebar.today': '今天',
  'sidebar.yesterday': '昨天',
  'sidebar.earlier': '更早',
};

export default zhCN;
