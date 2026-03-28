import { useState, useMemo, useEffect } from "react";
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

export default function CollectionsPage() {
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
