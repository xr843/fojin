import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useNavigate, Link } from "react-router";
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

/** 语言码 → 显示身份。zh/lzh 都显示为「中文」，比较时算同一种语言。 */
function langIdentity(lang: string): string {
  return LANG_LABEL_KEYS[lang] ?? lang;
}

/**
 * 分组里的词条该不该挂语言标签。分组标题只写了辞典名，所以语言标签只在它
 * 说了标题没说的事时才有用：
 *   - 分组内语言不唯一（如 DPD 同时命中巴利与英文词条）；
 *   - 或分组内语言唯一、却不是该辞典的默认语言（如 84000 登记为藏/英，
 *     命中的全是英文词条）。
 * defaultLang：undefined = 辞典信息还在加载（先不挂，免得标签闪一下又消失）；
 * null = 拿不到辞典信息（不猜，照常挂）。默认语言取登记的第一种语言。
 */
function groupNeedsLangTag(entries: DictEntry[], defaultLang: string | null | undefined): boolean {
  const langs = new Set(entries.map((e) => langIdentity(e.lang)));
  if (langs.size > 1) return true;
  if (defaultLang === undefined) return false;
  if (defaultLang === null) return true;
  return !langs.has(langIdentity(defaultLang));
}

function EntryItem({
  entry,
  showLang,
  showSource,
}: {
  entry: DictEntry;
  showLang: boolean;
  showSource: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="dict-entry-item">
      {/* 可点开合的部分单独包一层，出口链接留在它外面。嵌在 role="button" 里
          的 <a>/<button> 是 nested-interactive：读屏软件只报最外层那个按钮，
          键盘用户 Tab 不到里面的出口。 */}
      <div
        className="dict-entry-main"
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
          {showLang && (
            <Tag
              color={LANG_COLORS[entry.lang] || "default"}
              style={{ fontSize: 11, marginLeft: 8 }}
            >
              {LANG_LABEL_KEYS[entry.lang] ? t(LANG_LABEL_KEYS[entry.lang]) : entry.lang}
            </Tag>
          )}
          {showSource && entry.source_name && (
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

      {/* 读完释义处的两个出口。辞典此前是个死胡同：30 天 1,886 次浏览里
          dictionary→dictionary 有 1,331 次，去 /chat 只有 71 次、去经文只有
          15 次 —— 唯一的出口是右下角那颗浮动按钮，而且它带的是搜索框里的词、
          不是眼前这一条的词头。出口要贴着内容放，且要带**这一条**的词头。 */}
      {expanded && (
        <div className="dict-entry-exits">
          <Link to={`/chat?q=${encodeURIComponent(entry.headword)}`}>
            {t("dict.entry_ask", { word: entry.headword })}
          </Link>
          <Link to={`/search?q=${encodeURIComponent(entry.headword)}`}>
            {t("dict.entry_in_canon")}
          </Link>
        </div>
      )}
    </div>
  );
}

const COLLAPSE_THRESHOLD = 3;

function DictGroup({
  group,
  defaultLang,
  defaultExpanded = false,
}: {
  group: DictGroupedResult;
  defaultLang: string | null | undefined;
  defaultExpanded?: boolean;
}) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const hasMore = group.entries.length > COLLAPSE_THRESHOLD;
  const visibleEntries = expanded ? group.entries : group.entries.slice(0, COLLAPSE_THRESHOLD);
  // 按整组（不只是折叠后可见的前几条）判断，展开时标签不会忽然冒出来。
  const showLang = groupNeedsLangTag(group.entries, defaultLang);

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
          <EntryItem
            key={entry.id}
            entry={entry}
            showLang={showLang}
            // 分组标题已写着辞典名；只有词条来源与分组不一致时才值得再标一次。
            showSource={entry.source_code !== group.source_code && entry.source_name !== group.source_name}
          />
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

  const { data: sources, isLoading: loadingSources, isError: sourcesFailed } = useQuery({
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
    <div className={isSearching ? "dict-page dict-page--with-ask" : "dict-page"}>
      <Helmet>
        <title>{`${t("nav.dictionary")} - ${t("app.name")}`}</title>
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
                <DictGroup
                  key={group.source_code}
                  group={group}
                  defaultLang={
                    sources
                      ? (sources.find((s) => s.code === group.source_code)?.languages[0] ?? null)
                      : sourcesFailed
                        ? null
                        : undefined
                  }
                  defaultExpanded={!!sourceFilter}
                />
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

          {/* Ask AI floating button. 手机上缩成圆形图标按钮（见 dictionary.css），文字靠 aria-label/title 保留。 */}
          <div className="dict-ask-ai">
            <Button
              type="primary"
              icon={<RobotOutlined />}
              aria-label={t("dict.ask_ai")}
              title={t("dict.ask_ai")}
              style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
              onClick={() => navigate(`/chat?q=${encodeURIComponent(query)}`)}
            >
              <span className="dict-ask-ai-label">{t("dict.ask_ai")}</span>
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
