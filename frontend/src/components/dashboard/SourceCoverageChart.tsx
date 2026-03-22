import { useRef, useEffect } from "react";
import * as d3 from "d3";
import type { SourceCoverage } from "../../api/stats";

interface SourceCoverageChartProps {
  data: SourceCoverage[];
  scholarlyMode: boolean;
}

export default function SourceCoverageChart({ data, scholarlyMode }: SourceCoverageChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const sorted = [...data]
      .map((d) => ({ ...d, total: d.full_content + d.metadata_only }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10);

    const margin = { top: 10, right: scholarlyMode ? 60 : 20, bottom: 30, left: 120 };
    const barHeight = 24;
    const gap = 4;
    const width = 600;
    const height = margin.top + margin.bottom + sorted.length * (barHeight + gap);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

    const xScale = d3
      .scaleLinear()
      .domain([0, d3.max(sorted, (d) => d.total) ?? 1])
      .range([0, innerWidth])
      .nice();

    const yScale = d3
      .scaleBand()
      .domain(sorted.map((d) => d.source_name))
      .range([0, innerHeight])
      .padding(gap / (barHeight + gap));

    // Y axis
    g.append("g")
      .call(d3.axisLeft(yScale).tickSize(0))
      .call((axis) => axis.select(".domain").remove())
      .selectAll("text")
      .style("font-size", "10px")
      .style("fill", "var(--fj-ink, #2b2318)");

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${innerHeight})`)
      .call(d3.axisBottom(xScale).ticks(5))
      .selectAll("text")
      .style("font-size", "10px")
      .style("fill", "var(--fj-ink, #2b2318)");

    // Full content bars (accent)
    g.selectAll(".bar-full")
      .data(sorted)
      .join("rect")
      .attr("class", "bar-full")
      .attr("x", 0)
      .attr("y", (d) => yScale(d.source_name) ?? 0)
      .attr("width", (d) => xScale(d.full_content))
      .attr("height", yScale.bandwidth())
      .attr("fill", "var(--fj-accent, #8b2500)")
      .attr("rx", 2);

    // Metadata-only bars (muted, stacked after full_content)
    g.selectAll(".bar-meta")
      .data(sorted)
      .join("rect")
      .attr("class", "bar-meta")
      .attr("x", (d) => xScale(d.full_content))
      .attr("y", (d) => yScale(d.source_name) ?? 0)
      .attr("width", (d) => xScale(d.metadata_only))
      .attr("height", yScale.bandwidth())
      .attr("fill", "#b08d57")
      .attr("opacity", 0.5)
      .attr("rx", 2);

    // Count labels in scholarly mode
    if (scholarlyMode) {
      g.selectAll(".count-label")
        .data(sorted)
        .join("text")
        .attr("class", "count-label")
        .attr("x", (d) => xScale(d.total) + 4)
        .attr("y", (d) => (yScale(d.source_name) ?? 0) + yScale.bandwidth() / 2)
        .attr("dy", "0.35em")
        .style("font-size", "10px")
        .style("fill", "var(--fj-ink, #2b2318)")
        .text((d) => d.total.toLocaleString());
    }
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
