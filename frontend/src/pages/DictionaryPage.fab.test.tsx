import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter } from "react-router";
import DictionaryPage from "./DictionaryPage";
import { getDictionarySources, searchDictionaryGrouped, getDictConcept } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return {
    ...actual,
    getDictionarySources: vi.fn(),
    searchDictionaryGrouped: vi.fn(),
    getDictConcept: vi.fn(),
  };
});

/**
 * 2026-10-11 生产 390×844 /dictionary?q=般若：「问小津」圆钮（44×44，x 334 / y 788）
 * 在首屏压住词条正文 2 个字（320×640 压 4 个），往下读时每一屏右下角都被它盖住。
 * 与阅读器 #1295 同一做法：≤1024 往下滑收起、往回滑 / 回到顶部 / 到页尾出现。
 * 没选「内容右侧让位」：让出 56px 后 390 首屏可见字数 425 → 346（-19%），代价远大于 2 个字。
 */
const originalMatchMedia = window.matchMedia;

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

function scrollTo(y: number) {
  act(() => {
    Object.defineProperty(window, "scrollY", { value: y, configurable: true });
    window.dispatchEvent(new Event("scroll"));
  });
}

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
  Object.defineProperty(document.documentElement, "scrollHeight", { value: 20000, configurable: true });
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
          { id: 1, headword: "般若", reading: null, lang: "zh", definition: "智慧。", source_name: "佛光大辞典" },
        ],
      },
    ],
  } as never);
});

afterEach(() => {
  scrollTo(0);
  window.matchMedia = originalMatchMedia;
});

const fab = (c: HTMLElement) => c.querySelector(".dict-ask-ai") as HTMLElement;

describe("辞典「问小津」浮钮：下滑收起、上滑出现", () => {
  it("手机：往下读时收起，往回滑时出现，回到顶部也出现", async () => {
    installMatchMedia("phone");
    const { container } = renderAt("/dictionary?q=般若");
    await waitFor(() => expect(screen.getByText("般若")).toBeInTheDocument());
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(false);

    // 从顶部一开始往下滑就收起——首屏被压住的就是最底下那一行，读它必须往下滑。
    scrollTo(40);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(true);
    scrollTo(400);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(true);

    scrollTo(300);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(false);

    scrollTo(600);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(true);
    scrollTo(0);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(false);
  });

  it("到页尾时出现（无处可滑，不能让入口消失）", async () => {
    installMatchMedia("phone");
    Object.defineProperty(document.documentElement, "scrollHeight", { value: 1500, configurable: true });
    const { container } = renderAt("/dictionary?q=般若");
    await waitFor(() => expect(screen.getByText("般若")).toBeInTheDocument());
    scrollTo(200);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(true);
    scrollTo(1500 - window.innerHeight);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(false);
  });

  it("桌面不受影响：滚动不收起", async () => {
    installMatchMedia("desktop");
    const { container } = renderAt("/dictionary?q=般若");
    await waitFor(() => expect(screen.getByText("般若")).toBeInTheDocument());
    scrollTo(300);
    scrollTo(600);
    expect(fab(container).classList.contains("dict-ask-ai--tucked")).toBe(false);
  });
});
