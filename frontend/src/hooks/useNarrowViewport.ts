import { useEffect, useState } from "react";

/**
 * 阅读器「侧栏不再并排」的断点。与 reader.css 的 Tablet 块（max-width: 1024px）
 * 保持同一个数，改一处必须改另一处。
 */
export const NARROW_VIEWPORT_QUERY = "(max-width: 1024px)";

/**
 * 一次性判断，供 useState 惰性初值用。matchMedia 缺失（jsdom / SSR）时按宽屏处理 ——
 * 宽屏是原有行为，缺环境时保持原样比猜成窄屏安全。
 */
export function isNarrowViewport(query: string = NARROW_VIEWPORT_QUERY): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(query).matches;
}

/** 响应式的 isNarrowViewport：断点跨越时跟着变（与 useEffectiveTheme 同一手法）。 */
export function useNarrowViewport(query: string = NARROW_VIEWPORT_QUERY): boolean {
  const [narrow, setNarrow] = useState(() => isNarrowViewport(query));
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setNarrow(e.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return narrow;
}
