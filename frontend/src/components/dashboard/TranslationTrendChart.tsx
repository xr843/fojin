import { useRef, useEffect } from "react";
import * as d3 from "d3";
import type { DynastyDistribution } from "../../api/stats";
import { DYNASTIES } from "../../data/dynasty_years";

interface TranslationTrendChartProps {
  data: DynastyDistribution[];
  scholarlyMode: boolean;
}

export default function TranslationTrendChart({ data, scholarlyMode }: TranslationTrendChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    // Sort by DYNASTIES config order, use start year as x position
    const dynastyMap = new Map(DYNASTIES.map((d, i) => [d.name_zh, { index: i, start: d.start }]));
    const sorted = [...data]
      .filter((d) => dynastyMap.has(d.dynasty))
      .sort((a, b) => {
        const ai = dynastyMap.get(a.dynasty)!.index;
        const bi = dynastyMap.get(b.dynasty)!.index;
        return ai - bi;
      })
      .map((d) => ({
        ...d,
        x: dynastyMap.get(d.dynasty)!.start,
      }));

    if (sorted.length === 0) return;

    const margin = { top: 20, right: 20, bottom: 40, left: 50 };
    const width = 600;
    const height = 300;

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
      .domain(d3.extent(sorted, (d) => d.x) as [number, number])
      .range([0, innerWidth]);

    const yScale = d3
      .scaleLinear()
      .domain([0, d3.max(sorted, (d) => d.count) ?? 1])
      .range([innerHeight, 0])
      .nice();

    // Gradient definition
    const defs = svg.append("defs");
    const gradient = defs
      .append("linearGradient")
      .attr("id", "trend-area-gradient")
      .attr("x1", "0")
      .attr("y1", "0")
      .attr("x2", "0")
      .attr("y2", "1");
    gradient.append("stop").attr("offset", "0%").attr("stop-color", "var(--fj-accent, #8b2500)").attr("stop-opacity", 0.3);
    gradient.append("stop").attr("offset", "100%").attr("stop-color", "var(--fj-accent, #8b2500)").attr("stop-opacity", 0.05);

    // Area
    const area = d3
      .area<(typeof sorted)[number]>()
      .x((d) => xScale(d.x))
      .y0(innerHeight)
      .y1((d) => yScale(d.count))
      .curve(d3.curveMonotoneX);

    g.append("path")
      .datum(sorted)
      .attr("fill", "url(#trend-area-gradient)")
      .attr("d", area);

    // Line
    const line = d3
      .line<(typeof sorted)[number]>()
      .x((d) => xScale(d.x))
      .y((d) => yScale(d.count))
      .curve(d3.curveMonotoneX);

    g.append("path")
      .datum(sorted)
      .attr("fill", "none")
      .attr("stroke", "var(--fj-accent, #8b2500)")
      .attr("stroke-width", 2)
      .attr("d", line);

    // Data points
    g.selectAll(".dot")
      .data(sorted)
      .join("circle")
      .attr("class", "dot")
      .attr("cx", (d) => xScale(d.x))
      .attr("cy", (d) => yScale(d.count))
      .attr("r", 3)
      .attr("fill", "var(--fj-accent, #8b2500)");

    // X axis
    g.append("g")
      .attr("transform", `translate(0,${innerHeight})`)
      .call(d3.axisBottom(xScale).ticks(8).tickFormat((d) => {
        const v = d.valueOf();
        return v < 0 ? `${Math.abs(v)} BCE` : `${v}`;
      }))
      .selectAll("text")
      .style("font-size", "9px")
      .style("fill", "var(--fj-ink, #2b2318)")
      .attr("transform", "rotate(-30)")
      .attr("text-anchor", "end");

    // Y axis
    g.append("g")
      .call(d3.axisLeft(yScale).ticks(5))
      .selectAll("text")
      .style("font-size", "10px")
      .style("fill", "var(--fj-ink, #2b2318)");

    // Data point labels in scholarly mode
    if (scholarlyMode) {
      g.selectAll(".point-label")
        .data(sorted)
        .join("text")
        .attr("class", "point-label")
        .attr("x", (d) => xScale(d.x))
        .attr("y", (d) => yScale(d.count) - 8)
        .attr("text-anchor", "middle")
        .style("font-size", "9px")
        .style("fill", "var(--fj-ink, #2b2318)")
        .text((d) => d.count.toLocaleString());
    }
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
