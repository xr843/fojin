// Pre-paint theme init. Loaded as a render-blocking <script src> in index.html's
// <head> (NOT inline): the production CSP is `script-src 'self'` with no
// 'unsafe-inline'/nonce/hash, so an inline block would be silently dropped in
// prod (dev/CI send no CSP, hiding the bug) — same reason sw-update.js is external.
// Sets data-theme before first paint so a reload never flashes the wrong theme.
// Reads the zustand-persist shape {"state":{"mode":"…"}}; MUST match resolveTheme()
// in src/stores/themeStore.ts.
(function () {
  try {
    var raw = localStorage.getItem("fojin-theme");
    var mode = raw ? (JSON.parse(raw).state || {}).mode : "system";
    if (mode !== "light" && mode !== "dark" && mode !== "system") mode = "system";
    var prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    var effective = mode === "system" ? (prefersDark ? "dark" : "light") : mode;
    document.documentElement.setAttribute("data-theme", effective);
  } catch (e) {}
})();
