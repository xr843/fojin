import { useRef, useEffect } from "react";
import * as d3 from "d3";
import type { CategoryDistribution } from "../../api/stats";

interface CategoryTreemapProps {
  data: CategoryDistribution[];
  scholarlyMode: boolean;
}

const WARM_PALETTE = [
  "#8b2500", "#b08d57", "#c75450", "#d4a56a", "#6b8e5b",
  "#4a7c9b", "#9b8b6e", "#c75480", "#5470c6", "#91cc75",
  "#a07d47", "#d4756b", "#7a9e6a", "#8aae7a", "#8b7355",
];

export default function CategoryTreemap({ data, scholarlyMode }: CategoryTreemapProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const width = 600;
    const height = 400;
    const total = data.reduce((s, d) => s + d.count, 0);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    interface TreeNode {
      category?: string;
      count?: number;
      children?: TreeNode[];
    }

    const root = d3
      .hierarchy<TreeNode>({ children: data.map((d) => ({ category: d.category, count: d.count })) })
      .sum((d) => d.count ?? 0);

    d3.treemap<TreeNode>()
      .size([width, height])
      .padding(2)
      .round(true)(root);

    const color = d3
      .scaleOrdinal<string>()
      .domain(data.map((d) => d.category))
      .range(WARM_PALETTE);

    const leaves = root.leaves() as d3.HierarchyRectangularNode<TreeNode>[];

    const cell = svg
      .selectAll("g")
      .data(leaves)
      .join("g")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`);

    cell
      .append("rect")
      .attr("width", (d) => d.x1 - d.x0)
      .attr("height", (d) => d.y1 - d.y0)
      .attr("fill", (d) => color(d.data.category ?? ""))
      .attr("rx", 2)
      .attr("opacity", 0.85);

    // Clip text to rect
    cell
      .append("clipPath")
      .attr("id", (_, i) => `clip-cat-${i}`)
      .append("rect")
      .attr("width", (d) => d.x1 - d.x0)
      .attr("height", (d) => d.y1 - d.y0);

    const textGroup = cell
      .append("g")
      .attr("clip-path", (_, i) => `url(#clip-cat-${i})`);

    textGroup
      .append("text")
      .attr("x", 4)
      .attr("y", 14)
      .style("font-size", "11px")
      .style("fill", "#fff")
      .style("font-weight", "600")
      .text((d) => d.data.category ?? "");

    textGroup
      .append("text")
      .attr("x", 4)
      .attr("y", 28)
      .style("font-size", "10px")
      .style("fill", "#fff")
      .style("opacity", "0.8")
      .text((d) => {
        const count = d.data.count ?? 0;
        const countLabel = count.toLocaleString();
        if (scholarlyMode) {
          const pct = ((count / total) * 100).toFixed(1);
          return `${countLabel} (${pct}%)`;
        }
        return countLabel;
      });
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
