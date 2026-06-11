import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
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

function TextItem({ t, navigate, cbetaMap }: { t: CollectionText; navigate: ReturnType<typeof useNavigate>; cbetaMap: Record<string, number> }) {
  const textId = t.cbeta_id ? cbetaMap[t.cbeta_id] : undefined;
  return (
    <div className="coll-text-item">
      <div className="coll-text-main">
        <span
          className="coll-text-title"
          style={textId ? { cursor: "pointer", color: "var(--fj-accent)" } : undefined}
          onClick={textId ? () => navigate(`/texts/${textId}`) : undefined}
        >
          {t.title}
        </span>
        {t.cbeta_id && (
          <Tag
            color={textId ? "green" : "volcano"}
            style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px", cursor: "pointer" }}
            onClick={() => textId ? navigate(`/texts/${textId}`) : navigate(`/search?q=${encodeURIComponent(t.cbeta_id!)}`)}
          >
            {t.cbeta_id}
          </Tag>
        )}
        {textId && (
          <Tag color="green" style={{ fontSize: 10, margin: 0, lineHeight: "16px", padding: "0 4px" }}>
            已收录
          </Tag>
        )}
      </div>
      <div className="coll-text-meta">
        {t.dynasty && <span>[{t.dynasty}]</span>}
        {t.author && <span>{t.author}</span>}
        {t.note && <span className="coll-text-note">— {t.note}</span>}
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
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState(false);

  const totalResources = (Object.keys(RESOURCE_CATEGORIES) as ResourceCategory[]).reduce(
    (sum, k) => sum + (coll.resources[k]?.length || 0),
    0,
  );

  return (
    <div className="coll-card">
      <div className="coll-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="coll-card-title-row">
          <BookOutlined className="coll-card-icon" />
          <h3 className="coll-card-name">{coll.name}</h3>
          <Tag color="geekblue" style={{ fontSize: 11, marginLeft: 8 }}>{coll.tradition}</Tag>
          <span className="coll-card-count">
            {coll.mainTexts.length + coll.commentaries.length} 部典籍 · {totalResources} 个资源
          </span>
        </div>
        <p className="coll-card-desc">{coll.description}</p>
        <span className="coll-card-toggle">
          {expanded ? "收起 ▲" : "展开查看 ▼"}
        </span>
      </div>

      {expanded && (
        <div className="coll-card-body">
          {/* 主要经典 */}
          <div className="coll-section">
            <div className="coll-section-title">
              <ReadOutlined /> 主要经典（{coll.mainTexts.length}）
            </div>
            <div className="coll-text-list">
              {coll.mainTexts.map((t) => (
                <TextItem key={t.cbeta_id || t.title} t={t} navigate={navigate} cbetaMap={cbetaMap} />
              ))}
            </div>
          </div>

          {/* 注疏论释 */}
          {coll.commentaries.length > 0 && (
            <div className="coll-section">
              <div className="coll-section-title">
                <BookOutlined /> 注疏论释（{coll.commentaries.length}）
              </div>
              <div className="coll-text-list">
                {coll.commentaries.map((t) => (
                  <TextItem key={t.cbeta_id || t.title} t={t} navigate={navigate} cbetaMap={cbetaMap} />
                ))}
              </div>
            </div>
          )}

          {/* 分类资源 */}
          <div className="coll-section">
            <div className="coll-section-title">
              <LinkOutlined /> 相关资源（{totalResources}）
            </div>
            <ResourceTabs resources={coll.resources} />
          </div>

          {/* 站内搜索 */}
          <div className="coll-card-actions">
            <button
              className="source-btn source-btn-search"
              onClick={() => navigate(`/search?q=${encodeURIComponent(coll.name.replace("系列", ""))}`)}
            >
              <SearchOutlined /> 在佛津搜索「{coll.name.replace("系列", "")}」
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const LANG_LABELS: Record<string, { label: string; color: string }> = {
  pi: { label: "巴利", color: "green" },
  bo: { label: "藏文", color: "purple" },
  sa: { label: "梵文", color: "orange" },
};

/** 跨藏对照专区：哪些经有逐段对照语料（可发现性入口）。
    API 失败/空数据时整块隐身，可与 backend 端点解耦部署。 */
function ParallelCatalogSection({ navigate }: { navigate: ReturnType<typeof useNavigate> }) {
  const { data } = useQuery({
    queryKey: ["alignmentCatalog"],
    queryFn: getAlignmentCatalog,
    staleTime: 3600_000,
    retry: 1,
  });
  if (!data || data.entries.length === 0) return null;
  return (
    <div className="coll-card" style={{ marginBottom: 24 }}>
      <div className="coll-section" style={{ padding: "16px 20px" }}>
        <div className="coll-section-title">
          <TranslationOutlined /> 跨藏对照（{new Set(data.entries.map((e) => e.text_id)).size} 部经 · {data.total_pairs.toLocaleString()} 组对齐段落）
        </div>
        <p style={{ fontSize: 12, color: "var(--fj-ink-muted)", margin: "4px 0 12px" }}>
          以下经典已建立逐段跨语对照（AI 对齐 + 置信度过滤），点击进入阅读器，正文旁即可逐段查看对照。
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {data.entries.map((e) => {
            const lang = LANG_LABELS[e.other_lang] ?? { label: e.other_lang, color: "default" };
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
                <span>{e.title_zh}</span>
                <Tag color={lang.color} style={{ margin: 0, fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                  {lang.label}
                </Tag>
                <span style={{ fontSize: 11, color: "var(--fj-ink-muted)" }}>
                  {e.pair_count} 段{e.partner_count > 1 ? ` · ${e.partner_count} 部对本` : ""}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function CollectionsPage() {
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
        <title>经典专题 | 佛津</title>
        <meta name="description" content="按经论系列分类浏览佛教经典，包含主要经典、注疏论释及相关资源。" />
      </Helmet>

      <div className="sources-header">
        <h1 className="sources-title">经典专题</h1>
        <p className="sources-desc">
          {collections.length} 个经论系列 · {totalTexts} 部典籍 · {totalResources} 个外部资源
        </p>
      </div>

      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder="搜索经典名称、传统、作者..."
          allowClear
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: 320 }}
        />
      </div>

      <ParallelCatalogSection navigate={navigate} />

      <div className="sources-stats-bar">
        当前显示 <strong>{filtered.length}</strong> / {collections.length} 个专题
      </div>

      {filtered.length === 0 ? (
        <Empty description="无匹配专题" style={{ marginTop: 60 }} />
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
          aria-label="回到顶部"
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
