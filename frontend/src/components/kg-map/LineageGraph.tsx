import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { escapeHtml } from "../../utils/sanitize";
import type { KGLineageArc } from "../../api/client";

interface LineageNode extends d3.SimulationNodeDatum {
  id: number;
  name: string;
  school: string | null;
}

interface LineageLink extends d3.SimulationLinkDatum<LineageNode> {
  school: string | null;
  year: number | null;
}

/** Resolved link after simulation tick — source/target are objects, not IDs */
interface ResolvedLink {
  source: LineageNode;
  target: LineageNode;
  school: string | null;
  year: number | null;
}

interface LineageGraphProps {
  arcs: KGLineageArc[];
  schoolFilter: string | null;
  height?: number;
  onNodeClick?: (entityId: number) => void;
}

/* -- School color palette -- */
const SCHOOL_COLORS: Record<string, string> = {
  "\u4e2d\u89c2": "#4a7c9b",
  "\u552f\u8bc6": "#7b5ea7",
  "\u5929\u53f0": "#6b8e5b",
  "\u534e\u4e25": "#c08b3e",
  "\u7985\u5b97": "#3d8a8a",
  "\u51c0\u571f": "#c75450",
  "\u5f8b\u5b97": "#b35c8a",
  "\u5bc6\u5b97": "#5b8c6b",
};

const DEFAULT_COLOR = "#9a8e7a";

function getSchoolColor(school: string | null): string {
  if (!school) return DEFAULT_COLOR;
  for (const [key, color] of Object.entries(SCHOOL_COLORS)) {
    if (school.includes(key)) return color;
  }
  return DEFAULT_COLOR;
}

export default function LineageGraph({
  arcs,
  schoolFilter,
  height = 600,
  onNodeClick,
}: LineageGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(800);

  // Responsive width via ResizeObserver
  useEffect(() => {
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
  }, []);

  const width = containerWidth;

  // Tooltip helpers
  const showTooltip = useCallback(
    (html: string, x: number, y: number) => {
      const tip = tooltipRef.current;
      if (!tip) return;
      tip.innerHTML = html;
      tip.style.opacity = "1";
      tip.style.left = `${x + 12}px`;
      tip.style.top = `${y - 8}px`;
    },
    [],
  );
  const hideTooltip = useCallback(() => {
    const tip = tooltipRef.current;
    if (tip) tip.style.opacity = "0";
  }, []);

  useEffect(() => {
    if (!svgRef.current || !arcs.length) return;

    // Filter arcs by school
    const filtered = schoolFilter
      ? arcs.filter((a) => a.school && a.school.includes(schoolFilter))
      : arcs;

    if (!filtered.length) return;

    // Build deduplicated nodes
    const nodeMap = new Map<number, LineageNode>();
    for (const arc of filtered) {
      if (!nodeMap.has(arc.teacher_id)) {
        nodeMap.set(arc.teacher_id, {
          id: arc.teacher_id,
          name: arc.teacher_name,
          school: arc.school,
        });
      }
      if (!nodeMap.has(arc.student_id)) {
        nodeMap.set(arc.student_id, {
          id: arc.student_id,
          name: arc.student_name,
          school: arc.school,
        });
      }
    }
    const simNodes = [...nodeMap.values()].map((n) => ({ ...n }));
    const simLinks: LineageLink[] = filtered.map((a) => ({
      source: a.teacher_id,
      target: a.student_id,
      school: a.school,
      year: a.year,
    }));

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // Defs: arrow marker
    const defs = svg.append("defs");
    defs
      .append("marker")
      .attr("id", "lineage-arrow")
      .attr("viewBox", "0 0 10 6")
      .attr("refX", 22)
      .attr("refY", 3)
      .attr("markerWidth", 8)
      .attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,0 L10,3 L0,6 Z")
      .attr("fill", "#9a8e7a")
      .attr("opacity", 0.5);

    const g = svg.append("g");

    // Zoom
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 6])
      .on("zoom", (event) => g.attr("transform", event.transform));
    svg.call(zoom);

    // Adaptive forces
    const nodeCount = simNodes.length;
    const chargeStrength = nodeCount > 100 ? -200 : nodeCount > 50 ? -280 : -350;
    const linkDist = nodeCount > 100 ? 90 : nodeCount > 50 ? 110 : 140;

    const simulation = d3
      .forceSimulation<LineageNode>(simNodes)
      .force(
        "link",
        d3
          .forceLink<LineageNode, LineageLink>(simLinks)
          .id((d) => d.id)
          .distance(linkDist),
      )
      .force("charge", d3.forceManyBody().strength(chargeStrength))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(24))
      .force("x", d3.forceX(width / 2).strength(0.03))
      .force("y", d3.forceY(height / 2).strength(0.03));

    // Links
    const linkGroup = g.append("g").attr("class", "links");
    const link = linkGroup
      .selectAll("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", (d: LineageLink) => getSchoolColor(d.school))
      .attr("stroke-opacity", 0.35)
      .attr("stroke-width", 1.5)
      .attr("marker-end", "url(#lineage-arrow)");

    // Nodes
    const nodeGroup = g.append("g").attr("class", "nodes");
    const node = nodeGroup
      .selectAll("g")
      .data(simNodes)
      .join("g")
      .style("cursor", "pointer")
      .call(
        d3
          .drag<SVGGElement, LineageNode>()
          .on("start", (event: d3.D3DragEvent<SVGGElement, LineageNode, LineageNode>, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event: d3.D3DragEvent<SVGGElement, LineageNode, LineageNode>, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event: d3.D3DragEvent<SVGGElement, LineageNode, LineageNode>, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          }) as any,
      );

    // Node circles
    node
      .append("circle")
      .attr("r", 12)
      .attr("fill", (d: LineageNode) => getSchoolColor(d.school))
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
      .attr("filter", "drop-shadow(0 1px 2px rgba(0,0,0,0.12))");

    // 1-char label inside node
    node
      .append("text")
      .text((d: LineageNode) => d.name.slice(0, 1))
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", 10)
      .attr("font-weight", 600)
      .attr("fill", "#fff")
      .attr("pointer-events", "none");

    // Full name below node (truncate at 5 chars)
    node
      .append("text")
      .text((d: LineageNode) =>
        d.name.length > 5 ? d.name.slice(0, 5) + "\u2026" : d.name,
      )
      .attr("text-anchor", "middle")
      .attr("dy", 24)
      .attr("font-size", 11)
      .attr("font-family", '"Noto Serif SC", serif')
      .attr("fill", "#2b2318")
      .attr("pointer-events", "none");

    // Hover highlight
    node
      .on("mouseover", function (event: MouseEvent, d: LineageNode) {
        const connectedIds = new Set<number>();
        connectedIds.add(d.id);
        simLinks.forEach((l) => {
          const resolved = l as unknown as ResolvedLink;
          const sid = typeof resolved.source === "object" ? resolved.source.id : (resolved.source as unknown as number);
          const tid = typeof resolved.target === "object" ? resolved.target.id : (resolved.target as unknown as number);
          if (sid === d.id) connectedIds.add(tid);
          if (tid === d.id) connectedIds.add(sid);
        });

        node
          .transition()
          .duration(150)
          .style("opacity", (n: LineageNode) => (connectedIds.has(n.id) ? 1 : 0.15));
        link
          .transition()
          .duration(150)
          .attr("stroke-opacity", (l: LineageLink) => {
            const resolved = l as unknown as ResolvedLink;
            const sid = typeof resolved.source === "object" ? resolved.source.id : (resolved.source as unknown as number);
            const tid = typeof resolved.target === "object" ? resolved.target.id : (resolved.target as unknown as number);
            return sid === d.id || tid === d.id ? 0.8 : 0.05;
          })
          .attr("stroke-width", (l: LineageLink) => {
            const resolved = l as unknown as ResolvedLink;
            const sid = typeof resolved.source === "object" ? resolved.source.id : (resolved.source as unknown as number);
            const tid = typeof resolved.target === "object" ? resolved.target.id : (resolved.target as unknown as number);
            return sid === d.id || tid === d.id ? 2.5 : 0.5;
          });

        // Tooltip
        const schoolLabel = d.school ? escapeHtml(d.school) : "\u672a\u77e5";
        showTooltip(
          `<strong>${escapeHtml(d.name)}</strong> <span style="color:#9a8e7a">${schoolLabel}</span>`,
          event.offsetX,
          event.offsetY,
        );
      })
      .on("mouseout", function () {
        node.transition().duration(200).style("opacity", 1);
        link
          .transition()
          .duration(200)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", 1.5);
        hideTooltip();
      })
      .on("click", (_event: MouseEvent, d: LineageNode) => {
        if (onNodeClick) onNodeClick(d.id);
      });

    // Tick
    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d as unknown as ResolvedLink).source.x ?? 0)
        .attr("y1", (d) => (d as unknown as ResolvedLink).source.y ?? 0)
        .attr("x2", (d) => (d as unknown as ResolvedLink).target.x ?? 0)
        .attr("y2", (d) => (d as unknown as ResolvedLink).target.y ?? 0);
      node.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [arcs, schoolFilter, width, height, onNodeClick, showTooltip, hideTooltip]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", position: "relative" }}
      role="img"
      aria-label="\u5e08\u627f\u4f20\u627f\u7f51\u7edc\u56fe"
    >
      <span className="sr-only">
        \u5e08\u627f\u4f20\u627f\u7f51\u7edc\uff1a\u663e\u793a\u5e08\u5f92\u5173\u7cfb\u7684\u6709\u5411\u7f51\u7edc\u56fe
      </span>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ background: "#fdfcfa" }}
      />
      {/* Tooltip */}
      <div
        ref={tooltipRef}
        style={{
          position: "absolute",
          pointerEvents: "none",
          background: "rgba(255,255,255,0.96)",
          border: "1px solid #e8e0d4",
          borderRadius: 6,
          padding: "6px 10px",
          fontSize: 12,
          lineHeight: 1.5,
          color: "#2b2318",
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
