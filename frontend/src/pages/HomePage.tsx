import { useState, useRef, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import { AutoComplete } from "antd";
import {
  DatabaseOutlined,
  SearchOutlined,
  UpOutlined,
  DownOutlined,
  ApartmentOutlined,
  RobotOutlined,
  BookOutlined,
  FileTextOutlined,
  GlobalOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { InfoCircleOutlined, CloseOutlined } from "@ant-design/icons";
import SourceSelector from "../components/SourceSelector";
import { getStats, getSources, getFilters, getSearchSuggestions, getHomeShowcase } from "../api/client";
import { getLocalizedCollections } from "../data/collections";
import { getLangName } from "../utils/sourceUrls";
import { getReadingHistory } from "../utils/readingHistory";
import { useAuthStore } from "../stores/authStore";
import "../styles/home.css"; // mobile-responsive v2.1

/** 代码点级截断：CBETA 题名偶含扩展 B 区汉字，String.slice 会撕裂代理对。 */
function truncateTitle(title: string, max = 12): string {
  const chars = Array.from(title);
  return chars.length > max ? `${chars.slice(0, max).join("")}…` : title;
}

export default function HomePage() {
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const { user } = useAuthStore();
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [sourceOpen, setSourceOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [tipDismissed, setTipDismissed] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  // 一次性读取，避免每次 render 触碰 localStorage
  const [recentReading] = useState(() => getReadingHistory().slice(0, 3));

  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: getSources, enabled: sourceOpen });
  const { data: filters } = useQuery({ queryKey: ["filters"], queryFn: getFilters });

  // Dynamic hero-card content. Best-effort: on error/loading, `showcase` is
  // undefined and each card renders its static `feature_*_desc` fallback.
  const { data: showcase } = useQuery({ queryKey: ["homeShowcase"], queryFn: getHomeShowcase, staleTime: 5 * 60_000 });

  // One random value per pool, fixed once at mount (a lazy initializer is the
  // allowed place for the impure Math.random). So every page load / refresh
  // shows a different pick from each cached pool — the cards feel alive without
  // any extra backend round-trip.
  const [rand] = useState(() => ({
    chat: Math.random(), dict: Math.random(), kg: Math.random(),
    geo: Math.random(), col: Math.random(),
  }));

  // Pick one item from each cached pool using the per-mount random values.
  const sc = useMemo(() => {
    const at = (r: number, len: number) => Math.floor(r * len) % Math.max(1, len);
    const q = showcase?.chat?.questions ?? [];
    const terms = showcase?.dictionary?.terms ?? [];
    const triples = showcase?.kg?.triples ?? [];
    const places = showcase?.geo?.places ?? [];
    return {
      sources: showcase?.sources ?? null,
      chat: q.length ? q[at(rand.chat, q.length)] : null,
      dict: terms.length ? terms[at(rand.dict, terms.length)] : null,
      kg: triples.length ? triples[at(rand.kg, triples.length)] : null,
      geo: showcase?.geo && showcase.geo.count > 0
        ? { count: showcase.geo.count, places: places.length
            ? [0, 1, 2].map((i) => places[(at(rand.geo, places.length) + i) % places.length]) : [] }
        : null,
    };
  }, [showcase, rand]);

  // 经典专题 card is driven by the frontend's own collection content (the server
  // doesn't hold it). Pick a random featured slice per load, same as the pools.
  const collectionsDesc = useMemo(() => {
    const cols = getLocalizedCollections(i18n.language).map((c) => c.name).filter(Boolean);
    if (cols.length === 0) return null;
    const start = Math.floor(rand.col * cols.length) % cols.length;
    return [0, 1, 2].map((i) => cols[(start + i) % cols.length]).join(" · ");
  }, [i18n.language, rand.col]);

  // 搜索联想：复用 SearchPage 已有的 /search/suggest 接口与防抖模式
  const [acOptions, setAcOptions] = useState<{ value: string }[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchSuggestions = useCallback((value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value || value.length < 1) {
      setAcOptions([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const suggestions = await getSearchSuggestions(value);
        setAcOptions(suggestions.map((s) => ({ value: s })));
      } catch {
        setAcOptions([]);
      }
    }, 300);
  }, []);

  const handleSearch = (q?: string) => {
    const term = (q ?? query).trim();
    if (term) {
      setAcOptions([]);
      const params = new URLSearchParams({ q: term });
      if (selectedSources.size > 0) {
        params.set("sources", Array.from(selectedSources).join(","));
      }
      navigate(`/search?${params.toString()}`);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  const langAllCount = filters?.languages_all
    ? new Set(filters.languages_all.map(getLangName)).size
    : 0;
  const srcCount = stats?.source_count ?? 0;
  const srcLabel = selectedSources.size > 0
    ? t("home.selected_sources", { n: selectedSources.size })
    : t("home.all_sources");
  const rawTags = t("home.hot_tags", { returnObjects: true });
  const hotTags = Array.isArray(rawTags) ? rawTags : [];

  return (
    <div className="home-page">
      <Helmet>
        <title>{t("app.title")}</title>
        <link rel="alternate" hrefLang="x-default" href="https://fojin.app/" />
        <link rel="alternate" hrefLang="zh" href="https://fojin.app/" />
        <link rel="alternate" hrefLang="en" href="https://fojin.app/?lang=en" />
        <link rel="alternate" hrefLang="zh-Hant" href="https://fojin.app/?lang=zh-Hant" />
      </Helmet>
      <section className="home-hero">
        <div className="home-hero-bg">
          <img src="/landscape-bg.png" alt="" />
        </div>
        <h1 className="home-title">
          <span className="home-title-accent">{t("home.title_accent")}</span>{t("home.title_rest")}
        </h1>
        <div className="home-subtitle">{t("app.tagline")}</div>

        {/* 合并搜索栏 */}
        <div className="search-combo">
          <div className="search-combo-bar">
            <button
              className="search-combo-src"
              onClick={() => setSourceOpen(!sourceOpen)}
              aria-label={t("home.select_source")}
              aria-expanded={sourceOpen}
              aria-haspopup="listbox"
            >
              <DatabaseOutlined />
              <span className="search-combo-src-text">{srcLabel}</span>
              <span className="search-combo-badge">{srcCount}</span>
              {sourceOpen ? <UpOutlined /> : <DownOutlined />}
            </button>
            <div className="search-combo-divider" />
            <AutoComplete
              className="search-combo-ac"
              options={acOptions}
              value={query}
              onChange={setQuery}
              onSearch={fetchSuggestions}
              onSelect={(value: string) => handleSearch(value)}
              popupMatchSelectWidth={280}
            >
              <input
                ref={inputRef}
                className="search-combo-input"
                placeholder={t("home.search_placeholder")}
                onKeyDown={handleKeyDown}
                aria-label={t("home.search_label")}
              />
            </AutoComplete>
            <button className="search-combo-btn" onClick={() => handleSearch()}>
              <SearchOutlined /> <span className="search-combo-btn-text">{t("home.search_btn")}</span>
            </button>
          </div>

          {/* 数据源面板 */}
          {sourceOpen && sources && (
            <SourceSelector
              sources={sources}
              selected={selectedSources}
              onChange={setSelectedSources}
            />
          )}
        </div>

        {/* 热门检索 */}
        <div className="home-hot-tags">
          <span className="home-hot-label">{t("home.hot_label")}</span>
          {hotTags.map((tag) => (
            <button key={tag} className="home-hot-tag" onClick={() => handleSearch(tag)}>
              {tag}
            </button>
          ))}
        </div>

        {/* 续读入口：有本地阅读记录才出现，复用热门检索的样式 */}
        {recentReading.length > 0 && (
          <div className="home-hot-tags">
            <span className="home-hot-label">{t("home.continue_reading")}</span>
            {recentReading.map((e) => (
              <button
                key={e.textId}
                className="home-hot-tag"
                onClick={() => navigate(`/texts/${e.textId}/read?juan=${e.juan}`)}
                title={e.title}
              >
                《{truncateTitle(e.title)}》{t("home.juan_n", { n: e.juan })}
              </button>
            ))}
          </div>
        )}

        <div className="home-stats" role="group" aria-label={t("home.stat_label")}>
          <div className="home-stat-item">
            <div className="home-stat-num">
              {stats ? stats.total_texts.toLocaleString() : "—"}
            </div>
            <div className="home-stat-lbl">{t("home.stat_texts")}</div>
          </div>
          <div className="home-stat-item">
            <div className="home-stat-num">{srcCount || "—"}</div>
            <div className="home-stat-lbl">{t("home.stat_sources")}</div>
          </div>
          <div className="home-stat-item">
            <div className="home-stat-num">{langAllCount || "—"}</div>
            <div className="home-stat-lbl">{t("home.stat_langs")}</div>
          </div>
        </div>

        <div className="home-features">
          <div className="home-feature-card" onClick={() => navigate("/sources")}>
            <DatabaseOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_sources_title")}</div>
            <div className="home-feature-desc">
              {sc.sources
                ? t("home.sc_sources", {
                    sources: sc.sources.sources.toLocaleString(),
                    texts: sc.sources.texts.toLocaleString(),
                  })
                : t("home.feature_sources_desc")}
            </div>
          </div>
          <div
            className="home-feature-card"
            onClick={() =>
              navigate(sc.chat ? `/chat?q=${encodeURIComponent(sc.chat)}` : "/chat")
            }
          >
            <RobotOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_chat_title")}</div>
            <div className="home-feature-desc">
              {sc.chat || t("home.feature_chat_desc")}
            </div>
          </div>
          <div
            className="home-feature-card"
            onClick={() =>
              navigate(sc.dict ? `/dictionary?q=${encodeURIComponent(sc.dict.term)}` : "/dictionary")
            }
          >
            <FileTextOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_dict_title")}</div>
            <div className="home-feature-desc">
              {sc.dict
                ? `${sc.dict.term}${sc.dict.definition ? ` — ${sc.dict.definition}` : ""}`
                : t("home.feature_dict_desc")}
            </div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/kg")}>
            <ApartmentOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_kg_title")}</div>
            <div className="home-feature-desc">
              {sc.kg
                ? `${sc.kg.subject} → ${sc.kg.predicate} → ${sc.kg.object}`
                : t("home.feature_kg_desc")}
            </div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/map")}>
            <GlobalOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_geo_title")}</div>
            <div className="home-feature-desc">
              {sc.geo
                ? t("home.sc_geo", {
                    count: sc.geo.count.toLocaleString(),
                    places: sc.geo.places.join("、"),
                  })
                : t("home.feature_geo_desc")}
            </div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/collections")}>
            <BookOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_collections_title")}</div>
            <div className="home-feature-desc">
              {collectionsDesc || t("home.feature_collections_desc")}
            </div>
          </div>
        </div>

        {!user && !tipDismissed && (
          <div className="home-tip">
            <InfoCircleOutlined style={{ marginRight: 6, flexShrink: 0 }} />
            <span>
              {t("home.guest_tip.before")}
              <a onClick={() => navigate("/login")} style={{ cursor: "pointer", textDecoration: "underline" }}>
                {t("home.guest_tip.login")}
              </a>
              {t("home.guest_tip.after")}
            </span>
            <CloseOutlined
              onClick={() => setTipDismissed(true)}
              style={{ marginLeft: 8, cursor: "pointer", flexShrink: 0, fontSize: 12, opacity: 0.6 }}
            />
          </div>
        )}

        <div className="home-trust">
          {t("home.trust")} ·{" "}
          <span className="home-trust-link" onClick={() => navigate("/sources")}>{t("home.trust_link")}</span>
        </div>

      </section>
    </div>
  );
}
