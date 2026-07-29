import { useMemo, useState, useRef, useEffect } from "react";
import { Button, Spin, Alert, Tabs } from "antd";
import { useTranslation } from "react-i18next";
import { BookOutlined, ArrowRightOutlined, CloseOutlined, GlobalOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { getChunkContext, getChunkAlignment, type ChunkContextItem, type ParallelPair } from "../api/client";
import { findQuoteSpans } from "../utils/citationMatch";
import { reflowText } from "../utils/textReflow";
import { hasDisplayConfidence } from "../utils/parallelDisplay";

export interface CitationTarget {
  textId: number;
  juanNum: number;
  chunkIndex: number;
  titleZh: string;
  /** The quoted passage, when the citation came from a 「…」 quote — lets the
   *  drawer highlight the exact sentence inside the cited chunk. */
  quote?: string;
}

// Map ISO language codes from alignment_pairs to display labels + font classes.
// The CSS lang attribute styles (see global.css) pick font families based on
// lang="pi" / lang="bo" etc so Devanagari and Tibetan render correctly.
const LANG_TAB_KEY: Record<string, string> = {
  lzh: "reader.citation.lang_tab.lzh",
  pi: "reader.citation.lang_tab.pi",
  sa: "reader.citation.lang_tab.sa",
  bo: "reader.citation.lang_tab.bo",
  en: "reader.citation.lang_tab.en",
};

interface Props {
  target: CitationTarget | null;
  onClose: () => void;
}

const CHUNK_OVERLAP_CHARS = 50;

/**
 * Strip the leading overlap from every non-first chunk so concatenation
 * yields continuous text. Chunks are 500 chars with 50-char overlap per
 * the ingestion pipeline; the first CHUNK_OVERLAP_CHARS of each follow-on
 * chunk duplicate the end of the previous one.
 */
function dedupeOverlap(chunks: ChunkContextItem[]): ChunkContextItem[] {
  if (chunks.length <= 1) return chunks;
  return chunks.map((c, i) => {
    if (i === 0) return c;
    const prev = chunks[i - 1].chunk_text;
    const prevTail = prev.slice(-CHUNK_OVERLAP_CHARS);
    if (c.chunk_text.startsWith(prevTail)) {
      return { ...c, chunk_text: c.chunk_text.slice(CHUNK_OVERLAP_CHARS) };
    }
    return c;
  });
}

/**
 * Snap the outer context edges to the nearest sentence boundary so the
 * panel does not start or end mid-sentence. Only trims chunks[0] head
 * and chunks[last] tail, and only when there is actually more text
 * outside the window (has_more_before/after) — otherwise we are at the
 * juan boundary and should show everything. Never touches the center
 * (highlighted) chunk.
 */
const SENTENCE_END = /[。！？；][”’》」』）)]*/g;

function snapSentenceBoundaries(
  chunks: ChunkContextItem[],
  hasMoreBefore: boolean,
  hasMoreAfter: boolean,
): ChunkContextItem[] {
  if (chunks.length === 0) return chunks;
  const out = chunks.map((c) => ({ ...c }));

  if (hasMoreBefore && !out[0].is_center) {
    const text = out[0].chunk_text;
    SENTENCE_END.lastIndex = 0;
    const m = SENTENCE_END.exec(text);
    if (m && m.index + m[0].length < text.length - 20) {
      out[0].chunk_text = text.slice(m.index + m[0].length).replace(/^\s+/, '');
    }
  }

  const lastIdx = out.length - 1;
  if (hasMoreAfter && !out[lastIdx].is_center) {
    const text = out[lastIdx].chunk_text;
    let lastEnd = -1;
    SENTENCE_END.lastIndex = 0;
    let m;
    while ((m = SENTENCE_END.exec(text)) !== null) {
      lastEnd = m.index + m[0].length;
    }
    if (lastEnd > 20) {
      out[lastIdx].chunk_text = text.slice(0, lastEnd).replace(/\s+$/, '');
    }
  }

  return out;
}


interface StitchedPassage {
  text: string;
  /** Char range of the cited chunk within `text`; [0,0) when there is none. */
  centerStart: number;
  centerEnd: number;
}

/**
 * Join the chunks into ONE continuous string, remembering where the cited
 * chunk sits inside it.
 *
 * The panel used to render one padded <div> per block (leading context /
 * center / trailing). Chunk boundaries fall every ~500 chars wherever the
 * ingestion pipeline happened to cut, so that put a visible gap in the middle
 * of whatever sentence straddled the seam — prod 2026-07-29 split
 * 「相各云何？頌曰：」 across two boxes and it read as truncated text. The
 * boundary is an implementation detail of chunking; it has no business being
 * visible to a reader checking a citation.
 */
/**
 * Widen a raw-coordinate range outward to the nearest sentence boundaries.
 *
 * Only used for the fallback highlight (the cited chunk), whose edges are
 * 500-char ingestion cut points. Left as-is they open and close mid-word, which
 * a reader reads as a broken highlight rather than "the passage is around here".
 * Widening, not narrowing: the cited chunk must stay fully covered.
 */
function snapToSentence(text: string, start: number, end: number): [number, number] {
  const BOUNDARY = /[。！？；]/;
  let lo = start;
  while (lo > 0 && !BOUNDARY.test(text[lo - 1])) lo--;
  let hi = end;
  while (hi < text.length && !BOUNDARY.test(text[hi - 1])) hi++;
  return [lo, hi];
}

function stitchChunks(chunks: ChunkContextItem[]): StitchedPassage {
  let text = "";
  let centerStart = 0;
  let centerEnd = 0;
  for (const c of chunks) {
    if (c.is_center && centerEnd === centerStart) {
      centerStart = text.length;
      centerEnd = text.length + c.chunk_text.length;
    } else if (c.is_center) {
      centerEnd = text.length + c.chunk_text.length;
    }
    text += c.chunk_text;
  }
  return { text, centerStart, centerEnd };
}

/**
 * Render the 汉文 passage as one continuous text with the quoted sentence
 * wrapped in <mark> and scrolled into view, so a citation lands on the exact
 * passage rather than a ~500-char chunk the reader must scan.
 *
 * Matching runs over the stitched passage, which also removes the old
 * split-quote problem for free: a sentence straddling a chunk seam used to be
 * highlighted in two halves because each block was matched separately.
 */
function CitationBlocks({ chunks, quote }: { chunks: ChunkContextItem[]; quote?: string }) {
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [chunks, quote]);

  const { text, centerStart, centerEnd } = stitchChunks(chunks);

  // Prefer the exact quoted sentence. Falling back to marking the whole cited
  // chunk only makes sense when we could not locate the quote — when we can,
  // the chunk tint marks a ~500-char window the reader still has to scan, and
  // its edges land on arbitrary cut points.
  //
  // Both spans are in RAW coordinates (newlines included). findQuoteSpan's
  // punctuation-tolerant pass strips \s and maps hits back to raw indices, so
  // a quote whose CBETA original is hard-wrapped mid-word still resolves.
  const quoteSpans = findQuoteSpans(text, quote);
  // Fallback: the quote could not be located even fragment-by-fragment, so mark
  // the cited chunk. Its edges are ingestion cut points, not sentence ends, so
  // snap them outward to the nearest boundary — a highlight that opens mid-word
  // reads as a rendering fault rather than "roughly here".
  const spans: [number, number][] =
    quoteSpans.length > 0
      ? quoteSpans
      : centerEnd > centerStart
        ? [snapToSentence(text, centerStart, centerEnd)]
        : [];
  const markClass =
    quoteSpans.length > 0
      ? "chat-citation-quote-mark"
      : "chat-citation-chunk-mark";

  // Same reflow the reader uses, so the passage reads as prose and verse
  // instead of CBETA's ~18-char source lines. Each segment carries the raw
  // offset of every character, which is what lets the highlight survive
  // re-segmentation — the marked range is expressed in raw coordinates and
  // simply re-found per segment.
  const segments = reflowText(text);

  // Per-segment highlight range, resolved before render: mutating a flag while
  // mapping would be a render-time side effect (react-hooks/immutability), and
  // the first highlighted segment has to be known up front anyway — that is
  // where the scroll anchor goes.
  // 每个 segment 内被高亮的字符区间（可能不止一段——省略号缩写的引文会命中多处）。
  const ranges = segments.map((seg) => {
    if (spans.length === 0 || seg.type === "break") return [];
    const out: [number, number][] = [];
    for (const [lo, hi] of spans) {
      let from = -1;
      let to = -1;
      for (let k = 0; k < seg.offsets.length; k++) {
        const o = seg.offsets[k];
        if (o >= lo && o < hi) {
          if (from < 0) from = k;
          to = k + 1;
        }
      }
      if (from >= 0) out.push([from, to]);
    }
    return out;
  });
  const anchorIdx = ranges.findIndex((r) => r.length > 0);

  return (
    <div
      className="chat-citation-body"
      style={{
        fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
        fontSize: 15,
        lineHeight: 1.9,
        color: "var(--fj-ink)",
      }}
    >
      {segments.map((seg, i) => {
        if (seg.type === "break") return <br key={i} />;
        const segRanges = ranges[i];
        if (segRanges.length === 0) {
          return <p key={i} className={`text-${seg.type}`}>{seg.text}</p>;
        }
        const parts: React.ReactNode[] = [];
        let cursor = 0;
        segRanges.forEach(([from, to], n) => {
          if (from > cursor) parts.push(seg.text.slice(cursor, from));
          parts.push(
            <mark
              key={`m${n}`}
              className={markClass}
              ref={i === anchorIdx && n === 0 ? markRef : undefined}
            >
              {seg.text.slice(from, to)}
            </mark>,
          );
          cursor = to;
        });
        if (cursor < seg.text.length) parts.push(seg.text.slice(cursor));
        return (
          <p key={i} className={`text-${seg.type}`}>{parts}</p>
        );
      })}
    </div>
  );
}

/**
 * Inline citation panel: a sibling of the main chat column inside a flex
 * row, sized by the parent via an explicit width passed through the CSS
 * class (see .chat-citation-panel in global.css). Not an antd Drawer —
 * we deliberately avoid the modal overlay so users can keep interacting
 * with the chat on the left while verifying the cited passage.
 */
export default function CitationDrawer({ target, onClose }: Props) {
  const { t } = useTranslation();
  const [activeLang, setActiveLang] = useState<string>("lzh");

  const { data, isLoading, error } = useQuery({
    queryKey: ["citation-context", target?.textId, target?.juanNum, target?.chunkIndex],
    queryFn: () =>
      getChunkContext(target!.textId, target!.juanNum, target!.chunkIndex, 2),
    enabled: target !== null,
    staleTime: 15 * 60 * 1000,
  });

  // Fetch cross-canon parallels (trilingual RAG). Independent from chunk context
  // so the main 汉文 passage renders immediately while parallels load in background.
  const { data: alignmentData } = useQuery({
    queryKey: ["citation-alignment", target?.textId, target?.juanNum, target?.chunkIndex],
    queryFn: () =>
      getChunkAlignment(target!.textId, target!.juanNum, target!.chunkIndex, 5),
    enabled: target !== null,
    staleTime: 15 * 60 * 1000,
    // parallels are optional — don't block rendering if this 404s or empty
    retry: false,
  });

  const dedupedChunks = useMemo(
    () =>
      data
        ? snapSentenceBoundaries(
            dedupeOverlap(data.chunks),
            data.has_more_before,
            data.has_more_after,
          )
        : [],
    [data],
  );

  // Group parallels by lang so each language becomes a tab.
  // Primary source (汉文) is always the first tab; additional langs appended.
  const parallelsByLang = useMemo(() => {
    const groups: Record<string, ParallelPair[]> = {};
    const parallels = alignmentData?.parallels || [];
    for (const p of parallels) {
      if (!groups[p.lang]) groups[p.lang] = [];
      groups[p.lang].push(p);
    }
    return groups;
  }, [alignmentData]);

  const availableLangs = useMemo(() => {
    const langs = ["lzh"];
    for (const lang of Object.keys(parallelsByLang)) {
      if (lang !== "lzh" && !langs.includes(lang)) langs.push(lang);
    }
    return langs;
  }, [parallelsByLang]);

  const hasParallels = availableLangs.length > 1;

  // 汉文 body, shared by the tabbed and untabbed layouts.
  //
  // The empty branch matters: a 200 response can still carry zero chunks (the
  // cited chunk does not exist — unknown juan, index past the end, or a text
  // with no embeddings). Rendering the boundary hints around an empty body told
  // the reader「前文（本卷第 0 段之前）」— a claim that content exists just out of
  // view, when in fact nothing was found. Say so plainly instead.
  const lzhBody =
    dedupedChunks.length === 0 ? (
      <Alert
        type="warning"
        showIcon
        message={t("reader.citation.empty")}
        description={t("reader.citation.empty_desc")}
      />
    ) : (
      <>
        {data?.has_more_before && (
          <div className="chat-citation-boundary-hint">
            {t("reader.citation.before_context", { n: dedupedChunks[0].chunk_index })}
          </div>
        )}
        <CitationBlocks chunks={dedupedChunks} quote={target?.quote} />
        {data?.has_more_after && (
          <div className="chat-citation-boundary-hint">
            {t("reader.citation.after_context", {
              n: dedupedChunks[dedupedChunks.length - 1].chunk_index,
            })}
          </div>
        )}
      </>
    );

  const readerUrl = target
    ? `/texts/${target.textId}/read?juan=${target.juanNum}&highlight_chunk=${target.chunkIndex}`
    : "#";

  const titleText = target
    ? t("reader.citation.title_with_juan", {
        title: target.titleZh || data?.title_zh || "",
        n: target.juanNum,
      })
    : t("reader.citation.title");

  return (
    <>
      <div className="chat-citation-panel-header">
        <span className="chat-citation-panel-title">
          <BookOutlined />
          <span style={{ fontFamily: '"Noto Serif SC", serif' }}>{titleText}</span>
        </span>
        <Button
          type="text"
          size="small"
          icon={<CloseOutlined />}
          onClick={onClose}
          aria-label={t("reader.citation.close")}
        />
      </div>

      <div className="chat-citation-panel-body">
        {isLoading && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <Spin />
            <div style={{ marginTop: 12, color: "var(--fj-ink-muted)", fontSize: 13 }}>
              {t("reader.citation.loading")}
            </div>
          </div>
        )}

        {error && (
          <Alert
            type="error"
            showIcon
            message={t("reader.citation.load_failed")}
            description={t("reader.citation.load_failed_desc")}
          />
        )}

        {data && !isLoading && !error && (
          <>
            {hasParallels ? (
              <Tabs
                size="small"
                activeKey={activeLang}
                onChange={setActiveLang}
                items={availableLangs.map((lang) => ({
                  key: lang,
                  label: (
                    <span>
                      {lang === "lzh" ? <BookOutlined /> : <GlobalOutlined />} {LANG_TAB_KEY[lang] ? t(LANG_TAB_KEY[lang]) : lang}
                      {lang !== "lzh" && parallelsByLang[lang] && ` (${parallelsByLang[lang].length})`}
                    </span>
                  ),
                  children: lang === "lzh" ? (
                    <div lang="zh-Hans">{lzhBody}</div>
                  ) : (
                    <div lang={lang}>
                      {(parallelsByLang[lang] || []).map((p, idx) => (
                        <div
                          key={`${p.text_id}-${p.juan_num}-${p.chunk_index}-${idx}`}
                          className="chat-citation-chunk"
                          style={{
                            fontSize: 15,
                            lineHeight: 1.9,
                            color: "var(--fj-ink)",
                          }}
                        >
                          {p.title && (
                            <div
                              style={{
                                fontSize: 12,
                                color: "var(--fj-ink-muted)",
                                marginBottom: 6,
                                fontStyle: "italic",
                              }}
                            >
                              {hasDisplayConfidence(p)
                                ? t("reader.citation.parallel_title", {
                                    title: p.title,
                                    n: p.juan_num,
                                    confidence: (p.confidence * 100).toFixed(0),
                                  })
                                : t("reader.citation.parallel_title_mitra", {
                                    title: p.title,
                                  })}
                            </div>
                          )}
                          {p.chunk_text}
                        </div>
                      ))}
                    </div>
                  ),
                }))}
              />
            ) : (
              <div lang="zh-Hans">{lzhBody}</div>
            )}
          </>
        )}
      </div>

      <div className="chat-citation-panel-footer">
        <Link to={readerUrl} onClick={onClose}>
          <Button
            type="primary"
            size="middle"
            icon={<ArrowRightOutlined />}
            style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
          >
            {t("reader.citation.open_reader")}
          </Button>
        </Link>
      </div>
    </>
  );
}
