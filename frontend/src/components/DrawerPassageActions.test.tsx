import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DrawerPassageActions from "./DrawerPassageActions";
import { drawerTargetText, DRAWER_TARGET_MAX } from "./ReaderSelectionExtras.types";
import { getVernacular, searchContent, type ContentSearchResponse } from "../api/client";

vi.mock("../api/client", () => ({
  searchContent: vi.fn(),
  submitFeedback: vi.fn(),
  getVernacular: vi.fn(),
}));
const mockVern = vi.mocked(getVernacular);
const mockSearch = vi.mocked(searchContent);

const PASSAGE = "佛告須菩提：\n凡所有相，皆是虛妄。若見諸相非相，\n則見如來。須菩提白佛言";
const QUOTE = "凡所有相，皆是虛妄。若見諸相非相，則見如來。";

function spansOf(passage: string, q: string): [number, number][] {
  // 测试里用最朴素的定位：原文含换行，按去空白后的位置换回原始坐标
  const raw: number[] = [];
  let flat = "";
  for (let i = 0; i < passage.length; i++) if (!/\s/.test(passage[i])) { raw.push(i); flat += passage[i]; }
  const k = flat.indexOf(q);
  return k < 0 ? [] : [[raw[k], raw[k + q.length - 1] + 1]];
}

function renderActions(quoteSpans: [number, number][]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DrawerPassageActions textId={7} juanNum={1} title="金剛般若波羅蜜經" passage={PASSAGE} quoteSpans={quoteSpans}>
          <p data-testid="body">{PASSAGE}</p>
        </DrawerPassageActions>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockVern.mockReset();
  mockSearch.mockReset();
});

describe("drawerTargetText 抽屉作用对象", () => {
  const spans = spansOf(PASSAGE, QUOTE);
  it("无选区：取定位到的原文被引句（去空白），不是模型复述", () => {
    expect(drawerTargetText(PASSAGE, spans, "")).toEqual({ text: QUOTE, from: "quote" });
  });
  it("有选区（≥2 字）优先用选区", () => {
    expect(drawerTargetText(PASSAGE, spans, " 須菩提\n")).toEqual({ text: "須菩提", from: "selection" });
  });
  it("单字选区忽略，回到被引句", () => {
    expect(drawerTargetText(PASSAGE, spans, "相")?.from).toBe("quote");
  });
  it("多段命中取首尾之间的连续原文", () => {
    const multi: [number, number][] = [spansOf(PASSAGE, "凡所有相")[0], spansOf(PASSAGE, "則見如來")[0]];
    expect(drawerTargetText(PASSAGE, multi, "")?.text).toBe("凡所有相，皆是虛妄。若見諸相非相，則見如來");
  });
  it("定位不到引文且无选区：没有作用对象", () => {
    expect(drawerTargetText(PASSAGE, [], "")).toBeNull();
  });
  it("超长截断到上限（后端白话会拒 >200 字）", () => {
    expect(drawerTargetText("字".repeat(300), [[0, 300]], "")?.text).toHaveLength(DRAWER_TARGET_MAX);
  });
});

describe("DrawerPassageActions", () => {
  it("定位到引文：默认作用于被引句，白话带全文语境请求", async () => {
    mockVern.mockResolvedValue({ translation: "凡是一切相都是虚妄的……", uncertain: false, model: "m", prompt_version: "v1", cached: false });
    renderActions(spansOf(PASSAGE, QUOTE));
    expect(screen.getByText(/被引这句/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "白话" }));
    expect(await screen.findByText("凡是一切相都是虚妄的……")).toBeInTheDocument();
    expect(mockVern).toHaveBeenCalledWith({ text_id: 7, sentence: QUOTE, before: "佛告須菩提：", after: "須菩提白佛言" });
    expect(screen.getByText(/仅供参考，以原文为准/)).toBeInTheDocument();
  });

  it("抽屉内划词后改为作用于选区", async () => {
    mockSearch.mockResolvedValue({ total: 0, results: [] } as unknown as ContentSearchResponse);
    renderActions(spansOf(PASSAGE, QUOTE));
    vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "須菩提白佛言" } as unknown as Selection);
    fireEvent.mouseUp(screen.getByTestId("body"));
    expect(screen.getByText(/选中的文字/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "全藏出处" }));
    await screen.findByText("其它经论里没有找到这段文字");
    expect(mockSearch).toHaveBeenCalledWith(expect.objectContaining({ q: "須菩提白佛言", phrase: true }));
    vi.restoreAllMocks();
  });

  it("无引文可定位且未划词：只给提示，不给按钮", () => {
    renderActions([]);
    expect(screen.getByText(/在上方经文中选中一句/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "白话" })).toBeNull();
  });
});
