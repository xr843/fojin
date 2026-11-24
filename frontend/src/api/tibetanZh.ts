import { api } from "./client";

/**
 * 藏译汉稿（tibetan-canon-zh）。后端只做转发与缓存——浏览器不直连 GitHub
 * （大陆读者多半打不开 raw.githubusercontent.com）。AI 译稿，不进问答/检索。
 */

export const TIBETAN_ZH_REPO = "https://github.com/xr843/tibetan-canon-zh";

export interface TibetanZhItem {
  id: string;
  title: string;
  /** 作者 */
  au: string;
  /** 甘珠尔 / 丹珠尔 / 松绷 */
  part: string;
  /** 部类 */
  cat: string;
  /** 审核情况 */
  rv: string;
  md: string | null;
  pdf: string | null;
  docx: string | null;
}

export interface TibetanZhIndex {
  repo: string;
  fetched_at: number;
  stale: boolean;
  items: TibetanZhItem[];
}

export async function getTibetanZhIndex(): Promise<TibetanZhIndex> {
  const { data } = await api.get<TibetanZhIndex>("/tibetan-zh/index");
  return data;
}

export async function getTibetanZhDocument(id: string): Promise<string> {
  const { data } = await api.get<string>(`/tibetan-zh/${encodeURIComponent(id)}`, {
    responseType: "text",
    // 原样拿 Markdown，别让 axios 试着当 JSON 解析
    transformResponse: (raw) => raw,
    // 最大一部约 2.5 MB，首次还要等服务器回源
    timeout: 60_000,
  });
  return data;
}
