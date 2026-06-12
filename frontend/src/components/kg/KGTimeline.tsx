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

import { useMemo, useRef, useState, useEffect, useLayoutEffect } from "react";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
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
function formatYear(t: TFunction, year: number): string {
  if (year < 0) return t("geo.year_bce", { n: Math.abs(year) });
  return t("geo.year_ce", { n: year });
}

// Bucket 时间范围标签：endInclusive 越过当前年份时显示「至今」
// （avoid 「公元 2049」 这种落到未来的别扭文案，与 dynasty band 「現代 — 至今」一致）
function formatBucketRange(t: TFunction, startYear: number, endInclusive: number): string {
  const now = new Date().getFullYear();
  const tail = endInclusive > now ? t("kg.to_present") : formatYear(t, endInclusive);
  return `${formatYear(t, startYear)} — ${tail}`;
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

// 直方图分桶配置 — 所有非空桶一律柱条（含 count=1）
// 历史：曾有 DENSE_THRESHOLD=6 的混合渲染（<6 画圆点），但视觉切换
// 打断阅读流。sqrt 缩放下 count=1 → ~6px（MIN_DENSE_BAR_HEIGHT 兜底），
// 相对密集峰一眼看出是单条；tooltip 仍给精确人数。统一柱条更一致。
const BUCKET_YEARS = 50;      // 50 年/桶
const MAX_BAR_HEIGHT = 60;    // px
const MIN_DENSE_BAR_HEIGHT = 6;

// 朝代分段（非重叠版本，用于底部学术信息条带）
// 边界做了简化：北宋/遼/金、南宋/金/元、隋/南北朝 等并存期取主流。
// 颜色用交错的两种暖色调，与正文柱条主色（#b85450 person）拉开。
// 朝代名是史学专名（与底层数据一致，繁体书写），不随 UI 语言切换。
const DYNASTIES: { name: string; startYear: number; endYear: number; fill: string }[] = [
  { name: "西晉", startYear: 265, endYear: 317, fill: "#e8dccc" }, // i18n-exempt
  { name: "東晉", startYear: 317, endYear: 420, fill: "#d6c9b3" }, // i18n-exempt
  { name: "南北朝", startYear: 420, endYear: 589, fill: "#e8dccc" }, // i18n-exempt
  { name: "隋", startYear: 589, endYear: 618, fill: "#d6c9b3" }, // i18n-exempt
  { name: "唐", startYear: 618, endYear: 907, fill: "#e8dccc" }, // i18n-exempt
  { name: "五代", startYear: 907, endYear: 960, fill: "#d6c9b3" }, // i18n-exempt
  { name: "北宋", startYear: 960, endYear: 1127, fill: "#e8dccc" }, // i18n-exempt
  { name: "南宋", startYear: 1127, endYear: 1279, fill: "#d6c9b3" }, // i18n-exempt
  { name: "元", startYear: 1279, endYear: 1368, fill: "#e8dccc" }, // i18n-exempt
  { name: "明", startYear: 1368, endYear: 1644, fill: "#d6c9b3" }, // i18n-exempt
  { name: "清", startYear: 1644, endYear: 1912, fill: "#e8dccc" }, // i18n-exempt
  { name: "民國", startYear: 1912, endYear: 1949, fill: "#d6c9b3" }, // i18n-exempt
  // 現代 endYear 用当前年份动态求值，tooltip 显示「至今」。
  { name: "現代", startYear: 1949, endYear: new Date().getFullYear(), fill: "#e8dccc" }, // i18n-exempt
];
const DYNASTY_LABEL_MIN_W = 8;    // 段宽 < 8px 才完全省略；其余靠 textLength 压缩

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
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);
  const [openBucket, setOpenBucket] = useState<PersonBucket | null>(null);

  // 响应容器宽度。第一次挂载时同步读 BoundingClientRect 拿到真实宽度
  // (面板 lazy mount 时 ResizeObserver 首发可能 contentRect.width=0 → 被
  // 'w > 0' 守卫挡住，width 永远卡在 useState 初值 800px，画布只用一半屏)。
  useLayoutEffect(() => {
    if (!containerRef.current) return;
    const initialW = containerRef.current.getBoundingClientRect().width;
    if (initialW > 0) setWidth(initialW);
  }, []);

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

  // wrap div 始终渲染（即使 loading/empty）— 否则 useLayoutEffect/
  // ResizeObserver 在 deps=[] 首次执行时 containerRef.current 还是 null
  // (因为 wrap 未挂载)，宽度永远卡在 useState 初值 800px。loading 状态时
  // wrap 仍存在，effect 跑、ResizeObserver 接管后续宽度变化。
  if (loading) {
    return (
      <div className="kg-timeline-wrap" ref={containerRef}>
        <div className="kg-timeline-loading">
          <Spin />
        </div>
      </div>
    );
  }

  if (!entities.length) {
    return (
      <div className="kg-timeline-wrap" ref={containerRef}>
        <div className="kg-timeline-empty">
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("kg.no_timeline_data")} />
        </div>
      </div>
    );
  }

  return (
    <div className="kg-timeline-wrap" ref={containerRef}>
      <svg
        width={width}
        height={svgHeight}
        className="kg-timeline-svg"
        aria-label={t("kg.timeline_aria")}
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
                {y < 0 ? t("kg.year_bce_short", { n: Math.abs(y) }) : y}
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
          // textLength + lengthAdjust='spacingAndGlyphs' **既能压缩也能拉伸**
          // 字符。原先无条件加 textLength=w-4 让单字短段（如「隋」）的字
          // 被拉伸到段宽，看起来字号变大。
          // 正确做法：只压缩、不拉伸 — 仅当自然字宽 > 可用宽时才设
          // textLength。汉字 fontSize=11 时近似 1 字 ≈ 11 px。
          const estimatedNaturalW = d.name.length * 11;
          const availableW = w - 4;
          const useTextLength = estimatedNaturalW > availableW;
          const textLengthValue = Math.max(availableW, 6);
          return (
            <Tooltip
              key={d.name}
              title={t("kg.dynasty_tooltip", {
                name: d.name,
                start: d.startYear,
                end: d.name === "現代" ? t("kg.to_present") : d.endYear,
              })}
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

              {/* person 行：所有非空桶一律柱条（含 count=1） */}
              {etype === "person" ? (
                <>
                  {personBuckets.map((bucket) => {
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
                        ? t("kg.bucket_more", { n: bucket.entities.length })
                        : "";
                    return (
                      <Tooltip
                        key={`bucket-${bucket.startYear}`}
                        title={t("kg.bucket_tooltip", {
                          range: formatBucketRange(t, bucket.startYear, bucket.endYear - 1),
                          n: bucket.entities.length,
                          names: `${sample}${more}`,
                        })}
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
                          aria-label={`${formatBucketRange(t, bucket.startYear, bucket.endYear - 1)} ${t("kg.n_people", { n: bucket.entities.length })}`}
                          onKeyDown={(ev) => {
                            if (ev.key === "Enter" || ev.key === " ") {
                              ev.preventDefault();
                              setOpenBucket(bucket);
                            }
                          }}
                        />
                      </Tooltip>
                    );
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
                        title={t("kg.entity_year_range", {
                          name: e.name_zh,
                          start: formatYear(t, e.year_start),
                          end: formatYear(t, e.year_end),
                        })}
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
                      title={t("kg.entity_year_single", {
                        name: e.name_zh,
                        year: formatYear(t, e.year_start),
                      })}
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
            {etype === "person" ? t("geo.type_person") : etype === "dynasty" ? t("geo.type_dynasty") : etype}
            <span className="kg-timeline-legend-count">
              {rowGroups[etype].length}
            </span>
          </span>
        ))}
        <span className="kg-timeline-legend-hint">
          {t("kg.timeline_legend_hint")}
        </span>
      </div>

      {/* ── 时段抽屉 ── */}
      <Drawer
        title={
          openBucket
            ? t("kg.bucket_drawer_title", {
                range: formatBucketRange(t, openBucket.startYear, openBucket.endYear - 1),
                n: openBucket.entities.length,
              })
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
              const yearLabel = `${formatYear(t, e.year_start)}${
                e.year_end != null && e.year_end !== e.year_start
                  ? ` — ${formatYear(t, e.year_end)}`
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
