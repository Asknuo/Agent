# 实现任务：前端体验增强

## 任务 1：暗色模式（Dark Mode）

- [x] 1.1 创建主题配置与 CSS 变量
  - [x] 1.1.1 在 `src/theme.ts` 中定义 `ThemeMode` 类型、`THEME_CONFIGS` 常量（light/dark 两套 CSS 变量映射）、`toggleTheme`、`resolveTheme`、`applyTheme` 函数
  - [x] 1.1.2 在 `src/index.css` 中添加 `[data-theme="dark"]` 选择器下的暗色样式覆盖，覆盖所有现有类（.app-bg、.chat-container、.chat-header、.msg-bot、.login-card 等）
  - [x] 1.1.3 [PBT] 编写属性测试验证 `toggleTheme` 循环属性（任意起始值，3 次 toggle 回到原点）和 `resolveTheme` 返回值只能是 'light' | 'dark' `src/__tests__/test_theme_properties.test.ts`
- [x] 1.2 创建 ThemeProvider 上下文
  - [x] 1.2.1 在 `src/ThemeProvider.tsx` 中实现 ThemeContext、ThemeProvider 组件和 `useTheme` Hook，包含 localStorage 持久化、系统偏好监听（matchMedia）、CSS 变量应用
  - [x] 1.2.2 在 `src/App.tsx` 中用 ThemeProvider 包裹根组件，将 Ant Design ConfigProvider 的 theme token 与当前主题联动
- [x] 1.3 添加主题切换 UI
  - [x] 1.3.1 在 ChatPage 的 header-actions 区域添加主题切换按钮（☀️/🌙/💻 图标），调用 `useTheme().toggleTheme()`
  - [x] 1.3.2 在 LoginPage 右上角添加主题切换按钮

## 任务 2：多语言 UI 切换（i18n）

- [x] 2.1 创建国际化基础设施
  - [x] 2.1.1 在 `src/i18n.ts` 中实现 `translate` 函数、`Locale` 类型定义、`TranslationResource` 类型
  - [x] 2.1.2 在 `src/locales/zh-CN.ts` 和 `src/locales/en-US.ts` 中定义翻译资源，覆盖所有现有中文硬编码文本（登录页、聊天页、欢迎语、快捷回复、元数据标签、错误提示等）
  - [x] 2.1.3 [PBT] 编写属性测试验证 `translate` 函数：未注册 key 返回 key 本身、参数插值完整性、翻译资源完整性（所有 key 在所有 locale 中存在） `src/__tests__/test_i18n_properties.test.ts`
- [x] 2.2 创建 I18nProvider 上下文
  - [x] 2.2.1 在 `src/I18nProvider.tsx` 中实现 I18nContext、I18nProvider 组件和 `useI18n` Hook，包含 localStorage 持久化、Ant Design locale 同步
  - [x] 2.2.2 在 `src/App.tsx` 中用 I18nProvider 包裹根组件（在 ThemeProvider 内层）
- [x] 2.3 替换硬编码文本
  - [x] 2.3.1 将 `src/App.tsx` 中所有中文硬编码字符串替换为 `t('key')` 调用，包括：LoginPage 的标题/按钮/提示、ChatPage 的欢迎语/快捷回复/输入提示、MetricsPanel 的标题/标签、sentimentMap 和 intentMap 的中文标签
  - [x] 2.3.2 在 ChatPage 的 header-actions 区域添加语言切换按钮（中/EN 切换）

## 任务 3：对话导出

- [x] 3.1 实现导出核心逻辑
  - [x] 3.1.1 在 `src/export.ts` 中实现 `exportToJSON` 函数（生成 ExportedConversation JSON 字符串）、`exportToPDF` 函数（iframe + window.print 方案）、`buildPrintableHTML` 辅助函数、`downloadBlob` 工具函数
  - [x] 3.1.2 [PBT] 编写属性测试验证 JSON 导出：输出可解析、messageCount 一致、元数据包含控制、高亮位置有效性 `src/__tests__/test_export_properties.test.ts`
- [x] 3.2 添加导出 UI
  - [x] 3.2.1 在 ChatPage 的 header-actions 区域添加导出按钮（Ant Design Dropdown），包含 PDF 和 JSON 两个选项，消息为空时禁用

## 任务 4：消息搜索与历史筛选

- [x] 4.1 实现搜索引擎
  - [x] 4.1.1 在 `src/search.ts` 中实现 `searchMessages` 函数（支持关键词匹配、角色筛选、时间范围筛选、元数据筛选）和 `useMessageSearch` Hook（含 300ms 防抖）
  - [x] 4.1.2 [PBT] 编写属性测试验证搜索引擎：结果是输入子集、顺序保持、空关键词全匹配、高亮位置有效、角色筛选正确 `src/__tests__/test_search_properties.test.ts`
- [x] 4.2 添加搜索 UI
  - [x] 4.2.1 在 ChatPage 中添加搜索栏组件（点击 header 搜索按钮展开），包含关键词输入框、角色筛选下拉、搜索结果计数显示
  - [x] 4.2.2 在消息列表中实现关键词高亮渲染（用 `<mark>` 标签包裹匹配文本）

## 任务 5：移动端适配优化

- [x] 5.1 添加响应式样式
  - [x] 5.1.1 在 `src/index.css` 中添加 `@media (max-width: 768px)` 媒体查询，覆盖：chat-container 全宽无圆角、header 按钮紧凑排列、消息气泡最大宽度调整、输入区域贴底、快捷回复按钮适配小屏
  - [x] 5.1.2 确保所有可交互元素（按钮、输入框）在移动端最小触控区域 ≥ 44×44px，添加 `min-height` 和 `min-width` 约束
- [x] 5.2 移动端交互优化
  - [x] 5.2.1 添加 viewport meta 标签确认（index.html），禁止双击缩放，优化软键盘弹出时的布局调整
