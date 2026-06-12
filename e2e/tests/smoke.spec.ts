import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

/**
 * Six smoke checks for the paths a real visitor walks. Each one encodes a
 * production incident we actually shipped:
 *  - dead header buttons under a stale SW (issue #657 / PR #680)
 *  - search page hardcoded Chinese in the en locale (PR #706)
 *  - stale translation.json pinned by heuristic caching (PR #708)
 *  - CSP-killed inline script breaking updates silently (PR #680)
 */

test("home page loads without fatal console errors", async ({ page }) => {
  const fatal: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    // Cloudflare injects its RUM beacon which our CSP rejects — known noise.
    if (text.includes("cloudflareinsights")) return;
    if (/Failed to load resource.*40[34]/.test(text)) return; // optional assets
    fatal.push(text);
  });
  await page.goto("/");
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(fatal, `fatal console errors:\n${fatal.join("\n")}`).toHaveLength(0);
});

test("catalog search returns result cards", async ({ page }) => {
  await page.goto("/search?q=般若&tab=catalog");
  // Loading skeletons also use .s-card — assert on the result title, which
  // only real ResultCards render, or a hung search API would pass.
  await expect(page.locator(".s-card .s-card-title").first()).toBeVisible({
    timeout: 20_000,
  });
});

test("language switcher opens and switches the UI to English", async ({ page }) => {
  await page.goto("/");
  // The #657 report: this exact button did nothing under a stale SW bundle.
  await page
    .getByRole("button", { name: /Switch language|切换语言|切換語言/ })
    .click();
  await page.getByRole("menuitem", { name: "English" }).click();
  await expect(
    page.getByRole("button", { name: /Buddhist Dictionary/ })
  ).toBeVisible({ timeout: 10_000 });
});

test("english locale file is current and the search page renders in English", async ({
  page,
  request,
}) => {
  // Guard against the PR #708 incident class: a stale/short translation file
  // means new keys silently fall back to Chinese. The floor derives from the
  // checked-out repo's en file (90%, absorbing small refactors and the
  // master-vs-prod skew between scheduled runs and deploys).
  // Path is cwd-relative; both local runs and CI execute from e2e/.
  const repoKeys = Object.keys(
    JSON.parse(readFileSync("../frontend/public/locales/en/translation.json", "utf8"))
  ).length;
  const res = await request.get("/locales/en/translation.json");
  expect(res.ok()).toBeTruthy();
  const keys = Object.keys(await res.json());
  expect(keys.length).toBeGreaterThanOrEqual(Math.floor(repoKeys * 0.9));
  expect(res.headers()["cache-control"] || "").toContain("no-cache");

  await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"));
  await page.goto("/search?q=wise+attention");
  const tabs = page.locator(".ant-tabs-tab");
  await expect(tabs.first()).toBeVisible({ timeout: 20_000 });
  await expect(tabs.first()).toHaveText("All", { timeout: 10_000 });
  await expect(page.locator(".s-mode-bar")).not.toContainText("搜经典");
  // Returning-visitor path (locale from localStorage, init-time async load):
  // the header language label must show the active language, not the stale
  // resolvedLanguage fallback (was「中文」on an all-English page).
  await expect(page.locator(".header-lang-text")).toHaveText("English", {
    timeout: 10_000,
  });
});

test("reader opens the Heart Sutra via CBETA id redirect", async ({ page, request }) => {
  // /api/cbeta/T0251 is the stable anchor; text ids could change on reingest.
  const res = await request.get("/api/cbeta/T0251");
  expect(res.ok()).toBeTruthy();
  const { redirect_to } = await res.json();
  await page.goto(redirect_to);
  await expect(page.locator("#root")).toContainText(/般若|心经|心經/, {
    timeout: 20_000,
  });
});

test("chat page renders its input box", async ({ page }) => {
  // Page render only — no LLM request, keeps the smoke run free.
  await page.goto("/chat");
  await expect(
    page.locator("textarea, [contenteditable='true']").first()
  ).toBeVisible({ timeout: 20_000 });
});
