import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Empty, Spin, Alert, Collapse, Tag, Progress, Tabs, Button } from "antd";
import { LinkOutlined, BookOutlined, ExpandAltOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getJuanAlignment, getCanonicalParallels, getFullParallelContent, getSentenceParallels } from "../api/client";
import OtherVersions from "./OtherVersions";
import SentenceParallelView from "./parallel/SentenceParallelView";

interface Props {
  textId: number;
  juanNum: number;
}

const LANG_LABEL_KEY: Record<string, string> = {
  lzh: "reader.parallel.lang.lzh",
  pi: "reader.parallel.lang.pi",
  sa: "reader.parallel.lang.sa",
  bo: "reader.parallel.lang.bo",
  en: "reader.parallel.lang.en",
};

const LANG_SHORT_LABEL_KEY: Record<string, string> = {
  lzh: "reader.parallel.lang_short.lzh",
  pi: "reader.parallel.lang_short.pi",
  sa: "reader.parallel.lang_short.sa",
  bo: "reader.parallel.lang_short.bo",
  en: "reader.parallel.lang_short.en",
};

const LANG_COLOR: Record<string, string> = {
  lzh: "gold",
  pi: "cyan",
  sa: "purple",
  bo: "magenta",
  en: "geekblue",
};

const RELATION_LABEL_KEY: Record<string, string> = {
  parallel: "reader.parallel.relation.parallel",
  mention: "reader.parallel.relation.mention",
  retell: "reader.parallel.relation.retell",
};

const RELATION_COLOR: Record<string, string> = {
  parallel: "green",
  mention: "orange",
  retell: "purple",
};

function ParallelCardBody({ p }: { p: import("../api/client").CanonicalParallel }) {
  const { t } = useTranslation();
  const [showFull, setShowFull] = useState(false);
  const { data: full, isLoading: loadingFull } = useQuery({
    queryKey: ["canonical-parallel-full", p.related_text_id],
    queryFn: () => getFullParallelContent(p.related_text_id),
    enabled: showFull,
    staleTime: 30 * 60 * 1000,
  });

  const paliDisplay = full?.pali_full ?? (p.pali_preview ? `${p.pali_preview}…` : null);
  const englishDisplay = full?.english_full ?? (p.english_preview ? `${p.english_preview}…` : null);

  return (
    <div style={{ paddingLeft: 8, borderLeft: "2px solid #e8e8e8" }}>
      {paliDisplay && (
        <div style={{ marginBottom: 10, padding: "8px 10px", background: "#f6fafd", borderLeft: "3px solid #5b8c6b", borderRadius: 4 }}>
          <div style={{ fontSize: 11, color: "#5b8c6b", marginBottom: 4, fontWeight: 500, display: "flex", justifyContent: "space-between" }}>
            <span>{t("reader.parallel.pali_original")}</span>
            {full?.pali_chars ? (
              <span style={{ color: "#999", fontWeight: 400 }}>
                {t("reader.parallel.char_count", { n: full.pali_chars.toLocaleString() })}
              </span>
            ) : null}
          </div>
          <div
            lang="pi"
            className="parallel-full-scroll"
            style={{
              fontSize: 12, lineHeight: 1.8, color: "#333",
              maxHeight: showFull ? 360 : undefined,
              overflowY: showFull ? "auto" : undefined,
              whiteSpace: "pre-wrap",
            }}
          >
            {paliDisplay}
          </div>
        </div>
      )}
      {englishDisplay && (
        <div style={{ marginBottom: 10, padding: "8px 10px", background: "#fafafa", borderRadius: 4 }}>
          <div style={{ fontSize: 11, color: "#666", marginBottom: 4, fontWeight: 500, display: "flex", justifyContent: "space-between" }}>
            <span>English (Sujato)</span>
            {full?.english_chars ? <span style={{ color: "#999", fontWeight: 400 }}>{full.english_chars.toLocaleString()} chars</span> : null}
          </div>
          <div
            lang="en"
            className="parallel-full-scroll"
            style={{
              fontSize: 12, lineHeight: 1.8, color: "#333",
              maxHeight: showFull ? 360 : undefined,
              overflowY: showFull ? "auto" : undefined,
              whiteSpace: "pre-wrap",
            }}
          >
            {englishDisplay}
          </div>
        </div>
      )}
      <div style={{ marginTop: 8, fontSize: 12, display: "flex", gap: 12, flexWrap: "wrap" }}>
        {!showFull && (
          <Button
            type="link"
            size="small"
            icon={<ExpandAltOutlined />}
            onClick={() => setShowFull(true)}
            loading={loadingFull}
            style={{ padding: 0, height: "auto", color: "#5b8c6b" }}
          >
            {t("reader.parallel.expand_full")}
          </Button>
        )}
        <Link
          to={`/texts/${p.related_text_id}/read?juan=1`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#5b8c6b" }}
        >
          <BookOutlined style={{ marginRight: 4 }} />
          {t("reader.parallel.open_reader")}
        </Link>
      </div>
    </div>
  );
}

function CanonicalView({ textId }: { textId: number }) {
  const { t } = useTranslation();
  const [activeKeys, setActiveKeys] = useState<string[]>([]);
  const { data, isLoading, error } = useQuery({
    queryKey: ["canonical-parallels", textId],
    queryFn: () => getCanonicalParallels(textId),
    enabled: textId > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin />
        <div style={{ marginTop: 12, color: "#888" }}>{t("reader.parallel.canonical.loading")}</div>
      </div>
    );
  }
  if (error) {
    return <Alert type="error" showIcon message={t("reader.parallel.load_failed")} style={{ margin: 12 }} />;
  }
  if (!data || data.total === 0) {
    return (
      <Empty
        description={t("reader.parallel.canonical.empty")}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 40 }}
      />
    );
  }

  return (
    <>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee", fontSize: 13, color: "#555" }}>
        {t("reader.parallel.canonical.summary", { title: data.source_title, n: data.total })}
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
        <Collapse
          activeKey={activeKeys}
          onChange={(keys) => setActiveKeys(Array.isArray(keys) ? keys : [keys])}
          ghost
          items={data.parallels.map((p, idx) => ({
            key: `${p.related_text_id}-${idx}`,
            label: (
              <div style={{ paddingRight: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
                  <Tag color={RELATION_COLOR[p.relation_type] || "default"} style={{ margin: 0 }}>
                    {RELATION_LABEL_KEY[p.relation_type] ? t(RELATION_LABEL_KEY[p.relation_type]) : p.relation_type}
                  </Tag>
                  <Tag color={LANG_COLOR[p.related_lang] || "default"} style={{ margin: 0 }}>
                    {LANG_LABEL_KEY[p.related_lang] ? t(LANG_LABEL_KEY[p.related_lang]) : p.related_lang}
                  </Tag>
                  <span style={{ fontSize: 12, color: "#666", fontWeight: 500 }}>
                    《{p.related_title}》
                  </span>
                </div>
                {p.note && (
                  <div style={{ fontSize: 11, color: "#999" }}>{p.note}</div>
                )}
              </div>
            ),
            children: <ParallelCardBody p={p} />,
          }))}
        />
        <div style={{ marginTop: 20, padding: 12, background: "#fafafa", borderRadius: 4, fontSize: 12, color: "#666" }}>
          <LinkOutlined style={{ marginRight: 6 }} />
          {t("reader.parallel.canonical.attribution")}
        </div>
      </div>
    </>
  );
}

function ChunkView({ textId, juanNum }: Props) {
  const { t } = useTranslation();
  const [activeKeys, setActiveKeys] = useState<string[]>([]);
  const { data, isLoading, error } = useQuery({
    queryKey: ["juan-alignment", textId, juanNum],
    queryFn: () => getJuanAlignment(textId, juanNum),
    enabled: textId > 0 && juanNum > 0,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const coveragePct = data && data.total_chunks > 0
    ? Math.round((data.chunks_with_parallels / data.total_chunks) * 100)
    : 0;

  if (isLoading) {
    return (
      <div style={{ textAlign: "center", padding: 80 }}>
        <Spin />
        <div style={{ marginTop: 12, color: "#888" }}>{t("reader.parallel.chunk.loading")}</div>
      </div>
    );
  }
  if (error) {
    return (
      <Alert
        type="info" showIcon
        message={t("reader.parallel.chunk.no_data")}
        description={t("reader.parallel.chunk.no_data_desc")}
        style={{ margin: 12 }}
      />
    );
  }
  if (!data) return null;

  return (
    <>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <span style={{ fontSize: 13, color: "#555" }}>{t("reader.parallel.chunk.coverage")}</span>
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            {t("reader.parallel.chunk.coverage_count", {
              matched: data.chunks_with_parallels,
              total: data.total_chunks,
              pct: coveragePct,
            })}
          </span>
        </div>
        <Progress percent={coveragePct} size="small" showInfo={false}
          strokeColor={coveragePct > 50 ? "#5b8c6b" : coveragePct > 20 ? "#d48806" : "#999"} />
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
        {data.entries.length === 0 && (
          <Empty description={t("reader.parallel.chunk.empty")} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
        {data.entries.length > 0 && (
          <Collapse
            activeKey={activeKeys}
            onChange={(keys) => setActiveKeys(Array.isArray(keys) ? keys : [keys])}
            ghost
            items={data.entries.map((entry) => ({
              key: `chunk-${entry.chunk_index}`,
              label: (
                <div style={{ paddingRight: 8 }}>
                  <div style={{ fontSize: 12, color: "#888", marginBottom: 4 }}>
                    {t("reader.parallel.chunk.item_label", {
                      index: entry.chunk_index,
                      n: entry.parallels.length,
                    })}
                  </div>
                  <div lang="zh-Hans" style={{
                    fontFamily: '"Noto Serif SC", "Source Han Serif", serif',
                    fontSize: 14, lineHeight: 1.7, color: "#222",
                    display: "-webkit-box", WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical", overflow: "hidden",
                  }}>
                    {entry.chunk_text}
                  </div>
                </div>
              ),
              children: (
                <div style={{ paddingLeft: 8, borderLeft: "2px solid #e8e8e8" }}>
                  <div lang="zh-Hans" style={{
                    fontFamily: '"Noto Serif SC", serif',
                    fontSize: 14, lineHeight: 1.9, color: "#333",
                    padding: "8px 12px", background: "#fafafa",
                    borderRadius: 4, marginBottom: 12,
                  }}>
                    {entry.chunk_text}
                  </div>
                  {entry.parallels.map((p, idx) => {
                    const isMitra = p.source === "mitra-parallel";
                    const langLabel = isMitra
                      ? (LANG_SHORT_LABEL_KEY[p.lang] ? t(LANG_SHORT_LABEL_KEY[p.lang]) : p.lang)
                      : (LANG_LABEL_KEY[p.lang] ? t(LANG_LABEL_KEY[p.lang]) : p.lang);
                    return (
                    <div key={`${p.source || "fojin"}-${p.text_id}-${p.juan_num}-${p.chunk_index}-${idx}`}
                      style={{ padding: "10px 12px", marginBottom: 10, borderRadius: 4,
                        background: "#fff", border: "1px solid #e8e8e8" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                        <Tag color={LANG_COLOR[p.lang] || "default"} style={{ margin: 0 }}>
                          {langLabel}
                        </Tag>
                        {isMitra ? (
                          <Tag color="volcano" style={{ margin: 0 }}>MITRA</Tag>
                        ) : (
                          <span style={{ fontSize: 12, color: "#666" }}>
                            {t("reader.parallel.text_fascicle", {
                              title: p.title || t("reader.parallel.other_canon"),
                              n: p.juan_num,
                            })}
                          </span>
                        )}
                        {!isMitra && (
                          <span style={{ fontSize: 11, color: "#999", marginLeft: "auto" }}>
                            {t("reader.parallel.confidence", { n: (p.confidence * 100).toFixed(0) })}
                          </span>
                        )}
                      </div>
                      <div lang={p.lang} style={{
                        fontSize: 13,
                        lineHeight: p.lang === "bo" ? 2.1 : 1.85,
                        color: "#333",
                      }}>
                        …{p.chunk_text}…
                      </div>
                      {p.original_preview && p.original_lang && (
                        <div lang={p.original_lang} style={{
                          marginTop: 8, padding: "8px 10px",
                          background: "#f6fafd", borderLeft: "3px solid #5b8c6b",
                          fontSize: 12, lineHeight: 1.8, color: "#444",
                        }}>
                          <div style={{ fontSize: 11, color: "#5b8c6b", marginBottom: 4, fontWeight: 500 }}>
                            {p.original_lang === "pi"
                              ? t("reader.parallel.original_preview_pali")
                              : t("reader.parallel.original_preview")}
                          </div>
                          {p.original_preview}
                          {p.original_preview.length >= 500 && "…"}
                        </div>
                      )}
                      {isMitra ? (
                        <div style={{ marginTop: 8, fontSize: 11, color: "#999" }}>
                          MITRA · CC BY-SA 4.0
                        </div>
                      ) : (
                        <div style={{ marginTop: 8, fontSize: 12 }}>
                          <Link
                            to={`/texts/${p.text_id}/read?juan=${p.juan_num}`}
                            target="_blank" rel="noopener noreferrer"
                            style={{ color: "#5b8c6b" }}
                          >
                            <BookOutlined style={{ marginRight: 4 }} />
                            {t("reader.parallel.read_full")}
                          </Link>
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
              ),
            }))}
          />
        )}
      </div>
    </>
  );
}

/**
 * Reader 右侧"跨藏对照"统一面板（非 modal）。一处汇聚三种跨藏视角：
 *  - 其他版本：同一 FRBR Work 的不同译本（Work 脊椎，来源 work_witnesses）
 *  - 按经对读（默认 tab）：SuttaCentral 权威经级对应，来源 text_relations
 *  - 按段对读（实验）：embedding+LLM 段级对齐，来源 alignment_pairs
 *
 * 「其他版本」= 同一部经的不同语言译本（最直接的跨藏入口），无则不渲染；
 * 「对读」= 相关但不同的经文之间的平行关系。
 */
export default function ReaderParallelPanel({ textId, juanNum }: Props) {
  const { t } = useTranslation();
  // Default-tab selection: most Mahayana texts have no SuttaCentral (按经对读)
  // parallel but DO have MITRA 段级 parallels, so landing on an empty 按经对读
  // reads as "no data". When canonical is empty, default to 按段对读. The query
  // shares CanonicalView's cache key (deduped). activeKey=undefined means
  // "auto"; a user click pins it. Reset on textId change so auto re-applies.
  const [activeKey, setActiveKey] = useState<string | undefined>(undefined);
  const [prevTextId, setPrevTextId] = useState(textId);
  if (prevTextId !== textId) {
    setPrevTextId(textId);
    setActiveKey(undefined);
  }
  const { data: canonical, isSuccess, isError } = useQuery({
    queryKey: ["canonical-parallels", textId],
    queryFn: () => getCanonicalParallels(textId),
    enabled: textId > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  // Ship-dark gate for 按句对读: only surface the sentence tab once the frozen
  // P4-C endpoint reports rows for this juan. Shares SentenceParallelView's
  // query key, so react-query dedupes — this is a lightweight total-only read,
  // not a second request. Left off the effectiveKey default logic on purpose
  // (design: sentence stays a third clickable tab, never the auto-default).
  const { data: sentence } = useQuery({
    queryKey: ["sentence-parallels", textId, juanNum],
    queryFn: () => getSentenceParallels(textId, juanNum),
    enabled: textId > 0,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const hasSentence = (sentence?.total ?? 0) > 0;
  // Once the canonical query has SETTLED (success or error), default to 按段对读
  // unless canonical actually has content. Treating the error path as "empty" is
  // deliberate: a failed canonical query must not strand the user on the empty
  // 按经对读 tab when MITRA 段级 parallels exist in 按段对读. While still loading,
  // hold on canonical to avoid a flash. A user click (activeKey) always wins.
  const settled = isSuccess || isError;
  const effectiveKey =
    activeKey ?? (settled ? ((canonical?.total ?? 0) > 0 ? "canonical" : "chunk") : "canonical");
  return (
    <div className="reader-parallel-panel">
      <div style={{ padding: "0 12px" }}>
        <OtherVersions textId={textId} />
      </div>
      <Tabs
        activeKey={effectiveKey}
        onChange={setActiveKey}
        size="small"
        style={{ padding: "0 12px" }}
        items={[
          {
            key: "canonical",
            label: t("reader.parallel.tab_canonical"),
            children: <CanonicalView textId={textId} />,
          },
          {
            key: "chunk",
            label: t("reader.parallel.tab_chunk"),
            children: <ChunkView textId={textId} juanNum={juanNum} />,
          },
          ...(hasSentence
            ? [
                {
                  key: "sentence",
                  label: t("reader.parallel.tab_sentence"),
                  children: <SentenceParallelView textId={textId} juanNum={juanNum} />,
                },
              ]
            : []),
        ]}
      />
    </div>
  );
}
