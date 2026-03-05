import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  DatabaseOutlined,
  SearchOutlined,
  UpOutlined,
  DownOutlined,
} from "@ant-design/icons";
import SourceSelector from "../components/SourceSelector";
import { getStats, getSources, getFilters } from "../api/client";
import { getLangName } from "../utils/sourceUrls";
import "../styles/home.css";

const HOT_TAGS = [
  "金刚经", "心经", "华严经", "楞严经",
  "玄奘", "鸠摩罗什",
  "禅宗", "天台宗",
];

export default function HomePage() {
  const navigate = useNavigate();
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
    ? `已选 ${selectedSources.size} 源`
    : "全部数据源";

  return (
    <div className="home-page">
      <section className="home-hero">
        <div className="home-hero-bg">
          <img src="/landscape-bg.png" alt="" />
        </div>
        <h1 className="home-title">
          <span className="home-title-accent">佛</span>津
        </h1>
        <div className="home-subtitle">全球佛教古籍数字资源聚合平台</div>

        {/* 合并搜索栏 */}
        <div className="search-combo">
          <div className="search-combo-bar">
            <button
              className="search-combo-src"
              onClick={() => setSourceOpen(!sourceOpen)}
              aria-label="选择数据源"
              aria-expanded={sourceOpen}
              aria-haspopup="listbox"
            >
              <DatabaseOutlined />
              <span>{srcLabel}</span>
              <span className="search-combo-badge">{srcCount}</span>
              {sourceOpen ? <UpOutlined /> : <DownOutlined />}
            </button>
            <div className="search-combo-divider" />
            <input
              ref={inputRef}
              className="search-combo-input"
              placeholder="输入经名、译者、宗派..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              aria-label="搜索佛教典籍"
            />
            <button className="search-combo-btn" onClick={() => handleSearch()}>
              <SearchOutlined /> 搜索
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
          <span className="home-hot-label">热门检索</span>
          {HOT_TAGS.map((tag) => (
            <button key={tag} className="home-hot-tag" onClick={() => handleSearch(tag)}>
              {tag}
            </button>
          ))}
        </div>

        <div className="home-stats" role="group" aria-label="平台数据统计">
          <div className="home-stat-item">
            <div className="home-stat-num">
              {stats ? stats.total_texts.toLocaleString() : "—"}
            </div>
            <div className="home-stat-lbl">收录典籍</div>
          </div>
          <div className="home-stat-item">
            <div className="home-stat-num">{srcCount || "—"}</div>
            <div className="home-stat-lbl">数据来源</div>
          </div>
          <div className="home-stat-item">
            <div className="home-stat-num">{langAllCount || "—"}</div>
            <div className="home-stat-lbl">关联语种</div>
          </div>
        </div>
        <div className="home-trust">
          数据来源均为全球学术机构公开资源，定期同步，自动去重 ·{" "}
          <span className="home-trust-link" onClick={() => navigate("/sources")}>了解数据来源 →</span>
        </div>
      </section>
    </div>
  );
}
