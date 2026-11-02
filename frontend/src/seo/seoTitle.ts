import { localizeHan } from "../utils/hanScript";
import type { SeoLang } from "./langUrl";

// 从 langUrl.ts 拆出：它被 main.tsx 静态导入，带着 OpenCC 会让每个页面首屏多下 ~550 KB。
/**
 * Sutra titles are stored in traditional script. The simplified page shows
 * 「简体（繁體）」— same rule as the server's `localize_title`, so the title a
 * JS-rendering crawler sees matches the one in the served HTML.
 */
export function seoTitle(title: string, lang: SeoLang): string {
  if (lang !== "zh" || !title) return title;
  const simplified = localizeHan(title, "zh");
  return simplified === title ? title : `${simplified}（${title}）`;
}
