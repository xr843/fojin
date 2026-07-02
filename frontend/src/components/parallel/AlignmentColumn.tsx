import type { Ref } from "react";
import { Card, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { ParallelTextContent, JuanAlignmentResponse } from "../../api/client";

const LANG_LABEL_KEY: Record<string, string> = {
  lzh: "parallel.column.lang.lzh",
  pi: "parallel.column.lang.pi",
  sa: "parallel.column.lang.sa",
  bo: "parallel.column.lang.bo",
  en: "parallel.column.lang.en",
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
  selectedKeys?: Set<string>;
  onChunkClick?: (chunkIndex: number, paragraph: string) => void;
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

export default function AlignmentColumn({
  text,
  alignment,
  scrollRef,
  selectedKeys,
  onChunkClick,
}: Props) {
  const { t } = useTranslation();
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
            {LANG_LABEL_KEY[text.lang] ? t(LANG_LABEL_KEY[text.lang]) : text.lang}
          </Tag>
        </div>
      }
    >
      <div ref={scrollRef} className="parallel-column-scroll" data-text-id={text.text_id}>
        {paragraphs.map((p, i) => {
          const idx = chunkIndexFor(p, chunkIndex);
          const selectionKey = idx !== null ? `${text.text_id}:${idx}` : "";
          const isSelected = idx !== null && selectedKeys?.has(selectionKey);
          const isClickable = onChunkClick && idx !== null;
          return (
            <p
              key={i}
              className={`parallel-paragraph${isSelected ? " is-selected" : ""}`}
              data-chunk-index={idx ?? undefined}
              lang={text.lang}
              onClick={isClickable ? () => onChunkClick(idx, p) : undefined}
              style={isClickable ? { cursor: "pointer" } : undefined}
            >
              {p}
            </p>
          );
        })}
      </div>
    </Card>
  );
}
