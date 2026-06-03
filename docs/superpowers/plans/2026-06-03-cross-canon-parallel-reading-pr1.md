# Cross-Canon Parallel Reading PR-1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `ParallelReaderPage` from 2-column independent scrolling to 2-3 column synchronized scrolling with chunk-anchor based alignment (hybrid algorithm: anchor when alignment exists, proportional fallback).

**Architecture:** Pure-frontend feature; uses existing `getParallelRead` + `getJuanAlignment` APIs. New isolated hook `useSyncScroll` + helper `buildAlignmentMap` + presentational `AlignmentColumn`. `ParallelReaderPage` rewritten to N-column model with backward-compatible URLs.

**Tech Stack:** React 19 · TypeScript · Vite · Vitest · @testing-library/react · Ant Design 5 · react-router-dom · @tanstack/react-query

**Spec:** `docs/superpowers/specs/2026-06-03-cross-canon-parallel-reading-v1-design.md`

---

## File Structure

| File | Role |
|---|---|
| `frontend/src/components/parallel/buildAlignmentMap.ts` | Pure helper: builds `{ fromTextId → fromChunkIndex → { toTextId → toChunkIndex } }` lookup from `JuanAlignmentResponse[]` |
| `frontend/src/components/parallel/buildAlignmentMap.test.ts` | Unit tests for the helper |
| `frontend/src/components/parallel/useSyncScroll.ts` | Hook: wires `IntersectionObserver` per column ref + applies hybrid sync algorithm |
| `frontend/src/components/parallel/useSyncScroll.test.tsx` | Unit tests with mocked refs |
| `frontend/src/components/parallel/AlignmentColumn.tsx` | Presentational column: header + content + chunk markup |
| `frontend/src/components/parallel/AlignmentColumn.test.tsx` | Unit tests for rendering + chunk markup |
| `frontend/src/components/parallel/types.ts` | Shared types for V1 parallel reader (column model + alignment map) |
| `frontend/src/pages/ParallelReaderPage.tsx` | Rewritten to N-column with sync scroll (existing file replaced) |
| `frontend/src/styles/parallel.css` | Extended with V1 grid classes + chunk highlight styles |

---

## Task 0: Setup branch

**Files:** none

- [ ] **Step 0.1: Switch to master and pull latest**

```bash
cd /home/lqsxi/projects/fojin
git checkout master
git pull origin master
```

- [ ] **Step 0.2: Create PR-1 branch**

```bash
git checkout -b feat/parallel-reader-v1-sync-scroll
```

---

## Task 1: Shared types

**Files:**
- Create: `frontend/src/components/parallel/types.ts`

- [ ] **Step 1.1: Write the types file**

```typescript
// frontend/src/components/parallel/types.ts
import type { ParallelTextContent, JuanAlignmentResponse } from "../../api/client";

/** A single column's data (text content + its own alignment table). */
export interface ColumnData {
  text: ParallelTextContent;
  /** Alignment data for this column (its chunks + parallels to other columns). May be null when API failed. */
  alignment: JuanAlignmentResponse | null;
}

/**
 * For column A.chunk_index = i, what is the corresponding chunk_index in column B?
 *
 *   map[textA_id]?.[chunk_i]?.[textB_id] === chunk_j_in_B
 *
 * Symmetric: built so both (A→B) and (B→A) entries exist.
 */
export type AlignmentMap = Record<number, Record<number, Record<number, number>>>;
```

- [ ] **Step 1.2: Commit**

```bash
git add frontend/src/components/parallel/types.ts
git commit -m "feat(parallel): shared V1 types (ColumnData, AlignmentMap)"
```

---

## Task 2: `buildAlignmentMap` helper (TDD)

**Files:**
- Create: `frontend/src/components/parallel/buildAlignmentMap.test.ts`
- Create: `frontend/src/components/parallel/buildAlignmentMap.ts`

- [ ] **Step 2.1: Write the failing test**

```typescript
// frontend/src/components/parallel/buildAlignmentMap.test.ts
import { describe, it, expect } from "vitest";
import { buildAlignmentMap } from "./buildAlignmentMap";
import type { JuanAlignmentResponse } from "../../api/client";

function alignmentFixture(
  text_id: number,
  entries: Array<{ chunk_index: number; parallels: Array<{ text_id: number; chunk_index: number }> }>,
): JuanAlignmentResponse {
  return {
    text_id,
    juan_num: 1,
    total_chunks: entries.length,
    chunks_with_parallels: entries.length,
    entries: entries.map((e) => ({
      chunk_index: e.chunk_index,
      chunk_text: `chunk_${e.chunk_index}_of_${text_id}`,
      parallels: e.parallels.map((p) => ({
        text_id: p.text_id,
        juan_num: 1,
        chunk_index: p.chunk_index,
        chunk_text: `chunk_${p.chunk_index}_of_${p.text_id}`,
        lang: "lzh",
        title: "",
        confidence: 1.0,
      })),
    })),
  };
}

describe("buildAlignmentMap", () => {
  it("returns empty map for empty input", () => {
    expect(buildAlignmentMap([])).toEqual({});
  });

  it("indexes A → B with A's alignment data", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
      { chunk_index: 1, parallels: [{ text_id: 200, chunk_index: 6 }] },
    ]);
    const map = buildAlignmentMap([a]);
    expect(map[100][0][200]).toBe(5);
    expect(map[100][1][200]).toBe(6);
  });

  it("builds bidirectional index when both sides provided", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
    ]);
    const b = alignmentFixture(200, [
      { chunk_index: 5, parallels: [{ text_id: 100, chunk_index: 0 }] },
    ]);
    const map = buildAlignmentMap([a, b]);
    expect(map[100][0][200]).toBe(5);
    expect(map[200][5][100]).toBe(0);
  });

  it("handles chunks with multiple parallels (picks first per text)", () => {
    const a = alignmentFixture(100, [
      {
        chunk_index: 0,
        parallels: [
          { text_id: 200, chunk_index: 5 },
          { text_id: 300, chunk_index: 7 },
        ],
      },
    ]);
    const map = buildAlignmentMap([a]);
    expect(map[100][0][200]).toBe(5);
    expect(map[100][0][300]).toBe(7);
  });

  it("ignores null alignment entries (failed API)", () => {
    const a = alignmentFixture(100, [
      { chunk_index: 0, parallels: [{ text_id: 200, chunk_index: 5 }] },
    ]);
    const map = buildAlignmentMap([a, null]);
    expect(map[100][0][200]).toBe(5);
  });
});
```

- [ ] **Step 2.2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/parallel/buildAlignmentMap.test.ts
```

Expected: FAIL with "Cannot find module './buildAlignmentMap'"

- [ ] **Step 2.3: Write minimal implementation**

```typescript
// frontend/src/components/parallel/buildAlignmentMap.ts
import type { JuanAlignmentResponse } from "../../api/client";
import type { AlignmentMap } from "./types";

/**
 * Build a lookup table mapping (fromTextId, fromChunkIndex, toTextId) → toChunkIndex.
 *
 * Null entries are skipped (allows graceful degradation when a per-column alignment
 * fetch failed). Multiple parallels for the same (chunk, toText) keep the first.
 */
export function buildAlignmentMap(
  alignments: Array<JuanAlignmentResponse | null>,
): AlignmentMap {
  const map: AlignmentMap = {};
  for (const a of alignments) {
    if (!a) continue;
    const fromId = a.text_id;
    map[fromId] ??= {};
    for (const entry of a.entries) {
      map[fromId][entry.chunk_index] ??= {};
      for (const p of entry.parallels) {
        if (map[fromId][entry.chunk_index][p.text_id] === undefined) {
          map[fromId][entry.chunk_index][p.text_id] = p.chunk_index;
        }
      }
    }
  }
  return map;
}
```

- [ ] **Step 2.4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/parallel/buildAlignmentMap.test.ts
```

Expected: PASS (5 tests)

- [ ] **Step 2.5: Commit**

```bash
git add frontend/src/components/parallel/buildAlignmentMap.ts frontend/src/components/parallel/buildAlignmentMap.test.ts
git commit -m "feat(parallel): buildAlignmentMap helper with bidirectional index"
```

---

## Task 3: `useSyncScroll` hook (TDD)

**Files:**
- Create: `frontend/src/components/parallel/useSyncScroll.test.tsx`
- Create: `frontend/src/components/parallel/useSyncScroll.ts`

- [ ] **Step 3.1: Write the failing test**

```typescript
// frontend/src/components/parallel/useSyncScroll.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSyncScroll } from "./useSyncScroll";
import type { AlignmentMap } from "./types";

// jsdom doesn't implement scrollTo on elements
function makeColumnEl(textId: number, chunks: number[]): HTMLDivElement {
  const el = document.createElement("div");
  el.dataset.textId = String(textId);
  Object.defineProperty(el, "scrollHeight", { value: 1000, configurable: true });
  Object.defineProperty(el, "clientHeight", { value: 200, configurable: true });
  el.scrollTop = 0;
  // Add chunk nodes
  for (const idx of chunks) {
    const span = document.createElement("span");
    span.dataset.chunkIndex = String(idx);
    Object.defineProperty(span, "offsetTop", { value: idx * 100, configurable: true });
    Object.defineProperty(span, "offsetHeight", { value: 80, configurable: true });
    el.appendChild(span);
  }
  // Stub scrollTo
  el.scrollTo = vi.fn((opts: ScrollToOptions) => {
    el.scrollTop = (opts as { top: number }).top;
  }) as unknown as Element["scrollTo"];
  return el;
}

describe("useSyncScroll", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  it("syncs follower to driver via anchor when alignment exists", () => {
    const colA = makeColumnEl(100, [0, 1, 2]);
    const colB = makeColumnEl(200, [5, 6, 7]);
    const map: AlignmentMap = { 100: { 1: { 200: 6 } }, 200: { 6: { 100: 1 } } };
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // Simulate scrolling A so that chunk_index=1 is at top
    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20); // debounce
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 600 }));
    // chunk 6 in B has offsetTop = 6*100 = 600
  });

  it("falls back to proportional when no anchor for visible chunk", () => {
    const colA = makeColumnEl(100, [0]);
    const colB = makeColumnEl(200, [0]);
    // Map has no entry for A.chunk 0 → B
    const map: AlignmentMap = {};
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // Scroll A to 50% (scrollTop=400 since scrollHeight=1000, clientHeight=200, max=800)
    colA.scrollTop = 400;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 400 }));
  });

  it("suppresses programmatic scroll feedback loop (80ms guard)", () => {
    const colA = makeColumnEl(100, [0, 1]);
    const colB = makeColumnEl(200, [5, 6]);
    const map: AlignmentMap = { 100: { 1: { 200: 6 } }, 200: { 6: { 100: 1 } } };
    const refs = { current: [{ textId: 100, el: colA }, { textId: 200, el: colB }] };

    renderHook(() => useSyncScroll(refs, map));

    // First: user scrolls A, B receives programmatic scroll
    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });
    (colB.scrollTo as ReturnType<typeof vi.fn>).mockClear();
    (colA.scrollTo as ReturnType<typeof vi.fn>).mockClear();

    // Now: B receives its own scroll event (echo) within 80ms — should NOT trigger sync
    colB.scrollTop = 600;
    act(() => {
      colB.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colA.scrollTo).not.toHaveBeenCalled();
  });

  it("syncs 3 columns when driver scrolls", () => {
    const colA = makeColumnEl(100, [0, 1]);
    const colB = makeColumnEl(200, [5, 6]);
    const colC = makeColumnEl(300, [10, 11]);
    const map: AlignmentMap = {
      100: { 1: { 200: 6, 300: 11 } },
    };
    const refs = {
      current: [
        { textId: 100, el: colA },
        { textId: 200, el: colB },
        { textId: 300, el: colC },
      ],
    };

    renderHook(() => useSyncScroll(refs, map));

    colA.scrollTop = 100;
    act(() => {
      colA.dispatchEvent(new Event("scroll"));
      vi.advanceTimersByTime(20);
    });

    expect(colB.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 600 }));
    expect(colC.scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 1100 }));
  });
});
```

- [ ] **Step 3.2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/parallel/useSyncScroll.test.tsx
```

Expected: FAIL with "Cannot find module './useSyncScroll'"

- [ ] **Step 3.3: Write the hook implementation**

```typescript
// frontend/src/components/parallel/useSyncScroll.ts
import { useEffect, useRef } from "react";
import type { AlignmentMap } from "./types";

export interface ColumnRef {
  textId: number;
  el: HTMLElement | null;
}

interface ColumnRefArray {
  current: ColumnRef[];
}

const DEBOUNCE_MS = 16;
const SUPPRESS_MS = 80;

/**
 * Find the top-most visible `[data-chunk-index]` element within the scroll container.
 * Returns its chunk_index, or null if none in view.
 */
function topVisibleChunk(el: HTMLElement): number | null {
  const chunks = el.querySelectorAll<HTMLElement>("[data-chunk-index]");
  const scrollTop = el.scrollTop;
  for (const chunk of chunks) {
    if (chunk.offsetTop + chunk.offsetHeight >= scrollTop) {
      const idx = Number(chunk.dataset.chunkIndex);
      return Number.isNaN(idx) ? null : idx;
    }
  }
  return null;
}

/**
 * Compute the scrollTop in `target` that brings chunk_index=N to the top of the viewport.
 * Returns null if the chunk node is not found.
 */
function scrollTopForChunk(target: HTMLElement, chunkIndex: number): number | null {
  const node = target.querySelector<HTMLElement>(`[data-chunk-index="${chunkIndex}"]`);
  return node ? node.offsetTop : null;
}

/**
 * Compute proportional scrollTop given a driver's scroll position.
 */
function proportionalScrollTop(driver: HTMLElement, target: HTMLElement): number {
  const driverMax = driver.scrollHeight - driver.clientHeight;
  if (driverMax <= 0) return 0;
  const pct = driver.scrollTop / driverMax;
  const targetMax = target.scrollHeight - target.clientHeight;
  return Math.round(pct * Math.max(targetMax, 0));
}

/**
 * Hybrid sync scroll: anchor-based when alignment exists between the driver's top-visible
 * chunk and a follower; proportional fallback otherwise.
 *
 * Suppress window prevents programmatic-scroll feedback loops across columns.
 */
export function useSyncScroll(refs: ColumnRefArray, map: AlignmentMap): void {
  const suppressUntil = useRef<Map<HTMLElement, number>>(new Map());
  const debounceTimer = useRef<Map<HTMLElement, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const cols = refs.current.filter((c): c is ColumnRef & { el: HTMLElement } => !!c.el);
    if (cols.length < 2) return;

    function onScroll(driver: ColumnRef & { el: HTMLElement }) {
      const existing = debounceTimer.current.get(driver.el);
      if (existing) clearTimeout(existing);
      const timer = setTimeout(() => {
        const now = Date.now();
        const suppressEnd = suppressUntil.current.get(driver.el) ?? 0;
        if (now < suppressEnd) return;

        const driverChunk = topVisibleChunk(driver.el);
        for (const follower of cols) {
          if (follower.el === driver.el) continue;
          let targetTop: number | null = null;

          // Anchor-based
          if (driverChunk !== null) {
            const followerChunk = map[driver.textId]?.[driverChunk]?.[follower.textId];
            if (followerChunk !== undefined) {
              targetTop = scrollTopForChunk(follower.el, followerChunk);
            }
          }
          // Proportional fallback
          if (targetTop === null) {
            targetTop = proportionalScrollTop(driver.el, follower.el);
          }

          suppressUntil.current.set(follower.el, Date.now() + SUPPRESS_MS);
          follower.el.scrollTo({ top: targetTop, behavior: "auto" });
        }
      }, DEBOUNCE_MS);
      debounceTimer.current.set(driver.el, timer);
    }

    const handlers = cols.map((c) => {
      const h = () => onScroll(c);
      c.el.addEventListener("scroll", h, { passive: true });
      return { el: c.el, h };
    });

    return () => {
      for (const { el, h } of handlers) el.removeEventListener("scroll", h);
      for (const t of debounceTimer.current.values()) clearTimeout(t);
      debounceTimer.current.clear();
      suppressUntil.current.clear();
    };
    // refs and map are stable per render — rebind only when the column set / alignment changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refs.current.map((c) => c.textId).join(","), JSON.stringify(map)]);
}
```

- [ ] **Step 3.4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/parallel/useSyncScroll.test.tsx
```

Expected: PASS (4 tests)

- [ ] **Step 3.5: Commit**

```bash
git add frontend/src/components/parallel/useSyncScroll.ts frontend/src/components/parallel/useSyncScroll.test.tsx
git commit -m "feat(parallel): useSyncScroll hook with hybrid anchor+proportional algorithm"
```

---

## Task 4: `AlignmentColumn` presentational component (TDD)

**Files:**
- Create: `frontend/src/components/parallel/AlignmentColumn.test.tsx`
- Create: `frontend/src/components/parallel/AlignmentColumn.tsx`

- [ ] **Step 4.1: Write the failing test**

```tsx
// frontend/src/components/parallel/AlignmentColumn.test.tsx
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
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/parallel/AlignmentColumn.test.tsx
```

Expected: FAIL with "Cannot find module './AlignmentColumn'"

- [ ] **Step 4.3: Write the component**

```tsx
// frontend/src/components/parallel/AlignmentColumn.tsx
import type { Ref } from "react";
import { Card, Tag } from "antd";
import type { ParallelTextContent, JuanAlignmentResponse } from "../../api/client";

const LANG_LABEL: Record<string, string> = {
  lzh: "汉",
  pi: "Pāli",
  sa: "Sanskrit",
  bo: "བོ་",
  en: "English",
};

const LANG_COLOR: Record<string, string> = {
  lzh: "gold",
  pi: "cyan",
  sa: "purple",
  bo: "magenta",
  en: "geekblue",
};

interface Props {
  text: ParallelTextContent;
  alignment: JuanAlignmentResponse | null;
  scrollRef?: Ref<HTMLDivElement>;
}

/** Split raw content into paragraph lines, normalising whitespace. */
function splitParagraphs(content: string): string[] {
  return content
    .split(/\r?\n+/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0);
}

/**
 * Build a Map<paragraphText, chunkIndex> so paragraphs matching alignment chunks
 * get a data-chunk-index attribute. We match by substring (chunk_text contained
 * in paragraph) to be robust against trailing punctuation differences.
 */
function buildChunkIndex(alignment: JuanAlignmentResponse | null): Map<string, number> {
  const map = new Map<string, number>();
  if (!alignment) return map;
  for (const entry of alignment.entries) {
    const key = entry.chunk_text.trim();
    if (key.length > 0 && !map.has(key)) {
      map.set(key, entry.chunk_index);
    }
  }
  return map;
}

function chunkIndexFor(paragraph: string, chunkIndex: Map<string, number>): number | null {
  // exact match first
  const exact = chunkIndex.get(paragraph);
  if (exact !== undefined) return exact;
  // substring match (chunk_text inside paragraph, or paragraph inside chunk_text)
  for (const [key, idx] of chunkIndex.entries()) {
    if (paragraph.includes(key) || key.includes(paragraph)) return idx;
  }
  return null;
}

export default function AlignmentColumn({ text, alignment, scrollRef }: Props) {
  const paragraphs = splitParagraphs(text.content);
  const chunkIndex = buildChunkIndex(alignment);

  return (
    <Card
      size="small"
      className="parallel-column-card"
      title={
        <div className="parallel-column-header">
          <span className="parallel-column-title">{text.title_zh}</span>
          {text.translator && <span className="parallel-column-translator">{text.translator}</span>}
          <Tag color={LANG_COLOR[text.lang] || "default"} className="parallel-column-lang">
            {LANG_LABEL[text.lang] || text.lang}
          </Tag>
        </div>
      }
    >
      <div ref={scrollRef} className="parallel-column-scroll" data-text-id={text.text_id}>
        {paragraphs.map((p, i) => {
          const idx = chunkIndexFor(p, chunkIndex);
          return (
            <p
              key={i}
              className="parallel-paragraph"
              data-chunk-index={idx ?? undefined}
              lang={text.lang}
            >
              {p}
            </p>
          );
        })}
      </div>
    </Card>
  );
}
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/parallel/AlignmentColumn.test.tsx
```

Expected: PASS (5 tests)

- [ ] **Step 4.5: Commit**

```bash
git add frontend/src/components/parallel/AlignmentColumn.tsx frontend/src/components/parallel/AlignmentColumn.test.tsx
git commit -m "feat(parallel): AlignmentColumn renderer with chunk markup"
```

---

## Task 5: Extend `parallel.css` with V1 grid + chunk styles

**Files:**
- Modify: `frontend/src/styles/parallel.css` (append)

- [ ] **Step 5.1: Read current parallel.css to see existing classes**

Run:
```bash
cat /home/lqsxi/projects/fojin/frontend/src/styles/parallel.css
```

- [ ] **Step 5.2: Append V1 styles**

Add the following to the END of `frontend/src/styles/parallel.css`:

```css
/* === V1 sync-scroll grid === */
.parallel-grid-v1 {
  display: grid;
  gap: 12px;
  margin-top: 8px;
}
.parallel-grid-v1.cols-2 {
  grid-template-columns: 1fr 1fr;
}
.parallel-grid-v1.cols-3 {
  grid-template-columns: 1fr 1fr 1fr;
}
@media (max-width: 1279px) {
  .parallel-grid-v1.cols-3 {
    grid-template-columns: 1fr 1fr;
  }
  .parallel-grid-v1.cols-3 > :nth-child(3) {
    display: none;
  }
}
@media (max-width: 767px) {
  .parallel-grid-v1.cols-2,
  .parallel-grid-v1.cols-3 {
    grid-template-columns: 1fr;
  }
}

.parallel-column-card {
  height: calc(100vh - 220px);
  min-height: 480px;
  display: flex;
  flex-direction: column;
}
.parallel-column-card .ant-card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
}

.parallel-column-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  line-height: 1.95;
}

.parallel-column-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.parallel-column-title {
  font-weight: 500;
}
.parallel-column-translator {
  font-size: 12px;
  color: #888;
  font-weight: normal;
}
.parallel-column-lang {
  margin-left: auto;
}

.parallel-paragraph {
  margin: 0 0 0.6em 0;
  font-size: 15px;
  color: #222;
}
.parallel-paragraph[data-chunk-index] {
  transition: background-color 0.2s ease;
}
.parallel-paragraph[data-chunk-index]:hover {
  background-color: rgba(91, 140, 107, 0.08);
}

.parallel-coverage-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  margin-bottom: 12px;
  background: #fafafa;
  border-left: 3px solid #5b8c6b;
  border-radius: 4px;
  font-size: 13px;
  color: #555;
  flex-wrap: wrap;
}
.parallel-coverage-hint {
  color: #999;
  font-size: 12px;
}

- [ ] **Step 5.3: Commit**

```bash
git add frontend/src/styles/parallel.css
git commit -m "feat(parallel): V1 responsive grid + column card + chunk hover styles"
```

---

## Task 6: Rewrite `ParallelReaderPage` to N-column with sync scroll

**Files:**
- Modify: `frontend/src/pages/ParallelReaderPage.tsx` (full rewrite)

- [ ] **Step 6.1: Read existing file first to preserve URL contract**

Run:
```bash
cat /home/lqsxi/projects/fojin/frontend/src/pages/ParallelReaderPage.tsx
```

Confirm: existing route is `/parallel/:textId?compare=Y&juan=N`. We add `compare2=Z` without breaking that.

- [ ] **Step 6.2: Replace the file with N-column implementation**

```tsx
// frontend/src/pages/ParallelReaderPage.tsx
import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Button,
  Card,
  Empty,
  InputNumber,
  Result,
  Select,
  Space,
  Spin,
  Typography,
} from "antd";
import { ArrowLeftOutlined, SwapOutlined } from "@ant-design/icons";
import {
  getJuanAlignment,
  getParallelRead,
  getTextRelations,
} from "../api/client";
import AlignmentColumn from "../components/parallel/AlignmentColumn";
import { buildAlignmentMap } from "../components/parallel/buildAlignmentMap";
import { useSyncScroll, type ColumnRef } from "../components/parallel/useSyncScroll";
import type { ColumnData } from "../components/parallel/types";
import "../styles/parallel.css";

const { Title } = Typography;

export default function ParallelReaderPage() {
  const { textId } = useParams<{ textId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const baseId = Number(textId);
  const compareId = searchParams.get("compare") ? Number(searchParams.get("compare")) : null;
  const compare2Id = searchParams.get("compare2") ? Number(searchParams.get("compare2")) : null;
  const juan = Number(searchParams.get("juan") || "1");

  const { data: relations } = useQuery({
    queryKey: ["relations", baseId],
    queryFn: () => getTextRelations(baseId),
    enabled: !!baseId,
  });

  const compareIds = [compareId, compare2Id].filter((x): x is number => x !== null);

  // Fetch parallel-read pairs for each compare
  const parallelQueries = useQueries({
    queries: compareIds.map((cid) => ({
      queryKey: ["parallel", baseId, cid, juan],
      queryFn: () => getParallelRead(baseId, cid, juan),
      enabled: !!baseId,
    })),
  });

  // Fetch alignment for base + each compare (for symmetric anchor map)
  const allTextIds = [baseId, ...compareIds];
  const alignmentQueries = useQueries({
    queries: allTextIds.map((tid) => ({
      queryKey: ["juan-alignment", tid, juan],
      queryFn: () => getJuanAlignment(tid, juan),
      enabled: !!tid,
      retry: false,
    })),
  });

  const anyLoading = parallelQueries.some((q) => q.isLoading);
  const anyError = parallelQueries.some((q) => q.isError);

  // Build column data: base text from first parallel query's text_a, compares from text_b of each
  const columns: ColumnData[] = useMemo(() => {
    if (parallelQueries.length === 0) return [];
    const result: ColumnData[] = [];
    const first = parallelQueries[0].data;
    if (first) {
      result.push({
        text: first.text_a,
        alignment: alignmentQueries[0]?.data ?? null,
      });
    }
    parallelQueries.forEach((q, i) => {
      if (q.data) {
        result.push({
          text: q.data.text_b,
          alignment: alignmentQueries[i + 1]?.data ?? null,
        });
      }
    });
    return result;
  }, [parallelQueries, alignmentQueries]);

  const alignmentMap = useMemo(
    () => buildAlignmentMap(alignmentQueries.map((q) => q.data ?? null)),
    [alignmentQueries],
  );

  // Refs to each column's scroll container — kept as a stable array
  const scrollRefs = useRef<ColumnRef[]>([]);
  scrollRefs.current = columns.map((col, i) => ({
    textId: col.text.text_id,
    el: scrollRefs.current[i]?.el ?? null,
  }));

  useSyncScroll(scrollRefs, alignmentMap);

  const handleCompareChange = (value: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("compare", String(value));
    next.set("juan", String(juan));
    setSearchParams(next);
  };

  const handleCompare2Change = (value: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null) {
      next.delete("compare2");
    } else {
      next.set("compare2", String(value));
    }
    next.set("juan", String(juan));
    setSearchParams(next);
  };

  const handleJuanChange = (value: number | null) => {
    if (value && compareId) {
      const next = new URLSearchParams(searchParams);
      next.set("juan", String(value));
      setSearchParams(next);
    }
  };

  const relationOptions =
    relations?.relations.map((r) => ({
      value: r.text_id,
      label: `${r.title_zh} (${r.translator || "佚名"} · ${r.dynasty || ""}) [${r.relation_type}]`,
    })) ?? [];

  return (
    <div className="parallel-container">
      <div className="parallel-header">
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>
          返回
        </Button>
        <Title level={3} style={{ margin: 0 }}>
          <SwapOutlined /> 跨藏并排对照
        </Title>
      </div>

      <Card size="small" style={{ marginBottom: 16 }} className="parallel-controls">
        <Space wrap>
          <span>对照版本：</span>
          <Select
            style={{ minWidth: 260 }}
            placeholder="选择对照文本"
            value={compareId ?? undefined}
            onChange={handleCompareChange}
            options={relationOptions}
          />
          <span>+ 第三列：</span>
          <Select
            allowClear
            style={{ minWidth: 260 }}
            placeholder="可选"
            value={compare2Id ?? undefined}
            onChange={(v) => handleCompare2Change(v ?? null)}
            options={relationOptions.filter((o) => o.value !== compareId)}
          />
          <span>卷：</span>
          <InputNumber min={1} value={juan} onChange={handleJuanChange} />
        </Space>
      </Card>

      {!compareId ? (
        <Empty description="请选择对照文本" />
      ) : anyLoading ? (
        <div style={{ textAlign: "center", padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : anyError ? (
        <Result
          status="error"
          title="加载失败"
          subTitle="对照内容加载出错，请稍后重试。"
          extra={
            <Button type="primary" onClick={() => parallelQueries.forEach((q) => q.refetch())}>
              重试
            </Button>
          }
        />
      ) : columns.length === 0 ? (
        <Empty description="对照内容未找到" />
      ) : (
        <>
          <AlignmentCoverageBanner alignments={alignmentQueries.map((q) => q.data ?? null)} />
          <div className={`parallel-grid-v1 cols-${columns.length}`}>
            {columns.map((col, i) => (
              <AlignmentColumn
                key={col.text.text_id}
                text={col.text}
                alignment={col.alignment}
                scrollRef={(el) => {
                  scrollRefs.current[i] = { textId: col.text.text_id, el };
                }}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

interface CoverageBannerProps {
  alignments: Array<import("../api/client").JuanAlignmentResponse | null>;
}

function AlignmentCoverageBanner({ alignments }: CoverageBannerProps) {
  // Use the base column (first alignment) for the coverage stat — that's the driver
  const base = alignments[0];
  if (!base || base.total_chunks === 0) return null;
  const pct = Math.round((base.chunks_with_parallels / base.total_chunks) * 100);
  const tone = pct >= 60 ? "#5b8c6b" : pct >= 30 ? "#d48806" : "#999";
  return (
    <div className="parallel-coverage-banner" style={{ borderLeftColor: tone }}>
      <span>本卷对齐覆盖</span>
      <strong style={{ color: tone }}>
        {base.chunks_with_parallels} / {base.total_chunks} 段 ({pct}%)
      </strong>
      <span className="parallel-coverage-hint">
        {pct >= 60
          ? "锚点对齐为主，滚动精准"
          : pct >= 30
            ? "部分锚点对齐，无对齐处比例滚动"
            : "无段级对齐，按比例同步滚动"}
      </span>
    </div>
  );
}
```

- [ ] **Step 6.3: Run typecheck**

```bash
cd frontend && npx tsc -b --noEmit
```

Expected: no errors

- [ ] **Step 6.4: Run all parallel tests + linter**

```bash
cd frontend && npx vitest run src/components/parallel/
cd frontend && npx eslint src/components/parallel/ src/pages/ParallelReaderPage.tsx
```

Expected: all tests PASS; eslint clean (or only matches existing project warnings)

- [ ] **Step 6.5: Commit**

```bash
git add frontend/src/pages/ParallelReaderPage.tsx
git commit -m "feat(parallel): rewrite ParallelReaderPage to N-column sync scroll

- Up to 3 columns (compare + compare2)
- useSyncScroll hook wires hybrid anchor+proportional algorithm
- Backward-compatible with existing ?compare=X&juan=N URL shape
- New ?compare2=Y param opens 3rd column"
```

---

## Task 7: Manual smoke test

**Files:** none

- [ ] **Step 7.1: Start the dev server**

```bash
cd /home/lqsxi/projects/fojin/frontend && npm run dev
```

Expected: Vite dev server on a localhost port (5173).

- [ ] **Step 7.2: Open the production-realistic test URL**

In a browser, open:
```
http://localhost:5173/parallel/<textId>?compare=<otherTextId>&juan=1
```
Replace `<textId>` and `<otherTextId>` with two real `buddhist_texts.id` values that have a known `text_relations` entry. (Verify: open `/texts/<textId>/read?juan=1` first and check the "其他版本" panel for a valid pair.)

Verify:
- Two columns render side by side
- Each shows the correct title + translator + lang chip
- Scrolling left column → right column follows
- Scroll feels smooth, no jitter, no infinite loop

- [ ] **Step 7.3: Test 3-column mode**

Add `&compare2=<thirdTextId>` to the URL. Reload. Verify:
- 3 columns render on a ≥1280px viewport
- 3rd column collapses below 1280px

- [ ] **Step 7.4: Test responsive breakpoints**

Resize browser to 1100px width → 3rd column hidden.
Resize to 700px → all columns stack to single column (each scrolling independently is acceptable; sync scroll on mobile is best-effort).

- [ ] **Step 7.5: Test missing alignment fallback**

Open a parallel URL where you suspect no `alignment_pairs` data exists (a less-covered relation). Verify that scrolling still syncs proportionally (not stuck).

- [ ] **Step 7.6: If any smoke test fails, fix and re-commit; otherwise proceed**

---

## Task 8: Push branch and open PR

**Files:** none

- [ ] **Step 8.1: Push the branch**

```bash
cd /home/lqsxi/projects/fojin
git push -u origin feat/parallel-reader-v1-sync-scroll
```

- [ ] **Step 8.2: Open the PR**

```bash
gh pr create \
  --title "feat(parallel): V1 cross-canon parallel reading — sync scroll + 3-column" \
  --body "$(cat <<'EOF'
## Summary
- Rewrites \`ParallelReaderPage\` from 2-col independent scrolling to N-column synchronized scrolling
- Hybrid sync algorithm: anchor-based via \`alignment_pairs.chunk_index\` when available, proportional fallback
- Adds optional 3rd column (\`?compare2=<id>\`); existing 2-col URLs unchanged
- 0 backend changes — pure frontend feature on top of existing \`getParallelRead\` + \`getJuanAlignment\`
- Responsive: 3-col on ≥1280px, 2-col 768-1279px, stacked on mobile

## Design
See \`docs/superpowers/specs/2026-06-03-cross-canon-parallel-reading-v1-design.md\` — this is PR-1 of 3 (sync scroll core → AI diff → export/share).

## Test plan
- [x] Unit: \`buildAlignmentMap\` (5 tests)
- [x] Unit: \`useSyncScroll\` (4 tests: anchor hit, proportional fallback, suppress guard, 3-col)
- [x] Unit: \`AlignmentColumn\` (5 tests: rendering, paragraph split, chunk markup, scrollRef, lang chip)
- [x] Manual smoke test: 2-col sync scroll, 3-col on desktop, mobile fallback, missing-alignment fallback
- [x] tsc typecheck clean
- [x] eslint clean on touched files

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 8.3: Verify PR URL and check CI status**

```bash
gh pr view --json url,statusCheckRollup --jq '{url, checks: .statusCheckRollup}'
```

If CI fails on the PR, investigate and fix before requesting review.

---

## Done criteria for PR-1

- All 14 unit tests (5 buildAlignmentMap + 4 useSyncScroll + 5 AlignmentColumn) pass
- Manual smoke test all 5 scenarios green
- tsc typecheck clean
- eslint clean on touched files
- PR opened, CI green
- Existing `/parallel/:textId?compare=X&juan=N` URLs continue to work unchanged

## What ships next (post merge — separate plans)

- **PR-2**: AI difference analysis — new `/alignment/ai-diff` endpoint + `ai_diff_cache` table + `AIDiffPopover`
- **PR-3**: Export markdown + shareable deep link + bookmark
