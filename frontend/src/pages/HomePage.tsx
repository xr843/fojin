import { useState, useRef, useCallback, useMemo } from "react";
import { Link, useNavigate } from "react-router";
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
  ReadOutlined,
  FileTextOutlined,
} from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import { InfoCircleOutlined, CloseOutlined } from "@ant-design/icons";
import SourceSelector from "../components/SourceSelector";
import XiaojinPet from "../components/XiaojinPet";
import HomeRecentReading from "../components/HomeRecentReading";
import HomeDaily from "../components/HomeDaily";
import { getStats, getSources, getFilters, getSearchSuggestItems, getHomeShowcase } from "../api/client";
import { askQueryFrom, buildHomeSuggestOptions, itemsFromSuggestResponse, type SuggestGroup } from "./homeSuggest";
import { getLangName } from "../utils/sourceUrls";
import { getReadingHistory } from "../utils/readingHistory";
import { fitSourceNames, pickHan } from "./homeShowcase";
import { useAuthStore } from "../stores/authStore";
import "../styles/home.css"; // mobile-responsive v2.1
import { LangAlternates } from "../seo/LangAlternates";

const GUEST_TIP_KEY = "fojin.home.guestTipDismissed";

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
  // 关闭后记住（以前只存在组件 state 里，回到首页又会冒出来）
  const [tipDismissed, setTipDismissed] = useState(() => {
    try {
      return localStorage.getItem(GUEST_TIP_KEY) === "1";
    } catch {
      return false;
    }
  });
  const dismissTip = () => {
    setTipDismissed(true);
    try {
      localStorage.setItem(GUEST_TIP_KEY, "1");
    } catch {
      /* 隐私模式：本次会话内关闭即可 */
    }
  };
  const inputRef = useRef<HTMLInputElement>(null);
  // 一次性读取，避免每次 render 触碰 localStorage；「最近阅读」栏移除条目时回写这里，
  // 让下方「读经」卡的「继续读《…》」同步变化
  const [recentReading, setRecentReading] = useState(() => getReadingHistory());

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
    sources: Math.random(), chat: Math.random(), dict: Math.random(),
    kg: Math.random(), geo: Math.random(),
  }));


  // Pick one item from each cached pool using the per-mount random values.
  const sc = useMemo(() => {
    const at = (r: number, len: number) => Math.floor(r * len) % Math.max(1, len);
    // Deterministic seeded shuffle → take n. Uses only the passed seed (pure),
    // so multi-item cards (source names, geo places) get a fully-random distinct
    // sample per load, not an overlapping sliding window.
    const sample = (arr: string[], n: number, seed: number): string[] => {
      const a = arr.slice();
      let s = Math.floor(seed * 2 ** 31) || 1;
      const rnd = () => { s = (s * 1103515245 + 12345) & 0x7fffffff; return s / 0x7fffffff; };
      for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(rnd() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
      }
      return a.slice(0, n);
    };
    const q = showcase?.chat?.questions ?? [];
    const terms = showcase?.dictionary?.terms ?? [];
    const triples = showcase?.kg?.triples ?? [];
    const places = showcase?.geo?.places ?? [];
    const srcNames = showcase?.sources?.names ?? [];
    return {
      sources: showcase?.sources
        ? { count: showcase.sources.sources, names: sample(srcNames, 3, rand.sources) }
        : null,
      chat: q.length ? q[at(rand.chat, q.length)] : null,
      dict: terms.length ? terms[at(rand.dict, terms.length)] : null,
      kg: triples.length ? triples[at(rand.kg, triples.length)] : null,
      geo: showcase?.geo && showcase.geo.count > 0
        ? { count: showcase.geo.count, places: sample(places, 3, rand.geo) }
        : null,
    };
  }, [showcase, rand]);

  // 搜索联想：复用 SearchPage 已有的 /search/suggest 接口与防抖模式。
  // 后端按 type 排好序，这里分组显示（经名 / 词条 / 热门问题），末尾固定一行「问小津」
  // —— 首页主输入框此前只会搜索，而产品核心是问答（见 homeSuggest.ts）。
  const [acOptions, setAcOptions] = useState<SuggestGroup[]>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const fetchSuggestions = useCallback((value: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!value || value.length < 1) {
      setAcOptions([]);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await getSearchSuggestItems(value);
        setAcOptions(buildHomeSuggestOptions(itemsFromSuggestResponse(data), value, t));
      } catch {
        // 联想挂了也要留「问小津」这一行 —— 它不依赖后端
        setAcOptions(buildHomeSuggestOptions([], value, t));
      }
    }, 300);
  }, [t]);

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
  const hotTags: string[] = Array.isArray(rawTags) ? rawTags : [];
  // 热门检索不再单占一行：输入框为空时点开，下拉里列出这几个词
  const hotOptions = hotTags.length
    ? [{ label: t("home.hot_label"), options: hotTags.map((tag) => ({ value: tag, label: tag })) }]
    : [];

  return (
    <div className="home-page">
      <Helmet>
        <title>{t("app.title")}</title>
      </Helmet>
      <LangAlternates path="/" />
      <section className="home-hero">
        <div className="home-hero-bg">
          <img src="/landscape-bg.webp" alt="" decoding="async" />
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
              <span className="search-combo-badge">{srcCount || "—"}</span>
              {sourceOpen ? <UpOutlined /> : <DownOutlined />}
            </button>
            <div className="search-combo-divider" />
            <AutoComplete
              className="search-combo-ac"
              options={
                query.trim()
                  ? acOptions.map((g) => ({ label: t(g.label), options: g.options }))
                  : hotOptions
              }
              value={query}
              onChange={setQuery}
              onSearch={fetchSuggestions}
              onSelect={(value: string) => {
                if (!query.trim() && hotTags.includes(value)) {
                  // 空输入框点开下拉里的热门检索词（2026-11-25 由首页一行标签收进下拉）
                  if (typeof umami !== "undefined") umami.track("home_hot_tag", { tag: value });
                }
                const ask = askQueryFrom(value);
                if (ask) {
                  // 用户已按下「问小津」—— 等同于在 /chat 里按回车（send=1 深链契约）
                  setQuery(ask);
                  navigate(`/chat?q=${encodeURIComponent(ask)}&send=1`);
                  return;
                }
                handleSearch(value);
              }}
              popupMatchSelectWidth={320}
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

        {/* 今日经句：直接显示当天那一句，点进 /daily */}
        <HomeDaily />

        {/* 最近阅读：有本地阅读记录才出现（对标 CBETA Online 首页「最近操作」） */}
        <HomeRecentReading initial={recentReading} onChange={setRecentReading} />

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
          {/* 首页功能卡与顶部导航一一对应、同顺序：AI 问答 · 读经 · 佛学辞典 · 数据源 · 知识图谱
              （2026-11-03 按 30 天真实使用重排，读经取代经典专题）。核对经文、佛教地理不在导航，
              卡片也不放；/verify、/map、/collections 路由仍可直达。导航增减时这里同步改。 */}
          <Link
            className="home-feature-card"
            data-umami-event="home_card"
            data-umami-event-card="chat"
            to={sc.chat ? `/chat?q=${encodeURIComponent(sc.chat)}` : "/chat"}
          >
            <RobotOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_chat_title")}</div>
            <div className="home-feature-desc">
              {sc.chat || t("home.feature_chat_desc")}
            </div>
          </Link>
          {/* 读经卡：有本地阅读记录就直达上次读到的卷，否则去 /read。 */}
          <Link
            className="home-feature-card"
            data-umami-event="home_card"
            data-umami-event-card={recentReading[0] ? "read_continue" : "read"}
            to={
              recentReading[0]
                ? `/texts/${recentReading[0].textId}/read?juan=${recentReading[0].juan}`
                : "/read"
            }
          >
            <ReadOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_read_title")}</div>
            <div className="home-feature-desc">
              {recentReading[0]
                ? t("home.feature_read_continue", { title: truncateTitle(recentReading[0].title) })
                : t("home.feature_read_desc")}
            </div>
          </Link>
          <Link
            className="home-feature-card"
            data-umami-event="home_card"
            data-umami-event-card="dict"
            to={sc.dict ? `/dictionary?q=${encodeURIComponent(sc.dict.term)}` : "/dictionary"}
          >
            <FileTextOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_dict_title")}</div>
            <div className="home-feature-desc">
              {sc.dict
                ? `${sc.dict.term}${sc.dict.definition ? ` — ${pickHan(sc.dict.definition, sc.dict.definition_hans, i18n.language)}` : ""}`
                : t("home.feature_dict_desc")}
            </div>
          </Link>
          <Link
            className="home-feature-card"
            data-umami-event="home_card"
            data-umami-event-card="sources"
            to="/sources"
          >
            <DatabaseOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_sources_title")}</div>
            <div className="home-feature-desc">
              {sc.sources && sc.sources.names.length > 0
                ? t("home.sc_sources_names", {
                    sources: sc.sources.count.toLocaleString(),
                    names: fitSourceNames(sc.sources.names).join("、"),
                  })
                : t("home.feature_sources_desc")}
            </div>
          </Link>
          <Link
            className="home-feature-card"
            data-umami-event="home_card"
            data-umami-event-card="kg"
            to="/kg"
          >
            <ApartmentOutlined className="home-feature-icon" />
            <div className="home-feature-title">{t("home.feature_kg_title")}</div>
            <div className="home-feature-desc">
              {sc.kg
                ? `${pickHan(sc.kg.subject, sc.kg.subject_hans, i18n.language)} → ${sc.kg.predicate} → ${pickHan(sc.kg.object, sc.kg.object_hans, i18n.language)}`
                : t("home.feature_kg_desc")}
            </div>
          </Link>
        </div>

        {!user && !tipDismissed && (
          <div className="home-tip">
            <InfoCircleOutlined style={{ marginRight: 6, flexShrink: 0 }} />
            <span>
              {t("home.guest_tip.before")}
              <Link to="/login" style={{ textDecoration: "underline" }}>
                {t("home.guest_tip.login")}
              </Link>
              {t("home.guest_tip.after")}
            </span>
            <button type="button" className="home-tip-close" onClick={dismissTip} aria-label={t("home.guest_tip.dismiss")}>
              <CloseOutlined />
            </button>
          </div>
        )}

        <div className="home-trust">
          {t("home.trust")} ·{" "}
          <Link className="home-trust-link" to="/sources">{t("home.trust_link")}</Link>
        </div>

      </section>

      {/* 小津：默认右下角，可拖到任意位置（位置记在 localStorage）。
          position:fixed，不参与 hero 的定高布局；意见反馈入口在它气泡底部。 */}
      <XiaojinPet />
    </div>
  );
}
