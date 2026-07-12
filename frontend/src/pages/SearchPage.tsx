import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { SUPPORTED_UI_LANGS } from "../i18n";
import { useQuery } from "@tanstack/react-query";
import {
  Pagination, Empty, Checkbox, Input, Tag, Button, Tabs, Result, Select, Typography, Skeleton, AutoComplete, Alert,
} from "antd";
import {
  SearchOutlined, VerticalAlignTopOutlined, CloseOutlined,
} from "@ant-design/icons";
import { searchTexts, searchContent, searchDictionary, searchCrossLanguage, searchSemantic, searchUnified, searchParallelSentences, getSources, getSearchSuggestions, searchDictionaryGrouped, getCbetaRedirect } from "../api/client";
import type { DictGroupedSearchResponse } from "../api/client";
import { hasDirectSearchUrl } from "../utils/sourceUrls";
import { addSearchHistory, getSearchHistory, type SearchHistoryItem } from "../utils/history";
import { localizedSourceName } from "../utils/sourceName";
import { ResultCard, ExternalSourcesSection, DictCard, ContentCard, CrossLangCard, SemanticCard, UnifiedResults } from "../components/search";
import ParallelSentenceCard from "../components/search/ParallelSentenceCard";
import "../styles/search.css";
import "../styles/sources.css";

// CBETA-style identifier: prefix letter (T/X/J/B/P/C) + 1-4 digits + optional lowercase suffix.
// 例：T0278、X0235a、J1510b。命中即直跳 /texts/{id}，跳过结果列表。
const CBETA_ID_RE = /^[TXJBPC]\d{1,4}[a-z]?$/i;
const REGION_CHINA = "中国"; // i18n-exempt
const REGION_TAIWAN = "台湾"; // i18n-exempt
const REGION_MAINLAND_CHINA = "中国大陆"; // i18n-exempt
const REGION_TAIWAN_CHINA = "中国台湾"; // i18n-exempt
const REGION_OTHER = "其他"; // i18n-exempt

export default function SearchPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Derive state from URL — these are the source of truth.
  // Default tab is "all" (unified overview); legacy aliases still resolve to
  // their canonical tab so old links keep working.
  const query = searchParams.get("q") ?? "";
  const rawTab = searchParams.get("tab") ?? "all";
  const tab = rawTab === "crosslang" ? "catalog" : rawTab === "semantic" ? "content" : rawTab === "dictionary" ? "catalog" : rawTab;
  const selectedSources = searchParams.get("sources") ?? "";

  const [page, setPage] = useState(1);

  // Search history
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>(getSearchHistory);

  const saveSearchHistory = (q: string) => {
    addSearchHistory(q, tab);
    setSearchHistory(getSearchHistory());
  };

  // Autocomplete suggestions
  const [acOptions, setAcOptions] = useState<{ value: string }[]>([]);
  const [acInput, setAcInput] = useState(query);
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

  // Sync acInput when the URL query changes (e.g. clicking a "did you mean"
  // link). Adjusted during render — no effect pass.
  const [prevQuery, setPrevQuery] = useState(query);
  if (prevQuery !== query) {
    setPrevQuery(query);
    setAcInput(query);
  }

  // CBETA ID 直跳：用户输入 T0278 / X0235a 等时，命中即跳 /texts/{id}，
  // 跳过结果列表。404/非 CBETA 静默 fallback 到常规搜索。
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed || !CBETA_ID_RE.test(trimmed)) return;
    let cancelled = false;
    (async () => {
      const result = await getCbetaRedirect(trimmed.toUpperCase());
      if (cancelled || !result) return;
      // Umami: track CBETA shortcut hits — power-user signal.
      if (typeof umami !== "undefined") {
        umami.track("cbeta-shortcut", { cbeta_id: result.cbeta_id });
      }
      navigate(result.redirect_to, { replace: true });
    })();
    return () => { cancelled = true; };
  }, [query, navigate]);

  // #709: the text-language filter param was renamed `lang` → `tl`. The old
  // name collided with i18next's querystring detector — selecting the
  // "English" filter and refreshing flipped (and persisted via localStorage)
  // the entire UI language. Legacy ?lang= links still resolve as filters for
  // unambiguous codes; UI locale codes (zh/zh-Hant/en) belong to i18n.
  const legacyLangParam = searchParams.get("lang") || "";
  const legacyLangIsFilter =
    legacyLangParam !== "" && !(SUPPORTED_UI_LANGS as readonly string[]).includes(legacyLangParam);
  const langFilter = searchParams.get("tl") || (legacyLangIsFilter ? legacyLangParam : "");
  const dictLang = searchParams.get("dict_lang") || "";
  const [dictPage, setDictPage] = useState(1);
  // Cross-lingual (MITRA) foreign-language filter: all | sa | bo. Local state
  // (like the parallel query's non-paginated shape) — not URL-driven.
  const [parallelLang, setParallelLang] = useState<string>("all");
  const [dynasty] = useState<string>();
  const [category] = useState<string>();
  const [showTop, setShowTop] = useState(false);
  const [regionFilter, setRegionFilter] = useState<Set<string>>(new Set());
  const [institutionFilter, setInstitutionFilter] = useState<Set<string>>(new Set());


  const sortBy = searchParams.get("sort") || "relevance";

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  /** Update URL params (replaces current history entry) */
  const updateUrl = (overrides: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(overrides)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    setSearchParams(next, { replace: true });
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["search", query, page, dynasty, category, selectedSources, sortBy, langFilter],
    queryFn: () => searchTexts({ q: query, page, size: 20, dynasty, category, sources: selectedSources || undefined, sort: sortBy !== "relevance" ? sortBy : undefined, lang: langFilter || undefined }),
    enabled: query.length > 0 && tab === "catalog",
  });

  const { data: contentData, isLoading: contentLoading, isError: contentError } = useQuery({
    queryKey: ["searchContent", query, page, selectedSources, langFilter],
    queryFn: () => searchContent({ q: query, page, size: 20, sources: selectedSources || undefined, lang: langFilter || undefined }),
    enabled: query.length > 0 && tab === "content",
  });

  const { data: dictData, isLoading: dictLoading, isError: dictError } = useQuery({
    queryKey: ["searchDict", query, dictPage, dictLang],
    queryFn: () => searchDictionary({ q: query, page: dictPage, size: 20, lang: dictLang || undefined }),
    enabled: query.length > 0 && tab === "dictionary",
  });

  const { data: crossLangData, isLoading: crossLangLoading } = useQuery({
    queryKey: ["searchCrossLang", query, page, dynasty, category, selectedSources],
    queryFn: () => searchCrossLanguage({ q: query, page, size: 20, dynasty, category, sources: selectedSources || undefined }),
    enabled: query.length > 0 && tab === "catalog",
  });

  const { data: semanticData, isLoading: semanticLoading } = useQuery({
    queryKey: ["searchSemantic", query, selectedSources, langFilter, dynasty, category],
    queryFn: () => searchSemantic({ q: query, size: 20, dynasty, category, lang: langFilter || undefined, sources: selectedSources || undefined }),
    enabled: query.length > 0 && tab === "content",
  });

  // Unified search powers the default "全部 / All" tab — single round trip
  // to /search/unified returns sectioned results (dictionary, catalog,
  // content, semantic) so the user no longer has to pick a tab.
  const { data: unifiedData, isLoading: unifiedLoading, isError: unifiedError, refetch: refetchUnified } = useQuery({
    queryKey: ["searchUnified", query, selectedSources, langFilter],
    queryFn: () => searchUnified({ q: query, sources: selectedSources || undefined, lang: langFilter || undefined }),
    enabled: query.length > 0 && tab === "all",
  });

  // Cross-lingual parallel sentences (MITRA). Non-paginated; empty result is
  // the natural dark state (coverage is sparse and grows with imports).
  const { data: parallelData, isLoading: parallelLoading, isError: parallelError, refetch: refetchParallel } = useQuery({
    queryKey: ["searchParallel", query, parallelLang],
    queryFn: () => searchParallelSentences(query, { lang: parallelLang === "all" ? undefined : parallelLang, limit: 30 }),
    enabled: query.length > 0 && tab === "parallel",
  });

  // Dictionary knowledge card (parallel, non-blocking)
  const [dictCardDismissed, setDictCardDismissed] = useState(false);
  // Reset dismissal when the query changes — adjusted during render.
  const [prevDictQuery, setPrevDictQuery] = useState(query);
  if (prevDictQuery !== query) {
    setPrevDictQuery(query);
    setDictCardDismissed(false);
  }
  const { data: dictKnowledge } = useQuery<DictGroupedSearchResponse>({
    queryKey: ["dictKnowledge", query],
    queryFn: () => searchDictionaryGrouped({ q: query }),
    enabled: query.length > 0 && tab !== "dictionary",
    staleTime: 5 * 60 * 1000,
  });

  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: getSources });

  const handleSearch = (value: string) => {
    setPage(1);
    updateUrl({ q: value });
    saveSearchHistory(value);
    // Umami: track search keyword
    if (typeof umami !== "undefined" && value) {
      umami.track("search", { keyword: value });
    }
  };

  const clearSource = (code: string) => {
    const codes = selectedSources.split(",").filter((c) => c && c !== code);
    setPage(1);
    updateUrl({ sources: codes.join(",") });
  };

  /* 地区 & 馆藏统计 */
  /* 地区：中国→中国大陆，台湾→中国台湾，其余保持原国家名 */
  const normalizeRegion = (r: string): string => {
    if (r === REGION_CHINA) return REGION_MAINLAND_CHINA;
    if (r === REGION_TAIWAN) return REGION_TAIWAN_CHINA;
    return r || REGION_OTHER;
  };

  /* 只保留有真实搜索入口的外部数据源（左侧筛选只针对外部源） */
  const extSearchable = useMemo(() =>
    (sources || []).filter((s) =>
      s.access_type === "external" && hasDirectSearchUrl(s.code)
    ),
    [sources]
  );

  /* 按 selectedSources / 地区 / 馆藏筛选后的外部源 */
  const filteredExtSources = useMemo(() => {
    let result = extSearchable;
    if (selectedSources) {
      const codes = new Set(selectedSources.split(",").filter(Boolean));
      result = result.filter((s) => codes.has(s.code));
    }
    if (regionFilter.size > 0) {
      result = result.filter((s) => regionFilter.has(normalizeRegion(s.region || REGION_OTHER)));
    }
    if (institutionFilter.size > 0) {
      result = result.filter((s) => institutionFilter.has(s.name_zh));
    }
    return result;
  }, [extSearchable, selectedSources, regionFilter, institutionFilter]);

  /* 地区统计：只统计外部可搜索源 */
  const regionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    extSearchable.forEach((s) => {
      const r = normalizeRegion(s.region || REGION_OTHER);
      counts[r] = (counts[r] || 0) + 1;
    });
    return counts;
  }, [extSearchable]);

  /* 馆藏列表：只列出外部可搜索源，带数量。filter key 固定用 name_zh，
     显示名按 locale 走 name_en (#707)。 */
  const institutionList = useMemo(() => {
    const counts = new Map<string, { count: number; nameEn: string | null }>();
    extSearchable.forEach((s) => {
      const entry = counts.get(s.name_zh) ?? { count: 0, nameEn: s.name_en ?? null };
      entry.count += 1;
      counts.set(s.name_zh, entry);
    });
    return Array.from(counts, ([name, { count, nameEn }]) => ({ name, nameEn, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh"));
  }, [extSearchable]);

  const toggleRegion = (r: string) => {
    const next = new Set(regionFilter);
    if (next.has(r)) next.delete(r); else next.add(r);
    setRegionFilter(next);
  };

  const toggleInstitution = (name: string) => {
    const next = new Set(institutionFilter);
    if (next.has(name)) next.delete(name); else next.add(name);
    setInstitutionFilter(next);
  };

  const loading = tab === "catalog" ? (isLoading || crossLangLoading) : tab === "content" ? (contentLoading || semanticLoading) : dictLoading;
  // Primary query loading state (excluding secondary cross-language / semantic queries),
  // used to bail out of skeleton rendering once the main result count is known to be 0.
  const primaryLoading = tab === "catalog" ? isLoading : tab === "content" ? contentLoading : dictLoading;
  const localTotal = tab === "catalog" ? (data?.total || 0) : tab === "content" ? (contentData?.total || 0) : (dictData?.total || 0);
  const hasSecondaryResults = tab === "catalog"
    ? (crossLangData?.results.length || 0) > 0
    : tab === "content"
    ? (semanticData?.results.length || 0) > 0
    : false;
  // Don't fire the empty state when the primary query failed — the existing
  // error UI handles that case. Without this guard, an API error renders
  // both the error block AND the "no on-site matches" copy.
  const primaryError = tab === "catalog" ? isError : tab === "content" ? contentError : dictError;
  const showEmptyState = !primaryLoading && !primaryError && localTotal === 0 && !hasSecondaryResults;

  const sortedRegions = useMemo(() => {
    return Object.keys(regionCounts).sort((a, b) => {
      // 中国大陆第一，中国台湾第二，其他最后，其余按数量降序
      if (a === REGION_MAINLAND_CHINA) return -1;
      if (b === REGION_MAINLAND_CHINA) return 1;
      if (a === REGION_TAIWAN_CHINA) return -1;
      if (b === REGION_TAIWAN_CHINA) return 1;
      if (a === REGION_OTHER) return 1;
      if (b === REGION_OTHER) return -1;
      return (regionCounts[b] || 0) - (regionCounts[a] || 0);
    });
  }, [regionCounts]);

  const pageTitle = query ? t("search.page_title", { query }) : t("search.page_title_default");
  const pageDesc = query ? t("search.page_desc", { query }) : t("search.page_desc_default");

  return (
    <div className="s-page">
      <Helmet>
        <title>{pageTitle}</title>
        <meta name="description" content={pageDesc} />
        <link rel="canonical" href={`https://fojin.app/search${(() => { const p = new URLSearchParams(); if (query) p.set("q", query); if (page > 1) p.set("page", String(page)); return p.toString() ? `?${p.toString()}` : ""; })()}`} />
        <link rel="alternate" hrefLang="x-default" href={`https://fojin.app/search${query ? `?q=${encodeURIComponent(query)}` : ""}`} />
        <link rel="alternate" hrefLang="zh" href={`https://fojin.app/search${query ? `?q=${encodeURIComponent(query)}` : ""}`} />
        <link rel="alternate" hrefLang="en" href={`https://fojin.app/search?${new URLSearchParams({ ...(query ? { q: query } : {}), lang: "en" }).toString()}`} />
        <link rel="alternate" hrefLang="zh-Hant" href={`https://fojin.app/search?${new URLSearchParams({ ...(query ? { q: query } : {}), lang: "zh-Hant" }).toString()}`} />
        {query && page > 1 && (
          <link rel="prev" href={`https://fojin.app/search?${new URLSearchParams({ q: query, ...(page > 2 ? { page: String(page - 1) } : {}) }).toString()}`} />
        )}
        {query && localTotal > page * 20 && (
          <link rel="next" href={`https://fojin.app/search?${new URLSearchParams({ q: query, page: String(page + 1) }).toString()}`} />
        )}
      </Helmet>
      {/* 搜索栏 */}
      <div className="s-search-bar">
        <AutoComplete
          options={acOptions}
          onSearch={fetchSuggestions}
          onSelect={(value: string) => { setAcOptions([]); handleSearch(value); }}
          value={acInput}
          onChange={setAcInput}
          style={{ maxWidth: 640, width: "100%" }}
        >
          <Input.Search
            placeholder={t("search.input_placeholder")}
            enterButton={<><SearchOutlined /> {t("search.button")}</>}
            size="large"
            onSearch={handleSearch}
          />
        </AutoComplete>
      </div>

      {/* 已选数据源标签 */}
      {selectedSources && (
        <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: "#9a8e7a", lineHeight: "24px" }}>{t("search.filter_sources_label")}</span>
          {selectedSources.split(",").filter(Boolean).map((code) => (
            <Tag key={code} closable onClose={() => clearSource(code)} color="volcano" style={{ fontSize: 11 }}>
              {code}
            </Tag>
          ))}
        </div>
      )}

      {/* 搜索模式 */}
      <div className="s-mode-bar">
        <Tabs
          activeKey={tab}
          onChange={(k) => { setPage(1); updateUrl({ tab: k }); }}
          items={[
            { key: "all", label: t("search.tab_all") },
            { key: "catalog", label: t("search.tab_catalog") },
            { key: "content", label: t("search.tab_content") },
            { key: "parallel", label: t("search.tab_parallel") },
          ]}
          size="small"
        />
        <div className="s-mode-hint">
          {tab === "all"
            ? t("search.subtitle_all")
            : tab === "catalog"
            ? t("search.subtitle_catalog")
            : tab === "parallel"
            ? t("search.subtitle_parallel")
            : t("search.subtitle_content")}
        </div>
      </div>

      {query.length === 0 ? (
        <div style={{ marginTop: 80, textAlign: "center" }}>
          <Empty description={t("search.enter_keyword")} />
          {searchHistory.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>{t("search.recent_searches")}</Typography.Text>
              <div style={{ marginTop: 8, display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                {searchHistory.map((h) => (
                  <Tag key={h.query} style={{ cursor: "pointer" }} onClick={() => handleSearch(h.query)}>{h.query}</Tag>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="s-layout">
          {/* 左侧筛选（辞典 / 跨语对照 Tab 不显示） */}
          {tab !== "dictionary" && tab !== "parallel" && <aside className="s-sidebar">
            <div className="s-filter-group">
              <div className="s-filter-title">🌐 {t("search.filter_region")}</div>
              <div className="s-filter-scroll">
                {sortedRegions.map((r) => (
                  <label key={r} className="s-filter-item">
                    <Checkbox
                      checked={regionFilter.has(r)}
                      onChange={() => toggleRegion(r)}
                    />
                    <span className="s-filter-name">{t(`region.${r}`, r)}</span>
                    <span className="s-filter-count">{regionCounts[r]}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="s-filter-group">
              <div className="s-filter-title">🏛 {t("search.filter_institution")}</div>
              <div className="s-filter-scroll">
                {institutionList.map(({ name, nameEn, count }) => (
                  <label key={name} className="s-filter-item">
                    <Checkbox
                      checked={institutionFilter.has(name)}
                      onChange={() => toggleInstitution(name)}
                    />
                    <span className="s-filter-name">{localizedSourceName({ name_zh: name, name_en: nameEn })}</span>
                    <span className="s-filter-count">{count}</span>
                  </label>
                ))}
              </div>
            </div>
          </aside>}

          {/* 主内容 */}
          <main className="s-main">
            {tab === "all" ? (
              <>
                {unifiedLoading && (
                  <div style={{ marginTop: 16 }}>
                    {Array.from({ length: 4 }).map((_, i) => (
                      <div className="s-card" key={`skel-all-${i}`}>
                        <div className="s-card-body">
                          <Skeleton.Input active size="small" style={{ width: 200, height: 18, marginBottom: 8 }} />
                          <Skeleton active paragraph={{ rows: 2 }} title={false} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {!unifiedLoading && unifiedError && (
                  <Result
                    status="error"
                    title={t("search.failed_title")}
                    subTitle={t("search.failed_subtitle")}
                    extra={<Button type="primary" onClick={() => refetchUnified()}>{t("search.retry")}</Button>}
                  />
                )}
                {!unifiedLoading && !unifiedError && unifiedData && (
                  <UnifiedResults data={unifiedData} />
                )}
                {/* 外部数据源结果 */}
                {!unifiedLoading && !unifiedError && query.length > 0 && filteredExtSources.length > 0 && (
                  <ExternalSourcesSection sources={filteredExtSources} query={query} />
                )}
              </>
            ) : tab === "parallel" ? (
              <>
                <div className="s-result-header">
                  <span className="s-result-count">
                    {t("search.found_parallel", { n: (parallelData?.total || 0).toLocaleString() })}
                  </span>
                  <Select
                    size="small"
                    value={parallelLang}
                    onChange={(v) => { setPage(1); setParallelLang(v); }}
                    style={{ width: 110 }}
                    options={[
                      { value: "all", label: t("search.lang_all") },
                      { value: "sa", label: t("lang.sa") },
                      { value: "bo", label: t("lang.bo") },
                    ]}
                  />
                </div>

                {parallelLoading && Array.from({ length: 5 }).map((_, i) => (
                  <div className="s-card" key={`skel-par-${i}`}>
                    <div className="s-card-body">
                      <Skeleton active paragraph={{ rows: 2 }} title={false} />
                    </div>
                  </div>
                ))}

                {!parallelLoading && parallelError && (
                  <Result
                    status="error"
                    title={t("search.failed_title")}
                    subTitle={t("search.failed_subtitle")}
                    extra={<Button type="primary" onClick={() => refetchParallel()}>{t("search.retry")}</Button>}
                  />
                )}

                {!parallelLoading && !parallelError && parallelData?.error && (
                  <Alert type="warning" message={parallelData.error} showIcon closable style={{ marginBottom: 12 }} />
                )}

                {!parallelLoading && !parallelError && parallelData && parallelData.results.map((hit, i) => (
                  <ParallelSentenceCard key={`${hit.text_id}_${hit.taisho_id}_${i}`} hit={hit} rank={i + 1} />
                ))}

                {!parallelLoading && !parallelError && parallelData && parallelData.results.length === 0 && (
                  <div className="s-empty-state" style={{ margin: "24px 0 12px", padding: "16px 20px", background: "var(--fj-sand-light, #faf7f2)", border: "1px solid #e8e0d4", borderRadius: 6, color: "#6b5d4a", fontSize: 14 }}>
                    {t("search.parallel_empty")}
                  </div>
                )}
              </>
            ) : (
            <>
            <div className="s-result-header">
              <span className="s-result-count">
                {tab === "dictionary"
                  ? t("search.found_dict", { n: localTotal.toLocaleString() })
                  : tab === "content"
                  ? t("search.found_catalog", { n: localTotal.toLocaleString(), juans: (contentData?.total_juans || 0).toLocaleString() })
                  : tab === "semantic"
                  ? t("search.found_semantic", { n: localTotal.toLocaleString() })
                  : tab === "crosslang"
                  ? t("search.found_crosslang", { n: localTotal.toLocaleString() })
                  : t("search.found_results", { n: localTotal.toLocaleString() })
                }
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {(tab === "catalog" || tab === "content") && (
                  <Select
                    size="small"
                    value={langFilter || "all"}
                    onChange={(v) => { setPage(1); updateUrl({ tl: v === "all" ? "" : v, ...(legacyLangIsFilter ? { lang: "" } : {}) }); }}
                    style={{ width: 110 }}
                    options={[
                      { value: "all", label: t("search.lang_all") },
                      { value: "lzh", label: t("lang.lzh") },
                      { value: "pi", label: t("lang.pi") },
                      { value: "en", label: t("lang.en") },
                      { value: "bo", label: t("lang.bo") },
                      { value: "sa", label: t("lang.sa") },
                    ]}
                  />
                )}
                {tab === "catalog" && (
                  <Select
                    size="small"
                    value={sortBy}
                    onChange={(v) => { setPage(1); updateUrl({ sort: v }); }}
                    style={{ width: 120 }}
                    options={[
                      { value: "relevance", label: t("search.sort_relevance") },
                      { value: "title", label: t("search.sort_title") },
                      { value: "dynasty", label: t("search.sort_dynasty") },
                    ]}
                  />
                )}
                {tab === "dictionary" && (
                <Select
                  size="small"
                  value={dictLang || "all"}
                  onChange={(v) => { setDictPage(1); updateUrl({ dict_lang: v === "all" ? "" : v }); }}
                  style={{ width: 120 }}
                  options={[
                    { value: "all", label: t("search.lang_all") },
                    { value: "zh", label: t("lang.zh") },
                    { value: "pi", label: t("lang.pi") },
                    { value: "sa", label: t("lang.sa") },
                  ]}
                />
              )}
              </div>
            </div>

            {/* Dictionary knowledge card */}
            {!dictCardDismissed && dictKnowledge && dictKnowledge.groups.length > 0 && tab !== "dictionary" && (
              <div className="s-dict-knowledge">
                <div className="s-dict-knowledge-header">
                  <span className="s-dict-knowledge-title">{"\uD83D\uDCD6"} {t("search.dict_gloss_title", { query })}</span>
                  <button
                    className="s-dict-knowledge-close"
                    onClick={() => setDictCardDismissed(true)}
                    aria-label={t("search.dict_gloss_close")}
                  >
                    <CloseOutlined />
                  </button>
                </div>
                <div className="s-dict-knowledge-body">
                  {dictKnowledge.groups.slice(0, 2).map((group) => (
                    <div key={group.source_code} className="s-dict-knowledge-entry">
                      <span className="s-dict-knowledge-source">{group.source_name}</span>
                      <span className="s-dict-knowledge-def">
                        {group.entries[0]?.definition
                          ? group.entries[0].definition.length > 150
                            ? group.entries[0].definition.slice(0, 150) + "..."
                            : group.entries[0].definition
                          : ""}
                      </span>
                    </div>
                  ))}
                </div>
                <div className="s-dict-knowledge-footer">
                  <Link to={`/dictionary?q=${encodeURIComponent(query)}`}>
                    {t("search.view_all_dict")}
                  </Link>
                </div>
              </div>
            )}

            {/* "Did you mean..." suggestion */}
            {!loading && tab === "catalog" && data && data.suggestion && data.total < 3 && (
              <div className="s-did-you-mean">
                {t("search.no_results_for", { query })}
                {" — "}
                {t("search.did_you_mean")}{" "}
                <a
                  className="s-did-you-mean-link"
                  onClick={(e) => { e.preventDefault(); handleSearch(data.suggestion!); }}
                  href="#"
                >
                  &ldquo;{data.suggestion}&rdquo;
                </a>
                {t("search.dym_qmark")}
              </div>
            )}

            {loading && !showEmptyState && Array.from({ length: 5 }).map((_, i) => (
              <div className="s-card" key={`skel-${i}`}>
                <div className="s-card-rank">
                  <Skeleton.Button active size="small" style={{ width: 28, height: 14 }} />
                </div>
                <div className="s-card-body">
                  <Skeleton.Input active size="small" style={{ width: 220, height: 22, marginBottom: 8 }} />
                  <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
                    <Skeleton.Button active size="small" style={{ width: 60, height: 22, borderRadius: 4 }} />
                    <Skeleton.Button active size="small" style={{ width: 60, height: 22, borderRadius: 4 }} />
                  </div>
                  {tab === "content" ? (
                    <div style={{ padding: "8px 12px", background: "var(--fj-sand-light, #faf7f2)", borderLeft: "3px solid #d4a574", borderRadius: 4, marginTop: 8 }}>
                      <Skeleton active paragraph={{ rows: 2 }} title={false} />
                    </div>
                  ) : tab === "dictionary" ? (
                    <Skeleton active paragraph={{ rows: 2 }} title={false} />
                  ) : (
                    <>
                      <Skeleton.Input active size="small" style={{ width: 180, height: 16, marginBottom: 4 }} />
                      <Skeleton.Input active size="small" style={{ width: 120, height: 16, marginBottom: 12 }} />
                      <div style={{ display: "flex", gap: 8 }}>
                        <Skeleton.Button active size="small" style={{ width: 90, height: 28 }} />
                        <Skeleton.Button active size="small" style={{ width: 80, height: 28 }} />
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}

            {!loading && isError && tab === "catalog" && (
              <Result
                status="error"
                title={t("search.failed_title")}
                subTitle={t("search.failed_subtitle")}
                extra={<Button type="primary" onClick={() => refetch()}>{t("search.retry")}</Button>}
              />
            )}

            {/* 本地结果 */}
            {!loading && tab === "catalog" && data && data.results.map((hit, i) => (
              <ResultCard key={hit.id} hit={hit} rank={i + 1 + (page - 1) * 20} />
            ))}

            {!loading && tab === "content" && contentData && contentData.results.map((hit, i) => (
              <ContentCard key={`${hit.text_id}_${i}`} hit={hit} rank={i + 1 + (page - 1) * 20} />
            ))}

            {/* 语义搜索错误提示 */}
            {!loading && tab === "content" && semanticData?.error && (
              <Alert
                type="warning"
                message={semanticData.error}
                showIcon
                closable
                style={{ marginBottom: 12 }}
              />
            )}

            {/* 语义搜索结果 */}
            {!loading && tab === "content" && semanticData && semanticData.results.length > 0 && (<><div style={{margin: "16px 0 8px", fontSize: 13, color: "#9a8e7a"}}>⚡ {t("search.semantic_match")}</div>{semanticData.results.map((hit, i) => (
              <SemanticCard key={`${hit.text_id}_${hit.juan_num}`} hit={hit} rank={i + 1} />
            ))}</>)}

            {/* 跨语言结果 */}
            {!loading && tab === "catalog" && crossLangData && crossLangData.results.length > 0 && (<><div style={{margin: "16px 0 8px", fontSize: 13, color: "#9a8e7a", borderTop: "1px solid #e8e0d4", paddingTop: 12}}>🌐 {t("search.crosslang_match")}</div>{crossLangData.results.map((hit, i) => (
              <CrossLangCard key={hit.id} hit={hit} rank={i + 1 + (page - 1) * 20} />
            ))}</>)}

            {/* 辞典结果 */}
            {!loading && tab === "dictionary" && dictData && dictData.results.map((hit, i) => (
              <DictCard key={hit.id} hit={hit} rank={i + 1 + (dictPage - 1) * 20} />
            ))}

            {/* 辞典分页 */}
            {!loading && tab === "dictionary" && (dictData?.total || 0) > 20 && (
              <div style={{ textAlign: "center", margin: "16px 0" }}>
                <Pagination current={dictPage} total={dictData?.total || 0} pageSize={20}
                  showSizeChanger={false} onChange={(p) => setDictPage(p)} />
              </div>
            )}

            {/* 本地分页（语义搜索不分页） */}
            {!loading && tab !== "dictionary" && tab !== "semantic" && localTotal > 20 && (
              <div style={{ textAlign: "center", margin: "16px 0" }}>
                <Pagination current={page} total={localTotal} pageSize={20}
                  showSizeChanger={false} onChange={(p) => setPage(p)} />
              </div>
            )}

            {/* 站内 0 结果显式空状态：避免与外部源卡片混淆 */}
            {showEmptyState && tab !== "dictionary" && (
              <div className="s-empty-state" style={{ margin: "24px 0 12px", padding: "16px 20px", background: "var(--fj-sand-light, #faf7f2)", border: "1px solid #e8e0d4", borderRadius: 6, color: "#6b5d4a", fontSize: 14 }}>
                {t("search.empty_state_external")}
              </div>
            )}

            {/* 外部数据源结果 */}
            {(!loading || showEmptyState) && tab !== "dictionary" && query.length > 0 && filteredExtSources.length > 0 && (
              <ExternalSourcesSection sources={filteredExtSources} query={query} />
            )}
            </>
            )}
          </main>
        </div>
      )}
      {showTop && (
        <button
          className="sources-back-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label={t("search.back_to_top")}
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
