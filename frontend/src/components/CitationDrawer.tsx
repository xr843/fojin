import { useEffect, useMemo, useState } from "react";
import { Drawer, Button, Spin, Alert } from "antd";
import { BookOutlined, ArrowRightOutlined } from "@ant-design/icons";
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
  open: boolean;
  target: CitationTarget | null;
  onClose: () => void;
}

const MOBILE_BREAKPOINT = 768;
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

function useIsMobile(): boolean {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`).matches,
  );
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT}px)`);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);
  return isMobile;
}

export default function CitationDrawer({ open, target, onClose }: Props) {
  const isMobile = useIsMobile();

  const { data, isLoading, error } = useQuery({
    queryKey: ["citation-context", target?.textId, target?.juanNum, target?.chunkIndex],
    queryFn: () =>
      getChunkContext(target!.textId, target!.juanNum, target!.chunkIndex, 2),
    enabled: open && target !== null,
    staleTime: 15 * 60 * 1000,
  });

  const dedupedChunks = useMemo(
    () => (data ? dedupeOverlap(data.chunks) : []),
    [data],
  );

  const drawerPlacement = isMobile ? "bottom" : "right";
  const drawerSize = isMobile
    ? { height: "70vh" as const, width: "100%" as const }
    : { width: 480 };

  const readerUrl = target
    ? `/texts/${target.textId}/read?juan=${target.juanNum}&highlight_chunk=${target.chunkIndex}`
    : "#";

  const titleText = target
    ? `《${target.titleZh || data?.title_zh || ""}》· 第 ${target.juanNum} 卷`
    : "原文对照";

  return (
    <Drawer
      open={open}
      onClose={onClose}
      placement={drawerPlacement}
      {...drawerSize}
      title={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <BookOutlined style={{ color: "var(--fj-accent)" }} />
          <span style={{ fontFamily: '"Noto Serif SC", serif', fontSize: 16 }}>
            {titleText}
          </span>
        </div>
      }
      styles={{
        body: { padding: 0, display: "flex", flexDirection: "column" },
      }}
      destroyOnHidden={false}
    >
      <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
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
              <div
                style={{
                  fontSize: 12,
                  color: "var(--fj-ink-muted)",
                  textAlign: "center",
                  marginBottom: 12,
                  fontStyle: "italic",
                }}
              >
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
                  style={{
                    padding: "8px 12px",
                    marginBottom: 6,
                    borderRadius: 4,
                    borderLeft: c.is_center ? "3px solid var(--fj-accent)" : "3px solid transparent",
                    background: c.is_center ? "rgba(255, 220, 90, 0.15)" : "transparent",
                    transition: "all 0.2s",
                  }}
                >
                  {c.chunk_text}
                </div>
              ))}
            </div>

            {data.has_more_after && (
              <div
                style={{
                  fontSize: 12,
                  color: "var(--fj-ink-muted)",
                  textAlign: "center",
                  marginTop: 12,
                  fontStyle: "italic",
                }}
              >
                … 后文（本卷第 {data.chunks[data.chunks.length - 1]?.chunk_index ?? 0} 段之后）
              </div>
            )}
          </>
        )}
      </div>

      <div
        style={{
          borderTop: "1px solid rgba(217,208,193,0.5)",
          padding: "12px 20px",
          display: "flex",
          justifyContent: "flex-end",
          gap: 8,
          background: "rgba(249, 246, 239, 0.6)",
        }}
      >
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
    </Drawer>
  );
}
