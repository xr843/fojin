import type { TimelineItem } from "../../api/stats";

interface TimelineTooltipProps {
  item: TimelineItem | null;
  x: number;
  y: number;
  visible: boolean;
}

export default function TimelineTooltip({
  item,
  x,
  y,
  visible,
}: TimelineTooltipProps) {
  if (!visible || !item) return null;

  const yearRange =
    item.year_start != null
      ? item.year_end != null && item.year_end !== item.year_start
        ? `${item.year_start} – ${item.year_end}`
        : `${item.year_start}`
      : null;

  // Keep tooltip within viewport
  const adjustedX = Math.min(x, window.innerWidth - 300);
  const adjustedY = y > window.innerHeight - 120 ? y - 80 : y + 16;

  return (
    <div
      className="timeline-tooltip"
      style={{
        left: adjustedX,
        top: adjustedY,
      }}
    >
      <div className="tt-title">{item.name_zh}</div>
      <div className="tt-meta">
        {item.dynasty && <div>{item.dynasty}</div>}
        {item.translator && <div>{item.translator}</div>}
        {item.entity_type && <div>{item.entity_type}</div>}
        {yearRange && <div>{yearRange}</div>}
      </div>
    </div>
  );
}
