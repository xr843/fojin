/**
 * 搜索关键词长度上限。与后端 `Query(max_length=200)`（backend/app/api/search*.py）一致。
 * Pydantic 按 Python 字符串长度算，也就是 Unicode 码点；JS 的 .length 按 UTF-16
 * 码元算，扩展区汉字会算成 2——所以这里一律用 Array.from 数码点。
 *
 * 超过上限的请求后端直接 422，前端曾把它显示成「搜索服务暂时不可用，请稍后重试」，
 * 而用户重试多少次都一样（2026-10-12 用户截图：贴了一段《瑜伽師地論》）。
 * 贴整段经文来查正是佛津用户的典型用法，所以不拒绝，而是截到上限内再搜。
 */
export const SEARCH_QUERY_MAX = 200;

// 句末标点优先，其次句中停顿。截断点太靠前（不到上限的 40%）就宁可硬切，
// 免得一段长文只剩开头几个字去搜。
const SENTENCE_END = /[。！？；!?;]/u;
const CLAUSE_END = /[，、,：:]/u;
const MIN_KEEP_RATIO = 0.4;

export interface ClampedQuery {
  /** 实际发给后端的关键词（≤ SEARCH_QUERY_MAX 个码点）。 */
  text: string;
  /** 是否被截断过。 */
  truncated: boolean;
  /** 原始关键词（trim 后）的码点数。 */
  total: number;
}

function lastBoundary(chars: string[], re: RegExp): number {
  for (let i = chars.length - 1; i >= 0; i--) {
    if (re.test(chars[i])) return i;
  }
  return -1;
}

export function clampSearchQuery(raw: string, max: number = SEARCH_QUERY_MAX): ClampedQuery {
  const q = raw.trim();
  const chars = Array.from(q);
  if (chars.length <= max) return { text: q, truncated: false, total: chars.length };

  const head = chars.slice(0, max);
  const minKeep = Math.ceil(max * MIN_KEEP_RATIO);
  let cut = lastBoundary(head, SENTENCE_END);
  if (cut + 1 < minKeep) cut = lastBoundary(head, CLAUSE_END);
  const text = (cut + 1 >= minKeep ? head.slice(0, cut + 1) : head).join("").trim();
  return { text, truncated: true, total: chars.length };
}
