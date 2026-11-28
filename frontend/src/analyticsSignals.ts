/**
 * 给网站统计（Umami）补三种信号，用来把真人、登录用户和爬虫分开数（2026-11-28）：
 *
 * 1. 登录用户：会话标上账号的哈希代号（SHA-256(用户 id + 固定盐) 前 16 位，不含邮箱 / 用户名），
 *    各板块每天有几个登录用户可以精确数出来。
 * 2. 有效访问：页面打开 ≥3 秒后出现第一次「真人输入」（浏览器标记 isTrusted 的点击 / 触摸 / 按键 / 滚轮；
 *    程序模拟的事件 isTrusted 为 false），本会话在这个板块记一次 `engaged`（带板块名），每板块每会话一次。
 *    2026-11-27 实测：九成访客是只加载页面、不操作的爬虫（直落 /search、/dictionary）。
 * 3. 自动化：浏览器自报 navigator.webdriver（Puppeteer / Playwright / Selenium 默认如此）的会话
 *    照常记录，只标上 automation，便于单独统计爬虫——不丢弃。
 *
 * 没注入统计脚本（自托管者没配 VITE_UMAMI_*）时什么都不做。
 */
import { useAuthStore } from "./stores/authStore";

type Umami = {
  track: (event: string, data?: Record<string, string | number>) => void;
  identify?: (idOrData: string | Record<string, string | number>, data?: Record<string, string | number>) => void;
};

const MEMBER_SALT = "fojin-umami-member-2026-11";
export const ENGAGE_MIN_MS = 3000;

/** 路径 → 板块（看板按它分）。没列出的归 other。 */
export function sectionOf(path: string): string {
  if (path.startsWith("/chat") || path.startsWith("/share/qa")) return "chat";
  if (/^\/texts\/\d+\/read/.test(path) || path === "/read" || path.startsWith("/read-aloud")) return "read";
  if (path.startsWith("/texts")) return "texts";
  if (path.startsWith("/dictionary") || path.startsWith("/dict/")) return "dict";
  if (path.startsWith("/sources")) return "sources";
  if (path.startsWith("/history")) return "history";
  if (path.startsWith("/kg")) return "kg";
  if (path.startsWith("/search")) return "search";
  if (path.startsWith("/daily")) return "daily";
  if (path === "/") return "home";
  return "other";
}

/** 这次输入算不算一次有效访问：真人输入、页面已开够久、本会话这个板块还没记过。 */
export function shouldEngage(isTrusted: boolean, msSinceLoad: number, section: string, sent: Set<string>): boolean {
  return isTrusted && msSinceLoad >= ENGAGE_MIN_MS && !sent.has(section);
}

function umami(): Umami | undefined {
  return (window as unknown as { umami?: Umami }).umami;
}

/** 统计脚本是 defer 加载的：等它就绪再调，最多等 15 秒。 */
function whenUmami(fn: (u: Umami) => void, waited = 0): void {
  const u = umami();
  if (u) fn(u);
  else if (waited < 15000) window.setTimeout(() => whenUmami(fn, waited + 300), 300);
}

async function memberCode(userId: number): Promise<string> {
  const bytes = new TextEncoder().encode(`${userId}|${MEMBER_SALT}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest).slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
}

const SENT_KEY = "fojin.engaged";

function sentSections(): Set<string> {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(SENT_KEY) || "[]") as string[]);
  } catch {
    return new Set();
  }
}

export function installAnalyticsSignals(): void {
  if (!import.meta.env.VITE_UMAMI_URL || !import.meta.env.VITE_UMAMI_WEBSITE_ID) return;

  // 1. 自动化标签（不丢弃，只标）
  if (navigator.webdriver) whenUmami((u) => u.identify?.({ automation: "webdriver" }));

  // 2. 登录用户：当前已登录、以及之后登录，都标上代号
  let identified: number | null = null;
  const tag = (id: number | null | undefined) => {
    if (!id || id === identified || !crypto?.subtle) return;
    identified = id;
    void memberCode(id).then((code) => whenUmami((u) => u.identify?.(code, { member: 1 })));
  };
  tag(useAuthStore.getState().user?.id);
  useAuthStore.subscribe((s) => tag(s.user?.id));

  // 3. 有效访问
  const sent = sentSections();
  const onInput = (e: Event) => {
    const section = sectionOf(window.location.pathname);
    if (!shouldEngage(e.isTrusted, performance.now(), section, sent)) return;
    if (document.visibilityState !== "visible") return;
    sent.add(section);
    try {
      sessionStorage.setItem(SENT_KEY, JSON.stringify([...sent]));
    } catch {
      /* 隐私模式：记不住就每页各记一次，影响很小 */
    }
    whenUmami((u) => u.track("engaged", { section }));
  };
  for (const type of ["pointerdown", "touchstart", "keydown", "wheel"]) {
    window.addEventListener(type, onInput, { passive: true, capture: true });
  }
}
