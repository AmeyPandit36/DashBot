import { expect, test } from "@playwright/test";

test.describe("Authentication", () => {
  test("register creates an organisation and lands in the workspace", async ({ page }) => {
    const unique = `${Date.now()}-${Math.floor(Math.random() * 10_000)}`;
    await page.goto("/register");
    await page.getByLabel(/full name/i).fill("E2E Analyst");
    await page.getByLabel(/work email/i).fill(`e2e-${unique}@example.com`);
    await page.getByLabel(/organi[sz]ation/i).fill(`E2E Org ${unique}`);
    await page.getByLabel(/^password/i).fill("StrongPass123!");
    await page.getByLabel(/confirm password/i).fill("StrongPass123!");
    await page.getByRole("button", { name: /create workspace/i }).click();

    await expect(page).toHaveURL(/\/app$/, { timeout: 20_000 });
    await expect(page.getByRole("link", { name: /datasets/i }).first()).toBeVisible();
    await expect(page.getByText(/upload|\(0\)|no datasets/i).first()).toBeVisible();
  });

  test("rejects invalid credentials with a visible message", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/work email/i).fill("nobody@example.com");
    await page.getByLabel(/^password/i).fill("WrongPass123!");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/invalid|incorrect|check your email/i).first()).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });
});
