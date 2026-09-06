import { expect, test } from "@playwright/test";

/**
 * End-to-end smoke of the critical paths. If any of these break, the
 * product is broken — that's the bar. Runs against the dev servers
 * (see playwright.config.js) using the long-lived dev seller account.
 */

const SELLER_EMAIL = "test@gmail.com";
const SELLER_PASSWORD = "test123456789";
const API_URL = "http://localhost:8000";

test("landing page renders", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText("Privacy Policy")).toBeVisible();
});

test("unknown URL shows the 404 page", async ({ page }) => {
  await page.goto("/this-page-does-not-exist");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
});

test("signup shows the check-your-email screen", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Store name").fill("E2E Smoke Shop");
  await page.getByLabel("Email").fill(`e2e-${Date.now()}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("smoketest123");
  await page.getByLabel("Confirm password").fill("smoketest123");
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
});

test("login → dashboard with stats", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(SELLER_EMAIL);
  await page.getByLabel("Password").fill(SELLER_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();

  // Dashboard loads with its stat cards
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText(/Orders \(/).first()).toBeVisible();
});

test("public form order → confirmation → tracking page", async ({ page }) => {
  // Log in to learn this seller's public form slug from the API
  await page.goto("/login");
  await page.getByLabel("Email").fill(SELLER_EMAIL);
  await page.getByLabel("Password").fill(SELLER_PASSWORD);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard/);

  const token = await page.evaluate(() => localStorage.getItem("orderkoi_token"));
  const me = await page.request.get(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(me.ok()).toBeTruthy();
  const { store_slug } = await me.json();

  // Customer fills the public order form
  await page.goto(`/order/${store_slug}`);
  await expect(
    page.getByRole("heading", { name: "test", exact: true })
  ).toBeVisible();

  await page.getByLabel("Your name *").fill("E2E Smoke Customer");
  await page.getByLabel("Phone number *").fill("01700000001");
  await page.getByLabel("Email address *").fill("e2e-customer@example.com");
  await page.getByLabel("Delivery address *").fill("House 1, Road 1, Dhaka");
  await page.getByLabel("Item 1 name").fill("Smoke test item");
  await page.getByLabel("item 1 price").fill("100");
  await page.getByRole("button", { name: "Place order" }).click();

  // Confirmation with a tracking code
  await expect(page.getByRole("heading", { name: "Order placed!" })).toBeVisible();
  const trackLink = page.getByRole("link", { name: /Track your order anytime/ });
  await expect(trackLink).toBeVisible();
  await trackLink.click();

  // Tracking page shows the order and its status timeline
  await expect(page).toHaveURL(/\/track\//);
  await expect(page.getByText("E2E Smoke Customer")).toBeVisible();
  await expect(page.getByText("placed", { exact: false }).first()).toBeVisible();
});
