import { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
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
  TYPE_LABELS,
  PREDICATE_LABELS,
  PREDICATE_COLORS,
} from "../components/ForceGraph";
import EntityCard from "../components/EntityCard";
import KGTimeline from "../components/kg/KGTimeline";
import KGPathQuery from "../components/kg/KGPathQuery";
import { searchKGEntities, getKGEntity, getKGEntityGraph, getKGStats, getKGTimeline } from "../api/client";
import type { KGEntity, KGGraphNode, KGGraphLink } from "../api/client";
import "../styles/kg.css";

const { Search } = Input;

const ENTITY_TYPES = [
  { value: "", label: "全部类型" },
  { value: "person", label: "人物" },
  { value: "text", label: "典籍" },
  { value: "monastery", label: "寺院" },
  { value: "school", label: "宗派" },
  { value: "place", label: "地点" },
  { value: "concept", label: "概念" },
  { value: "dynasty", label: "朝代" },
];

const ALL_PREDICATES = [
  { value: "translated", label: "翻译" },
  { value: "teacher_of", label: "师承" },
  { value: "member_of_school", label: "宗派" },
  { value: "cites", label: "引用" },
  { value: "commentary_on", label: "注疏" },
  { value: "active_in", label: "所处" },
  { value: "alt_translation", label: "异译" },
  { value: "parallel_text", label: "平行文本" },
  { value: "associated_with", label: "相关" },
];

const ALL_PREDICATE_VALUES = ALL_PREDICATES.map((p) => p.value);

// One-line plain-language gloss for each relation type — surfaced as a
// tooltip on the filter checkboxes so terms like 「异译」「平行文本」
// don't gate casual users out of the graph.
const PREDICATE_DESC: Record<string, string> = {
  translated: "某人翻译了某部典籍",
  teacher_of: "师徒之间的传法承继关系",
  member_of_school: "人物所归属的宗派",
  cites: "一部典籍引用了另一部典籍",
  commentary_on: "对某部典籍的注释或疏解",
  active_in: "人物活跃的朝代或地域",
  alt_translation: "同一原典的不同译本（异译）",
  parallel_text: "跨语言或跨藏经对应的平行文本",
  associated_with: "其它相关联系",
};

const TYPE_LABEL_MAP: Record<string, string> = {
  person: "人物",
  text: "典籍",
  monastery: "寺院",
  school: "宗派",
  place: "地点",
  concept: "概念",
  dynasty: "朝代",
};

// Curated entry points for the "推荐探索" strip. Every name below was
// verified against the production /kg/entities API to resolve to at
// least one related entity, so a chip never lands on an empty graph.
const CURATED_GROUPS: { title: string; items: { label: string; type: string }[] }[] = [
  {
    title: "高僧大德",
    items: [
      { label: "玄奘", type: "person" },
      { label: "鸠摩罗什", type: "person" },
      { label: "不空", type: "person" },
      { label: "义净", type: "person" },
      { label: "法显", type: "person" },
      { label: "龙树", type: "person" },
      { label: "世亲", type: "person" },
      { label: "无著", type: "person" },
      { label: "法藏", type: "person" },
      { label: "惠能", type: "person" },
      { label: "智顗", type: "person" },
      { label: "道宣", type: "person" },
    ],
  },
  {
    title: "八大宗派",
    items: [
      { label: "天台宗", type: "school" },
      { label: "华严宗", type: "school" },
      { label: "法相宗", type: "school" },
      { label: "三论宗", type: "school" },
      { label: "律宗", type: "school" },
      { label: "净土宗", type: "school" },
      { label: "禅宗", type: "school" },
      { label: "密宗", type: "school" },
    ],
  },
  {
    title: "核心概念",
    items: [
      { label: "缘起", type: "concept" },
      { label: "四圣谛", type: "concept" },
      { label: "八正道", type: "concept" },
      { label: "十二因缘", type: "concept" },
      { label: "三法印", type: "concept" },
      { label: "空性", type: "concept" },
      { label: "中道", type: "concept" },
      { label: "般若", type: "concept" },
      { label: "涅槃", type: "concept" },
      { label: "菩提", type: "concept" },
      { label: "佛性", type: "concept" },
      { label: "菩提心", type: "concept" },
      { label: "唯识", type: "concept" },
      { label: "如来藏", type: "concept" },
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
  const [query, setQuery] = useState(() => searchParams.get("q") || "玄奘");
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
    queryFn: () => getKGTimeline({ limit: 1000 }),
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

  const handleGraphNodeClick = (node: { id: number }) => {
    setSelectedEntityId(node.id);
    // 移动端：点击图谱节点后自动切到详情 Tab
    if (isMobile) setMobileTab("detail");
  };

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
        <h3>知识图谱</h3>
        {kgStats && (
          <Tooltip title="查看统计">
            <span
              className="kg-stats-toggle"
              onClick={() => setShowStats(!showStats)}
            >
              <BarChartOutlined />
              <span className="kg-stats-summary">
                {kgStats.total_entities.toLocaleString()} 实体 / {kgStats.total_relations.toLocaleString()} 关系
              </span>
            </span>
          </Tooltip>
        )}
        <Tooltip title="时间轴视图">
          <span
            className={`kg-timeline-toggle${showTimeline ? " active" : ""}`}
            onClick={() => setShowTimeline((v) => !v)}
          >
            <FieldTimeOutlined />
            <span>时间轴</span>
          </span>
        </Tooltip>
      </div>
      {showTimeline && (
        <div className="kg-timeline-panel">
          <div className="kg-timeline-header">
            <span className="kg-timeline-title">
              <FieldTimeOutlined style={{ marginRight: 6 }} />
              历史时间轴
            </span>
            <span style={{ fontSize: 11, color: "#9a8e7a" }}>
              点击实体可查看详情
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
            <span className="kg-stats-group-title">实体</span>
            {Object.entries(kgStats.entities).map(([type, count]) => (
              <span key={type} className="kg-stats-item">
                <span className="kg-legend-dot" style={{ background: TYPE_COLORS[type] || "#888" }} />
                {TYPE_LABEL_MAP[type] || type}
                <span className="kg-stats-count">{count.toLocaleString()}</span>
              </span>
            ))}
          </div>
          <div className="kg-stats-group">
            <span className="kg-stats-group-title">关系</span>
            {Object.entries(kgStats.relations).map(([pred, count]) => (
              <span key={pred} className="kg-stats-item">
                <span className="kg-legend-line" style={{ background: PREDICATE_COLORS[pred] || "#bbb5a6" }} />
                {PREDICATE_LABELS[pred] || pred}
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
            placeholder={isMobile ? "搜索实体…" : "搜索实体（人物、典籍、宗派…）"}
            allowClear
            enterButton={<SearchOutlined />}
            onSearch={handleSearch}
            style={{ width: isMobile ? "100%" : 340 }}
          />
          <Select
            style={{ width: 110 }}
            value={entityType}
            onChange={setEntityType}
            options={ENTITY_TYPES}
          />
          <div className="kg-depth-control">
            <span className="kg-depth-label">深度</span>
            <Slider
              min={1}
              max={4}
              value={graphDepth}
              onChange={setGraphDepth}
              style={{ width: 80 }}
              tooltip={{ formatter: (v) => `${v} 层` }}
            />
          </div>
        </div>
        <div className="kg-predicate-bar">
          <span className="kg-predicate-label">关系:</span>
          <Checkbox.Group
            value={selectedPredicates}
            onChange={(vals) => setSelectedPredicates(vals as string[])}
            options={ALL_PREDICATES.map((p) => ({
              value: p.value,
              label: (
                <Tooltip title={PREDICATE_DESC[p.value]}>
                  <span>{p.label}</span>
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
          <span className="kg-curated-title">推荐探索</span>
          {curatedOpen ? <DownOutlined /> : <RightOutlined />}
        </div>
        {curatedOpen && (
          <div className="kg-curated-body">
            {CURATED_GROUPS.map((g) => (
              <div key={g.title} className="kg-curated-group">
                <span className="kg-curated-group-title">{g.title}</span>
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
                    <span>搜索结果</span>
                  </span>
                ),
              },
              {
                value: "graph",
                label: (
                  <span className="kg-tab-label">
                    <ApartmentOutlined />
                    <span>图谱</span>
                  </span>
                ),
              },
              {
                value: "detail",
                label: (
                  <span className="kg-tab-label">
                    <ProfileOutlined />
                    <span>详情</span>
                  </span>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 路径查询面板 — 当前选中实体作为起点 */}
      <KGPathQuery
        fromEntity={entityDetail ?? null}
        onNodeClick={handleGraphNodeClick}
      />

      {/* 搜索结果面板 */}
      {/* 桌面端：渲染在三栏内；移动端：仅 search Tab 激活时渲染 */}
      {/* 三栏布局（桌面端：三列并排；移动端：各 Tab 单独展示） */}
      <div className={`kg-layout${isMobile ? " kg-layout--mobile" : ""}`}>
        {/* Left: Search Results */}
        {(!isMobile || mobileTab === "search") && (
          <div className="kg-sidebar">
            <div className="kg-sidebar-card">
              <div className="kg-sidebar-title">
                搜索结果
                {searchResults && (
                  <span style={{ fontWeight: 400, color: "#9a8e7a", marginLeft: 6, fontSize: 11 }}>
                    {searchResults.total} 条
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
                      description={query ? "未找到相关实体" : "输入关键词搜索"}
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
                          {TYPE_LABEL_MAP[entity.entity_type] || entity.entity_type}
                        </span>
                        {entity.relation_count != null && entity.relation_count > 0 && (
                          <span className="kg-result-degree">
                            {entity.relation_count} 关系
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
            ) : selectedEntityId && !entityHasRelations ? (
              <div className="kg-graph-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="该实体尚未与其他实体建立关系"
                >
                  {entityDetail && (
                    <p style={{ color: "#9a8e7a", fontSize: 12, margin: 0 }}>
                      「{entityDetail.name_zh}」暂无图谱关系数据
                    </p>
                  )}
                </Empty>
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
                          ? `节点过多（${displayGraph.nodes.length}），请减小深度或按需展开`
                          : `图谱节点超出（${displayGraph.nodes.length} 节点 / ${displayGraph.links.length} 边），可减小深度、过滤关系类型，或双击节点按需展开`
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
                    <span className="kg-legend-title">节点</span>
                    {usedNodeTypes.map((type) => (
                      <span key={type} className="kg-legend-item">
                        <span
                          className="kg-legend-dot"
                          style={{ background: TYPE_COLORS[type] || "#888" }}
                        />
                        {TYPE_LABELS[type] || type}
                      </span>
                    ))}
                  </div>
                  <div style={{ width: 1, height: 16, background: "#e8e0d4" }} />
                  <div className="kg-legend-section">
                    <span className="kg-legend-title">关系</span>
                    {usedPredicates.map((pred) => (
                      <span key={pred} className="kg-legend-item">
                        <span
                          className="kg-legend-line"
                          style={{
                            background: PREDICATE_COLORS[pred] || "#bbb5a6",
                          }}
                        />
                        {PREDICATE_LABELS[pred] || pred}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="kg-graph-empty">
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="选择实体查看知识图谱"
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
                  description="点击节点查看详情"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
