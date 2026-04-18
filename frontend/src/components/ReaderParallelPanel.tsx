import { useState } from "react";
import { Empty, Spin, Alert, Collapse, Tag, Progress, Tabs, Button } from "antd";
import { LinkOutlined, BookOutlined, ExpandAltOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getJuanAlignment, getCanonicalParallels, getFullParallelContent } from "../api/client";

interface Props {
  textId: number;
  juanNum: number;
}

const LANG_LABEL: Record<string, string> = {
  lzh: "汉",
  pi: "巴利 · 英译",
  sa: "梵",
  bo: "藏 · 英译",
  en: "英",
};

const LANG_COLOR: Record<string, string> = {
  lzh: "gold",
  pi: "cyan",
  sa: "purple",
  bo: "magenta",
  en: "geekblue",
};

const RELATION_LABEL: Record<string, string> = {
  parallel: "平行",
  mention: "提及",
  retell: "复述",
};

const RELATION_COLOR: Record<string, string> = {
  parallel: "green",
  mention: "orange",
  retell: "purple",
};

function ParallelCardBody({ p }: { p: import("../api/client").CanonicalParallel }) {
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
            <span>Pāli 原文</span>
            {full?.pali_chars ? <span style={{ color: "#999", fontWeight: 400 }}>{full.pali_chars.toLocaleString()} 字</span> : null}
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
            展开完整对读
          </Button>
        )}
        <Link
          to={`/texts/${p.related_text_id}/read?juan=1`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#5b8c6b" }}
        >
          <BookOutlined style={{ marginRight: 4 }} />
          在阅读器打开 →
        </Link>
      </div>
    </div>
  );
}

function CanonicalView({ textId }: { textId: number }) {
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
        <div style={{ marginTop: 12, color: "#888" }}>加载 SuttaCentral 对应中…</div>
      </div>
    );
  }
  if (error) {
    return <Alert type="error" showIcon message="加载失败" style={{ margin: 12 }} />;
  }
  if (!data || data.total === 0) {
    return (
      <Empty
        description="本经暂无 SuttaCentral 学术对应"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        style={{ marginTop: 40 }}
      />
    );
  }

  return (
    <>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee", fontSize: 13, color: "#555" }}>
        本经《{data.source_title}》共 <b>{data.total}</b> 条 SuttaCentral 学术对应
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
                    {RELATION_LABEL[p.relation_type] || p.relation_type}
                  </Tag>
                  <Tag color={LANG_COLOR[p.related_lang] || "default"} style={{ margin: 0 }}>
                    {LANG_LABEL[p.related_lang] || p.related_lang}
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
          经级对应来自 SuttaCentral 学术平行表（Akanuma + 现代学者修订）。
          权威可引用，覆盖四阿含 ↔ 尼柯耶全量对应关系。
        </div>
      </div>
    </>
  );
}

function ChunkView({ textId, juanNum }: Props) {
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
        <div style={{ marginTop: 12, color: "#888" }}>加载段落对应中…</div>
      </div>
    );
  }
  if (error) {
    return (
      <Alert
        type="info" showIcon
        message="本卷暂无段落级对照数据"
        description="段级数据由 embedding+LLM 管线生成，覆盖不全且存在噪音。建议以经级对读为主。"
        style={{ margin: 12 }}
      />
    );
  }
  if (!data) return null;

  return (
    <>
      <div style={{ padding: "12px 16px", borderBottom: "1px solid #eee" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 6 }}>
          <span style={{ fontSize: 13, color: "#555" }}>本卷段落覆盖</span>
          <span style={{ fontSize: 13, fontWeight: 500 }}>
            {data.chunks_with_parallels} / {data.total_chunks} 段 ({coveragePct}%)
          </span>
        </div>
        <Progress percent={coveragePct} size="small" showInfo={false}
          strokeColor={coveragePct > 50 ? "#5b8c6b" : coveragePct > 20 ? "#d48806" : "#999"} />
      </div>
      <div style={{ flex: 1, overflow: "auto", padding: "8px 12px" }}>
        {data.entries.length === 0 && (
          <Empty description="本卷没有已对齐的段落" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
                    段 #{entry.chunk_index} · {entry.parallels.length} 条对应
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
                  {entry.parallels.map((p, idx) => (
                    <div key={`${p.text_id}-${p.juan_num}-${p.chunk_index}-${idx}`}
                      style={{ padding: "10px 12px", marginBottom: 10, borderRadius: 4,
                        background: "#fff", border: "1px solid #e8e8e8" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, flexWrap: "wrap" }}>
                        <Tag color={LANG_COLOR[p.lang] || "default"} style={{ margin: 0 }}>
                          {LANG_LABEL[p.lang] || p.lang}
                        </Tag>
                        <span style={{ fontSize: 12, color: "#666" }}>
                          《{p.title || "其他藏经"}》第 {p.juan_num} 卷
                        </span>
                        <span style={{ fontSize: 11, color: "#999", marginLeft: "auto" }}>
                          置信度 {(p.confidence * 100).toFixed(0)}%
                        </span>
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
                            {p.original_lang === "pi" ? "Pāli 原文（本卷前 500 字）" : "原文（本卷前 500 字）"}
                          </div>
                          {p.original_preview}
                          {p.original_preview.length >= 500 && "…"}
                        </div>
                      )}
                      <div style={{ marginTop: 8, fontSize: 12 }}>
                        <Link
                          to={`/texts/${p.text_id}/read?juan=${p.juan_num}`}
                          target="_blank" rel="noopener noreferrer"
                          style={{ color: "#5b8c6b" }}
                        >
                          <BookOutlined style={{ marginRight: 4 }} />
                          阅读全文 →
                        </Link>
                      </div>
                    </div>
                  ))}
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
 * Reader 右侧"多语对读"内联面板（非 modal）。
 *
 * 两个视图：
 *  - 按经对读（默认）：SuttaCentral 权威经级对应，来源 text_relations
 *  - 按段对读（实验）：embedding+LLM 段级对齐，来源 alignment_pairs
 */
export default function ReaderParallelPanel({ textId, juanNum }: Props) {
  return (
    <div className="reader-parallel-panel">
      <Tabs
        defaultActiveKey="canonical"
        size="small"
        style={{ padding: "0 12px" }}
        items={[
          {
            key: "canonical",
            label: "按经对读",
            children: <CanonicalView textId={textId} />,
          },
          {
            key: "chunk",
            label: "按段对读",
            children: <ChunkView textId={textId} juanNum={juanNum} />,
          },
        ]}
      />
    </div>
  );
}
