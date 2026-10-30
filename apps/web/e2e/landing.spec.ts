import { expect, test } from "@playwright/test";

test.describe("Landing page", () => {
  test("communicates the proposition and routes to sign in", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Your business data.");
    await expect(page.getByText("An intelligent new perspective.")).toBeVisible();
    await expect(page.getByRole("link", { name: /sign in/i }).first()).toBeVisible();

    await page.getByRole("link", { name: /sign in/i }).first().click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
  });

  test("theme toggle switches between light and dark", async ({ page }) => {
    await page.goto("/");
    const html = page.locator("html");
    const before = await html.getAttribute("class");
    await page.getByRole("button", { name: /switch to (dark|light) mode/i }).click();
    await expect
      .poll(async () => (await html.getAttribute("class")) !== before)
      .toBe(true);
  });

  test("shows the demo preview without placeholder lorem ipsum", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText(/Illustrative|synthetic/i).first()).toBeVisible();
    await expect(page.locator("body")).not.toContainText("lorem ipsum");
  });
});
