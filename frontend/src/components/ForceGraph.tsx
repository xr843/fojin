import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
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

interface ForceGraphProps {
  nodes: GraphNode[];
  links: GraphLink[];
  width?: number;
  height?: number;
  onNodeClick?: (node: GraphNode) => void;
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

const TYPE_LABELS: Record<string, string> = {
  person: "人物",
  text: "典籍",
  monastery: "寺院",
  school: "宗派",
  place: "地点",
  concept: "概念",
  dynasty: "朝代",
};

const PREDICATE_LABELS: Record<string, string> = {
  translated: "翻译",
  active_in: "所处",
  alt_translation: "异译",
  parallel_text: "平行文本",
  member_of_school: "宗派",
  teacher_of: "师承",
  cites: "引用",
  commentary_on: "注疏",
  associated_with: "相关",
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

export { TYPE_COLORS, TYPE_LABELS, PREDICATE_LABELS, PREDICATE_COLORS };

export default function ForceGraph({
  nodes,
  links,
  width: propWidth,
  height = 600,
  onNodeClick,
}: ForceGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
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
        .attr("refX", 26)
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
    const simNodes = nodes.map((n) => ({ ...n }));
    const simLinks = links.map((l) => ({ ...l }));

    // Adaptive forces based on node count
    const nodeCount = simNodes.length;
    const chargeStrength = nodeCount > 100 ? -200 : nodeCount > 50 ? -280 : -350;
    const linkDist = nodeCount > 100 ? 90 : nodeCount > 50 ? 110 : 140;

    const simulation = d3
      .forceSimulation(simNodes as any)
      .force(
        "link",
        d3
          .forceLink(simLinks as any)
          .id((d: any) => d.id)
          .distance(linkDist)
      )
      .force("charge", d3.forceManyBody().strength(chargeStrength))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(28))
      .force("x", d3.forceX(width / 2).strength(0.03))
      .force("y", d3.forceY(height / 2).strength(0.03));

    // ── Links ──
    const linkGroup = g.append("g").attr("class", "links");
    const link = linkGroup
      .selectAll("line")
      .data(simLinks)
      .join("line")
      .attr("stroke", (d: any) => PREDICATE_COLORS[d.predicate] || "#bbb5a6")
      .attr("stroke-opacity", 0.35)
      .attr("stroke-width", (d: any) => {
        // cites edges thinner to reduce visual noise
        if (d.predicate === "cites") return 0.8;
        return Math.max(1, Math.min(d.confidence * 2, 2.5));
      })
      .attr("marker-end", (d: any) =>
        d.predicate !== "cites" ? `url(#arrow-${d.predicate})` : null
      );

    // Edge hover: show tooltip
    link
      .on("mouseover", function (event: any, d: any) {
        d3.select(this)
          .attr("stroke-opacity", 0.9)
          .attr("stroke-width", 3);
        const label = PREDICATE_LABELS[d.predicate] || d.predicate;
        const parts = [`<strong>${escapeHtml(label)}</strong>`];
        if (d.provenance)
          parts.push(`<span style="color:#9a8e7a">来源: ${escapeHtml(d.provenance)}</span>`);
        if (d.evidence)
          parts.push(`<span style="color:#7a6e5c">证据: ${escapeHtml(d.evidence)}</span>`);
        if (d.confidence < 1)
          parts.push(`<span style="color:#b08d57">置信度: ${d.confidence}</span>`);
        showTooltip(parts.join("<br>"), event.offsetX, event.offsetY);
      })
      .on("mouseout", function (_event: any, d: any) {
        d3.select(this)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", d.predicate === "cites" ? 0.8 : Math.max(1, Math.min(d.confidence * 2, 2.5)));
        hideTooltip();
      });

    // ── Nodes ──
    const nodeGroup = g.append("g").attr("class", "nodes");
    const node = nodeGroup
      .selectAll("g")
      .data(simNodes)
      .join("g")
      .style("cursor", "pointer")
      .call(
        d3
          .drag<any, any>()
          .on("start", (event, d: any) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d: any) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d: any) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }) as any
      );

    // Node circle with subtle shadow
    node
      .append("circle")
      .attr("r", 16)
      .attr("fill", (d: any) => TYPE_COLORS[d.entity_type] || "#888")
      .attr("stroke", "#fff")
      .attr("stroke-width", 2)
      .attr("filter", "drop-shadow(0 1px 2px rgba(0,0,0,0.12))");

    // Short label inside node (1-2 chars)
    node
      .append("text")
      .text((d: any) => {
        const n = d.name;
        return n.length <= 2 ? n : n.slice(0, 1);
      })
      .attr("text-anchor", "middle")
      .attr("dy", "0.35em")
      .attr("font-size", 10)
      .attr("font-weight", 600)
      .attr("fill", "#fff")
      .attr("pointer-events", "none");

    // Full name label below node
    node
      .append("text")
      .text((d: any) =>
        d.name.length > 6 ? d.name.slice(0, 6) + "…" : d.name
      )
      .attr("text-anchor", "middle")
      .attr("dy", 30)
      .attr("font-size", 11)
      .attr("font-family", '"Noto Serif SC", serif')
      .attr("fill", "#2b2318")
      .attr("pointer-events", "none");

    // ── Hover highlight: dim everything except neighbors ──
    node
      .on("mouseover", function (event: any, d: any) {
        const connectedIds = new Set<number>();
        connectedIds.add(d.id);
        simLinks.forEach((l: any) => {
          const sid = typeof l.source === "object" ? l.source.id : l.source;
          const tid = typeof l.target === "object" ? l.target.id : l.target;
          if (sid === d.id) connectedIds.add(tid);
          if (tid === d.id) connectedIds.add(sid);
        });

        // Dim non-connected nodes
        node.transition().duration(150).style("opacity", (n: any) =>
          connectedIds.has(n.id) ? 1 : 0.15
        );
        // Highlight connected edges, dim others
        link.transition().duration(150)
          .attr("stroke-opacity", (l: any) => {
            const sid = typeof l.source === "object" ? l.source.id : l.source;
            const tid = typeof l.target === "object" ? l.target.id : l.target;
            return sid === d.id || tid === d.id ? 0.8 : 0.05;
          })
          .attr("stroke-width", (l: any) => {
            const sid = typeof l.source === "object" ? l.source.id : l.source;
            const tid = typeof l.target === "object" ? l.target.id : l.target;
            return sid === d.id || tid === d.id ? 2.5 : 0.5;
          });

        // Tooltip
        const typeLabel = TYPE_LABELS[d.entity_type] || d.entity_type;
        let html = `<strong>${escapeHtml(d.name)}</strong> <span style="color:#9a8e7a">${escapeHtml(typeLabel)}</span>`;
        if (d.description) html += `<br><span style="color:#7a6e5c;font-size:11px">${escapeHtml(d.description)}</span>`;
        showTooltip(html, event.offsetX, event.offsetY);
      })
      .on("mouseout", function () {
        node.transition().duration(200).style("opacity", 1);
        link.transition().duration(200)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", (l: any) =>
            l.predicate === "cites" ? 0.8 : Math.max(1, Math.min(l.confidence * 2, 2.5))
          );
        hideTooltip();
      })
      .on("click", (_event: any, d: any) => {
        if (onNodeClick) onNodeClick(d);
      });

    // ── Tick ──
    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, links, width, height, onNodeClick, showTooltip, hideTooltip]);

  return (
    <div ref={containerRef} style={{ width: "100%", position: "relative" }} role="img" aria-label="知识图谱可视化">
      <span className="sr-only">知识图谱：包含节点和关系的可视化网络图</span>
      <svg
        ref={svgRef}
        width={width}
        height={height}
        style={{ background: "#fdfcfa" }}
      />
      {/* Custom tooltip */}
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
