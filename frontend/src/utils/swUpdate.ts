/**
 * 部署后让读者拿到新版本（2026-11-26 读者反馈：「读经」页加了搜索框，Ctrl+F5 后仍看不到）。
 *
 * 机制：Service Worker 预缓存了全部页面代码。部署后第一次打开，页面照样从缓存里出旧版，
 * 新 SW 在后台把几十个文件重下一遍（大陆网络约一分钟），装好后 skipWaiting + clientsClaim
 * 接管——但已经显示的页面还是旧代码，要再刷新才看到新版。读者不知道，以为没改。
 *
 * public/sw-update.js 负责定时与切回标签时检查新版；这里在新 SW 接管（controllerchange）时：
 * - 刚打开不久（< FRESH_MS）且没在输入框里打字 → 直接刷新一次，读者几乎察觉不到；
 * - 否则标记「有新版」：页面底部提示一行（可点刷新），下次站内换页时顺手整页刷新；
 * 首次安装（之前没有 controller）不算更新，不刷新。
 *
 * 另：旧页面在新 SW 接管后再按需加载某个旧代码块，文件已不在服务器上 → Vite 抛
 * vite:preloadError，这里整页刷新一次换成新版（60 秒内只刷一次，免得死循环）。
 */

// 新 SW 在大陆网络下重下全部文件约需一分钟：两分钟内接管的都算「刚打开」
const FRESH_MS = 120_000;
const PRELOAD_RELOAD_KEY = "fojin.sw.preloadReloadAt";

let updateReady = false;
const listeners = new Set<() => void>();

export function isUpdateReady(): boolean {
  return updateReady;
}

export function onUpdateReady(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function typing(): boolean {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  if (el.isContentEditable) return true;
  if (el instanceof HTMLTextAreaElement) return el.value.trim() !== "";
  if (el instanceof HTMLInputElement) return el.type !== "checkbox" && el.type !== "radio" && el.value.trim() !== "";
  return false;
}

/** 新版已接管时决定：现在就刷新，还是先提示。导出给测试用。 */
export function handleControllerChange(now: number, loadedAt: number, reload: () => void): "reloaded" | "deferred" {
  if (now - loadedAt < FRESH_MS && !typing()) {
    reload();
    return "reloaded";
  }
  updateReady = true;
  listeners.forEach((fn) => fn());
  return "deferred";
}

/** 旧代码块加载失败：60 秒内只整页刷新一次。导出给测试用。 */
export function handlePreloadError(now: number, reload: () => void, storage: Storage = sessionStorage): boolean {
  try {
    const last = Number(storage.getItem(PRELOAD_RELOAD_KEY) || 0);
    if (now - last < 60_000) return false;
    storage.setItem(PRELOAD_RELOAD_KEY, String(now));
  } catch {
    /* 无痕模式等拿不到存储：照样刷一次 */
  }
  reload();
  return true;
}

export function installSwUpdateHandling(): void {
  if (typeof window === "undefined") return;
  const loadedAt = Date.now();
  const reload = () => window.location.reload();
  window.addEventListener("vite:preloadError", (e) => {
    if (handlePreloadError(Date.now(), reload)) e.preventDefault();
  });
  if (!("serviceWorker" in navigator)) return;
  const hadController = !!navigator.serviceWorker.controller;
  let handled = false;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!hadController || handled) return;
    handled = true;
    handleControllerChange(Date.now(), loadedAt, reload);
  });
}
