import { useRef, useEffect } from "react";
import * as d3 from "d3";
import type { TopTranslator } from "../../api/stats";
import { resolveDynasty } from "../../data/dynasty_years";

interface TopTranslatorsChartProps {
  data: TopTranslator[];
  scholarlyMode: boolean;
}

export default function TopTranslatorsChart({ data, scholarlyMode }: TopTranslatorsChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const sorted = [...data].sort((a, b) => b.count - a.count).slice(0, 15);

    const margin = { top: 10, right: scholarlyMode ? 60 : 20, bottom: 30, left: 120 };
    const barHeight = 22;
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

    // Build label: name + dynasty
    const label = (d: TopTranslator) => {
      if (d.dynasty) return `${d.name}（${d.dynasty}）`;
      return d.name;
    };

    const xScale = d3
      .scaleLinear()
      .domain([0, d3.max(sorted, (d) => d.count) ?? 1])
      .range([0, innerWidth])
      .nice();

    const yScale = d3
      .scaleBand()
      .domain(sorted.map(label))
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

    // Bars
    g.selectAll(".bar")
      .data(sorted)
      .join("rect")
      .attr("class", "bar")
      .attr("x", 0)
      .attr("y", (d) => yScale(label(d)) ?? 0)
      .attr("width", (d) => xScale(d.count))
      .attr("height", yScale.bandwidth())
      .attr("fill", (d) => resolveDynasty(d.dynasty)?.color ?? "#b08d57")
      .attr("rx", 2);

    // Count labels in scholarly mode
    if (scholarlyMode) {
      g.selectAll(".count-label")
        .data(sorted)
        .join("text")
        .attr("class", "count-label")
        .attr("x", (d) => xScale(d.count) + 4)
        .attr("y", (d) => (yScale(label(d)) ?? 0) + yScale.bandwidth() / 2)
        .attr("dy", "0.35em")
        .style("font-size", "10px")
        .style("fill", "var(--fj-ink, #2b2318)")
        .text((d) => d.count.toLocaleString());
    }
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
