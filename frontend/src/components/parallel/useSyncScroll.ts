import { useEffect, useRef } from "react";
import type { AlignmentMap } from "./types";

export interface ColumnRef {
  textId: number;
  el: HTMLElement | null;
}

interface ColumnRefArray {
  current: ColumnRef[];
}

const DEBOUNCE_MS = 16;
const SUPPRESS_MS = 80;

/**
 * Find the top-most visible `[data-chunk-index]` element within the scroll container.
 * Returns its chunk_index, or null if none in view.
 */
function topVisibleChunk(el: HTMLElement): number | null {
  const chunks = el.querySelectorAll<HTMLElement>("[data-chunk-index]");
  const scrollTop = el.scrollTop;
  for (const chunk of chunks) {
    if (chunk.offsetTop + chunk.offsetHeight >= scrollTop) {
      const idx = Number(chunk.dataset.chunkIndex);
      return Number.isNaN(idx) ? null : idx;
    }
  }
  return null;
}

/**
 * Compute the scrollTop in `target` that brings chunk_index=N to the top of the viewport.
 * Returns null if the chunk node is not found.
 */
function scrollTopForChunk(target: HTMLElement, chunkIndex: number): number | null {
  const node = target.querySelector<HTMLElement>(`[data-chunk-index="${chunkIndex}"]`);
  return node ? node.offsetTop : null;
}

/**
 * Compute proportional scrollTop given a driver's scroll position.
 */
function proportionalScrollTop(driver: HTMLElement, target: HTMLElement): number {
  const driverMax = driver.scrollHeight - driver.clientHeight;
  if (driverMax <= 0) return 0;
  const pct = driver.scrollTop / driverMax;
  const targetMax = target.scrollHeight - target.clientHeight;
  return Math.round(pct * Math.max(targetMax, 0));
}

/**
 * Hybrid sync scroll: anchor-based when alignment exists between the driver's top-visible
 * chunk and a follower; proportional fallback otherwise.
 *
 * Suppress window prevents programmatic-scroll feedback loops across columns.
 */
export function useSyncScroll(refs: ColumnRefArray, map: AlignmentMap): void {
  const suppressUntil = useRef<Map<HTMLElement, number>>(new Map());
  const debounceTimer = useRef<Map<HTMLElement, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    const cols = refs.current.filter((c): c is ColumnRef & { el: HTMLElement } => !!c.el);
    if (cols.length < 2) return;

    function onScroll(driver: ColumnRef & { el: HTMLElement }) {
      const existing = debounceTimer.current.get(driver.el);
      if (existing) clearTimeout(existing);
      const timer = setTimeout(() => {
        const now = Date.now();
        const suppressEnd = suppressUntil.current.get(driver.el) ?? 0;
        if (now < suppressEnd) return;

        const driverChunk = topVisibleChunk(driver.el);
        for (const follower of cols) {
          if (follower.el === driver.el) continue;
          let targetTop: number | null = null;

          // Anchor-based
          if (driverChunk !== null) {
            const followerChunk = map[driver.textId]?.[driverChunk]?.[follower.textId];
            if (followerChunk !== undefined) {
              targetTop = scrollTopForChunk(follower.el, followerChunk);
            }
          }
          // Proportional fallback
          if (targetTop === null) {
            targetTop = proportionalScrollTop(driver.el, follower.el);
          }

          suppressUntil.current.set(follower.el, Date.now() + SUPPRESS_MS);
          follower.el.scrollTo({ top: targetTop, behavior: "auto" });
        }
      }, DEBOUNCE_MS);
      debounceTimer.current.set(driver.el, timer);
    }

    const handlers = cols.map((c) => {
      const h = () => onScroll(c);
      c.el.addEventListener("scroll", h, { passive: true });
      return { el: c.el, h };
    });

    return () => {
      for (const { el, h } of handlers) el.removeEventListener("scroll", h);
      for (const t of debounceTimer.current.values()) clearTimeout(t);
      debounceTimer.current.clear();
      suppressUntil.current.clear();
    };
    // refs and map are stable per render — rebind only when the column set / alignment changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refs.current.map((c) => c.textId).join(","), JSON.stringify(map)]);
}
