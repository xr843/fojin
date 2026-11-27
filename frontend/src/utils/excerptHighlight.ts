/**
 * 个人摘录在阅读页里的定位与高亮。
 *
 * 摘录存的是「行号 + 划选时的原文」。重新打开时在经文里找回那段原文：
 * - 去掉空白再比（CBETA 有硬换行，选区 toString 会带进换行/空格）；
 * - 跳过校勘标记 <sup class="apparatus-marker">[n]</sup>，原文里的「[n]」同样去掉；
 *   行首标签是 CSS ::before 画的，不在文字里，不用管；
 * - 从记下的那一行起往后找，找不到（行号重导后变了）再退回全卷找第一处；
 * - 夹注 <span class="inline-note">（2026-11-27 起显示）：先连夹注一起找（新划选会带进夹注），
 *   找不到再跳过夹注找——此前存的摘录里没有夹注。
 *
 * 高亮用 CSS Custom Highlight API：不改经文 DOM（经文的行号锚点、划词、续读都靠 DOM），
 * 不支持的浏览器（Firefox < 140 等）不显示底纹，摘录本身照常保存、在「我的摘录」里可见。
 */

export const EXCERPT_HIGHLIGHT_NAME = "fojin-excerpt";

export function normalizeQuote(s: string): string {
  return s.replace(/\[\d+\]/g, "").replace(/\s+/g, "");
}

interface CharPos {
  node: Text;
  offset: number;
}

function indexContainer(container: HTMLElement, lineRef: string | null | undefined, skipNotes = false) {
  const chars: string[] = [];
  const map: CharPos[] = [];
  let lineStart = -1;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      if (n.nodeType === Node.ELEMENT_NODE) {
        const cl = (n as Element).classList;
        if (cl.contains("apparatus-marker") || (skipNotes && cl.contains("inline-note"))) {
          return NodeFilter.FILTER_REJECT; // 跳过整个子树
        }
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let n: Node | null;
  while ((n = walker.nextNode())) {
    if (n.nodeType === Node.ELEMENT_NODE) {
      const el = n as HTMLElement;
      if (lineRef && lineStart < 0 && el.classList.contains("cbeta-line") && el.dataset.ref === lineRef) {
        lineStart = chars.length;
      }
      continue;
    }
    const text = n.textContent ?? "";
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (/\s/.test(ch)) continue;
      chars.push(ch);
      map.push({ node: n as Text, offset: i });
    }
  }
  return { str: chars.join(""), map, lineStart };
}

/** 在 container 里找回摘录原文，返回覆盖它的 Range；找不到返回 null。 */
export function locateQuote(container: HTMLElement, quote: string, lineRef?: string | null): Range | null {
  const q = normalizeQuote(quote);
  if (!q) return null;
  for (const skipNotes of [false, true]) {
    const { str, map, lineStart } = indexContainer(container, lineRef, skipNotes);
    let at = lineStart >= 0 ? str.indexOf(q, lineStart) : -1;
    if (at < 0) at = str.indexOf(q);
    if (at >= 0) return rangeOf(map, at, q.length);
  }
  return null;
}

function rangeOf(map: CharPos[], at: number, len: number): Range {
  const start = map[at];
  const end = map[at + len - 1];
  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset + 1);
  return range;
}

type HighlightCtor = new (...ranges: Range[]) => unknown;
type HighlightRegistry = { set(name: string, h: unknown): void; delete(name: string): void };

function registry(): { Highlight: HighlightCtor; highlights: HighlightRegistry } | null {
  const w = window as unknown as { Highlight?: HighlightCtor; CSS?: { highlights?: HighlightRegistry } };
  if (typeof w.Highlight !== "function" || !w.CSS?.highlights) return null;
  return { Highlight: w.Highlight, highlights: w.CSS.highlights };
}

/** 把这些摘录画成底纹；返回实际找到的条数。传空数组即清除。 */
export function paintExcerpts(
  container: HTMLElement,
  excerpts: { quote: string; line_ref?: string | null }[],
): number {
  const ranges = excerpts
    .map((e) => locateQuote(container, e.quote, e.line_ref))
    .filter((r): r is Range => r !== null);
  const reg = registry();
  if (reg) {
    if (ranges.length) reg.highlights.set(EXCERPT_HIGHLIGHT_NAME, new reg.Highlight(...ranges));
    else reg.highlights.delete(EXCERPT_HIGHLIGHT_NAME);
  }
  return ranges.length;
}

export function clearExcerptPaint(): void {
  registry()?.highlights.delete(EXCERPT_HIGHLIGHT_NAME);
}
