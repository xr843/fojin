// 界面语言检测的两处本地规则（issue #1340）。独立成文件，是为了不初始化 i18next 就能单测。

/**
 * 记录「用户主动选的界面语言」的 localStorage 键。
 *
 * 故意不用检测器默认的 `i18nextLng`：旧配置会把**自动检测**结果也写进那个键（浏览器
 * 语言列表英文在前 → 首访就存下 en），分不清哪些是用户选的、哪些是被动写入的。
 * 换新键等于把这些被动值一次性作废；代价是主动选过语言的老用户需要再选一次。
 */
export const UI_LANG_STORAGE_KEY = "fojin.uiLang";
const LEGACY_STORAGE_KEY = "i18nextLng";

const HANT_REGIONS = /^zh-(tw|hk|mo|hant)/i;

/**
 * 浏览器语言列表里只要有中文，就用中文——不管它排第几。
 *
 * 中文 Windows 上很常见的配置是浏览器界面装成英文、语言列表 `["en-GB","zh-CN",…]`
 * （2026-10-19 站长本机 Chrome 实测即如此）。标准的 navigator 检测取第一个受支持
 * 的语言 → 英文，于是中文读者打开就是英文界面（#1340）。佛津的读者以华语为主，
 * 列表里出现中文就说明读得懂中文，优先给中文；台港澳与显式 Hant 给繁体。
 * 列表里没有中文时返回 undefined，交给后面的标准 navigator 检测。
 */
export function chineseFromLanguages(langs: readonly string[] | undefined): string | undefined {
  for (const l of langs ?? []) {
    if (!/^zh\b/i.test(l)) continue;
    return HANT_REGIONS.test(l) ? "zh-Hant" : "zh";
  }
  return undefined;
}

/**
 * 记住用户**主动选择**的界面语言。
 *
 * 检测器不再自动缓存（i18n.ts 里 caches: []）：否则落地一次 `?lang=en` 链接
 * （搜索结果、分享链接、hreflang 变体）就会把 en 写进 localStorage，之后打开
 * 不带参数的网址也一直是英文，用户以为「切换无效」（#1340）。`?lang=` 现在只管
 * 这一次访问；只有点语言菜单才落盘。
 */
export function rememberUILang(lng: string): void {
  try {
    localStorage.setItem(UI_LANG_STORAGE_KEY, lng);
  } catch {
    // 隐私模式或禁用存储：本次切换照样生效，只是不记住。
  }
}

/** 清掉旧键，免得它在 DevTools 里误导排查（检测器已不再读它）。 */
export function dropLegacyUILang(): void {
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // 同上
  }
}
