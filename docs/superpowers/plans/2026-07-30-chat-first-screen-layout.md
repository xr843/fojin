# /chat 首屏布局紧凑化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `/chat` 首屏左侧 371px 死白与中间 162px 竖向空洞，把空状态收成「标题 + 输入框 + 建议」一组并落在视觉中心，输入区周边控件密度降下来。

**Architecture:** 纯前端呈现层改动。根容器由 `maxWidth:1100` 居中块改为满宽，对话内容用 `.chat-column-inner`（840px 上限）在侧栏右侧自居中；空状态的竖向居中由「消息区 `flex:1 1 auto` + 输入区后置 `flex:1 1 0` 撑高块」上下配对实现，不搬动输入框的 DOM 位置；建议卡片从消息区下移到输入框之后，宗风整行收进输入框工具栏。

**Tech Stack:** React 19 + TypeScript + Vite + Ant Design 5 + react-i18next + vitest / @testing-library/react（jsdom）。

设计依据：[`docs/superpowers/specs/2026-07-30-chat-first-screen-layout-design.md`](../specs/2026-07-30-chat-first-screen-layout-design.md)（D1–D9）。

## Global Constraints

- 分支：`feat/chat-first-screen-layout`（已存在，spec 已在其上）。不直接提交到 `master` —— 该仓 master 由 webhook 自动部署。
- **新增 i18n 键 = 0。** 只复用现有 `chat.*` 键；`public/locales/{zh,zh-Hant,en}/translation.json` 三个文件都不改。
- **i18n ratchet 基线为空字典 = 每文件上限 0。** 不得引入 `t(...)` 调用之外的裸中文字符串字面量（`scripts/scan-hardcoded-zh.mjs` 的 `insideT()` 只豁免 `t()` / `console.*` / `umami.*` / `logger.*` 内部，以及行尾带 `// i18n-exempt` 的行）。
- 每个提交后五道 CI 门禁必须全绿：`npm run lint`（`eslint src/`，CI 用 `--max-warnings 0`）、`npx tsc -b --noEmit`、`npm test`、`npm run i18n:check`、`npm run build`。**不提交红测试。**
- 提交信息用 conventional commits（`feat:` / `fix:` / `refactor:` / `test:`），**不带任何 Claude 署名 trailer**（无 `Co-authored-by`、`Claude-Session`、`Generated-with`）。
- 新增 CSS 规则优先用 `var(--fj-*)` 令牌。已存在于被替换代码中的 `rgba(176,141,87,…)`（即 `--fj-gold` 的 rgb）可原样搬运以保持视觉连续，但**不得新增**新的硬编码十六进制色值。
- 命令都在 `frontend/` 目录下执行。
- **本次明确不动**：消息气泡形态、引用链接、信任标记、参考经文 chip、输入框 placeholder 的建议词轮播与 `⇥ Tab` 提示、后端任何行为。

## File Structure

| 文件 | 职责 | 动作 |
|---|---|---|
| `frontend/src/pages/ChatPage.tsx` | 页面结构与状态 | 修改（D1–D8） |
| `frontend/src/styles/global.css` | 新增 5 组 chat 布局类 | 修改 |
| `frontend/src/styles/master-gallery.css` | 删除失去引用的 `.mg-head*` | 修改（D9） |
| `frontend/src/pages/ChatPage.test.tsx` | 首屏结构回归测试 | 新建 |

`ChatPage.tsx` 已 1571 行，偏大。但本次是呈现层局部改动，不做文件拆分 —— 拆 `ChatPage` 需要连带迁移 SSE 生命周期与十余个 `useState`，超出本次授权范围，且会把一个可回滚的样式改动变成高风险重构。

---

### Task 1: 测试脚手架

建立 ChatPage 的 jsdom 渲染脚手架，并放一条必定为绿的自检。后续每个任务在此文件上追加自己那条断言。

**本任务的脚手架已在设计阶段实跑验证过**：`npx tsc -b --noEmit` 与 `npx eslint` 均干净，自检用例通过（6.5s）。

**Files:**
- Create: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: 无
- Produces: 供 Task 2–7 复用的 `renderPage()`、`renderEmpty()`、mock 数据 `CARDS` / `MASTERS`、以及 `beforeEach` 里灌好的 7 个 `../api/client` mock 与 `useAuthStore` 登录态。（DOM 顺序断言用的 `FOLLOWING` 常量**不在**本任务，见 Task 5。）

- [ ] **Step 1: 写脚手架与自检用例**

创建 `frontend/src/pages/ChatPage.test.tsx`：

```tsx
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import ChatPage from "./ChatPage";
import { useAuthStore } from "../stores/authStore";
import {
  getApiKeyStatus,
  getChatQuota,
  getChatSessions,
  getHotQuestions,
  getMasters,
  getRandomHotQuestions,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getApiKeyStatus: vi.fn(),
    getChatQuota: vi.fn(),
    getChatSessions: vi.fn(),
    getChatSessionMessages: vi.fn(),
    getHotQuestions: vi.fn(),
    getMasters: vi.fn(),
    getRandomHotQuestions: vi.fn(),
    sendChatMessageStream: vi.fn(),
    deleteChatSession: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
    getChunkContext: vi.fn(),
  };
});

// antd (Button/Tooltip/Select) reads matchMedia via useBreakpoint under jsdom.
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
});

const CARDS = [
  { id: 1, category: "白话翻译" as const, display_text: "「三毒」指的是哪三种毒？" },
  { id: 2, category: "经文解读" as const, display_text: "《胜鬘经》一乘如来藏怎么讲？" },
];

const MASTERS = [
  {
    id: "huineng", name_zh: "慧能", name_en: "Huineng", tradition: "禅宗",
    dates: "638–713", description: "南宗禅。", epigraph: null,
  },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/chat"]}>
          <ChatPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getRandomHotQuestions).mockResolvedValue({ questions: CARDS });
  vi.mocked(getHotQuestions).mockResolvedValue({ questions: ["什么是四圣谛？"] });
  vi.mocked(getMasters).mockResolvedValue(MASTERS);
  vi.mocked(getChatSessions).mockResolvedValue([]);
  vi.mocked(getApiKeyStatus).mockResolvedValue({
    has_api_key: true, provider: "deepseek", model: null, key_preview: null,
  });
  vi.mocked(getChatQuota).mockResolvedValue({
    limit: 10, used: 0, remaining: 10, has_byok: true,
  });
  useAuthStore.setState({
    token: "t",
    user: {
      id: 1, username: "reader", email: "r@example.com", display_name: null,
      role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
    },
  });
});

afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ token: null, user: null });
});

/** 等空状态首屏就绪（建议卡片到位）后再断言结构。 */
async function renderEmpty() {
  const r = renderPage();
  await waitFor(() => {
    expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument();
  });
  return r;
}

describe("ChatPage 首屏结构", () => {
  it("空状态渲染出标题与建议卡片（脚手架自检）", async () => {
    const { container } = await renderEmpty();
    expect(screen.getByText("小津 AI 佛典问答")).toBeInTheDocument();
    expect(container.querySelector(".chat-input-shell")).not.toBeNull();
  });
});
```

本任务**不要**预先声明任何后续任务才用到的常量。本仓 `tsconfig.json` 开着 `noUnusedLocals: true`（未引用的模块级 `const` → `TS6133`），且 `@typescript-eslint/no-unused-vars` 虽配为 `warn`，CI 跑的是 `--max-warnings 0`，同样会挂。DOM 顺序断言要用的 `FOLLOWING` 常量在 Task 5 —— 第一个真正引用它的任务 —— 才声明。

- [ ] **Step 2: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  1 passed (1)`

- [ ] **Step 3: 跑类型与 lint 门禁**

```bash
cd frontend && npx tsc -b --noEmit && npx eslint src/pages/ChatPage.test.tsx --max-warnings 0
```

Expected: 两条命令均无输出、退出码 0。（`mockResolvedValue` 的对象必须字段完整 —— `ApiKeyStatus` 需要 `model` / `key_preview`，`ChatQuota` 需要 `has_byok`；漏了 vitest 照样绿但 tsc 会报 TS2345。）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/ChatPage.test.tsx
git commit -m "test: 为 ChatPage 首屏结构建立渲染脚手架"
```

---

### Task 2: D1 + D2 — 根容器满宽，对话列 840px 自居中

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1131-1137`（根容器）、`:1254-1275`（头部行）、`:1277`（消息滚动区）、`:1388`（输入区）
- Modify: `frontend/src/styles/global.css`（在 `.chat-input-shell` 规则块之前新增 `.chat-column-inner`）
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `renderEmpty()`
- Produces: CSS 类 `.chat-column-inner`，被 Task 3 的 `.chat-msgs-empty` 叠加使用；消息滚动区内新增的包裹 div 是 Task 3 插入撑高块的宿主。

- [ ] **Step 1: 写失败测试**

在 `describe("ChatPage 首屏结构", …)` 内、自检用例之后追加：

```tsx
  it("D1: 头部行/消息区/输入区三处各有一个 .chat-column-inner", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelectorAll(".chat-column-inner")).toHaveLength(3);
  });
```

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected  to have a length of 3 but got +0`

- [ ] **Step 3: 加 CSS 类**

在 `frontend/src/styles/global.css` 中 `/* ========== Chat Input Shell (Claude.ai-style) ========== */` 这行注释**之前**插入：

```css
/* ========== Chat Column ========== */
/* 根容器满宽，对话内容自己居中 —— 侧栏因此贴到页面左边距（与顶栏字标的
   32px 对齐），而不是跟着一个 1100px 居中块浮到屏幕中间。
   只加在滚动容器的「内容」上，不加在滚动容器本身，否则滚动条会向内缩。 */
.chat-column-inner {
  width: 100%;
  max-width: 840px;
  margin: 0 auto;
}
```

- [ ] **Step 4: 根容器去掉 1100 居中与引文面板特例**

`ChatPage.tsx` 把：

```tsx
      <div style={{
        display: "flex",
        height: "calc(100vh - 120px)",
        maxWidth: citationTarget ? undefined : 1100,
        margin: citationTarget ? "0 16px" : "0 auto",
        gap: 16,
      }}>
```

改为：

```tsx
      <div style={{
        display: "flex",
        height: "calc(100vh - 120px)",
        gap: 16,
      }}>
```

- [ ] **Step 5: 头部行套上 .chat-column-inner**

把：

```tsx
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
            {user ? (
              <Button
                className="chat-mobile-toggle"
                type="text"
                icon={<MenuOutlined />}
                onClick={() => setSidebarOpen(true)}
              >
                {t("chat.session_list")}
              </Button>
            ) : <div />}
            {messages.length > 0 && (
              <Tooltip title={t("chat.export_tooltip")}>
                <Button
                  type="text"
                  icon={<DownloadOutlined />}
                  onClick={handleExport}
                  style={{ color: "var(--fj-ink-muted)" }}
                />
              </Tooltip>
            )}
          </div>
```

改为（外层只负责占位，内层负责对齐）：

```tsx
          <div style={{ display: "flex", marginBottom: 4 }}>
            <div className="chat-column-inner" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              {user ? (
                <Button
                  className="chat-mobile-toggle"
                  type="text"
                  icon={<MenuOutlined />}
                  onClick={() => setSidebarOpen(true)}
                >
                  {t("chat.session_list")}
                </Button>
              ) : <div />}
              {messages.length > 0 && (
                <Tooltip title={t("chat.export_tooltip")}>
                  <Button
                    type="text"
                    icon={<DownloadOutlined />}
                    onClick={handleExport}
                    style={{ color: "var(--fj-ink-muted)" }}
                  />
                </Tooltip>
              )}
            </div>
          </div>
```

- [ ] **Step 6: 消息滚动区内加包裹层**

把：

```tsx
          <div style={{ flex: 1, overflow: "auto", padding: "16px 0" }}>
            <div ref={messagesTopRef} />
```

改为：

```tsx
          <div style={{ flex: 1, overflow: "auto", padding: "16px 0" }}>
            <div className="chat-column-inner">
            <div ref={messagesTopRef} />
```

并在该滚动区的收尾处，把：

```tsx
            {/* Streaming cursor is shown inline via ▌ in the message bubble */}
            <div ref={bottomRef} />
          </div>
```

改为：

```tsx
            {/* Streaming cursor is shown inline via ▌ in the message bubble */}
            <div ref={bottomRef} />
            </div>
          </div>
```

两个滚动哨兵移入包裹层后仍在同一滚动容器内，`scrollIntoView` 行为不变。

- [ ] **Step 7: 输入区内加包裹层**

把：

```tsx
          {/* Input */}
          <div style={{ padding: "12px 0", borderTop: "1px solid rgba(217,208,193,0.5)" }}>
```

改为：

```tsx
          {/* Input */}
          <div style={{ padding: "12px 0", borderTop: "1px solid rgba(217,208,193,0.5)" }}>
            <div className="chat-column-inner">
```

并在该输入区块的末尾（`</div>` 闭合 `.chat-input-shell` 之后、闭合输入区之前）补一层收尾 `</div>`。改完后输入区结构为：

```tsx
          <div style={{ padding: "12px 0", borderTop: "1px solid rgba(217,208,193,0.5)" }}>
            <div className="chat-column-inner">
              {/* 游客保存提示 Alert … */}
              {/* .mg-head 宗风整行 … */}
              {/* .mg-disclaimer … */}
              {/* <DraggableModal> … */}
              {/* 配额 Alert … */}
              <div className="chat-input-shell">…</div>
            </div>
          </div>
```

- [ ] **Step 8: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  2 passed (2)`

- [ ] **Step 9: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。`npm test` 会跑整套（含 `MessageBubble.test.tsx`），确认没连带打坏别的用例。

- [ ] **Step 10: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): 根容器改满宽，对话列 840px 自居中，消除左侧 371px 死白"
```

---

### Task 3: D3 + D4 — 空状态抬到视觉中心，去掉顶部横线

`paddingBottom` 那种固定抬升在草稿里实测**偏下 90px**，达不到「视觉中心」；改用上下两个 flex 撑高块配对均分，实测 1905×900 与 375×900 下均为**偏下 13px**。

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`（消息滚动区容器与其包裹层、hero 之前、输入区之后、输入区 `borderTop`）
- Modify: `frontend/src/styles/global.css`（`.chat-column-inner` 规则之后）
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: Task 2 的 `.chat-column-inner` 包裹层
- Produces: CSS 类 `.chat-msgs-empty` / `.chat-hero-lead` / `.chat-hero-trail`

- [ ] **Step 1: 写失败测试**

追加：

```tsx
  it("D3: 空状态有前后两个撑高块", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelector(".chat-hero-lead")).not.toBeNull();
    expect(container.querySelector(".chat-hero-trail")).not.toBeNull();
  });
```

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected null not to be null`

- [ ] **Step 3: 加 CSS**

在 `global.css` 的 `.chat-column-inner` 规则之后追加：

```css
/* 空状态：hero 贴到输入框上沿，整组由上下两个撑高块均分剩余空间而居中。
   min-height 而非 height —— 有对话时内容超高仍要能撑开滚动。
   不用 justify-content: flex-end：它作用在 overflow:auto 容器上时，内容超出
   容器（矮屏 / 浏览器放大）会让溢出的顶部滚不到，Safari 上尤其。撑高块在
   空间不足时自己压到 0，hero 永远从滚动原点开始。 */
.chat-msgs-empty {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
.chat-hero-lead,
.chat-hero-trail {
  flex: 1 1 0;
  min-height: 0;
}
```

- [ ] **Step 4: 消息滚动区改用 auto 基准并挂上空状态类**

把 Task 2 改出来的：

```tsx
          <div style={{ flex: 1, overflow: "auto", padding: "16px 0" }}>
            <div className="chat-column-inner">
            <div ref={messagesTopRef} />
```

改为（`flex: "1 1 auto"` 的基准 = hero 自身高度，只有这样上下两块才真正均分）：

```tsx
          <div style={{ flex: messages.length === 0 ? "1 1 auto" : 1, overflow: "auto", padding: "16px 0" }}>
            <div className={messages.length === 0 ? "chat-column-inner chat-msgs-empty" : "chat-column-inner"}>
            <div ref={messagesTopRef} />
            {messages.length === 0 && <div className="chat-hero-lead" />}
```

`{messages.length === 0 && <div className="chat-hero-lead" />}` 必须插在 `messagesTopRef` 之后、`{hasOlderMessages && …}` 之前。

- [ ] **Step 5: 输入区之后加撑高块**

在对话列内，输入区那个 `</div>`（闭合 `padding: "12px 0"` 的 div）之后、闭合对话列 `</div>` 之前插入：

```tsx
          {messages.length === 0 && <div className="chat-hero-trail" />}
```

改完后对话列的子节点顺序为 `[头部行, 消息区, 输入区, {空状态 && 撑高块}]` —— 撑高块是**追加在末尾**的条件槽位，输入区恒定停在槽位 2。这一点是承重的：`{cond && <X/>}` 会占住一个稳定的子节点槽位（条件为假时 React 渲染 `false` 但保留位置），所以条件兄弟节点永远不会让后面的索引位移，`.chat-input-shell` 里的 TextArea fiber 得以存活。若 TextArea remount，`ChatPage.tsx:1058` 那个拦 Tab 的 effect（依赖是 `[tabSuggestions, tabIndex]`、不含 textarea 元素本身）不会重挂，Tab 轮播建议词会静默失效。

- [ ] **Step 6: 空状态去掉输入区顶部横线**

把：

```tsx
          <div style={{ padding: "12px 0", borderTop: "1px solid rgba(217,208,193,0.5)" }}>
```

改为：

```tsx
          <div style={{ padding: "12px 0", borderTop: messages.length === 0 ? undefined : "1px solid rgba(217,208,193,0.5)" }}>
```

有对话时保留 —— 那时它起的是分隔消息流与输入区的正当作用。

- [ ] **Step 7: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  3 passed (3)`

- [ ] **Step 8: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): 空状态首屏抬到视觉中心，消除 162px 竖向空洞"
```

---

### Task 4: D5 — 首屏标记：未选祖师时不放图标

未选祖师时删掉 44px `RobotOutlined` 及其 12px 下边距，省下 56px 竖向空间；选中祖师时改放 `MasterSeal`，此时它是信息而非装饰。标题 18→22px。

不盖「小津」印：`en` 的 `chat.title` 是 "AI Buddhist Q&A"，通篇没有「小津」，在英文标题上盖中文印不通；新增 `chat.seal` 键会逼人替英文界面凭空发明印文。本方案因此新增 i18n 键为 0。

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`（空状态 hero 开头）
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: 已有的 `MasterSeal`（`ChatPage.tsx:34` 已 `import MasterGallery, { MasterSeal } from "../components/MasterGallery"`）、已有的 `selectedMaster`（`:459-462`）
- Produces: 无

- [ ] **Step 1: 写失败测试**

追加：

```tsx
  it("D5: 未选祖师时首屏不放机器人图标", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelectorAll(".anticon-robot")).toHaveLength(0);
  });
```

空状态没有消息，所以 `MessageBubble` 里那个助手头像的 `RobotOutlined` 不会渲染，`.anticon-robot` 的唯一来源就是 hero。

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected <span role="img" …(3)>…(1)</span> to have a length of +0 but got 1`

- [ ] **Step 3: 改 hero 开头**

把：

```tsx
              <div style={{ textAlign: "center", padding: "clamp(16px, 4vh, 60px) 24px", color: "var(--fj-ink-muted)" }}>
                <RobotOutlined style={{ fontSize: 44, marginBottom: 12, color: "var(--fj-accent)" }} />
                <div style={{ fontSize: 18, fontFamily: '"Noto Serif SC", serif', marginBottom: 6 }}>
                  {t("chat.title")}
                </div>
```

改为（竖向定位已由 Task 3 的撑高块负责，hero 自己不再需要 clamp 内边距）：

```tsx
              <div style={{ textAlign: "center", padding: "0 24px 14px", color: "var(--fj-ink-muted)" }}>
                {selectedMaster && (
                  <div style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
                    <MasterSeal text={Array.from(selectedMaster.name_zh).slice(0, 2).join("")} size={40} />
                  </div>
                )}
                <div style={{ fontSize: 22, fontFamily: '"Noto Serif SC", serif', marginBottom: 6 }}>
                  {t("chat.title")}
                </div>
```

印文取名字前两字，与 `ChatPage.tsx:1419` 现有写法一致（用 `Array.from` 而非 `slice`，避免切断代理对）。

`RobotOutlined` 的 import **保留** —— `MessageBubbleInner`（`:278`）仍在用它作助手头像。

- [ ] **Step 4: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  4 passed (4)`

- [ ] **Step 5: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): 首屏标记改为仅在选中祖师时显示印章，标题提到 22px"
```

---

### Task 5: D6 — 建议卡片下移到输入框之后并铺满列宽

去掉 `maxWidth: 480`，铺满 840 列（每张 420px）；卡片内部由「标签在上、问题在下」改为同行，长问题允许折两行、**不做省略号**（截断经名会让人无法判断该不该点）。顺带把卡片从 `<div onClick>` 改为 `<button type="button">`（可聚焦、可回车触发），hover 从内联事件处理器移到 CSS。

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx`（删除 hero 内的卡片网格与「换一批」；在输入区 `.chat-input-shell` 之后新增）
- Modify: `frontend/src/styles/global.css`
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: Task 1 的 `renderEmpty()`；已有的 `welcomeCardsData` / `welcomeCardsLoading` / `refetchWelcomeCards`（`:615-620`）、`HOT_QUESTION_CATEGORY_SLUGS`（`:75-80`）、`handleSendMessage`
- Produces: CSS 类 `.chat-hero-cards` / `.chat-hero-card` / `.chat-hero-card-tag`；测试常量 `FOLLOWING = 4`（Task 7 会复用它，不要重复声明）

- [ ] **Step 1: 写失败测试**

在 `describe(…)` 块**之前**（紧跟 `renderEmpty()` 函数之后）声明 DOM 顺序断言用的常量 —— 本任务是第一个引用它的任务，提前声明会因 `noUnusedLocals` / `--max-warnings 0` 挂掉门禁：

```tsx
const FOLLOWING = 4; // Node.DOCUMENT_POSITION_FOLLOWING
```

然后在 `describe` 内追加：

```tsx
  it("D6: 建议卡片在输入区内，且排在输入框之后", async () => {
    const { container } = await renderEmpty();
    const shell = container.querySelector(".chat-input-shell");
    const cards = container.querySelector(".chat-hero-cards");
    expect(shell).not.toBeNull();
    expect(cards).not.toBeNull();
    expect(shell!.compareDocumentPosition(cards!) & FOLLOWING).toBeTruthy();
  });
```

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected null not to be null`（`.chat-hero-cards` 还不存在）

- [ ] **Step 3: 加 CSS**

在 `global.css` 的 `.chat-hero-lead, .chat-hero-trail` 规则之后追加：

```css
/* 建议卡片：铺满对话列（840 → 每张 420px），标签与问题同行。
   rgba(176,141,87,…) 是 --fj-gold 的 rgb，从被替换的内联样式原样搬运。 */
.chat-hero-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 10px;
}
.chat-hero-card {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--fj-border);
  border-radius: 8px;
  background: transparent;
  color: var(--fj-ink-muted);
  font: inherit;
  font-size: 13px;
  line-height: 1.6;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}
.chat-hero-card:hover {
  border-color: var(--fj-accent);
  color: var(--fj-accent);
  background: rgba(176, 141, 87, 0.06);
}
.chat-hero-card-tag {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(176, 141, 87, 0.12);
  color: var(--fj-highlight);
  font-family: "Noto Serif SC", serif;
  letter-spacing: 0.02em;
}
/* 新断点。本仓现有 768（隐藏侧栏）与 480（工具栏换行）都不合用：768px 下侧栏
   已消失、对话列约 748px，两列各 370px 仍宽裕；拖到 480 才换单列的话，
   600–480 这段每列只剩约 230px，卡片会挤成三四行。 */
@media (max-width: 600px) {
  .chat-hero-cards { grid-template-columns: 1fr; }
}
```

- [ ] **Step 4: 从 hero 里删掉卡片网格与「换一批」**

删除 hero 内从 `<div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", …` 起、到「换一批」`Button` 所在块结束为止的整段（原 `ChatPage.tsx:1297-1364`）。删除后 hero 只剩：印章（条件）、标题、副标题两行。

- [ ] **Step 5: 在输入框之后插入卡片**

在输入区的 `.chat-input-shell` 那个 `</div>` 之后插入：

```tsx
              {messages.length === 0 && (welcomeCardsData?.questions?.length ?? 0) > 0 && (
                <>
                  <div className="chat-hero-cards">
                    {(welcomeCardsData?.questions ?? []).map((card: HotQuestionCard) => (
                      <button
                        key={card.id}
                        type="button"
                        className="chat-hero-card"
                        onClick={() => handleSendMessage(card.display_text, { hotQuestionId: card.id })}
                      >
                        <span className="chat-hero-card-tag">
                          {t(`chat.hot_question_category_${HOT_QUESTION_CATEGORY_SLUGS[card.category]}`, card.category)}
                        </span>
                        <span>{card.display_text}</span>
                      </button>
                    ))}
                  </div>
                  <div style={{ textAlign: "center", marginTop: 8 }}>
                    <Button
                      size="small"
                      type="text"
                      icon={<ReloadOutlined />}
                      loading={welcomeCardsLoading}
                      onClick={() => refetchWelcomeCards()}
                      style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                    >
                      {t("chat.refresh_hot_questions", "换一批")}
                    </Button>
                  </div>
                </>
              )}
```

用 `<>…</>` 包住两块，让它们共占**一个**子节点槽位，不打乱 `.chat-input-shell` 的槽位。`t("chat.refresh_hot_questions", "换一批")` 里的中文是 `t()` 的默认值参数，`insideT()` 会豁免，ratchet 不会报。

- [ ] **Step 6: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  5 passed (5)`

- [ ] **Step 7: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。若 `HotQuestionCard` 报未使用，检查它是否仍在 `import type { … }` 列表中被引用 —— 本步仍在用。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): 建议卡片下移到输入框之后并铺满列宽，标签与问题同行"
```

---

### Task 6: D7 — 宗风整行收进输入框工具栏

`ChatPage.tsx:1411-1415` 的注释记录了一个刻意决定：15 位祖师是本产品最锋利的差异点，此前藏在灰色 `Select` 里，遂改成显眼整行「把所选宗风明说出来」。**保留文字标签**守住「明说」，只是不再占一整行。

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:11-30`（新增 `DownOutlined` import）、`:1416-1445`（删 `.mg-head` 与旧位置的 disclaimer）、`:1508-1518`（工具栏）
- Modify: `frontend/src/styles/global.css`
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: 已有的 `selectedMaster`、`setGalleryOpen`、`MasterSeal`
- Produces: CSS 类 `.chat-lineage-btn`

- [ ] **Step 1: 写失败测试**

追加：

```tsx
  it("D7: 宗风控件在输入框工具栏内，且 .mg-head 整行已移除", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelector(".mg-head")).toBeNull();
    const toolbar = container.querySelector(".chat-input-toolbar");
    expect(toolbar).not.toBeNull();
    expect(toolbar!.querySelector(".chat-lineage-btn")).not.toBeNull();
  });
```

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected <div class="mg-head" …(1)>…(2)</div> to be null`

- [ ] **Step 3: 加 CSS**

在 `global.css` 的 `.chat-hero-card-tag` 规则之后（600px 媒体查询之前）追加：

```css
/* 宗风控件：收进工具栏但保留文字标签 —— 所选宗风仍被明说，只是不再占一整行 */
.chat-lineage-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--fj-ink-light);
}
```

- [ ] **Step 4: 新增 DownOutlined import**

在 `ChatPage.tsx` 顶部的 `@ant-design/icons` import 列表里，`ShareAltOutlined,` 之后加一行：

```tsx
  DownOutlined,
```

- [ ] **Step 5: 删掉 .mg-head 整行与旧位置的 disclaimer**

删除原 `ChatPage.tsx:1411-1445` 中的这两块（连同它们上面那段解释 `.mg-head` 由来的注释一起删 —— 决定本身已记进本任务开头与 spec 的 D7）：

```tsx
            <div className="mg-head" style={{ marginBottom: 8 }}>
              … 印章 / 名号 / 更换宗派 按钮 …
            </div>
            {selectedMaster && (
              <div className="mg-disclaimer" style={{ marginTop: 0, marginBottom: 8 }}>
                {t("chat.master_disclaimer")}
              </div>
            )}
```

`<DraggableModal open={galleryOpen} …>` **保留原处** —— 删掉上面两块后它自然落到槽位 1。它通过 portal 渲染，在子节点数组里的位置不影响输出的 DOM 结构。

- [ ] **Step 6: 工具栏加入宗风控件**

把：

```tsx
              <div className="chat-input-toolbar">
                <Tooltip title={t("chat.attachment_tooltip")}>
                  <Button
                    type="text"
                    size="small"
                    icon={uploadingAttachment ? <Spin size="small" /> : <PlusOutlined />}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingAttachment || attachments.length >= MAX_ATTACHMENTS}
                  />
                </Tooltip>
                <ChatModelSelector value={modelId} onChange={handleModelChange} />
```

改为：

```tsx
              <div className="chat-input-toolbar">
                <Tooltip title={t("chat.attachment_tooltip")}>
                  <Button
                    type="text"
                    size="small"
                    icon={uploadingAttachment ? <Spin size="small" /> : <PlusOutlined />}
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadingAttachment || attachments.length >= MAX_ATTACHMENTS}
                  />
                </Tooltip>
                <Tooltip title={t("chat.change_master")}>
                  <Button
                    type="text"
                    size="small"
                    className="chat-lineage-btn"
                    onClick={() => setGalleryOpen(true)}
                  >
                    {selectedMaster && (
                      <MasterSeal text={Array.from(selectedMaster.name_zh).slice(0, 2).join("")} size={18} />
                    )}
                    <span>{selectedMaster ? selectedMaster.name_zh : t("chat.general_assistant")}</span>
                    <DownOutlined style={{ fontSize: 10 }} />
                  </Button>
                </Tooltip>
                <ChatModelSelector value={modelId} onChange={handleModelChange} />
```

- [ ] **Step 7: disclaimer 移到输入框之后**

在输入区的 `.chat-input-shell` 那个 `</div>` 之后、Task 5 插入的卡片块**之前**插入：

```tsx
              {selectedMaster && (
                <div className="mg-disclaimer" style={{ marginTop: 8 }}>
                  {t("chat.master_disclaimer")}
                </div>
              )}
```

改完后输入区包裹层的子节点槽位为：`0` 游客保存提示 Alert（条件）、`1` `DraggableModal`（恒定）、`2` 配额 Alert（条件）、`3` **`.chat-input-shell`（恒定）**、`4` `.mg-disclaimer`（条件）、`5` 卡片 fragment（条件）。`.chat-input-shell` 恒定停在槽位 3。

- [ ] **Step 8: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  6 passed (6)`

- [ ] **Step 9: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。

- [ ] **Step 10: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): 宗风整行收进输入框工具栏，保留文字标签"
```

---

### Task 7: D8 — Key 状态行沉到侧栏底部

会话列表本就是 `flex: 1`，把 Key 行排在它后面即自然沉底。桌面侧栏与移动抽屉同步改。

已知边界（接受，不处理）：零会话的用户会看到该按钮孤零零钉在约 670px 高的空侧栏底部 —— ChatGPT 的账号行同理。

**Files:**
- Modify: `frontend/src/pages/ChatPage.tsx:1144-1177`（移动抽屉）、`:1201-1248`（桌面侧栏）
- Modify: `frontend/src/styles/global.css`
- Test: `frontend/src/pages/ChatPage.test.tsx`

**Interfaces:**
- Consumes: 已有的 `keyStatus`、`sidebarCollapsed`、`navigate`
- Produces: CSS 类 `.chat-sidebar-foot`；DOM 类 `.chat-session-list`

- [ ] **Step 1: 写失败测试**

追加：

```tsx
  it("D8: Key 状态行排在会话列表之后（沉到侧栏底部）", async () => {
    const { container } = await renderEmpty();
    const list = container.querySelector(".chat-session-list");
    const foot = container.querySelector(".chat-sidebar-foot");
    expect(list).not.toBeNull();
    expect(foot).not.toBeNull();
    expect(list!.compareDocumentPosition(foot!) & FOLLOWING).toBeTruthy();
  });
```

移动抽屉在 `sidebarOpen === false` 时不渲染，所以 `querySelector` 命中的是桌面侧栏那一对。

- [ ] **Step 2: 跑测试确认为红**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: FAIL —— `AssertionError: expected null not to be null`

- [ ] **Step 3: 加 CSS**

在 `global.css` 的 `.chat-lineage-btn` 规则之后追加：

```css
/* Key 状态行沉到侧栏底部（会话列表是 flex:1，排它后面即到底） */
.chat-sidebar-foot {
  flex-shrink: 0;
  border-top: 1px solid var(--fj-border);
  padding-top: 6px;
}
```

- [ ] **Step 4: 改桌面侧栏**

删除紧跟在「新对话」`Tooltip` 之后的这一块：

```tsx
          {!sidebarCollapsed && <Button icon={<SettingOutlined />} block type="text" size="small"
            style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
            onClick={() => navigate("/profile?tab=apikey")}>
            {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
          </Button>}
```

给会话列表容器加类，把：

```tsx
          {!sidebarCollapsed && <div style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
```

改为：

```tsx
          {!sidebarCollapsed && <div className="chat-session-list" style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
```

在会话列表那个 `</div>}` 之后、闭合侧栏 `</div>}` 之前插入：

```tsx
          {!sidebarCollapsed && (
            <div className="chat-sidebar-foot">
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => navigate("/profile?tab=apikey")}>
                {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
              </Button>
            </div>
          )}
```

侧栏折叠（48px）时该按钮本来就不渲染，行为不变。

- [ ] **Step 5: 改移动抽屉**

删除紧跟在抽屉「新对话」按钮之后的这一块：

```tsx
              <Button icon={<SettingOutlined />} block type="text" size="small"
                style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                onClick={() => { navigate("/profile?tab=apikey"); setSidebarOpen(false); }}>
                {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
              </Button>
```

把抽屉的列表容器：

```tsx
              <div style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
```

改为：

```tsx
              <div className="chat-session-list" style={{ flex: 1, overflow: "auto", marginTop: 8 }}>
```

在该列表 `</div>` 之后、闭合 `.chat-sidebar-drawer` 之前插入：

```tsx
              <div className="chat-sidebar-foot">
                <Button icon={<SettingOutlined />} block type="text" size="small"
                  style={{ color: "var(--fj-ink-muted)", fontSize: 12 }}
                  onClick={() => { navigate("/profile?tab=apikey"); setSidebarOpen(false); }}>
                  {keyStatus?.has_api_key ? `${t("chat.key_configured")} (${keyStatus.provider})` : t("chat.configure_key")}
                </Button>
              </div>
```

- [ ] **Step 6: 跑测试确认为绿**

```bash
cd frontend && npx vitest run src/pages/ChatPage.test.tsx
```

Expected: `Tests  7 passed (7)`

- [ ] **Step 7: 跑全部门禁**

```bash
cd frontend && npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: 全部通过。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/pages/ChatPage.tsx frontend/src/styles/global.css frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): Key 状态行沉到侧栏底部"
```

---

### Task 8: D9 — 删除失去引用的 .mg-head* CSS，并做真机目视验收

**Files:**
- Modify: `frontend/src/styles/master-gallery.css:255-288`

**Interfaces:**
- Consumes: Task 6 已删除 `.mg-head` 的全部 JSX 用法
- Produces: 无

- [ ] **Step 1: 确认零引用**

```bash
cd frontend && grep -rn "mg-head" src/ ; echo "exit=$?"
```

Expected: 只在 `src/styles/master-gallery.css` 里命中（5 条规则）。若 `src/pages/ChatPage.tsx` 仍有命中，说明 Task 6 没做干净，先回去补。

- [ ] **Step 2: 删掉五条规则**

删除 `frontend/src/styles/master-gallery.css` 中从注释 `/* ── Persona header, shown above the thread once a lineage is chosen ── */` 起、到 `.mg-head-swap { … }` 结束为止的整段（`.mg-head` / `.mg-head-id` / `.mg-head-name` / `.mg-head-sub` / `.mg-head-swap`，约 30 行）。

**保留** 紧随其后的 `.mg-disclaimer`（含其上的注释 `/* The disclaimer is not fine print — it is the fuse on the whole persona idea. */`）—— Task 6 把它移了位置但仍在用。

- [ ] **Step 3: 复验零引用与门禁**

```bash
cd frontend && grep -rn "mg-head" src/ ; echo "--- 上面应无输出 ---"
grep -rn "mg-disclaimer" src/    # 应命中 ChatPage.tsx 与 master-gallery.css 各一处
npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build
```

Expected: `mg-head` 无命中；`mg-disclaimer` 两处命中；五道门禁全绿。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/styles/master-gallery.css
git commit -m "refactor(chat): 删除 .mg-head* 五条失去引用的 CSS 规则"
```

- [ ] **Step 5: 真机目视验收（不可跳过）**

```bash
cd frontend && npm run dev
```

在**真实 Chrome** 里打开 `http://localhost:5173/chat`，逐格看下表。单测覆盖的是 DOM 结构，**看不到布局**；下面每一格都必须用眼睛确认。

| # | 状态 | 要确认的事 |
|---|---|---|
| 1 | 1905 宽 · 已登录 · 空状态 | 侧栏贴到距视口 32px（与顶栏「佛津」字标对齐）；标题+输入框+卡片一组落在视觉中心；标题与输入框之间无横线、无空洞 |
| 2 | 1905 宽 · 游客 · 空状态 | 无侧栏，整组仍居中 |
| 3 | 1905 宽 · 有对话 | 消息气泡、引用链接、信任标记、参考经文 chip 与改动前一致；输入区顶部横线**回来了** |
| 4 | 1280 宽 · 引文面板开 | 三栏不重叠、不横向溢出。对话列约 380px 偏窄是现状问题（今天 348px），本次不处理 |
| 5 | 1905 宽 · 引文面板开 | 对话列仍居中，面板可拖拽改宽 |
| 6 | 768 宽 | 侧栏隐藏、「☰ 会话列表」出现；卡片仍两列 |
| 7 | 375 宽 | 卡片单列；工具栏应为 `＋ 通用助手▾ DeepSeek V4 Pro▾` / `发送` **两行**（草稿已验证，此处复核）。若顶成三行，改 `ChatModelSelector` 在 ≤480px 下的标签，**不动**宗风文字标签 |
| 8 | 已选祖师（点「通用助手 ▾」选慧能） | 标题上方出现印章；工具栏按钮变「慧能 ▾」带小印章；免责声明出现在输入框**下方** |
| 9 | 侧栏折叠（点折叠图标） | 48px 窄栏正常，Key 行不渲染 |
| 10 | 深色主题（顶栏切换） | 新增的卡片/宗风按钮/侧栏底部分隔线在深色下都可读 |
| 11 | 矮窗口（把窗口拖到约 600px 高）· 空状态 | 上下撑高块压到 0，标题仍从滚动区顶部开始、可读可滚 |
| 12 | **有对话且消息多到出现滚动条** | 消息区的居中列与输入区的居中列**左右边缘是否对齐**。三个 `.chat-column-inner` 是独立节点，消息区那个在滚动容器内 —— 滚动条出现时该容器少约 15px 可用宽度，840 居中列会相对偏左约 7.5px。Task 2 审查已指出此风险 |

**第 12 格的实测结论（2026-07-30）**：偏移真实存在（实测消息区 `left=643` vs 头部/输入区 `left=651`），**判定可接受、不改结构**。可见性低的原因不是「被 `padding: 0 16px` 吸收」—— padding 吸收不了位移，它只把两边同时内缩；真实效果是消息块相对输入框的内缩由 16/16 变成 8.5/23.5，引入了约 15px 的左右不对称。判定可接受的理由是：左右两侧的参照物不同侧也不同类（左边是助手头像圆圈的左缘，右边是用户气泡的右缘，二者从不在同一视线上比较），且 15px 在 840 列上只占 1.8%。

若日后判定需要修：**不要用 `scrollbar-gutter: stable`** —— 它只在滚动条一侧预留槽，会把偶发的 7.5px 偏移变成**恒定存在**的偏移，把可见的偶发问题换成不可见的永久问题。正确的两个选项是：(a) `scrollbar-gutter: stable both-edges`（两侧对称预留 → 居中列根本不移，但会吃掉 30px 列宽，<900px 视口需 media query 收口）；(b) 三个包裹层合成一个，把 840 上限提到对话列本身。

- [ ] **Step 6: 回归验证 Tab 轮播（单测覆盖不到）**

这是 D3 唯一真正想防住的失效模式，依赖真实 textarea 的原生 keydown，jsdom 测不到：

1. 空状态下，光标放进输入框（**不要打字**），连按 `Tab` 三次 —— placeholder 里的建议问题应逐条轮换。
2. 随便发一条消息，等回答完成。
3. 清空输入框，再连按 `Tab` 三次 —— **建议问题必须仍然轮换**。

若第 3 步不轮换了，说明 TextArea 被 remount、原生监听掉了。

> **实施后修订（终审纠正）**：
>
> 1. **「插到输入区之前会让槽位位移」在机制上是错的。** JSX 字面量子节点的 `createElement` 实参个数在编译期固定，`false` 槽位仍占据数组下标；React 的 `mapRemainingChildren` 按 `key ?? fiber.index` 建映射，下标不变即命中复用。**没有任何运行时状态迁移能让它位移。** 实测印证：把撑高块挪到输入区之前，节点同一性测试仍然通过。真正需要防的是别人日后给 `.chat-input-shell` 加上随状态变化的 `key`、或把它挪进条件分支的不同子树。
> 2. **这条手工回归不足以证伪 remount。** `tabSuggestions` 在助手回答带出 `[追问]` 后必然换引用 → effect 重跑 → 监听重挂，所以即便真发生了 remount，「发一条消息、等回答完成、再按 Tab」也会通过。真正的失效窗口是「已发出但 follow-up 还没到」。
> 3. **守这条论点的是自动化测试**：`ChatPage.test.tsx` 的「D3 承重点」用例断言空态→有对话前后 `textarea` 是同一个 DOM 节点，已用「给 shell 加随状态变化的 key」探针实测能红。手工 Tab 回归仍值得做（它验的是端到端可用性），但不要把它当作 remount 的判据。

- [ ] **Step 7: 推分支并开 PR**

```bash
cd /home/lqsxi/projects/fojin
git push -u origin feat/chat-first-screen-layout
gh pr create --base master \
  --title "feat(chat): /chat 首屏布局紧凑化" \
  --body "$(cat <<'EOF'
## 做了什么

消除 `/chat` 首屏左侧 371px 死白与中间 162px 竖向空洞，空状态收成「标题 + 输入框 + 建议」一组并落在视觉中心。

设计与实测依据见 `docs/superpowers/specs/2026-07-30-chat-first-screen-layout-design.md`。

## 实测对比（1905×900 空状态）

| | 左侧留白 | 右侧留白 | 竖向空洞 | 首屏这组的竖向中心 |
|---|---|---|---|---|
| 改前 | 403px | 403px | 162px | 偏上 165px |
| 改后 | 32px | 415px | 16px | 偏下 13px |

侧栏左移 371px，对话列基本原地不动（右侧 403→415），可读行宽不退化。

## 不在本次范围

- 消息气泡形态、引用链接、信任标记、参考经文 chip
- 输入框 placeholder 的建议词轮播与 `⇥ Tab` 提示
- 1280px 开引文面板时对话列偏窄（改前 348px / 改后 380px，是现状问题）

## 验证

- 五道 CI 门禁全绿
- 新增 `ChatPage.test.tsx` 7 条结构断言（其中 6 条已实测在改动前为红）
- 真机 Chrome 11 格目视矩阵 + Tab 轮播回归
EOF
)"
```

---

## 自查

**Spec 覆盖**：D1→Task 2 · D2→Task 2 · D3→Task 3 · D4→Task 3 · D5→Task 4 · D6→Task 5 · D7→Task 6 · D8→Task 7 · D9→Task 8。spec 的「验证」章节 → Task 8 Step 5/6 的目视矩阵与 Tab 回归；spec 的「风险」章节四条 → 分别落在 Task 3 Step 5 的槽位说明、Task 3 Step 3 的 CSS 注释、Task 8 Step 5 第 7 格、Task 2 Step 6 的「不加在滚动容器本身」。

**类型/命名一致性**：`.chat-column-inner`（Task 2 建，Task 3 叠加）· `.chat-msgs-empty` / `.chat-hero-lead` / `.chat-hero-trail`（Task 3）· `.chat-hero-cards` / `.chat-hero-card` / `.chat-hero-card-tag`（Task 5）· `.chat-lineage-btn`（Task 6 建，Task 6 测）· `.chat-session-list` / `.chat-sidebar-foot`（Task 7）。测试辅助 `renderEmpty()` 在 Task 1 定义、Task 2–7 引用；`FOLLOWING` 在 Task 5 定义、Task 7 复用 —— **常量必须在第一个引用它的任务里声明**，本仓 `noUnusedLocals: true` 且 CI 用 `--max-warnings 0`，提前声明会挂门禁（Task 1 首次派活即因此 BLOCKED）。

**新增 i18n 键**：0。用到的 13 个 `chat.*` 键已逐一核对存在于 `zh` locale。
