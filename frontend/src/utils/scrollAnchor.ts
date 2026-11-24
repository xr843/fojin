/**
 * 版面变化（侧栏开合、栏宽改变）前后，让读者正在看的那一处留在屏幕上原来的位置。
 *
 * 2026-11-21 用户录屏反馈：阅读页选中「有十四音名為字義」点「问小津」，AI 面板一开，
 * 经文栏变窄重新排行，真正滚动的元素也从整页换成了 .reader-container，页面停在
 * 好几段之后，选中的那句被甩出视野。
 *
 * 做法：变化前记一个锚点（优先用选区；没有选区就取视口 1/3 高处的那个字）及其
 * 离视口顶的距离；变化后量锚点新位置，把差值滚回去。锚点用 Range 而不是段落元素：
 * 长段落重新排行后，段首的位置不变而那一句可能下移好几行。
 */

export interface ScrollAnchor {
  range: Range;
  /** 锚点顶边离视口顶的距离（px） */
  top: number;
}

function rangeTop(range: Range): number | null {
  // 折叠的 Range 在部分浏览器里 getBoundingClientRect 全 0，取第一个 client rect
  const rects = range.getClientRects();
  if (rects.length > 0) return rects[0].top;
  const r = range.getBoundingClientRect();
  return r.width === 0 && r.height === 0 && r.top === 0 ? null : r.top;
}

function caretRangeAt(x: number, y: number): Range | null {
  const doc = document as Document & {
    caretPositionFromPoint?: (x: number, y: number) => { offsetNode: Node; offset: number } | null;
    caretRangeFromPoint?: (x: number, y: number) => Range | null;
  };
  let node: Node | null = null;
  let offset = 0;
  if (typeof doc.caretPositionFromPoint === "function") {
    const p = doc.caretPositionFromPoint(x, y);
    if (p) { node = p.offsetNode; offset = p.offset; }
  } else if (typeof doc.caretRangeFromPoint === "function") {
    const r = doc.caretRangeFromPoint(x, y);
    if (r) { node = r.startContainer; offset = r.startOffset; }
  }
  if (!node) return null;
  const range = document.createRange();
  if (node.nodeType === Node.TEXT_NODE) {
    const len = (node.textContent ?? "").length;
    // 包住一个字：折叠 Range 的位置在换行处不可靠
    const start = Math.min(offset, Math.max(0, len - 1));
    range.setStart(node, start);
    range.setEnd(node, Math.min(len, start + 1));
  } else {
    range.selectNode(node);
  }
  return range;
}

/**
 * 记锚点。preferred（通常是最近一次划选的 Range）还在 container 里且在视口内就用它，
 * 否则取 container 里视口 1/3 高处的字。
 */
export function captureScrollAnchor(container: HTMLElement, preferred?: Range | null): ScrollAnchor | null {
  const vh = window.innerHeight;
  if (preferred && container.contains(preferred.commonAncestorContainer)) {
    const top = rangeTop(preferred);
    if (top !== null && top >= 0 && top <= vh) return { range: preferred.cloneRange(), top };
  }
  const box = container.getBoundingClientRect();
  const y = Math.min(Math.max(vh / 3, box.top + 1), box.bottom - 1);
  if (y <= 0 || y >= vh) return null;
  const range = caretRangeAt(box.left + Math.min(40, box.width / 2), y);
  if (!range || !container.contains(range.commonAncestorContainer)) return null;
  const top = rangeTop(range);
  return top === null ? null : { range, top };
}

/** 找 el 的实际滚动祖先；没有就是整页滚动。 */
export function findScrollContainer(el: HTMLElement): HTMLElement | null {
  let p = el.parentElement;
  while (p) {
    const style = getComputedStyle(p);
    if ((style.overflowY === "auto" || style.overflowY === "scroll") && p.scrollHeight > p.clientHeight) {
      return p;
    }
    p = p.parentElement;
  }
  return null;
}

/** 把锚点滚回记下的位置。先滚内层滚动盒，剩下的差值（滚动盒到底/到顶）交给整页。 */
export function restoreScrollAnchor(anchor: ScrollAnchor, container: HTMLElement): void {
  const now = rangeTop(anchor.range);
  if (now === null) return;
  let delta = now - anchor.top;
  if (Math.abs(delta) < 1) return;
  const scroller = findScrollContainer(container);
  if (scroller) {
    const before = scroller.scrollTop;
    scroller.scrollTop = before + delta;
    delta -= scroller.scrollTop - before;
  }
  if (Math.abs(delta) >= 1) window.scrollBy(0, delta);
}
