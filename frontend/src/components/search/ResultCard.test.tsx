import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import ResultCard from "./ResultCard";
import CrossLangCard from "./CrossLangCard";
import type { CrossLanguageSearchHit, SearchHit } from "../../api/client";
import type { TextId } from "../../types/branded";

vi.mock("../../api/client", () => ({
  getAlignmentCatalog: vi.fn(async () => ({ entries: [] })),
}));

function makeHit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    id: 236 as TextId,
    taisho_id: "T0235",
    cbeta_id: "T0235",
    title_zh: "金剛般若波羅蜜經",
    translator: "鳩摩羅什",
    dynasty: "十六國",
    category: "大正藏",
    cbeta_url: null,
    has_content: true,
    source_code: "cbeta",
    lang: "lzh",
    score: 1,
    highlight: { title_zh: ["<em>金剛</em>般若波羅蜜經"] },
    related_translations: [],
    ...overrides,
  };
}

function makeCrossHit(overrides: Partial<CrossLanguageSearchHit> = {}): CrossLanguageSearchHit {
  return {
    ...makeHit(),
    title_en: "Diamond Sutra",
    title_sa: null,
    title_pi: null,
    title_bo: null,
    lang: "lzh",
    ...overrides,
  } as CrossLanguageSearchHit;
}

function renderWithProviders(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// 经名本身就是去详情页的主链接：此前标题是死文字，唯一入口是每张卡上一颗实心朱砂
// 「查看详情」——一页十几颗主按钮，视觉重心全压在按钮上，而经名反倒点不动。
describe.each([
  ["ResultCard", () => renderWithProviders(<ResultCard hit={makeHit()} />)],
  ["CrossLangCard", () => renderWithProviders(<CrossLangCard hit={makeCrossHit()} />)],
])("%s 经名即主链接", (_name, renderIt) => {
  it("经名是指向 /texts/{id} 的链接，且保留命中高亮", () => {
    const { container } = renderIt();
    const link = screen.getByRole("link", { name: "金剛般若波羅蜜經" });
    expect(link).toHaveAttribute("href", "/texts/236");
    expect(link.querySelector("em")?.textContent).toBe("金剛");
    expect(container.querySelector(".s-card-title a")).toBe(link);
  });

  it("不再有实心「查看详情」主按钮", () => {
    const { container } = renderIt();
    expect(screen.queryByText("查看详情")).not.toBeInTheDocument();
    expect(container.querySelector(".ant-btn-primary")).toBeNull();
  });

  it("不渲染「排序 #N」窄栏——顺序本身就是排序", () => {
    const { container } = renderIt();
    expect(container.querySelector(".s-card-rank")).toBeNull();
    expect(screen.queryByText(/排序/)).not.toBeInTheDocument();
  });
});

// 「其他语言版本 / 关联翻译」那排原是 antd Tag + onClick 跳转：Tag 是 <span>，Tab 到不了、
// 回车也不触发，键盘用户进不去别的译本。改成真正的 <a href>，保留标签外观。
// 英文界面「Classical Chinese - 佛說能斷金剛般若波羅蜜多經」又是 nowrap 的 Tag，
// 在 320px 把整列撑出 22px（生产实测）——改成链接后必须允许折行。
describe.each([
  ["ResultCard", "其他语言版本:", (h: Partial<SearchHit>) => renderWithProviders(<ResultCard hit={makeHit(h)} />)],
  ["CrossLangCard", "关联翻译:", (h: Partial<SearchHit>) => renderWithProviders(<CrossLangCard hit={makeCrossHit(h as Partial<CrossLanguageSearchHit>)} />)],
])("%s 其他译本是可 Tab 的链接", (_name, label, renderIt) => {
  const related = [
    { id: 237 as TextId, lang: "lzh", title: "金剛能斷般若波羅蜜經" },
    { id: 900 as TextId, lang: "en", title: "The Diamond Sutra" },
  ];

  it("每个译本是指向 /texts/{id} 的 <a>，不是带 onClick 的 Tag", () => {
    const { container } = renderIt({ related_translations: related } as Partial<SearchHit>);
    expect(screen.getByText(label)).toBeInTheDocument();
    const row = container.querySelector(".s-card-translations")!;
    expect(row.querySelector(".ant-tag")).toBeNull();
    const links = [...row.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/texts/237", "/texts/900"]);
    expect(links[0]).toHaveTextContent("金剛能斷般若波羅蜜經");
    for (const a of links) expect(a).toHaveClass("s-card-translation-link");
  });
});

// antd 的 blue / geekblue 是全站色板之外的冷蓝（#1300 已在其它页清掉）；搜索结果卡上
// 剩下的语种标签（非汉文）与来源标签改用中性默认 Tag。
describe("搜索结果卡不再用 antd 蓝色系 Tag", () => {
  it("ResultCard 非汉文语种标签是中性的", () => {
    const { container } = renderWithProviders(<ResultCard hit={makeHit({ lang: "en" })} />);
    expect(screen.getByText("英文")).toBeInTheDocument();
    expect(container.querySelector(".ant-tag-blue, .ant-tag-geekblue")).toBeNull();
  });

  it("CrossLangCard 英文标签是中性的", () => {
    const { container } = renderWithProviders(<CrossLangCard hit={makeCrossHit({ lang: "en" })} />);
    expect(container.querySelector(".ant-tag-blue, .ant-tag-geekblue")).toBeNull();
  });
});
