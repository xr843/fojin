import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HelmetProvider } from "react-helmet-async";
import { MemoryRouter, Route, Routes } from "react-router";
import i18n from "../i18n";
import zh from "../../public/locales/zh/translation.json";
import VerifyPage from "./VerifyPage";
import { verifyClaim, type ClaimVerdict } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, verifyClaim: vi.fn() };
});

const locale = zh as unknown as Record<string, string>;

const DIAMOND = {
  text_id: 7,
  cbeta_id: "T0235",
  title_zh: "金剛般若波羅蜜經",
  juan_num: 1,
  reader_url: "https://fojin.app/texts/7/read?juan=1",
  canon_class: "sutra" as const,
};

function verdict(v: Partial<ClaimVerdict>): ClaimVerdict {
  return { query: "", verdict: "absent", source_class: null, segments: [], ...v };
}

function renderAt(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/verify" element={<VerifyPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

beforeAll(async () => {
  await i18n.changeLanguage("zh");
});

afterEach(() => {
  vi.mocked(verifyClaim).mockReset();
});

describe("VerifyPage", () => {
  it("checks the sentence in ?q= on load and says it is from a sutra", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(
      verdict({
        verdict: "sutra",
        source_class: "sutra",
        segments: [{ text: "一切有为法，如梦幻泡影", found: true, sources: [DIAMOND], similarity: 1 , close: null }],
      }),
    );
    renderAt("/verify?q=一切有为法，如梦幻泡影");
    expect(await screen.findByText(locale["verify.verdict.sutra"])).toBeInTheDocument();
    expect(verifyClaim).toHaveBeenCalledWith("一切有为法，如梦幻泡影");
    // Title rendered in the reader's script, linked in-app (not to the absolute host).
    const link = screen.getByRole("link", { name: /金刚般若波罗蜜经/ });
    expect(link.getAttribute("href")).toBe("/texts/7/read?juan=1");
    // The result card is the server-rendered image for this q.
    const img = screen.getByAltText(new RegExp(locale["verify.card_alt"]));
    expect(img.getAttribute("src")).toContain("/api/og/verify?q=");
  });

  it("names the kind of work when the line is not from a sutra", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(
      verdict({
        verdict: "not_sutra",
        source_class: "school",
        segments: [{ text: "菩提本无树", found: true, sources: [{ ...DIAMOND, canon_class: "school" }], similarity: 1 , close: null }],
      }),
    );
    renderAt("/verify?q=菩提本无树");
    const expected = locale["verify.verdict.not_sutra"].replace("{{cls}}", locale["verify.class.school"]);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });

  it("marks the invented tail of a partly real saying", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(
      verdict({
        verdict: "partial",
        segments: [
          { text: "一切有为法", found: true, sources: [DIAMOND], similarity: 1 , close: null },
          { text: "看开便是福", found: false, sources: [], similarity: 0.2, close: null },
        ],
      }),
    );
    renderAt("/verify?q=一切有为法，看开便是福");
    expect(await screen.findByText(locale["verify.verdict.partial"])).toBeInTheDocument();
    const missing = screen.getByText("看开便是福").closest("li");
    expect(missing?.className).toContain("is-missing");
  });

  it("says plainly when nothing is in the canon", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(
      verdict({ verdict: "absent", segments: [{ text: "一切都是最好的安排", found: false, sources: [], similarity: 0.3, close: null }] }),
    );
    const { container } = renderAt("/verify?q=一切都是最好的安排");
    await waitFor(() =>
      expect(container.querySelector(".verify-badge")?.textContent).toBe(locale["verify.verdict.absent"]),
    );
  });

  it("shows the canon's own wording when the popular version is a character off", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(
      verdict({
        verdict: "variant",
        source_class: "sutra",
        segments: [
          {
            text: "犹如莲花不著水，亦如日月不住空",
            found: false,
            sources: [],
            similarity: 0.93,
            close: {
              text_id: 297,
              juan_num: 1,
              reader_url: "https://fojin.app/texts/297/read?juan=1",
              similarity: 0.93,
              window_normalised: "犹如莲花不着水亦如日月不着空",
              cbeta_id: "T0297",
              title_zh: "普賢菩薩行願讚",
              canon_class: "sutra",
            },
          },
        ],
      }),
    );
    const { container } = renderAt("/verify?q=犹如莲花不著水，亦如日月不住空");
    await waitFor(() =>
      expect(container.querySelector(".verify-badge")?.textContent).toBe(locale["verify.verdict.variant"]),
    );
    expect(screen.getByText("「犹如莲花不着水亦如日月不着空」")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /普贤菩萨行愿赞/ }).getAttribute("href")).toBe("/texts/297/read?juan=1");
    expect(container.querySelectorAll(".verify-seg.is-close")).toHaveLength(1);
  });

  it("keeps result pages out of the index but not the entry page", async () => {
    vi.mocked(verifyClaim).mockResolvedValue(verdict({}));
    renderAt("/verify?q=一切都是最好的安排");
    await waitFor(() =>
      expect(document.head.querySelector('meta[name="robots"]')?.getAttribute("content")).toBe("noindex, follow"),
    );
    expect(document.head.querySelector('link[rel="canonical"]')?.getAttribute("href")).toBe("https://fojin.app/verify");
  });

  it("does not call the API on the bare entry page", async () => {
    renderAt("/verify");
    await waitFor(() => expect(document.head.querySelector('link[rel="canonical"]')).not.toBeNull());
    expect(verifyClaim).not.toHaveBeenCalled();
    expect(document.head.querySelector('meta[name="robots"]')).toBeNull();
  });
});
