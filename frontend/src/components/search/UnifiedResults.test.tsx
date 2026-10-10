import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import UnifiedResults from "./UnifiedResults";
import type { UnifiedSearchResponse } from "../../api/client";
import type { TextId } from "../../types/branded";

vi.mock("../../api/client", () => ({
  getAlignmentCatalog: vi.fn(async () => ({ entries: [] })),
}));

// 彩色 emoji 依赖系统字体：没装彩色 emoji 字体的机器上 🔤📖🔍 渲染成豆腐块，
// 且和全站导航那套 @ant-design/icons 线性图标不是一个语汇。
const EMOJI = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

const data: UnifiedSearchResponse = {
  query: "金剛經",
  errors: {},
  sections: {
    dictionary: [{ id: 1, headword: "金剛經", reading: null, definition: "一卷", source: "佛光大辭典", url: "" }],
    catalog: {
      total: 1,
      results: [
        {
          id: 236 as TextId, taisho_id: "T0235", cbeta_id: "T0235", title_zh: "金剛般若波羅蜜經",
          translator: null, dynasty: null, category: null, cbeta_url: null, has_content: true,
          source_code: "cbeta", lang: "lzh", score: 1, highlight: null, related_translations: [],
        },
      ],
    },
    content: {
      total: 1,
      results: [
        {
          text_id: 99 as TextId, cbeta_id: "X1636", title_zh: "金剛經感應分類輯要", translator: null,
          dynasty: null, juan_num: 1, lang: "lzh", source_code: "cbeta", highlight: ["<em>金剛經</em>"],
          score: 1, matched_juan_count: 1, matched_juans: [{ juan_num: 1, highlight: ["x"], score: 1 }],
        },
      ],
    },
  },
};

describe("UnifiedResults 区块标题", () => {
  it("三个区块标题不含 emoji，改用线性图标", () => {
    const qc = new QueryClient();
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <UnifiedResults data={data} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const heads = screen.getAllByRole("heading", { level: 3 });
    expect(heads.map((h) => h.textContent?.trim())).toEqual(["辞典释义", "经文标题", "经文内文片段"]);
    for (const h of heads) {
      expect(h.textContent).not.toMatch(EMOJI);
      const icon = h.querySelector(".anticon");
      expect(icon).not.toBeNull();
      // 图标纯装饰：不进读屏（antd 图标默认 role="img"+aria-label，会把「book」念出来）
      expect(icon).toHaveAttribute("aria-hidden", "true");
    }
  });
});
