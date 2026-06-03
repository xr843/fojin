# Cross-Canon Parallel Reading V1 — Design

**Date**: 2026-06-03
**Status**: Approved (brainstorm → spec)
**Owner**: @xr843

## Goal

Ship a "killer" parallel reading experience that is fojin's strongest moat against CBETA / SuttaCentral / 84000: **side-by-side multi-column reading with synchronized scrolling, paragraph-anchor alignment, and AI difference analysis**, scoped to the 5 trilingual classics already covered by the embed-LLM alignment pipeline (and gracefully degrading for the rest of the corpus).

The product question this answers: when a scholar (or curious reader) wants to compare 心经 across 汉/藏英/巴英 versions, today they get a sidebar with collapsed snippets. After V1, they get a true side-by-side immersive reader where scrolling one column moves the others to the corresponding paragraph, hovering a paragraph highlights the parallels, and selecting a passage triggers AI difference analysis.

## Why not the existing reader

We have three parallel-reading surfaces already:

1. **`TextReaderPage` + `ReaderParallelPanel` (sidebar Tab)** — the production "reader mode" with a collapsible panel showing canonical / chunk parallels. Strong for "reading one text, glancing at parallels". Weak for "actively comparing two or three versions".
2. **`ParallelReaderPage` (`/parallel/:textId`)** — a 2-column standalone page with independent scrolling and juan-only granularity. Functional but flat: no sync scrolling, no anchor highlighting, no 3-column support.
3. **`OtherVersions` (inside sidebar)** — FRBR Work witness switcher, narrow scope.

V1 upgrades surface #2 (`ParallelReaderPage`) without touching #1 or #3. Scholars who want immersive comparison go to the upgraded `/parallel/:textId`; casual readers using the standard reader continue to see the sidebar panel as today.

## Architecture

### Route

`/parallel/:textId?compare=<id>&compare2=<id>&juan=<n>`

- `compare` — primary compare text (required)
- `compare2` — optional third text (3-column mode)
- `juan` — current juan number (default 1)
- Backward compatible with current 2-column URL shape

### Frontend components

```
ParallelReaderPage (page)
├── ParallelControls (Card)     compare/compare2/juan selectors + open/close 3-col
├── AlignmentColumn × N          one per source/compare text
│   ├── ColumnHeader             title + translator + lang chip
│   └── ParagraphList            text rendered as <p> nodes with data-chunk-index
└── AIDiffPopover (overlay)      triggered by paragraph selection
```

Three columns max (UX flatlines at 4+ for synchronized scrolling). 3rd column hidden on `xs`/`sm` breakpoints (mobile → 2-col, tablet → switchable, desktop → 3-col).

### `useSyncScroll(refs, alignmentMap)` hook

Hybrid algorithm:

1. **Anchor-based** when alignment exists:
   - On scroll of column A, find the top-most visible `data-chunk-index` element via `IntersectionObserver`.
   - Look up `alignmentMap[A→B]` for the corresponding `chunk_index` in B.
   - `scrollIntoView({ block: "start" })` the matching element in B.
2. **Proportional fallback** when no alignment for the visible chunk:
   - Apply `scrollPercentage` of A to B.
3. **Loop guard** — every programmatic scroll sets `suppressUntil = Date.now() + 80ms` on the receiving columns to prevent ping-pong.

Wired via a single `IntersectionObserver` per column observing all `[data-chunk-index]` nodes; on intersection events the hook fires `applySync(driverColumn)`.

### `AlignmentColumn`

Stateless renderer.

Props: `text: { title, translator, lang, content }`, `chunks: ChunkMap` (chunk_index → { offset, text }), `highlightedChunk: number | null`.

Renders content as `<p data-chunk-index="N">` blocks. Highlighting handled via CSS `:has` or controlled class.

### 3-column data fetch (Approach X — no backend changes)

```ts
Promise.all([
  getParallelRead(textA, compareB, juan),  // existing API
  compareC ? getParallelRead(textA, compareC, juan) : null,
  getJuanAlignment(textA, juan),           // existing API, returns chunk-level alignment
]).then(([ab, ac, alignment]) => mergeColumns(ab, ac, alignment));
```

Note: `getJuanAlignment` returns alignment_pairs entries for textA. We index by `(text_b_id, chunk_index)` and rebuild the chunkMap client-side. If `compareC` is set but alignment_pairs only covers textA↔textB, the third column falls back to proportional scroll silently.

### `AIDiffPopover` + new `/alignment/ai-diff` backend endpoint

**Frontend trigger**: user selects 1+ paragraphs in any column → floating "AI 差异分析" button appears → click → popover loads.

**Backend** — new endpoint:

```
POST /alignment/ai-diff
{
  chunks: [
    { text_id, juan_num, chunk_index, lang, text },
    ...
  ]
}
→
{
  cached: bool,
  analysis: { differences: [...], doctrinal_notes: string, ... }
}
```

- Backed by new `ai_diff_cache` table: `chunks_hash (sha256 of sorted chunk_ids) | analysis_json | created_at`
- LLM call goes through existing `app.services.llm.chat()` with a locked system prompt (versioned in code, change requires migration)
- Streaming response not needed for V1 (analyses are short, ~500-1500 tokens)
- Cache hit → return immediately; miss → call LLM → cache → return

### Out of scope for V1

- Editing alignments (curator UI)
- Real-time AI translation
- Diff highlighting within paragraphs (word-level)
- Voice playback
- Export PDF (V1 ships markdown export only; PDF is V2)

## Data flow

```
URL params change
  ↓
useQuery × 3 (parallel: AB, AC, alignment)
  ↓
mergeColumns(ab, ac, alignmentPairs) → ColumnsModel
  ↓
<AlignmentColumn × N> renders <p data-chunk-index="i">
  ↓
useSyncScroll wires IntersectionObserver on each column
  ↓
[user scrolls A] → observer fires → applySync(B, C) via anchor lookup
[user selects text] → AIDiffPopover trigger
[user clicks AI diff] → POST /alignment/ai-diff → render popover
```

## Error handling

- `getParallelRead` fails → Result component (existing pattern from `ParallelReaderPage`)
- `getJuanAlignment` fails → silent fallback to proportional-only scroll, log to Sentry
- Selected chunks language mismatch → AIDiffPopover still works (LLM handles mixed lang)
- AI diff endpoint timeout (>30s) → show "分析超时，请重试" + retry button
- 3rd column 404 (compare2 invalid) → render 2-col with toast

## Testing

### Unit

- `useSyncScroll` algorithm:
  - anchor hit → calls scrollIntoView on target
  - anchor miss → falls back to proportional
  - loop guard → suppresses programmatic scrolls within 80ms window
  - 3-column case → driver scroll triggers both followers
- `mergeColumns` reducer:
  - alignment from AB only → C falls back
  - alignment fully present → both followers get anchors
  - empty alignment → both proportional

### Integration

- Render `<ParallelReaderPage>` with mock APIs (心经 + 巴英 + 藏英) → verify 3 columns render, juan switch works, controls update URL
- AIDiffPopover with mocked endpoint → verify cache hit shows instantly, miss shows loader

### E2E (Playwright)

- Open `/parallel/T0251?compare=<korean>&compare2=<sc-pi>&juan=1`
- Scroll column A → verify B and C scroll to matching chunks
- Select paragraph in column A → click AI diff → verify popover loads
- Resize to tablet width → verify 3rd column collapses gracefully

## Rollout plan — three PRs, stable & shippable each

### PR-1 (3-4 days) — Core: sync scroll + 3-column + anchor

- `useSyncScroll` hook + tests
- `AlignmentColumn` extracted from current inline JSX
- `ParallelReaderPage` rewrite to N-column model (supports 2 and 3)
- Backward-compatible URL handling
- Existing 2-col URLs (`?compare=X&juan=N`) keep working
- Ships independently — user can open `/parallel/...` and use sync scroll immediately
- **Demo-ready**: write announcement on merge

### PR-2 (1-2 days) — AI difference analysis

- New `alembic` migration: `ai_diff_cache` table
- Backend: `POST /alignment/ai-diff` endpoint + caching
- Locked system prompt versioned in `app/services/ai_diff.py`
- Frontend: `AIDiffPopover` component
- Frontend: paragraph selection handler + floating trigger button
- Ships independently after PR-1 — adds the differentiation feature
- **Demo-ready**: AI diff GIF for social

### PR-3 (1-2 days) — Sugar: export + share + bookmark

- "导出对照 markdown" button (client-side; uses current column data)
- Shareable deep link `?compare=X&compare2=Y&juan=N&anchor=chunk_3`
- Bookmark current view (uses existing bookmark API if present, else new)
- Ships last — pure UX polish, no risk

## Decisions log

- **Hybrid sync scroll over pure-anchor** — corpus alignment coverage is uneven (memory: 547 sources, embed-LLM alignment only for trilingual MVP 5 classics); pure-anchor would break for ~95% of compare pairs. Hybrid preserves UX while rewarding texts with alignment data.
- **Front-end 2-call data fetch over backend batch endpoint** — adding a `/parallel/batch` API would be premature; 2 parallel HTTP calls are well under any latency budget for this UI.
- **Independent `/alignment/ai-diff` endpoint over reusing `/chat`** — locked prompt, cacheable, and analysis-shape pydantic model for typed frontend.
- **Three PRs over one** — every PR ships a demoable artifact; reduces review burden; each merge is a separate distribution touchpoint (announcement, GIF, share).
- **No changes to TextReaderPage / ReaderParallelPanel** — the production sidebar mode is good as-is; scholars who want immersion use the upgraded standalone page.

## Risks

| Risk | Mitigation |
|---|---|
| Sync scroll feels janky on long juans | Throttle observer to 16ms; loop guard 80ms; test on T0251 (longest juan ~10k chars) before merge |
| AI diff hallucinates differences | Locked prompt requires citation of specific chunk text; cache keyed by chunk content prevents re-rolling |
| 3-column readability on small desktops | CSS responsive: 3-col only ≥1280px, 2-col 768-1279px, single-col with column-switcher on mobile |
| Alignment coverage gap surprises users | Header banner shows "本卷对齐覆盖 X%" using `getJuanAlignment.chunks_with_parallels` |
