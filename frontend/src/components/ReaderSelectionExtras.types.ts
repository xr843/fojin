/** 划词所在的经文位置——「全藏出处」要排除本经、「报错」要写进勘误单。 */
export interface SelectionContext {
  textId: number;
  juanNum: number;
  title: string;
  cbetaId: string;
  /** CBETA 页栏行（如 0748c24）；没有行锚的文本为 null */
  lineRef: string | null;
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
