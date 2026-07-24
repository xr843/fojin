import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Checkbox, Spin, Empty, Tooltip, Switch, AutoComplete } from "antd";
import { GlobalOutlined, BarChartOutlined, SearchOutlined } from "@ant-design/icons";
import { useTranslation } from "react-i18next";
import * as OpenCC from "opencc-js";
import DeckGLMap from "../components/kg-map/DeckGLMap";
import MapEntityPopup from "../components/kg-map/MapEntityPopup";
import { getKGGeoEntities, getKGLineageArcs } from "../api/client";
import type { KGGeoEntity } from "../api/client";
import "../styles/kg-map.css";

const ENTITY_TYPE_OPTIONS = [
  { value: "monastery", labelKey: "geo.type_temple" },
  { value: "place", labelKey: "geo.type_place" },
  { value: "person", labelKey: "geo.type_person" },
  { value: "school", labelKey: "geo.type_school" },
];

const s2t = OpenCC.Converter({ from: "cn", to: "tw" });
const t2s = OpenCC.Converter({ from: "tw", to: "cn" });

const TYPE_CSS_COLORS: Record<string, string> = {
  person: "#dc2626",
  monastery: "#22c55e",
  place: "#7c3aed",
  school: "#2563eb",
};

export default function KGMapPage() {
  const { t } = useTranslation();

  const [entityTypes, setEntityTypes] = useState<string[]>([
    "monastery",
    "place",
    "person",
  ]);
  const [showArcs, setShowArcs] = useState(false);
  const [selectedEntity, setSelectedEntity] = useState<KGGeoEntity | null>(null);
  const [chineseOnly, setChineseOnly] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [focusEntity, setFocusEntity] = useState<KGGeoEntity | null>(null);

  /* ---------- Queries ---------- */

  const { data: geoData, isLoading: geoLoading } = useQuery({
    queryKey: ["kg-geo"],
    queryFn: () => getKGGeoEntities({ limit: 80000 }),
    staleTime: 5 * 60_000,
  });

  const { data: arcData } = useQuery({
    queryKey: ["kg-lineage-arcs"],
    queryFn: () => getKGLineageArcs({ limit: 8000 }),
    staleTime: 5 * 60_000,
    enabled: showArcs,
  });

  /* ---------- Derived ---------- */

  const filteredEntities = useMemo(() => {
    const CJK_REGEX = /[\u4E00-\u9FFF\u3040-\u30FF]/;
    const HANGUL_REGEX = /[\uAC00-\uD7AF]/;
    const isChineseName = (name: string | null | undefined): boolean => {
      if (!name) return false;
      if (HANGUL_REGEX.test(name)) return false;
      return CJK_REGEX.test(name);
    };
    if (!chineseOnly) return geoData?.entities ?? [];
    return (geoData?.entities ?? []).filter((e) => isChineseName(e.name_zh));
  }, [geoData, chineseOnly]);

  const searchOptions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (q.length < 1) return [];
    const qSimp = t2s(q);
    const qTrad = s2t(q);
    const queries = Array.from(new Set([q, qSimp, qTrad]));
    // Split query into tokens for multi-part matching
    const tokenize = (s: string): string[][] => {
      const parts = s.split(/\s+/).filter(Boolean);
      if (parts.length > 1) return [parts];
      const combos: string[][] = [[s]];
      for (let i = 1; i < s.length; i++) {
        combos.push([s.slice(0, i), s.slice(i)]);
      }
      return combos;
    };
    const allTokenSets = queries.flatMap(tokenize);
    const pool = geoData?.entities ?? [];
    const matches: KGGeoEntity[] = [];
    for (const e of pool) {
      const zh = (e.name_zh || "").toLowerCase();
      const en = (e.name_en || "").toLowerCase();
      const addr = [e.province || "", e.city || "", e.district || ""].join("").toLowerCase();
      const full = zh + " " + en + " " + addr;
      const hit = allTokenSets.some((tokens) =>
        tokens.every((t) => full.includes(t)),
      );
      if (hit) {
        matches.push(e);
        if (matches.length >= 30) break;
      }
    }
    const addr = (e: KGGeoEntity) =>
      [e.province, e.city, e.district].filter(Boolean).join(" ");
    return matches.map((e) => ({
      value: String(e.id),
      label: (
        <div style={{ display: "flex", alignItems: "baseline", gap: 6, padding: "2px 0" }}>
          <SearchOutlined style={{ color: "#bbb", fontSize: 12, flexShrink: 0, position: "relative", top: 2 }} />
          <span style={{ fontWeight: 600, color: "#1677ff", flexShrink: 0 }}>{e.name_zh}</span>
          <span style={{ color: "var(--fj-text-secondary)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {addr(e) || e.name_en || ""}
          </span>
        </div>
      ),
      entity: e,
    }));
  }, [searchQuery, geoData]);

  const handleSearchSelect = (_value: string, option: { entity: KGGeoEntity }) => {
    const e = option.entity;
    setFocusEntity(e);
    setSelectedEntity(e);
    setSearchQuery(e.name_zh);
  };

  /* ---------- Handlers ---------- */

  const handleEntityClick = (entity: KGGeoEntity) => {
    setSelectedEntity(entity);
  };


  /* ---------- Render ---------- */

  return (
    <div className="kg-map-page">
      {/* Header */}
      <div className="kg-map-header">
        <GlobalOutlined />
        <h3>{t("geo.title")}</h3>
        {geoData && (
          <Tooltip
            title={t("geo.stats_tooltip")}
          >
            <span className="kg-map-stats" style={{ cursor: "help" }}>
              <BarChartOutlined />
              <span>
                {t("geo.marker_count", { n: filteredEntities.length.toLocaleString() })}
                {chineseOnly && <span className="kg-map-stats-filter"> · {t("geo.chinese_only")}</span>}
              </span>
            </span>
          </Tooltip>
        )}
      </div>

      {/* Toolbar */}
      <div className="kg-map-toolbar">
        <div className="kg-map-toolbar-row">
          <span className="kg-map-filter-label">{t("geo.entity_types")}:</span>
          <Checkbox.Group
            value={entityTypes}
            onChange={(vals) => setEntityTypes(vals as string[])}
            options={ENTITY_TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
          />
          <Checkbox
            checked={showArcs}
            onChange={(e) => setShowArcs(e.target.checked)}
          >
            {t("geo.type_lineage")}
          </Checkbox>
          <span className="kg-map-filter-label">{t("geo.chinese_only")}:</span>
          <Switch
            size="small"
            checked={chineseOnly}
            onChange={setChineseOnly}
          />
          <AutoComplete
            value={searchQuery}
            options={searchOptions}
            onSearch={setSearchQuery}
            onChange={setSearchQuery}
            onSelect={handleSearchSelect}
            placeholder={t("geo.search_placeholder")}
            allowClear
            style={{ width: 280, marginLeft: "auto" }}
            popupMatchSelectWidth={380}
            suffixIcon={<SearchOutlined style={{ color: "var(--fj-text-secondary)" }} />}
          />
        </div>
      </div>

      {/* Map Container */}
      <div className="kg-map-container">
        {geoLoading ? (
          <div className="kg-map-loading">
            <Spin size="large" />
          </div>
        ) : !geoData?.entities.length ? (
          <div className="kg-map-loading">
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t("geo.no_data")}
            />
          </div>
        ) : (
          <>
            <DeckGLMap
              geoEntities={filteredEntities}
              lineageArcs={arcData?.arcs ?? []}
              showArcs={showArcs}
              currentYear={null}
              entityTypeFilter={entityTypes}
              onEntityClick={handleEntityClick}
              focusEntity={focusEntity}
            />

            <div className="kg-map-legend">
              {ENTITY_TYPE_OPTIONS.filter((o) => entityTypes.includes(o.value)).map((o) => (
                <span key={o.value} className="kg-map-legend-item">
                  <span className="kg-legend-dot" style={{ background: TYPE_CSS_COLORS[o.value] || "#888" }} />
                  {t(o.labelKey)}
                </span>
              ))}
              {showArcs && (
                <span className="kg-map-legend-item">
                  <span className="kg-legend-line" style={{ background: "#eab308" }} />
                  {t("geo.lineage")}
                </span>
              )}
            </div>

            {/* Time filter hidden: only 0.7% of entities have year data (see issue tracker) */}

            {selectedEntity && (
              <MapEntityPopup
                entity={selectedEntity}
                onClose={() => setSelectedEntity(null)}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
