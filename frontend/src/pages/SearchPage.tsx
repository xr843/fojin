import { useState, useMemo } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { useQuery } from "@tanstack/react-query";
import {
  Pagination, Spin, Empty, Checkbox, Input, Tag, Button, Tabs, Result, Select, Typography,
} from "antd";
import {
  SearchOutlined, EyeOutlined, LinkOutlined, ReadOutlined, CloudOutlined,
} from "@ant-design/icons";
import BookmarkButton from "../components/BookmarkButton";
import { Alert } from "antd";
import { searchTexts, searchContent, getSources, type SearchHit, type DataSource } from "../api/client";
import { federatedSearch, type DianjinSearchHit } from "../api/dianjin";
import { buildSearchUrl, hasDirectSearchUrl, getSourceLabel, buildSourceReadUrl } from "../utils/sourceUrls";
import { sanitizeHighlight } from "../utils/sanitize";
import "../styles/search.css";

/* ---- 本地结果卡片 ---- */
function ResultCard({ hit, rank }: { hit: SearchHit; rank: number }) {
  const navigate = useNavigate();
  const titleHtml = hit.highlight?.title_zh?.[0] ?? hit.title_zh;
  const sourceName = hit.source_code ? getSourceLabel(hit.source_code) : null;
  // Only build read URL for cbeta source where cbeta_id is the correct identifier.
  // For other sources, cbeta_id may not be a valid identifier for that source;
  // users should go to detail page to get the correct source-specific URL.
  const isCbetaSource = !hit.source_code || hit.source_code === "cbeta" || hit.source_code === "cbeta-org" || hit.source_code === "cbeta-api";
  const readUrl = isCbetaSource ? buildSourceReadUrl("cbeta", hit.cbeta_id) : null;

  return (
    <div className="s-card">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title" dangerouslySetInnerHTML={{ __html: sanitizeHighlight(titleHtml) }} />
        <div className="s-card-tags">
          {sourceName && (
            <Tag color="volcano" style={{ fontSize: 11 }}>{sourceName}</Tag>
          )}
          <Tag style={{ fontSize: 11 }}>{hit.has_content ? "本地全文" : "目录数据"}</Tag>
          {hit.category && <Tag style={{ fontSize: 11 }}>{hit.category}</Tag>}
        </div>
        <div className="s-card-meta">
          {hit.translator && (
            <span>主要责任者: {hit.dynasty ? `[${hit.dynasty}] ` : ""}{hit.translator}</span>
          )}
        </div>
        <div className="s-card-meta">
          <span>编号: {hit.cbeta_id}</span>
        </div>
        <div className="s-card-actions">
          {hit.has_content && (
            <Button type="primary" size="small" icon={<ReadOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500" }}
              onClick={() => navigate(`/read/${hit.id}`)}>
              在线阅读
            </Button>
          )}
          {!hit.has_content && readUrl && (
            <Button type="primary" size="small" icon={<LinkOutlined />}
              style={{ background: "#8b2500", borderColor: "#8b2500" }}
              href={readUrl} target="_blank" rel="noopener noreferrer">
              前往 {sourceName || "原站"} 阅读
            </Button>
          )}
          <Button size="small" icon={<EyeOutlined />}
            onClick={() => navigate(`/texts/${hit.id}`)}>
            查看详情
          </Button>
          <BookmarkButton textId={hit.id} size="small" />
        </div>
      </div>
    </div>
  );
}

/* ---- 外部数据源结果卡片 ---- */
function ExternalCard({ source, query, rank }: { source: DataSource; query: string; rank: number }) {
  const url = buildSearchUrl(source.code, query) || "#";
  return (
    <div className="s-card s-card-ext">
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">{query}</div>
        <div className="s-card-tags">
          <Tag color="blue" style={{ fontSize: 11 }}>{source.name_zh}</Tag>
          <Tag style={{ fontSize: 11 }}>外链跳转</Tag>
          {source.region && <Tag style={{ fontSize: 11 }}>{source.region}</Tag>}
        </div>
        <div className="s-card-meta">
          <span>馆藏: {source.name_zh}</span>
        </div>
        <div className="s-card-actions">
          <a className="s-card-btn-primary" href={url} target="_blank" rel="noopener noreferrer"
            aria-label={`前往 ${source.name_zh} 搜索 ${query}`}>
            <LinkOutlined /> 前往原站搜索
          </a>
          {source.base_url && (
            <a className="s-card-btn" href={source.base_url} target="_blank" rel="noopener noreferrer"
              aria-label={`访问 ${source.name_zh} 主页`}>
              <EyeOutlined /> 访问主页
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---- 典津结果卡片 ---- */
function DianjinCard({ hit, rank }: { hit: DianjinSearchHit; rank: number }) {
  return (
    <div className="s-card" style={{ borderLeft: "3px solid #1677ff" }}>
      <div className="s-card-rank">排序<br />#{rank}</div>
      <div className="s-card-body">
        <div className="s-card-title">{hit.title || "无题"}</div>
        <div className="s-card-tags">
          <Tag color="blue" style={{ fontSize: 11 }}>典津</Tag>
          {hit.datasource_name && <Tag color="volcano" style={{ fontSize: 11 }}>{hit.datasource_name}</Tag>}
          {hit.collection && <Tag style={{ fontSize: 11 }}>{hit.collection}</Tag>}
          {hit.datasource_tags?.map((t) => (
            <Tag key={t} style={{ fontSize: 10 }}>{t}</Tag>
          ))}
        </div>
        <div className="s-card-meta">
          {hit.main_responsibility && <span>责任者: {hit.main_responsibility}</span>}
          {hit.edition && <span style={{ marginLeft: 12 }}>版本: {hit.edition}</span>}
        </div>
        <div className="s-card-actions">
          {hit.detail_url && (
            <a className="s-card-btn-primary" href={hit.detail_url} target="_blank" rel="noopener noreferrer">
              <LinkOutlined /> 前往典津查看
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // Derive state from URL — these are the source of truth
  const query = searchParams.get("q") ?? "";
  const tab = searchParams.get("tab") ?? "catalog";
  const selectedSources = searchParams.get("sources") ?? "";

  const [page, setPage] = useState(1);

  // Search history
  const HISTORY_KEY = "fojin-search-history";
  const getSearchHistory = (): string[] => {
    try {
      return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
    } catch { return []; }
  };
  const [searchHistory, setSearchHistory] = useState<string[]>(getSearchHistory);

  const saveSearchHistory = (q: string) => {
    if (!q.trim()) return;
    const history = [q, ...getSearchHistory().filter((h) => h !== q)].slice(0, 10);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    setSearchHistory(history);
  };

  const [dynasty] = useState<string>();
  const [category] = useState<string>();
  const [regionFilter, setRegionFilter] = useState<Set<string>>(new Set());
  const [institutionFilter, setInstitutionFilter] = useState<Set<string>>(new Set());
  const sortBy = searchParams.get("sort") || "relevance";

  /** Update URL params (replaces current history entry) */
  const updateUrl = (overrides: Record<string, string>) => {
    const next = new URLSearchParams(searchParams);
    for (const [k, v] of Object.entries(overrides)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    setSearchParams(next, { replace: true });
  };

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["search", query, page, dynasty, category, selectedSources, sortBy],
    queryFn: () => searchTexts({ q: query, page, size: 20, dynasty, category, sources: selectedSources || undefined, sort: sortBy !== "relevance" ? sortBy : undefined }),
    enabled: query.length > 0 && tab === "catalog",
  });

  const { data: contentData, isLoading: contentLoading } = useQuery({
    queryKey: ["searchContent", query, page, selectedSources],
    queryFn: () => searchContent({ q: query, page, size: 20, sources: selectedSources || undefined }),
    enabled: query.length > 0 && tab === "content",
  });

  const { data: fedData, isLoading: fedLoading } = useQuery({
    queryKey: ["federatedSearch", query, page, dynasty, category, selectedSources],
    queryFn: () => federatedSearch({ q: query, page, size: 20, dynasty, category, sources: selectedSources || undefined }),
    enabled: query.length > 0 && tab === "federated",
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

  const loading = tab === "catalog" ? isLoading : tab === "content" ? contentLoading : fedLoading;
  const localTotal = tab === "catalog" ? (data?.total || 0) : tab === "content" ? (contentData?.total || 0) : (fedData?.local_total || 0);
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
        <Input.Search
          key={query}
          defaultValue={query}
          placeholder="输入书名、作者或版本"
          enterButton={<><SearchOutlined /> 搜索</>}
          size="large"
          onSearch={handleSearch}
          style={{ maxWidth: 640 }}
        />
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
            { key: "federated", label: <><CloudOutlined /> 联合检索</> },
            { key: "content", label: "全文检索" },
          ]}
          size="small"
        />
        <div className="s-mode-hint">
          {tab === "catalog"
            ? "按经名、译者、编号检索经典目录"
            : tab === "content"
            ? "在经文正文中检索关键词"
            : "同时搜索本地数据库和典津跨平台古籍资源"}
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
                  <Tag key={h} style={{ cursor: "pointer" }} onClick={() => handleSearch(h)}>{h}</Tag>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="s-layout">
          {/* 左侧筛选 */}
          <aside className="s-sidebar">
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
          </aside>

          {/* 主内容 */}
          <main className="s-main">
            <div className="s-result-header">
              <span className="s-result-count">
                {tab === "federated"
                  ? <>联合找到 <strong>{(fedData?.combined_total || 0).toLocaleString()}</strong> 条结果（本地 {localTotal.toLocaleString()} + 典津 {(fedData?.dianjin_total || 0).toLocaleString()}）</>
                  : <>本地找到 <strong>{localTotal.toLocaleString()}</strong> 条结果</>
                }
              </span>
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
            </div>

            {loading && <div style={{ textAlign: "center", padding: 60 }}><Spin size="large" /></div>}

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
              <div key={`${hit.text_id}_${hit.juan_num}_${i}`} className="s-card">
                <div className="s-card-rank">#{i + 1 + (page - 1) * 20}</div>
                <div className="s-card-body">
                  <div className="s-card-title">{hit.title_zh}</div>
                  <div className="s-card-tags">
                    <Tag style={{ fontSize: 11 }}>{hit.cbeta_id} · 第{hit.juan_num}卷</Tag>
                  </div>
                  {hit.highlight.map((h, j) => (
                    <div key={j} className="s-card-meta" style={{ lineHeight: 1.7 }}
                      dangerouslySetInnerHTML={{ __html: `...${sanitizeHighlight(h)}...` }} />
                  ))}
                  <div className="s-card-actions">
                    <Button type="primary" size="small" icon={<ReadOutlined />}
                      style={{ background: "#8b2500", borderColor: "#8b2500" }}
                      onClick={() => navigate(`/read/${hit.text_id}?juan=${hit.juan_num}`)}>
                      在线阅读
                    </Button>
                  </div>
                </div>
              </div>
            ))}

            {/* 联合检索结果 */}
            {!loading && tab === "federated" && fedData && (
              <>
                {fedData.dianjin_error && (
                  <Alert
                    type="warning"
                    showIcon
                    message="典津平台提示"
                    description={fedData.dianjin_error}
                    style={{ marginBottom: 12 }}
                  />
                )}

                {/* 本地结果 */}
                {fedData.local_results.map((hit, i) => (
                  <ResultCard key={hit.id} hit={hit as SearchHit} rank={i + 1 + (page - 1) * 20} />
                ))}

                {/* 典津结果 */}
                {fedData.dianjin_results.length > 0 && (
                  <>
                    <div className="s-ext-divider">
                      典津跨平台找到 {fedData.dianjin_total.toLocaleString()} 条结果
                    </div>
                    {fedData.dianjin_results.map((hit, i) => (
                      <DianjinCard key={`dj-${i}`} hit={hit} rank={i + 1} />
                    ))}
                  </>
                )}
              </>
            )}

            {/* 本地分页 */}
            {!loading && localTotal > 20 && (
              <div style={{ textAlign: "center", margin: "16px 0" }}>
                <Pagination current={page} total={localTotal} pageSize={20}
                  showSizeChanger={false} onChange={(p) => setPage(p)} />
              </div>
            )}

            {/* 外部数据源结果 */}
            {!loading && query.length > 0 && filteredExtSources.length > 0 && (
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
    </div>
  );
}
