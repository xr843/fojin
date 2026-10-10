import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router";
import TextReaderPage from "./TextReaderPage";
import {
  checkBookmark,
  getJuanApparatus,
  getJuanAudio,
  getJuanContent,
  getJuanLanguages,
  getJuanLineAnchors,
  getJuanList,
  getTextDetail,
} from "../api/client";
import type { TextDetail } from "../api/client";
import type { TextId } from "../types/branded";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getTextDetail: vi.fn(),
    getJuanList: vi.fn(),
    getJuanContent: vi.fn(),
    getJuanLanguages: vi.fn(),
    getJuanLineAnchors: vi.fn(),
    getJuanAudio: vi.fn(),
    getJuanApparatus: vi.fn(),
    checkBookmark: vi.fn(),
    searchDictionaryGrouped: vi.fn(),
    sendChatMessageStream: vi.fn(),
  };
});

vi.mock("../api/chatModels", () => ({
  fetchChatModels: vi.fn().mockResolvedValue([]),
}));

// 面板本身不是这里要测的东西：换成只汇报「开没开」的桩，断言「菜单项真的触发了原功能」。
vi.mock("../components/CitationGenerator", () => ({
  default: ({ open }: { open: boolean }) => (open ? <div data-testid="citation-open" /> : null),
}));
vi.mock("../components/AnnotationPanel", () => ({
  default: ({ visible }: { visible: boolean }) => (visible ? <div data-testid="annotation-open" /> : null),
}));
vi.mock("../components/ReaderParallelPanel", () => ({
  default: () => <div data-testid="parallel-open" />,
}));

/** 手机（≤768）同时也是窄屏（≤1024）；桌面一律不命中。 */
function installMatchMedia(width: "phone" | "desktop") {
  window.matchMedia = ((query: string) => ({
    matches: width === "phone" && (query === "(max-width: 1024px)" || query === "(max-width: 768px)"),
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => {};
  if (!window.requestAnimationFrame) {
    window.requestAnimationFrame = ((cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number) as typeof window.requestAnimationFrame;
  }
});

const TEXT_ID = 69 as TextId;

function detail(extra: Partial<TextDetail> = {}): TextDetail {
  return {
    id: TEXT_ID, taisho_id: "T0676", cbeta_id: "T0676", title_zh: "解深密經",
    title_sa: null, title_bo: null, title_pi: null, translator: "玄奘", dynasty: "唐",
    fascicle_count: 5, category: null, subcategory: null, cbeta_url: null,
    has_content: true, content_char_count: 7574, lang: "lzh", created_at: "2026-01-01T00:00:00Z",
    ...extra,
  };
}

function multiJuan() {
  vi.mocked(getJuanList).mockResolvedValue({
    text_id: TEXT_ID, title_zh: "解深密經", total_juans: 5,
    juans: [{ juan_num: 1, char_count: 7574 }, { juan_num: 2, char_count: 7000 }],
  });
  vi.mocked(getJuanContent).mockResolvedValue({
    text_id: TEXT_ID, cbeta_id: "T0676", title_zh: "解深密經", juan_num: 1, total_juans: 5,
    content: "如是我聞：一時，薄伽梵住最勝光曜七寶莊嚴。", char_count: 20,
    prev_juan: null, next_juan: 2, canon: "taisho", canon_label: "大正藏",
  });
}

function singleJuan() {
  vi.mocked(getJuanList).mockResolvedValue({
    text_id: TEXT_ID, title_zh: "金剛般若波羅蜜經", total_juans: 1,
    juans: [{ juan_num: 1, char_count: 6505 }],
  });
  vi.mocked(getJuanContent).mockResolvedValue({
    text_id: TEXT_ID, cbeta_id: "T0235", title_zh: "金剛般若波羅蜜經", juan_num: 1, total_juans: 1,
    content: "如是我聞：一時，佛在舍衛國祇樹給孤獨園。", char_count: 20,
    prev_juan: null, next_juan: null, canon: "taisho", canon_label: "大正藏",
  });
}

beforeEach(() => {
  vi.mocked(getTextDetail).mockResolvedValue(detail());
  multiJuan();
  vi.mocked(getJuanLanguages).mockResolvedValue({
    text_id: TEXT_ID, juan_num: 1, languages: ["lzh"], default_lang: "lzh",
  });
  vi.mocked(getJuanLineAnchors).mockResolvedValue({ text_id: TEXT_ID, juan_num: 1, anchors: [] });
  vi.mocked(getJuanAudio).mockRejectedValue(new Error("404"));
  vi.mocked(getJuanApparatus).mockResolvedValue({ text_id: TEXT_ID, juan_num: 1, entries: [] } as never);
  vi.mocked(checkBookmark).mockResolvedValue(false);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  localStorage.removeItem("fojin.reader.aiPanel");
});

async function renderReader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const r = render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/texts/69/read"]}>
          <Routes>
            <Route path="/texts/:id/read" element={<TextReaderPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
  await screen.findByText(/如是我聞/);
  return r;
}

const prevNextButtons = () => screen.queryAllByRole("button", { name: /上一卷|下一卷/ });

async function openMore() {
  fireEvent.click(screen.getByRole("button", { name: /更多/ }));
  return await screen.findByRole("menu");
}

describe("单卷经不显示翻卷按钮", () => {
  // 金剛經只有 1 卷：生产上顶部和经末各有一组禁用态的「上一卷/下一卷」，四颗按钮全是死的。
  it("手机：顶部与经末都没有上一卷/下一卷", async () => {
    installMatchMedia("phone");
    singleJuan();
    await renderReader();
    await screen.findAllByText("金剛般若波羅蜜經");
    expect(prevNextButtons()).toHaveLength(0);
  });

  it("桌面：同样不显示", async () => {
    installMatchMedia("desktop");
    singleJuan();
    await renderReader();
    await screen.findAllByText("金剛般若波羅蜜經");
    expect(prevNextButtons()).toHaveLength(0);
  });

  it("多卷经照常显示两组（顶部 + 经末）", async () => {
    installMatchMedia("phone");
    await renderReader();
    expect(prevNextButtons()).toHaveLength(4);
  });
});

describe("手机工具栏收成一行 + 「更多」菜单", () => {
  it("手机：收藏/标注/引用/导出/校勘/跨藏对照/高丽藏/字号不再平铺在工具栏上", async () => {
    installMatchMedia("phone");
    vi.mocked(getTextDetail).mockResolvedValue(detail({ goryeo_k: "K0154", kabc_url: "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_K0154" }));
    const { container } = await renderReader();
    const nav = container.querySelector(".reader-nav") as HTMLElement;
    for (const name of [/收藏/, /标注/, /引用/, /导出/, /校勘/, /跨藏对照/, /高丽藏/, /A\+/, /A-/]) {
      expect(within(nav).queryByRole("button", { name })).toBeNull();
    }
    expect(within(nav).getByRole("button", { name: /更多/ })).toBeTruthy();
  });

  it("桌面：工具栏原样平铺，没有「更多」", async () => {
    installMatchMedia("desktop");
    const { container } = await renderReader();
    const nav = container.querySelector(".reader-nav") as HTMLElement;
    for (const name of [/收藏/, /标注/, /引用/, /导出/, /校勘/, /跨藏对照/, /A\+/]) {
      expect(within(nav).getByRole("button", { name })).toBeTruthy();
    }
    expect(within(nav).queryByRole("button", { name: /更多/ })).toBeNull();
  });

  it("菜单项「引用」「标注」打开原来的面板", async () => {
    installMatchMedia("phone");
    await renderReader();
    fireEvent.click(within(await openMore()).getByText("引用"));
    expect(await screen.findByTestId("citation-open")).toBeTruthy();

    fireEvent.click(within(await openMore()).getByText("标注"));
    expect(await screen.findByTestId("annotation-open")).toBeTruthy();
  });

  it("菜单项「跨藏对照」打开对照面板，「校勘」打开校勘层", async () => {
    installMatchMedia("phone");
    await renderReader();
    fireEvent.click(within(await openMore()).getByText("跨藏对照"));
    expect(await screen.findByTestId("parallel-open")).toBeTruthy();

    expect(getJuanApparatus).not.toHaveBeenCalled();
    fireEvent.click(within(await openMore()).getByText("校勘"));
    await waitFor(() => expect(getJuanApparatus).toHaveBeenCalled());
  });

  it("菜单项「高丽藏」仍是外链：带外链图标，点了 window.open 去 KABC 本卷", async () => {
    installMatchMedia("phone");
    vi.mocked(getTextDetail).mockResolvedValue(detail({ goryeo_k: "K0154", kabc_url: "https://kabc.dongguk.edu/content/view?dataId=ABC_IT_K0154" }));
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    await renderReader();
    const menu = await openMore();
    const item = within(menu).getByText("高丽藏").closest("li") as HTMLElement;
    expect(item.querySelector(".anticon-export")).not.toBeNull();
    fireEvent.click(item);
    expect(open).toHaveBeenCalledWith(expect.stringContaining("ABC_IT_K0154_T_001"), "_blank", "noopener");
  });

  it("菜单里的字号按钮能调字号且不关菜单", async () => {
    installMatchMedia("phone");
    localStorage.removeItem("fojin-reader-font-size");
    const { container } = await renderReader();
    const menuRoot = (await openMore()).closest(".ant-dropdown") as HTMLElement;
    fireEvent.click(within(menuRoot).getByRole("button", { name: /A\+/ }));
    const body = container.querySelector(".reader-body") as HTMLElement;
    await waitFor(() => expect(body.style.getPropertyValue("--reader-font-size")).toBe("20px"));
    expect(menuRoot.classList.contains("ant-dropdown-hidden")).toBe(false);
    localStorage.removeItem("fojin-reader-font-size");
  });
});

describe("手机 AI 浮钮：下滑收起、上滑出现", () => {
  function scrollTo(y: number) {
    act(() => {
      Object.defineProperty(window, "scrollY", { value: y, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });
  }

  it("往下读时浮钮收起（不压经文），往回滑时出现", async () => {
    installMatchMedia("phone");
    Object.defineProperty(document.documentElement, "scrollHeight", { value: 20000, configurable: true });
    const { container } = await renderReader();
    const fab = () => container.querySelector(".reader-ai-fab") as HTMLElement;
    expect(fab().classList.contains("reader-fab-tucked")).toBe(false);

    scrollTo(300);
    scrollTo(600);
    expect(fab().classList.contains("reader-fab-tucked")).toBe(true);

    scrollTo(500);
    expect(fab().classList.contains("reader-fab-tucked")).toBe(false);
    scrollTo(0);
  });

  it("桌面不受影响：滚动不收起浮钮", async () => {
    installMatchMedia("desktop");
    localStorage.setItem("fojin.reader.aiPanel", "closed");
    const { container } = await renderReader();
    scrollTo(300);
    scrollTo(600);
    expect((container.querySelector(".reader-ai-fab") as HTMLElement).classList.contains("reader-fab-tucked")).toBe(false);
    scrollTo(0);
  });
});

describe("卷选择框：只显示卷次，字数留在下拉选项里", () => {
  // 2026-10-10 生产实测：手机上选择框只有约 120px 可用、桌面 116px，「第 22 卷 (9,820字)」
  // 要 131px、英文「Fascicle 22 (9,820 chars)」要 175px，被截成「第 22 卷 (9,8…」。
  const selected = (container: HTMLElement) =>
    container.querySelector(".juan-select .ant-select-selection-item")?.textContent;

  it("手机：选中项只显示「第 1 卷」", async () => {
    installMatchMedia("phone");
    const { container } = await renderReader();
    await waitFor(() => expect(selected(container)).toBe("第 1 卷"));
  });

  it("手机：展开后选项仍带字数", async () => {
    installMatchMedia("phone");
    const { container } = await renderReader();
    await waitFor(() => expect(selected(container)).toMatch(/^第 1 卷/));
    fireEvent.mouseDown(container.querySelector(".juan-select .ant-select-selector") as HTMLElement);
    expect(await screen.findByText("第 2 卷 (7,000字)")).toBeTruthy();
  });

  it("桌面：同样只显示卷次，展开后选项带字数", async () => {
    installMatchMedia("desktop");
    const { container } = await renderReader();
    await waitFor(() => expect(selected(container)).toBe("第 1 卷"));
    fireEvent.mouseDown(container.querySelector(".juan-select .ant-select-selector") as HTMLElement);
    expect(await screen.findByText("第 2 卷 (7,000字)")).toBeTruthy();
  });
});
