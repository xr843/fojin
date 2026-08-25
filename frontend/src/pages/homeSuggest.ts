import type { SearchSuggestionItem, SearchSuggestionType } from "../api/client";

/**
 * 首页联想框的选项构造 —— 纯函数，好测。
 *
 * 2026-08-25 生产实测：输入「金刚」出来的是 金刚 / 金刚石 / 金刚砂 / 金刚宝石 / 金刚怒目，
 * 全站最热的《金刚经》根本不在列。后端现在按 别名正典经名 → 精确词头 → 经名 → 前缀词头
 * → 热门问题 排序并带 type；这里按 type 分三组（Spotlight / Algolia 那种分组下拉），
 * 另加一行「问小津：{q}」—— 首页主输入框此前只会搜索，而产品核心是问答。
 *
 * 「问小津」行的位置：看起来像个问题（带问号、疑问词）就放最前 —— 下拉是虚拟列表，
 * 十条联想加组头之后的一行要滚动才看得见，放最后等于没有；像经名/词头就放最后，
 * 不挤占联想。
 */

/** 「问小津」行的 value 前缀：AutoComplete 的 value 必须唯一且不能与联想词撞车。 */
export const ASK_PREFIX = " ask:";

const GROUP_ORDER: SearchSuggestionType[] = ["title", "term", "question"];
const GROUP_LABEL_KEY: Record<SearchSuggestionType, string> = {
  title: "home.suggest_group_title",
  term: "home.suggest_group_term",
  question: "home.suggest_group_question",
};

// 问号，或常见疑问词/句式。经名、词头、人名不会命中。
const QUESTION_RE = /[?？]|是什么|什么是|为什么|為什麼|为何|如何|怎么|怎樣|怎样|哪|吗$|嗎$|意思|区别|區別|含义|含義|\bwhat\b|\bwhy\b|\bhow\b|\bwho\b/i;

export function looksLikeQuestion(q: string): boolean {
  const s = q.trim();
  if (!s) return false;
  return QUESTION_RE.test(s) || s.length >= 12;
}

export interface SuggestOption {
  value: string;
  label: string;
}
export interface SuggestGroup {
  label: string;
  options: SuggestOption[];
}

type T = (key: string, opts?: Record<string, unknown>) => string;

export function buildHomeSuggestOptions(items: SearchSuggestionItem[], query: string, t: T): SuggestGroup[] {
  const q = query.trim();
  if (!q) return [];
  const groups: SuggestGroup[] = [];
  for (const type of GROUP_ORDER) {
    const options = items.filter((i) => i.type === type).map((i) => ({ value: i.value, label: i.value }));
    if (options.length > 0) groups.push({ label: GROUP_LABEL_KEY[type], options });
  }
  const ask: SuggestGroup = {
    label: "home.suggest_group_ask",
    options: [{ value: `${ASK_PREFIX}${q}`, label: t("home.suggest_ask", { q }) }],
  };
  if (looksLikeQuestion(q)) groups.unshift(ask);
  else groups.push(ask);
  return groups;
}

/** 选中的是「问小津」行则还原问句，否则 null。 */
export function askQueryFrom(value: string): string | null {
  if (!value || !value.startsWith(ASK_PREFIX)) return null;
  const q = value.slice(ASK_PREFIX.length).trim();
  return q || null;
}

/** 旧后端副本（滚动部署期间）只回 suggestions 字符串：全当经名，不丢联想。 */
export function itemsFromSuggestResponse(data: {
  suggestions?: string[];
  items?: SearchSuggestionItem[];
}): SearchSuggestionItem[] {
  if (Array.isArray(data.items)) return data.items;
  return (data.suggestions ?? []).map((value) => ({ value, type: "title" as const }));
}
