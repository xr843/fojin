import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import PassageLocateCard from "./PassageLocateCard";
import { locateInfoFrom, snippetOf, LOCATE_SNIPPET_MAX } from "../utils/passageLocate";
import type { ChatRetrieval, ChatSource } from "../api/client";
import type { TextId } from "../types/branded";

const WINDOW = "凡所有相，皆是虛妄。若見諸相非相，則見如來。";

function src(over: Partial<ChatSource> = {}): ChatSource {
  return {
    text_id: 7 as TextId,
    juan_num: 1,
    chunk_index: 3,
    chunk_text: "凡所有相，皆是虛妄。若見諸相非相，則見如來。須菩提白佛言",
    score: 1,
    title_zh: "金剛般若波羅蜜經",
    ...over,
  };
}

const located = (texts: number | null) =>
  src({ located: true, located_window: WINDOW, located_texts: texts });
const plain = src({ text_id: 9 as TextId, title_zh: "金剛經疏" });

describe("PassageLocateCard", () => {
  const track = vi.fn();
  beforeEach(() => {
    track.mockReset();
    vi.stubGlobal("umami", { track });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("没有定位来源时什么都不渲染", () => {
    const { container } = render(<PassageLocateCard sources={[plain]} onOpen={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(track).not.toHaveBeenCalled();
  });

  it("单部命中：写「见于」不写「出自」，显示经名卷号与原文片段，不出现「另见于」", () => {
    render(<PassageLocateCard sources={[located(1), plain]} onOpen={vi.fn()} />);
    const card = screen.getByTestId("passage-locate-card");
    // 界面语言 zh：经名转简体
    expect(card.textContent).toContain("逐字见于《金刚般若波罗蜜经》第 1 卷");
    expect(card.textContent).not.toContain("出自《");
    expect(card.textContent).toContain(`「${WINDOW}」`);
    expect(screen.queryByTestId("passage-locate-also")).toBeNull();
    // 「逐字 ≠ 出处」说明始终在
    expect(card.textContent).toContain("不等于出自此处");
  });

  it("多部命中：写「另见于 N 部典籍」，N 不含本书", () => {
    render(<PassageLocateCard sources={[located(4)]} onOpen={vi.fn()} />);
    expect(screen.getByTestId("passage-locate-also").textContent).toContain("另有至多 3 部典籍含这些语句");
  });

  it("典籍数未知（0/缺省）时不编「另见于」", () => {
    render(<PassageLocateCard sources={[located(0)]} onOpen={vi.fn()} />);
    expect(screen.queryByTestId("passage-locate-also")).toBeNull();
  });

  it("点「打开原文」：按定位块打开抽屉并带窗口做高亮，记点击埋点", () => {
    const onOpen = vi.fn();
    render(<PassageLocateCard sources={[located(2)]} onOpen={onOpen} />);
    fireEvent.click(screen.getByTestId("passage-locate-open"));
    expect(onOpen).toHaveBeenCalledTimes(1);
    const [s, quote] = onOpen.mock.calls[0];
    expect(s).toMatchObject({ text_id: 7, juan_num: 1, chunk_index: 3, title_zh: "金剛般若波羅蜜經" });
    expect(quote).toBe(WINDOW);
    expect(track).toHaveBeenCalledWith("paste_locate_click", { text_id: 7, texts: 2 });
  });

  it("展示埋点一条回答只记一次（重挂载不重复计）", () => {
    const sources = [located(1)];
    const { unmount } = render(<PassageLocateCard sources={sources} onOpen={vi.fn()} />);
    unmount();
    render(<PassageLocateCard sources={sources} onOpen={vi.fn()} />);
    const shows = track.mock.calls.filter((c) => c[0] === "paste_locate_show");
    expect(shows).toHaveLength(1);
    expect(shows[0][1]).toEqual({ text_id: 7, texts: 1, phase: "history" });
  });

  it("流式中：sources 还没来，retrieved.located 就能撑起卡片", () => {
    const retrieval: ChatRetrieval = {
      count: 5,
      titles: ["金剛般若波羅蜜經"],
      located: { text_id: 7, juan_num: 2, chunk_index: 0, title_zh: "金剛般若波羅蜜經", window: WINDOW, texts: 3 },
    };
    render(<PassageLocateCard sources={null} retrieval={retrieval} onOpen={vi.fn()} />);
    expect(screen.getByTestId("passage-locate-card").textContent).toContain("第 2 卷");
    expect(screen.getByTestId("passage-locate-also").textContent).toContain("另有至多 2 部典籍含这些语句");
    expect(track).toHaveBeenCalledWith("paste_locate_show", { text_id: 7, texts: 3, phase: "live" });
  });
});

describe("locateInfoFrom / snippetOf", () => {
  it("sources 优先于 retrieval（入库那份才是准的）", () => {
    const retrieval: ChatRetrieval = { count: 1, titles: [], located: { text_id: 99, juan_num: 9, window: "x", texts: 1 } };
    expect(locateInfoFrom([located(2)], retrieval)?.textId).toBe(7);
    expect(locateInfoFrom([plain], retrieval)?.textId).toBe(99);
    expect(locateInfoFrom(null, null)).toBeNull();
  });

  it("片段超长截断加省略号，按字符而非 UTF-16 单元截", () => {
    const long = "𠀀".repeat(LOCATE_SNIPPET_MAX + 5);
    const out = snippetOf(long);
    expect(Array.from(out)).toHaveLength(LOCATE_SNIPPET_MAX + 1);
    expect(out.endsWith("…")).toBe(true);
    expect(snippetOf("短句")).toBe("短句");
  });
});
