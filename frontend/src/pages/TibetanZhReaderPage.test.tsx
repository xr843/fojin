import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { HelmetProvider } from "react-helmet-async";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AxiosError, AxiosHeaders } from "axios";
import TibetanZhReaderPage from "./TibetanZhReaderPage";
import { getTibetanZhDocument, getTibetanZhIndex } from "../api/tibetanZh";

vi.mock("../api/tibetanZh", async (orig) => ({
  ...(await orig<typeof import("../api/tibetanZh")>()),
  getTibetanZhIndex: vi.fn(),
  getTibetanZhDocument: vi.fn(),
}));

const scrolled: string[] = [];
beforeAll(() => {
  Element.prototype.scrollIntoView = function (this: Element) {
    scrolled.push(this.id);
  };
});

const DOC = [
  "# 真实光明论",
  "",
  "## 序分",
  "",
  "##### 〔1〕",
  "",
  "> [244B]ཡང་དག་བདུད་རྩི།",
  "",
  "已善得真实甘露〔校注 1〕。",
  "",
  "## 校注",
  "",
  "1. **〔1〕** 校注正文。",
].join("\n");

beforeEach(() => {
  scrolled.length = 0;
  localStorage.clear();
  vi.mocked(getTibetanZhIndex).mockResolvedValue({
    repo: "https://github.com/xr843/tibetan-canon-zh",
    fetched_at: 0,
    stale: false,
    items: [
      {
        id: "T-2796",
        title: "真实光明论",
        au: "莲花戒",
        part: "丹珠尔",
        cat: "中观部",
        rv: "经两层 AI 审核",
        md: "https://github.com/xr843/tibetan-canon-zh/blob/main/x.md",
        pdf: "https://github.com/xr843/tibetan-canon-zh/releases/download/translations/T-2796.pdf",
        docx: null,
      },
    ],
  });
  vi.mocked(getTibetanZhDocument).mockResolvedValue(DOC);
});

function renderAt(path = "/tibetan-zh/T-2796") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <HelmetProvider>
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/tibetan-zh/:id" element={<TibetanZhReaderPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  );
}

describe("TibetanZhReaderPage", () => {
  it("页顶有 AI 提示、本部审核情况与源文件/PDF 链接（索引里没有的 Word 不出现）", async () => {
    renderAt();
    expect(await screen.findByText("AI 译稿，未经懂藏文的专家审定，仅供研究参考")).toBeInTheDocument();
    expect(await screen.findByText(/经两层 AI 审核/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /GitHub 源文件/ })).toHaveAttribute(
      "href",
      "https://github.com/xr843/tibetan-canon-zh/blob/main/x.md",
    );
    expect(screen.getByRole("link", { name: /PDF/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Word/ })).toBeNull();
    expect(screen.getByRole("link", { name: "github.com/xr843/tibetan-canon-zh" })).toHaveAttribute(
      "href",
      "https://github.com/xr843/tibetan-canon-zh",
    );
  });

  it("藏文引用块标 lang=bo；「只看汉文」开关隐藏它（并记住选择）", async () => {
    const { container } = renderAt();
    await screen.findByText(/已善得真实甘露/);
    const bo = container.querySelector("blockquote.tz-bo");
    expect(bo).not.toBeNull();
    expect(bo).toHaveAttribute("lang", "bo");

    const page = container.querySelector(".tz-reader-page")!;
    expect(page.classList.contains("tz-zh-only")).toBe(false);
    fireEvent.click(screen.getByRole("switch"));
    expect(page.classList.contains("tz-zh-only")).toBe(true);
    expect(localStorage.getItem("fojin-tibetan-zh-zh-only")).toBe("1");
  });

  it("点〔校注 N〕跳到校注，点 ↩ 跳回刚才那个标记", async () => {
    const { container } = renderAt();
    const ref = await screen.findByRole("link", { name: "〔校注 1〕" });
    fireEvent.click(ref);
    await waitFor(() => expect(scrolled).toContain("tz-note-0-1"));
    expect(container.querySelector("#tz-note-0-1")?.closest("li")?.textContent).toContain("校注正文");

    fireEvent.click(screen.getByRole("link", { name: "返回正文" }));
    await waitFor(() => expect(scrolled).toContain(ref.id));
  });

  it("目录列出各「## 」节，点了跳到对应块", async () => {
    renderAt();
    const toc = await screen.findByRole("complementary", { name: "目录" });
    const link = Array.from(toc.querySelectorAll("a")).find((a) => a.textContent === "校注")!;
    fireEvent.click(link);
    await waitFor(() => expect(scrolled.some((id) => id.startsWith("tz-chunk-"))).toBe(true));
  });

  it("不存在的编号显示「没有这部译稿」", async () => {
    vi.mocked(getTibetanZhDocument).mockRejectedValue(
      new AxiosError("nf", "ERR_BAD_REQUEST", undefined, undefined, {
        status: 404,
        statusText: "Not Found",
        data: {},
        headers: {},
        config: { headers: new AxiosHeaders() },
      }),
    );
    renderAt("/tibetan-zh/T-0001");
    expect(await screen.findByText("没有这部译稿。")).toBeInTheDocument();
  });
});
