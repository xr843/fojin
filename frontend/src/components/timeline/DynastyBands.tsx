import type { ScaleLinear } from "d3";
import { DYNASTIES } from "../../data/dynasty_years";

const NON_CHINESE_KEYS = new Set(["india", "japan", "korea", "tibet"]);

interface DynastyBandsProps {
  xScale: ScaleLinear<number, number>;
  height: number;
}

export default function DynastyBands({ xScale, height }: DynastyBandsProps) {
  const [domainStart, domainEnd] = xScale.domain() as [number, number];

  const visible = DYNASTIES.filter(
    (d) => d.end > domainStart && d.start < domainEnd,
  );

  return (
    <g className="dynasty-bands">
      {visible.map((d) => {
        const x = xScale(Math.max(d.start, domainStart));
        const xEnd = xScale(Math.min(d.end, domainEnd));
        const w = xEnd - x;
        if (w < 1) return null;

        const isNonChinese = NON_CHINESE_KEYS.has(d.key);
        const opacity = isNonChinese ? 0.04 : 0.08;
        const midX = x + w / 2;

        return (
          <g key={d.key}>
            <rect
              x={x}
              y={0}
              width={w}
              height={height}
              fill={d.color}
              opacity={opacity}
            />
            {w > 24 && (
              <text
                x={midX}
                y={14}
                textAnchor="middle"
                fontSize={11}
                fontFamily='"Noto Serif SC", serif'
                fill={d.color}
                opacity={0.6}
              >
                {d.name_zh}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}
