import { scriptForLanguage } from "../utils/hanLocale";

/**
 * 首页功能卡预览文字的两个小工具（纯函数，便于测试）。
 */

/** 简体界面用后端转好的简体版，繁体界面用原文；简体版缺失（旧缓存）时回退原文。 */
export function pickHan(original: string, hans: string | null | undefined, language: string): string {
  if (scriptForLanguage(language) === "traditional") return original;
  return hans || original;
}

/** 估算显示宽度：CJK/全角按 1，其余（拉丁字母、数字、空格）按约半格。 */
function displayWidth(s: string): number {
  let w = 0;
  for (const ch of s) w += /[⺀-鿿豈-﫿＀-￯]/.test(ch) ? 1 : 0.55;
  return w;
}

/**
 * 数据源卡：从随机抽到的名字里依次取，总宽不超过 budget（约等于两行减去「667 个来源 ·」前缀），
 * 至少保留一个。此前固定取 3 个，经常在第二行中途被省略号切断成「8400…」。
 */
export function fitSourceNames(names: string[], budget = 14): string[] {
  const out: string[] = [];
  let used = 0;
  for (const n of names) {
    const w = displayWidth(n) + (out.length ? 1 : 0); // 「、」
    if (out.length && used + w > budget) break;
    out.push(n);
    used += w;
  }
  return out;
}
