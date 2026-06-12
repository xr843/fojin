import { defineConfig } from "@playwright/test";

/**
 * Post-deploy smoke suite. Runs against production by default — override
 * with BASE_URL for staging/local. Kept deliberately small (~6 specs):
 * these are the "is the site actually working for a real visitor" checks
 * that unit tests and curl probes structurally cannot catch (SW pinning,
 * CSP-killed scripts, stale locale files, dead header buttons — all of
 * which shipped to production at some point in 2026).
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  retries: 2,
  workers: 1, // be gentle with the production VPS
  use: {
    baseURL: process.env.BASE_URL || "https://fojin.app",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
});
