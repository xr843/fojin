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
