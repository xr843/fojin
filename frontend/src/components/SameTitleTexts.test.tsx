import { describe, it, expect, vi, beforeEach, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SameTitleTexts from "./SameTitleTexts";
import {
  getTextVersions,
  getTextRelations,
  getWorkByText,
  type TextVersionsResponse,
  type VersionTranslation,
} from "../api/client";

beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList;
  }
});

vi.mock("../api/client", () => ({
  getTextVersions: vi.fn(),
  getTextRelations: vi.fn(),
  getWorkByText: vi.fn(),
}));

function tr(o: Partial<VersionTranslation> = {}): VersionTranslation {
  return {
    text_id: 6491,
    title_zh: "金剛般若波羅蜜經",
    title_en: null,
    translator: "真諦",
    dynasty: "南朝",
    lang: "lzh",
    source_name: "CBETA",
    relation_type: null,
    ...o,
  };
}

function versions(translations: VersionTranslation[]): TextVersionsResponse {
  return { text_id: 7, title_zh: "金剛般若波羅蜜經", translations, iiif_manifests: [], source_links: [] };
}

function renderPanel(textId = 7) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SameTitleTexts textId={textId} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SameTitleTexts 同名经典", () => {
  beforeEach(() => {
    vi.mocked(getTextVersions).mockReset();
    vi.mocked(getTextRelations).mockResolvedValue({ text_id: 7 as never, title_zh: "", relations: [] });
    vi.mocked(getWorkByText).mockResolvedValue(null);
  });

  // 生产 /texts/7（羅什譯金剛經）：relations 空、works 只有自己一个见证本，
  // 页面下方一片空白——可 /versions 明明按题名找到了菩提流支、真諦两译。
  it("列出 /versions 里按同名找到的文本，并链到各自详情页", async () => {
    vi.mocked(getTextVersions).mockResolvedValue(
      versions([
        tr({ text_id: 10036, translator: "魏 菩提流支", dynasty: "元" }),
        tr({ text_id: 6491, translator: "真諦", dynasty: "南朝" }),
      ]),
    );
    renderPanel();
    await waitFor(() => expect(screen.getByText(/真諦/)).toBeInTheDocument());
    expect(screen.getByText(/同名经典/)).toBeInTheDocument();
    expect(screen.getByText(/菩提流支/)).toBeInTheDocument();
    const links = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(links).toEqual(expect.arrayContaining(["/texts/10036", "/texts/6491"]));
  });

  // relation_type 非空的行来自 text_relations，「关联文本」卡已经列过；
  // 已在「其他版本」（works 见证本）或「关联文本」里出现的 id 也不重复列。
  it("不重复列出已由关联文本 / 其他版本展示的条目", async () => {
    vi.mocked(getTextVersions).mockResolvedValue(
      versions([
        tr({ text_id: 1, title_zh: "Parallel sutta", relation_type: "parallel", lang: "pi" }),
        tr({ text_id: 2, title_zh: "同名甲", relation_type: null }),
        tr({ text_id: 3, title_zh: "同名乙", relation_type: null }),
        tr({ text_id: 4, title_zh: "同名丙", relation_type: null }),
      ]),
    );
    vi.mocked(getTextRelations).mockResolvedValue({
      text_id: 7 as never,
      title_zh: "",
      relations: [{ text_id: 3, cbeta_id: "X", title_zh: "同名乙", translator: null, dynasty: null, lang: "lzh", relation_type: "cites", confidence: 1, note: null } as never],
    });
    vi.mocked(getWorkByText).mockResolvedValue({
      slug: "w",
      title_primary: "",
      title_sa: null,
      witness_count: 2,
      witnesses: [
        { text_id: 7, cbeta_id: "T", title: "", lang: "lzh", canon: null, role: "translation", confidence: "auto", has_content: true },
        { text_id: 4, cbeta_id: "T", title: "", lang: "lzh", canon: null, role: "translation", confidence: "auto", has_content: true },
      ],
    });
    renderPanel();
    await waitFor(() => expect(screen.getByText("同名甲")).toBeInTheDocument());
    expect(screen.queryByText("Parallel sutta")).toBeNull();
    expect(screen.queryByText("同名乙")).toBeNull();
    expect(screen.queryByText("同名丙")).toBeNull();
  });

  it("没有同名文本时整块不渲染（不放空态占位）", async () => {
    vi.mocked(getTextVersions).mockResolvedValue(
      versions([tr({ text_id: 1, relation_type: "parallel" })]),
    );
    const { container } = renderPanel();
    await waitFor(() => expect(getTextVersions).toHaveBeenCalledWith(7));
    expect(container.innerHTML).toBe("");
  });

  // /texts/3 的 /versions 有上千行；同名行也可能很多，默认只露一屏，按需展开。
  it("条目多时先收起，点「展开全部」后显示其余", async () => {
    vi.mocked(getTextVersions).mockResolvedValue(
      versions(Array.from({ length: 12 }, (_, i) => tr({ text_id: 100 + i, translator: `译者${i}` }))),
    );
    renderPanel();
    await waitFor(() => expect(screen.getByText(/译者0/)).toBeInTheDocument());
    expect(screen.queryByText(/译者11/)).toBeNull();
    screen.getByRole("button", { name: /展开全部/ }).click();
    await waitFor(() => expect(screen.getByText(/译者11/)).toBeInTheDocument());
  });
});
