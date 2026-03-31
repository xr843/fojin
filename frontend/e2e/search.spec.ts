import { test, expect } from "@playwright/test";

test.describe("搜索功能", () => {
  test("在首页搜索栏输入并跳转到搜索结果页", async ({ page }) => {
    await page.goto("/");

    const searchInput = page.locator(".search-combo-input");
    await searchInput.fill("心经");
    await page.locator(".search-combo-btn").click();

    // 应导航到搜索页，URL 包含查询参数
    await expect(page).toHaveURL(/\/search\?q=%E5%BF%83%E7%BB%8F/);
  });

  test("直接访问搜索页并输入查询", async ({ page }) => {
    await page.goto("/search?q=般若");

    // 搜索页应该加载，等待页面内容渲染
    await page.waitForLoadState("networkidle");

    // 页面上应该有搜索相关的内容区域
    await expect(page.locator("body")).toBeVisible();
  });

  test("空搜索不触发导航", async ({ page }) => {
    await page.goto("/");

    // 不输入任何内容直接点击搜索
    await page.locator(".search-combo-btn").click();

    // 应该仍然在首页
    await expect(page).toHaveURL("/");
  });

  test("搜索栏支持回车键触发搜索", async ({ page }) => {
    await page.goto("/");

    const searchInput = page.locator(".search-combo-input");
    await searchInput.fill("金刚经");
    await searchInput.press("Enter");

    await expect(page).toHaveURL(/\/search\?q=/);
  });
});

test.describe("语义搜索", () => {
  test("智能搜索 tab 可见", async ({ page }) => {
    await page.goto("/search?q=般若");
    await page.waitForLoadState("networkidle");

    // 验证"智能搜索"tab 存在且可见
    const semanticTab = page.getByRole("tab", { name: /智能搜索/ });
    await expect(semanticTab).toBeVisible();
  });

  test("点击智能搜索 tab 切换激活状态", async ({ page }) => {
    await page.goto("/search?q=般若");
    await page.waitForLoadState("networkidle");

    const semanticTab = page.getByRole("tab", { name: /智能搜索/ });
    await semanticTab.click();

    // 切换后 URL 应包含 tab=semantic
    await expect(page).toHaveURL(/tab=semantic/);

    // tab 应处于激活状态（Ant Design 用 aria-selected 标记）
    await expect(semanticTab).toHaveAttribute("aria-selected", "true");
  });

  test("切换到智能搜索 tab 后显示提示文案", async ({ page }) => {
    await page.goto("/search?q=般若");
    await page.waitForLoadState("networkidle");

    // 点击智能搜索 tab
    const semanticTab = page.getByRole("tab", { name: /智能搜索/ });
    await semanticTab.click();

    // 验证提示文案可见
    const hint = page.locator(".s-mode-hint");
    await expect(hint).toContainText("基于 AI 向量语义理解");
  });

  test("智能搜索 tab 下输入查询触发搜索", async ({ page }) => {
    // 直接通过 URL 进入语义搜索 tab
    await page.goto("/search?q=心经&tab=semantic");
    await page.waitForLoadState("networkidle");

    // 验证页面处于语义搜索 tab（URL 参数正确）
    await expect(page).toHaveURL(/tab=semantic/);

    // 验证结果区域存在（主内容区应可见，不验证具体搜索结果）
    const main = page.locator(".s-main");
    await expect(main).toBeVisible();

    // 验证结果计数区域显示了语义搜索的统计文案
    const resultCount = page.locator(".s-result-count");
    await expect(resultCount).toContainText("语义搜索找到");
  });
});
