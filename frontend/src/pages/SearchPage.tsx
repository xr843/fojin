import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import {
  Pagination, Empty, Checkbox, Input, Tag, Button, Tabs, Result, Select, Typography, Skeleton, AutoComplete,
} from "antd";
import {
  SearchOutlined, BookOutlined, VerticalAlignTopOutlined,
} from "@ant-design/icons";
import { searchTexts, searchContent, searchDictionary, getSources, getSearchSuggestions } from "../api/client";
import { hasDirectSearchUrl } from "../utils/sourceUrls";
import { addSearchHistory, getSearchHistory, type SearchHistoryItem } from "../utils/history";
import { ResultCard, ExternalCard, DictCard, ContentCard } from "../components/search";
import "../styles/search.css";
import "../styles/sources.css";

export default function SearchPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // Derive state from URL — these are the source of truth
  const query = searchParams.get("q") ?? "";
  const tab = searchParams.get("tab") ?? "catalog";
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
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

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

  // Sync acInput when URL query changes (e.g. clicking "did you mean" link)
  useEffect(() => {
    setAcInput(query);
  }, [query]);

  const langFilter = searchParams.get("lang") || "";
  const dictLang = searchParams.get("dict_lang") || "";
  const [dictPage, setDictPage] = useState(1);
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

  const { data: contentData, isLoading: contentLoading } = useQuery({
    queryKey: ["searchContent", query, page, selectedSources, langFilter],
    queryFn: () => searchContent({ q: query, page, size: 20, sources: selectedSources || undefined, lang: langFilter || undefined }),
    enabled: query.length > 0 && tab === "content",
  });

  const { data: dictData, isLoading: dictLoading } = useQuery({
    queryKey: ["searchDict", query, dictPage, dictLang],
    queryFn: () => searchDictionary({ q: query, page: dictPage, size: 20, lang: dictLang || undefined }),
    enabled: query.length > 0 && tab === "dictionary",
  });

  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: getSources });

  const handleSearch = (value: string) => {
    setPage(1);
    updateUrl({ q: value });
    saveSearchHistory(value);
  };

  const clearSource = (code: string) => {
    const codes = selectedSources.split(",").filter((c) => c && c !== code);
    setPage(1);
    updateUrl({ sources: codes.join(",") });
  };

  /* 地区 & 馆藏统计 */
  /* 地区：中国→中国大陆，台湾→中国台湾，其余保持原国家名 */
  const normalizeRegion = (r: string): string => {
    if (r === "中国") return "中国大陆";
    if (r === "台湾") return "中国台湾";
    return r || "其他";
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
      result = result.filter((s) => regionFilter.has(normalizeRegion(s.region || "其他")));
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
      const r = normalizeRegion(s.region || "其他");
      counts[r] = (counts[r] || 0) + 1;
    });
    return counts;
  }, [extSearchable]);

  /* 馆藏列表：只列出外部可搜索源，带数量 */
  const institutionList = useMemo(() => {
    const counts: Record<string, number> = {};
    extSearchable.forEach((s) => {
      counts[s.name_zh] = (counts[s.name_zh] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
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

  const loading = tab === "catalog" ? isLoading : tab === "content" ? contentLoading : dictLoading;
  const localTotal = tab === "catalog" ? (data?.total || 0) : tab === "content" ? (contentData?.total || 0) : (dictData?.total || 0);
  const extTotal = query.length > 0 ? filteredExtSources.length : 0;

  const sortedRegions = useMemo(() => {
    return Object.keys(regionCounts).sort((a, b) => {
      // 中国大陆第一，中国台湾第二，其他最后，其余按数量降序
      if (a === "中国大陆") return -1;
      if (b === "中国大陆") return 1;
      if (a === "中国台湾") return -1;
      if (b === "中国台湾") return 1;
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      return (regionCounts[b] || 0) - (regionCounts[a] || 0);
    });
  }, [regionCounts]);

  const pageTitle = query ? `${query} — 搜索 | 佛津` : "搜索 | 佛津";
  const pageDesc = query ? `在佛津搜索"${query}"的结果` : "搜索全球佛教古籍数字资源";

  return (
    <div className="s-page">
      <Helmet>
        <title>{pageTitle}</title>
        <meta name="description" content={pageDesc} />
        <link rel="canonical" href={`https://fojin.app/search${query ? `?q=${encodeURIComponent(query)}` : ""}`} />
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
            placeholder="输入书名、作者或版本"
            enterButton={<><SearchOutlined /> 搜索</>}
            size="large"
            onSearch={handleSearch}
          />
        </AutoComplete>
      </div>

      {/* 已选数据源标签 */}
      {selectedSources && (
        <div style={{ display: "flex", gap: 6, justifyContent: "center", marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: "#9a8e7a", lineHeight: "24px" }}>筛选数据源：</span>
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
            { key: "catalog", label: "经典检索" },
            { key: "content", label: "全文检索" },
            { key: "dictionary", label: <><BookOutlined /> 辞典检索</> },
          ]}
          size="small"
        />
        <div className="s-mode-hint">
          {tab === "catalog"
            ? "按经名、译者、编号检索经典目录"
            : tab === "content"
            ? "在经文正文中检索关键词"
            : "在 393,624 条多语种辞典词条中检索词头与释义"}
        </div>
      </div>

      {query.length === 0 ? (
        <div style={{ marginTop: 80, textAlign: "center" }}>
          <Empty description="请输入搜索关键词" />
          {searchHistory.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>最近搜索：</Typography.Text>
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
          {/* 左侧筛选（辞典 Tab 不显示） */}
          {tab !== "dictionary" && <aside className="s-sidebar">
            <div className="s-filter-group">
              <div className="s-filter-title">🌐 国家/地区</div>
              <div className="s-filter-scroll">
                {sortedRegions.map((r) => (
                  <label key={r} className="s-filter-item">
                    <Checkbox
                      checked={regionFilter.has(r)}
                      onChange={() => toggleRegion(r)}
                    />
                    <span className="s-filter-name">{r}</span>
                    <span className="s-filter-count">{regionCounts[r]}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="s-filter-group">
              <div className="s-filter-title">🏛 馆藏</div>
              <div className="s-filter-scroll">
                {institutionList.map(({ name, count }) => (
                  <label key={name} className="s-filter-item">
                    <Checkbox
                      checked={institutionFilter.has(name)}
                      onChange={() => toggleInstitution(name)}
                    />
                    <span className="s-filter-name">{name}</span>
                    <span className="s-filter-count">{count}</span>
                  </label>
                ))}
              </div>
            </div>
          </aside>}

          {/* 主内容 */}
          <main className="s-main">
            <div className="s-result-header">
              <span className="s-result-count">
                {tab === "dictionary"
                  ? <>辞典找到 <strong>{localTotal.toLocaleString()}</strong> 条词条</>
                  : tab === "content"
                  ? <>在 <strong>{localTotal.toLocaleString()}</strong> 部经典中找到匹配（共 {(contentData?.total_juans || 0).toLocaleString()} 卷）</>
                  : <>找到 <strong>{localTotal.toLocaleString()}</strong> 条结果</>
                }
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {(tab === "catalog" || tab === "content") && (
                  <Select
                    size="small"
                    value={langFilter || "all"}
                    onChange={(v) => { setPage(1); updateUrl({ lang: v === "all" ? "" : v }); }}
                    style={{ width: 110 }}
                    options={[
                      { value: "all", label: "全部语种" },
                      { value: "lzh", label: "汉文" },
                      { value: "pi", label: "巴利文" },
                      { value: "en", label: "英文" },
                      { value: "bo", label: "藏文" },
                      { value: "sa", label: "梵文" },
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
                      { value: "relevance", label: "相关度" },
                      { value: "title", label: "按经名" },
                      { value: "dynasty", label: "按朝代" },
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
                    { value: "all", label: "全部语种" },
                    { value: "zh", label: "中文" },
                    { value: "pi", label: "巴利文" },
                    { value: "sa", label: "梵文" },
                  ]}
                />
              )}
              </div>
            </div>

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
                ？
              </div>
            )}

            {loading && Array.from({ length: 5 }).map((_, i) => (
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
                title="搜索失败"
                subTitle="搜索服务暂时不可用，请稍后重试。"
                extra={<Button type="primary" onClick={() => refetch()}>重试</Button>}
              />
            )}

            {/* 本地结果 */}
            {!loading && tab === "catalog" && data && data.results.map((hit, i) => (
              <ResultCard key={hit.id} hit={hit} rank={i + 1 + (page - 1) * 20} />
            ))}

            {!loading && tab === "content" && contentData && contentData.results.map((hit, i) => (
              <ContentCard key={`${hit.text_id}_${i}`} hit={hit} rank={i + 1 + (page - 1) * 20} />
            ))}

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

            {/* 本地分页 */}
            {!loading && tab !== "dictionary" && localTotal > 20 && (
              <div style={{ textAlign: "center", margin: "16px 0" }}>
                <Pagination current={page} total={localTotal} pageSize={20}
                  showSizeChanger={false} onChange={(p) => setPage(p)} />
              </div>
            )}

            {/* 外部数据源结果 */}
            {!loading && tab !== "dictionary" && query.length > 0 && filteredExtSources.length > 0 && (
              <>
                <div className="s-ext-divider">
                  以下 {extTotal} 个外部数据源可继续搜索「{query}」
                </div>
                {filteredExtSources.map((s, i) => (
                  <ExternalCard key={s.code} source={s} query={query}
                    rank={i + 1} />
                ))}
              </>
            )}
          </main>
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
