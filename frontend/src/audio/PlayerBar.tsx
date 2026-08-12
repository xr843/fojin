import { CloseOutlined, PauseCircleOutlined, PlayCircleOutlined, SoundOutlined } from "@ant-design/icons";
import { Button, Select, Slider, Tooltip } from "antd";
import { useTranslation } from "react-i18next";

import { useAudioPlayer } from "./useAudioPlayback";

const RATES = [0.75, 1, 1.25, 1.5];

function fmt(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** 底部读诵播放条。只在有曲目时渲染；由 Layout 挂载在 Provider 内。 */
export default function PlayerBar() {
  const { t } = useTranslation();
  const { track, playing, rate, positionMs, toggle, seek, setRate, stop } = useAudioPlayer();

  if (!track) return null;

  return (
    <div className="reader-audio-bar" role="region" aria-label={t("reader.audio.button")}>
      <Button
        type="text"
        icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
        onClick={toggle}
        aria-label={playing ? t("reader.audio.pause") : t("reader.audio.play")}
      />
      <div className="reader-audio-meta">
        <div className="reader-audio-title">{track.title}</div>
        <div className="reader-audio-note">
          {/* 诚信标注：不得让用户以为是法师读诵 */}
          <SoundOutlined /> {t("reader.audio.synthetic_label")}
          {/* ⚖️ 许可证义务：模型声明必须真实渲染，不是可选文案 */}
          <Tooltip title={t("reader.audio.model_disclaimer")}>
            <span
              className="reader-audio-license"
              aria-label={t("reader.audio.model_disclaimer")}
            >
              ⓘ
            </span>
          </Tooltip>
        </div>
      </div>
      <span className="reader-audio-time">{fmt(positionMs)}</span>
      <Slider
        className="reader-audio-progress"
        min={0}
        max={track.audio.duration_ms}
        value={Math.min(positionMs, track.audio.duration_ms)}
        tooltip={{ formatter: (v) => fmt(Number(v ?? 0)) }}
        onChange={seek}
      />
      <span className="reader-audio-time">{fmt(track.audio.duration_ms)}</span>
      <Tooltip title={t("reader.audio.speed")}>
        <Select
          size="small"
          value={rate}
          onChange={setRate}
          options={RATES.map((r) => ({ value: r, label: `${r}×` }))}
          style={{ width: 76 }}
        />
      </Tooltip>
      <Button
        type="text"
        icon={<CloseOutlined />}
        onClick={stop}
        aria-label={t("reader.audio.close")}
      />
    </div>
  );
}
