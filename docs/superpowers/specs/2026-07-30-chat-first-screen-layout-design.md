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

已在草稿里实测不退化，但**下面的数字是修正后的** —— 初稿算错了：`gap: 16` 作用于**所有**相邻 flex 子项，而开着面板时子项是「侧栏｜对话列｜拖拽条｜面板」，共**三个** 16px 间隙，初稿只算了一个。

1280px 开着面板时的对话列宽：

| | 算式 | 结果 |
|---|---|---|
| 今天 | `1280 − 64(布局内边距) − 32(根 margin:0 16px) − 220 − 16×3 − 8 − 560` | **348px** |
| 改后 | `1280 − 64 − 220 − 16×3 − 8 − 560` | **380px** |

变宽 32px，结论不变。

**同时记录一个现状就存在、本次不处理的问题**：380px 的对话列本身窄得难用（草稿实测助手气泡只有 228px，正文每约 8 字换行，输入框工具栏也挤成两行）。今天是 348px，更窄 —— 这不是本次引入的。用户可以拖窄面板（可拖范围 360–900px）换回列宽：拖到 360 时对话列有 580px。若要根治，最便宜的一招是去掉拖拽条两侧那两个冗余的 16px 间隙（拖拽条本身已是视觉分隔），可回收 32px；但这改的是用户没提的状态，列为待定，不并入本次。

### D3 — 空状态抬到视觉中心，且不动输入框的 DOM 位置

- 空状态下，消息滚动区里那层 `.chat-column-inner` 包裹 div 取 `display: flex; flex-direction: column; min-height: 100%`（`min-height` 而非 `height`，这样有对话时内容超高仍能正常撑开滚动），并在 hero 之前插一个 `{messages.length === 0 && <div style={{ flex: "1 1 0", minHeight: 0 }} />}` 撑高块 —— hero 因此贴到输入框上沿。这三条 flex 属性只在 `messages.length === 0` 时施加；有对话时包裹层退回普通块级，消息按原样堆叠。
- 输入区**之后**追加一个撑高块 `{messages.length === 0 && <div style={{ flex: "1 1 0", minHeight: 0 }} />}`，与消息区的 flex 上下配对、均分剩余空间。
- 空状态下消息区改用 `flex: 1 1 auto`（基准 = hero 自身高度）而非 `flex: 1`（基准 0）—— 只有这样上下两块才真正均分，整组才落在中心。

**为何不用固定的 `paddingBottom: min(12vh, 96px)`（初稿的写法）**：草稿实测证否了。固定抬升补不回输入框下方新增的约 150px 卡片区，整组仍**偏下 90px**，达不到 D3 说的「视觉中心」。改成上下撑高块配对后实测**偏下 13px**（1905×900），且因为是 flex 比例而非固定值，任意屏高都自动成立 —— 375×900 下实测同为偏下 13px。

**不用 `justifyContent: flex-end`**：它作用在 `overflow: auto` 容器上时，内容超出容器（矮屏、浏览器放大）会让溢出的顶部滚不到 —— Safari 上尤其。`flex: 1 1 0` 撑高块在空间不足时自己压到 0，hero 永远从滚动原点开始，没有这个失效模式。

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

对话列自身的槽位同理：`[头部行, 消息区, 输入区, {空状态 && 撑高块}]` —— 撑高块作为条件槽位追加在**末尾**，输入区恒定停在槽位 2，不受空状态切换影响。

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

宗风控件为 `Button type="text" size="small"`，文字标签取 `selectedMaster ? selectedMaster.name_zh : t("chat.general_assistant")`，后置 `DownOutlined`；`onClick` 开长廊；Tooltip 用现有 `chat.change_master`。

> **实施后修订（2026-07-30，commit `83846954`）**：初版在选中祖师时于按钮内前置 18px `MasterSeal`，真机目视否掉了 —— `MasterSeal` 的字号是 `size × 0.32`，18px 只剩 6px，两个汉字挤成认不出的色块；而紧邻的文字标签已把名号写明（`textContent` 实测为「慧能慧能」）。**已去掉按钮内的印章**，只留文字标签 —— 变化的文字本身就是「已选宗风」的指示器。印章保留在空状态 hero（D5），那里 40px、字号 13px 可读，且不与名号重复（hero 标题是产品名而非祖师名）。

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

375px 一格原是 D7 的风险点，**已在草稿里验证通过**：靠 `global.css` 现有的 `@media (max-width:480px)`（`.chat-input-toolbar` 换行 + `.chat-input-spacer` 撑满一行）,工具栏在 375px 下是 `＋ 通用助手▾ DeepSeek V4 Pro▾` / `发送` **两行**，不是担心的三行。**不需要**改模型选择器的标签。真机仍要复核一次（草稿用的是容器查询模拟，与真实的视口 media query 触发条件不完全等价）。

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
| 矮屏（≤600px 高）空状态被压扁 | 上下两个撑高块先压到 0；hero 仍从滚动原点开始可读。再矮时消息区收缩、hero 在小窗口内滚动 —— 与今天完全相同（今天消息区也是 `flex: 1 1 0%`，同样会收缩到滚动窗口），不是退化 |
| ~~375px 工具栏顶成三行~~ | 草稿已验证为两行，无需处置；真机复核一次 |
| 1280 开引文面板时对话列仅 380px | 现状问题（今天 348px），本次不处理；已在 D2 记录成因、可拖窄面板的缓解办法、以及一个待定的 32px 回收方案 |
| `.chat-column-inner` 改错层级导致滚动条内缩 | 类只加在滚动容器的**内容** div 上，不加在容器本身 |
