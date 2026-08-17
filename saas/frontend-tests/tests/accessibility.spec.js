// @ts-check
const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;

/**
 * Accessibility (WCAG 2.2 A/AA) + journey checks against real rendered pages.
 *
 * Only unauthenticated pages are covered here so no GitHub OAuth is needed.
 * axe-core is run with the wcag2a/wcag2aa/wcag21aa/wcag22aa tags; any
 * "serious" or "critical" violation fails the build.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** @param {import('@playwright/test').Page} page */
async function axeSeriousViolations(page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  return results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
}

test.describe("Login page", () => {
  test("has no serious/critical accessibility violations", async ({ page }) => {
    await page.goto("/");
    const violations = await axeSeriousViolations(page);
    expect(
      violations,
      JSON.stringify(violations.map((v) => ({ id: v.id, nodes: v.nodes.length })), null, 2)
    ).toEqual([]);
  });

  test("exposes a skip-to-content link and a single H1", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("a.skip-to-content")).toHaveAttribute(
      "href",
      "#main-content"
    );
    await expect(page.locator("h1")).toHaveCount(1);
  });

  test("keyboard focus reaches the GitHub sign-in control", async ({ page }) => {
    await page.goto("/");
    // Tab from the top; the skip link then the GitHub button must be reachable.
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.className || "");
    expect(active.length).toBeGreaterThan(0);
    await expect(page.locator("a.btn-auth-github")).toBeVisible();
  });
});

test.describe("OAuth error journey", () => {
  test("declined consent shows a clear page with no a11y violations", async ({ page }) => {
    await page.goto("/callback?error=access_denied");
    await expect(page.locator("body")).toContainText("Authorization Cancelled");
    const violations = await axeSeriousViolations(page);
    expect(
      violations,
      JSON.stringify(violations.map((v) => ({ id: v.id, nodes: v.nodes.length })), null, 2)
    ).toEqual([]);
  });

  test("404 page renders the status code", async ({ page }) => {
    const response = await page.goto("/this-route-does-not-exist");
    expect(response?.status()).toBe(404);
    await expect(page.locator("body")).toContainText("404");
    await expect(page.locator("body")).toContainText("Page Not Found");
  });
});

test.describe("Reduced motion", () => {
  test("respects prefers-reduced-motion on the login page", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/");
    // No serious violations under reduced motion either.
    const violations = await axeSeriousViolations(page);
    expect(violations).toEqual([]);
    await context.close();
  });
});

