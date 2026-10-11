import { useEffect, useState } from "react";

/** 离页尾不到这么多像素就让浮钮出现：无处可滑时不能让入口消失。 */
const REVEAL_NEAR_END = 120;
/** 小于这个位移的滚动（惯性尾巴、地址栏伸缩）不改变收起状态。 */
const SCROLL_JITTER = 8;

/**
 * 浮钮「往下读时收起、往回滑 / 回到顶部 / 到页尾时出现」，与阅读器 #1295 同一手法
 * （阅读器那份写在 TextReaderPage 里、另有 120px 起收的门槛，这里从顶部一滑就收）。
 * 只读 window.scrollY：用到它的页面在窄屏上都是 document 在滚。
 * enabled=false（宽屏）时恒为 false，监听也不挂。
 */
export function useTuckOnScrollDown(enabled: boolean): boolean {
  const [tucked, setTucked] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let last = window.scrollY;
    const onScroll = () => {
      const y = window.scrollY;
      const nearEnd = document.documentElement.scrollHeight - (y + window.innerHeight) < REVEAL_NEAR_END;
      if (nearEnd || y <= 0) {
        setTucked(false);
        last = y;
        return;
      }
      const delta = y - last;
      if (Math.abs(delta) < SCROLL_JITTER) return;
      setTucked(delta > 0);
      last = y;
    };
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });
    return () => window.removeEventListener("scroll", onScroll, { capture: true });
  }, [enabled]);
  return enabled && tucked;
}
