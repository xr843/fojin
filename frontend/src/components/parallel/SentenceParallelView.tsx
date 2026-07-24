import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Spin, Alert, Empty, Tag, Button } from "antd";
import { useTranslation } from "react-i18next";
import { getSentenceParallels, type SentencePair } from "../../api/client";

interface Props {
  textId: number;
  juanNum: number;
}

// Same lang → color mapping the sibling ChunkView/CanonicalView use, so the
// foreign-side tag reads consistently across the three parallel tabs.
const LANG_COLOR: Record<string, string> = {
  lzh: "gold",
  pi: "cyan",
  sa: "purple",
  bo: "magenta",
  en: "geekblue",
};

// bertalign 'moves': 1-1 needs no badge; 1-2 / 2-1 signal one-to-many spans
// (the backend has already merged the many side into side_a.text/side_b.text).
function alignBadgeKey(alignType: SentencePair["align_type"]): string | null {
  if (alignType === "1-2") return "reader.parallel.sentence.align_1_2";
  if (alignType === "2-1") return "reader.parallel.sentence.align_2_1";
  return null;
}

function SentencePairCard({
  pair,
  active,
  onToggle,
}: {
  pair: SentencePair;
  active: boolean;
  onToggle: (el: HTMLDivElement | null) => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDivElement>(null);
  const badgeKey = alignBadgeKey(pair.align_type);
  return (
    <div
      ref={ref}
      data-testid="sentence-pair-card"
      className={`sentence-pair-card${active ? " is-active" : ""}`}
      onClick={() => onToggle(ref.current)}
      style={{
        padding: "10px 12px",
        marginBottom: 10,
        borderRadius: 4,
        cursor: "pointer",
        background: active ? "#e6f4ff" : "#fff",
        border: `1px solid ${active ? "#69b1ff" : "#e8e8e8"}`,
        transition: "background 0.15s, border-color 0.15s",
      }}
    >
      <div
        lang={pair.side_a.lang}
        style={{
          fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
          fontSize: 14,
          lineHeight: 1.9,
          color: "#222",
        }}
      >
        {pair.side_a.text}
      </div>
      <div
        lang={pair.side_b.lang}
        style={{
          marginTop: 6,
          paddingTop: 6,
          borderTop: "1px dashed #eee",
          fontSize: 13,
          lineHeight: pair.side_b.lang === "bo" ? 2.1 : 1.85,
          color: "#555",
        }}
      >
        {pair.side_b.text}
      </div>
      <div
        style={{
          marginTop: 6,
          display: "flex",
          alignItems: "center",
          gap: 6,
          flexWrap: "wrap",
          fontSize: 12,
          color: "var(--fj-text-secondary)",
        }}
      >
        <Tag color={LANG_COLOR[pair.side_b.lang] || "default"} style={{ margin: 0 }}>
          {pair.side_b.lang}
        </Tag>
        {pair.side_b.title && <span>{pair.side_b.title}</span>}
        {badgeKey && (
          <Tag color="blue" style={{ margin: 0 }}>
            {t(badgeKey)}
          </Tag>
        )}
        {pair.is_verified && (
          <Tag color="green" style={{ margin: 0 }}>
            {t("reader.parallel.sentence.verified")}
          </Tag>
        )}
        <span style={{ marginLeft: "auto" }}>{pair.similarity.toFixed(2)}</span>
      </div>
    </div>
  );
}

/**
 * 逐句对读视图（P4-C 前端）。消费冻结的
 * GET /api/alignment/sentences/{textId}/{juanNum} 契约，把句级对齐渲染为堆叠
 * 句对卡片（汉文上、外文下）。与 CanonicalView / ChunkView 平级，但独立成文件
 * 以便单测隔离。空数据（flag 关 / 空表）→ Empty，永不报错（ship-dark）。
 */
export default function SentenceParallelView({ textId, juanNum }: Props) {
  const { t } = useTranslation();
  // Click-to-pin: which pair index is active (null = none). Pure UI state.
  const [active, setActive] = useState<number | null>(null);
  // Reset the active pin when the reader navigates to another text/juan, so a
  // stale index can't stay highlighted against a different pair list.
  const [prevKey, setPrevKey] = useState(`${textId}:${juanNum}`);
  if (prevKey !== `${textId}:${juanNum}`) {
    setPrevKey(`${textId}:${juanNum}`);
    setActive(null);
  }
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["sentence-parallels", textId, juanNum],
    queryFn: () => getSentenceParallels(textId, juanNum),
    enabled: textId > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin />
        <div style={{ marginTop: 12, color: "#888" }}>{t("reader.parallel.sentence.loading")}</div>
      </div>
    );
  }
  if (isError) {
    return (
      <Alert
        type="error"
        showIcon
        message={t("reader.parallel.sentence.load_error")}
        action={
          <Button size="small" onClick={() => refetch()}>
            {t("reader.parallel.sentence.retry")}
          </Button>
        }
        style={{ margin: 12 }}
      />
    );
  }
  if (!data || data.total === 0) {
    return (
      <Empty
        description={t("reader.parallel.sentence.empty")}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 40 }}
      />
    );
  }

  return (
    <div className="sentence-parallel-view" style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
      {data.pairs.map((p, i) => (
        <SentencePairCard
          key={i}
          pair={p}
          active={active === i}
          onToggle={(el) => {
            const next = active === i ? null : i;
            setActive(next);
            // jsdom has no real scrollIntoView — guard so tests don't throw.
            if (next !== null) el?.scrollIntoView?.({ block: "nearest" });
          }}
        />
      ))}
    </div>
  );
}
