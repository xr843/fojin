// Service worker freshness for returning visitors.
//
// External file on purpose: the previous inline version of this script was
// silently blocked by the CSP (`script-src 'self'` — no 'unsafe-inline'),
// which meant stale service workers were never told to update (#657).
(function () {
  if (!("serviceWorker" in navigator)) return;

  // How often a long-lived tab re-checks for a new sw.js.
  var CHECK_INTERVAL_MS = 30 * 60 * 1000; // 30 min

  function checkForUpdate() {
    navigator.serviceWorker.getRegistrations().then(function (regs) {
      regs.forEach(function (reg) {
        reg.update().catch(function () {});
      });
    });
  }

  // Restore the #185 behavior: proactively check for a newer sw.js.
  checkForUpdate();

  // ...but a load-time check alone only helps people who navigate. FoJin is an
  // SPA people leave open for a long reading session, and route changes don't
  // reload — so a tab opened before a deploy would never discover the new SW
  // and would keep running the old bundle indefinitely. Re-check periodically,
  // and again whenever the tab is brought back to the foreground (the cheap
  // proxy for "the user came back after a while").
  setInterval(checkForUpdate, CHECK_INTERVAL_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") checkForUpdate();
  });

  // 新版 SW 接管（controllerchange）后刷不刷新，由 src/utils/swUpdate.ts 决定：
  // 刚打开不久且没在打字 → 自动刷新；否则底部提示「佛津已更新」、站内换页时再刷新。
  // 这里原先无条件 reload，读者正在问答框里打字也会被刷掉（2026-11-26 改）。
})();
