import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, useLocation } from "react-router";
import { message } from "antd";
import ChatPage from "./ChatPage";
import { useAuthStore } from "../stores/authStore";
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
import type { ChatSessionId } from "../types/branded";

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

function renderPage(entry = "/chat") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
  // 侧栏收起状态持久化在 localStorage —— 不清的话它会泄漏到后面的用例里
  localStorage.removeItem("fojin.chat.sidebarCollapsed");
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
  function loggedIn(quota: { limit: number; used: number; remaining: number; has_byok: boolean }) {
    vi.mocked(getChatQuota).mockResolvedValue(quota);
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
    cb.onError!("上游中断");
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "mid_stream" }]);
  });

  it("一个 token 都没到就失败 → 记为 no_token，且不被 onDone 重复计一次", async () => {
    // 承重：onError 之后 onDone 必定到达，而此时 tokenCount 仍是 0 —— 少了
    // sawError 守卫，同一次失败会同时记 no_token 和 empty_done，
    // 直接把失败率的分子灌成两倍。
    const track = withUmami();
    const cb = await startSend();
    cb.onError!("上游 503");
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "no_token" }]);
  });

  it("流悄无声息地结束（没有 error 帧、也没有 token）→ 记为 empty_done", async () => {
    const track = withUmami();
    const cb = await startSend();
    cb.onDone!();
    expect(errEvents(track)).toEqual([{ stage: "empty_done" }]);
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

describe("空状态副标题", () => {
  it("只留「可核对」那句，不再重复卡片已经在演示的「能问什么」", async () => {
    await renderEmpty();
    // 两行原本同处一个 <div>、由 <br> 分隔，getByText 匹配不到单独的文本节点，
    // 所以对整块 hero 的 textContent 断言。
    const hero = screen.getByText("小津 AI 佛典问答").parentElement!;

    // 差异点声明必须在：整个首屏只有这一处告诉用户答案可以被核对，
    // 而且措辞是「你可以核对」而非「我保证正确」—— 不能悄悄丢掉。
    expect(hero.textContent).toContain("答案标注经文出处，可点开核对原文");

    // 原来的第一行「可以问我关于佛经内容、佛教历史、经典翻译等问题」是第三次
    // 重复：下方四张卡片（白话翻译/经文解读/对比辨析/佛教史话）带真实例题且可点，
    // 输入框 placeholder 还在轮播真实例题。抽象地再说一遍只是噪音。
    expect(hero.textContent).not.toContain("可以问我关于");
  });
});
