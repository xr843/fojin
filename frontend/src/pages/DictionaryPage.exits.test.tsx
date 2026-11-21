import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import DictionaryPage from "./DictionaryPage";
import {
  getDictionarySources,
  searchDictionaryGrouped,
  getDictConcept,
} from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getDictionarySources: vi.fn(),
    searchDictionaryGrouped: vi.fn(),
    getDictConcept: vi.fn(),
  };
});

const HEADWORD = "因果";

function renderAt(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[entry]}>
          <DictionaryPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getDictionarySources).mockResolvedValue([]);
  vi.mocked(getDictConcept).mockResolvedValue(null as never);
  vi.mocked(searchDictionaryGrouped).mockResolvedValue({
    total: 1,
    page: 1,
    page_size: 20,
    groups: [
      {
        source_code: "fgd",
        source_name: "佛光大辞典",
        total: 1,
        entries: [
          {
            id: 1,
            headword: HEADWORD,
            reading: null,
            lang: "zh",
            definition: "梵语 hetu-phala。指原因与结果。",
            source_name: "佛光大辞典",
          },
        ],
      },
    ],
  } as never);
});

/**
 * 辞典此前是个死胡同：Umami 30 天里 /dictionary 有 1,886 次浏览、428 个会话、
 * 813 个不同词头（全站最真实的需求信号），但 dictionary→dictionary 的跳转有
 * 1,331 次，去 /chat 只有 71 次、去经文只有 15 次。唯一的出口是右下角那颗浮动
 * 按钮，而且它带走的是搜索框里的词、不是眼前这一条词条的词头。
 */
describe("辞典词条的出口", () => {
  it("展开词条后给出「问小津」和「在藏经中检索」两个出口，且都带这一条的词头", async () => {
    const { container } = renderAt(`/dictionary?q=${encodeURIComponent(HEADWORD)}`);
    await waitFor(() => expect(screen.getByText(HEADWORD)).toBeInTheDocument());

    // 折叠态不该有出口 —— 一屏几十条，每条都挂两个链接就成了噪音。
    expect(container.querySelector(".dict-entry-exits")).toBeNull();

    fireEvent.click(container.querySelector(".dict-entry-main")!);

    const exits = await waitFor(() => {
      const el = container.querySelector(".dict-entry-exits");
      expect(el).not.toBeNull();
      return el!;
    });
    const hrefs = [...exits.querySelectorAll("a")].map((a) => a.getAttribute("href"));
    expect(hrefs).toEqual([
      `/chat?q=${encodeURIComponent(HEADWORD)}`,
      `/search?q=${encodeURIComponent(HEADWORD)}`,
    ]);
  });

  it("出口是可点开合区域的兄弟节点，不嵌在 role=button 里", async () => {
    // nested-interactive：<a> 套在 role="button" 里，读屏软件只报最外层那颗
    // 按钮，键盘用户 Tab 不进去 —— 出口等于对他们不存在。
    const { container } = renderAt(`/dictionary?q=${encodeURIComponent(HEADWORD)}`);
    await waitFor(() => expect(screen.getByText(HEADWORD)).toBeInTheDocument());
    fireEvent.click(container.querySelector(".dict-entry-main")!);
    await waitFor(() => expect(container.querySelector(".dict-entry-exits")).not.toBeNull());

    const toggle = container.querySelector('[role="button"].dict-entry-main')!;
    expect(toggle).not.toBeNull();
    expect(toggle.querySelector("a")).toBeNull();
  });
});

/**
 * 2026-11-21 用户反馈（附录屏）：在词条释义上拖选文字想复制，松开鼠标那一下被当成
 * 「点击词条」，词条随之展开/收起，选区跟着跳走，复制不了。
 */
describe("在词条里选文字不会触发展开/收起", () => {
  function selectTextIn(el: Element) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection()!;
    sel.removeAllRanges();
    sel.addRange(range);
  }

  it("词条内有选中文字时点击不切换；没有选区时照常切换", async () => {
    const { container } = renderAt(`/dictionary?q=${encodeURIComponent(HEADWORD)}`);
    await waitFor(() => expect(screen.getByText(HEADWORD)).toBeInTheDocument());
    const main = container.querySelector(".dict-entry-main")!;

    // 折叠态拖选预览文字：不应展开
    selectTextIn(container.querySelector(".dict-entry-def-preview")!);
    fireEvent.click(main);
    expect(container.querySelector(".dict-entry-def-full")).toBeNull();

    // 清掉选区后点击：照常展开
    window.getSelection()!.removeAllRanges();
    fireEvent.click(main);
    expect(container.querySelector(".dict-entry-def-full")).not.toBeNull();

    // 展开态拖选全文：不应收起
    selectTextIn(container.querySelector(".dict-entry-def-full")!);
    fireEvent.click(main);
    expect(container.querySelector(".dict-entry-def-full")).not.toBeNull();
    window.getSelection()!.removeAllRanges();
  });
});
