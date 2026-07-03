import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Helmet } from "react-helmet-async";
import { useTranslation } from "react-i18next";
import { Empty, Input, Select, Skeleton } from "antd";
import { SearchOutlined, ThunderboltOutlined, VerticalAlignTopOutlined } from "@ant-design/icons";
import { getSources, type DataSource } from "../api/client";
import { SUPPORTED_UI_LANGS } from "../i18n";
import { getLangName, hasDirectSearchUrl, localizedLangName, normalizeLangCode } from "../utils/sourceUrls";
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
type Capability = "direct" | "local" | "remote" | "iiif" | "api";

const VALID_GROUP_BY: readonly GroupBy[] = ["region", "field", "lang"] as const;
const VALID_CAPABILITY: readonly Capability[] = ["direct", "local", "remote", "iiif", "api"] as const;

const CAPABILITY_LABELS: Record<Capability, { labelKey: string; tipKey: string }> = {
  direct: { labelKey: "sources.cap_direct", tipKey: "sources.cap_direct_tip" },
  local: { labelKey: "sources.cap_local", tipKey: "sources.cap_local_tip" },
  remote: { labelKey: "sources.cap_remote", tipKey: "sources.cap_remote_tip" },
  iiif: { labelKey: "sources.cap_iiif", tipKey: "sources.cap_iiif_tip" },
  api: { labelKey: "sources.cap_api", tipKey: "sources.cap_api_tip" },
};

export default function SourcesPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();

  // URL params are the source of truth; defaults live here, not in state.
  const search = searchParams.get("q") ?? "";
  const regionFilter = searchParams.get("region") ?? "all";
  // #709: filter param renamed `lang` → `tl` (collision with the i18next
  // querystring detector). Legacy ?lang= links resolve for non-UI codes.
  const legacyLangParam = searchParams.get("lang") ?? "";
  const langFilter =
    searchParams.get("tl") ??
    (legacyLangParam && !(SUPPORTED_UI_LANGS as readonly string[]).includes(legacyLangParam)
      ? legacyLangParam
      : "all");
  const fieldFilter = searchParams.get("field") ?? "all";
  const fulltextOnly = searchParams.get("fulltext") === "1";
  const searchQuery = searchParams.get("try") ?? "";
  const rawGroupBy = searchParams.get("group") ?? "";
  const groupBy: GroupBy = (VALID_GROUP_BY as readonly string[]).includes(rawGroupBy)
    ? (rawGroupBy as GroupBy)
    : "region";
  const rawCap = searchParams.get("cap") ?? "";
  const capability: Capability | null = (VALID_CAPABILITY as readonly string[]).includes(rawCap)
    ? (rawCap as Capability)
    : null;

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
    (v: string) => {
      updateParam("tl", v, "all");
      // Clean a lingering legacy filter value, or the read fallback springs
      // it back (e.g. old link ?lang=sa → user picks "All" → still sa).
      if (
        legacyLangParam &&
        !(SUPPORTED_UI_LANGS as readonly string[]).includes(legacyLangParam)
      ) {
        updateParam("lang", "", "");
      }
    },
    [updateParam, legacyLangParam],
  );
  const setFieldFilter = useCallback(
    (v: string) => updateParam("field", v, "all"),
    [updateParam],
  );
  const setFulltextOnly = useCallback(
    (v: boolean) => updateParam("fulltext", v ? "1" : "", ""),
    [updateParam],
  );
  const setSearchQuery = useCallback(
    (v: string) => updateParam("try", v, ""),
    [updateParam],
  );
  const setCapability = useCallback(
    (v: Capability | null) => updateParam("cap", v ?? "", ""),
    [updateParam],
  );
  const toggleCapability = useCallback(
    (v: Capability) => setCapability(capability === v ? null : v),
    [capability, setCapability],
  );
  // Local mirrors for free-text inputs so typing stays smooth; URL is written
  // after a short debounce. Resynced below when URL changes externally
  // (back/forward, shared link landing).
  const [searchInput, setSearchInput] = useState(search);
  const [tryInput, setTryInput] = useState(searchQuery);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout>>(undefined);

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

  const GROUP_COLLAPSE_LIMIT = 12;
  const toggleGroup = useCallback((name: string) => {
    setExpandedGroups((prev) => ({ ...prev, [name]: !prev[name] }));
  }, []);

  // Resync mirrors when the URL changes externally — adjusted during render.
  const [prevSearch, setPrevSearch] = useState(search);
  if (prevSearch !== search) {
    setPrevSearch(search);
    setSearchInput(search);
  }
  const [prevSearchQuery, setPrevSearchQuery] = useState(searchQuery);
  if (prevSearchQuery !== searchQuery) {
    setPrevSearchQuery(searchQuery);
    setTryInput(searchQuery);
  }

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
      regionSet.add(s.region || "其他"); // i18n-exempt

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
      if (a === "其他") return 1; // i18n-exempt
      if (b === "其他") return -1; // i18n-exempt
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
      if (regionFilter !== "all" && (s.region || "其他") !== regionFilter) return false; // i18n-exempt
      if (langFilter !== "all") {
        const langs = (s.languages || "").split(",").map((l) => l.trim());
        const filterName = getLangName(langFilter);
        if (!langs.some((l) => getLangName(l) === filterName)) return false;
      }
      if (fieldFilter !== "all") {
        const fields = (s.research_fields || "").split(",").map((f) => f.trim());
        if (!fields.includes(fieldFilter)) return false;
      }
      if (fulltextOnly && !s.has_local_fulltext && !s.has_remote_fulltext) {
        return false;
      }
      if (capability) {
        if (capability === "direct" && !hasDirectSearchUrl(s.code)) return false;
        if (capability === "local" && !s.has_local_fulltext) return false;
        if (capability === "remote" && !s.has_remote_fulltext) return false;
        if (capability === "iiif" && !s.supports_iiif) return false;
        if (capability === "api" && !s.supports_api) return false;
      }
      return true;
    });
  }, [sources, search, regionFilter, langFilter, fieldFilter, fulltextOnly, capability]);

  const grouped = useMemo(() => {
    const map: Record<string, DataSource[]> = {};
    const addTo = (key: string, s: DataSource) => {
      if (!map[key]) map[key] = [];
      map[key].push(s);
    };
    for (const s of filtered) {
      if (groupBy === "region") {
        addTo(s.region || "其他", s); // i18n-exempt
      } else if (groupBy === "field") {
        const fields = (s.research_fields || "")
          .split(",")
          .map((f) => f.trim())
          .filter(Boolean);
        if (fields.length === 0) {
          addTo("其他", s); // i18n-exempt
        } else {
          // Group by field CODE; translated to a display name at render time.
          fields.forEach((f) => addTo(f, s));
        }
      } else {
        const langs = (s.languages || "")
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean);
        if (langs.length === 0) {
          addTo("其他", s); // i18n-exempt
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
          ? FIELD_ORDER
          : LANG_ORDER.map((l) => getLangName(l));
    return Object.entries(map).sort(([a], [b]) => {
      if (a === "其他") return 1; // i18n-exempt
      if (b === "其他") return -1; // i18n-exempt
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

  // Group keys are raw data values (zh region names / field codes / language
  // display names) — translate at display time, falling back to the raw value.
  const groupLabel = (name: string): string => {
    if (name === "其他") return t("region.其他", name); // i18n-exempt
    if (groupBy === "region") return t(`region.${name}`, name);
    if (groupBy === "field") return t(`field.${name}`, FIELD_NAMES[name] || name);
    // language groups are keyed by the Chinese data name — reverse to the
    // ISO code and resolve through lang.* keys
    if (groupBy === "lang") return localizedLangName(normalizeLangCode(name), t);
    return name;
  };

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
        <title>{t("sources.page_title")}</title>
        <meta
          name="description"
          content={
            total > 0
              ? t("sources.page_desc", { n: total })
              : t("sources.page_desc_default")
          }
        />
        <link rel="canonical" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="x-default" href="https://fojin.app/sources" />
        <link rel="alternate" hrefLang="zh" href="https://fojin.app/sources" />
      </Helmet>
      <div className="sources-header">
        <h1 className="sources-title">{t("sources.heading")}</h1>
        <p className="sources-desc">{t("sources.subtitle", { n: total })}</p>
        <div className="sources-cap-chips" role="group" aria-label={t("sources.filter_by_capability_aria")}>
          {(
            [
              { key: "direct", count: counters.directSearch },
              { key: "local", count: counters.local },
              { key: "remote", count: counters.remote },
              { key: "iiif", count: counters.iiif },
              { key: "api", count: counters.api },
            ] as { key: Capability; count: number }[]
          )
            .slice()
            .sort((a, b) => b.count - a.count)
            .map(({ key, count }) => {
            const active = capability === key;
            return (
              <button
                key={key}
                type="button"
                className={`sources-cap-chip sources-cap-chip-${key}${active ? " is-active" : ""}`}
                onClick={() => toggleCapability(key)}
                title={t(CAPABILITY_LABELS[key].tipKey)}
                aria-pressed={active}
              >
                <strong>{count}</strong>
                <span>{t(CAPABILITY_LABELS[key].labelKey)}</span>
              </button>
            );
          })}
          {capability && (
            <button
              type="button"
              className="sources-cap-chip-clear"
              onClick={() => setCapability(null)}
              aria-label={t("sources.clear_capability_aria")}
            >
              {t("sources.clear")}
            </button>
          )}
        </div>
      </div>

      <div className="sources-hero-search">
        <div className="sources-hero-search-head">
          <ThunderboltOutlined className="sources-hero-search-icon" />
          <div className="sources-hero-search-copy">
            <div className="sources-hero-search-title">{t("sources.hero_title", { n: counters.directSearch })}</div>
            <div className="sources-hero-search-sub">
              {t("sources.hero_sub")}
            </div>
          </div>
        </div>
        <Input.Search
          placeholder={t("sources.hero_placeholder")}
          size="large"
          enterButton={t("sources.hero_button")}
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
                const prefersReduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
                document
                  .querySelector(".sources-toolbar")
                  ?.scrollIntoView({ behavior: prefersReduced ? "auto" : "smooth", block: "start" });
              });
            }
          }}
        />
        {searchQuery && (
          <div className="sources-hero-search-result" role="status" aria-live="polite">
            {t("sources.hero_result", { n: counters.directSearch, query: searchQuery })}
          </div>
        )}
      </div>

      <div className="sources-trust">
        <div className="sources-trust-items">
          <div className="sources-trust-item">
            <div className="sources-trust-title">{t("sources.trust_provenance")}</div>
            <div className="sources-trust-desc">
              {t("sources.trust_provenance_tip")}
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">{t("sources.trust_sync")}</div>
            <div className="sources-trust-desc">
              {t("sources.trust_sync_tip")}
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">{t("sources.trust_dedup")}</div>
            <div className="sources-trust-desc">
              {t("sources.trust_dedup_tip")}
            </div>
          </div>
          <div className="sources-trust-item">
            <div className="sources-trust-title">{t("sources.trust_coverage")}</div>
            <div className="sources-trust-desc">
              {t("sources.trust_coverage_tip", { regions: regions.length, langs: languages.length })}
            </div>
          </div>
        </div>
      </div>

      <div className="sources-toolbar">
        <Input
          prefix={<SearchOutlined style={{ color: "#9a8e7a" }} />}
          placeholder={t("sources.search_placeholder")}
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
            { value: "all", label: t("sources.all_regions", { n: regions.length }) },
            ...regions.map((r) => ({ value: r, label: t(`region.${r}`, r) })),
          ]}
        />
        <Select
          value={langFilter}
          onChange={setLangFilter}
          style={{ width: 140 }}
          options={[
            { value: "all", label: t("sources.all_langs", { n: languages.length }) },
            ...languages.map((l) => ({ value: l, label: localizedLangName(normalizeLangCode(l), t) })),
          ]}
        />
        <Select
          value={fieldFilter}
          onChange={setFieldFilter}
          style={{ width: 150 }}
          options={[
            { value: "all", label: t("sources.all_fields", { n: researchFields.length }) },
            ...researchFields.map((f) => ({ value: f, label: t(`field.${f}`, FIELD_NAMES[f] || f) })),
          ]}
        />
        <button
          type="button"
          className={`sources-toggle-chip${fulltextOnly ? " is-active" : ""}`}
          onClick={() => setFulltextOnly(!fulltextOnly)}
          title={t("sources.fulltext_only_tip")}
        >
          {fulltextOnly ? "✓ " : ""}{t("sources.fulltext_only", { n: counters.local + counters.remote })}
        </button>
        <Select
          value={groupBy}
          onChange={setGroupBy}
          style={{ width: 130 }}
          options={[
            { value: "region", label: t("sources.group_by_region") },
            { value: "field", label: t("sources.group_by_field") },
            { value: "lang", label: t("sources.group_by_lang") },
          ]}
        />
      </div>

      <div className="sources-stats-bar">
        {t("sources.stats_showing")} <strong>{filtered.length}</strong> / {total} {t("sources.stats_unit")}
        {groupBy !== "region" && ` · ${t("sources.stats_groups", { n: grouped.length })}`}
        {groupBy !== "region" && (
          <span className="sources-stats-hint">{groupBy === "field" ? t("sources.stats_hint_field") : t("sources.stats_hint_lang")}</span>
        )}
      </div>

      {filtered.length === 0 ? (
        <Empty description={t("sources.no_match")} style={{ marginTop: 60 }} />
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
                  <span className="sources-group-name">{groupLabel(groupName)}</span>
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
                      ? t("sources.collapse_group", { group: groupLabel(groupName) })
                      : t("sources.expand_group", { n: items.length, remaining: items.length - GROUP_COLLAPSE_LIMIT })}
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
          aria-label={t("sources.back_to_top_aria")}
        >
          <VerticalAlignTopOutlined />
          <span>Top</span>
        </button>
      )}
    </div>
  );
}
