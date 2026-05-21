/**
 * KGTimeline — 知识图谱实体时间轴视图（直方图分桶 + 稀疏点混合）
 *
 * 渲染逻辑：
 * - dynasty 实体：保持原样（年代横条，本来就稀疏）
 * - person 实体：按 BUCKET_YEARS 年分桶；
 *   - 高密度桶（>= DENSE_THRESHOLD 人）渲染成柱条（高度=对数缩放人数）
 *   - 低密度桶散落渲染为圆点（每个仍可单独点击）
 *   - 点击柱条 → 抽屉列出该桶全部人物，点击列表项激活实体面板
 * - 单点和单条都保留键盘可达 + tooltip。
 */

import { useMemo, useRef, useState, useEffect } from "react";
import { Spin, Empty, Tooltip, Drawer, List } from "antd";
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

// 每个 entity_type 在时间轴上的垂直分组序号
const TYPE_ROW: Record<string, number> = {
  dynasty: 0,
  person: 1,
};

const ROW_HEIGHT = 80;       // px per entity-type row (taller for histogram)
const POINT_R = 5;
const BAR_H = 10;            // dynasty 时段横条高度
const MIN_BAR_W = 4;
const AXIS_H = 28;
const DYNASTY_BAND_H = 22;   // 朝代背景条带高度（位于刻度下方）
const PADDING = { top: 8, right: 24, bottom: AXIS_H + DYNASTY_BAND_H, left: 24 };

// 直方图分桶配置
const BUCKET_YEARS = 50;      // 50 年/桶
const DENSE_THRESHOLD = 6;    // 桶内 >=6 人则渲染为柱条
const MAX_BAR_HEIGHT = 60;    // px
const MIN_DENSE_BAR_HEIGHT = 6;

// 朝代分段（非重叠版本，用于底部学术信息条带）
// 边界做了简化：北宋/遼/金、南宋/金/元、隋/南北朝 等并存期取主流。
// 颜色用交错的两种暖色调，与正文柱条主色（#b85450 person）拉开。
const DYNASTIES: { name: string; startYear: number; endYear: number; fill: string }[] = [
  { name: "西晉", startYear: 265, endYear: 317, fill: "#e8dccc" },
  { name: "東晉", startYear: 317, endYear: 420, fill: "#d6c9b3" },
  { name: "南北朝", startYear: 420, endYear: 589, fill: "#e8dccc" },
  { name: "隋", startYear: 589, endYear: 618, fill: "#d6c9b3" },
  { name: "唐", startYear: 618, endYear: 907, fill: "#e8dccc" },
  { name: "五代", startYear: 907, endYear: 960, fill: "#d6c9b3" },
  { name: "北宋", startYear: 960, endYear: 1127, fill: "#e8dccc" },
  { name: "南宋", startYear: 1127, endYear: 1279, fill: "#d6c9b3" },
  { name: "元", startYear: 1279, endYear: 1368, fill: "#e8dccc" },
  { name: "明", startYear: 1368, endYear: 1644, fill: "#d6c9b3" },
  { name: "清", startYear: 1644, endYear: 1912, fill: "#e8dccc" },
  // 民國 endYear 用当前年份动态求值，避免硬编码后随时间 drift。
  { name: "民國", startYear: 1912, endYear: new Date().getFullYear(), fill: "#d6c9b3" },
];
const DYNASTY_LABEL_MIN_W = 8;    // 段宽 < 8px 才完全省略；其余靠 textLength 压缩
const DYNASTY_LABEL_NATURAL_W = 24; // 自然字宽 (~11px × 2 char + padding)；超过此宽度按自然字距

interface PersonBucket {
  startYear: number;
  endYear: number;
  entities: KGTimelineEntity[];
}

function bucketPersons(entities: KGTimelineEntity[]): PersonBucket[] {
  // Bucketing uses astronomical years (-50 means 50 BCE, 0 included);
  // formatYear collapses 0 → "公元前 1" so labels read naturally.
  // We bucket by birth year (year_start) only — long-lived monks land in
  // their birth bucket, the standard scholarly cohorting choice.
  if (!entities.length) return [];
  const sorted = [...entities].sort((a, b) => a.year_start - b.year_start);
  const minY = sorted[0].year_start;
  const maxY = sorted[sorted.length - 1].year_start;
  const startBucket = Math.floor(minY / BUCKET_YEARS) * BUCKET_YEARS;
  const buckets: PersonBucket[] = [];
  for (let s = startBucket; s <= maxY; s += BUCKET_YEARS) {
    buckets.push({ startYear: s, endYear: s + BUCKET_YEARS, entities: [] });
  }
  for (const e of sorted) {
    const idx = Math.floor((e.year_start - startBucket) / BUCKET_YEARS);
    if (buckets[idx]) buckets[idx].entities.push(e);
  }
  return buckets.filter((b) => b.entities.length > 0);
}

export default function KGTimeline({
  entities,
  loading,
  onEntityClick,
  selectedEntityId,
}: KGTimelineProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [openBucket, setOpenBucket] = useState<PersonBucket | null>(null);

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

  const { domain, rowGroups, personBuckets, maxPersonBucket, svgHeight } = useMemo(() => {
    if (!entities.length) {
      return {
        domain: [-100, 2000] as [number, number],
        rowGroups: {} as Record<string, KGTimelineEntity[]>,
        personBuckets: [] as PersonBucket[],
        maxPersonBucket: 0,
        svgHeight: 80,
      };
    }

    const allYears = entities.flatMap((e) =>
      e.year_end != null ? [e.year_start, e.year_end] : [e.year_start]
    );
    const minY = Math.min(...allYears);
    const maxY = Math.max(...allYears);
    const pad = Math.max((maxY - minY) * 0.02, 30);
    const domain: [number, number] = [minY - pad, maxY + pad];

    const rowGroups: Record<string, KGTimelineEntity[]> = {};
    for (const e of entities) {
      (rowGroups[e.entity_type] ??= []).push(e);
    }

    const personBuckets = bucketPersons(rowGroups.person ?? []);
    const maxPersonBucket = personBuckets.reduce(
      (m, b) => Math.max(m, b.entities.length),
      0
    );

    const numRows = Object.keys(rowGroups).length;
    const svgHeight = PADDING.top + numRows * ROW_HEIGHT + PADDING.bottom + 8;

    return { domain, rowGroups, personBuckets, maxPersonBucket, svgHeight };
  }, [entities]);

  // 线性映射 year → x
  const chartW = width - PADDING.left - PADDING.right;
  const scaleX = (year: number) => {
    const ratio = (year - domain[0]) / (domain[1] - domain[0]);
    return PADDING.left + ratio * chartW;
  };

  // 平方根高度缩放：sqrt(count) / sqrt(max) * MAX
  // 比对数更陡，能拉开 641 vs 41 这种 16× 真实差距的视觉对比
  // (对数把 16× 压成 2.5×；sqrt 拉到 ~4×)
  const scaleBarHeight = (count: number) => {
    if (maxPersonBucket <= 0) return 0;
    const ratio = Math.sqrt(count) / Math.sqrt(maxPersonBucket);
    return Math.max(MIN_DENSE_BAR_HEIGHT, ratio * MAX_BAR_HEIGHT);
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

  // 按类型排序的 row 列表
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
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无时间数据" />
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

        {/* ── 朝代背景条带（位于刻度下方）── */}
        {DYNASTIES.map((d) => {
          // 裁剪到当前 domain
          const ds = Math.max(d.startYear, domain[0]);
          const de = Math.min(d.endYear, domain[1]);
          if (de <= ds) return null;
          const x1 = scaleX(ds);
          const x2 = scaleX(de);
          const w = x2 - x1;
          if (w < 1) return null;
          const bandTop = svgHeight - DYNASTY_BAND_H;
          const showLabel = w >= DYNASTY_LABEL_MIN_W;
          // 短段（西晉 52y、隋 29y、五代 53y 等）用 textLength 压缩字距
          // 而非整体省略；这样所有朝代都有名称，只是窄段字距收紧。
          const useTextLength = w < DYNASTY_LABEL_NATURAL_W;
          // 留 2px 内边距，避免字与相邻段边界紧贴。
          const textLengthValue = Math.max(w - 4, 6);
          return (
            <Tooltip
              key={d.name}
              title={`${d.name}（公元 ${d.startYear} — ${d.endYear}）`}
              placement="top"
            >
              <g style={{ cursor: "help" }}>
                <rect
                  x={x1}
                  y={bandTop}
                  width={w}
                  height={DYNASTY_BAND_H - 2}
                  fill={d.fill}
                  fillOpacity={0.55}
                  stroke="rgba(154, 142, 122, 0.25)"
                  strokeWidth={0.5}
                />
                {showLabel && (
                  <text
                    x={x1 + w / 2}
                    y={bandTop + DYNASTY_BAND_H / 2 + 1}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={11}
                    fill="#6b5d47"
                    fontFamily="'Noto Serif SC', serif"
                    style={{ pointerEvents: "none" }}
                    {...(useTextLength
                      ? {
                          textLength: textLengthValue,
                          lengthAdjust:
                            "spacingAndGlyphs" as React.SVGAttributes<SVGTextElement>["lengthAdjust"],
                        }
                      : {})}
                  >
                    {d.name}
                  </text>
                )}
              </g>
            </Tooltip>
          );
        })}

        {/* ── 各类型行 ── */}
        {sortedTypes.map((etype, rowIdx) => {
          const color = TYPE_COLORS[etype] ?? "#888";
          const rowY = PADDING.top + rowIdx * ROW_HEIGHT + ROW_HEIGHT / 2;
          const baselineY = PADDING.top + rowIdx * ROW_HEIGHT + ROW_HEIGHT - 4;
          const rowEntities = rowGroups[etype];

          return (
            <g key={etype}>
              {/* 行背景网格线（柱条 baseline） */}
              <line
                x1={PADDING.left}
                y1={baselineY}
                x2={width - PADDING.right}
                y2={baselineY}
                stroke="#f0ebe3"
                strokeWidth={1}
              />

              {/* person 行：分桶混合渲染 */}
              {etype === "person" ? (
                <>
                  {personBuckets.map((bucket) => {
                    const dense = bucket.entities.length >= DENSE_THRESHOLD;
                    if (dense) {
                      // 直方图柱条
                      const x1 = scaleX(bucket.startYear);
                      const x2 = scaleX(bucket.endYear);
                      const barW = Math.max(x2 - x1 - 1, MIN_BAR_W);
                      const barH = scaleBarHeight(bucket.entities.length);
                      const sample = bucket.entities
                        .slice(0, 5)
                        .map((e) => e.name_zh)
                        .join("、");
                      const more =
                        bucket.entities.length > 5
                          ? `…等 ${bucket.entities.length} 人`
                          : "";
                      return (
                        <Tooltip
                          key={`bucket-${bucket.startYear}`}
                          title={`${formatYear(bucket.startYear)} — ${formatYear(
                            bucket.endYear - 1
                          )}\u3000${bucket.entities.length} 人物：${sample}${more}（点击查看全部）`}
                          placement="top"
                          overlayStyle={{ maxWidth: 320 }}
                        >
                          <rect
                            x={x1}
                            y={baselineY - barH}
                            width={barW}
                            height={barH}
                            fill={color}
                            fillOpacity={0.65}
                            stroke="rgba(0,0,0,0.18)"
                            strokeWidth={0.5}
                            rx={1}
                            ry={1}
                            style={{ cursor: "pointer" }}
                            onClick={() => setOpenBucket(bucket)}
                            tabIndex={0}
                            role="button"
                            aria-label={`${formatYear(bucket.startYear)} — ${formatYear(bucket.endYear - 1)} ${bucket.entities.length} 人物`}
                            onKeyDown={(ev) => {
                              if (ev.key === "Enter" || ev.key === " ") {
                                ev.preventDefault();
                                setOpenBucket(bucket);
                              }
                            }}
                          />
                        </Tooltip>
                      );
                    }

                    // 稀疏桶：每个实体单独画点
                    return bucket.entities.map((e) => {
                      const x = scaleX(e.year_start);
                      const isSelected = e.id === selectedEntityId;
                      return (
                        <Tooltip
                          key={e.id}
                          title={`${e.name_zh}（${formatYear(e.year_start)}${
                            e.year_end != null && e.year_end !== e.year_start
                              ? ` — ${formatYear(e.year_end)}`
                              : ""
                          }）`}
                          placement="top"
                        >
                          <circle
                            cx={x}
                            cy={baselineY - 4}
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
                    });
                  })}
                </>
              ) : (
                /* 非 person 行（dynasty 等）：保持原样 */
                rowEntities.map((e) => {
                  const x1 = scaleX(e.year_start);
                  const isSelected = e.id === selectedEntityId;

                  if (e.year_end != null && e.year_end !== e.year_start) {
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
                })
              )}
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
        <span className="kg-timeline-legend-hint">
          密集时段折叠为柱条，点击展开
        </span>
      </div>

      {/* ── 时段抽屉 ── */}
      <Drawer
        title={
          openBucket
            ? `${formatYear(openBucket.startYear)} — ${formatYear(
                openBucket.endYear - 1
              )}\u3000${openBucket.entities.length} 位人物`
            : ""
        }
        placement="right"
        width={360}
        open={openBucket !== null}
        onClose={() => setOpenBucket(null)}
        destroyOnClose
      >
        {openBucket && (
          <List
            size="small"
            dataSource={openBucket.entities}
            renderItem={(e) => {
              const yearLabel = `${formatYear(e.year_start)}${
                e.year_end != null && e.year_end !== e.year_start
                  ? ` — ${formatYear(e.year_end)}`
                  : ""
              }`;
              const open = () => {
                onEntityClick(e.id);
                setOpenBucket(null);
              };
              return (
                <List.Item
                  style={{ cursor: "pointer", padding: "8px 4px" }}
                  tabIndex={0}
                  role="button"
                  aria-label={`${e.name_zh}\u3000${yearLabel}`}
                  onClick={open}
                  onKeyDown={(ev) => {
                    if (ev.key === "Enter" || ev.key === " ") {
                      ev.preventDefault();
                      open();
                    }
                  }}
                >
                  <span style={{ fontWeight: 500 }}>{e.name_zh}</span>
                  <span style={{ color: "#9a8e7a", fontSize: 12 }}>
                    {yearLabel}
                  </span>
                </List.Item>
              );
            }}
          />
        )}
      </Drawer>
    </div>
  );
}
