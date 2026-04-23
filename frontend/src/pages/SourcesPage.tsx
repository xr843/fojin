import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Helmet } from "react-helmet-async";
import { Empty, Input, Select, Skeleton } from "antd";
import { SearchOutlined, ThunderboltOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { getSources, type DataSource } from "../api/client";
import { getLangName, hasDirectSearchUrl, normalizeLangCode } from "../utils/sourceUrls";
import SourceCard from "./sources/SourceCard";
import SuggestSourceForm from "./sources/SuggestSourceForm";
import {
  FIELD_NAMES,
  FIELD_ORDER,
  LANG_ORDER,
  REGION_ORDER,
} from "./sources/constants";
import "../styles/sources.css";

type GroupBy = "region" | "field" | "lang";

const VALID_GROUP_BY: readonly GroupBy[] = ["region", "field", "lang"] as const;

export default function SourcesPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // URL params are the source of truth; defaults live here, not in state.
  const search = searchParams.get("q") ?? "";
  const regionFilter = searchParams.get("region") ?? "all";
  const langFilter = searchParams.get("lang") ?? "all";
  const fieldFilter = searchParams.get("field") ?? "all";
  const searchQuery = searchParams.get("try") ?? "";
  const rawGroupBy = searchParams.get("group") ?? "";
  const groupBy: GroupBy = (VALID_GROUP_BY as readonly string[]).includes(rawGroupBy)
    ? (rawGroupBy as GroupBy)
    : "region";

  const updateParam = useCallback(
    (key: string, value: string, defaultValue: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (value === defaultValue || value === "") {
            next.delete(key);
          } else {
            next.set(key, value);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setSearch = useCallback((v: string) => updateParam("q", v, ""), [updateParam]);
  const setRegionFilter = useCallback(
    (v: string) => updateParam("region", v, "all"),
    [updateParam],
  );
  const setLangFilter = useCallback(
    (v: string) => updateParam("lang", v, "all"),
    [updateParam],
  );
  const setFieldFilter = useCallback(
    (v: string) => updateParam("field", v, "all"),
    [updateParam],
  );
  const setSearchQuery = useCallback(
    (v: string) => updateParam("try", v, ""),
    [updateParam],
  );
  const setGroupBy = useCallback(
    (v: GroupBy) => {
      updateParam("group", v, "region");
      // Reset expansion state: group names can collide across groupBy modes
      // (e.g. "其他" exists in all three, "国际" is both a region and could be
      // a bucket label), so a key like "其他" would carry over incorrectly.
      setExpandedGroups({});
    },
    [updateParam],
  );

  // Local mirrors for free-text inputs so typing stays smooth; URL is written
  // after a short debounce. useEffect resyncs when URL changes externally
  // (back/forward, shared link landing).
  const [searchInput, setSearchInput] = useState(search);
  const [tryInput, setTryInput] = useState(searchQuery);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout>>();
  const GROUP_COLLAPSE_LIMIT = 12;
  const toggleGroup = useCallback((name: string) => {
    setExpandedGroups((prev) => ({ ...prev, [name]: !prev[name] }));
  }, []);

  useEffect(() => {
    setSearchInput(search);
  }, [search]);

  useEffect(() => {
    setTryInput(searchQuery);
  }, [searchQuery]);

  const handleSearchInputChange = useCallback(
    (v: string) => {
      setSearchInput(v);
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
      searchDebounceRef.current = setTimeout(() => setSearch(v), 250);
    },
    [setSearch],
  );

  useEffect(() => {
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current);
    };
  }, []);

  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const { data: sources, isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: getSources,
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
  });

  const { regions, languages, researchFields } = useMemo(() => {
    const regionSet = new Set<string>();
    const nameToLangCode = new Map<string, string>();
    const fieldSet = new Set<string>();

    for (const s of sources ?? []) {
      regionSet.add(s.region || "其他");

      if (s.languages) {
        for (const raw of s.languages.split(",")) {
          const code = normalizeLangCode(raw.trim());
          const name = getLangName(code);
          if (!nameToLangCode.has(name)) nameToLangCode.set(name, code);
        }
      }

      if (s.research_fields) {
        for (const raw of s.research_fields.split(",")) {
          const key = raw.trim();
          if (key in FIELD_NAMES) fieldSet.add(key);
        }
      }
    }

    const regionArr = Array.from(regionSet).sort((a, b) => {
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      const ia = REGION_ORDER.indexOf(a);
      const ib = REGION_ORDER.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });

    const langArr = Array.from(nameToLangCode.values()).sort((a, b) => {
      const order = (c: string) =>
        c === "mul" ? 999 : LANG_ORDER.indexOf(c) === -1 ? 99 : LANG_ORDER.indexOf(c);
      return order(a) - order(b);
    });

    const fieldArr = Array.from(fieldSet).sort((a, b) => {
      const ia = FIELD_ORDER.indexOf(a);
      const ib = FIELD_ORDER.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });

    return { regions: regionArr, languages: langArr, researchFields: fieldArr };
  }, [sources]);

  const filtered = useMemo(() => {
    if (!sources) return [];
    return sources.filter((s) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !s.name_zh.toLowerCase().includes(q) &&
          !(s.name_en || "").toLowerCase().includes(q) &&
          !(s.description || "").toLowerCase().includes(q) &&
          !s.code.toLowerCase().includes(q)
        ) {
          return false;
        }
      }
      if (regionFilter !== "all" && (s.region || "其他") !== regionFilter) return false;
      if (langFilter !== "all") {
        const langs = (s.languages || "").split(",").map((l) => l.trim());
        const filterName = getLangName(langFilter);
        if (!langs.some((l) => getLangName(l) === filterName)) return false;
      }
      if (fieldFilter !== "all") {
        const fields = (s.research_fields || "").split(",").map((f) => f.trim());
        if (!fields.includes(fieldFilter)) return false;
      }
      return true;
    });
  }, [sources, search, regionFilter, langFilter, fieldFilter]);

  const grouped = useMemo(() => {
    const map: Record<string, DataSource[]> = {};
    const addTo = (key: string, s: DataSource) => {
      if (!map[key]) map[key] = [];
      map[key].push(s);
    };
    for (const s of filtered) {
      if (groupBy === "region") {
        addTo(s.region || "其他", s);
      } else if (groupBy === "field") {
        const fields = (s.research_fields || "")
          .split(",")
          .map((f) => f.trim())
          .filter(Boolean);
        if (fields.length === 0) {
          addTo("其他", s);
        } else {
          fields.forEach((f) => addTo(FIELD_NAMES[f] || f, s));
        }
      } else {
        const langs = (s.languages || "")
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean);
        if (langs.length === 0) {
          addTo("其他", s);
        } else {
          const seen = new Set<string>();
          langs.forEach((l) => {
            const name = getLangName(l);
            if (!seen.has(name)) {
              seen.add(name);
              addTo(name, s);
            }
          });
        }
      }
    }
    for (const items of Object.values(map)) {
      items.sort(
        (a, b) =>
          (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
          a.name_zh.localeCompare(b.name_zh, "zh"),
      );
    }
    const orderList =
      groupBy === "region"
        ? REGION_ORDER
        : groupBy === "field"
          ? FIELD_ORDER.map((f) => FIELD_NAMES[f] || f)
          : LANG_ORDER.map((l) => getLangName(l));
    return Object.entries(map).sort(([a], [b]) => {
      if (a === "其他") return 1;
      if (b === "其他") return -1;
      const ia = orderList.indexOf(a);
      const ib = orderList.indexOf(b);
      return (ia === -1 ? 98 : ia) - (ib === -1 ? 98 : ib);
    });
  }, [filtered, groupBy]);

  const counters = useMemo(() => {
    const all = sources ?? [];
    return {
      local: all.filter((s) => s.has_local_fulltext).length,
      remote: all.filter((s) => s.has_remote_fulltext).length,
      // Count sources with a registered direct-search template, not the DB
      // `supports_search` flag — the flag means "site has a search page" but
      // doesn't guarantee we know the query URL template.
      directSearch: all.filter((s) => hasDirectSearchUrl(s.code)).length,
      iiif: all.filter((s) => s.supports_iiif).length,
      api: all.filter((s) => s.supports_api).length,
    };
  }, [sources]);

  if (isLoading) {
    return (
      <div className="sources-page">
        <div className="sources-header">
          <Skeleton.Input active size="large" style={{ width: 180, marginBottom: 12 }} />
          <br />
          <Skeleton.Input active size="small" style={{ width: 520 }} />
        </div>
        <div className="sources-skeleton-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="source-card">
              <Skeleton active paragraph={{ rows: 2 }} title />
            </div>
          ))}
        </div>
      </div>
    );
  }

  const total = sources?.length || 0;

  return (
    <div className="sources-page">
      <Helmet>
        <title>数据源导航 | 佛津</title>
        <meta
          name="description"
          content={
            total > 0
              ? `聚合全球 ${total} 个佛教数字资源，覆盖图书馆、大学、研究机构、数字项目等。`
              : "聚合全球佛教数字资源，覆盖图书馆、大学、研究机构、数字项目等。"
          }
        />
        <link rel="canonical" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="x-default" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="zh" href="https://fojin.app/sources" />
      </Helmet>
      <div className="sources-header">
        <h1 className="sources-title">数据源导航</h1>
        <p className="sources-desc">
          聚合全球 {total} 个佛教数字资源：
          {counters.directSearch} 可搜索 · {counters.local} 已入库全文 · {counters.remote} 外站全文 · {counters.iiif} 影像 · {counters.api} API
        </p>
      </div>

      <div className="sources-hero-search">
        <div className="sources-hero-search-head">
          <ThunderboltOutlined className="sources-hero-search-icon" />
          <div className="sources-hero-search-copy">
            <div className="sources-hero-search-title">一次输入，直达 {counters.directSearch} 个可搜索数据源</div>
            <div className="sources-hero-search-sub">
              敲入一个关键词，下方每张卡片会生成对应数据源的站内搜索直链
            </div>
          </div>
        </div>
        <Input.Search
          placeholder="例：般若、涅槃、慈悲、阿含"
          size="large"
          enterButton="生成直达"
          allowClear
          value={tryInput}
          onChange={(e) => setTryInput(e.target.value)}
          onSearch={(v) => {
            setSearchQuery(v);
            if (v) {
              // Without this the URL updates silently but the viewport stays
              // on the hero — users don't see the per-card direct links and
              // think the button did nothing.
              requestAnimationFrame(() => {
                document
                  .querySelector(".sources-toolbar")
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              });
            }
          }}
        />
        {searchQuery && (
          <div className="sources-hero-search-result">
            已为 {counters.directSearch} 个数据源生成「{searchQuery}」直达链接 —— 下滑查看每张卡片的「搜索」按钮
          </div>
        )}
      </div>

      <div className="sources-trust">
        <div className="sources-trust-items">
          <div className="sources-trust-item">
            <div className="sources-trust-title">来源可溯</div>
            <div className="sources-trust-desc">
              所有数据均来自 CBETA、BDRC、SAT、SuttaCentral 等学术机构公开发布的数字资源，每条记录保留原始来源标识与链接。
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">定期同步</div>
            <div className="sources-trust-desc">
              通过 Git、API、批量导入等渠道与上游数据源保持同步，确保收录内容反映最新发布状态。
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">自动去重</div>
            <div className="sources-trust-desc">
              跨数据源自动识别同一典籍的不同收录，合并为统一记录，保留各源的独立编号与访问链接。
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">覆盖广泛</div>
            <div className="sources-trust-desc">
              涵盖 {regions.length} 个国家和地区、{languages.length} 种语言，覆盖汉传、藏传、南传、梵文等多种佛教传统。
            </div>
          </div>
        </div>
      </div>

      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder="搜索数据源名称、描述..."
          allowClear
          value={searchInput}
          onChange={(e) => handleSearchInputChange(e.target.value)}
          style={{ width: 260 }}
        />
        <Select
          value={regionFilter}
          onChange={setRegionFilter}
          style={{ width: 140 }}
          options={[
            { value: "all", label: `全部地区 (${regions.length})` },
            ...regions.map((r) => ({ value: r, label: r })),
          ]}
        />
        <Select
          value={langFilter}
          onChange={setLangFilter}
          style={{ width: 140 }}
          options={[
            { value: "all", label: `全部语种 (${languages.length})` },
            ...languages.map((l) => ({ value: l, label: getLangName(l) })),
          ]}
        />
        <Select
          value={fieldFilter}
          onChange={setFieldFilter}
          style={{ width: 150 }}
          options={[
            { value: "all", label: `研究领域 (${researchFields.length})` },
            ...researchFields.map((f) => ({ value: f, label: FIELD_NAMES[f] || f })),
          ]}
        />
        <Select
          value={groupBy}
          onChange={setGroupBy}
          style={{ width: 130 }}
          options={[
            { value: "region", label: "按地区分组" },
            { value: "field", label: "按研究领域" },
            { value: "lang", label: "按语种" },
          ]}
        />
      </div>

      <div className="sources-stats-bar">
        当前显示 <strong>{filtered.length}</strong> / {total} 个数据源
        {groupBy !== "region" && ` · ${grouped.length} 个分组`}
        {groupBy !== "region" && (
          <span className="sources-stats-hint">（一个数据源可归属多个{groupBy === "field" ? "研究领域" : "语种"}）</span>
        )}
      </div>

      {filtered.length === 0 ? (
        <Empty description="无匹配数据源" style={{ marginTop: 60 }} />
      ) : (
        <div className="sources-groups">
          {grouped.map(([groupName, items]) => {
            const isExpanded = expandedGroups[groupName] ?? false;
            const shouldCollapse = items.length > GROUP_COLLAPSE_LIMIT;
            const visible =
              shouldCollapse && !isExpanded ? items.slice(0, GROUP_COLLAPSE_LIMIT) : items;
            return (
              <div key={groupName} className="sources-group">
                <div className="sources-group-header">
                  <span className="sources-group-name">{groupName}</span>
                  <span className="sources-group-count">{items.length}</span>
                </div>
                <div className="sources-grid">
                  {visible.map((s) => (
                    <SourceCard key={s.code} source={s} searchQuery={searchQuery} />
                  ))}
                </div>
                {shouldCollapse && (
                  <button
                    type="button"
                    className="sources-group-toggle"
                    onClick={() => toggleGroup(groupName)}
                    aria-expanded={isExpanded}
                  >
                    {isExpanded
                      ? `收起 ${groupName}`
                      : `展开全部 ${items.length} 个 (还有 ${items.length - GROUP_COLLAPSE_LIMIT} 个)`}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      <SuggestSourceForm />

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
