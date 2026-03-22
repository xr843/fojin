import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import {
  DatabaseOutlined,
  SearchOutlined,
  UpOutlined,
  DownOutlined,
  ApartmentOutlined,
  RobotOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import SourceSelector from "../components/SourceSelector";
import { getStats, getSources, getFilters } from "../api/client";
import { getLangName } from "../utils/sourceUrls";
import "../styles/home.css";

export default function HomePage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [selectedSources, setSelectedSources] = useState<Set<string>>(new Set());
  const [sourceOpen, setSourceOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: getStats });
  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: getSources });
  const { data: filters } = useQuery({ queryKey: ["filters"], queryFn: getFilters });

  const handleSearch = (q?: string) => {
    const term = (q ?? query).trim();
    if (term) {
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
  const srcCount = sources?.length || 0;
  const srcLabel = selectedSources.size > 0
    ? t("home.selected_sources", { count: selectedSources.size })
    : t("home.all_sources");
  const rawTags = t("home.hot_tags", { returnObjects: true });
  const hotTags = Array.isArray(rawTags) ? rawTags : [];

  return (
    <div className="home-page">
      <Helmet>
        <title>{t("app.title")}</title>
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
            <input
              ref={inputRef}
              className="search-combo-input"
              placeholder={t("home.search_placeholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              aria-label={t("home.search_label")}
            />
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
            <div className="home-feature-desc">{t("home.feature_sources_desc")}</div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/kg")}>
            <ApartmentOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_kg_title")}</div>
            <div className="home-feature-desc">{t("home.feature_kg_desc")}</div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/chat")}>
            <RobotOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_chat_title")}</div>
            <div className="home-feature-desc">{t("home.feature_chat_desc")}</div>
          </div>
          <div className="home-feature-card" onClick={() => navigate("/collections")}>
            <BookOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_collections_title")}</div>
            <div className="home-feature-desc">{t("home.feature_collections_desc")}</div>
          </div>
        </div>

        <div className="home-trust">
          {t("home.trust")} ·{" "}
          <span className="home-trust-link" onClick={() => navigate("/sources")}>{t("home.trust_link")}</span>
        </div>

      </section>
    </div>
  );
}
