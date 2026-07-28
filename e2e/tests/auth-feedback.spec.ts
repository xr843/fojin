import { test, expect } from "@playwright/test";

/**
 * Guards the incident that shipped 2026-07-03 and stayed live for three weeks:
 * a React 19 bump silently broke every antd v5 static overlay (message.*,
 * Modal.confirm, notification.*), because they mount via the legacy
 * ReactDOM.render that React 19 removed. Register and logout gave "no
 * response" — the request ran, but no toast and no confirm dialog rendered —
 * across ~80 call sites. Fixed by @ant-design/v5-patch-for-react-19 (#1028).
 *
 * A unit test (frontend/src/test/antdStaticMethods.test.tsx) already asserts
 * message/Modal mount in jsdom. These are the *production* guards: only a real
 * browser hitting real prod catches "the patch was dropped from the bundle".
 *
 * Selectors are locale-agnostic: a fresh browser resolves the UI to English,
 * so placeholders read "Username"/"Password", not "用户名"/"密码".
 */

const USERNAME = /用户名|username/i;
const PASSWORD = /密码|password/i;

// Login with credentials that cannot authenticate. This is the safe probe:
// no account is created, no state changes, a failed login is harmless — yet
// the failure path calls antd's static message.error, which renders nothing
// if the React 19 patch regresses. Covers the shared root cause behind the
// register/logout/notification breakage (all go through the same static
// render bridge the patch installs).
test("a failed login surfaces an antd toast (React 19 static-method guard)", async ({ page }) => {
  await page.goto("/login");

  await page.getByPlaceholder(USERNAME).fill(`smoke_nouser_${Date.now()}`);
  await page.getByPlaceholder(PASSWORD).fill("this-password-cannot-be-correct");
  await page.locator('button[type="submit"]').click();

  // If antd's static message is dead (React 19 without the patch), this notice
  // never mounts and the test fails — exactly the signal that was missing for
  // three weeks.
  await expect(page.locator(".ant-message-notice")).toBeVisible({ timeout: 10_000 });
});

// Full logout flow, exercising Modal.confirm (the other overlay the incident
// killed) and a real sign-out. Needs a dedicated production test account —
// set SMOKE_USER / SMOKE_PASSWORD as repo secrets and pass them into the smoke
// workflow's env to enable. Skipped (not failed) when absent, so the suite
// stays green out of the box.
test("logout shows the confirm dialog and signs out (needs SMOKE_USER)", async ({ page }) => {
  const user = process.env.SMOKE_USER;
  const pass = process.env.SMOKE_PASSWORD;
  test.skip(!user || !pass, "set SMOKE_USER / SMOKE_PASSWORD to enable the logout-flow check");

  await page.goto("/login");
  await page.getByPlaceholder(USERNAME).fill(user!);
  await page.getByPlaceholder(PASSWORD).fill(pass!);
  await page.locator('button[type="submit"]').click();

  // Logged in: the success toast rendered and the user menu button appears.
  await expect(page.locator(".ant-message-notice")).toBeVisible({ timeout: 10_000 });
  const userMenu = page.getByRole("button", { name: /用户菜单|user menu/i });
  await expect(userMenu).toBeVisible({ timeout: 10_000 });

  // Open the dropdown and click Log out. Playwright dispatches real browser
  // events, so antd's menu onClick fires (unlike synthetic clicks).
  await userMenu.hover();
  await page.getByRole("menuitem", { name: /退出登录|log ?out/i }).click();

  // THE guard: handleLogout opens Modal.confirm; its onOk calls logout(). If
  // the dialog does not render, sign-out can never happen — the exact bug.
  const confirm = page.locator(".ant-modal-confirm");
  await expect(confirm).toBeVisible({ timeout: 10_000 });
  await confirm.locator(".ant-modal-confirm-btns button").last().click();

  // Signed out: the header shows the login entry again.
  await expect(page.getByRole("button", { name: /^\s*登\s*录\s*$|^\s*log ?in\s*$/i })).toBeVisible({
    timeout: 10_000,
  });
});
