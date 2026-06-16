import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Input, Tag, Empty } from "antd";
import {
  SearchOutlined,
  BookOutlined,
  ReadOutlined,
  LinkOutlined,
  GlobalOutlined,
  BankOutlined,
  TranslationOutlined,
  FileImageOutlined,
  VerticalAlignTopOutlined,
} from "@ant-design/icons";
import collections, {
  RESOURCE_CATEGORIES,
  type Collection,
  type CollectionText,
  type CollectionLink,
  type ResourceCategory,
} from "../data/collections";
import { getAlignmentCatalog } from "../api/client";
import "../styles/sources.css";
import "../styles/collections.css";

const RESOURCE_ICONS: Record<ResourceCategory, React.ReactNode> = {
  reading: <ReadOutlined />,
  translation: <TranslationOutlined />,
  manuscript: <FileImageOutlined />,
  research: <BankOutlined />,
  temple: <GlobalOutlined />,
};

function TextItem({ text, navigate, cbetaMap }: { text: CollectionText; navigate: ReturnType<typeof useNavigate>; cbetaMap: Record<string, number> }) {
  const { t } = useTranslation();
  const textId = text.cbeta_id ? cbetaMap[text.cbeta_id] : undefined;
  return (
    <div className="coll-text-item">
      <div className="coll-text-main">
        <span
          className="coll-text-title"
          style={textId ? { cursor: "pointer", color: "var(--fj-accent)" } : undefined}
          onClick={textId ? () => navigate(`/texts/${textId}`) : undefined}
        >
          {text.title}
        </span>
        {text.cbeta_id && (
          <Tag
            color={textId ? "green" : "volcano"}
            style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px", cursor: "pointer" }}
            onClick={() => textId ? navigate(`/texts/${textId}`) : navigate(`/search?q=${encodeURIComponent(text.cbeta_id!)}`)}
          >
            {text.cbeta_id}
          </Tag>
        )}
        {textId && (
          <Tag color="green" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
            {t("collections.indexed")}
          </Tag>
        )}
      </div>
      <div className="coll-text-meta">
        {text.dynasty && <span>[{text.dynasty}]</span>}
        {text.author && <span>{text.author}</span>}
        {text.note && <span className="coll-text-note">— {text.note}</span>}
      </div>
    </div>
  );
}

function ResourceTabs({ resources }: { resources: Collection["resources"] }) {
  const availableTabs = (Object.keys(RESOURCE_CATEGORIES) as ResourceCategory[]).filter(
    (k) => resources[k] && resources[k]!.length > 0,
  );
  const [activeTab, setActiveTab] = useState<ResourceCategory>(availableTabs[0]);

  if (availableTabs.length === 0) return null;

  const links: CollectionLink[] = resources[activeTab] || [];

  return (
    <div className="coll-res-section">
      <div className="coll-res-tabs">
        {availableTabs.map((key) => (
          <button
            key={key}
            className={`coll-res-tab${activeTab === key ? " active" : ""}`}
            onClick={() => setActiveTab(key)}
          >
            {RESOURCE_ICONS[key]}
            <span>{RESOURCE_CATEGORIES[key]}</span>
            <span className="coll-res-tab-count">{resources[key]!.length}</span>
          </button>
        ))}
      </div>
      <div className="coll-res-content">
        {links.map((link) => (
          <a
            key={link.url}
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="coll-link-item"
          >
            <span className="coll-link-name">{link.name}</span>
            {link.desc && <span className="coll-link-desc">{link.desc}</span>}
          </a>
        ))}
      </div>
    </div>
  );
}

function CollectionCard({ coll, cbetaMap }: { coll: Collection; cbetaMap: Record<string, number> }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const totalResources = (Object.keys(RESOURCE_CATEGORIES) as ResourceCategory[]).reduce(
    (sum, k) => sum + (coll.resources[k]?.length || 0),
    0,
  );

  // Strip the data-layer suffix to build the on-site search query term.
  const searchName = coll.name.replace("系列", ""); // i18n-exempt

  return (
    <div className="coll-card">
      <div className="coll-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="coll-card-title-row">
          <BookOutlined className="coll-card-icon" />
          <h3 className="coll-card-name">{coll.name}</h3>
          <Tag color="geekblue" style={{ fontSize: 11, marginLeft: 8 }}>{coll.tradition}</Tag>
          <span className="coll-card-count">
            {t("collections.card_stats", { texts: coll.mainTexts.length + coll.commentaries.length, resources: totalResources })}
          </span>
        </div>
        <p className="coll-card-desc">{coll.description}</p>
        <span className="coll-card-toggle">
          {expanded ? `${t("search.collapse")} ▲` : `${t("collections.expand")} ▼`}
        </span>
      </div>

      {expanded && (
        <div className="coll-card-body">
          {/* 主要经典 */}
          <div className="coll-section">
            <div className="coll-section-title">
              <ReadOutlined /> {t("collections.main_texts", { n: coll.mainTexts.length })}
            </div>
            <div className="coll-text-list">
              {coll.mainTexts.map((tx) => (
                <TextItem key={tx.cbeta_id || tx.title} text={tx} navigate={navigate} cbetaMap={cbetaMap} />
              ))}
            </div>
          </div>

          {/* 注疏论释 */}
          {coll.commentaries.length > 0 && (
            <div className="coll-section">
              <div className="coll-section-title">
                <BookOutlined /> {t("collections.commentaries", { n: coll.commentaries.length })}
              </div>
              <div className="coll-text-list">
                {coll.commentaries.map((tx) => (
                  <TextItem key={tx.cbeta_id || tx.title} text={tx} navigate={navigate} cbetaMap={cbetaMap} />
                ))}
              </div>
            </div>
          )}

          {/* 分类资源 */}
          <div className="coll-section">
            <div className="coll-section-title">
              <LinkOutlined /> {t("collections.resources", { n: totalResources })}
            </div>
            <ResourceTabs resources={coll.resources} />
          </div>

          {/* 站内搜索 */}
          <div className="coll-card-actions">
            <button
              className="source-btn source-btn-search"
              onClick={() => navigate(`/search?q=${encodeURIComponent(searchName)}`)}
            >
              <SearchOutlined /> {t("collections.search_in_fojin", { name: searchName })}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Language chips reuse the shared lang.* locale family (keys match other_lang codes).
const LANG_LABELS: Record<string, { labelKey: string; color: string }> = {
  pi: { labelKey: "lang.pi", color: "green" },
  bo: { labelKey: "lang.bo", color: "purple" },
  sa: { labelKey: "lang.sa", color: "orange" },
};

/** 跨藏对照专区：哪些经有逐段对照语料（可发现性入口）。
    API 失败/空数据时整块隐身，可与 backend 端点解耦部署。 */
function ParallelCatalogSection({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { t } = useTranslation();
  const { data } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });
  // Catalog now spans ~1500 (text × lang) rows (mitra coverage merged in);
  // entries arrive sorted by pair_count desc, so cap to the most-covered to
  // keep this discovery card bounded. Full browse is a follow-up (dedicated page).
  const TOP_N = 48;
  if (!data || data.entries.length === 0) return null;
  return (
    <div className="coll-card" style={{ marginBottom: 24 }}>
      <div className="coll-section" style={{ padding: "16px 20px" }}>
        <div className="coll-section-title">
          <TranslationOutlined /> {t("collections.alignment_title", { texts: new Set(data.entries.map((e) => e.text_id)).size, pairs: data.total_pairs.toLocaleString() })}
        </div>
        <p style={{ fontSize: 12, color: "var(--fj-ink-muted)", margin: "4px 0 12px" }}>
          {t("collections.alignment_desc")}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {data.entries.slice(0, TOP_N).map((e) => {
            const lang = LANG_LABELS[e.other_lang];
            return (
              <button
                key={`${e.text_id}-${e.other_lang}`}
                className="source-btn"
                style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
                onClick={() =>
                  // 阅读器而非 /parallel：sample_juan 保证该卷有锚点；reader 的
                  // 按段对照面板不依赖对本侧 text_contents 的卷结构（对本整本
                  // 存为 juan 1，/parallel 在 juan>1 时对本栏全空）。
                  navigate(`/texts/${e.text_id}/read?juan=${e.sample_juan}`)
                }
              >
                <span>{e.title_zh || e.cbeta_id}</span>
                <Tag color={lang?.color ?? "default"} style={{ margin: 0, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                  {lang ? t(lang.labelKey) : e.other_lang}
                </Tag>
                <span style={{ fontSize: 11, color: "var(--fj-ink-muted)" }}>
                  {t("collections.pair_count", { n: e.pair_count })}{e.partner_count > 1 ? ` · ${t("collections.partner_count", { n: e.partner_count })}` : ""}
                </span>
              </button>
            );
          })}
        </div>
        {data.entries.length > TOP_N && (
          <p style={{ fontSize: 11, color: "var(--fj-ink-muted)", margin: "12px 0 0" }}>
            {t("collections.alignment_more", { n: TOP_N, total: data.entries.length })}
          </p>
        )}
      </div>
    </div>
  );
}

export default function CollectionsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [showTop, setShowTop] = useState(false);
  const [cbetaMap, setCbetaMap] = useState<Record<string, number>>({});

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const allIds = collections.flatMap((c) =>
      [...c.mainTexts, ...c.commentaries].map((t) => t.cbeta_id).filter(Boolean),
    );
    if (allIds.length === 0) return;
    fetch(`/api/texts/lookup-cbeta?ids=${encodeURIComponent(allIds.join(","))}`)
      .then((r) => r.json())
      .then((data) => setCbetaMap(data))
      .catch(() => {});
  }, []);

  const filtered = useMemo(() => {
    if (!search) return collections;
    const q = search.toLowerCase();
    return collections.filter((c) =>
      c.name.toLowerCase().includes(q) ||
      c.tradition.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q) ||
      c.mainTexts.some((t) => t.title.toLowerCase().includes(q) || t.author?.toLowerCase().includes(q)) ||
      c.commentaries.some((t) => t.title.toLowerCase().includes(q) || t.author?.toLowerCase().includes(q))
    );
  }, [search]);

  const totalTexts = collections.reduce((sum, c) => sum + c.mainTexts.length + c.commentaries.length, 0);
  const totalResources = collections.reduce(
    (sum, c) =>
      sum +
      (Object.keys(RESOURCE_CATEGORIES) as ResourceCategory[]).reduce(
        (s, k) => s + (c.resources[k]?.length || 0),
        0,
      ),
    0,
  );

  return (
    <div className="sources-page">
      <Helmet>
        <title>{t("collections.page_title")}</title>
        <meta name="description" content={t("collections.page_desc")} />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">{t("collections.title")}</h1>
        <p className="sources-desc">
          {t("collections.subtitle", { series: collections.length, texts: totalTexts, resources: totalResources })}
        </p>
      </div>

      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder={t("collections.search_placeholder")}
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 320 }}
        />
      </div>

      <ParallelCatalogSection navigate={navigate} />

      <div className="sources-stats-bar">
        {t("sources.stats_showing")} <strong>{filtered.length}</strong> / {collections.length} {t("collections.stats_unit")}
      </div>

      {filtered.length === 0 ? (
        <Empty description={t("collections.no_match")} style={{ marginTop: 60 }} />
      ) : (
        <div className="coll-list">
          {filtered.map((c) => (
            <CollectionCard key={c.id} coll={c} cbetaMap={cbetaMap} />
          ))}
        </div>
      )}

      {showTop && (
        <button
          className="sources-back-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label={t("sources.back_to_top_aria")}
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
