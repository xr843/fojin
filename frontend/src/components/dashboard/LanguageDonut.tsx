import { useRef, useEffect } from "react";
import * as d3 from "d3";
import type { LanguageDistribution } from "../../api/stats";

interface LanguageDonutProps {
  data: LanguageDistribution[];
  scholarlyMode: boolean;
}

const WARM_PALETTE = [
  "#8b2500", "#b08d57", "#c75450", "#d4a56a", "#6b8e5b",
  "#4a7c9b", "#9b8b6e", "#c75480", "#5470c6", "#91cc75",
  "#a07d47",
];

export default function LanguageDonut({ data, scholarlyMode }: LanguageDonutProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const sorted = [...data].sort((a, b) => b.count - a.count);
    const top10 = sorted.slice(0, 10);
    const rest = sorted.slice(10);
    const pieData = rest.length > 0
      ? [...top10, { language: "Other", count: rest.reduce((s, d) => s + d.count, 0) }]
      : top10;

    const total = pieData.reduce((s, d) => s + d.count, 0);

    const size = 400;
    const radius = size / 2;
    const innerRadius = radius * 0.55;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg
      .attr("viewBox", `0 0 ${size} ${size}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    const g = svg.append("g").attr("transform", `translate(${radius},${radius})`);

    const color = d3.scaleOrdinal<string>().domain(pieData.map((d) => d.language)).range(WARM_PALETTE);

    const pie = d3
      .pie<(typeof pieData)[number]>()
      .value((d) => d.count)
      .sort(null);

    const arc = d3.arc<d3.PieArcDatum<(typeof pieData)[number]>>()
      .innerRadius(innerRadius)
      .outerRadius(radius - 10);

    const labelArc = d3.arc<d3.PieArcDatum<(typeof pieData)[number]>>()
      .innerRadius(radius * 0.75)
      .outerRadius(radius * 0.75);

    g.selectAll(".slice")
      .data(pie(pieData))
      .join("path")
      .attr("class", "slice")
      .attr("d", arc)
      .attr("fill", (d) => color(d.data.language))
      .attr("stroke", "var(--fj-bg, #f8f5ef)")
      .attr("stroke-width", 1.5);

    // Percentage labels in scholarly mode
    if (scholarlyMode) {
      g.selectAll(".pct-label")
        .data(pie(pieData))
        .join("text")
        .attr("class", "pct-label")
        .attr("transform", (d) => `translate(${labelArc.centroid(d)})`)
        .attr("text-anchor", "middle")
        .attr("dy", "0.35em")
        .style("font-size", "10px")
        .style("fill", "#fff")
        .style("pointer-events", "none")
        .text((d) => `${((d.data.count / total) * 100).toFixed(1)}%`);
    }

    // Language name labels
    g.selectAll(".name-label")
      .data(pie(pieData))
      .join("text")
      .attr("class", "name-label")
      .attr("transform", (d) => {
        const pos = labelArc.centroid(d);
        const midAngle = (d.startAngle + d.endAngle) / 2;
        pos[0] = (radius - 2) * (midAngle < Math.PI ? 1 : -1);
        return `translate(${pos})`;
      })
      .attr("text-anchor", (d) => {
        const midAngle = (d.startAngle + d.endAngle) / 2;
        return midAngle < Math.PI ? "start" : "end";
      })
      .attr("dy", "0.35em")
      .style("font-size", "10px")
      .style("fill", "var(--fj-ink, #2b2318)")
      .text((d) => d.data.language);

    // Center text: total count
    g.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "-0.2em")
      .style("font-size", "22px")
      .style("font-weight", "700")
      .style("fill", "var(--fj-accent, #8b2500)")
      .style("font-family", '"Noto Serif SC", serif')
      .text(total.toLocaleString());

    g.append("text")
      .attr("text-anchor", "middle")
      .attr("dy", "1.2em")
      .style("font-size", "11px")
      .style("fill", "var(--fj-ink, #2b2318)")
      .style("opacity", "0.6")
      .text("languages");
  }, [data, scholarlyMode]);

  return <svg ref={svgRef} style={{ width: "100%", height: "auto" }} />;
}
