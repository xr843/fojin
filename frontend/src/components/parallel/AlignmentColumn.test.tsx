import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { forwardRef } from "react";
import AlignmentColumn from "./AlignmentColumn";
import type { ParallelTextContent, JuanAlignmentResponse } from "../../api/client";

function textFixture(overrides: Partial<ParallelTextContent> = {}): ParallelTextContent {
  return {
    text_id: 100 as ParallelTextContent["text_id"],
    cbeta_id: "T0251",
    title_zh: "般若波羅蜜多心經",
    translator: "玄奘",
    lang: "lzh",
    juan_num: 1,
    content: "觀自在菩薩。\n行深般若波羅蜜多時。\n照見五蘊皆空。",
    ...overrides,
  };
}

function alignmentFixture(): JuanAlignmentResponse {
  return {
    text_id: 100,
    juan_num: 1,
    total_chunks: 3,
    chunks_with_parallels: 2,
    entries: [
      {
        chunk_index: 0,
        chunk_text: "觀自在菩薩。",
        parallels: [],
      },
      {
        chunk_index: 1,
        chunk_text: "行深般若波羅蜜多時。",
        parallels: [],
      },
    ],
  };
}

describe("AlignmentColumn", () => {
  it("renders title, translator, and content", () => {
    render(
      <AlignmentColumn text={textFixture()} alignment={null} />
    );
    expect(screen.getByText(/般若波羅蜜多心經/)).toBeTruthy();
    expect(screen.getByText(/玄奘/)).toBeTruthy();
    expect(screen.getByText(/觀自在菩薩/)).toBeTruthy();
  });

  it("renders content split into paragraphs by newline", () => {
    const { container } = render(
      <AlignmentColumn text={textFixture()} alignment={null} />
    );
    const paragraphs = container.querySelectorAll(".parallel-paragraph");
    expect(paragraphs.length).toBe(3);
  });

  it("wraps paragraphs matching alignment chunk_text with data-chunk-index", () => {
    const { container } = render(
      <AlignmentColumn text={textFixture()} alignment={alignmentFixture()} />
    );
    const indexed = container.querySelectorAll("[data-chunk-index]");
    expect(indexed.length).toBe(2);
    expect(indexed[0].getAttribute("data-chunk-index")).toBe("0");
    expect(indexed[1].getAttribute("data-chunk-index")).toBe("1");
  });

  it("forwards scroll container ref", () => {
    let captured: HTMLElement | null = null;
    const Wrapper = forwardRef<HTMLDivElement>((_, ref) => (
      <AlignmentColumn text={textFixture()} alignment={null} scrollRef={ref} />
    ));
    Wrapper.displayName = "Wrapper";

    render(
      <Wrapper
        ref={(el) => {
          captured = el;
        }}
      />
    );
    expect(captured).toBeTruthy();
    expect(captured?.classList.contains("parallel-column-scroll")).toBe(true);
  });

  it("renders lang chip", () => {
    render(<AlignmentColumn text={textFixture({ lang: "pi" })} alignment={null} />);
    expect(screen.getByText("Pāli")).toBeTruthy();
  });
});
