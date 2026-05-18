/**
 * KGTimeline — 知识图谱实体时间轴视图
 *
 * 将携带 year_start（及可选 year_end）的实体渲染在水平时间轴上。
 * - person / dynasty 各自以 TYPE_COLORS 配色区分。
 * - BCE 年份以负整数表示，坐标轴正确处理跨零点跨度。
 * - 单点实体（无 year_end）显示为圆点；有时段的显示为短横条。
 * - 点击实体调用 onEntityClick(id)。
 */

import { useMemo, useRef, useState, useEffect } from "react";
import { Spin, Empty, Tooltip } from "antd";
import { TYPE_COLORS } from "../ForceGraph";
import type { KGTimelineEntity } from "../../api/client";

interface KGTimelineProps {
  entities: KGTimelineEntity[];
  loading?: boolean;
  onEntityClick: (id: number) => void;
  selectedEntityId?: number | null;
}

// 年份格式化：负数显示为 BCE，正数直接显示
function formatYear(year: number): string {
  if (year < 0) return `公元前 ${Math.abs(year)}`;
  return `公元 ${year}`;
}

// 每个 entity_type 在时间轴上的垂直分组序号（影响 y 偏移，用于错排防重叠）
const TYPE_ROW: Record<string, number> = {
  dynasty: 0,
  person: 1,
};

const ROW_HEIGHT = 28;   // px per entity-type row
const POINT_R = 5;       // 单点圆半径
const BAR_H = 10;        // 时段横条高度
const MIN_BAR_W = 4;     // 最小横条宽度（避免过细不可点）
const AXIS_H = 28;       // 坐标轴高度（底部）
const PADDING = { top: 8, right: 24, bottom: AXIS_H, left: 24 };

export default function KGTimeline({
  entities,
  loading,
  onEntityClick,
  selectedEntityId,
}: KGTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);

  // 响应容器宽度
  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setWidth(w);
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const { domain, rowGroups, svgHeight } = useMemo(() => {
    if (!entities.length) {
      return { domain: [-100, 2000] as [number, number], rowGroups: {}, svgHeight: 80 };
    }

    const allYears = entities.flatMap((e) =>
      e.year_end != null ? [e.year_start, e.year_end] : [e.year_start]
    );
    const minY = Math.min(...allYears);
    const maxY = Math.max(...allYears);
    // 留出边距
    const pad = Math.max((maxY - minY) * 0.02, 30);
    const domain: [number, number] = [minY - pad, maxY + pad];

    // 按 entity_type 分组
    const rowGroups: Record<string, KGTimelineEntity[]> = {};
    for (const e of entities) {
      (rowGroups[e.entity_type] ??= []).push(e);
    }

    const numRows = Object.keys(rowGroups).length;
    const svgHeight = PADDING.top + numRows * ROW_HEIGHT + PADDING.bottom + 8;

    return { domain, rowGroups, svgHeight };
  }, [entities]);

  // 线性映射 year → x
  const chartW = width - PADDING.left - PADDING.right;
  const scaleX = (year: number) => {
    const ratio = (year - domain[0]) / (domain[1] - domain[0]);
    return PADDING.left + ratio * chartW;
  };

  // 坐标轴刻度（最多 10 个）
  const ticks = useMemo(() => {
    const span = domain[1] - domain[0];
    const rough = span / 8;
    const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
    const candidates = [1, 2, 5, 10].map((m) => m * magnitude);
    const step = candidates.find((c) => span / c <= 10) ?? magnitude * 10;
    const start = Math.ceil(domain[0] / step) * step;
    const result: number[] = [];
    for (let y = start; y <= domain[1]; y += step) result.push(y);
    return result;
  }, [domain]);

  // 按类型排序的 row 列表（dynasty 排在上方）
  const sortedTypes = Object.keys(rowGroups).sort(
    (a, b) => (TYPE_ROW[a] ?? 99) - (TYPE_ROW[b] ?? 99)
  );

  if (loading) {
    return (
      <div className="kg-timeline-loading">
        <Spin />
      </div>
    );
  }

  if (!entities.length) {
    return (
      <div className="kg-timeline-empty">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无时间数据"
        />
      </div>
    );
  }

  return (
    <div className="kg-timeline-wrap" ref={containerRef}>
      <svg
        width={width}
        height={svgHeight}
        className="kg-timeline-svg"
        aria-label="知识图谱时间轴"
      >
        {/* ── 坐标轴底线 ── */}
        <line
          x1={PADDING.left}
          y1={svgHeight - PADDING.bottom}
          x2={width - PADDING.right}
          y2={svgHeight - PADDING.bottom}
          stroke="#c8bfb0"
          strokeWidth={1}
        />

        {/* ── 刻度 ── */}
        {ticks.map((y) => {
          const x = scaleX(y);
          return (
            <g key={y}>
              <line
                x1={x} y1={svgHeight - PADDING.bottom}
                x2={x} y2={svgHeight - PADDING.bottom + 5}
                stroke="#c8bfb0"
                strokeWidth={1}
              />
              <text
                x={x}
                y={svgHeight - PADDING.bottom + 16}
                textAnchor="middle"
                fontSize={10}
                fill="#9a8e7a"
                fontFamily="'Noto Serif SC', serif"
              >
                {y < 0 ? `前${Math.abs(y)}` : y}
              </text>
            </g>
          );
        })}

        {/* ── 各类型行 ── */}
        {sortedTypes.map((etype, rowIdx) => {
          const color = TYPE_COLORS[etype] ?? "#888";
          const rowY = PADDING.top + rowIdx * ROW_HEIGHT + ROW_HEIGHT / 2;
          const rowEntities = rowGroups[etype];

          return (
            <g key={etype}>
              {/* 行背景网格线 */}
              <line
                x1={PADDING.left}
                y1={rowY}
                x2={width - PADDING.right}
                y2={rowY}
                stroke="#f0ebe3"
                strokeWidth={1}
              />

              {/* 实体 */}
              {rowEntities.map((e) => {
                const x1 = scaleX(e.year_start);
                const isSelected = e.id === selectedEntityId;

                if (e.year_end != null && e.year_end !== e.year_start) {
                  // 时段横条
                  const x2 = scaleX(e.year_end);
                  const barW = Math.max(x2 - x1, MIN_BAR_W);
                  return (
                    <Tooltip
                      key={e.id}
                      title={`${e.name_zh}（${formatYear(e.year_start)} — ${formatYear(e.year_end)}）`}
                      placement="top"
                    >
                      <rect
                        x={x1}
                        y={rowY - BAR_H / 2}
                        width={barW}
                        height={BAR_H}
                        rx={3}
                        ry={3}
                        fill={color}
                        fillOpacity={isSelected ? 1 : 0.72}
                        stroke={isSelected ? "#fff" : "none"}
                        strokeWidth={isSelected ? 1.5 : 0}
                        style={{ cursor: "pointer" }}
                        onClick={() => onEntityClick(e.id)}
                        tabIndex={0}
                        role="button"
                        aria-label={e.name_zh}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter" || ev.key === " ") {
                            ev.preventDefault();
                            onEntityClick(e.id);
                          }
                        }}
                      />
                    </Tooltip>
                  );
                }

                // 单点
                return (
                  <Tooltip
                    key={e.id}
                    title={`${e.name_zh}（${formatYear(e.year_start)}）`}
                    placement="top"
                  >
                    <circle
                      cx={x1}
                      cy={rowY}
                      r={isSelected ? POINT_R + 2 : POINT_R}
                      fill={color}
                      fillOpacity={isSelected ? 1 : 0.78}
                      stroke={isSelected ? "#fff" : "rgba(0,0,0,0.12)"}
                      strokeWidth={isSelected ? 2 : 1}
                      style={{ cursor: "pointer" }}
                      onClick={() => onEntityClick(e.id)}
                      tabIndex={0}
                      role="button"
                      aria-label={e.name_zh}
                      onKeyDown={(ev) => {
                        if (ev.key === "Enter" || ev.key === " ") {
                          ev.preventDefault();
                          onEntityClick(e.id);
                        }
                      }}
                    />
                  </Tooltip>
                );
              })}
            </g>
          );
        })}
      </svg>

      {/* ── 图例 ── */}
      <div className="kg-timeline-legend">
        {sortedTypes.map((etype) => (
          <span key={etype} className="kg-timeline-legend-item">
            <span
              className="kg-timeline-legend-swatch"
              style={{ background: TYPE_COLORS[etype] ?? "#888" }}
            />
            {etype === "person" ? "人物" : etype === "dynasty" ? "朝代" : etype}
            <span className="kg-timeline-legend-count">
              {rowGroups[etype].length}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
