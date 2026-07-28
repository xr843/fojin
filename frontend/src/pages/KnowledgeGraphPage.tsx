import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Input, Select, Spin, Empty, Slider, Checkbox, Alert, Tooltip, Segmented } from "antd";
import {
  ApartmentOutlined,
  SearchOutlined,
  BarChartOutlined,
  CompassOutlined,
  DownOutlined,
  RightOutlined,
  UnorderedListOutlined,
  ProfileOutlined,
  FieldTimeOutlined,
} from "@ant-design/icons";
import ForceGraph, {
  TYPE_COLORS,
  TYPE_LABEL_KEYS,
  PREDICATE_LABEL_KEYS,
  PREDICATE_COLORS,
} from "../components/ForceGraph";
import EntityCard from "../components/EntityCard";
import KGTimeline from "../components/kg/KGTimeline";
import KGMentionsPanel from "../components/kg/KGMentionsPanel";
import { searchKGEntities, getKGEntity, getKGEntityGraph, getKGStats, getKGTimeline } from "../api/client";
import type { KGEntity, KGGraphNode, KGGraphLink } from "../api/client";
import "../styles/kg.css";

const { Search } = Input;

const ENTITY_TYPES = [
  { value: "", labelKey: "kg.all_types" },
  { value: "person", labelKey: "geo.type_person" },
  { value: "text", labelKey: "geo.type_text" },
  { value: "monastery", labelKey: "geo.type_temple" },
  { value: "school", labelKey: "geo.type_school" },
  { value: "place", labelKey: "geo.type_place" },
  { value: "concept", labelKey: "geo.type_concept" },
  { value: "dynasty", labelKey: "geo.type_dynasty" },
];

const ALL_PREDICATES = [
  { value: "translated", labelKey: "kg.pred_translated" },
  { value: "teacher_of", labelKey: "geo.lineage" },
  { value: "member_of_school", labelKey: "kg.pred_member_of_school" },
  { value: "cites", labelKey: "kg.pred_cites" },
  { value: "commentary_on", labelKey: "kg.pred_commentary_on" },
  { value: "active_in", labelKey: "kg.pred_active_in" },
  { value: "alt_translation", labelKey: "kg.pred_alt_translation" },
  { value: "parallel_text", labelKey: "kg.pred_parallel_text" },
  { value: "associated_with", labelKey: "kg.pred_associated_with" },
];

const ALL_PREDICATE_VALUES = ALL_PREDICATES.map((p) => p.value);

// One-line plain-language gloss for each relation type — surfaced as a
// tooltip on the filter checkboxes so terms like 「异译」「平行文本」
// don't gate casual users out of the graph.
const PREDICATE_DESC_KEYS: Record<string, string> = {
  translated: "kg.pred_desc_translated",
  teacher_of: "kg.pred_desc_teacher_of",
  member_of_school: "kg.pred_desc_member_of_school",
  cites: "kg.pred_desc_cites",
  commentary_on: "kg.pred_desc_commentary_on",
  active_in: "kg.pred_desc_active_in",
  alt_translation: "kg.pred_desc_alt_translation",
  parallel_text: "kg.pred_desc_parallel_text",
  associated_with: "kg.pred_desc_associated_with",
};

// Curated entry points for the "推荐探索" strip. Every name below was
// verified against the production /kg/entities API to resolve to at
// least one related entity, so a chip never lands on an empty graph.
// Item labels are entity names sent verbatim to the search API (and the
// graph data is Chinese-canonical), so they stay untranslated.
const CURATED_GROUPS: { titleKey: string; items: { label: string; type: string }[] }[] = [
  {
    titleKey: "kg.curated_masters",
    items: [
      { label: "玄奘", type: "person" }, // i18n-exempt
      { label: "鸠摩罗什", type: "person" }, // i18n-exempt
      { label: "不空", type: "person" }, // i18n-exempt
      { label: "义净", type: "person" }, // i18n-exempt
      { label: "法显", type: "person" }, // i18n-exempt
      { label: "龙树", type: "person" }, // i18n-exempt
      { label: "世亲", type: "person" }, // i18n-exempt
      { label: "无著", type: "person" }, // i18n-exempt
      { label: "法藏", type: "person" }, // i18n-exempt
      { label: "惠能", type: "person" }, // i18n-exempt
      { label: "智顗", type: "person" }, // i18n-exempt
      { label: "道宣", type: "person" }, // i18n-exempt
    ],
  },
  {
    titleKey: "kg.curated_schools",
    items: [
      { label: "天台宗", type: "school" }, // i18n-exempt
      { label: "华严宗", type: "school" }, // i18n-exempt
      { label: "法相宗", type: "school" }, // i18n-exempt
      { label: "三论宗", type: "school" }, // i18n-exempt
      { label: "律宗", type: "school" }, // i18n-exempt
      { label: "净土宗", type: "school" }, // i18n-exempt
      { label: "禅宗", type: "school" }, // i18n-exempt
      { label: "密宗", type: "school" }, // i18n-exempt
    ],
  },
  {
    titleKey: "kg.curated_concepts",
    items: [
      { label: "缘起", type: "concept" }, // i18n-exempt
      { label: "四圣谛", type: "concept" }, // i18n-exempt
      { label: "八正道", type: "concept" }, // i18n-exempt
      { label: "十二因缘", type: "concept" }, // i18n-exempt
      { label: "三法印", type: "concept" }, // i18n-exempt
      { label: "空性", type: "concept" }, // i18n-exempt
      { label: "中道", type: "concept" }, // i18n-exempt
      { label: "般若", type: "concept" }, // i18n-exempt
      { label: "涅槃", type: "concept" }, // i18n-exempt
      { label: "菩提", type: "concept" }, // i18n-exempt
      { label: "佛性", type: "concept" }, // i18n-exempt
      { label: "菩提心", type: "concept" }, // i18n-exempt
      { label: "唯识", type: "concept" }, // i18n-exempt
      { label: "如来藏", type: "concept" }, // i18n-exempt
    ],
  },
];

// 移动端 Tab 三选项
type MobileTab = "search" | "graph" | "detail";

// ── Graph merge helpers ──────────────────────────────────────────────────────
// Merge a freshly-fetched subgraph into the accumulated display set.
// Nodes are deduped by id; links are deduped by source+target+predicate.
function mergeGraphData(
  base: { nodes: KGGraphNode[]; links: KGGraphLink[] },
  incoming: { nodes: KGGraphNode[]; links: KGGraphLink[] },
): { nodes: KGGraphNode[]; links: KGGraphLink[] } {
  const nodeMap = new Map<number, KGGraphNode>(base.nodes.map((n) => [n.id as number, n]));
  for (const n of incoming.nodes) {
    if (!nodeMap.has(n.id as number)) nodeMap.set(n.id as number, n);
  }

  // Link key: smaller-id first so undirected duplicates also collapse.
  const linkKey = (l: KGGraphLink) => {
    const s = l.source as number;
    const t = l.target as number;
    return `${Math.min(s, t)}_${Math.max(s, t)}_${l.predicate}`;
  };
  const linkMap = new Map<string, KGGraphLink>(base.links.map((l) => [linkKey(l), l]));
  for (const l of incoming.links) {
    const k = linkKey(l);
    if (!linkMap.has(k)) linkMap.set(k, l);
  }

  return {
    nodes: [...nodeMap.values()],
    links: [...linkMap.values()],
  };
}

export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  // 响应式 isMobile：监听 resize，避免旋转/窗口变化后失效
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= 768
  );
  const handleResize = useCallback(() => {
    setIsMobile(window.innerWidth <= 768);
  }, []);
  useEffect(() => {
    window.addEventListener("resize", handleResize, { passive: true });
    return () => window.removeEventListener("resize", handleResize);
  }, [handleResize]);

  // 移动端当前激活的 Tab
  const [mobileTab, setMobileTab] = useState<MobileTab>("search");

  const [searchParams, setSearchParams] = useSearchParams();

  // Initialise all view state from the URL once, so a shared/bookmarked
  // /kg?q=…&id=…&depth=…&rels=… link restores the exact same view.
  const [query, setQuery] = useState(() => searchParams.get("q") || "玄奘"); // i18n-exempt — default search seed, sent to the API
  const [entityType, setEntityType] = useState(() => searchParams.get("type") || "");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(() => {
    const id = searchParams.get("id");
    return id && /^\d+$/.test(id) ? Number(id) : null;
  });
  const [graphDepth, setGraphDepth] = useState(() => {
    const d = Number(searchParams.get("depth"));
    return d >= 1 && d <= 4 ? d : isMobile ? 1 : 2;
  });
  const [selectedPredicates, setSelectedPredicates] = useState<string[]>(() => {
    const rels = searchParams.get("rels");
    if (rels) {
      const parsed = rels.split(",").filter((r) => ALL_PREDICATE_VALUES.includes(r));
      if (parsed.length) return parsed;
    }
    return ALL_PREDICATE_VALUES;
  });
  const [showStats, setShowStats] = useState(false);
  const [showTimeline, setShowTimeline] = useState(false);
  const [curatedOpen, setCuratedOpen] = useState(!isMobile);

  // ── Progressive expand state ──────────────────────────────────────────────
  // The graph displayed is an *accumulated* union of the initial fetch plus any
  // depth-1 expansions triggered by the user.  Reset whenever the root entity,
  // depth slider, or predicate filter changes.
  const [accumulatedGraph, setAccumulatedGraph] = useState<{
    nodes: KGGraphNode[];
    links: KGGraphLink[];
    truncated: boolean;
  } | null>(null);

  // Track which node ids have already been depth-1 fetched so we can draw
  // the expand-ring affordance on unexpanded nodes.
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<number>>(new Set());

  // Ref mirror of expandedNodeIds — kept in sync after every setState so
  // handleNodeExpand can read the latest value without being recreated.
  const expandedNodeIdsRef = useRef<Set<number>>(new Set());

  const queryClient = useQueryClient();

  const { data: kgStats } = useQuery({
    queryKey: ["kg-stats"],
    queryFn: getKGStats,
    staleTime: 60_000,
  });

  const { data: timelineData, isLoading: timelineLoading } = useQuery({
    queryKey: ["kg-timeline"],
    queryFn: () => getKGTimeline({ limit: 5000 }),
    staleTime: 300_000,
    enabled: showTimeline,
  });

  // 标记是否需要自动选中下一次搜索结果。初始为 true，除非 URL 已指定 id。
  const autoSelectRef = useRef(!searchParams.get("id"));

  // Mirror view state back into the URL (replace, so it doesn't spam
  // history). Only non-default values are written to keep links clean.
  useEffect(() => {
    const next = new URLSearchParams();
    if (query) next.set("q", query);
    if (entityType) next.set("type", entityType);
    if (selectedEntityId != null) next.set("id", String(selectedEntityId));
    if (graphDepth !== (isMobile ? 1 : 2)) next.set("depth", String(graphDepth));
    if (selectedPredicates.length !== ALL_PREDICATE_VALUES.length) {
      next.set("rels", selectedPredicates.join(","));
    }
    setSearchParams(next, { replace: true });
  }, [query, entityType, selectedEntityId, graphDepth, selectedPredicates, isMobile, setSearchParams]);

  const { data: searchResults, isLoading: searching } = useQuery({
    queryKey: ["kg-search", query, entityType],
    queryFn: () => searchKGEntities(query, entityType || undefined),
    enabled: query.length > 0,
  });

  // 搜索结果到达后自动选中第一条
  useEffect(() => {
    if (autoSelectRef.current && searchResults?.results.length) {
      autoSelectRef.current = false;
      setSelectedEntityId(searchResults.results[0].id);
    }
  }, [searchResults]);

  const { data: entityDetail } = useQuery({
    queryKey: ["kg-entity", selectedEntityId],
    queryFn: () => getKGEntity(selectedEntityId!),
    enabled: !!selectedEntityId,
  });

  const { data: graphData, isLoading: loadingGraph } = useQuery({
    queryKey: ["kg-graph", selectedEntityId, graphDepth, selectedPredicates],
    queryFn: () =>
      getKGEntityGraph(selectedEntityId!, graphDepth, 150, selectedPredicates),
    enabled: !!selectedEntityId,
  });

  // Single coherent effect: manages both clearing on root-key change and
  // seeding from graphData.  Tracks the "current root key" so we only seed
  // accumulatedGraph when graphData actually belongs to the active query —
  // this eliminates the two-effect race where the clear ran, then the old
  // graphData seeded stale data for one render before the refetch finished.
  const prevRootRef = useRef<string>("");
  // The root key that graphData currently corresponds to (react-query's
  // queryKey is [entity, depth, predicates], so we build the same key here).
  useEffect(() => {
    const key = `${selectedEntityId}_${graphDepth}_${selectedPredicates.join(",")}`;
    const rootChanged = key !== prevRootRef.current;

    if (rootChanged) {
      // Root changed: immediately wipe accumulated state.
      prevRootRef.current = key;
      setAccumulatedGraph(null);
      const empty = new Set<number>();
      setExpandedNodeIds(empty);
      expandedNodeIdsRef.current = empty;
    }

    // Seed from graphData only when it matches the *current* root key.
    // If the root just changed above, graphData is still from the old query
    // (react-query hasn't refetched yet) — we must not seed from it.
    if (!rootChanged && graphData) {
      setAccumulatedGraph({
        nodes: graphData.nodes,
        links: graphData.links,
        truncated: graphData.truncated,
      });
      // Mark the root entity as expanded (initial fetch covers its neighbourhood)
      const seeded = selectedEntityId != null ? new Set([selectedEntityId]) : new Set<number>();
      setExpandedNodeIds(seeded);
      expandedNodeIdsRef.current = seeded;
    }
  }, [selectedEntityId, graphDepth, selectedPredicates, graphData]);

  // ── Expand handler ─────────────────────────────────────────────────────────
  // Fetches the depth-1 neighbourhood of a node and merges it into the
  // accumulated display graph.  Uses queryClient.fetchQuery so the result is
  // cached and avoids re-fetching if the same node is double-clicked again.
  //
  // P2: reads expandedNodeIds from a ref (not the state) so this callback
  // is never recreated on each expand — stable identity prevents the d3
  // simulation from re-initialising on every expand.
  //
  // selectedPredicates is captured via a ref for the same reason: the
  // callback identity must not change when predicates change between expands.
  const selectedPredicatesRef = useRef<string[]>(selectedPredicates);
  useEffect(() => {
    selectedPredicatesRef.current = selectedPredicates;
  }, [selectedPredicates]);

  const handleNodeExpand = useCallback(
    async (node: { id: number }) => {
      if (expandedNodeIdsRef.current.has(node.id)) return; // already expanded

      const predicates = selectedPredicatesRef.current;
      try {
        const incoming = await queryClient.fetchQuery({
          queryKey: ["kg-graph-expand", node.id, predicates],
          queryFn: () => getKGEntityGraph(node.id, 1, 80, predicates),
          staleTime: 5 * 60_000,
        });

        setAccumulatedGraph((prev) => {
          if (!prev) return prev;
          const merged = mergeGraphData(prev, incoming);
          return { ...merged, truncated: prev.truncated || incoming.truncated };
        });

        setExpandedNodeIds((prev) => {
          const next = new Set([...prev, node.id]);
          expandedNodeIdsRef.current = next;
          return next;
        });
      } catch {
        // Silent fail — if the network request errors the graph stays as-is
      }
    },
    // queryClient is stable; refs are stable — no deps that would cause churn
    [queryClient],
  );

  const handleSearch = (value: string) => {
    setQuery(value.trim());
    setSelectedEntityId(null);
    autoSelectRef.current = true;  // 允许自动选中下次搜索结果
  };

  const handleEntitySelect = (entity: KGEntity) => {
    setSelectedEntityId(entity.id);
    // 移动端：选中搜索结果后自动切到图谱 Tab
    if (isMobile) setMobileTab("graph");
  };

  // Memoised so its identity is stable across KGPage re-renders. ForceGraph's
  // d3 effect lists onNodeClick in its deps; an inline function would be a new
  // reference every render and rebuild the entire force simulation (selectAll
  // remove + re-layout) on any unrelated state change. onNodeExpand is already
  // memoised for the same reason.
  const handleGraphNodeClick = useCallback(
    (node: { id: number }) => {
      setSelectedEntityId(node.id);
      // 移动端：点击图谱节点后自动切到详情 Tab
      if (isMobile) setMobileTab("detail");
    },
    [isMobile],
  );

  // 点击「推荐探索」入口：相当于一次带类型过滤的搜索
  const handleCurated = (label: string, type: string) => {
    setQuery(label);
    setEntityType(type);
    setSelectedEntityId(null);
    autoSelectRef.current = true;
    // 移动端：推荐探索触发搜索后切到搜索结果 Tab（让用户看到结果）
    if (isMobile) setMobileTab("search");
  };

  // Use accumulated graph for display; fall back to raw query result while the
  // first effect hasn't run yet (avoids a blank frame on initial load).
  const displayGraph = accumulatedGraph ?? graphData ?? null;

  const entityHasRelations = displayGraph && displayGraph.links.length > 0;

  // Compute used types/predicates for legend
  const usedNodeTypes = useMemo(
    () => [...new Set((displayGraph?.nodes || []).map((n) => n.entity_type))],
    [displayGraph]
  );
  const usedPredicates = useMemo(
    () => [...new Set((displayGraph?.links || []).map((l) => l.predicate))],
    [displayGraph]
  );

  // Graph height: fill viewport; on mobile use a shorter but still usable height
  const graphHeight = isMobile
    ? Math.max(300, typeof window !== "undefined" ? window.innerHeight * 0.5 : 350)
    : Math.max(500, typeof window !== "undefined" ? window.innerHeight - 260 : 600);

  return (
    <div className="kg-page">
      {/* Header */}
      <div className="kg-header">
        <ApartmentOutlined />
        <h3>{t("nav.kg")}</h3>
        {kgStats && (
          <Tooltip title={t("kg.view_stats")}>
            <span
              className="kg-stats-toggle"
              onClick={() => setShowStats(!showStats)}
            >
              <BarChartOutlined />
              <span className="kg-stats-summary">
                {t("kg.n_entities", { n: kgStats.total_entities.toLocaleString() })}{" / "}
                {t("kg.n_relations", { n: kgStats.total_relations.toLocaleString() })}
              </span>
            </span>
          </Tooltip>
        )}
        <Tooltip title={t("kg.timeline_title")}>
          <span
            className={`kg-timeline-toggle${showTimeline ? " active" : ""}`}
            onClick={() => setShowTimeline((v) => !v)}
          >
            <FieldTimeOutlined />
            <span>{t("kg.timeline_title")}</span>
          </span>
        </Tooltip>
      </div>
      {showTimeline && (
        <div className="kg-timeline-panel">
          <div className="kg-timeline-header">
            <span className="kg-timeline-title">
              <FieldTimeOutlined style={{ marginRight: 6 }} />
              {t("kg.timeline_title")}
            </span>
            <span style={{ fontSize: 11, color: "var(--fj-ink-muted)" }}>
              {t("kg.timeline_hint")}
            </span>
          </div>
          <div className="kg-timeline-body">
            <KGTimeline
              entities={timelineData?.entities ?? []}
              loading={timelineLoading}
              selectedEntityId={selectedEntityId}
              onEntityClick={(id) => setSelectedEntityId(id)}
            />
          </div>
        </div>
      )}
      {showStats && kgStats && (
        <div className="kg-stats-panel">
          <div className="kg-stats-group">
            <span className="kg-stats-group-title">{t("kg.entities_label")}</span>
            {Object.entries(kgStats.entities).map(([type, count]) => (
              <span key={type} className="kg-stats-item">
                <span className="kg-legend-dot" style={{ background: TYPE_COLORS[type] || "#888" }} />
                {TYPE_LABEL_KEYS[type] ? t(TYPE_LABEL_KEYS[type]) : type}
                <span className="kg-stats-count">{count.toLocaleString()}</span>
              </span>
            ))}
          </div>
          <div className="kg-stats-group">
            <span className="kg-stats-group-title">{t("kg.relations_label")}</span>
            {Object.entries(kgStats.relations).map(([pred, count]) => (
              <span key={pred} className="kg-stats-item">
                <span className="kg-legend-line" style={{ background: PREDICATE_COLORS[pred] || "#bbb5a6" }} />
                {PREDICATE_LABEL_KEYS[pred] ? t(PREDICATE_LABEL_KEYS[pred]) : pred}
                <span className="kg-stats-count">{count.toLocaleString()}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="kg-toolbar">
        <div className="kg-toolbar-main">
          <Search
            placeholder={isMobile ? t("kg.search_placeholder_short") : t("kg.search_placeholder")}
            allowClear
            enterButton={<SearchOutlined />}
            onSearch={handleSearch}
            style={{ width: isMobile ? "100%" : 340 }}
          />
          <Select
            style={{ width: 110 }}
            value={entityType}
            onChange={setEntityType}
            options={ENTITY_TYPES.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
          />
          <div className="kg-depth-control">
            <span className="kg-depth-label">{t("kg.depth")}</span>
            <Slider
              min={1}
              max={4}
              value={graphDepth}
              onChange={setGraphDepth}
              style={{ width: 80 }}
              tooltip={{ formatter: (v) => t("kg.depth_layers", { n: v }) }}
            />
          </div>
        </div>
        <div className="kg-predicate-bar">
          <span className="kg-predicate-label">{t("kg.relations_filter")}</span>
          <Checkbox.Group
            value={selectedPredicates}
            onChange={(vals) => setSelectedPredicates(vals as string[])}
            options={ALL_PREDICATES.map((p) => ({
              value: p.value,
              label: (
                <Tooltip title={t(PREDICATE_DESC_KEYS[p.value])}>
                  <span>{t(p.labelKey)}</span>
                </Tooltip>
              ),
            }))}
          />
        </div>
      </div>

      {/* 推荐探索 — curated entry points so a new user doesn't face a blank search box */}
      <div className="kg-curated">
        <div
          className="kg-curated-head"
          role="button"
          tabIndex={0}
          aria-expanded={curatedOpen}
          onClick={() => setCuratedOpen((o) => !o)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setCuratedOpen((o) => !o);
            }
          }}
        >
          <CompassOutlined />
          <span className="kg-curated-title">{t("kg.curated_title")}</span>
          {curatedOpen ? <DownOutlined /> : <RightOutlined />}
        </div>
        {curatedOpen && (
          <div className="kg-curated-body">
            {CURATED_GROUPS.map((g) => (
              <div key={g.titleKey} className="kg-curated-group">
                <span className="kg-curated-group-title">{t(g.titleKey)}</span>
                <div className="kg-curated-chips">
                  {g.items.map((item) => (
                    <button
                      key={item.label}
                      className={`kg-chip${query === item.label ? " active" : ""}`}
                      onClick={() => handleCurated(item.label, item.type)}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 移动端 Tab 切换器 — 仅在 ≤768px 显示 */}
      {isMobile && (
        <div className="kg-mobile-tabs">
          <Segmented
            block
            value={mobileTab}
            onChange={(v) => setMobileTab(v as MobileTab)}
            options={[
              {
                value: "search",
                label: (
                  <span className="kg-tab-label">
                    <UnorderedListOutlined />
                    <span>{t("kg.search_results")}</span>
                  </span>
                ),
              },
              {
                value: "graph",
                label: (
                  <span className="kg-tab-label">
                    <ApartmentOutlined />
                    <span>{t("kg.tab_graph")}</span>
                  </span>
                ),
              },
              {
                value: "detail",
                label: (
                  <span className="kg-tab-label">
                    <ProfileOutlined />
                    <span>{t("kg.tab_detail")}</span>
                  </span>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 搜索结果面板 */}
      {/* 桌面端：渲染在三栏内；移动端：仅 search Tab 激活时渲染 */}
      {/* 三栏布局（桌面端：三列并排；移动端：各 Tab 单独展示） */}
      <div className={`kg-layout${isMobile ? " kg-layout--mobile" : ""}`}>
        {/* Left: Search Results */}
        {(!isMobile || mobileTab === "search") && (
          <div className="kg-sidebar">
            <div className="kg-sidebar-card">
              <div className="kg-sidebar-title">
                {t("kg.search_results")}
                {searchResults && (
                  <span style={{ fontWeight: 400, color: "var(--fj-ink-muted)", marginLeft: 6, fontSize: 11 }}>
                    {t("kg.result_count", { n: searchResults.total })}
                  </span>
                )}
              </div>
              <div className="kg-sidebar-body">
                {searching ? (
                  <div style={{ padding: 32, textAlign: "center" }}>
                    <Spin />
                  </div>
                ) : !searchResults?.results.length ? (
                  <div style={{ padding: 32 }}>
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={query ? t("kg.no_entities_found") : t("kg.enter_keyword")}
                    />
                  </div>
                ) : (
                  searchResults.results.map((entity) => (
                    <div
                      key={entity.id}
                      className={`kg-result-item${selectedEntityId === entity.id ? " active" : ""}`}
                      onClick={() => handleEntitySelect(entity)}
                    >
                      <div className="kg-result-name">
                        {entity.name_zh}
                        {entity.name_sa && (
                          <span className="kg-result-sub">{entity.name_sa}</span>
                        )}
                      </div>
                      {entity.description && (
                        <div className="kg-result-desc">{entity.description}</div>
                      )}
                      <div className="kg-result-tags">
                        <span
                          className={`kg-type-tag kg-type-tag--${entity.entity_type}`}
                        >
                          {TYPE_LABEL_KEYS[entity.entity_type] ? t(TYPE_LABEL_KEYS[entity.entity_type]) : entity.entity_type}
                        </span>
                        {entity.relation_count != null && entity.relation_count > 0 && (
                          <span className="kg-result-degree">
                            {t("kg.n_relations", { n: entity.relation_count })}
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* Center: Graph */}
        {(!isMobile || mobileTab === "graph") && (
          <div className="kg-graph-area">
            {loadingGraph ? (
              <div className="kg-graph-empty">
                <Spin size="large" />
              </div>
            ) : selectedEntityId && !loadingGraph && !entityHasRelations && entityDetail ? (
              // Only fall through to the mentions panel after the graph
              // fetch has resolved with zero links — otherwise during a
              // loading transition we'd flash the mentions panel.
              <div className="kg-graph-empty-with-mentions">
                <KGMentionsPanel
                  entityId={selectedEntityId}
                  entityName={entityDetail.name_zh}
                  onEntityClick={(id) => {
                    setSelectedEntityId(id);
                    autoSelectRef.current = false;
                  }}
                />
              </div>
            ) : displayGraph?.nodes.length ? (
              <div className="kg-graph-container">
                {displayGraph.truncated && (
                  <div className="kg-truncated-bar">
                    <Alert
                      type="warning"
                      showIcon
                      message={
                        isMobile
                          ? t("kg.too_many_nodes", { n: displayGraph.nodes.length })
                          : t("kg.graph_truncated", {
                              nodes: displayGraph.nodes.length,
                              edges: displayGraph.links.length,
                            })
                      }
                      closable
                    />
                  </div>
                )}
                <ForceGraph
                  nodes={displayGraph.nodes}
                  links={displayGraph.links}
                  height={graphHeight}
                  onNodeClick={handleGraphNodeClick}
                  onNodeExpand={handleNodeExpand}
                  expandedNodeIds={expandedNodeIds}
                />
                {/* HTML Legend */}
                <div className="kg-legend">
                  <div className="kg-legend-section">
                    <span className="kg-legend-title">{t("kg.nodes_label")}</span>
                    {usedNodeTypes.map((type) => (
                      <span key={type} className="kg-legend-item">
                        <span
                          className="kg-legend-dot"
                          style={{ background: TYPE_COLORS[type] || "#888" }}
                        />
                        {TYPE_LABEL_KEYS[type] ? t(TYPE_LABEL_KEYS[type]) : type}
                      </span>
                    ))}
                  </div>
                  <div style={{ width: 1, height: 16, background: "#e8e0d4" }} />
                  <div className="kg-legend-section">
                    <span className="kg-legend-title">{t("kg.relations_label")}</span>
                    {usedPredicates.map((pred) => (
                      <span key={pred} className="kg-legend-item">
                        <span
                          className="kg-legend-line"
                          style={{
                            background: PREDICATE_COLORS[pred] || "#bbb5a6",
                          }}
                        />
                        {PREDICATE_LABEL_KEYS[pred] ? t(PREDICATE_LABEL_KEYS[pred]) : pred}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="kg-graph-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("kg.select_entity_hint")}
                />
              </div>
            )}
          </div>
        )}

        {/* Right: Entity Detail */}
        {(!isMobile || mobileTab === "detail") && (
          <div className="kg-detail-panel">
            {entityDetail ? (
              <div className="kg-detail-card">
                <EntityCard
                  entity={entityDetail}
                  onEntityClick={(id) => setSelectedEntityId(id)}
                />
              </div>
            ) : selectedEntityId ? (
              <div className="kg-detail-empty">
                <Spin />
              </div>
            ) : (
              <div className="kg-detail-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={t("kg.click_node_hint")}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
