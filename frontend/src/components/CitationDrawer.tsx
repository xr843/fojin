import { useMemo } from "react";
import { Button, Spin, Alert } from "antd";
import { BookOutlined, ArrowRightOutlined, CloseOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getChunkContext, type ChunkContextItem } from "../api/client";

export interface CitationTarget {
  textId: number;
  juanNum: number;
  chunkIndex: number;
  titleZh: string;
}

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
 * Inline citation panel: a sibling of the main chat column inside a flex
 * row, sized by the parent via an explicit width passed through the CSS
 * class (see .chat-citation-panel in global.css). Not an antd Drawer —
 * we deliberately avoid the modal overlay so users can keep interacting
 * with the chat on the left while verifying the cited passage.
 */
export default function CitationDrawer({ target, onClose }: Props) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["citation-context", target?.textId, target?.juanNum, target?.chunkIndex],
    queryFn: () =>
      getChunkContext(target!.textId, target!.juanNum, target!.chunkIndex, 2),
    enabled: target !== null,
    staleTime: 15 * 60 * 1000,
  });

  const dedupedChunks = useMemo(
    () => (data ? dedupeOverlap(data.chunks) : []),
    [data],
  );

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
          </>
        )}
      </div>

      <div className="chat-citation-panel-footer">
        <Button onClick={onClose} size="middle">
          关闭
        </Button>
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
