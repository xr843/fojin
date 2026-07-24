import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { useTranslation } from "react-i18next";
import { CompressOutlined } from "@ant-design/icons";
import { escapeHtml } from "../utils/sanitize";

interface GraphNode {
  id: number;
  name: string;
  entity_type: string;
  description?: string | null;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
}

interface GraphLink {
  source: number | GraphNode;
  target: number | GraphNode;
  predicate: string;
  confidence: number;
  provenance?: string | null;
  evidence?: string | null;
}

interface SimNode extends GraphNode, d3.SimulationNodeDatum {
  _clickTimer?: number | null;
}

type SimLinkEndpoint = string | number | SimNode;

interface SimLink
  extends Omit<GraphLink, "source" | "target">,
    d3.SimulationLinkDatum<SimNode> {
  source: SimLinkEndpoint;
  target: SimLinkEndpoint;
}

interface ForceGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  width?: number;
  height?: number;
  onNodeClick?: (node: GraphNode) => void;
  /** Called when the user double-clicks a node to progressively expand it. */
  onNodeExpand?: (node: GraphNode) => void;
  /** Set of node ids that have already been expanded (depth-1 fetched). */
  expandedNodeIds?: Set<number>;
}

/* ── 古典配色 ── */
const TYPE_COLORS: Record<string, string> = {
  person:    "#c75450",  // 朱砂
  text:      "#4a7c9b",  // 靛青
  monastery: "#6b8e5b",  // 松绿
  school:    "#7b5ea7",  // 紫藤
  place:     "#c08b3e",  // 赭石
  concept:   "#3d8a8a",  // 青碧
  dynasty:   "#b35c8a",  // 洋紫
};

/* i18n key maps — translated at render time via t(); shared by the KG
   surfaces (graph legend, stats panel, mentions panel, entity cards). */
const TYPE_LABEL_KEYS: Record<string, string> = {
  person: "geo.type_person",
  text: "geo.type_text",
  monastery: "geo.type_temple",
  school: "geo.type_school",
  place: "geo.type_place",
  concept: "geo.type_concept",
  dynasty: "geo.type_dynasty",
};

const PREDICATE_LABEL_KEYS: Record<string, string> = {
  translated: "kg.pred_translated",
  active_in: "kg.pred_active_in",
  alt_translation: "kg.pred_alt_translation",
  parallel_text: "kg.pred_parallel_text",
  member_of_school: "kg.pred_member_of_school",
  teacher_of: "geo.lineage",
  cites: "kg.pred_cites",
  commentary_on: "kg.pred_commentary_on",
  associated_with: "kg.pred_associated_with",
};

const PREDICATE_COLORS: Record<string, string> = {
  translated:       "#4a7c9b",
  active_in:        "#b35c8a",
  alt_translation:  "#3d8a8a",
  parallel_text:    "#6b8e5b",
  member_of_school: "#7b5ea7",
  teacher_of:       "#c08b3e",
  cites:            "#bbb5a6",
  commentary_on:    "#c75450",
  associated_with:  "#5b8c6b",  // 翡翠
};

export { TYPE_COLORS, TYPE_LABEL_KEYS, PREDICATE_LABEL_KEYS, PREDICATE_COLORS };

export default function ForceGraph({
  nodes,
  links,
  width: propWidth,
  height = 600,
  onNodeClick,
  onNodeExpand,
  expandedNodeIds,
}: ForceGraphProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  // Holds the current graph's fit-to-view function. The 适应窗口 button
  // (rendered in JSX, outside the d3 effect) calls it on demand.
  const fitToViewRef = useRef<(() => void) | null>(null);
  const [containerWidth, setContainerWidth] = useState(propWidth || 800);

  // Responsive width via ResizeObserver
  useEffect(() => {
    if (propWidth) {
      setContainerWidth(propWidth);
      return;
    }
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    observer.observe(el);
    setContainerWidth(el.clientWidth);
    return () => observer.disconnect();
  }, [propWidth]);

  const width = containerWidth;

  // Tooltip helper
  const showTooltip = useCallback(
    (html: string, x: number, y: number) => {
      const tip = tooltipRef.current;
      if (!tip) return;
      tip.innerHTML = html;
      tip.style.opacity = "1";
      tip.style.left = `${x + 12}px`;
      tip.style.top = `${y - 8}px`;
    },
    []
  );
  const hideTooltip = useCallback(() => {
    const tip = tooltipRef.current;
    if (tip) tip.style.opacity = "0";
  }, []);

  useEffect(() => {
    if (!svgRef.current || !nodes.length) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Defs: arrow markers
    const defs = svg.append("defs");

    // Create arrow marker per predicate color
    const usedPredicates = [...new Set(links.map((l) => l.predicate))];
    usedPredicates.forEach((pred) => {
      const color = PREDICATE_COLORS[pred] || "#bbb5a6";
      defs
        .append("marker")
        .attr("id", `arrow-${pred}`)
        .attr("viewBox", "0 0 10 6")
        // Lines are shortened to the target node's edge in the tick
        // handler, so the arrow tip should sit at the line endpoint.
        .attr("refX", 10)
        .attr("refY", 3)
        .attr("markerWidth", 8)
        .attr("markerHeight", 5)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,0 L10,3 L0,6 Z")
        .attr("fill", color)
        .attr("opacity", 0.5);
    });

    const g = svg.append("g");

    // Zoom
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 6])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // Clone data to avoid mutation
    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }));
    const simNodeById = new Map(simNodes.map((n) => [n.id, n]));
    const endpointKey = (endpoint: number | GraphNode) =>
      typeof endpoint === "object" ? String(endpoint.id) : String(endpoint);
    const endpointId = (endpoint: SimLinkEndpoint) =>
      typeof endpoint === "object" ? endpoint.id : Number(endpoint);
    const endpointNode = (endpoint: SimLinkEndpoint): SimNode | undefined =>
      typeof endpoint === "object" ? endpoint : simNodeById.get(Number(endpoint));
    const simLinks: SimLink[] = links.map((l) => ({
      ...l,
      source: endpointKey(l.source),
      target: endpointKey(l.target),
    }));

    // ── Node degree → radius ──
    // A node's degree (how many relations touch it) is its visual
    // importance. Sizing the circle by degree makes hubs — the
    // translators, the schools — pop out of a busy graph instead of
    // every node looking equally (un)important. Square-root scale so a
    // 16× busier node isn't 16× wider.
    const degree = new Map<number, number>();
    simLinks.forEach((l) => {
      const sid = endpointId(l.source);
      const tid = endpointId(l.target);
      degree.set(sid, (degree.get(sid) || 0) + 1);
      degree.set(tid, (degree.get(tid) || 0) + 1);
    });
    const maxDegree = Math.max(1, ...simNodes.map((n) => degree.get(n.id) || 0));
    const radiusScale = d3
      .scaleSqrt()
      .domain([0, maxDegree])
      .range([12, 30])
      .clamp(true);
    const nodeRadius = (d: SimNode) => radiusScale(degree.get(d.id) || 0);

    // Adaptive forces based on node count
    const nodeCount = simNodes.length;
    const chargeStrength = nodeCount > 100 ? -200 : nodeCount > 50 ? -280 : -350;
    const linkDist = nodeCount > 100 ? 90 : nodeCount > 50 ? 110 : 140;

    const simulation = d3
      .forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(simLinks)
          .id((d) => String(d.id))
          .distance(linkDist)
      )
      .force("charge", d3.forceManyBody<SimNode>().strength(chargeStrength))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide<SimNode>().radius((d) => nodeRadius(d) + 8))
      .force("x", d3.forceX<SimNode>(width / 2).strength(0.03))
      .force("y", d3.forceY<SimNode>(height / 2).strength(0.03));

    // ── Links ──
    const linkGroup = g.append("g").attr("class", "links");
    const link = linkGroup
      .selectAll<SVGLineElement, SimLink>("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", (d) => PREDICATE_COLORS[d.predicate] || "#bbb5a6")
      .attr("stroke-opacity", 0.35)
      .attr("stroke-width", (d) => {
        // cites edges thinner to reduce visual noise
        if (d.predicate === "cites") return 0.8;
        return Math.max(1, Math.min(d.confidence * 2, 2.5));
      })
      .attr("marker-end", (d) =>
        d.predicate !== "cites" ? `url(#arrow-${d.predicate})` : null
      );

    // Edge hover: show tooltip
    link
      .on("mouseover", function (this: SVGLineElement, event: MouseEvent, d) {
        d3.select(this)
          .attr("stroke-opacity", 0.9)
          .attr("stroke-width", 3);
        const label = PREDICATE_LABEL_KEYS[d.predicate]
          ? t(PREDICATE_LABEL_KEYS[d.predicate])
          : d.predicate;
        const parts = [`<strong>${escapeHtml(label)}</strong>`];
        if (d.provenance)
          parts.push(`<span style="color:var(--fj-ink-muted)">${escapeHtml(t("kg.tooltip_source"))}: ${escapeHtml(d.provenance)}</span>`);
        if (d.evidence)
          parts.push(`<span style="color:var(--fj-ink-muted)">${escapeHtml(t("kg.tooltip_evidence"))}: ${escapeHtml(d.evidence)}</span>`);
        if (d.confidence < 1)
          parts.push(`<span style="color:var(--fj-gold)">${escapeHtml(t("kg.tooltip_confidence"))}: ${d.confidence}</span>`);
        showTooltip(parts.join("<br>"), event.offsetX, event.offsetY);
      })
      .on("mouseout", function (this: SVGLineElement, _event: MouseEvent, d) {
        d3.select(this)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", d.predicate === "cites" ? 0.8 : Math.max(1, Math.min(d.confidence * 2, 2.5)));
        hideTooltip();
      });

    // ── Nodes ──
    const nodeGroup = g.append("g").attr("class", "nodes");
    const node = nodeGroup
      .selectAll<SVGGElement, SimNode>("g")
      .data(simNodes)
      .join("g")
      .style("cursor", "pointer")
      .call(
        d3
          .drag<SVGGElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    // ── Expand ring: a faint outer circle on nodes that haven't yet been
    // depth-1 expanded.  Gives the user a cue that double-clicking will
    // reveal more connections without cluttering the layout.
    node
      .append("circle")
      .attr("class", "expand-ring")
      .attr("r", (d) => nodeRadius(d) + 5)
      .attr("fill", "none")
      .attr("stroke", (d) =>
        expandedNodeIds?.has(d.id) ? "none" : (TYPE_COLORS[d.entity_type] || "var(--fj-ink-muted)")
      )
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", (d) => (expandedNodeIds?.has(d.id) ? 0 : 0.35))
      .attr("stroke-dasharray", "3 3")
      .attr("pointer-events", "none");

    // Node circle with subtle shadow — radius scaled by degree
    node
      .append("circle")
      .attr("r", nodeRadius)
      .attr("fill", (d) => TYPE_COLORS[d.entity_type] || "var(--fj-ink-muted)")
      .attr("stroke", "var(--fj-surface)")
      .attr("stroke-width", 2)
      .attr("filter", "drop-shadow(0 1px 2px rgba(0,0,0,0.12))");

    // Short label inside node (1-2 chars), font scaled with radius
    node
      .append("text")
      .text((d) => {
        const n = d.name;
        return n.length <= 2 ? n : n.slice(0, 1);
      })
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", (d) => Math.max(10, nodeRadius(d) * 0.62))
      .attr("font-weight", 600)
      .attr("fill", "#fff") /* count label sits inside a saturated colored node — stays white in both themes */
      .attr("pointer-events", "none");

    // Full name label below node — offset by the node's own radius
    node
      .append("text")
      .text((d) =>
        d.name.length > 6 ? d.name.slice(0, 6) + "…" : d.name
      )
      .attr("text-anchor", "middle")
      .attr("dy", (d) => nodeRadius(d) + 14)
      .attr("font-size", 11)
      .attr("font-family", '"Noto Serif SC", serif')
      .attr("fill", "var(--fj-ink)")
      .attr("pointer-events", "none");

    // ── Hover highlight: dim everything except neighbors ──
    node
      .on("mouseover", function (_event: MouseEvent, d) {
        const connectedIds = new Set<number>();
        connectedIds.add(d.id);
        simLinks.forEach((l) => {
          const sid = endpointId(l.source);
          const tid = endpointId(l.target);
          if (sid === d.id) connectedIds.add(tid);
          if (tid === d.id) connectedIds.add(sid);
        });

        // Dim non-connected nodes
        node.transition().duration(150).style("opacity", (n) =>
          connectedIds.has(n.id) ? 1 : 0.15
        );
        // Highlight connected edges, dim others
        link.transition().duration(150)
          .attr("stroke-opacity", (l) => {
            const sid = endpointId(l.source);
            const tid = endpointId(l.target);
            return sid === d.id || tid === d.id ? 0.8 : 0.05;
          })
          .attr("stroke-width", (l) => {
            const sid = endpointId(l.source);
            const tid = endpointId(l.target);
            return sid === d.id || tid === d.id ? 2.5 : 0.5;
          });

        // Tooltip — include expand hint if node hasn't been expanded yet
        const typeLabel = TYPE_LABEL_KEYS[d.entity_type]
          ? t(TYPE_LABEL_KEYS[d.entity_type])
          : d.entity_type;
        let html = `<strong>${escapeHtml(d.name)}</strong> <span style="color:var(--fj-ink-muted)">${escapeHtml(typeLabel)}</span>`;
        if (d.description) html += `<br><span style="color:var(--fj-ink-muted);font-size:11px">${escapeHtml(d.description)}</span>`;
        if (onNodeExpand && !expandedNodeIds?.has(d.id)) {
          html += `<br><span style="color:var(--fj-gold);font-size:10px">${escapeHtml(t("kg.dblclick_expand"))}</span>`;
        }
        showTooltip(html, _event.offsetX, _event.offsetY);
      })
      .on("mouseout", function () {
        node.transition().duration(200).style("opacity", 1);
        link.transition().duration(200)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", (l) =>
            l.predicate === "cites" ? 0.8 : Math.max(1, Math.min(l.confidence * 2, 2.5))
          );
        hideTooltip();
      })
      .on("click", (_event: MouseEvent, d) => {
        // Debounce: wait 250 ms so a double-click can cancel before we
        // treat this as a single-click re-root.  The timer is stored on
        // the node datum itself so each node has its own pending timer.
        if (d._clickTimer != null) return; // already waiting — this is the 2nd click of a dblclick, ignore
        d._clickTimer = window.setTimeout(() => {
          d._clickTimer = null;
          if (onNodeClick) onNodeClick(d);
        }, 250);
      })
      .on("dblclick", (event: MouseEvent, d) => {
        // Cancel the pending single-click timer so onNodeClick is NOT called.
        if (d._clickTimer != null) {
          clearTimeout(d._clickTimer);
          d._clickTimer = null;
        }
        // Prevent the zoom double-click handler from triggering on the node.
        event.stopPropagation();
        if (onNodeExpand) onNodeExpand(d);
      });

    // Trim a link to the node boundaries so it starts/ends at the
    // circle edge rather than the centre — with degree-scaled radii a
    // fixed offset would leave arrows floating or buried.
    const trimLink = (d: SimLink) => {
      const source = endpointNode(d.source);
      const target = endpointNode(d.target);
      if (!source || !target) return null;
      const sx = source.x ?? width / 2, sy = source.y ?? height / 2;
      const tx = target.x ?? width / 2, ty = target.y ?? height / 2;
      const dx = tx - sx, dy = ty - sy;
      const dist = Math.hypot(dx, dy) || 1;
      const sr = nodeRadius(source) + 2;
      const tr = nodeRadius(target) + 5; // extra gap for the arrowhead
      return {
        x1: sx + (dx / dist) * sr,
        y1: sy + (dy / dist) * sr,
        x2: tx - (dx / dist) * tr,
        y2: ty - (dy / dist) * tr,
      };
    };

    // ── Tick ──
    simulation.on("tick", () => {
      link.each(function (this: SVGLineElement, d) {
        const e = trimLink(d);
        if (!e) return;
        d3.select(this)
          .attr("x1", e.x1)
          .attr("y1", e.y1)
          .attr("x2", e.x2)
          .attr("y2", e.y2);
      });
      node.attr("transform", (d) => `translate(${d.x ?? width / 2},${d.y ?? height / 2})`);
    });

    // ── Fit-to-view (manual, on-demand) ──
    // This is deliberately NOT automatic. An earlier version fitted on
    // simulation "end" — but that fired several seconds after load and
    // jarringly shrank large graphs to an unreadable size, which users
    // mistook for a glitch. Now the 适应窗口 button triggers it when the
    // user actually wants the whole graph in view.
    const fitToView = () => {
      if (!simNodes.length) return;
      // Expand the bounds by each node's own radius plus its name-label
      // extent (~40px below + sideways), so a big hub at the edge of the
      // layout isn't clipped after the fit.
      const pad = 24;
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const n of simNodes) {
        const ext = nodeRadius(n) + 40;
        const x = n.x ?? width / 2, y = n.y ?? height / 2;
        minX = Math.min(minX, x - ext);
        maxX = Math.max(maxX, x + ext);
        minY = Math.min(minY, y - ext);
        maxY = Math.max(maxY, y + ext);
      }
      minX -= pad; maxX += pad; minY -= pad; maxY += pad;
      const bw = maxX - minX, bh = maxY - minY;
      if (bw < 1 || bh < 1) return;
      const scale = Math.min(2, Math.max(0.2, 0.92 * Math.min(width / bw, height / bh)));
      const tx = width / 2 - (scale * (minX + maxX)) / 2;
      const ty = height / 2 - (scale * (minY + maxY)) / 2;
      svg
        .transition()
        .duration(450)
        .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    };
    fitToViewRef.current = fitToView;

    return () => {
      simulation.stop();
    };
  }, [nodes, links, width, height, onNodeClick, onNodeExpand, expandedNodeIds, showTooltip, hideTooltip, t]);

  return (
    <div ref={containerRef} style={{ width: "100%", position: "relative" }} role="img" aria-label={t("kg.graph_aria")}>
      <span className="sr-only">{t("kg.graph_sr_desc")}</span>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ background: "var(--fj-surface)" }}
      />
      {/* 适应窗口 — on-demand fit-to-view (replaces the old jarring auto-fit) */}
      {nodes.length > 0 && (
        <button
          type="button"
          onClick={() => fitToViewRef.current?.()}
          title={t("kg.fit_view_tip")}
          style={{
            position: "absolute",
            top: 10,
            right: 10,
            display: "flex",
            alignItems: "center",
            gap: 4,
            padding: "4px 10px",
            fontSize: 12,
            fontFamily: '"Noto Serif SC", serif',
            color: "var(--fj-ink-light)",
            background: "var(--fj-surface)",
            border: "1px solid var(--fj-border)",
            borderRadius: 6,
            cursor: "pointer",
            boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
            zIndex: 10,
          }}
        >
          <CompressOutlined />
          {t("kg.fit_view")}
        </button>
      )}
      {/* Custom tooltip */}
      <div
        ref={tooltipRef}
        style={{
          position: "absolute",
          pointerEvents: "none",
          background: "var(--fj-surface)",
          border: "1px solid var(--fj-border)",
          borderRadius: 6,
          padding: "6px 10px",
          fontSize: 12,
          lineHeight: 1.5,
          color: "var(--fj-ink)",
          maxWidth: 260,
          boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
          opacity: 0,
          transition: "opacity 0.15s",
          zIndex: 10,
        }}
      />
    </div>
  );
}
