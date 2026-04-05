import { useEffect, useRef, useCallback } from "react";
import { Slider, Button, Switch, Tooltip } from "antd";
import { CaretRightOutlined, PauseOutlined, InfoCircleOutlined } from "@ant-design/icons";

interface TimeSliderProps {
  min: number;
  max: number;
  value: number | null;
  isPlaying: boolean;
  onChange: (year: number | null) => void;
  onPlayToggle: () => void;
}

function formatYear(year: number): string {
  if (year < 0) return `公元前${Math.abs(year)}年`;
  return `公元${year}年`;
}

export default function TimeSlider({
  min,
  max,
  value,
  isPlaying,
  onChange,
  onPlayToggle,
}: TimeSliderProps) {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  const tick = useCallback(() => {
    const cur = valueRef.current;
    if (cur === null) return;
    if (cur + 25 > max) {
      onPlayToggle();
      return;
    }
    onChange(cur + 25);
  }, [max, onChange, onPlayToggle]);

  const enabled = value !== null;

  useEffect(() => {
    if (isPlaying && enabled) {
      timerRef.current = setInterval(tick, 200);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPlaying, enabled, tick]);

  const handleSwitchChange = (checked: boolean) => {
    if (checked) {
      onChange(min);
    } else {
      onChange(null);
    }
  };

  return (
    <div className="kg-time-slider">
      <div className="kg-time-slider-row">
        <Switch
          size="small"
          checked={enabled}
          onChange={handleSwitchChange}
        />
        <span className="kg-time-slider-label">时间筛选</span>
        <Tooltip title="仅对有年代数据的实体生效（约 300 个人物/寺院）。无年代的实体始终显示。">
          <InfoCircleOutlined style={{ color: "#999", fontSize: 12, cursor: "help" }} />
        </Tooltip>

        {enabled && (
          <>
            <Button
              className="kg-time-play-btn"
              type="text"
              size="small"
              icon={isPlaying ? <PauseOutlined /> : <CaretRightOutlined />}
              onClick={onPlayToggle}
            />
            <span className="kg-time-current">
              {formatYear(value)}
            </span>
            <div className="kg-time-slider-track">
              <Slider
                min={min}
                max={max}
                step={25}
                value={value}
                onChange={(v) => onChange(v as number)}
                tooltip={{ formatter: (v) => v != null ? formatYear(v) : "" }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
