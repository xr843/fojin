import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { useNavigate } from "react-router-dom";
import type { TimelineItem } from "../../api/stats";
import { resolveDynasty } from "../../data/dynasty_years";
import DynastyBands from "./DynastyBands";
import TimelineTooltip from "./TimelineTooltip";

interface TimelineChartProps {
  items: TimelineItem[];
  scholarlyMode: boolean;
}

const MARGIN = { top: 24, right: 20, bottom: 36, left: 20 };
const DEFAULT_DOMAIN: [number, number] = [-500, 2000];

function hashPosition(id: number, start: number, end: number): number {
  const hash = ((id * 2654435761) >>> 0) / 4294967296;
  return start + (end - start) * hash;
}

function darken(hex: string, amount = 0.3): string {
  const c = d3.color(hex);
  return c ? c.darker(amount).formatHex() : hex;
}

export default function TimelineChart({
  items,
  scholarlyMode,
}: TimelineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const navigate = useNavigate();

  const [tooltip, setTooltip] = useState<{
    item: TimelineItem | null;
    x: number;
    y: number;
    visible: boolean;
  }>({ item: null, x: 0, y: 0, visible: false });

  const [dimensions, setDimensions] = useState({ width: 900, height: 500 });
  const [transform, setTransform] = useState<d3.ZoomTransform>(d3.zoomIdentity);

  // Observe container resize
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) {
          setDimensions({ width, height: Math.max(400, Math.min(600, width * 0.5)) });
        }
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const chartWidth = dimensions.width - MARGIN.left - MARGIN.right;
  const chartHeight = dimensions.height - MARGIN.top - MARGIN.bottom;

  const xScaleBase = d3
    .scaleLinear()
    .domain(DEFAULT_DOMAIN)
    .range([0, chartWidth]);

  const xScale = transform.rescaleX(xScaleBase);

  // Compute node positions
  const nodes = items.map((item, _idx) => {
    const dynasty = resolveDynasty(item.dynasty);
    let xYear: number;
    if (item.year_start != null) {
      xYear = item.year_start;
    } else if (dynasty) {
      xYear = hashPosition(item.id, dynasty.start, dynasty.end);
    } else {
      xYear = hashPosition(item.id, DEFAULT_DOMAIN[0], DEFAULT_DOMAIN[1]);
    }

    const color = dynasty?.color ?? "#999";
    return { item, xYear, color };
  });

  // Stagger y positions to reduce overlap
  // Sort by xYear, then assign y in a cycling pattern
  const sorted = [...nodes].sort((a, b) => a.xYear - b.xYear);
  const yPositions = new Map<number, number>();
  sorted.forEach((n, i) => {
    // Use modular distribution across height
    const row = i % Math.max(1, Math.floor(chartHeight / 10));
    const y = MARGIN.top + 20 + row * 10 + (i % 3) * 3;
    yPositions.set(n.item.id, Math.min(y, MARGIN.top + chartHeight - 8));
  });

  // Setup zoom
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown>>();

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 20])
      .translateExtent([
        [-200, 0],
        [dimensions.width + 200, dimensions.height],
      ])
      .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        setTransform(event.transform);
      });

    zoomRef.current = zoom;
    d3.select(svg).call(zoom);

    return () => {
      d3.select(svg).on(".zoom", null);
    };
  }, [dimensions.width, dimensions.height]);

  const handleMouseEnter = useCallback(
    (e: React.MouseEvent, item: TimelineItem) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      setTooltip({
        item,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        visible: true,
      });
    },
    [],
  );

  const handleMouseLeave = useCallback(() => {
    setTooltip((prev) => ({ ...prev, visible: false }));
  }, []);

  const handleClick = useCallback(
    (item: TimelineItem) => {
      if (item.entity_type) return; // entities: no navigation
      navigate(`/texts/${item.id}`);
    },
    [navigate],
  );

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <svg
        ref={svgRef}
        width={dimensions.width}
        height={dimensions.height}
        style={{ cursor: "grab", display: "block" }}
      >
        <defs>
          <clipPath id="timeline-clip">
            <rect
              x={MARGIN.left}
              y={MARGIN.top}
              width={chartWidth}
              height={chartHeight}
            />
          </clipPath>
        </defs>

        {/* Dynasty bands */}
        <g
          clipPath="url(#timeline-clip)"
          transform={`translate(${MARGIN.left},${MARGIN.top})`}
        >
          <DynastyBands xScale={xScale} height={chartHeight} />
        </g>

        {/* Nodes */}
        <g clipPath="url(#timeline-clip)">
          {nodes.map((n) => {
            const cx = MARGIN.left + xScale(n.xYear);
            const cy = yPositions.get(n.item.id) ?? MARGIN.top + chartHeight / 2;
            if (cx < MARGIN.left - 10 || cx > dimensions.width - MARGIN.right + 10)
              return null;
            return (
              <g key={n.item.id}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={4}
                  fill={n.color}
                  stroke={darken(n.color)}
                  strokeWidth={1}
                  style={{ cursor: "pointer" }}
                  onMouseEnter={(e) => handleMouseEnter(e, n.item)}
                  onMouseLeave={handleMouseLeave}
                  onClick={() => handleClick(n.item)}
                />
                {scholarlyMode && n.item.year_start != null && (
                  <text
                    x={cx + 6}
                    y={cy + 3}
                    fontSize={9}
                    fill="#666"
                    fontFamily='"Noto Serif SC", serif'
                  >
                    {n.item.year_start}
                  </text>
                )}
              </g>
            );
          })}
        </g>

        {/* X Axis */}
        <g
          transform={`translate(${MARGIN.left},${MARGIN.top + chartHeight})`}
          ref={(g) => {
            if (g) {
              const axis = d3.axisBottom(xScale).tickFormat((d) => `${d}`);
              d3.select(g).call(axis);
              d3.select(g)
                .selectAll("text")
                .attr("font-family", '"Noto Serif SC", serif')
                .attr("font-size", 11);
            }
          }}
        />
      </svg>

      <TimelineTooltip
        item={tooltip.item}
        x={tooltip.x}
        y={tooltip.y}
        visible={tooltip.visible}
      />
    </div>
  );
}
