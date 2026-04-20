# 需求文档：前端体验增强（Frontend Experience Enhancement）

## 需求 1：暗色模式（Dark Mode）

### 验收标准

- 1.1 Given 用户在聊天页面，When 点击主题切换按钮，Then 主题在 light → dark → system 三种模式间循环切换，界面颜色即时更新 <!-- PBT: toggleTheme 循环属性 — 任意起始 ThemeMode，3 次 toggle 回到原点 -->
- 1.2 Given 用户选择了某个主题模式，When 刷新页面或重新打开应用，Then 主题偏好从 localStorage 恢复，界面使用上次选择的主题 <!-- PBT: 任意 ThemeMode 值写入 localStorage 后读取一致 -->
- 1.3 Given 用户选择 system 模式，When 操作系统切换深色/浅色模式，Then 界面自动跟随系统偏好变化
- 1.4 Given 主题切换发生，When Ant Design 组件渲染，Then ConfigProvider 的 theme token 与当前主题一致（暗色模式使用暗色 token）
- 1.5 Given 主题切换为 dark 或 light，When applyTheme 执行，Then document.documentElement 上的所有 CSS 变量与 THEME_CONFIGS[resolved] 配置完全一致 <!-- PBT: 对 light/dark 两种模式验证 CSS 变量同步 -->

## 需求 2：对话导出

### 验收标准

- 2.1 Given 聊天记录非空，When 用户选择 JSON 导出，Then 生成包含 version、exportedAt、sessionId、messageCount、messages 的合法 JSON 文件并触发下载 <!-- PBT: 任意消息数组，exportToJSON 输出可解析且结构正确 -->
- 2.2 Given 聊天记录非空，When 用户选择 PDF 导出，Then 触发浏览器打印对话框，打印内容包含所有消息的角色、内容和时间戳
- 2.3 Given 导出选项 includeMetadata 为 false，When 执行导出，Then 导出数据中所有消息不含 metadata 字段；includeAgentEvents 为 false 时同理 <!-- PBT: 任意消息和选项组合，验证字段包含/排除控制 -->
- 2.4 Given 导出完成，When 文件生成，Then 通过 Blob + URL.createObjectURL 触发浏览器下载，文件名包含 sessionId 前缀

## 需求 3：消息搜索与历史筛选

### 验收标准

- 3.1 Given 消息列表非空，When 用户输入搜索关键词，Then 仅显示包含该关键词的消息，关键词在消息内容中高亮显示 <!-- PBT: 任意消息数组和关键词，搜索结果是输入的子集且每条结果包含关键词 -->
- 3.2 Given 搜索栏可见，When 用户选择角色筛选（用户/助手/全部），Then 仅显示匹配角色的消息 <!-- PBT: 筛选后所有消息的 role 匹配筛选条件 -->
- 3.3 Given 搜索栏可见，When 用户设置时间范围筛选，Then 仅显示时间戳在范围内的消息 <!-- PBT: 筛选后所有消息的 timestamp 在 [start, end] 范围内 -->
- 3.4 Given 搜索结果返回，When 渲染高亮，Then 所有 matchPositions 中的 [start, end] 满足 0 <= start < end <= content.length <!-- PBT: 任意消息和关键词，高亮位置均有效 -->
- 3.5 Given 用户快速连续输入，When 搜索触发，Then 使用 300ms 防抖，仅在用户停止输入后执行搜索

## 需求 4：移动端适配优化

### 验收标准

- 4.1 Given 视口宽度 < 768px，When 渲染聊天页面，Then 聊天容器宽度为 100%，无水平滚动条，圆角减小
- 4.2 Given 移动端视口，When 渲染所有可交互元素（按钮、输入框、链接），Then 最小触控区域 ≥ 44×44px
- 4.3 Given 移动端视口，When 渲染聊天界面，Then Header 按钮紧凑排列，快捷回复按钮适配小屏宽度，输入区域贴底显示

## 需求 5：多语言 UI 切换

### 验收标准

- 5.1 Given 翻译资源已加载，When 调用 t(key)，Then 已注册的 key 返回当前语言的翻译文本，未注册的 key 返回 key 本身 <!-- PBT: 任意随机 key，不存在时返回 key 本身 -->
- 5.2 Given 用户点击语言切换按钮，When 语言从 zh-CN 切换到 en-US（或反之），Then 界面所有可见文本更新为目标语言
- 5.3 Given 翻译资源定义，When 验证资源完整性，Then 所有 key 在 zh-CN 和 en-US 中都有对应翻译 <!-- PBT: 遍历所有 key，验证每个 locale 都有翻译 -->
- 5.4 Given 翻译文本含 {paramName} 占位符，When 调用 t(key, { paramName: value })，Then 返回文本中所有 {paramName} 被替换为 value <!-- PBT: 任意 key 和 params，替换后文本不含未替换的占位符 -->
- 5.5 Given 用户选择了某个语言，When 刷新页面，Then 语言偏好从 localStorage 恢复，界面使用上次选择的语言
