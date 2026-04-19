import { useMemo, useState } from "react";
import { Button, Spin, Alert, Tabs } from "antd";
import { BookOutlined, ArrowRightOutlined, CloseOutlined, GlobalOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getChunkContext, getChunkAlignment, type ChunkContextItem, type ParallelPair } from "../api/client";

export interface CitationTarget {
  textId: number;
  juanNum: number;
  chunkIndex: number;
  titleZh: string;
}

// Map ISO language codes from alignment_pairs to display labels + font classes.
// The CSS lang attribute styles (see global.css) pick font families based on
// lang="pi" / lang="bo" etc so Devanagari and Tibetan render correctly.
const LANG_CONFIG: Record<string, { label: string; tab: string }> = {
  lzh: { label: "汉", tab: "汉文" },
  pi: { label: "巴", tab: "巴利" },
  sa: { label: "梵", tab: "梵文" },
  bo: { label: "藏", tab: "藏文" },
  en: { label: "英", tab: "English" },
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

/**
 * Inline citation panel: a sibling of the main chat column inside a flex
 * row, sized by the parent via an explicit width passed through the CSS
 * class (see .chat-citation-panel in global.css). Not an antd Drawer —
 * we deliberately avoid the modal overlay so users can keep interacting
 * with the chat on the left while verifying the cited passage.
 */
export default function CitationDrawer({ target, onClose }: Props) {
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

  const readerUrl = target
    ? `/texts/${target.textId}/read?juan=${target.juanNum}&highlight_chunk=${target.chunkIndex}`
    : "#";

  const titleText = target
    ? `《${target.titleZh || data?.title_zh || ""}》· 第 ${target.juanNum} 卷`
    : "原文对照";

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
          aria-label="关闭原文对照"
        />
      </div>

      <div className="chat-citation-panel-body">
        {isLoading && (
          <div style={{ textAlign: "center", padding: "40px 0" }}>
            <Spin />
            <div style={{ marginTop: 12, color: "var(--fj-ink-muted)", fontSize: 13 }}>
              正在加载原文…
            </div>
          </div>
        )}

        {error && (
          <Alert
            type="error"
            showIcon
            message="无法加载原文"
            description="可能是该段暂未入库，请尝试在完整阅读器中打开。"
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
                      {lang === "lzh" ? <BookOutlined /> : <GlobalOutlined />} {LANG_CONFIG[lang]?.tab || lang}
                      {lang !== "lzh" && parallelsByLang[lang] && ` (${parallelsByLang[lang].length})`}
                    </span>
                  ),
                  children: lang === "lzh" ? (
                    <div lang="zh-Hans">
                      {data.has_more_before && (
                        <div className="chat-citation-boundary-hint">
                          … 前文（本卷第 {data.chunks[0]?.chunk_index ?? 0} 段之前）
                        </div>
                      )}
                      <div
                        style={{
                          fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
                          fontSize: 15,
                          lineHeight: 1.9,
                          color: "var(--fj-ink)",
                        }}
                      >
                        {dedupedChunks.map((c) => (
                          <div
                            key={c.chunk_index}
                            className={`chat-citation-chunk${c.is_center ? " chat-citation-chunk-center" : ""}`}
                          >
                            {c.chunk_text}
                          </div>
                        ))}
                      </div>
                      {data.has_more_after && (
                        <div className="chat-citation-boundary-hint">
                          … 后文（本卷第 {data.chunks[data.chunks.length - 1]?.chunk_index ?? 0} 段之后）
                        </div>
                      )}
                    </div>
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
                              《{p.title}》 第 {p.juan_num} 卷 · 置信度 {(p.confidence * 100).toFixed(0)}%
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
              <div lang="zh-Hans">
                {data.has_more_before && (
                  <div className="chat-citation-boundary-hint">
                    … 前文（本卷第 {data.chunks[0]?.chunk_index ?? 0} 段之前）
                  </div>
                )}
                <div
                  style={{
                    fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
                    fontSize: 15,
                    lineHeight: 1.9,
                    color: "var(--fj-ink)",
                  }}
                >
                  {dedupedChunks.map((c) => (
                    <div
                      key={c.chunk_index}
                      className={`chat-citation-chunk${c.is_center ? " chat-citation-chunk-center" : ""}`}
                    >
                      {c.chunk_text}
                    </div>
                  ))}
                </div>
                {data.has_more_after && (
                  <div className="chat-citation-boundary-hint">
                    … 后文（本卷第 {data.chunks[data.chunks.length - 1]?.chunk_index ?? 0} 段之后）
                  </div>
                )}
              </div>
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
            在阅读器中打开
          </Button>
        </Link>
      </div>
    </>
  );
}
