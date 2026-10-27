import type { Link, Parent, PhrasingContent, Root, Text } from "mdast";

/**
 * GFM 的裸网址只在空白处结束；中文行文里网址后面通常直接跟全角标点或汉字，不留空格，
 * 于是「（https://rywiki.tsadra.org/）和 Sacred…」整串成了一个链接，href 带着「）和」点开就 404。
 * 生产 180 天：AI 回答里 850 个网址有 778 个（91.5%）这样被吞，紧跟的全是全角「）」；
 * 网址本身合法含汉字的一次都没有（模型给的中文路径都已百分号编码）。
 *
 * 所以在 remark-gfm 之后，把「链接文字就是网址本身」的自动链接截在第一个 CJK 字符处，
 * 截下的部分还原成正文；那段正文里若还有网址（同样没被空格隔开而被吞进来的），再单独成链。
 * 显式的 [文字](网址) 链接不碰。
 */

// CJK 符号与标点、全角形式、汉字（基本区 + 扩展 A）、CJK 兼容表意文字。
const CJK = /[\u3000-\u303f\uff00-\uffef\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const URL_IN_TEXT = /(?:https?:\/\/|www\.)[^\s\u3000-\u303f\uff00-\uffef\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+/g;

function isLiteralAutolink(node: Link): node is Link & { children: [Text] } {
  const only = node.children.length === 1 ? node.children[0] : undefined;
  if (!only || only.type !== "text") return false;
  return node.url === only.value || node.url === `http://${only.value}` || node.url === `mailto:${only.value}`;
}

function linkify(text: string): PhrasingContent[] {
  const out: PhrasingContent[] = [];
  let last = 0;
  for (const m of text.matchAll(URL_IN_TEXT)) {
    const raw = m[0].replace(/[.,;:!?]+$/, ""); // 句末的 ASCII 标点不算网址，与 GFM 一致
    if (!raw) continue;
    if (m.index! > last) out.push({ type: "text", value: text.slice(last, m.index) });
    const url = raw.startsWith("www.") ? `http://${raw}` : raw;
    out.push({ type: "link", url, children: [{ type: "text", value: raw }] });
    last = m.index! + raw.length;
  }
  if (last < text.length) out.push({ type: "text", value: text.slice(last) });
  return out;
}

function walk(parent: Parent): void {
  for (let i = 0; i < parent.children.length; i++) {
    const node = parent.children[i];
    if (node.type === "link" && isLiteralAutolink(node)) {
      const label = node.children[0].value;
      const cut = label.search(CJK);
      if (cut > 0) {
        const head = label.slice(0, cut);
        node.children[0].value = head;
        node.url = node.url.slice(0, node.url.length - label.length + cut);
        const tail = linkify(label.slice(cut));
        parent.children.splice(i + 1, 0, ...(tail as Parent["children"]));
        i += tail.length;
      }
      continue;
    }
    if ("children" in node) walk(node as Parent); // code / inlineCode carry `value`, not children: never entered
  }
}

export default function remarkCjkAutolinkBoundary() {
  return (tree: Root) => walk(tree);
}
