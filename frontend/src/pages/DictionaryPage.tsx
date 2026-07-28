import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useNavigate } from "react-router";
import { Helmet } from "react-helmet-async";
import { Input, Tag, Spin, Empty, Badge, Button, Select, Pagination } from "antd";
import { SearchOutlined, RobotOutlined, DownOutlined, UpOutlined, ArrowLeftOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getDictionarySources,
  searchDictionaryGrouped,
  getDictConcept,
} from "../api/client";
import type { DictEntry, DictGroupedResult } from "../api/client";
import ConceptCard from "../components/ConceptCard";
import { localizedSourceName } from "../utils/sourceName";
import "../styles/dictionary.css";

const LANG_COLORS: Record<string, string> = {
  zh: "red",
  lzh: "red",
  pi: "green",
  sa: "orange",
  bo: "blue",
  en: "purple",
  ja: "cyan",
  ko: "geekblue",
  mn: "volcano",
  mnc: "lime",
};

// Language code → i18n key. lzh deliberately maps to lang.zh (not lang.lzh)
// to preserve the page's existing zh display "中文" for both codes; the
// dedupe below also relies on zh/lzh collapsing to one tag.
const LANG_LABEL_KEYS: Record<string, string> = {
  zh: "lang.zh",
  lzh: "lang.zh",
  pi: "lang.pi",
  sa: "lang.sa",
  bo: "lang.bo",
  en: "lang.en",
  ja: "lang.ja",
  ko: "lang.ko",
  mn: "lang.mn",
  mnc: "lang.mnc",
};

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

function EntryItem({ entry }: { entry: DictEntry }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="dict-entry-item"
      onClick={() => setExpanded(!expanded)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setExpanded(!expanded);
        }
      }}
    >
      <div>
        <span className="dict-entry-headword">{entry.headword}</span>
        {entry.reading && (
          <span className="dict-entry-reading">({entry.reading})</span>
        )}
        <Tag
          color={LANG_COLORS[entry.lang] || "default"}
          style={{ fontSize: 11, marginLeft: 8 }}
        >
          {LANG_LABEL_KEYS[entry.lang] ? t(LANG_LABEL_KEYS[entry.lang]) : entry.lang}
        </Tag>
        {entry.source_name && (
          <Tag color="orange" style={{ fontSize: 11, marginLeft: 4 }}>
            {entry.source_name}
          </Tag>
        )}
      </div>
      {expanded ? (
        <div className="dict-entry-def-full">{entry.definition}</div>
      ) : (
        <div className="dict-entry-def-preview">
          {truncate(entry.definition, 200)}
        </div>
      )}
    </div>
  );
}

const COLLAPSE_THRESHOLD = 3;

function DictGroup({ group, defaultExpanded = false }: { group: DictGroupedResult; defaultExpanded?: boolean }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasMore = group.entries.length > COLLAPSE_THRESHOLD;
  const visibleEntries = expanded ? group.entries : group.entries.slice(0, COLLAPSE_THRESHOLD);

  return (
    <div className="dict-group">
      <div className="dict-group-header">
        <span className="dict-group-name">{group.source_name}</span>
        <Badge
          count={group.total}
          style={{ backgroundColor: "var(--fj-gold)" }}
          overflowCount={9999}
        />
      </div>
      <div className="dict-entry-list">
        {visibleEntries.map((entry) => (
          <EntryItem key={entry.id} entry={entry} />
        ))}
      </div>
      {hasMore && (
        <div style={{ textAlign: "center", padding: "8px 0" }}>
          <Button
            type="link"
            size="small"
            icon={expanded ? <UpOutlined /> : <DownOutlined />}
            onClick={() => setExpanded(!expanded)}
            style={{ color: "var(--fj-highlight)", fontSize: 13 }}
          >
            {expanded ? t("dict.collapse") : t("dict.expand_all", { n: group.entries.length })}
          </Button>
        </div>
      )}
    </div>
  );
}

export default function DictionaryPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get("q") || "";
  const initialSource = searchParams.get("source") || "";
  const [inputValue, setInputValue] = useState(initialQ);
  const [query, setQuery] = useState(initialQ);
  const [langFilter, setLangFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>(initialSource);
  const [page, setPage] = useState(1);

  const { data: sources, isLoading: loadingSources } = useQuery({
    queryKey: ["dict-sources"],
    queryFn: getDictionarySources,
    staleTime: 300_000,
  });

  const { data: searchResult, isLoading: searching } = useQuery({
    queryKey: ["dict-search-grouped", query, langFilter, sourceFilter, page],
    queryFn: () =>
      searchDictionaryGrouped({
        q: query,
        lang: langFilter === "all" ? undefined : langFilter,
        source: sourceFilter || undefined,
        page,
      }),
    enabled: query.length > 0,
  });

  // Cross-lingual concept lookup — skipped for whole-source browse (q="*").
  const conceptQuery = query && query !== "*" ? query : "";
  const { data: conceptResult } = useQuery({
    queryKey: ["dict-concept", conceptQuery],
    queryFn: () => getDictConcept(conceptQuery),
    enabled: conceptQuery.length > 0,
    staleTime: 300_000,
  });

  const handleSearch = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    const params: Record<string, string> = { q: trimmed };
    if (sourceFilter) params.source = sourceFilter;
    setSearchParams(params);
  };

  const handleSourceClick = (code: string) => {
    setInputValue("");
    setQuery("*");
    setSourceFilter(code);
    setPage(1);
    setSearchParams({ q: "*", source: code });
  };


  // Collect unique languages from sources
  const availableLangs = useMemo(() => {
    if (!sources) return [];
    const set = new Set<string>();
    sources.forEach((s) => s.languages.forEach((l) => set.add(l)));
    return Array.from(set).sort((a, b) => {
      const order = ["zh", "pi", "sa", "bo", "en", "ja", "ko"];
      const ia = order.indexOf(a);
      const ib = order.indexOf(b);
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
    });
  }, [sources]);

  const totalEntries = sources
    ? sources.reduce((sum, s) => sum + s.entry_count, 0)
    : 0;

  const isSearching = query.length > 0;

  const browsedSource =
    sourceFilter && sources ? sources.find((s) => s.code === sourceFilter) ?? null : null;

  return (
    <div className="dict-page">
      <Helmet>
        <title>{t("nav.dictionary")} - {t("app.name")}</title>
      </Helmet>

      {/* Header */}
      <div className="dict-header">
        <h1 className="dict-title">{t("nav.dictionary")}</h1>
        <p className="dict-subtitle">
          {sources
            ? t("dict.subtitle", { n: sources.length, entries: totalEntries.toLocaleString() })
            : t("dict.subtitle_default")}
        </p>

        {/* Search */}
        <div className="dict-search-box">
          <Input.Search
            size="large"
            placeholder={t("dict.search_placeholder")}
            prefix={<SearchOutlined style={{ color: "var(--fj-ink-muted)" }} />}
            enterButton={t("dict.search_button")}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onSearch={handleSearch}
            allowClear
            style={{ height: 56 }}
            styles={{
              input: { height: 56, fontSize: 18, lineHeight: "56px" },
            }}
          />
        </div>

        {/* Hot terms removed per user request */}
      </div>

      {/* Landing state: source cards */}
      {!isSearching && (
        <>
          {loadingSources ? (
            <div style={{ textAlign: "center", padding: 60 }}>
              <Spin size="large" />
            </div>
          ) : sources && sources.length > 0 ? (
            <div className="dict-sources-grid">
              {sources.map((src) => (
                <div
                  key={src.id}
                  className="dict-source-card"
                  role="button"
                  tabIndex={0}
                  style={{ cursor: "pointer" }}
                  onClick={() => handleSourceClick(src.code)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSourceClick(src.code);
                    }
                  }}
                >
                  <div className="dict-source-card-name">{localizedSourceName(src)}</div>
                  <div className="dict-source-card-count">
                    {t("dict.entry_count", { n: src.entry_count.toLocaleString() })}
                  </div>
                  {src.description && (
                    <div style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginTop: 4, lineHeight: 1.5 }}>
                      {src.description.length > 50 ? src.description.slice(0, 50) + "..." : src.description}
                    </div>
                  )}
                  <div className="dict-source-card-langs">
                    {[...new Map(src.languages.map((l) => [LANG_LABEL_KEYS[l] || l, l])).values()].map((lang) => (
                      <Tag
                        key={lang}
                        color={LANG_COLORS[lang] || "default"}
                        style={{ fontSize: 11, margin: 0 }}
                      >
                        {LANG_LABEL_KEYS[lang] ? t(LANG_LABEL_KEYS[lang]) : lang}
                      </Tag>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty description={t("dict.no_sources")} />
          )}
        </>
      )}

      {/* Search results state */}
      {isSearching && (
        <>
          {/* Back + Filter bar */}
          <div className="dict-filter-bar">
            <Button
              type="link"
              icon={<ArrowLeftOutlined />}
              onClick={() => {
                setQuery("");
                setInputValue("");
                setSourceFilter("");
                setSearchParams({});
              }}
              style={{ color: "var(--fj-highlight)", fontSize: 13, padding: 0, marginRight: 16 }}
            >
              {t("dict.back_to_list")}
            </Button>
            {browsedSource && (
              <span style={{ fontSize: 14, color: "var(--fj-ink)", fontWeight: 500 }}>
                {t("dict.browsing", {
                  name: localizedSourceName(browsedSource),
                  n: browsedSource.entry_count.toLocaleString(),
                })}
              </span>
            )}
            <span style={{ fontSize: 13, color: "var(--fj-ink-muted)" }}>{t("dict.language_label")}</span>
            <Select
              value={langFilter}
              onChange={setLangFilter}
              style={{ width: 120 }}
              size="small"
              options={[
                { value: "all", label: t("dict.all_languages") },
                ...availableLangs.map((l) => ({
                  value: l,
                  label: LANG_LABEL_KEYS[l] ? t(LANG_LABEL_KEYS[l]) : l,
                })),
              ]}
            />
          </div>

          <ConceptCard
            data={conceptResult}
            onPick={(term) => {
              setInputValue(term);
              handleSearch(term);
            }}
          />

          {searching ? (
            <div style={{ textAlign: "center", padding: 60 }}>
              <Spin size="large" />
            </div>
          ) : searchResult && searchResult.groups.length > 0 ? (
            <>
              <div className="dict-result-stats">
                {t("dict.results_found_prefix")} <strong>{searchResult.total}</strong> {t("dict.results_found_suffix")}
              </div>
              {searchResult.groups.map((group) => (
                <DictGroup key={group.source_code} group={group} defaultExpanded={!!sourceFilter} />
              ))}
              {searchResult.page_size && (
                <div style={{ textAlign: "center", padding: "16px 0" }}>
                  <Pagination
                    current={page}
                    pageSize={searchResult.page_size}
                    total={searchResult.total}
                    onChange={(p) => setPage(p)}
                    showSizeChanger={false}
                    showTotal={(total) => t("dict.total_n", { n: total })}
                  />
                </div>
              )}
            </>
          ) : (
            <Empty description={t("dict.no_results", { query })} />
          )}

          {/* Ask AI floating button */}
          <div className="dict-ask-ai">
            <Button
              type="primary"
              icon={<RobotOutlined />}
              style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
              onClick={() => navigate(`/chat?q=${encodeURIComponent(query)}`)}
            >
              {t("dict.ask_ai")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
