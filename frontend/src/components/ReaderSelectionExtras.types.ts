/** 划词所在的经文位置——「全藏出处」要排除本经、「报错」要写进勘误单。 */
export interface SelectionContext {
  textId: number;
  juanNum: number;
  title: string;
  cbetaId: string;
  /** CBETA 页栏行（如 0748c24）；没有行锚的文本为 null */
  lineRef: string | null;
  /** 本卷原文，「白话」用它给模型取前后文 */
  juanText?: string;
  /** 从哪里触发：阅读页划词 / 对话引文抽屉——埋点据此分开计数，30 天复查要用 */
  surface?: "reader" | "drawer";
}

/** 最终落到读者面前的那段原文最多取这么长，超出就截掉，免得「白话」拿到整段 */
export const DRAWER_TARGET_MAX = 200;

/**
 * 抽屉里「白话 / 全藏出处」作用于哪段文字：读者在抽屉里另选了文字就用选区，
 * 否则用定位到的被引那句（取原文片段，不用模型复述的引文——后者可能是转述）。
 * 多段命中（省略号缩写的引文）取首尾之间的连续原文；空白一律去掉。
 */
export function drawerTargetText(
  passage: string,
  quoteSpans: [number, number][],
  selection: string,
): { text: string; from: "selection" | "quote" } | null {
  const sel = selection.replace(/\s+/g, "");
  if (sel.length >= 2) return { text: sel.slice(0, DRAWER_TARGET_MAX), from: "selection" };
  if (quoteSpans.length === 0) return null;
  const lo = Math.min(...quoteSpans.map(([a]) => a));
  const hi = Math.max(...quoteSpans.map(([, b]) => b));
  const q = passage.slice(lo, hi).replace(/\s+/g, "");
  return q ? { text: q.slice(0, DRAWER_TARGET_MAX), from: "quote" } : null;
}

/** 全藏出处的检索词上限：太长的选区要求太多小句同时命中，几乎必然落空 */
export const SIMILAR_QUERY_MAX = 40;
/** 少于 2 字的检索词在全藏里几乎处处命中，没有意义 */
export const SIMILAR_QUERY_MIN = 2;

/**
 * 标点与空白规整为单个空格，作为小句分隔交给后端短语模式（phrase=true）。
 * 不能直接删掉标点：索引是二元组分词，标点处不产生跨标点的二元组，
 * 「有為法如夢」整串做短语匹配在原文「有為法，如夢」上必然落空。
 */
export function similarQuery(text: string): string {
  return text
    .replace(/[\s\p{P}]+/gu, " ")
    .trim()
    .slice(0, SIMILAR_QUERY_MAX)
    .trim();
}

/** 去掉分隔空格后的有效字数，用于判断是否值得检索 */
export function similarQueryChars(q: string): number {
  return q.replace(/ /g, "").length;
}

/**
 * 摘要取第一个含命中标记的片段：ES 的首个高亮片段可能落在卷首题名/译者行上
 * （「四分律卷第二十一 / 姚秦罽賓三藏佛陀耶舍」），读者看不出这条为什么算出处。
 */
export function snippetOf(highlight: string[]): string | null {
  return highlight.find((h) => h.includes("<em>")) ?? highlight[0] ?? null;
}

/** 白话选文上限，与后端 VernacularRequest.sentence 的 max_length 一致，超了会 422 */
export const VERNACULAR_MAX_CHARS = 200;
/** 送给模型判断语境的前后文字数 */
export const VERNACULAR_CONTEXT_CHARS = 150;

/**
 * 在整卷原文里定位选文，取前后文。忽略空白比对：DOM 里的选区带换行、
 * 原文按 CBETA 行硬换行，两边空白位置对不上。找不到就返回空语境——
 * 模型仍能只凭选文翻译，只是少了消歧依据。
 */
export function contextAround(
  full: string | undefined,
  selected: string,
  n: number = VERNACULAR_CONTEXT_CHARS,
): { before: string; after: string } {
  if (!full) return { before: "", after: "" };
  const flat = full.replace(/\s+/g, "");
  const sel = selected.replace(/\s+/g, "");
  const i = sel ? flat.indexOf(sel) : -1;
  if (i < 0) return { before: "", after: "" };
  return { before: flat.slice(Math.max(0, i - n), i), after: flat.slice(i + sel.length, i + sel.length + n) };
}
