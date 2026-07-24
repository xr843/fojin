import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
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
import { api } from "../api/client";
import {
  getLocalizedCollections,
  getLocalizedResourceCategories,
  RESOURCE_CATEGORY_KEYS,
  type Collection,
  type CollectionText,
  type CollectionLink,
  type ResourceCategoryLabels,
  type ResourceCategory,
} from "../data/collections";
import { getAlignmentCatalog } from "../api/client";
import { localizeHan } from "../utils/hanScript";
import "../styles/sources.css";
import "../styles/collections.css";

const RESOURCE_ICONS: Record<ResourceCategory, React.ReactNode> = {
  reading: <ReadOutlined />,
  translation: <TranslationOutlined />,
  manuscript: <FileImageOutlined />,
  research: <BankOutlined />,
  temple: <GlobalOutlined />,
};

function TextItem({ text, cbetaMap }: { text: CollectionText; cbetaMap: Record<string, number> }) {
  const { t } = useTranslation();
  const textId = text.cbeta_id ? cbetaMap[text.cbeta_id] : undefined;
  // An indexed text is a real destination, so it gets a real <a href>: keyboard
  // reachable, middle-clickable, and crawlable. A span+onClick was none of those
  // — and left every one of these ~180 texts invisible to search engines while
  // the external resource links below were fully crawlable.
  const target = textId
    ? `/texts/${textId}`
    : text.cbeta_id
      ? `/search?q=${encodeURIComponent(text.cbeta_id)}`
      : undefined;

  return (
    <div className="coll-text-item">
      <div className="coll-text-main">
        {textId ? (
          <Link className="coll-text-title coll-text-title-link" to={target!}>
            {text.title}
          </Link>
        ) : (
          <span className="coll-text-title">{text.title}</span>
        )}
        {text.cbeta_id && (
          <Link to={target!} aria-label={text.cbeta_id}>
            <Tag
              color={textId ? "green" : "volcano"}
              style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px", cursor: "pointer" }}
            >
              {text.cbeta_id}
            </Tag>
          </Link>
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

function ResourceTabs({ resources, resourceCategories }: { resources: Collection["resources"]; resourceCategories: ResourceCategoryLabels }) {
  const availableTabs = RESOURCE_CATEGORY_KEYS.filter(
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
            <span>{resourceCategories[key]}</span>
            <span className="coll-res-tab-count">{resources[key]!.length}</span>
          </button>
        ))}
      </div>
      <div className="coll-res-content">
        {links.map((link) => (
          <a
            key={link.key}
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

function CollectionCard({
  coll,
  cbetaMap,
  resourceCategories,
  expanded,
  onToggle,
}: {
  coll: Collection;
  cbetaMap: Record<string, number>;
  resourceCategories: ResourceCategoryLabels;
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const totalResources = RESOURCE_CATEGORY_KEYS.reduce(
    (sum, k) => sum + (coll.resources[k]?.length || 0),
    0,
  );

  const searchName = coll.searchQuery;
  const panelId = `coll-panel-${coll.id}`;

  return (
    <div className="coll-card">
      {/* W3C APG accordion shape: the heading wraps the button, so the card is a
          real landmark in the heading outline AND the whole header stays one
          keyboard-reachable control announcing its own expanded state. Everything
          inside the button is phrasing content to keep the markup valid. */}
      <h2 className="coll-card-heading">
        <button
          type="button"
          className="coll-card-header"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={onToggle}
        >
          <span className="coll-card-title-row">
            <BookOutlined className="coll-card-icon" aria-hidden="true" />
            <span className="coll-card-name">{coll.name}</span>
            <Tag color="geekblue" style={{ fontSize: 11, marginLeft: 8 }}>{coll.tradition}</Tag>
            <span className="coll-card-count">
              {t("collections.card_stats", { texts: coll.mainTexts.length + coll.commentaries.length, resources: totalResources })}
            </span>
          </span>
          <span className="coll-card-desc">{coll.description}</span>
          {/* The button's own aria-expanded already conveys this to AT. */}
          <span className="coll-card-toggle" aria-hidden="true">
            {expanded ? `${t("search.collapse")} ▲` : `${t("collections.expand")} ▼`}
          </span>
        </button>
      </h2>

      {expanded && (
        <div className="coll-card-body" id={panelId}>
          {/* 主要经典 */}
          <div className="coll-section">
            <h3 className="coll-section-title">
              <ReadOutlined aria-hidden="true" /> {t("collections.main_texts", { n: coll.mainTexts.length })}
            </h3>
            <div className="coll-text-list">
              {coll.mainTexts.map((tx) => (
                <TextItem key={tx.key} text={tx} cbetaMap={cbetaMap} />
              ))}
            </div>
          </div>

          {/* 注疏论释 */}
          {coll.commentaries.length > 0 && (
            <div className="coll-section">
              <h3 className="coll-section-title">
                <BookOutlined aria-hidden="true" /> {t("collections.commentaries", { n: coll.commentaries.length })}
              </h3>
              <div className="coll-text-list">
                {coll.commentaries.map((tx) => (
                  <TextItem key={tx.key} text={tx} cbetaMap={cbetaMap} />
                ))}
              </div>
            </div>
          )}

          {/* 分类资源 */}
          <div className="coll-section">
            <h3 className="coll-section-title">
              <LinkOutlined aria-hidden="true" /> {t("collections.resources", { n: totalResources })}
            </h3>
            <ResourceTabs resources={coll.resources} resourceCategories={resourceCategories} />
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

// Muted CSS tints for the cross-canon table column headers — a quiet language
// cue without the 24 saturated antd Tags the old chip grid stacked up.
const LANG_TINT: Record<string, string> = { bo: "#7c5cbf", sa: "#bd7b3a", pi: "#3f9268" };

/** 跨藏对照专区：哪些经有逐段对照语料（可发现性入口）。
    API 失败/空数据时整块隐身，可与 backend 端点解耦部署。 */
function ParallelCatalogSection({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { t, i18n } = useTranslation();
  const { data } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });
  // The catalog spans ~1500 (text × lang) rows (mitra coverage merged in).
  // This is a discovery card, not the full index: dedupe by text (a work with
  // both 藏 and 梵 parallels is ONE entry, not two) and show only the most-
  // covered handful. Full browse/filter is a dedicated page (follow-up).
  const TOP_N = 12;
  const groups = useMemo(() => {
    if (!data) return [];
    const m = new Map<
      number,
      { text_id: number; title: string; cbeta_id: string; sample_juan: number; total: number; langs: { lang: string; count: number }[] }
    >();
    for (const e of data.entries) {
      let g = m.get(e.text_id);
      if (!g) {
        // title_zh is CBETA's own string, i.e. always traditional. Render it in
        // the reader's script instead of leaking the corpus's — otherwise a
        // 中文简体 visitor gets 大方廣佛華嚴經 sitting under 华严经系列.
        g = {
          text_id: e.text_id,
          title: localizeHan(e.title_zh || e.cbeta_id, i18n.language),
          cbeta_id: e.cbeta_id,
          sample_juan: e.sample_juan,
          total: 0,
          langs: [],
        };
        m.set(e.text_id, g);
      }
      g.langs.push({ lang: e.other_lang, count: e.pair_count });
      g.total += e.pair_count;
    }
    const arr = [...m.values()];
    arr.forEach((g) => g.langs.sort((a, b) => b.count - a.count));
    return arr.sort((a, b) => b.total - a.total);
  }, [data, i18n.language]);

  if (!data || groups.length === 0) return null;

  // Show the most-covered TOP_N as an aligned table. The previous flex-wrap of
  // variable-width chips left a ragged right edge and repeated the 藏文/梵文/段
  // labels on every chip; a table left-aligns the names into one column, right-
  // aligns tabular-number counts under single 藏文/梵文 column headers, and a
  // muted cbeta id disambiguates same-titled translations (e.g. 60卷/80卷 華嚴經).
  const shown = groups.slice(0, TOP_N);
  const LANG_ORDER = ["bo", "sa", "pi"];
  // Canonical bo/sa/pi columns first, then any other language present so a
  // stray lang's pair_count is never silently dropped from the table.
  const present = [...new Set(shown.flatMap((g) => g.langs.map((l) => l.lang)))];
  const langCols = [
    ...LANG_ORDER.filter((lc) => present.includes(lc)),
    ...present.filter((lc) => !LANG_ORDER.includes(lc)),
  ];
  const countFor = (g: (typeof shown)[number], lang: string) =>
    g.langs.find((l) => l.lang === lang)?.count;

  return (
    <div className="coll-card" style={{ marginBottom: 24 }}>
      <div className="coll-section" style={{ padding: "16px 20px" }}>
        {/* Peer of the collection cards in the outline, so h2 like they are. */}
        <h2 className="coll-section-title">
          <TranslationOutlined aria-hidden="true" /> {t("collections.alignment_title", { texts: groups.length, pairs: data.total_pairs.toLocaleString() })}
        </h2>
        <p style={{ fontSize: 13, color: "var(--fj-ink-muted)", margin: "4px 0 12px" }}>
          {t("collections.alignment_desc")}
        </p>
        <div className="cc-table-wrap">
          <table className="cc-table">
            <thead>
              <tr>
                <th className="cc-th cc-name-col">{t("collections.col_text")}</th>
                {langCols.map((lc) => (
                  <th key={lc} className="cc-th cc-num" style={{ color: LANG_TINT[lc] }}>
                    {t(LANG_LABELS[lc]?.labelKey ?? lc)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((g) => (
                // 阅读器而非 /parallel：sample_juan 保证该卷有锚点（对本整本存为
                // juan 1，/parallel 在 juan>1 时对本栏全空）。
                <tr
                  key={g.text_id}
                  className="cc-row"
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/texts/${g.text_id}/read?juan=${g.sample_juan}`)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      navigate(`/texts/${g.text_id}/read?juan=${g.sample_juan}`);
                    }
                  }}
                >
                  <td className="cc-name-col">
                    <span className="cc-title">{g.title}</span>
                    {/* title falls back to cbeta_id when title_zh is empty —
                        don't print the id twice ("T0279 T0279") in that case. */}
                    {g.cbeta_id && g.cbeta_id !== g.title && (
                      <span className="cc-cbeta">{g.cbeta_id}</span>
                    )}
                  </td>
                  {langCols.map((lc) => {
                    const c = countFor(g, lc);
                    return (
                      <td key={lc} className="cc-num">
                        {c != null ? c.toLocaleString() : <span className="cc-empty">—</span>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {groups.length > TOP_N && (
          <p style={{ fontSize: 12, margin: "12px 0 0" }}>
            <a onClick={() => navigate("/cross-canon")} style={{ cursor: "pointer", color: "var(--fj-accent)" }}>
              {t("collections.alignment_more", { n: TOP_N, total: groups.length })} →
            </a>
          </p>
        )}
      </div>
    </div>
  );
}

export default function CollectionsPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { collectionId } = useParams<{ collectionId?: string }>();
  const [search, setSearch] = useState("");
  const [showTop, setShowTop] = useState(false);
  const [cbetaMap, setCbetaMap] = useState<Record<string, number>>({});
  const collections = useMemo(() => getLocalizedCollections(i18n.language), [i18n.language]);
  const resourceCategories = useMemo(() => getLocalizedResourceCategories(i18n.language), [i18n.language]);

  // Which collection is open lives in the URL, not in each card's useState, so a
  // series can be linked, bookmarked and crawled instead of all 13 sharing
  // /collections. An unknown id degrades to the plain index rather than 404ing —
  // a stale bookmark should still land somewhere useful.
  const openCollection = useMemo(
    () => collections.find((c) => c.id === collectionId),
    [collections, collectionId],
  );
  // One open at a time: the URL names a single collection, so the accordion
  // state stays a clean bijection with it.
  const toggleCollection = (id: string) =>
    navigate(openCollection?.id === id ? "/collections" : `/collections/${id}`);

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
    // Go through the shared axios instance (interceptors + non-2xx → throw)
    // instead of a bare fetch whose `.then(r => r.json())` ignored the status
    // and whose `.catch(() => {})` swallowed failures silently. CBETA links are
    // progressive enhancement, so a failure still degrades gracefully — but it
    // must be visible in the console, not dropped.
    api
      .get<Record<string, number>>("/texts/lookup-cbeta", { params: { ids: allIds.join(",") } })
      .then((r) => setCbetaMap(r.data))
      .catch((err) => {
        console.warn("CBETA id 映射加载失败，相关外链将不可用", err);
      });
  }, [collections]);

  const filtered = useMemo(() => {
    if (!search) return collections;
    const q = search.toLowerCase();
    return collections.filter((c) =>
      c.name.toLowerCase().includes(q) ||
      c.tradition.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q) ||
      c.searchQuery.toLowerCase().includes(q) ||
      c.mainTexts.some((t) => t.title.toLowerCase().includes(q) || t.author?.toLowerCase().includes(q)) ||
      c.commentaries.some((t) => t.title.toLowerCase().includes(q) || t.author?.toLowerCase().includes(q))
    );
  }, [collections, search]);

  const totalTexts = collections.reduce((sum, c) => sum + c.mainTexts.length + c.commentaries.length, 0);
  const totalResources = collections.reduce(
    (sum, c) =>
      sum +
      RESOURCE_CATEGORY_KEYS.reduce(
        (s, k) => s + (c.resources[k]?.length || 0),
        0,
      ),
    0,
  );

  return (
    <div className="sources-page">
      {/* Each /collections/:id must describe itself, or the 13 URLs read as
          duplicates of the index to a crawler and the deep links cost more
          than they earn. Canonical points at the open series' own URL. */}
      <Helmet>
        <title>
          {openCollection
            ? t("collections.detail_page_title", { name: openCollection.name })
            : t("collections.page_title")}
        </title>
        <meta
          name="description"
          content={openCollection ? openCollection.description : t("collections.page_desc")}
        />
        <link
          rel="canonical"
          href={
            openCollection
              ? `https://fojin.app/collections/${openCollection.id}`
              : "https://fojin.app/collections"
          }
        />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">{t("collections.title")}</h1>
        <p className="sources-desc">
          {t("collections.subtitle", { series: collections.length, texts: totalTexts, resources: totalResources })}
        </p>
      </div>

      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "var(--fj-ink-muted)" }} />}
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
            <CollectionCard
              key={c.id}
              coll={c}
              cbetaMap={cbetaMap}
              resourceCategories={resourceCategories}
              expanded={openCollection?.id === c.id}
              onToggle={() => toggleCollection(c.id)}
            />
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
