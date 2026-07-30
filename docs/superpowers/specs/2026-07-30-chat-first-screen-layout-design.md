# /chat 首屏布局紧凑化 — 设计

日期：2026-07-30
状态：待评审
影响范围：`frontend/src/pages/ChatPage.tsx`、`frontend/src/styles/global.css`、`frontend/src/styles/master-gallery.css`

## 问题

1905px 宽屏上，`/chat` 整页被 `maxWidth: 1100 + margin: 0 auto`（`ChatPage.tsx:1131-1137`）压成居中块，左右各切掉约 400px 死白，会话侧栏因此浮在屏幕中间偏左而非贴近左缘。同时空状态的建议卡片区被 `maxWidth: 480`（`ChatPage.tsx:1302`）压窄，卡片内文字换行、外面却大片空着；欢迎区钉在滚动区顶部、输入框钉在底部，中间留下约 160px 竖向空洞。

## 目标与非目标

**目标**：消除横向死白与竖向空洞；空状态按 ChatGPT / Claude 的做法收成「标题 + 输入框 + 建议」一组、抬到视觉中心；输入区周边控件密度降下来。

**非目标**（本次明确不动）：
- 消息气泡形态、引用链接、信任标记、参考经文 chip 的排版（对应被否决的方案 C）
- RAG 检索、引文核验、任何后端行为
- 输入框 placeholder 的建议词轮播 + `⇥ Tab` 提示。建议卡片移到输入框下方后，placeholder 里再放一条建议确实冗余，但改掉它会一并抹掉 Tab 轮播这个功能的唯一发现入口，超出「优化布局」的授权范围。保持原样。

## 决策

### D1 — 根容器满宽，对话列自己居中

根容器去掉 `maxWidth: 1100` 与 `margin: 0 auto`，改为满宽；侧栏留在左侧，对话列用 `.chat-column-inner { width: 100%; max-width: 840px; margin: 0 auto }` 在侧栏右侧的剩余空间里居中。

该类施加于三处，使它们对齐成一列：

1. 头部行（移动端开关 + 导出）—— 直接加在该 div 上
2. 消息滚动区 —— **在滚动容器内新增一个 `.chat-column-inner` 包裹 div**，原有子节点（`messagesTopRef` 哨兵、加载更早按钮、hero、消息列表、`bottomRef` 哨兵）全部移进去。类**不加在滚动容器本身**，否则滚动条会跟着向内缩
3. 输入区 —— 同样在 `padding: "12px 0"` 那个 div 内新增一个 `.chat-column-inner` 包裹 div

两个哨兵 div 移入包裹层后仍在同一滚动容器内，`scrollIntoView` 行为不变。

实际位移：侧栏左移 371px 至距视口 32px —— 与顶栏「佛津」字标（`Layout.tsx:195`，`padding: 0 32px`）和 `.layout-content-inner`（`global.css:557`，`padding: 24px 32px`）的页边距对齐；对话列中心在 1905px 屏上保持 1071px 不变。

**为何不让对话列贴侧栏左对齐**：那样 1905px 屏右侧会空出约 800px，比现状更失衡，也不是参考产品的做法。

**840 这个数的来历**：助手气泡是列宽的 `maxWidth: 75%`，840 → 630px，与今天 864px 列宽下的 648px 基本持平，阅读行宽不退化；空状态两列卡片正好各 420px。

### D2 — 删掉引文面板的宽度特例

`maxWidth: citationTarget ? undefined : 1100` 与 `margin: citationTarget ? "0 16px" : "0 auto"` 两个三元表达式一并删除。840 上限在空间不足时自动失效，无需特例。

已核算不退化：1280px 开着面板时，对话列宽从今天的 `1280 − 64 − 32 − 220 − 16 − 8 − 560 = 380px` 变为 `1280 − 64 − 220 − 16 − 8 − 560 = 412px`，是变宽。

### D3 — 空状态抬到视觉中心，且不动输入框的 DOM 位置

- 空状态下，消息滚动区里那层 `.chat-column-inner` 包裹 div 取 `display: flex; flex-direction: column; min-height: 100%`（`min-height` 而非 `height`，这样有对话时内容超高仍能正常撑开滚动），并在 hero 之前插一个 `{messages.length === 0 && <div style={{ flex: "1 1 0", minHeight: 0 }} />}` 撑高块 —— hero 因此贴到输入框上沿。这三条 flex 属性只在 `messages.length === 0` 时施加；有对话时包裹层退回普通块级，消息按原样堆叠。
- 输入区（`ChatPage.tsx:1388`，`padding: "12px 0"`）在空状态下把 `paddingBottom` 覆写为 `min(12vh, 96px)`，把整组抬离底部。

**不用 `justifyContent: flex-end`**：它作用在 `overflow: auto` 容器上时，内容超出容器（矮屏、浏览器放大）会让溢出的顶部滚不到 —— Safari 上尤其。`flex: 1 1 0` 撑高块在空间不足时自己压到 0，hero 永远从滚动原点开始，没有这个失效模式。

**不用尾部撑高 div**：`paddingBottom` 少一个 DOM 节点，且 vh 单位随屏高自缩放，矮屏上不会硬吃固定的 120px。

**为何输入框必须留在原 DOM 位置**：`ChatPage.tsx:1058` 那个拦 Tab 的 effect 依赖是 `[tabSuggestions, tabIndex]`、不含 textarea 元素本身 —— 一旦 TextArea remount，监听不会重挂，Tab 轮播建议词会静默失效。

承重事实：`{cond && <X/>}` 会占住一个**稳定的子节点槽位**（条件为假时 React 渲染 `false` 但保留位置），所以条件兄弟节点永远不会让后面的索引位移。改后输入区的子节点槽位表：

| 槽位 | 内容 | 条件 |
|---|---|---|
| 0 | 游客保存提示 Alert | 条件 |
| 1 | `DraggableModal`（祖师长廊） | 恒定 |
| 2 | 配额 Alert | 条件 |
| 3 | **`.chat-input-shell`** | **恒定** |
| 4 | `.mg-disclaimer` | 条件 |
| 5 | `.chat-hero-cards` | 条件 |

`.chat-input-shell` 在所有运行时状态转移下恒定停在槽位 3，TextArea 的 fiber 得以存活。

注意 `DraggableModal` 在数组里从今天的第 4 位前移到槽位 1。这是安全的 —— 它通过 portal 渲染，在子节点数组里的位置不影响输出的 DOM 结构。前移的目的是让恒定槽位集中在条件槽位之前，槽位表更容易一眼看明白。

### D4 — 空状态去掉输入区顶部横线

`ChatPage.tsx:1388` 的 `borderTop: "1px solid rgba(217,208,193,0.5)"` 在空状态下正好把 hero 和输入框割开，而这道缝是参考产品没有的。改为 `borderTop: messages.length === 0 ? "none" : "1px solid rgba(217,208,193,0.5)"`。有对话时保留 —— 那时它起的是分隔消息流与输入区的正当作用。

### D5 — hero 标记：未选祖师时不要图标

- 未选祖师：删掉 44px 的 `RobotOutlined` 及其 12px 下边距，只留标题 + 副标题。省下 56px 竖向空间，与 ChatGPT 现在无图标的空状态一致。
- 已选祖师：在标题上方显示 `MasterSeal`（印文取 `name_zh` 前两字，与 `ChatPage.tsx:1419` 现有写法一致），此时它是信息而非装饰。

标题 `chat.title` 由 18px 提到 22px。副标题两行（`chat.subtitle` + `chat.subtitle2`）都保留 —— 第二行「答案标注经文出处，可点开核对原文」是本产品的核心承诺。

**为何不盖一枚「小津」印**：`en` 的 `chat.title` 是 "AI Buddhist Q&A"，通篇没有「小津」，在英文标题上盖中文印不通；而新增 `chat.seal` 键会逼我替英文界面凭空发明印文。本方案因此**新增 i18n 键为 0**，`zh` / `zh-Hant` / `en` 三个 locale 文件都不用动，i18n ratchet 不会被触发。

### D6 — 建议卡片移到输入框下方，铺满列宽

从消息区搬到输入区（槽位 5），去掉 `maxWidth: 480`，`grid-template-columns: 1fr 1fr`、gap 8，铺满 840 列（每张 420px）。「换一批」按钮随之下移。

卡片内部由「标签在上、问题在下」的竖向堆叠改为同行：`display: flex; align-items: baseline; gap: 8px`，标签 pill `flex-shrink: 0`，问题文字自然换行、**不截断**。420px 宽度下 13px 字约容 26 字，绝大多数问题一行放下；放不下的允许折成两行，不做省略号 —— 截断经名会让人无法判断该不该点。

≤600px 视口降为单列。这是一个新断点 —— 本仓现有断点是 768（侧栏隐藏）和 480（工具栏换行），都不合用：768px 下侧栏已消失、对话列约 748px，两列各 370px 仍宽裕；而拖到 480px 才换单列，中间 600-480 这段每列只剩约 230px，卡片会挤成三四行。故取 600。

### D7 — 宗风从整行收进输入框工具栏

删掉 `.mg-head` 那一整行（`ChatPage.tsx:1416-1440`），在 `.chat-input-toolbar` 里排成 `＋ | 宗风 ▾ | 模型 ▾ | ⟶ | 发送`。

宗风控件为 `Button type="text" size="small"`，文字标签取 `selectedMaster ? selectedMaster.name_zh : t("chat.general_assistant")`，选中祖师时前置 18px `MasterSeal`，后置 `DownOutlined`；`onClick` 开长廊；Tooltip 用现有 `chat.change_master`。

**为何保留文字标签**：`ChatPage.tsx:1411-1415` 的注释记录了一个刻意决定 —— 15 位祖师是本产品最锋利的差异点，此前藏在灰色 `Select` 里，遂改成显眼整行「把所选宗风明说出来」。收进工具栏但保留文字标签，守住"明说"，只是不再占一整行。

`.mg-disclaimer`（选中祖师时才出现）保留，移到输入框下方（槽位 4）。

### D8 — Key 状态移到侧栏底部

`已配置 Key (deepseek)` 按钮从「新对话」正下方移到会话列表之后。会话列表本就是 `flex: 1`，排它后面即自然沉底；加一道 `borderTop` 分隔。移动端抽屉同步改。

侧栏折叠（48px）时该按钮本来就不渲染，不受影响。

**已知边界**：零会话的用户会看到该按钮孤零零钉在约 670px 高的空侧栏底部。ChatGPT 的账号行同理，接受。

### D9 — 删死 CSS

`.mg-head` 删除后，`master-gallery.css:255-288` 的 `.mg-head` / `-id` / `-name` / `-sub` / `-swap` 共 30 行零引用，同 PR 删除。`.mg-disclaimer` 仍在用，保留。

新增 CSS 规则一律用 `var(--fj-*)` 令牌，不新增硬编码色值 —— 本仓已有硬编码色债（`.chat-input-shell` 的 `#d9d9d9` / `#f0f0f0` 即是），不再往上加。

## 新增 / 修改的 CSS

`global.css`：
- `.chat-column-inner` — `width: 100%; max-width: 840px; margin: 0 auto`
- `.chat-hero-cards` — 两列网格 + ≤600px 单列
- `.chat-hero-card` — 卡片本体（标签与问题同行）
- `.chat-lineage-btn` — 工具栏内宗风控件
- `.chat-sidebar-foot` — 侧栏底部 Key 行的分隔线

`master-gallery.css`：删除 `.mg-head*` 五条规则。

## 验证

**真实 Chrome 目视**（不只跑测试；矩阵每格都要看）：

| 维度 | 取值 |
|---|---|
| 登录态 | 已登录（有侧栏） / 游客（无侧栏） |
| 对话态 | 空状态 / 有对话 |
| 宽度 | 1905 · 1280 · 768 · 375 |
| 引文面板 | 开 / 关（1905 与 1280 两档） |
| 宗风 | 未选 / 已选（验证印章 + disclaimer） |
| 侧栏 | 展开 / 折叠 |

375px 一格是 D7 的验收点：工具栏若顶成三行，改模型选择器在 ≤480px 下的标签，**不动**宗风文字标签。

**自动化门禁**：`npm run lint`（`--max-warnings 0`）、`npx tsc -b --noEmit`、`npm test`、`npm run i18n:check`、`npm run build`。

**新增测试** `frontend/src/pages/ChatPage.test.tsx`：脚手架照 `CollectionsPage.test.tsx:1-45`（`QueryClientProvider` + `MemoryRouter` + `HelmetProvider` + `vi.mock("../api/client")`），另需灌 `useAuthStore` 与 7 个 client mock（`getChatSessions` / `getApiKeyStatus` / `getChatQuota` / `getHotQuestions` / `getRandomHotQuestions` / `getMasters` / `updateChatMessageFeedback`）。断言三条结构事实：

1. 空状态下宗风控件在 `.chat-input-toolbar` 内
2. 空状态下建议卡片在输入区内、且在 `.chat-input-shell` 之后
3. `.mg-head` 不再出现在 DOM 里

三条在改动前**都会红**（今天宗风在 `.mg-head`、卡片在消息区）。按仓库规矩，落笔前先在未改的代码上跑一遍确认是红的，再实施 —— 不接受恒真断言。

**回归重点**：改完后手动验一次 Tab 轮播建议词在「发出第一条消息之后」仍然工作 —— 这是 D3 唯一真正想防住的失效模式，而它是单测覆盖不到的（依赖真实 textarea 的原生 keydown）。

## 风险

| 风险 | 处置 |
|---|---|
| TextArea remount 导致 Tab 轮播失效 | D3 的槽位表已排除；另有手动回归验证兜底 |
| 矮屏（≤600px 高）空状态被压扁 | `flex: 1 1 0` 撑高块先压到 0；hero 仍从滚动原点开始可读。极矮屏下 hero 可能需要滚动才能看全，与现状相当 |
| 375px 工具栏顶成三行 | 实测项，处置办法已在 D7 写明 |
| `.chat-column-inner` 改错层级导致滚动条内缩 | 类只加在滚动容器的**内容** div 上，不加在容器本身 |
