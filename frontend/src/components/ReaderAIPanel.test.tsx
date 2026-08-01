import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import i18n from "../i18n";
import enTranslation from "../../public/locales/en/translation.json";
import ReaderAIPanel from "./ReaderAIPanel";
import { sendChatMessageStream } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, sendChatMessageStream: vi.fn() };
});

// 只替换 message —— antd v5 的静态 message 在 React 19 下要靠入口的 v5-patch 才
// 生效（setup.ts 里已引），但用 spy 断言比查 DOM 文案可靠。
vi.mock("antd", async () => {
  const actual = await vi.importActual<typeof import("antd")>("antd");
  return { ...actual, message: { ...actual.message, error: vi.fn(), success: vi.fn() } };
});

beforeAll(() => {
  // 只有 zh 被内联进 i18n 实例，其余语言走 HttpBackend —— 在 jsdom 下它永远不
  // resolve，changeLanguage() 会一路挂到用例超时。切到哪个语言就先把哪个包塞进去
  // （与 CollectionsPage.test.tsx 同一手法）。
  i18n.addResourceBundle("en", "translation", enTranslation, true, true);
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
  if (!window.requestAnimationFrame) {
    window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
  }
});

type Callbacks = Parameters<typeof sendChatMessageStream>[3];
let cb: Callbacks | undefined;

beforeEach(() => {
  cb = undefined;
  vi.mocked(sendChatMessageStream).mockImplementation(async (_m, _s, _mid, callbacks) => {
    cb = callbacks;   // 流不结束，停在"生成中"
  });
});

function renderPanel() {
  return render(
    <MemoryRouter>
      <ReaderAIPanel textId={1} juanNum={1} textTitle="金剛經" juanContent="如是我聞" />
    </MemoryRouter>,
  );
}

/** 发一句话，拿到流回调。 */
async function ask(container: HTMLElement) {
  const ta = container.querySelector("textarea")!;
  fireEvent.change(ta, { target: { value: "色即是空怎么讲" } });
  fireEvent.keyDown(ta, { key: "Enter", code: "Enter" });
  await waitFor(() => expect(cb).toBeDefined());
}

describe("ReaderAIPanel", () => {
  it("脚手架自检：能发出问题并进入等待态", async () => {
    const { container } = renderPanel();
    await ask(container);
    expect(container.querySelector(".ant-spin")).not.toBeNull();
  });

  // ── 缺陷 b：这条路径超时预算 300 秒，注释写明常态 90-180 秒 ──────────────
  // 此前 onSearching 是空壳、onRetrieved/onReasoning 完全没接，用户在这一两分钟
  // 里只看得到一句静态文案。
  it("b: 检索完成后显示已检索到的经典，而不是干等", async () => {
    const { container } = renderPanel();
    await ask(container);
    cb!.onRetrieved?.({ count: 5, titles: ["金剛般若波羅蜜經", "大智度論"] });
    expect(await screen.findByText(/已检索 5 部经典/)).toBeInTheDocument();
    expect(container.textContent).toContain("金剛般若波羅蜜經");
  });

  it("b: 收到推理信号后改显示「正在推敲经文」并计时", async () => {
    const { container } = renderPanel();
    await ask(container);
    cb!.onReasoning?.({ chars: 120 });
    expect(await screen.findByText(/正在推敲经文/)).toBeInTheDocument();
  });

  // 承重点：进度事件绝不能写进 content —— 一旦写进去，下面那条空转兜底就失效了
  // （它按哨兵的身份判断）。这正是 ChatPage 当初立的同一条约束。
  it("b 承重点: 进度事件之后仍能落到失败兜底", async () => {
    const { container } = renderPanel();
    await ask(container);
    cb!.onRetrieved?.({ count: 3, titles: ["法華經"] });
    cb!.onReasoning?.({ chars: 50 });
    cb!.onDone();   // 流结束，但一个 token 都没来过
    expect(await screen.findByText(/请求失败/)).toBeInTheDocument();
  });

  // ── 缺陷 d：流空转 ──────────────────────────────────────────────────
  it("d: 流结束却没收到任何 token 时转为失败态，而不是永远停在思考中", async () => {
    const { container } = renderPanel();
    await ask(container);
    expect(container.querySelector(".ant-spin")).not.toBeNull();
    cb!.onDone();
    expect(await screen.findByText(/请求失败/)).toBeInTheDocument();
    await waitFor(() => expect(container.querySelector(".ant-spin")).toBeNull());
  });

  // ── 缺陷 c：占位符此前按翻译字符串比较 ────────────────────────────────
  // 中途切一次语言，t() 返回值就变了 —— 四处比较全部失配。后果是叠加的：首个
  // token 追加在占位符后面，且 onError 的兜底也不再触发。
  it("c 承重点: 问答途中切换语言，首个 token 仍是替换而非追加", async () => {
    const { container } = renderPanel();
    await ask(container);
    await i18n.changeLanguage("en");   // 中途换语言
    try {
      cb!.onToken("色即是空");
      await waitFor(() => {
        expect(container.textContent).toContain("色即是空");
      });
      // 占位符的任一语言版本都不该残留在答案里
      expect(container.textContent).not.toMatch(/正在思考|Thinking/);
    } finally {
      await i18n.changeLanguage("zh");
    }
  });

  it("c: 切换语言后失败兜底仍然触发", async () => {
    const { container } = renderPanel();
    await ask(container);
    await i18n.changeLanguage("en");
    try {
      cb!.onDone();
      await waitFor(() => {
        expect(container.querySelector(".ant-spin")).toBeNull();
      });
    } finally {
      await i18n.changeLanguage("zh");
    }
  });
});

// ── 缺陷 a：无条件滚动 ────────────────────────────────────────────────
//
// 此前 scrollToBottom 没有任何守卫，每来一个 token 就调一次 —— 用户往上翻看前文
// 时会被反复拽回底部。这是 ChatPage 在 #1069 修过的同一个 P0。

describe("ReaderAIPanel 滚动跟随", () => {
  /** 把消息容器伪造成"用户已经往上滚了很远"。 */
  function scrollAwayFromBottom(container: HTMLElement) {
    const box = container.querySelector<HTMLElement>(".reader-ai-messages")!;
    Object.defineProperty(box, "scrollHeight", { value: 4000, configurable: true });
    Object.defineProperty(box, "clientHeight", { value: 500, configurable: true });
    Object.defineProperty(box, "scrollTop", { value: 200, writable: true, configurable: true });
    fireEvent.scroll(box);
    return box;
  }

  it("a 承重点: 流式中途上滚后，后续 token 不再把用户拽回底部", async () => {
    const { container } = renderPanel();
    await ask(container);
    // 发送自己会强制滚一次（见下一条用例），它排的 rAF 要先冲刷掉，
    // 否则会被误记到 token 头上 —— 这条最初就是这么假红的。
    await new Promise((r) => setTimeout(r, 60));
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    try {
      scrollAwayFromBottom(container);
      cb!.onToken("色");
      cb!.onToken("即是空");
      // rAF 排到下一帧才跑，等够
      await new Promise((r) => setTimeout(r, 60));
      expect(spy).not.toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  // 上一条只验了"调用时人已在上面"。真正难缠的是**调用时还在底部、rAF 落地前
  // 才上滚**：只在调用点判断的话，那个存量 rAF 照样把人拽回去。
  // ChatPage 的终审就是在这里翻车的，所以这条必须单独立。
  it("a 承重点: 上滚发生在 rAF 落地之前，存量回调也不该滚", async () => {
    const { container } = renderPanel();
    await ask(container);
    await new Promise((r) => setTimeout(r, 60));
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    try {
      cb!.onToken("色");                  // 此刻仍在底部 → 通过调用点检查，排下 rAF
      scrollAwayFromBottom(container);    // rAF 落地前，用户上滚
      await new Promise((r) => setTimeout(r, 60));
      expect(spy).not.toHaveBeenCalled();
    } finally {
      spy.mockRestore();
    }
  });

  it("a: 用户仍贴着底部时，自动跟随照常", async () => {
    const { container } = renderPanel();
    await ask(container);
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    try {
      cb!.onToken("色即是空");
      await waitFor(() => expect(spy).toHaveBeenCalled());
    } finally {
      spy.mockRestore();
    }
  });

  // 自己刚发出一句话，必然是想看新内容 —— 这一次必须强制滚到底，
  // 否则上一轮停在半空的阅读位置会让新问题看不见。
  it("a: 上滚之后再发一句，会强制滚回底部", async () => {
    const { container } = renderPanel();
    await ask(container);
    // 必须先结束首轮：sending 只在 onDone 里复位，不结束的话第二次发送会被
    // `if (!msg || sending) return` 直接挡掉。这条最初漏了这一步，于是 spy 抓到的
    // 其实是**首轮**强制滚动的存量 rAF —— 用例因错误的原因而绿，满载下才露馅。
    cb!.onDone();
    await waitFor(() => expect(container.querySelector(".ant-spin")).toBeNull());
    await new Promise((r) => setTimeout(r, 60));   // 冲刷首轮的 rAF

    scrollAwayFromBottom(container);
    const spy = vi.spyOn(Element.prototype, "scrollIntoView").mockImplementation(() => {});
    try {
      const ta = container.querySelector("textarea")!;
      fireEvent.change(ta, { target: { value: "再问一句" } });
      fireEvent.keyDown(ta, { key: "Enter", code: "Enter" });
      await waitFor(() => expect(spy).toHaveBeenCalled(), { timeout: 3000 });
    } finally {
      spy.mockRestore();
    }
  });
});
