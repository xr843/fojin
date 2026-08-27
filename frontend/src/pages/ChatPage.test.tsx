import { readFileSync } from "fs";
import { resolve } from "path";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, useLocation } from "react-router";
import { message } from "antd";
import ChatPage from "./ChatPage";
import { markSessionExpired, useAuthStore } from "../stores/authStore";
import { uploadChatAttachment } from "../api/chatAttachments";
import {
  getApiKeyStatus,
  getChatQuota,
  getChatSessions,
  getHotQuestions,
  getMasters,
  getRandomHotQuestions,
  getChatSessionMessages,
  sendChatMessageStream,
  updateChatSession,
  deleteChatSession,
  type ChatSessionItem,
} from "../api/client";
import type { ChatSessionId, TextId } from "../types/branded";

// 只替换 message，其余 antd 组件保持真实。
// 为什么不能靠"页面上有没有出现错误文案"来断言：antd v5 的静态 message 在
// React 19 下要靠入口处那个 v5-patch 才生效，而测试不走入口 —— 于是 message.error
// 在 jsdom 里是无声的，用 queryByText 断言会永远为真（实测变异打不红）。
vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return {
    ...actual,
    message: { ...actual.message, error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  };
});

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
    updateChatSession: vi.fn(),
    updateChatMessageFeedback: vi.fn(),
    getChunkContext: vi.fn(),
  };
});

vi.mock("../api/chatAttachments", () => ({
  uploadChatAttachment: vi.fn(),
}));

// ChatModelSelector 挂在每个 ChatPage 里，不 mock 的话它会在 jsdom 里真发
// XHR → Network Error → 异步 console.error。日志落在环境拆除之后就是 CI 那个
// 「Closing rpc while onUserConsoleLog was pending」的 EnvironmentTeardownError
// —— 389/389 全绿仍 exit 1（2026-08-06 实锤一次）。
vi.mock("../api/chatModels", () => ({
  fetchChatModels: vi.fn().mockResolvedValue([
    {
      id: "deepseek-v4-pro", provider: "deepseek", label: "DeepSeek V4 Pro",
      description: "", vision: false, available: true, requires_byok: false,
    },
  ]),
}));

// jsdom 没有实现 scrollIntoView —— ChatPage 的自动跟随会真的调它。
beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {};
  }
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

/** 把当前 URL 渲染出来，好断言跳转目标 —— 比 mock useNavigate 更接近真实。 */
function LocationProbe() {
  const loc = useLocation();
  return <span data-testid="loc">{loc.pathname + loc.search}</span>;
}

function renderPage(entry = "/chat", injected?: QueryClient) {
  // 默认客户端的 staleTime 是 0（任何情况都会重取）。要复现「缓存活过登录」
  // 这类缺陷，必须由用例注入一个带生产 staleTime 的客户端。
  const client = injected ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
          <LocationProbe />
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
    limit: 10, used: 0, remaining: 10, has_byok: true, authenticated: true,
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
  // 侧栏收起状态持久化在 localStorage —— 不清的话它会泄漏到后面的用例里
  localStorage.removeItem("fojin.chat.sidebarCollapsed");
  // 会话过期标记同理：留着会让后面每个用例都以为登录态刚死掉
  sessionStorage.clear();
});

/** 等空状态首屏就绪（建议卡片到位）后再断言结构。 */
async function renderEmpty() {
  const r = renderPage();
  await waitFor(() => {
    expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument();
  });
  return r;
}

const FOLLOWING = 4; // Node.DOCUMENT_POSITION_FOLLOWING
const CONTAINED_BY = 16; // Node.DOCUMENT_POSITION_CONTAINED_BY

describe("ChatPage 首屏结构", () => {
  // 外壳高度曾写死 calc(100vh - 120px)，而布局铬实际 150px：文档比视口高 30px，
  // 发送后自动贴底把导航栏滚出视口。高度必须由 global.css 的 .chat-shell 按 token
  // 计算，内联样式不许再给一个数字。
  it("对话外壳不再内联写死高度（交给 .chat-shell 的 token 计算）", async () => {
    const { container } = await renderEmpty();
    const shell = container.querySelector(".chat-shell") as HTMLElement;
    expect(shell).not.toBeNull();
    expect(shell.style.height).toBe("");
  });

  // 手机空态：外壳锁高 + 建议卡片/横幅/输入框把消息区挤到 52px，标题在里面被裁掉
  // 下半截、副标题整个不见（2026-08-25 Playwright 390px 生产实测）。空态时给外壳打
  // 上 chat-shell--empty，≤768px 的 CSS 据此放开高度；有对话后去掉，恢复锁高钉底。
  it("空态外壳带 chat-shell--empty，发出第一条消息后去掉", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    const shell = container.querySelector(".chat-shell") as HTMLElement;
    expect(shell.classList.contains("chat-shell--empty")).toBe(true);

    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());
    expect(shell.classList.contains("chat-shell--empty")).toBe(false);
  });

  it("空状态渲染出标题与建议卡片（脚手架自检）", async () => {
    const { container } = await renderEmpty();
    expect(screen.getByText("小津 佛典问答")).toBeInTheDocument();
    expect(container.querySelector(".chat-input-shell")).not.toBeNull();
  });

  it("D1: 头部行/消息区/输入区三处各有一个 .chat-column-inner", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelectorAll(".chat-column-inner")).toHaveLength(3);
  });

  // 只断言"存在"是不够的：整个居中效果的承重点是 trail 的位置 —— 把 trail 挪进
  // 消息列，居中立刻塌掉，而存在性断言照绿。所以这里断言前后次序。
  it("D3: 撑高块一前一后夹住输入框", async () => {
    const { container } = await renderEmpty();
    const lead = container.querySelector(".chat-hero-lead");
    const trail = container.querySelector(".chat-hero-trail");
    const shell = container.querySelector(".chat-input-shell");
    expect(lead).not.toBeNull();
    expect(trail).not.toBeNull();
    expect(lead!.compareDocumentPosition(shell!) & FOLLOWING).toBeTruthy();
    expect(shell!.compareDocumentPosition(trail!) & FOLLOWING).toBeTruthy();
  });

  // 设计的核心论点：`{cond && <X/>}` 占住稳定槽位，所以空态→有对话时输入框不会
  // remount。若它 remount，ChatPage 里那个拦 Tab 键的 effect（依赖数组不含 textarea
  // 元素本身）不会重挂，Tab 轮播会静默失效 —— 门禁与其余断言全都看不出来。
  // 这里直接锁节点同一性，是唯一能证伪 remount 的断言。
  it("D3 承重点: 空态→有对话，输入框不 remount", async () => {
    const { container } = await renderEmpty();
    const ta = container.querySelector("textarea");
    expect(ta).not.toBeNull();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => {
      expect(container.querySelector(".chat-hero-cards")).toBeNull();
    });
    expect(container.querySelector("textarea")).toBe(ta);
  });

  it("D5: 未选祖师时首屏不放机器人图标", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelectorAll(".anticon-robot")).toHaveLength(0);
  });

  it("D6: 建议卡片在输入区内，且排在输入框之后", async () => {
    const { container } = await renderEmpty();
    const shell = container.querySelector(".chat-input-shell");
    const cards = container.querySelector(".chat-hero-cards");
    expect(shell).not.toBeNull();
    expect(cards).not.toBeNull();
    const rel = shell!.compareDocumentPosition(cards!);
    expect(rel & FOLLOWING).toBeTruthy();
    // 必须是 shell 的兄弟而非后代 —— 后代同样满足 FOLLOWING（返回 20），
    // 只查 FOLLOWING 会把「卡片塞进输入框内部」也判为通过。
    expect(rel & CONTAINED_BY).toBeFalsy();
  });

  it("D7: 宗风控件在输入框工具栏内，且 .mg-head 整行已移除", async () => {
    const { container } = await renderEmpty();
    expect(container.querySelector(".mg-head")).toBeNull();
    const toolbar = container.querySelector(".chat-input-toolbar");
    expect(toolbar).not.toBeNull();
    expect(toolbar!.querySelector(".chat-lineage-btn")).not.toBeNull();
  });

  it("D8: Key 状态行排在会话列表之后（沉到侧栏底部）", async () => {
    const { container } = await renderEmpty();
    const list = container.querySelector(".chat-session-list");
    const foot = container.querySelector(".chat-sidebar-foot");
    expect(list).not.toBeNull();
    expect(foot).not.toBeNull();
    expect(list!.compareDocumentPosition(foot!) & FOLLOWING).toBeTruthy();
  });

  // P1 的承重约束。THINKING_SENTINEL 是按身份比较的哨兵：onDone 里「流结束但
  // 从未收到 token → 转失败哨兵」的兜底靠它。若实现把检索到的经名写进 content，
  // 那条兜底失效，用户会永远卡在假的「正在检索…」上且没有重试按钮。
  it("P1 承重点: retrieved 事件只写 retrieval 字段，不动 content", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onRetrieved?.({ count: 5, titles: ["般若波罗蜜多心经", "大智度论"] });

    await waitFor(() => {
      expect(screen.getByText(/已检索 5 部经典/)).toBeInTheDocument();
    });
    // .chat-thinking 只在 m.content === THINKING_SENTINEL（按值全等）时渲染，
    // 所以任何把经名写进 content 的实现 —— 覆盖、前置、追加都一样 —— 都会让这条红。
    expect(container.querySelector(".chat-thinking")).not.toBeNull();
  });

  // 等待期先给原文：首字前常等 30–180 秒，而检索 2–3 秒就完成了。retrieved.refs
  // 渲染成可点 chip，点开即引文抽屉 —— 用户等答案的同时先读经。承重约束不变：
  // refs 只进 retrieval 字段，content 仍是哨兵；m.sources 仍为 null（不喂
  // injectCitationLinks，否则会在残缺的流式文本上改写经名）。
  it("等待期: retrieved.refs 渲染成可点 chip，点开引文抽屉，content 仍是哨兵", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onRetrieved?.({
      count: 5,
      titles: ["般若波羅蜜多心經", "大智度論"],
      refs: [
        { text_id: 9, juan_num: 1, chunk_index: 3, title_zh: "般若波羅蜜多心經" },
        { text_id: 1509, juan_num: 43, chunk_index: 12, title_zh: "大智度論" },
      ],
    });

    const chip = await screen.findByRole("button", { name: /般若波罗蜜多心经/ });
    expect(container.querySelector(".chat-thinking")).not.toBeNull();
    expect(container.querySelector(".chat-thinking")!.contains(chip)).toBe(true);

    fireEvent.click(chip);
    await waitFor(() => {
      expect(container.querySelector(".chat-citation-panel")).not.toBeNull();
    });
    // 哨兵未被顶掉；参考经文行（依赖 m.sources）此时不该出现
    expect(container.querySelector(".chat-thinking")).not.toBeNull();
    expect(screen.queryByText("参考经文")).toBeNull();
  });

  // 旧后端副本（滚动部署期间）不带 refs：退回纯文本经名，不能因为 refs 缺席而不显示。
  it("等待期: 没有 refs 时仍显示纯文本经名", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onRetrieved?.({ count: 2, titles: ["般若波羅蜜多心經"] });
    await waitFor(() => {
      expect(screen.getByText(/已检索 2 部经典/)).toBeInTheDocument();
    });
    expect(screen.getByText(/般若波羅蜜多心經/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /般若波羅蜜多心經/ })).toBeNull();
  });

  // 上一条验的是症状（哨兵没被顶掉），这一条验真正的后果：哨兵一旦被改写，
  // onDone 里「流结束却从未收到 token → 转失败哨兵」的兜底就失效，用户会永远
  // 卡在假的「正在检索…」上、且没有重试按钮。这条不依赖 .chat-thinking 这个
  // class 名活着，是两条里更耐久的那条。
  it("P1 承重点: retrieved 之后空完成，仍能落到失败兜底", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onRetrieved?.({ count: 5, titles: ["般若波罗蜜多心经"] });
    cb!.onDone();   // 一个 token 都没来就结束 —— 兜底必须接住

    await waitFor(() => {
      expect(screen.getByText("请求失败，请重试")).toBeInTheDocument();
    });
  });

  // 响应耗时必须在**登录用户**身上也成立。这是它上线当天就挂掉的地方：
  // 后端在 done 之前先发 message_id（chat.py:1356 → :1361），onMessageId 把消息 id
  // 从 Date.now() 占位符换成真实的 chat_messages.id；而 onDone 里仍按占位符去找那条
  // 消息，于是再也匹配不上，耗时一个字都没写进去。
  //
  // 游客不落库、收不到 message_id，id 一直是占位符 —— 所以以游客身份怎么试都是好的。
  // 这条用例的关键就是**先发 message_id 再发 done**，复刻登录用户的真实顺序。
  it("响应耗时: message_id 换过 id 之后，onDone 仍要把耗时记到那条消息上", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onToken("《药师经》以东方净琉璃世界为依报。");
    cb!.onMessageId?.(31337);   // ← 登录用户才有的这一步
    cb!.onDone();

    await waitFor(() => {
      expect(screen.getByText(/共 \d/)).toBeInTheDocument();
    });
  });

  // 可点引文 / 「引用已校验」/ 「参考经文」必须在**登录用户**流结束时就在，而不是刷新后。
  // 生产实锤（2026-08-25，会话 2987 + 直读 SSE 复核）：trust_status → sources →
  // message_id → done 四帧落在同一个 XHR chunk、同一个同步 tick 里到达。onSources /
  // onTrustStatus 的 setMessages updater 是延后执行的，执行时才读 liveAssistantId，
  // 而 onMessageId 已在同一 tick 把它改成真 id —— updater 去找一个此刻还不存在的
  // id，sources 与 trust_status 静默丢弃；刷新后从库里读回来才有。
  //
  // 游客不落库、不发 message_id，活变量永不改名 —— 以游客身份怎么试都是好的。
  // 这条用例的关键是四帧**同步连发**（中间不 await），复刻真实到达顺序与时序。
  it("引文/信任行/参考经文: 与 message_id 同一 tick 到达时不得丢失", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    // 最后一批 token 与收尾四帧同一个 chunk —— 先来一个 token，让 fiber 带着
    // 未渲染的更新，后面的 updater 才会像生产那样被真正延后。
    cb!.onToken("「應無所住而生其心」出自【《金剛般若波羅蜜經》第1卷】。");
    cb!.onTrustStatus?.({
      state: "verified", citation_count: 1, source_count: 1,
      citation_mutation_count: 0, quote_mutation_count: 0, quote_checked_count: 1,
    });
    cb!.onSources([{
      text_id: 235 as TextId, juan_num: 1, chunk_index: 3,
      chunk_text: "應無所住而生其心", score: 0.9, title_zh: "金剛般若波羅蜜經",
    }]);
    cb!.onMessageId?.(31338);   // ← 登录用户才有的这一步，改名发生在这里
    cb!.onDone();

    await waitFor(() => {
      expect(screen.getByText("参考经文")).toBeInTheDocument();
    });
    expect(screen.getByText(/引用已校验/)).toBeInTheDocument();
    // 内联引文（精确文案）与「参考经文」chip 各一个按钮，两者都要在。
    expect(screen.getByRole("button", { name: "【《金刚般若波罗蜜经》第1卷】" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /金刚般若波罗蜜经/ })).toHaveLength(2);
  });

  // 推理进度：把此前被丢弃的 reasoning 增量用作「仍在推进」的实证。
  // 与 retrieved 同一条承重约束 —— 只写独立字段，绝不碰 content（哨兵一旦被顶掉，
  // onDone 的空回复兜底就失效）。
  it("推理进度: reasoning 事件换掉静态文案，且 content 仍是哨兵", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onReasoning?.({ chars: 1820 });

    await waitFor(() => {
      expect(screen.getByText(/正在推敲经文/)).toBeInTheDocument();
    });
    // 哨兵未被顶掉 —— .chat-thinking 只在 content === THINKING_SENTINEL 时渲染
    expect(container.querySelector(".chat-thinking")).not.toBeNull();
  });

  // 思考过程片段：等待期显示推理文本活窗。两条承重不变式：
  //   1. 文本只进等待区（.chat-reasoning-excerpt），content 仍是哨兵；
  //   2. 首个 token 一到，整块销毁 —— 被模型自己推翻的中间结论不能留在屏幕上，
  //      更不能混进答案正文。
  it("思考片段: reasoning.text 显示在等待区，首个 token 到达后整块销毁", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    const { container } = await renderEmpty();
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    // 放掉发送时 scrollToBottom(true) 的 100ms 定时器，再清零计数 —— 下面要
    // 单独断言「reasoning 事件本身触发跟滚」。
    await new Promise((r) => setTimeout(r, 150));
    const scrollSpy = vi.spyOn(Element.prototype, "scrollIntoView");
    scrollSpy.mockClear();

    cb!.onReasoning?.({ chars: 9, text: "先查《心經》的出處，" });
    cb!.onReasoning?.({ chars: 21, text: "再對比《大般若經》。" });

    await waitFor(() => {
      expect(container.querySelector(".chat-reasoning-excerpt")).not.toBeNull();
    });
    // 活窗把气泡撑高 ~100px，而钉底发生在发送时 —— reasoning 必须自己跟滚，
    // 否则已可滚动的对话里活窗整段等待期落在折叠线以下（对抗审查实锤）。
    // jsdom 测不到布局，这里锁的是「跟滚被触发」这个行为本身。
    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
    scrollSpy.mockRestore();
    // 两帧文本按序拼接、由打字机逐字吐出（约 33ms/字，20 字 ≈ 0.7s，放宽超时）
    await waitFor(
      () =>
        expect(container.querySelector(".chat-reasoning-excerpt")!.textContent)
          .toContain("先查《心經》的出處，再對比《大般若經》。"),
      { timeout: 3000 },
    );
    // content 仍是哨兵（等待 UI 还在）
    expect(container.querySelector(".chat-thinking")).not.toBeNull();

    cb!.onToken?.("「色不異空」出自《心經》。");

    await waitFor(() => {
      // 正文一到，思考片段整块销毁
      expect(container.querySelector(".chat-reasoning-excerpt")).toBeNull();
    });
    // 推理文本绝不在答案正文里
    const bubbles = container.querySelectorAll(".chat-markdown, .markdown-body");
    const answerText = Array.from(bubbles).map((b) => b.textContent).join("");
    expect(answerText).not.toContain("先查《心經》");
    expect(screen.getByText(/色不異空/)).toBeInTheDocument();
  });

  // P0 的核心不变式，也是本轮唯一能自动挡住「存量定时器把用户拽回底部」的断言。
  // 守卫在「调用时」判过一次，但真正的 scrollIntoView 在 100ms 后才执行；若不在
  // 触发时复判，用户在流式中途上滚后，存量定时器仍会把视口拽回底部，而那次程序化
  // 滚动又会触发 scroll 事件把 atBottom 翻回真，跟随重新锁死。
  it("P0 核心不变式: 流式中途上滚后，存量定时器不再滚动", async () => {
    vi.useFakeTimers();
    try {
      let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
      vi.mocked(sendChatMessageStream).mockImplementation(
        async (_m, _s, _mid, callbacks) => { cb = callbacks; },
      );
      const spy = vi.spyOn(Element.prototype, "scrollIntoView");
      const { container } = renderPage();
      await vi.waitFor(() => {
        expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument();
      });
      fireEvent.click(container.querySelector(".chat-hero-card")!);
      await vi.waitFor(() => expect(cb).toBeDefined());

      const scroller = [...container.querySelectorAll<HTMLElement>("div")]
        .find((d) => d.style.overflow === "auto" && d.querySelector(".chat-column-inner"))!;
      // jsdom 不做布局，滚动几何全是 0 —— 手工造出「已上滚」的形状
      Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
      Object.defineProperty(scroller, "clientHeight", { value: 500, configurable: true });
      Object.defineProperty(scroller, "scrollTop", { value: 1500, writable: true, configurable: true });

      cb!.onToken("色");            // 此刻仍算在底部 → 排下一个 100ms 定时器
      scroller.scrollTop = 200;    // 用户上滚
      fireEvent.scroll(scroller);  // → atBottom 转假

      spy.mockClear();
      vi.advanceTimersByTime(300); // 让存量定时器全部触发
      expect(spy).not.toHaveBeenCalled();
      spy.mockRestore();
    } finally {
      vi.useRealTimers();
    }
  });

  // 「新对话」必须复位这对状态。否则：内容清空后 scrollTop 已是 0、不会触发
  // scroll 事件（无需 clamp），按钮会留在空首屏右下角，点了什么也不会发生。
  it("P0 边界: 点新对话后不留悬空的回到底部按钮", async () => {
    const { container } = await renderEmpty();
    const scroller = [...container.querySelectorAll<HTMLElement>("div")]
      .find((d) => d.style.overflow === "auto" && d.querySelector(".chat-column-inner"))!;
    Object.defineProperty(scroller, "scrollHeight", { value: 2000, configurable: true });
    Object.defineProperty(scroller, "clientHeight", { value: 500, configurable: true });
    Object.defineProperty(scroller, "scrollTop", { value: 200, writable: true, configurable: true });
    fireEvent.scroll(scroller);
    await waitFor(() => {
      expect(container.querySelector(".chat-jump-bottom")).not.toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: /新对话/ }));

    await waitFor(() => {
      expect(container.querySelector(".chat-jump-bottom")).toBeNull();
    });
  });
});

// ── 会话行的 ⋯ 菜单（重命名 / 置顶 / 删除）──────────────────────────────

const SESSIONS: ChatSessionItem[] = [
  { id: 11 as ChatSessionId, title: "《心经》色空怎么讲", pinned: false, created_at: new Date().toISOString() },
  { id: 12 as ChatSessionId, title: "四圣谛是哪四谛", pinned: true, created_at: new Date().toISOString() },
];

/** 渲染出会话列表，并把 ⋯ 菜单打开在第 index 行上。 */
async function openRowMenu(index: number) {
  const title = SESSIONS[index].title!;
  const r = renderPage();
  await waitFor(() => {
    expect(screen.getByText(title)).toBeInTheDocument();
  });
  const rows = r.container.querySelectorAll<HTMLElement>(".chat-session-row");
  const row = [...rows].find((el) => el.textContent?.includes(title))!;
  fireEvent.click(row.querySelector(".chat-session-more")!);
  await waitFor(() => {
    expect(screen.getByText("重命名")).toBeInTheDocument();
  });
  return { ...r, row };
}

describe("会话行 ⋯ 菜单", () => {
  beforeEach(() => {
    vi.mocked(getChatSessions).mockResolvedValue(SESSIONS);
    vi.mocked(updateChatSession).mockResolvedValue(SESSIONS[0]);
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 0, page: 1, size: 50, messages: [],
    });
    vi.mocked(deleteChatSession).mockResolvedValue(undefined);
  });

  it("菜单开出三项：重命名 / 置顶 / 删除", async () => {
    await openRowMenu(0);
    expect(screen.getByText("重命名")).toBeInTheDocument();
    expect(screen.getByText("置顶聊天")).toBeInTheDocument();
    expect(screen.getByText("删除")).toBeInTheDocument();
  });

  // antd 的 Dropdown 一个 aria 都不加（实测 role/aria-haspopup/aria-expanded 全为
  // null）。读屏软件只会念「更多操作，按钮」，既不知道它开菜单，也不知道开没开。
  it("a11y: 触发器声明自己是菜单按钮，并如实反映展开状态", async () => {
    const { row } = await openRowMenu(0);
    const btn = row.querySelector(".chat-session-more")!;
    expect(btn.tagName).toBe("BUTTON");     // span[role=button] 上 Enter 不会合成 click
    expect(btn.getAttribute("aria-haspopup")).toBe("menu");
    expect(btn.getAttribute("aria-expanded")).toBe("true");
  });

  // 鼠标点开时 antd 不把焦点移进菜单，Esc 因此没有接收者 —— 得自己在
  // document 上接。
  it("a11y: 鼠标点开的菜单，Esc 能关掉", async () => {
    const { row } = await openRowMenu(0);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => {
      expect(row.querySelector(".chat-session-more")!.getAttribute("aria-expanded")).toBe("false");
    });
  });

  // 承重点。antd 的菜单渲染进 portal，但 React 合成事件仍沿**组件树**冒泡，
  // 而 Dropdown 在组件树里就挂在会话行内部 —— 不 stopPropagation 的话，点
  // 「重命名」会同时触发整行的 onClick，把用户甩进另一个会话。DOM 上看不出来，
  // 只有断言 getChatSessionMessages 没被调用才能证伪。
  it("承重点: 点菜单项不会顺带切换会话", async () => {
    await openRowMenu(0);
    fireEvent.click(screen.getByText("重命名"));
    await screen.findByPlaceholderText("输入新的对话名称");
    expect(vi.mocked(getChatSessionMessages)).not.toHaveBeenCalled();
  });

  it("已置顶的行菜单显示「取消置顶」，且发出的是 pinned:false", async () => {
    await openRowMenu(1);
    expect(screen.queryByText("置顶聊天")).toBeNull();
    fireEvent.click(screen.getByText("取消置顶"));
    await waitFor(() => {
      expect(vi.mocked(updateChatSession)).toHaveBeenCalledWith(12, { pinned: false });
    });
  });

  it("未置顶的行发出的是 pinned:true", async () => {
    await openRowMenu(0);
    fireEvent.click(screen.getByText("置顶聊天"));
    await waitFor(() => {
      expect(vi.mocked(updateChatSession)).toHaveBeenCalledWith(11, { pinned: true });
    });
  });

  // 注意 /保\s*存/：antd 的 Button 会在恰好两个汉字之间插一个空格，
  // 无线的 /保存/ 匹配不到 —— 这是把断言写成恒假、而非恒真的那一类。
  it("重命名弹窗预填当前标题，提交时去掉首尾空白", async () => {
    await openRowMenu(0);
    fireEvent.click(screen.getByText("重命名"));
    const input = await screen.findByPlaceholderText("输入新的对话名称");
    expect((input as HTMLInputElement).value).toBe("《心经》色空怎么讲");
    fireEvent.change(input, { target: { value: "  色空章逐句读  " } });
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
    await waitFor(() => {
      expect(vi.mocked(updateChatSession)).toHaveBeenCalledWith(11, { title: "色空章逐句读" });
    });
  });

  it("标题没改动就提交不发请求（省掉一次无谓写库）", async () => {
    await openRowMenu(0);
    fireEvent.click(screen.getByText("重命名"));
    await screen.findByPlaceholderText("输入新的对话名称");
    fireEvent.click(screen.getByRole("button", { name: /保\s*存/ }));
    // 用输入框消失（destroyOnHidden 会销毁弹窗内容）判定「已关闭」——
    // 标题节点在 antd 关闭后仍留在 DOM 里，用它判定会恒假。
    // 判定「弹窗已关闭」不能等 DOM 消失：jsdom 不派发 transitionend，rc-motion
    // 的离场动画永远走不完，destroyOnHidden 也就永远不销毁内容。退场类是弹窗
    // 由开变关的第一手证据，也让下面那条 not.toHaveBeenCalled 不至于恒真
    // （若这一次点击根本没落到 onOk 上，这里就先红了）。
    await waitFor(() => {
      expect(document.querySelector(".ant-modal")?.className).toContain("ant-zoom-leave");
    });
    expect(vi.mocked(updateChatSession)).not.toHaveBeenCalled();
  });

  // 删除「正在生成回答」的那个会话，必须先中断流。不中断的话流会跑到天然结束，
  // 这期间 sending 一直为真，输入框被 `if (!msg || sending) return` 锁死 6-18 秒，
  // 而画面上什么都没有 —— 用户只会以为站坏了。
  // （这是 ⋯ 菜单之前就有的老问题，删除入口本来就挂在同一行上。）
  it("承重点: 删除正在流式生成的当前会话，会中断请求", async () => {
    let signal: AbortSignal | undefined;
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks, options) => {
        cb = callbacks;
        signal = options?.signal;      // 流不结束，模拟"正在生成"
      },
    );
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText(SESSIONS[0].title!)).toBeInTheDocument());

    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());
    cb!.onSessionId(SESSIONS[0].id);   // 后端回传：当前活动会话 = 11
    await waitFor(() => expect(signal).toBeDefined());
    expect(signal!.aborted).toBe(false);

    const row = [...container.querySelectorAll<HTMLElement>(".chat-session-row")]
      .find((el) => el.textContent?.includes(SESSIONS[0].title!))!;
    fireEvent.click(row.querySelector(".chat-session-more")!);
    await waitFor(() => expect(screen.getByText("删除")).toBeInTheDocument());
    fireEvent.click(screen.getByText("删除"));
    // Modal.confirm 的确认键；antd 会在两个汉字间插空格
    const ok = await screen.findByRole("button", { name: /删\s*除/ });
    fireEvent.click(ok);

    await waitFor(() => {
      expect(signal!.aborted).toBe(true);
    });
  });

  // 置顶的会话必须从日期分组里**移走**，不是同时出现在两处 —— 后者会让同一个
  // 会话渲染两次并撞 React key。
  it("置顶会话只出现一次，且在「已置顶」组里", async () => {
    const { container } = renderPage();
    await waitFor(() => {
      expect(screen.getByText("四圣谛是哪四谛")).toBeInTheDocument();
    });
    expect(screen.getAllByText("四圣谛是哪四谛")).toHaveLength(1);

    const list = container.querySelector(".chat-session-list")!;
    const labels = [...list.querySelectorAll("div")]
      .filter((d) => ["已置顶", "今天"].includes(d.textContent?.trim() ?? ""))
      .map((d) => d.textContent!.trim());
    expect(labels[0]).toBe("已置顶");

    const pinnedRow = [...container.querySelectorAll(".chat-session-row")]
      .find((el) => el.textContent?.includes("四圣谛是哪四谛"))!;
    expect(pinnedRow.querySelector(".chat-session-pin-mark")).not.toBeNull();
  });
});

// ── 收起态的图标轨（对标 ChatGPT 的窄轨）────────────────────────────────

describe("收起态图标轨", () => {
  beforeEach(() => {
    // 搜索入口与展开态的搜索框共用 `sessions.length > 5` 这个显示条件，
    // 所以这里必须给足 6 条 —— 少于 6 条时轨上本来就不该有搜索图标。
    vi.mocked(getChatSessions).mockResolvedValue(
      Array.from({ length: 6 }, (_, i) => ({
        id: (i + 1) as ChatSessionId,
        title: `会话 ${i + 1}`,
        pinned: false,
        created_at: new Date().toISOString(),
      })),
    );
  });

  // 收起态的图标轨：点搜索图标要展开侧栏**并且**把光标送进搜索框。只断言
  // "搜索框出现了"是不够的 —— 展开后还要用户自己再点一次输入框，那这个图标
  // 就只是个"展开"按钮的重复。
  it("收起态: 点搜索图标 → 展开侧栏并聚焦搜索框", async () => {
    localStorage.setItem("fojin.chat.sidebarCollapsed", "1");
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelector(".chat-sidebar[data-collapsed]")).not.toBeNull();
    });
    // 收起态不该有搜索框，只有轨上的图标
    expect(container.querySelector(".chat-sidebar input")).toBeNull();

    // findBy* 而非 getBy*：会话列表是异步查询，图标要等它落地才出现
    fireEvent.click(await screen.findByRole("button", { name: "搜索会话" }));

    await waitFor(() => {
      expect(container.querySelector(".chat-sidebar[data-collapsed]")).toBeNull();
    });
    const input = container.querySelector<HTMLInputElement>(".chat-sidebar input")!;
    expect(input).not.toBeNull();
    expect(document.activeElement).toBe(input);
  });

  // 最近聊天：与"展开侧栏"动作相同、意图不同。断言必须落在"会话列表真的露出来了"
  // 上 —— 只断言侧栏展开的话，这个按钮就算什么也不做（沿用 Tooltip 的默认行为）
  // 也可能碰巧通过。
  it("收起态: 点最近聊天 → 展开侧栏并露出会话列表", async () => {
    localStorage.setItem("fojin.chat.sidebarCollapsed", "1");
    const { container } = renderPage();
    await screen.findByRole("button", { name: "最近聊天" });
    expect(container.querySelector(".chat-session-list")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "最近聊天" }));

    await waitFor(() => {
      expect(container.querySelector(".chat-sidebar[data-collapsed]")).toBeNull();
    });
    const list = container.querySelector(".chat-session-list")!;
    expect(list).not.toBeNull();
    expect(list.querySelectorAll(".chat-session-row").length).toBe(6);
    // 收起状态要落盘，否则刷新后又缩回去
    expect(localStorage.getItem("fojin.chat.sidebarCollapsed")).toBe("0");
  });

  // 收起态原本把 Key 状态整个藏了 —— 而"有没有配 Key"直接决定问答能不能用。
  it("收起态: 轨上是五个无边框图标，Key 状态没被藏掉", async () => {
    localStorage.setItem("fojin.chat.sidebarCollapsed", "1");
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelector(".chat-sidebar[data-collapsed]")).not.toBeNull();
    });
    await screen.findByRole("button", { name: "搜索会话" });   // 等会话查询落地
    const rail = container.querySelector(".chat-sidebar")!;
    const labels = [...rail.querySelectorAll("button")].map((b) => b.getAttribute("aria-label"));
    expect(labels).toEqual(["展开侧栏", "新对话", "搜索会话", "最近聊天", "配置 API Key"]);
    // 每个都挂上了图标轨样式类（边框是靠 .chat-rail-btn 去掉的）
    expect(rail.querySelectorAll("button.chat-rail-btn")).toHaveLength(5);
  });

  // 轨上五个必须是同一套描边图标。antd 的图标是实心字形，描边粗细烘焙在字形里
  // 改不掉 —— 混用的话四个并排时轻重不一，正是要修的那个观感问题。
  it("收起态: 五个都是描边图标（无 antd 实心字形混入）", async () => {
    localStorage.setItem("fojin.chat.sidebarCollapsed", "1");
    const { container } = renderPage();
    await screen.findByRole("button", { name: "搜索会话" });
    const rail = container.querySelector(".chat-sidebar")!;

    expect([...rail.querySelectorAll("[data-rail-icon]")].map((e) => e.getAttribute("data-rail-icon")))
      .toEqual(["sidebar", "new-chat", "search", "chats", "settings"]);
    // 一个 antd 字形都不该剩下
    expect(rail.querySelectorAll(".anticon")).toHaveLength(0);
    // 描边粗细必须一致，否则并排看轻重不一
    const widths = [...rail.querySelectorAll("[data-rail-icon]")]
      .map((e) => e.getAttribute("stroke-width"));
    expect(new Set(widths).size).toBe(1);
  });

});

// ── 会话与 URL 的往返（去配 Key 再回来不丢会话）────────────────────────

describe("会话与 URL", () => {
  const SIX = Array.from({ length: 6 }, (_, i) => ({
    id: (i + 1) as ChatSessionId,
    title: `会话 ${i + 1}`,
    pinned: false,
    created_at: new Date().toISOString(),
  }));

  beforeEach(() => {
    vi.mocked(getChatSessions).mockResolvedValue(SIX);
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 1, page: 1, size: 50,
      messages: [{ id: 99, role: "user" as const, content: "色即是空怎么讲", sources: null, created_at: new Date().toISOString() }],
    });
  });

  // 承重点。sessionId 此前只是组件 state，一离开 /chat 就没了 —— 这条断言的是
  // 「带 ?s= 进来能把那个会话读回来」，也就是返回按钮真正依赖的能力。
  it("带 ?s= 进入时恢复该会话", async () => {
    renderPage("/chat?s=3");
    await waitFor(() => {
      expect(vi.mocked(getChatSessionMessages)).toHaveBeenCalledWith(3, 1, 50);
    });
    expect(await screen.findByText("色即是空怎么讲")).toBeInTheDocument();
  });

  // 旧链接（会话已删 / 本就不属于自己，后端 403/404）不该在进页面时糊一脸报错。
  it("?s= 指向打不开的会话时静默退回空白首屏", async () => {
    vi.mocked(getChatSessionMessages).mockRejectedValue(new Error("404"));
    renderPage("/chat?s=999");
    await waitFor(() => {
      expect(vi.mocked(getChatSessionMessages)).toHaveBeenCalledWith(999, 1, 50);
    });
    // 首屏建议卡片还在 = 退回了空白态
    expect(await screen.findByText("「三毒」指的是哪三种毒？")).toBeInTheDocument();
    // 打不开的 id 不该留在地址栏里
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).not.toContain("s=999");
    });
    // 「静默」必须单独断言：只查"退回了空白态"的话，实现照样弹一个错误提示也能过
    // ——这条最初就是这么写的，变异测试（忽略 silent 参数）没能打红才发现。
    expect(vi.mocked(message.error)).not.toHaveBeenCalled();
  });

  it("点开会话后 ?s= 跟着写进 URL（可收藏）", async () => {
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("会话 2")).toBeInTheDocument());
    const row = [...container.querySelectorAll<HTMLElement>(".chat-session-row")]
      .find((el) => el.textContent?.includes("会话 2"))!;
    fireEvent.click(row.querySelector("span")!);
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat?s=2");
    });
  });

  it("点新对话清掉 ?s=", async () => {
    renderPage("/chat?s=3");
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat?s=3");
    });
    fireEvent.click(screen.getByRole("button", { name: /新对话/ }));
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat");
    });
  });

  // 「配置 Key」必须把来源和会话一起带过去，否则 /profile 那边既不知道该不该显示
  // 返回按钮，也不知道该返回到哪个会话。
  it("配置 Key 跳转带上 from=chat 与当前会话", async () => {
    renderPage("/chat?s=3");
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat?s=3");
    });
    fireEvent.click(screen.getByRole("button", { name: /已配置 Key|配置 API Key/ }));
    await waitFor(() => {
      const loc = screen.getByTestId("loc").textContent!;
      expect(loc).toContain("/profile?");
      expect(loc).toContain("tab=apikey");
      expect(loc).toContain("from=chat");
      expect(loc).toContain("s=3");
    });
  });
});

// ── 额度将尽提醒（登录用户此前什么都看不到）────────────────────────────

describe("额度提醒", () => {
  function loggedIn(quota: {
    limit: number; used: number; remaining: number; has_byok: boolean; authenticated?: boolean;
  }) {
    // 默认 true：这批用例测的是「后端认得这个人」时的额度提醒。
    vi.mocked(getChatQuota).mockResolvedValue({ authenticated: true, ...quota });
    return renderPage();
  }

  // 承重点：阈值以上不该出现。常驻一个「今日剩余 197 次」是纯噪音，
  // 只断言"快用完时会显示"的话，一个无条件常显的实现照样能过。
  it("额度充足时不打扰（197/200 不提示）", async () => {
    loggedIn({ limit: 200, used: 3, remaining: 197, has_byok: false });
    await screen.findByText("「三毒」指的是哪三种毒？");
    expect(screen.queryByText(/额度快用完/)).toBeNull();
  });

  it("剩余降到阈值内时提醒（15 次）", async () => {
    loggedIn({ limit: 200, used: 185, remaining: 15, has_byok: false });
    expect(await screen.findByText(/今日免费额度快用完了，剩余 15 次/)).toBeInTheDocument();
  });

  it("剩余极少时升级为 error 级", async () => {
    const { container } = loggedIn({ limit: 200, used: 198, remaining: 2, has_byok: false });
    await screen.findByText(/剩余 2 次/);
    expect(container.querySelector(".ant-alert-error")).not.toBeNull();
  });

  // 自带 Key 的用户后端返回 remaining = -1（不限次）。若实现用 `remaining <= 20`
  // 判定，-1 会满足条件 —— 给一个根本没有限额的人弹「额度快用完」。
  it("承重点: 自带 Key（remaining 为 -1）不弹额度提醒", async () => {
    loggedIn({ limit: 200, used: 500, remaining: -1, has_byok: true });
    await screen.findByText("「三毒」指的是哪三种毒？");
    expect(screen.queryByText(/额度快用完/)).toBeNull();
  });

  // ── 用户实拍复现（2026-08-15）──────────────────────────────────────
  //
  // 症状：登录用户进入 /chat 就看到「今日免费额度快用完了，剩余 10 次」，
  // 重新登录也不消失。查库：该用户当日只用了 1 次，按登录上限 200 真实剩余
  // 199；当天全站最高用量 3 次，没有任何人接近上限。
  //
  // 机制：JWT 只有 8 小时且无续期，resolve_optional_user 对过期 token 静默
  // 返回 None，/chat/quota 于是落到匿名分支返回 limit 10。而前端的 user 存在
  // 持久化 store 里，token 过期了 user 对象还在 —— 于是用「登录用户」的横幅
  // 渲染了「游客」的数字。10 恰好是匿名满额（10-0），不是巧合。
  it("回归: token 过期时不得把游客额度当成本人余额报出去", async () => {
    // 后端此刻返回的就是匿名配额：authenticated=false，remaining=10。
    loggedIn({ limit: 10, used: 0, remaining: 10, has_byok: false, authenticated: false });
    expect(await screen.findByText(/登录状态已过期/)).toBeInTheDocument();
    // 承重断言：那句编造的余额必须消失。只断言"出现过期提示"的话，
    // 一个把两条横幅同时显示的实现照样能过。
    expect(screen.queryByText(/额度快用完/)).toBeNull();
  });

  it("回归: 过期提示只给「本地有 user」的人看，游客不该看到", async () => {
    // 游客同样拿到 authenticated=false，但他没过期——他本来就没登录过。
    useAuthStore.setState({ token: null, user: null });
    loggedIn({ limit: 10, used: 8, remaining: 2, has_byok: false, authenticated: false });
    await screen.findByText("「三毒」指的是哪三种毒？");
    expect(screen.queryByText(/登录状态已过期/)).toBeNull();
  });

  it("登录态正常时，额度提醒照常工作（不因这次修复被误伤）", async () => {
    loggedIn({ limit: 200, used: 185, remaining: 15, has_byok: false, authenticated: true });
    expect(await screen.findByText(/今日免费额度快用完了，剩余 15 次/)).toBeInTheDocument();
    expect(screen.queryByText(/登录状态已过期/)).toBeNull();
  });

  // 上一版修复漏掉的那一格：401 拦截器的处理是 logout()，user 当场被清空。
  // 只判 `user && !authenticated` 的话，横幅最多在 401 到达前闪一下 ——
  // 实测手工把 token 改坏后进 /chat，两条横幅一条都不出现。
  it("承重点: 401 已清掉 user，过期提示仍必须在", async () => {
    useAuthStore.setState({ token: null, user: null });   // 拦截器登出后的真实状态
    markSessionExpired();
    loggedIn({ limit: 10, used: 2, remaining: 8, has_byok: false, authenticated: false });
    expect(await screen.findByText(/登录状态已过期/)).toBeInTheDocument();
  });

  it("过期者不该再被劝「登录后额度更多」——他刚才就是登录状态", async () => {
    useAuthStore.setState({ token: null, user: null });
    markSessionExpired();
    loggedIn({ limit: 10, used: 2, remaining: 8, has_byok: false, authenticated: false });
    await screen.findByText(/登录状态已过期/);
    expect(screen.queryByText(/每日免费/)).toBeNull();
  });

  // 标记没有任何自愈机制：全项目只有 setAuth/logout 会清它，而 sessionStorage
  // 活得过页面重载，也活得过浏览器「恢复上次标签页」。于是一条残留标记能在一个
  // **完全有效**的会话上长期挂着假横幅，而且重新登录也未必碰得到它（比如登录
  // 发生在另一个标签页）。
  //
  // 服务端刚刚说「我认得你」（authenticated: true），本地那条「你的登录死了」
  // 到此就是被推翻的陈旧事实。新鲜的服务端真相必须压过它。
  it("承重点: 服务端说认得这个人时，残留的过期标记必须自愈", async () => {
    markSessionExpired();                       // 上一次会话死掉时留下的
    loggedIn({ limit: 200, used: 1, remaining: 199, has_byok: false, authenticated: true });
    await screen.findByText("「三毒」指的是哪三种毒？");
    expect(screen.queryByText(/登录状态已过期/)).toBeNull();
  });

  it("真游客（没置位过期标记）照旧看到常规游客提示", async () => {
    useAuthStore.setState({ token: null, user: null });
    vi.mocked(getApiKeyStatus).mockResolvedValue({
      has_api_key: false, provider: null, model: null, key_preview: null,
    });
    loggedIn({ limit: 10, used: 2, remaining: 8, has_byok: false, authenticated: false });
    expect(await screen.findByText(/每日免费/)).toBeInTheDocument();
    expect(screen.queryByText(/登录状态已过期/)).toBeNull();
  });

  // 用户原话是「即便登录后也会出现」——这一条就是那个"即便"。
  // queryKey 若是常量 ["chatQuota"]，登录前后是同一个 key，配上全局 5 分钟
  // staleTime，登录后照旧吃登录前缓存的游客额度，不会重新取。
  it("回归: 登录后必须重新取额度，不能沿用登录前的游客缓存", async () => {
    useAuthStore.setState({ token: null, user: null });
    vi.mocked(getChatQuota)
      .mockResolvedValueOnce({ limit: 10, used: 0, remaining: 10, has_byok: false, authenticated: false })
      .mockResolvedValue({ limit: 200, used: 1, remaining: 199, has_byok: false, authenticated: true });

    renderPage();
    await screen.findByText("「三毒」指的是哪三种毒？");
    const callsAsGuest = vi.mocked(getChatQuota).mock.calls.length;

    act(() => {
      useAuthStore.setState({
        token: "fresh",
        user: {
          id: 42, username: "reader", email: "r@example.com", display_name: null,
          role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
        },
      });
    });

    await waitFor(() => {
      expect(vi.mocked(getChatQuota).mock.calls.length).toBeGreaterThan(callsAsGuest);
    });
  });

  // ── 用户实拍复现（2026-08-18，user 638 / 显示名 CFFF）──────────────────
  //
  // 症状：登录成功、右上角挂着自己的名字，/chat 却顶着「登录状态已过期，当前
  // 提问按游客额度计算」。生产日志佐证她不是在瞎说：35 分钟内登录了三次
  // （08:43:30 / 08:47:29 / 08:55:12 CST），而截图那一刻（09:16:01）的 10 秒后
  // `last_active_at` 又被顶了一次 —— 那个中间件只在 `verify_token` 通过时才写库，
  // 所以她当时握着的是一张**有效**票。横幅在说谎。
  //
  // 机制：/chat/quota 对过期 token 不 401，而是 200 + `authenticated: false`
  // （#1196 有意立的契约）。这份「你是游客」的回答被缓存进 ["chatQuota", 638]。
  // 她重新登录后仍是同一个 id，**queryKey 一模一样**，5 分钟 staleTime 内直接
  // 命中缓存、不重取 —— 横幅于是活过了那次成功登录。
  //
  // #1196 把常量 key 换成带 user id，只区分得开「游客 ↔ 本人」，区分不开
  // 「本人·票已死 ↔ 本人·刚换票」。同一个人，同一个 key。
  it("回归: 同一人重新登录后，过期期间的缓存不得让过期横幅活下来", async () => {
    // ⚠️ 必须按生产值（main.tsx:23）建客户端。harness 默认 staleTime=0，
    // 任何情况都会重取 —— 这个缺陷就是这么从门禁底下溜过去的。
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 5 * 60 * 1000 } },
    });
    const READER = {
      id: 638, username: "reader", email: "r@example.com", display_name: "CFFF",
      role: "user", is_active: true, created_at: "2026-01-01T00:00:00Z",
    };

    // 阶段一：票已经死了，但本地 store 里的 user 还在（persist 存着）。
    useAuthStore.setState({ token: "dead", user: READER });
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 10, used: 0, remaining: 10, has_byok: false, authenticated: false,
    });
    const first = renderPage("/chat", client);
    expect(await screen.findByText(/登录状态已过期/)).toBeInTheDocument();
    first.unmount();

    // 阶段二：她重新登录成功，后端从此认得她。走 setAuth——真实登录路径。
    vi.mocked(getChatQuota).mockResolvedValue({
      limit: 200, used: 1, remaining: 199, has_byok: false, authenticated: true,
    });
    act(() => { useAuthStore.getState().setAuth("fresh", READER); });
    renderPage("/chat", client);

    // 承重断言：登录成功之后，这句话不能还在。
    await screen.findByText("「三毒」指的是哪三种毒？");
    expect(screen.queryByText(/登录状态已过期/)).toBeNull();
  });
});

  // ── 用户实拍录屏复现（2026-08-01）────────────────────────────────────
  //
  // 症状：重新登录后问第一个问题，回答生成到一半，整个对话突然消失、退回空白首屏，
  // 而输入区的「停止」按钮还在（说明流仍在跑）。之后的问题都正常。
  //
  // 机制：恢复 effect 的 `if (!raw) return` 早退时没有置位守卫。干净进 /chat 时
  // 守卫保持 false；等流回传 session_id、syncSessionParam 把 ?s= 写进 URL，
  // searchParams 一变，这个 effect 就把**刚写进去的那个 id** 当成"要恢复的历史
  // 会话"去拉消息 —— 而此刻助手回答还没落库，拿回空数组，setMessages 把正在流式
  // 的对话整个替换掉。
  it("回归: 流式中途写入 ?s= 不得把正在进行的对话清空", async () => {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    // 新会话此刻在后端还没有任何已落库的消息
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 0, page: 1, size: 50, messages: [],
    });

    const { container } = renderPage();          // 干净进入，URL 里没有 ?s=
    await waitFor(() => expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument());

    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());

    cb!.onSessionId(4242 as unknown as number);  // 后端回传新会话 id → 写入 ?s=
    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat?s=4242");
    });
    cb!.onToken("色即是空");

    // 给"错误的恢复"足够的时间发生（微任务 + 一次 HTTP 往返）
    await new Promise((r) => setTimeout(r, 120));

    // 对话必须还在：空白首屏的建议卡片不该回来
    expect(container.querySelector(".chat-hero-cards")).toBeNull();
    expect(container.textContent).toContain("色即是空");
    // 而且根本不该去拉这个会话的历史消息
    expect(vi.mocked(getChatSessionMessages)).not.toHaveBeenCalled();
  });

describe("导出 Markdown", () => {
  /** 抓住 handleExport 生成的那个 Blob —— jsdom 没有 createObjectURL。 */
  function captureExport() {
    const blobs: Blob[] = [];
    const createURL = vi.fn((b: Blob) => { blobs.push(b); return "blob:x"; });
    (URL as unknown as { createObjectURL: unknown }).createObjectURL = createURL;
    (URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn();
    // a.click() 在 jsdom 里会尝试导航，噪声很大且无意义。
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    return { blobs, clickSpy };
  }

  it("导出的参考经文按界面语言折字，不直出 CBETA 繁体", async () => {
    // 导出的是给人读的 .md：界面是简体，文件里却写《雜阿含經》，
    // 与用户屏幕上刚看到的 chip 对不上号。
    vi.mocked(getChatSessions).mockResolvedValue([
      { id: 7 as ChatSessionId, title: "心经问答", created_at: "2026-08-01T00:00:00Z", pinned: false },
    ] as unknown as ChatSessionItem[]);
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 2, page: 1, size: 50,
      messages: [
        { id: 1, role: "user", content: "色是什么", sources: null, created_at: "2026-08-01T00:00:00Z" },
        {
          id: 2, role: "assistant", content: "色是 rūpa。", created_at: "2026-08-01T00:00:01Z",
          sources: [{ text_id: 5, title_zh: "雜阿含經", juan_num: 16, chunk_index: 0, chunk_text: "…", score: 0.9 }],
        },
      ],
    } as never);

    const { blobs, clickSpy } = captureExport();
    try {
      renderPage("/chat?s=7");
      await waitFor(() => expect(screen.getByText(/色是 rūpa/)).toBeInTheDocument());

      fireEvent.click(screen.getByRole("button", { name: "download" }));
      await waitFor(() => expect(blobs).toHaveLength(1));

      const md = await blobs[0].text();
      expect(md).toContain("《杂阿含经》第16卷");
      expect(md).not.toContain("《雜阿含經》第16卷");
    } finally {
      clickSpy.mockRestore();
    }
  });
});

describe("断流埋点 chat_stream_error", () => {
  /** 为什么要这个埋点：中途断流在今天完全量不出来。
   *  · docker logs 里那行 "LLM stream broke mid-stream" 随每次部署重建容器而清空
   *  · 「孤儿 user 消息」查不到 —— _save_messages 把 user+assistant 两行一起写，
   *    断流时一行都不落
   *  · 「Umami chat 事件 − DB user 行」也不行 —— 游客根本不建 session、完全不落库，
   *    而游客是大多数，差值会被游客淹没
   *  只剩前端知道真相：它手里有「这一条流吐没吐过 token」。 */
  function withUmami() {
    const track = vi.fn();
    (window as Window & { umami?: { track: typeof track } }).umami = { track };
    (globalThis as unknown as { umami: unknown }).umami = { track };
    return track;
  }

  async function startSend() {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, cbs) => { cb = cbs; },
    );
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 0, page: 1, size: 50, messages: [],
    } as never);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument());
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());
    return cb!;
  }

  afterEach(() => {
    delete (window as Window & { umami?: unknown }).umami;
    delete (globalThis as unknown as { umami?: unknown }).umami;
  });

  /** 只数 chat_stream_error 这一类事件 —— 同一次发送还会打 "chat" 等其它点。 */
  const errEvents = (track: ReturnType<typeof vi.fn>) =>
    track.mock.calls.filter((c) => c[0] === "chat_stream_error").map((c) => c[1]);

  it("吐过 token 后才失败 → 记为 mid_stream，且只记一次", async () => {
    // 这一种最危险：气泡里留着一段看似完整的半截答案，没有失败标记也没有重试按钮，
    // 而分享/复制按钮照常可用 —— 截断的内容能被做成分享卡片送出去。
    //
    // onDone 必须跟着调：client.ts 里**每一处** onError 后面都紧跟 onDone()，
    // 不调就是在测一个production里不存在的时序（第一版就是这么漏掉重复计数的）。
    const track = withUmami();
    const cb = await startSend();
    cb.onToken!("「色」是梵语 rūpa 的意译，在《心经》的语境中");
    cb.onError!("上游中断", "upstream_mid_stream");
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "mid_stream", reason: "upstream_mid_stream" }]);
  });

  it("一个 token 都没到就失败 → 记为 no_token，且不被 onDone 重复计一次", async () => {
    // 承重：onError 之后 onDone 必定到达，而此时 tokenCount 仍是 0 —— 少了
    // sawError 守卫，同一次失败会同时记 no_token 和 empty_done，
    // 直接把失败率的分子灌成两倍。
    const track = withUmami();
    const cb = await startSend();
    cb.onError!("上游 503", "upstream_http_503");
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "no_token", reason: "upstream_http_503" }]);
  });

  it("流悄无声息地结束（没有 error 帧、也没有 token）→ 记为 empty_done", async () => {
    const track = withUmami();
    const cb = await startSend();
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "empty_done", reason: "silent_done" }]);
  });

  it("用户按停止 → 一个错误事件都不记", async () => {
    // 承重条。abort 和真故障走的是同一个 onError，而推理模型要 24-180 秒才吐
    // 第一个字（生产日志实测最长 182.95s），等不及手动停止是最典型的动作 ——
    // 记进去就是把用户的不耐烦算成系统断流。2026-08-05 那版 6.4% 的断流率里
    // 混的正是这一类，而当时没有任何测试拦得住。
    const track = withUmami();
    const cb = await startSend();
    cb.onError!("已取消", "cancelled");
    cb.onDone!();
    expect(errEvents(track)).toEqual([]);
  });

  it("失败后点「重试」→ chat 只计一次、chat_retry 计一次（重试不再重复灌 chat）", async () => {
    // 承重：重试走的是同一个 handleSendMessage，而它无条件打 "chat"。于是 30 天里
    // 94 次 chat_retry 每一次都把「提问数」多灌一次；而「重发率」「断流率」的分母
    // 正是 chat —— 这一条不拦住，R7 的四个 KPI 里两个都是脏的。
    const track = withUmami();
    const cb = await startSend();
    cb.onError!("上游 503", "upstream_http_503");
    cb.onDone!();
    await waitFor(() => expect(document.querySelector(".anticon-reload")).toBeTruthy());
    const retryBtn = document.querySelector(".anticon-reload")!.closest("button")!;
    const sendsBefore = vi.mocked(sendChatMessageStream).mock.calls.length;
    fireEvent.click(retryBtn);
    await waitFor(() =>
      expect(vi.mocked(sendChatMessageStream).mock.calls.length).toBe(sendsBefore + 1),
    );
    const names = track.mock.calls.map((c) => c[0]);
    expect(names.filter((n) => n === "chat")).toHaveLength(1);
    expect(names.filter((n) => n === "chat_retry")).toHaveLength(1);
  });

  it("旧后端的 error 帧没有 code 时，reason 记为 unknown 而不是丢字段", async () => {
    // 滚动部署期间前端先上、后端还是旧副本，会收到不带 code 的 error 帧。
    // 让它落进一个显式的桶，别变成 undefined —— 那样 Umami 里这一维直接消失，
    // 看上去像「这些失败没有成因」。
    const track = withUmami();
    const cb = await startSend();
    cb.onError!("抱歉，AI 服务暂时不可用");
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "no_token", reason: "unknown" }]);
  });

  it("正常完成不记任何错误事件", async () => {
    // 承重：这个埋点是要拿来算失败率的分子，成功路径漏进去就直接把分子污染了。
    const track = withUmami();
    const cb = await startSend();
    cb.onToken!("完整答案");
    cb.onDone!();
    expect(errEvents(track)).toEqual([]);
  });
});

describe("URL 上的 ?q=", () => {
  const inputOf = (c: HTMLElement) =>
    c.querySelector<HTMLTextAreaElement>(".chat-input-shell textarea")!;

  it("只有 q、没有 context 时把词填进输入框，而不是丢掉", async () => {
    // 承重条。守卫原本是 `if (!q || !context) return`，于是所有不带 context 的
    // ?q= 被静默丢弃 —— 辞典那颗「问小津」按钮 navigate 到 /chat?q=因果，用户
    // 落地看到的是一个空白对话框，词没了。这个失败没有任何报错、日志或埋点，
    // 只能靠这条断言拦住。
    const { container } = renderPage("/chat?q=%E5%9B%A0%E6%9E%9C");
    await waitFor(() => expect(inputOf(container).value).toBe("因果"));
    // 不许自动发送：这种 URL 会被收藏和分享，自动发等于每打开一次烧一次配额。
    expect(sendChatMessageStream).not.toHaveBeenCalled();
  });

  it("带 context 时仍然自动发送（阅读页「问小津」的老行为不能被改坏）", async () => {
    renderPage("/chat?q=%E8%BF%99%E6%AE%B5%E6%80%8E%E4%B9%88%E8%A7%A3&context=%E8%89%B2%E5%8D%B3%E6%98%AF%E7%A9%BA&source=%E5%BF%83%E7%BB%8F");
    await waitFor(() => expect(sendChatMessageStream).toHaveBeenCalled());
    const sent = vi.mocked(sendChatMessageStream).mock.calls[0][0];
    expect(sent).toContain("色即是空");
    expect(sent).toContain("《心经》");
  });
});

describe("空状态副标题", () => {
  it("只留「可核对」那句，不再重复卡片已经在演示的「能问什么」", async () => {
    await renderEmpty();
    // 两行原本同处一个 <div>、由 <br> 分隔，getByText 匹配不到单独的文本节点，
    // 所以对整块 hero 的 textContent 断言。
    const hero = screen.getByText("小津 佛典问答").parentElement!;

    // 差异点声明必须在：整个首屏只有这一处告诉用户答案可以被核对，
    // 而且措辞是「你可以核对」而非「我保证正确」—— 不能悄悄丢掉。
    expect(hero.textContent).toContain("答案标注经文出处，可点开核对原文");

    // 原来的第一行「可以问我关于佛经内容、佛教历史、经典翻译等问题」是第三次
    // 重复：下方四张卡片（白话翻译/经文解读/对比辨析/佛教史话）带真实例题且可点，
    // 输入框 placeholder 还在轮播真实例题。抽象地再说一遍只是噪音。
    expect(hero.textContent).not.toContain("可以问我关于");
  });
});

describe("空状态标题", () => {
  // 朱红加粗必须走 --fj-cinnabar，不能写 --fj-accent、更不能写死十六进制。
  // --fj-accent 在浅色下也是一支红，肉眼复验（默认就在浅色下做）看不出差别，
  // 但它在暗色会变亮到 #e5764a，当文字用只有 3.35:1 —— 这个错只有切主题才暴露，
  // 所以这条断言是唯一能拦住它的地方。
  it("用朱红专用色（--fj-cinnabar）加粗，而不是继承正文的灰褐色", async () => {
    const { container } = await renderEmpty();
    const title = container.querySelector(".chat-hero-title");
    expect(title).not.toBeNull();
    expect(title!.textContent).toBe("小津 佛典问答");

    const css = readFileSync(resolve(__dirname, "../styles/global.css"), "utf-8");
    const rule = css.match(/\.chat-hero-title\s*\{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/color:\s*var\(--fj-cinnabar\)/);
    expect(rule).toMatch(/font-weight:\s*(700|bold)\b/);
  });

  // 简体下这行标题换成了品牌那支毛笔体（Ma Shan Zheng），与首页 88px 的「佛津」
  // 同一支。三条不变量都是肉眼复验看不出、或只在别的 locale 才暴露的：
  //  1) 字重必须 < 600 —— Ma Shan Zheng 只有 400 一档，写 700 浏览器会合成粗体，
  //     把毛笔的提按笔锋涂成糊边（基础规则那句「700 是真字重」只对 Noto Serif SC
  //     成立，换字体就不成立了）。
  //  2) 选择器必须排除 zh-Hant —— 这支字体是 GB2312 字量，繁体「問」(U+554F) 没有
  //     字形，简化成 :lang(zh) 会让繁体标题只有「問」一个字掉回衬线，夹在毛笔字
  //     中间像渲染坏了。简体页面上永远看不到这个错。
  //  3) 这条规则不许自己写 color —— 朱红由上面的基础规则提供，在这里覆盖就绕过了
  //     上面那条 --fj-cinnabar 断言。
  it("简体用毛笔体但不合成粗体、不波及繁体、不另写颜色", () => {
    const css = readFileSync(resolve(__dirname, "../styles/global.css"), "utf-8");
    const rule = css.match(
      /\.chat-hero-title:lang\(zh\):not\(:lang\(zh-Hant\)\)\s*\{([^}]*)\}/,
    )?.[1];
    expect(rule, "毛笔体规则必须只作用于简体：.chat-hero-title:lang(zh):not(:lang(zh-Hant))").toBeDefined();
    expect(rule!).toMatch(/font-family:\s*"Ma Shan Zheng Title"/);
    expect(Number(rule!.match(/font-weight:\s*(\d+)/)?.[1])).toBeLessThan(600);
    expect(rule!).not.toMatch(/color:/);

    // 窄屏不换行：字号必须写成 clamp，且它在真机上算出来的行宽要塞得进可用宽。
    //
    // 三个常数都是量出来的，不是估的：
    //  · K = 7.2 —— 整行宽 ÷ 字号，生产浏览器实测：38px → 266.9px（比值 7.03），
    //    28px → 200.4px（7.16，比例略高是因为 letter-spacing 固定 2px 不随字号缩）。
    //    取两者里的大头再留余量。间距或字数一改，K 就要重新量 —— 下面那条断言
    //    钉住了这两个前提。
    //  · CHROME = 68 —— 移动端 .layout-content-inner 的 20px，加 ChatPage 里 hero
    //    外层那个内联 padding: 0 24px 的 48px。两者都不随视口变。
    //  · VIEWPORTS —— Umami 90 天里真实出现过的屏宽，289 是最窄的一台。
    //
    // 为什么非要这条：320px 屏只有 252px 可用（97 个真实会话），289px 屏只有
    // 221px。桌面上把字号或间距调大是一眼可见的收益，窄屏换行却要真去那个宽度
    // 下看才发现 —— 没人会去。
    const K = 7.2;
    const CHROME = 68;
    const VIEWPORTS = [289, 292, 303, 320, 360, 390, 414, 768, 1920];

    const clamp = rule!.match(
      /font-size:\s*clamp\(\s*([\d.]+)px\s*,\s*([\d.]+)vw\s*,\s*([\d.]+)px\s*\)/,
    );
    expect(
      clamp,
      "毛笔标题的 font-size 必须是 clamp(下限px, N vw, 上限px)：定值在最窄的真机上会换行",
    ).not.toBeNull();
    const [floor, vwCoef, ceil] = clamp!.slice(1).map(Number);

    for (const vw of VIEWPORTS) {
      const fs = Math.min(Math.max(floor, (vwCoef * vw) / 100), ceil);
      const lineW = K * fs;
      expect(
        lineW,
        `${vw}px 屏：字号算出 ${fs.toFixed(1)}px → 行宽 ${lineW.toFixed(0)}px，` +
          `超过可用的 ${vw - CHROME}px 就会换行（clamp ${floor}/${vwCoef}vw/${ceil}）`,
      ).toBeLessThanOrEqual(vw - CHROME);
    }
  });

  it("「津」「佛」之间的空当由 word-spacing 管，且单位是 em", () => {
    const css = readFileSync(resolve(__dirname, "../styles/global.css"), "utf-8");
    const rule = css.match(
      /\.chat-hero-title:lang\(zh\):not\(:lang\(zh-Hant\)\)\s*\{([^}]*)\}/,
    )?.[1];
    const ws = rule!.match(/word-spacing:\s*([\d.]+)(em|px|rem)/);
    expect(
      ws,
      "这行标题的字间空当是刻意调过的（半角空格只有 9.7px 太挤），必须显式写 word-spacing",
    ).not.toBeNull();
    // px 会在 clamp 的小字号那一档显得过宽 —— 字号缩了间距不缩。
    expect(ws![2], "word-spacing 必须用 em，跟着 clamp 的字号一起缩").toBe("em");

    const zh = JSON.parse(
      readFileSync(resolve(__dirname, "../../public/locales/zh/translation.json"), "utf-8"),
    );
    const title = zh["chat.title"] as string;
    // 必须是普通半角空格。曾经改成过全角 U+3000（正好一个字宽），但那条路是死的：
    // word-spacing 对它完全无效（0em 与 0.5em 实测都是 40px），因为按 CSS Text
    // 规范 U+3000 不是 word-separator —— 想再调细一点都做不到。
    expect(
      [...title].map((c) => c.codePointAt(0)!),
      `chat.title 的分隔符必须是普通空格 U+0020，否则 word-spacing 会静默失效。实际：${[...title].map((c) => "U+" + c.codePointAt(0)!.toString(16).toUpperCase()).join(" ")}`,
    ).toContain(0x20);
    // 上面那条 clamp 断言里的 K 是按「6 个汉字 + 1 个空格」量出来的，字数一变就
    // 不再成立。
    expect(title, "标题长度变了就要重新量 K（见上一条断言）").toHaveLength(7);
  });

  // 这行标题不含拉丁字母是刻意的。原文案「小津 AI 佛典问答」试过三种安置那两个
  // 字母的办法，全部失败：毛笔自带的拉丁是行书连笔，28px 下 A 和 I 连成一团；
  // Noto Serif SC 的粗衬线字母插在毛笔行里像另换了块招牌（上过线，用户一眼看出
  // 不对）；配霞鹜文楷在 76px 放大图上确有区别，到 28px 实际尺寸几乎看不出来。
  // 毛笔子集里一个拉丁字形都没有，所以文案里再出现拉丁就会静默掉回 Noto Serif
  // SC —— 视觉上是回归，测试上却毫无动静。这条断言就是那个哨兵。
  it("简体标题文案不含拉丁字母（毛笔子集里没有，加进来会静默掉回衬线）", () => {
    const zh = JSON.parse(
      readFileSync(resolve(__dirname, "../../public/locales/zh/translation.json"), "utf-8"),
    );
    // 不锁死文案本身 —— 那句由上面那条 textContent 断言盯着，这里只管「不许有
    // 拉丁」这一条规则，文案怎么改都行。写成 toBe 会抢在下面这条之前失败，
    // 把真正的原因藏起来。
    const latin = [...(zh["chat.title"] as string)].filter((c) => /[!-~]/.test(c));
    expect(
      latin,
      `毛笔子集 MaShanZheng-title-v2.woff2 只有汉字，这些字符会掉回 Noto Serif SC：${latin.join("")}`,
    ).toEqual([]);

    // 「AI」这个定位词并没有丢，只是不在招牌这一行重复。
    expect(zh["chat.page_title"]).toContain("AI");
  });
});

// 用户实测（2026-08-04）：1.3MB 的 Word 上传，界面只说「上传失败，请稍后重试」。
// 真正发生的是反向代理按 nginx 默认的 client_max_body_size=1m 挡掉了请求，
// 回了一张 **HTML** 413 错误页 —— 于是 `err.response.data.detail` 取不到，
// 前端一路掉进兜底文案，把一个「文件太大」说成了「服务出错，再试试」。
describe("附件上传失败时说的是人话", () => {
  /** 选一个 1.3MB 的 .docx —— 过得了前端 10MB 自检，会真的发出请求。 */
  function pickWordFile(container: HTMLElement, sizeBytes = 1_300_000) {
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["stub"], "读书笔记.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    // File 构造出来的 size 由内容决定，这里要的是「体积大但不占内存」。
    Object.defineProperty(file, "size", { value: sizeBytes });
    fireEvent.change(input, { target: { files: [file] } });
  }

  async function shownMessage() {
    await waitFor(() => {
      expect(vi.mocked(message.error)).toHaveBeenCalled();
    });
    return vi.mocked(message.error).mock.calls[0][0];
  }

  it("代理回 413（HTML 页面、没有 detail）时要说文件太大，不能说「稍后重试」", async () => {
    vi.mocked(uploadChatAttachment).mockRejectedValue({
      response: {
        status: 413,
        // nginx 的 413 body 就长这样：HTML，不是 JSON。
        data: "<html>\r\n<head><title>413 Request Entity Too Large</title></head>\r\n</html>\r\n",
      },
    });
    const { container } = await renderEmpty();
    pickWordFile(container);

    const shown = await shownMessage();
    expect(shown).not.toBe("上传失败，请稍后重试");
    expect(shown).toContain("10MB");
  });

  it("后端给了 detail（如 415 不支持的类型）时照原样透出，别被兜底盖掉", async () => {
    vi.mocked(uploadChatAttachment).mockRejectedValue({
      response: {
        status: 415,
        data: { detail: "暂不支持该文件类型，可上传 PDF / TXT / MD / DOCX / CSV / HTML" },
      },
    });
    const { container } = await renderEmpty();
    pickWordFile(container, 40_000);

    expect(await shownMessage()).toBe(
      "暂不支持该文件类型，可上传 PDF / TXT / MD / DOCX / CSV / HTML",
    );
  });

  it("422 的 detail 是数组不是字符串，不能把 [object Object] 甩给用户", async () => {
    vi.mocked(uploadChatAttachment).mockRejectedValue({
      response: {
        status: 422,
        data: { detail: [{ loc: ["body", "file"], msg: "field required", type: "missing" }] },
      },
    });
    const { container } = await renderEmpty();
    pickWordFile(container, 40_000);

    const shown = await shownMessage();
    expect(typeof shown).toBe("string");
    expect(shown).not.toContain("object Object");
  });
});

describe("?q= 深链的发送契约", () => {
  it("send=1（小津气泡）：落地即发送，参数从 URL 抹掉，草稿不残留同文", async () => {
    const sent: string[] = [];
    vi.mocked(sendChatMessageStream).mockImplementation(async (m) => {
      sent.push(m);
    });
    renderPage("/chat?q=%E4%BB%80%E4%B9%88%E6%98%AF%E4%B8%89%E6%B3%95%E5%8D%B0%EF%BC%9F&send=1");

    await waitFor(() => expect(sent).toEqual(["什么是三法印？"]));
    // 参数抹掉：刷新/回退这条 URL 不该重发重扣配额
    expect(screen.getByTestId("loc").textContent).toBe("/chat");
    // 草稿残留这里不设断言：handleSendMessage 发送时本就 setInput("")，
    // 断了也咬不住（实测突变仍绿）。input 初值里对 send=1 的排除防的是
    // 真浏览器里发送前那一帧的闪现，jsdom 观测不到。
  });

  it("send=1 深链在会话号写回后不还魂：URL 只剩 ?s=", async () => {
    // 生产实锤的还魂路径：react-router 函数式 updater 的 prev 来自创建闭包那次
    // 渲染的 location（带 ?q=&send=1），不是 replace 后的实时 URL。onSessionId
    // 一写 ?s= 就把抹掉的参数带回来，刷新即重发重扣配额。
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, callbacks) => { cb = callbacks; },
    );
    renderPage("/chat?q=%E4%BB%80%E4%B9%88%E6%98%AF%E4%B8%89%E6%B3%95%E5%8D%B0%EF%BC%9F&send=1");

    await waitFor(() => expect(cb).toBeDefined());
    cb!.onSessionId(2726 as unknown as number);

    await waitFor(() => {
      expect(screen.getByTestId("loc").textContent).toBe("/chat?s=2726");
    });
  });

  it("裸 ?q=（辞典/收藏链接）：只填不发", async () => {
    const sent: string[] = [];
    vi.mocked(sendChatMessageStream).mockImplementation(async (m) => {
      sent.push(m);
    });
    renderPage("/chat?q=%E8%88%AC%E8%8B%A5");

    await waitFor(() => expect(screen.getByDisplayValue("般若")).toBeInTheDocument());
    expect(sent).toEqual([]);
    // 只填不发的 URL 保持可收藏、可复现
    expect(screen.getByTestId("loc").textContent).toContain("q=");
  });

  it("带 context 的 ?q=（阅读页）：包着经文引用发送，不受 send 参数影响", async () => {
    const sent: string[] = [];
    vi.mocked(sendChatMessageStream).mockImplementation(async (m) => {
      sent.push(m);
    });
    renderPage("/chat?q=%E8%BF%99%E6%AE%B5%E6%80%8E%E4%B9%88%E8%A7%A3%EF%BC%9F&context=%E8%89%B2%E5%8D%B3%E6%98%AF%E7%A9%BA&source=%E5%BF%83%E7%BB%8F");

    await waitFor(() => expect(sent.length).toBe(1));
    expect(sent[0]).toContain("《心经》");
    expect(sent[0]).toContain("> 色即是空");
    expect(sent[0]).toContain("这段怎么解？");
    expect(screen.getByTestId("loc").textContent).toBe("/chat");
  });
});

describe("答案截断 → 「继续写完」", () => {
  /** 普通问答 max_tokens=2000，贴长段求白话翻译会被截断（生产样本：「你还没翻译完呢」）。
   *  后端现在发 truncated 帧；前端要把它变成一个能一键续写的按钮，并把截断记成事件。 */
  function withUmami() {
    const track = vi.fn();
    (window as Window & { umami?: { track: typeof track } }).umami = { track };
    (globalThis as unknown as { umami: unknown }).umami = { track };
    return track;
  }

  async function startSend() {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, cbs) => { cb = cbs; },
    );
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 0, page: 1, size: 50, messages: [],
    } as never);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument());
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());
    return cb!;
  }

  afterEach(() => {
    delete (window as Window & { umami?: unknown }).umami;
    delete (globalThis as unknown as { umami?: unknown }).umami;
  });

  const ANSWER = "色不异空，空不异色，色即是空，空即是色。受想行识，亦复如是。舍利子，是诸法空相，不生不灭，不垢不净，不增不减。是故空中无色，无受想行识，无眼耳鼻舌身意";

  it("truncated 帧 → 流结束后出现「继续写完」与提示，并记一次 answer_truncated", async () => {
    const track = withUmami();
    const cb = await startSend();
    cb.onToken!(ANSWER);
    cb.onTruncated!("length");
    cb.onDone!();
    expect(await screen.findByRole("button", { name: "继续写完" })).toBeInTheDocument();
    expect(screen.getByText("回答因长度上限中断，未写完")).toBeInTheDocument();
    expect(track.mock.calls.filter((c) => c[0] === "answer_truncated")).toHaveLength(1);
  });

  it("点「继续写完」→ 发一条带上回答结尾的续写请求；记 answer_continue、不重复记 chat", async () => {
    // 承重：游客不落库、没有服务端历史，「继续」两个字对模型毫无上下文；
    // 把中断处的结尾带上，登录/游客都能接得上。
    const track = withUmami();
    const cb = await startSend();
    cb.onToken!(ANSWER);
    cb.onTruncated!("length");
    cb.onDone!();
    const btn = await screen.findByRole("button", { name: "继续写完" });
    const sendsBefore = vi.mocked(sendChatMessageStream).mock.calls.length;
    fireEvent.click(btn);
    await waitFor(() =>
      expect(vi.mocked(sendChatMessageStream).mock.calls.length).toBe(sendsBefore + 1),
    );
    const [msg] = vi.mocked(sendChatMessageStream).mock.calls[sendsBefore];
    expect(msg).toContain(ANSWER.slice(-40));
    expect(msg).toContain("不要重复");
    const names = track.mock.calls.map((c) => c[0]);
    expect(names.filter((n) => n === "chat")).toHaveLength(1);
    expect(names.filter((n) => n === "answer_continue")).toHaveLength(1);
  });

  it("没有 truncated 帧的正常回答不出现「继续写完」", async () => {
    withUmami();
    const cb = await startSend();
    cb.onToken!("色不异空。");
    cb.onDone!();
    await waitFor(() => expect(document.querySelector(".anticon-copy")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "继续写完" })).toBeNull();
  });
});

describe("重新生成与等待预期", () => {
  /** 30 天里约 88 次「隔一会儿把同一问题原样再发」前面没有失败也没有重试——
   *  用户对答案不满意，而界面上没有「重新生成」。等待预期：首字要等 24-180 秒，
   *  用户不知道该等多久，等不及就手动停止再发（记成断流）。 */
  function withUmami() {
    const track = vi.fn();
    (window as Window & { umami?: { track: typeof track } }).umami = { track };
    (globalThis as unknown as { umami: unknown }).umami = { track };
    return track;
  }

  async function startSend() {
    let cb: Parameters<typeof sendChatMessageStream>[3] | undefined;
    vi.mocked(sendChatMessageStream).mockImplementation(
      async (_m, _s, _mid, cbs) => { cb = cbs; },
    );
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 0, page: 1, size: 50, messages: [],
    } as never);
    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText("「三毒」指的是哪三种毒？")).toBeInTheDocument());
    fireEvent.click(container.querySelector(".chat-hero-card")!);
    await waitFor(() => expect(cb).toBeDefined());
    const calls = vi.mocked(sendChatMessageStream).mock.calls;
    return { cb: cb!, firstMsg: calls[calls.length - 1][0] };
  }

  afterEach(() => {
    delete (window as Window & { umami?: unknown }).umami;
    delete (globalThis as unknown as { umami?: unknown }).umami;
    localStorage.removeItem("fojin.chat.firstTokenMs");
  });

  it("完成的回答带「重新生成」：同一问题以 regenerate 重发、旧问答从视图移除，记 chat_regenerate 且不重复记 chat", async () => {
    const track = withUmami();
    const { cb, firstMsg } = await startSend();
    cb.onToken!("答案甲：贪、嗔、痴。");
    cb.onDone!();
    await waitFor(() => expect(document.querySelector(".anticon-redo")).toBeTruthy());
    const btn = document.querySelector(".anticon-redo")!.closest("button")!;
    const sendsBefore = vi.mocked(sendChatMessageStream).mock.calls.length;
    fireEvent.click(btn);
    await waitFor(() =>
      expect(vi.mocked(sendChatMessageStream).mock.calls.length).toBe(sendsBefore + 1),
    );
    const call = vi.mocked(sendChatMessageStream).mock.calls[sendsBefore];
    expect(call[0]).toBe(firstMsg);
    expect(call[4]).toMatchObject({ regenerate: true });
    expect(screen.queryByText("答案甲：贪、嗔、痴。")).toBeNull();
    // 旧的那对被移除、新的那对刚发出：问题气泡只剩一份
    expect(screen.getAllByText(firstMsg)).toHaveLength(1);
    const names = track.mock.calls.map((c) => c[0]);
    expect(names.filter((n) => n === "chat")).toHaveLength(1);
    expect(names.filter((n) => n === "chat_regenerate")).toHaveLength(1);
  });

  it("只有最后一条回答带「重新生成」", async () => {
    // 不做「从中间某条分叉」：那要把后面的历史一起作废，语义复杂而用户没有这个需求。
    vi.mocked(getChatSessions).mockResolvedValue([
      { id: 3 as ChatSessionId, title: "会话 3", pinned: false, created_at: new Date().toISOString() },
    ]);
    vi.mocked(getChatSessionMessages).mockResolvedValue({
      total: 4, page: 1, size: 50,
      messages: [
        { id: 1, role: "user", content: "问一", sources: null, created_at: "2026-08-27T00:00:00Z" },
        { id: 2, role: "assistant", content: "答一", sources: null, created_at: "2026-08-27T00:00:01Z" },
        { id: 3, role: "user", content: "问二", sources: null, created_at: "2026-08-27T00:00:02Z" },
        { id: 4, role: "assistant", content: "答二", sources: null, created_at: "2026-08-27T00:00:03Z" },
      ],
    });
    renderPage("/chat?s=3");
    await screen.findByText("答二");
    const redo = document.querySelectorAll(".anticon-redo");
    expect(redo).toHaveLength(1);
    let el: HTMLElement | null = redo[0].parentElement;
    while (el && !el.textContent?.includes("答二")) el = el.parentElement;
    expect(el?.textContent).not.toContain("答一");
  });

  it("有历史首字样本时，等待期显示「上次首字约 N 秒」；首字到达后样本被记录", async () => {
    localStorage.setItem("fojin.chat.firstTokenMs", JSON.stringify([38000, 42000, 40000]));
    withUmami();
    const { cb } = await startSend();
    expect(await screen.findByText("上次首字约 40 秒")).toBeInTheDocument();
    cb.onToken!("答");
    await waitFor(() => expect(screen.queryByText("上次首字约 40 秒")).toBeNull());
    expect(JSON.parse(localStorage.getItem("fojin.chat.firstTokenMs")!)).toHaveLength(4);
  });

  it("没有样本时不显示等待预期", async () => {
    withUmami();
    await startSend();
    await waitFor(() => expect(document.querySelector(".chat-thinking")).toBeTruthy());
    expect(screen.queryByText(/上次首字约/)).toBeNull();
  });
});
