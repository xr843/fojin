/**
 * 把正文、校注里夹着的藏文（U+0F00–U+0FFF 连续段）包成 <span lang="bo" class="tz-bo-inline">。
 *
 * 为什么：汉文段落里的藏文词只能靠浏览器逐字回退字体，Windows 上落到 Microsoft Himalaya，
 * 同字号下字形只有汉字的六成高，校注里的藏文几乎看不清（2026-11-24 真 Chrome 实测）。
 * 包上 lang="bo" 才能单独放大、并让读屏按藏文读。整段藏文引用块（blockquote）
 * 已经整块标了 lang="bo"，这里跳过不再重复包。
 */

type HNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HNode[];
};

const RUN = /[ༀ-࿿](?:[ༀ-࿿\s]*[ༀ-࿿])?/g;

function splitText(value: string): HNode[] | null {
  RUN.lastIndex = 0;
  if (!RUN.test(value)) return null;
  RUN.lastIndex = 0;
  const out: HNode[] = [];
  let last = 0;
  for (const m of value.matchAll(RUN)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ type: "text", value: value.slice(last, start) });
    out.push({
      type: "element",
      tagName: "span",
      properties: { lang: "bo", className: ["tz-bo-inline"] },
      children: [{ type: "text", value: m[0] }],
    });
    last = start + m[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function walk(node: HNode): void {
  if (!node.children) return;
  const next: HNode[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value) {
      const parts = splitText(child.value);
      if (parts) {
        next.push(...parts);
        continue;
      }
    } else if (child.type === "element" && child.tagName !== "blockquote" && child.tagName !== "code" && child.tagName !== "pre") {
      walk(child);
    }
    next.push(child);
  }
  node.children = next;
}

export default function rehypeTibetanInline() {
  return (tree: HNode) => walk(tree);
}
