import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import ChatRelatedTerms from "./ChatRelatedTerms";

const getRelatedTerms = vi.fn();
vi.mock("../api/client", () => ({ getRelatedTerms: (q: string) => getRelatedTerms(q) }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (k: string) => ({ "chat.related_terms.title": "相关词条", "chat.related_terms.note": "辞典释义，帮助理解名相；不是经文出处", "chat.related_terms.tag": "词条" })[k] ?? k,
    i18n: { language: "zh" },
  }),
}));

function renderIt(q: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ChatRelatedTerms question={q} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("问答相关词条卡片", () => {
  beforeEach(() => getRelatedTerms.mockReset());

  it("每张卡标「词条」与辞典名，区块注明不是经文出处，点开去辞典页该辞典", async () => {
    getRelatedTerms.mockResolvedValue([
      { id: 1, headword: "三藏", source_code: "foguang", source_name: "佛光大辭典", excerpt: "梵語 tri-piṭaka。指經藏、律藏、論藏。" },
    ]);
    renderIt("什么是三藏");
    const link = await screen.findByRole("link");
    expect(getRelatedTerms).toHaveBeenCalledWith("什么是三藏");
    expect(link.textContent).toContain("词条");
    expect(link.textContent).toContain("三藏");
    expect(link.textContent).toContain("佛光大辞典"); // 辞典名按界面语言转简
    expect(link.getAttribute("href")).toBe("/dictionary?q=%E4%B8%89%E8%97%8F&source=foguang");
    expect(screen.getByText("辞典释义，帮助理解名相；不是经文出处")).toBeTruthy();
  });

  it("没有词条时整块不显示", async () => {
    getRelatedTerms.mockResolvedValue([]);
    const { container } = renderIt("你好");
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector(".chat-related-terms")).toBeNull();
  });
});
