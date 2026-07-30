import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  sendChatMessageStream,
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

const FOLLOWING = 4; // Node.DOCUMENT_POSITION_FOLLOWING
const CONTAINED_BY = 16; // Node.DOCUMENT_POSITION_CONTAINED_BY

describe("ChatPage 首屏结构", () => {
  it("空状态渲染出标题与建议卡片（脚手架自检）", async () => {
    const { container } = await renderEmpty();
    expect(screen.getByText("小津 AI 佛典问答")).toBeInTheDocument();
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
