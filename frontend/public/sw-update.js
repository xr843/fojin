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

  // With skipWaiting + clientsClaim, a new SW can take over mid-session.
  // The running page then no longer matches the active precache (old lazy
  // chunks 404 after a redeploy). Reload once so page and SW stay in sync.
  // Guard: on the very first install clientsClaim also fires
  // controllerchange (null -> SW); don't reload first-time visitors.
  var hadController = !!navigator.serviceWorker.controller;
  var reloaded = false;
  navigator.serviceWorker.addEventListener("controllerchange", function () {
    if (!hadController) {
      hadController = true;
      return;
    }
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
})();
