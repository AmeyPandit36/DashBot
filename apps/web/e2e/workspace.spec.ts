import { expect, test } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "demo@agenticbi.dev";
const PASSWORD = process.env.E2E_PASSWORD ?? "DemoPass123!";

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByLabel(/work email/i).fill(EMAIL);
  await page.getByLabel(/^password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app$/, { timeout: 20_000 });
}

test.describe("Seeded retail workspace", () => {
  test("overview shows real metrics and navigation", async ({ page }) => {
    await signIn(page);
    await expect(page.getByText(/Retail Sales/i).first()).toBeVisible();
    await expect(page.getByText(/rows|datasets/i).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /AI analyst/i }).first()).toBeVisible();
  });

  test("dashboard renders widgets with SQL provenance", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/dashboards");
    await page.getByRole("link", { name: /Business performance overview/i }).first().click();
    await expect(page.getByRole("heading", { name: /Business performance overview/i })).toBeVisible();
    await expect(page.getByText(/Total Amount/i).first()).toBeVisible();
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20_000 });

    // SQL is reachable from any widget
    await page.getByRole("button", { name: /widget actions/i }).first().click();
    await page.getByRole("menuitem", { name: /view sql/i }).click();
    await expect(page.getByText(/SELECT/i).first()).toBeVisible();
  });

  test("analyst answers a numerical question with verification and evidence", async ({ page }) => {
    await signIn(page);
    await page.goto("/app/analyst");
    await page.getByLabel(/ask the ai analyst/i).fill("What is total revenue?");
    await page.getByRole("button", { name: /send question/i }).click();

    await expect(page.getByText(/Verified/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/₹/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /view sql/i }).first()).toBeVisible();
  });
});
