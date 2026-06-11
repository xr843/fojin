// Service worker freshness for returning visitors.
//
// External file on purpose: the previous inline version of this script was
// silently blocked by the CSP (`script-src 'self'` — no 'unsafe-inline'),
// which meant stale service workers were never told to update (#657).
(function () {
  if (!("serviceWorker" in navigator)) return;

  // Restore the #185 behavior: proactively check for a newer sw.js.
  navigator.serviceWorker.getRegistrations().then(function (regs) {
    regs.forEach(function (reg) {
      reg.update().catch(function () {});
    });
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
