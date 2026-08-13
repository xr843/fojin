import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

/** 思考过程片段活窗 —— 打字机式匀速吐字。
 *
 * 后端按 REASONING_EMIT_INTERVAL_S 聚合发帧，一帧几十字；直接整块渲染就是
 * 使用者反馈的「一段段文本不断地跳动」。这里把新到的文本先进缓冲，以 ~30Hz
 * 步进追赶：步长与积压成正比（积压越多走得越快，追平后逐字），视觉上与主流
 * LLM 界面的思考流一致，且缓冲永不丢字。
 *
 * 护栏与母组件相同：只在等待期挂载（content 仍是哨兵），正文一到整块卸载；
 * aria-hidden —— 读屏听「已思考 N 秒」即可，逐字变动的中间结论只会淹没读屏。
 */
const TICK_MS = 33;
// 追赶分母：每 tick 吐出 backlog/40（至少 1 字）。等效吐字速率 ≈
// backlog×0.75/s + 30 字/s 下限，对上游 40-70 字/s 的推理吞吐，稳态积压
// 约几十字（不到一秒的滞后），看起来是「实时在写」。
const CATCHUP_DIVISOR = 40;

export default function ReasoningExcerpt({ text }: { text: string }) {
  const { t } = useTranslation();
  // 减动效偏好：整段直出，不做打字机（放 useState 初始化器：渲染期不读环境）。
  const [reduceMotion] = useState(
    () =>
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [shown, setShown] = useState(0);
  // interval 回调要读最新的 text，但不能因 text 变化重建 interval（重建会打乱
  // 节拍）—— 经典的 latest-ref 模式，写入放 effect 里过 React Compiler 的
  // 「渲染期不写 ref」检查。
  const textRef = useRef(text);
  useEffect(() => {
    textRef.current = text;
  }, [text]);

  useEffect(() => {
    if (reduceMotion) return;
    const id = setInterval(() => {
      setShown((s) => {
        const len = textRef.current.length;
        if (s >= len) return s;
        return Math.min(len, s + Math.max(1, Math.ceil((len - s) / CATCHUP_DIVISOR)));
      });
    }, TICK_MS);
    return () => clearInterval(id);
  }, [reduceMotion]);

  const visible = reduceMotion ? text : text.slice(0, shown);
  return (
    <div className="chat-reasoning-excerpt" aria-hidden="true">
      <span className="chat-reasoning-excerpt-label">{t("chat.reasoning_excerpt_label")}</span>
      <div className="chat-reasoning-excerpt-clip">
        <div className="chat-reasoning-excerpt-text">
          {visible}
          <span className="chat-reasoning-caret">▌</span>
        </div>
      </div>
    </div>
  );
}
