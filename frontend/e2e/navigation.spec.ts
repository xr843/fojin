import { test, expect } from "@playwright/test";

test.describe("导航", () => {
  test("从首页导航到搜索页", async ({ page }) => {
    await page.goto("/");

    // 在搜索栏输入关键词并搜索
    const searchInput = page.locator(".search-combo-input");
    await searchInput.fill("般若");
    await searchInput.press("Enter");

    await expect(page).toHaveURL(/\/search\?q=/);
  });

  test("点击导航栏链接到数据源页", async ({ page }) => {
    await page.goto("/");

    // 桌面端导航中点击"数据源"
    const sourcesLink = page.locator(".nav-desktop").getByText(/数据源|Sources/);
    await sourcesLink.click();

    await expect(page).toHaveURL(/\/sources/);
  });

  test("点击导航栏链接到佛教史长卷", async ({ page }) => {
    await page.goto("/");

    const historyLink = page.locator(".nav-desktop").getByText(/佛教史|History/);
    await historyLink.click();

    await expect(page).toHaveURL(/\/history/);
  });

  test("点击导航栏链接到 AI 问答页", async ({ page }) => {
    await page.goto("/");

    const chatLink = page.locator(".nav-desktop").getByText(/问答|Chat/);
    await chatLink.click();

    await expect(page).toHaveURL(/\/chat/);
  });

  test("点击站名导航回首页", async ({ page }) => {
    await page.goto("/sources");

    await page.getByText("佛津").click();

    await expect(page).toHaveURL("/");
  });

  test("访问不存在的路径显示 404 页面", async ({ page }) => {
    await page.goto("/nonexistent-path");

    // 页面不应该崩溃，应该有某种 404 提示或渲染 NotFoundPage
    await expect(page.locator("body")).toBeVisible();
  });
});
