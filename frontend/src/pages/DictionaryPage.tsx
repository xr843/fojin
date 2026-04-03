import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import { Input, Tag, Spin, Empty, Badge, Button, Select } from "antd";
import { SearchOutlined, RobotOutlined, DownOutlined, UpOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import {
  getDictionarySources,
  searchDictionaryGrouped,
} from "../api/client";
import type { DictEntry, DictGroupedResult } from "../api/client";
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
};

const LANG_LABELS: Record<string, string> = {
  zh: "中文",
  lzh: "中文",
  pi: "巴利文",
  sa: "梵文",
  bo: "藏文",
  en: "英文",
  ja: "日文",
  ko: "韩文",
};

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + "...";
}

function EntryItem({ entry }: { entry: DictEntry }) {
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
          {LANG_LABELS[entry.lang] || entry.lang}
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

function DictGroup({ group }: { group: DictGroupedResult }) {
  const [expanded, setExpanded] = useState(false);
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
            style={{ color: "var(--fj-accent)", fontSize: 13 }}
          >
            {expanded ? "收起" : `展开全部 ${group.entries.length} 条`}
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
  const [inputValue, setInputValue] = useState(initialQ);
  const [query, setQuery] = useState(initialQ);
  const [langFilter, setLangFilter] = useState<string>("all");

  const { data: sources, isLoading: loadingSources } = useQuery({
    queryKey: ["dict-sources"],
    queryFn: getDictionarySources,
    staleTime: 300_000,
  });

  const { data: searchResult, isLoading: searching } = useQuery({
    queryKey: ["dict-search-grouped", query, langFilter],
    queryFn: () =>
      searchDictionaryGrouped({
        q: query,
        lang: langFilter === "all" ? undefined : langFilter,
      }),
    enabled: query.length > 0,
  });

  const handleSearch = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setSearchParams({ q: trimmed });
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
            ? `${sources.length} 部权威辞典 · ${totalEntries.toLocaleString()}+ 词条 · 中梵巴藏英五语`
            : "佛学辞典综合检索"}
        </p>

        {/* Search */}
        <div className="dict-search-box">
          <Input.Search
            size="large"
            placeholder="搜索佛学术语..."
            prefix={<SearchOutlined style={{ color: "var(--fj-ink-muted)" }} />}
            enterButton="搜 索"
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
                  onClick={() => {
                    setInputValue(src.name_zh);
                    setQuery(src.name_zh);
                    setSearchParams({ q: src.name_zh });
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setInputValue(src.name_zh);
                      setQuery(src.name_zh);
                      setSearchParams({ q: src.name_zh });
                    }
                  }}
                >
                  <div className="dict-source-card-name">{src.name_zh}</div>
                  <div className="dict-source-card-count">
                    {src.entry_count.toLocaleString()} 词条
                  </div>
                  {src.description && (
                    <div style={{ fontSize: 12, color: "var(--fj-ink-muted)", marginTop: 4, lineHeight: 1.5 }}>
                      {src.description.length > 50 ? src.description.slice(0, 50) + "..." : src.description}
                    </div>
                  )}
                  <div className="dict-source-card-langs">
                    {[...new Map(src.languages.map((l) => [LANG_LABELS[l] || l, l])).values()].map((lang) => (
                      <Tag
                        key={lang}
                        color={LANG_COLORS[lang] || "default"}
                        style={{ fontSize: 11, margin: 0 }}
                      >
                        {LANG_LABELS[lang] || lang}
                      </Tag>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty description="暂无辞典数据" />
          )}
        </>
      )}

      {/* Search results state */}
      {isSearching && (
        <>
          {/* Filter bar */}
          <div className="dict-filter-bar">
            <span style={{ fontSize: 13, color: "var(--fj-ink-muted)" }}>语言:</span>
            <Select
              value={langFilter}
              onChange={setLangFilter}
              style={{ width: 120 }}
              size="small"
              options={[
                { value: "all", label: "全部" },
                ...availableLangs.map((l) => ({
                  value: l,
                  label: LANG_LABELS[l] || l,
                })),
              ]}
            />
          </div>

          {searching ? (
            <div style={{ textAlign: "center", padding: 60 }}>
              <Spin size="large" />
            </div>
          ) : searchResult && searchResult.groups.length > 0 ? (
            <>
              <div className="dict-result-stats">
                共找到 <strong>{searchResult.total}</strong> 条结果
              </div>
              {searchResult.groups.map((group) => (
                <DictGroup key={group.source_code} group={group} />
              ))}
            </>
          ) : (
            <Empty description={`未找到"${query}"的相关词条`} />
          )}

          {/* Ask AI floating button */}
          <div className="dict-ask-ai">
            <Button
              type="primary"
              icon={<RobotOutlined />}
              style={{ background: "var(--fj-accent)", borderColor: "var(--fj-accent)" }}
              onClick={() => navigate(`/chat?q=${encodeURIComponent(query)}`)}
            >
              问小津
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
