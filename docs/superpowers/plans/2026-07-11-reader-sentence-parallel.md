# 阅读器逐句对读 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a「按句对读」sentence-level parallel tab to the reader's cross-canon sidebar, consuming the frozen P4-C endpoint, shipping dark until prod sentence data exists.

**Architecture:** New self-contained `SentenceParallelView` component fetches `GET /alignment/sentences/{textId}/{juanNum}` via react-query, renders each returned pair as a stacked card (汉文 above, 外文 below) with click-to-pin active-emphasis. `ReaderParallelPanel` conditionally adds the tab only when the endpoint returns `total > 0` (react-query dedupes the shared query). No backend changes.

**Tech Stack:** React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query (react-query) + react-i18next + vitest.

## Global Constraints

- No hardcoded Chinese in TSX — every user-facing string is an i18n key added to ALL locale files under `frontend/public/locales/{zh,en,zh-Hant}/translation.json`. `npm run i18n:check` MUST pass.
- Interpolation uses `{{n}}`, never `{{count}}`.
- Match existing patterns exactly: mirror `ChunkView` (in `frontend/src/components/ReaderParallelPanel.tsx:211`) for the react-query + Spin/Alert/Empty idiom, and mirror the existing alignment client methods in `frontend/src/api/client.ts` (`getJuanAlignment`, `getCanonicalParallels`) for method + type style.
- Frozen backend contract (do NOT change): `GET /api/alignment/sentences/{text_id}/{juan_num}?limit=200` → `{ text_id, juan_num, total, pairs: SentencePair[] }` where `SentencePair = { side_a: {char_start:number, char_end:number, lang:string, text:string}, side_b: {text_id:number, juan_num:number, char_start:number, char_end:number, lang:string, title:string, text:string}, similarity:number, align_type:"1-1"|"1-2"|"2-1", method:string, is_verified:boolean }`.
- CI gates all must pass: `npx tsc -b --noEmit`, `npm run lint`, `npm run i18n:check`, `npm test`, `npm run build`.
- Component lives in a NEW file `frontend/src/components/parallel/SentenceParallelView.tsx` (do not inline into ReaderParallelPanel; do not refactor the existing inline CanonicalView/ChunkView).

---

### Task 1: API client method + types

**Files:**
- Modify: `frontend/src/api/client.ts` (add types + `getSentenceParallels`, mirroring `getJuanAlignment`)
- Test: `frontend/src/api/client.sentenceParallels.test.ts` (or extend the existing client test file if one covers alignment methods — check first)

**Interfaces:**
- Produces: `export interface SentenceSideA { char_start:number; char_end:number; lang:string; text:string }`, `export interface SentenceSideB extends /* not extends */ { text_id:number; juan_num:number; char_start:number; char_end:number; lang:string; title:string; text:string }`, `export interface SentencePair { side_a:SentenceSideA; side_b:SentenceSideB; similarity:number; align_type:"1-1"|"1-2"|"2-1"; method:string; is_verified:boolean }`, `export interface SentenceAlignmentResponse { text_id:number; juan_num:number; total:number; pairs:SentencePair[] }`, and `getSentenceParallels(textId:number, juanNum:number): Promise<SentenceAlignmentResponse>`.

- [ ] **Step 1: Read the pattern.** Open `frontend/src/api/client.ts`, find `getJuanAlignment` and `getCanonicalParallels` — note the exact request helper used (e.g. `apiGet`/`fetch` wrapper), base path (`/api` prefix handling), and return-typing style. Note whether a shared alignment-types block exists.

- [ ] **Step 2: Write the failing test.** In the client test file:

```ts
import { getSentenceParallels } from "./client";
// mock the http layer the same way existing client tests do (check an existing *client*.test)
it("getSentenceParallels calls the sentence endpoint and returns typed pairs", async () => {
  const mockResp = { text_id: 1, juan_num: 5, total: 1, pairs: [{
    side_a: { char_start: 0, char_end: 10, lang: "lzh", text: "如是我聞。" },
    side_b: { text_id: 9, juan_num: 1, char_start: 0, char_end: 20, lang: "pi", title: "MN 10", text: "Evaṁ me sutaṁ." },
    similarity: 0.94, align_type: "1-1", method: "sentence-bertalign", is_verified: true,
  }] };
  // arrange mock to resolve mockResp for GET /alignment/sentences/1/5
  const r = await getSentenceParallels(1, 5);
  expect(r.total).toBe(1);
  expect(r.pairs[0].side_b.lang).toBe("pi");
  expect(r.pairs[0].align_type).toBe("1-1");
});
```

- [ ] **Step 3: Run test to verify it fails.** Run: `npx vitest run src/api/client.sentenceParallels.test.ts` — Expected: FAIL (`getSentenceParallels` not exported).

- [ ] **Step 4: Implement.** Add the interfaces above and the method, mirroring `getJuanAlignment`'s exact request idiom:

```ts
export async function getSentenceParallels(textId: number, juanNum: number): Promise<SentenceAlignmentResponse> {
  // use the SAME request helper getJuanAlignment uses:
  return apiGet<SentenceAlignmentResponse>(`/alignment/sentences/${textId}/${juanNum}`);
}
```
(Replace `apiGet` and path-prefix with whatever `getJuanAlignment` actually uses.)

- [ ] **Step 5: Run test to verify it passes.** Run: `npx vitest run src/api/client.sentenceParallels.test.ts` — Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.sentenceParallels.test.ts
git commit -m "feat(reader): add getSentenceParallels client method + types"
```

---

### Task 2: SentenceParallelView — fetch + render + states + i18n

**Files:**
- Create: `frontend/src/components/parallel/SentenceParallelView.tsx`
- Create: `frontend/src/components/parallel/SentenceParallelView.test.tsx`
- Modify: `frontend/public/locales/{zh,en,zh-Hant}/translation.json` (add keys under `reader.parallel.sentence`)

**Interfaces:**
- Consumes: `getSentenceParallels`, `SentenceAlignmentResponse`, `SentencePair` (Task 1).
- Produces: `export default function SentenceParallelView(props: { textId:number; juanNum:number }): JSX.Element`.

- [ ] **Step 1: Add i18n keys.** In each of the 3 locale files, under `reader.parallel`, add a `sentence` object. zh example (translate for en / zh-Hant):

```json
"sentence": {
  "empty": "本卷暂无逐句对齐",
  "verified": "已校",
  "load_error": "逐句对齐加载失败",
  "retry": "重试",
  "align_1_2": "1→2",
  "align_2_1": "2→1"
}
```
(en: "No sentence-level alignment for this fascicle" etc. zh-Hant: 繁体. Reuse existing `reader.parallel.tab_*` sibling keys' language conventions.)

- [ ] **Step 2: Write failing tests.** `SentenceParallelView.test.tsx`, mirroring the render/mock pattern of an existing `frontend/src/components/parallel/*.test.tsx` (read one first for the QueryClient + i18n test wrapper). Mock `getSentenceParallels`.

```tsx
// helper: render inside the repo's standard test wrapper (QueryClientProvider + I18nextProvider) — copy from an existing parallel test
const onePair = { text_id:1, juan_num:5, total:1, pairs:[{
  side_a:{char_start:0,char_end:5,lang:"lzh",text:"如是我聞。"},
  side_b:{text_id:9,juan_num:1,char_start:0,char_end:14,lang:"pi",title:"MN 10",text:"Evaṁ me sutaṁ."},
  similarity:0.94, align_type:"1-2", method:"sentence-bertalign", is_verified:true }] };

it("renders sentence pairs with both languages and align_type badge", async () => {
  mockGet.mockResolvedValue(onePair);
  render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
  expect(await screen.findByText("如是我聞。")).toBeInTheDocument();
  expect(screen.getByText("Evaṁ me sutaṁ.")).toBeInTheDocument();
  expect(screen.getByText(/1→2/)).toBeInTheDocument();  // align_type badge
});

it("shows Empty when total is 0", async () => {
  mockGet.mockResolvedValue({ text_id:1, juan_num:5, total:0, pairs:[] });
  render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
  expect(await screen.findByText(/暂无逐句对齐|No sentence-level/)).toBeInTheDocument();
});

it("shows an alert on error", async () => {
  mockGet.mockRejectedValue(new Error("boom"));
  render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 3: Run to verify fail.** Run: `npx vitest run src/components/parallel/SentenceParallelView.test.tsx` — Expected: FAIL (component missing).

- [ ] **Step 4: Implement the component** (render + states; click-to-pin comes in Task 3). Mirror `ChunkView`'s query idiom (`ReaderParallelPanel.tsx:211`):

```tsx
import { useQuery } from "@tanstack/react-query";
import { Spin, Alert, Empty, Tag, Button } from "antd";
import { useTranslation } from "react-i18next";
import { getSentenceParallels, type SentencePair } from "../../api/client";

export default function SentenceParallelView({ textId, juanNum }: { textId: number; juanNum: number }) {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["sentence-parallels", textId, juanNum],
    queryFn: () => getSentenceParallels(textId, juanNum),
    enabled: textId > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  if (isLoading) return <Spin style={{ display: "block", margin: "24px auto" }} />;
  if (isError)
    return <Alert type="error" message={t("reader.parallel.sentence.load_error")}
             action={<Button size="small" onClick={() => refetch()}>{t("reader.parallel.sentence.retry")}</Button>} />;
  if (!data || data.total === 0) return <Empty description={t("reader.parallel.sentence.empty")} />;
  return (
    <div className="sentence-parallel-view">
      {data.pairs.map((p, i) => (
        <SentencePairCard key={i} pair={p} />
      ))}
    </div>
  );
}

function alignBadge(p: SentencePair, t: (k: string) => string): string | null {
  if (p.align_type === "1-2") return t("reader.parallel.sentence.align_1_2");
  if (p.align_type === "2-1") return t("reader.parallel.sentence.align_2_1");
  return null;
}

function SentencePairCard({ pair }: { pair: SentencePair }) {
  const { t } = useTranslation();
  const badge = alignBadge(pair, t);
  return (
    <div className="sentence-pair-card" style={{ padding: 8, borderBottom: "1px solid var(--border, #f0f0f0)" }}>
      <div className="sp-zh">{pair.side_a.text}</div>
      <div className="sp-foreign" style={{ color: "#666", marginTop: 4 }}>{pair.side_b.text}</div>
      <div className="sp-meta" style={{ marginTop: 4, fontSize: 12, color: "#999" }}>
        <Tag>{pair.side_b.lang}</Tag>
        {pair.side_b.title && <span>{pair.side_b.title}</span>}
        {badge && <Tag color="blue">{badge}</Tag>}
        {pair.is_verified && <Tag color="green">{t("reader.parallel.sentence.verified")}</Tag>}
        <span> {pair.similarity.toFixed(2)}</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Run to verify pass.** Run: `npx vitest run src/components/parallel/SentenceParallelView.test.tsx` — Expected: PASS (3 tests). If the empty-text regex or wrapper differs, align to the real test wrapper.

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/components/parallel/SentenceParallelView.tsx frontend/src/components/parallel/SentenceParallelView.test.tsx frontend/public/locales
git commit -m "feat(reader): SentenceParallelView renders sentence pairs (fetch + states)"
```

---

### Task 3: Click-to-pin interaction

**Files:**
- Modify: `frontend/src/components/parallel/SentenceParallelView.tsx`
- Modify: `frontend/src/components/parallel/SentenceParallelView.test.tsx`

**Interfaces:**
- Consumes: the component from Task 2.
- Produces: click-to-pin behavior — clicking a card sets it active (adds `is-active` class, scrolls into view); clicking the active card again clears it.

- [ ] **Step 1: Write failing test.**

```tsx
it("click-to-pin: clicking a card activates it, clicking again clears", async () => {
  mockGet.mockResolvedValue({ text_id:1, juan_num:5, total:2, pairs:[pairA, pairB] });  // define 2 fixture pairs
  render(<SentenceParallelView textId={1} juanNum={5} />, { wrapper });
  const cards = await screen.findAllByTestId("sentence-pair-card");
  fireEvent.click(cards[0]);
  expect(cards[0].className).toMatch(/is-active/);
  expect(cards[1].className).not.toMatch(/is-active/);
  fireEvent.click(cards[0]);
  expect(cards[0].className).not.toMatch(/is-active/);
});
```

- [ ] **Step 2: Run to verify fail.** Run: `npx vitest run src/components/parallel/SentenceParallelView.test.tsx -t click-to-pin` — Expected: FAIL.

- [ ] **Step 3: Implement.** Lift active-index state into `SentenceParallelView`, pass `active`/`onToggle` to the card, add `data-testid="sentence-pair-card"`, toggle an `is-active` class, and `scrollIntoView({ block: "nearest" })` on activate:

```tsx
// in SentenceParallelView:
const [active, setActive] = useState<number | null>(null);
// reset when juan changes:
const [prevKey, setPrevKey] = useState(`${textId}:${juanNum}`);
if (prevKey !== `${textId}:${juanNum}`) { setPrevKey(`${textId}:${juanNum}`); setActive(null); }
// ...
{data.pairs.map((p, i) => (
  <SentencePairCard key={i} pair={p} active={active === i}
    onToggle={(el) => { setActive(active === i ? null : i); if (active !== i) el?.scrollIntoView({ block: "nearest" }); }} />
))}

// SentencePairCard signature gains: active:boolean; onToggle:(el:HTMLDivElement|null)=>void
// root div:
<div ref={ref} data-testid="sentence-pair-card"
     className={`sentence-pair-card${active ? " is-active" : ""}`}
     onClick={() => onToggle(ref.current)}
     style={{ ..., cursor: "pointer", background: active ? "var(--active-bg, #e6f4ff)" : undefined }}>
```
Add `useRef<HTMLDivElement>(null)` and `useState`/`useRef` imports.

- [ ] **Step 4: Run to verify pass.** Run: `npx vitest run src/components/parallel/SentenceParallelView.test.tsx` — Expected: PASS (all tests). Note: jsdom lacks a real `scrollIntoView`; if it throws, guard with `el?.scrollIntoView?.(...)`.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/parallel/SentenceParallelView.tsx frontend/src/components/parallel/SentenceParallelView.test.tsx
git commit -m "feat(reader): click-to-pin active-emphasis in SentenceParallelView"
```

---

### Task 4: Wire the「按句对读」tab into ReaderParallelPanel (conditional)

**Files:**
- Modify: `frontend/src/components/ReaderParallelPanel.tsx` (add the tab item conditionally on `total>0`)
- Modify: `frontend/public/locales/{zh,en,zh-Hant}/translation.json` (add `reader.parallel.tab_sentence`)
- Modify: `frontend/src/components/ReaderParallelPanel.test.tsx` if it exists, else create `ReaderParallelPanel.sentenceTab.test.tsx`

**Interfaces:**
- Consumes: `SentenceParallelView` (Task 3), `getSentenceParallels` (Task 1).
- Produces: the sidebar shows a third「按句对读」tab iff the sentence endpoint returns `total>0`.

- [ ] **Step 1: Add tab-label i18n key** `reader.parallel.tab_sentence` to all 3 locales (zh: `按句对读`, en: `By sentence`, zh-Hant: `按句對讀`), matching the sibling `tab_canonical`/`tab_chunk` style.

- [ ] **Step 2: Write failing test.** Mock `getSentenceParallels` and `getCanonicalParallels`/`getJuanAlignment`.

```tsx
it("shows 按句对读 tab when sentence data exists", async () => {
  mockSentence.mockResolvedValue({ text_id:1, juan_num:5, total:3, pairs:[/*...*/] });
  render(<ReaderParallelPanel textId={1} juanNum={5} />, { wrapper });
  expect(await screen.findByText(/按句对读|By sentence/)).toBeInTheDocument();
});
it("hides 按句对读 tab when sentence data is empty", async () => {
  mockSentence.mockResolvedValue({ text_id:1, juan_num:5, total:0, pairs:[] });
  render(<ReaderParallelPanel textId={1} juanNum={5} />, { wrapper });
  await waitFor(() => expect(screen.queryByText(/按句对读|By sentence/)).not.toBeInTheDocument());
});
```

- [ ] **Step 3: Run to verify fail.** Run: `npx vitest run src/components/ReaderParallelPanel.sentenceTab.test.tsx` — Expected: FAIL.

- [ ] **Step 4: Implement.** In `ReaderParallelPanel`, add a lightweight query (shares Task-2's key → deduped) and conditionally append the tab item:

```tsx
import SentenceParallelView from "./parallel/SentenceParallelView";
import { getSentenceParallels } from "../api/client";
// inside ReaderParallelPanel, after existing canonical query:
const { data: sentence } = useQuery({
  queryKey: ["sentence-parallels", textId, juanNum],
  queryFn: () => getSentenceParallels(textId, juanNum),
  enabled: textId > 0,
  staleTime: 10 * 60 * 1000,
  retry: false,
});
const hasSentence = (sentence?.total ?? 0) > 0;
// build items:
const items = [
  { key: "canonical", label: t("reader.parallel.tab_canonical"), children: <CanonicalView textId={textId} /> },
  { key: "chunk", label: t("reader.parallel.tab_chunk"), children: <ChunkView textId={textId} juanNum={juanNum} /> },
  ...(hasSentence
    ? [{ key: "sentence", label: t("reader.parallel.tab_sentence"), children: <SentenceParallelView textId={textId} juanNum={juanNum} /> }]
    : []),
];
// pass items={items} to <Tabs>. Leave effectiveKey (canonical>chunk default) UNCHANGED.
```

- [ ] **Step 5: Run to verify pass.** Run: `npx vitest run src/components/ReaderParallelPanel.sentenceTab.test.tsx` — Expected: PASS.

- [ ] **Step 6: Full gate + commit.**

Run all: `npx tsc -b --noEmit && npm run lint && npm run i18n:check && npm test && npm run build` — all must pass.
```bash
git add frontend/src/components/ReaderParallelPanel.tsx frontend/src/components/*.test.tsx frontend/public/locales
git commit -m "feat(reader): show 按句对读 tab when sentence alignment exists"
```

---

## Self-Review

- **Spec coverage:** surface=sidebar tab (Task 4 ✓); interaction=click-to-pin (Task 3 ✓); structure=new conditional tab (Task 4 ✓); stacked cards render (Task 2 ✓); client+types (Task 1 ✓); empty/error/ship-dark (Task 2 + Task 4 conditional ✓); i18n all-locales (Tasks 2,4 ✓); tests fixture-only (all ✓). Non-goals (no full-content overlay, no main-reader linkage, no default-tab change) respected.
- **Placeholder scan:** all steps carry real code/commands. Locale values give zh + translation guidance for en/zh-Hant.
- **Type consistency:** `getSentenceParallels`, `SentenceAlignmentResponse`, `SentencePair`, `side_a/side_b`, `align_type` union used identically across Tasks 1–4; `is-active` class + `data-testid="sentence-pair-card"` consistent between Task 3 impl and test.
