import { expect, test } from "@playwright/test";

import { apiToken, signIn, watch } from "./watch.js";

/**
 * Page-by-page sweep of the whole app.
 *
 * smoke.spec.js proves the critical paths work. This proves the rest:
 * every route in App.jsx is visited with the console and network
 * watched, so a page that renders but throws (or 500s in the
 * background) fails here with the source file and line that caused it.
 *
 * Run with both dev servers up:
 *   cd frontend && npx playwright test
 *
 * The suite logs in often enough to trip the dev backend's 10/min login
 * bucket, so a full run needs that limiter off — see
 * docs/FRONTEND_GUIDE.md ("E2E tests").
 */

const API_URL = "http://localhost:8000";
const SELLER = { email: "test@gmail.com", password: "test123456789" };
const ADMIN = { email: "abin@test.com", password: "secretpass123" };

/**
 * Responses that are the app working as designed, not defects.
 *
 * A signed-out browser asking /auth/me and getting 401 is how the
 * client finds out it has no session — it clears the token and moves
 * on. Asserting that behaviour belongs in the login test below, not in
 * a global allowance, so this list stays as short as possible.
 */
const EXPECTED = [/^401 GET \/auth\/me$/];

/**
 * Fail with the browser's own words, each pointing at a source line.
 *
 * `allowed` exists for the pages that deliberately provoke an error —
 * an unknown tracking code is supposed to 404, and a watcher that
 * cannot tell that from a broken request is a watcher people learn to
 * ignore. Each test names what it expects, so nothing is silenced
 * globally.
 */
function assertClean(watcher, label, allowed = []) {
  const problems = watcher.format([...EXPECTED, ...allowed]);
  if (problems.length) {
    throw new Error(
      `${label} — the browser reported ${problems.length} problem(s):\n${problems.join("\n")}`,
    );
  }
}

/**
 * Call the API as the signed-in browser.
 *
 * `fetch`, not `get`: page.request.get() hard-codes the method to GET
 * and discards the `method` in the options, so a caller asking for a
 * DELETE was quietly sending a GET — and a cleanup step that never
 * deletes anything fails later as confusing, accumulating litter.
 */
async function api(page, path, options = {}) {
  const response = await page.request.fetch(`${API_URL}${path}`, {
    method: "GET",
    ...options,
    headers: {
      Authorization: `Bearer ${await apiToken(page)}`,
      ...options.headers,
    },
  });
  return response;
}

// ---------------------------------------------------------------- public

test("every public page renders, with nothing on the console", async ({ page }) => {
  const watcher = watch(page);

  const routes = [
    ["/", page.getByRole("heading", { level: 1 })],
    ["/login", page.getByRole("heading", { name: "Welcome back" })],
    ["/signup", page.getByRole("heading", { name: "Create your store" })],
    ["/forgot-password", page.getByRole("heading", { name: "Forgot your password?" })],
    ["/reset-password", page.getByRole("heading", { name: "Missing reset token" })],
    ["/verify-email", page.getByRole("heading", { level: 1 })],
    ["/privacy", page.getByRole("heading", { name: "Privacy Policy" })],
    ["/terms", page.getByRole("heading", { name: "Terms of Service" })],
    ["/no-such-page", page.getByRole("heading", { name: "Page not found" })],
  ];

  for (const [path, landmark] of routes) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(landmark).toBeVisible();
      assertClean(watcher, path);
    });
  }
});

test("a signed-out browser is treated as signed out, not as an error", async ({ page }) => {
  const watcher = watch(page);
  await page.goto("/dashboard/orders");

  // ProtectedRoute must bounce to the login page rather than render a
  // half-empty dashboard.
  await expect(page).toHaveURL(/\/login/);
  assertClean(watcher, "protected route while signed out");
});

test("the public order form and tracking page work end to end", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, SELLER.email, SELLER.password);
  const me = await (await api(page, "/auth/me")).json();

  await page.goto(`/order/${me.store_slug}`);
  await expect(page.getByRole("heading", { name: me.store_name, exact: true })).toBeVisible();

  await page.getByLabel("Your name *").fill("Walk-in Sweep");
  await page.getByLabel("Phone number *").fill("01700000099");
  await page.getByLabel("Email address *").fill("walkin.sweep@example.com");
  await page.getByLabel("Delivery address *").fill("House 4, Road 7, Banani, Dhaka");
  await page.getByLabel("Item 1 name").fill("Sweep Panjabi");
  // The quantity is a stepper — +/− buttons around a number input, so
  // "Item 1 quantity" matches three elements. Ask for the input itself.
  await page.getByRole("spinbutton", { name: /item 1 quantity/i }).fill("2");
  await page.getByLabel("Item 1 price").fill("1450");
  await page.getByRole("button", { name: /Place order/i }).click();

  await expect(page.getByRole("heading", { name: "Order placed!" })).toBeVisible();
  assertClean(watcher, "public order form");

  // The confirmation prints the code in a known element; read it there
  // rather than guessing at the page text.
  const code = (await page.locator(".orderform-track-code").innerText()).trim();
  expect(code, "the confirmation must show a tracking code").toMatch(/^[A-Z0-9]{6,12}$/);

  await page.goto(`/track/${code}`);
  // The public tracking view is deliberately a status page, not a
  // receipt: it shows who the order is for, the status timeline, and
  // the code — the line items live on the seller's side.
  await expect(page.getByText("Walk-in Sweep")).toBeVisible();
  await expect(page.getByText(/placed/i).first()).toBeVisible();
  await expect(page.getByText(code)).toBeVisible();
  assertClean(watcher, "tracking page");

  // And the copy-link button is a real feature, so exercise it.
  await page.goto(`/order/${me.store_slug}`);
  await expect(page.getByRole("heading", { name: me.store_name, exact: true })).toBeVisible();

  // A customer cannot delete their own order, but the seller can while
  // it is still 'placed' — so clean up with the seller's token. Without
  // this the shared dev database grows a dozen phantom orders a day and
  // the seller's dashboard stops looking like the real thing.
  const mine = await (await api(page, "/orders?limit=100")).json();
  for (const order of mine.orders.filter((o) => o.customer_name === "Walk-in Sweep")) {
    await api(page, `/orders/${order.id}`, { method: "delete" });
  }
});

test("the tracking page reports an unknown code as not found", async ({ page }) => {
  const watcher = watch(page);
  await page.goto("/track/NOPE12345");
  await expect(page.getByRole("heading", { name: "Order not found" })).toBeVisible();
  // The 404 is the point of this page — the app must show "not found"
  // rather than "something went wrong".
  assertClean(watcher, "tracking page (unknown code)", [/^404 GET track\/NOPE12345$/]);
});

test("forgot-password confirms without revealing whether the account exists", async ({ page }) => {
  const watcher = watch(page);
  await page.goto("/forgot-password");
  await page.getByLabel("Email").fill("nobody-at-all@example.com");
  await page.getByRole("button", { name: /Send reset link/i }).click();
  await expect(page.getByText(/check your (email|inbox)/i)).toBeVisible();
  assertClean(watcher, "forgot password");
});

// ---------------------------------------------------------------- seller

test("every seller page renders, with nothing on the console", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, SELLER.email, SELLER.password);

  const orders = await (await api(page, "/orders?limit=1")).json();
  const orderId = orders.orders[0]?.id;
  expect(orderId, "the dev seller needs at least one order for this sweep").toBeTruthy();

  const routes = [
    ["/dashboard", page.getByRole("heading", { level: 1 })],
    ["/dashboard/orders", page.getByRole("heading", { name: "Orders" })],
    ["/dashboard/settings", page.getByRole("heading", { name: "Store settings" })],
    [`/dashboard/orders/${orderId}`, page.locator("h1.order-detail-title")],
  ];

  for (const [path, landmark] of routes) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(landmark).toBeVisible();
      assertClean(watcher, path);
    });
  }
});

test("the dashboard can create, track, and delete an order", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, SELLER.email, SELLER.password);

  // Clear any leftover from a previous failed run first: two orders with
  // the same customer name make the row below ambiguous, and a test that
  // only passes on a clean database is a test that fails in CI.
  const existing = await (await api(page, "/orders?limit=100")).json();
  for (const order of existing.orders.filter((o) => o.customer_name === "Dashboard Sweep")) {
    await api(page, `/orders/${order.id}`, { method: "delete" });
  }

  await page.goto("/dashboard/orders");

  // Whatever the button is called, it opens the order form.
  await page.getByRole("button", { name: /new order|add order|create order/i }).first().click();
  await expect(page.getByRole("heading", { name: "New order" })).toBeVisible();
  await page.getByLabel("Customer name").fill("Dashboard Sweep");
  await page.getByLabel("Phone").fill("01700000055");
  await page.getByLabel(/address/i).first().fill("House 1, Road 1, Dhanmondi, Dhaka");
  await page.getByLabel("Item 1 name").fill("Sweep Item");
  await page.getByRole("spinbutton", { name: /item 1 quantity/i }).fill("3");
  await page.getByLabel("Item 1 unit price").fill("900");
  await page.getByRole("button", { name: "Create order" }).click();

  await expect(page.getByText("Dashboard Sweep").first()).toBeVisible();
  assertClean(watcher, "creating an order");

  // Open it, and confirm the detail page renders the order just made.
  // The desktop table row is not itself clickable — the View link in
  // the Actions cell is how you get to the detail page. The row is
  // matched by customer, not by position: the list is newest-first and
  // other tests create orders too.
  await page
    .getByRole("row", { name: /Dashboard Sweep/ })
    .getByRole("link", { name: "View" })
    .click();
  await expect(page.locator("h1.order-detail-title")).toBeVisible();
  await expect(page.getByText("Sweep Item").first()).toBeVisible();
  assertClean(watcher, "order detail");

  // Clean up through the API so a failed test does not leave litter.
  const orders = await (await api(page, "/orders?limit=100")).json();
  const mine = orders.orders.find((order) => order.customer_name === "Dashboard Sweep");
  if (mine) {
    await api(page, `/orders/${mine.id}`, { method: "delete" });
  }
});

test("store settings save, and saying so", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, SELLER.email, SELLER.password);
  const before = await (await api(page, "/auth/me")).json();

  await page.goto("/dashboard/settings");
  const nameField = page.getByLabel("Store name").first();
  await nameField.fill(`${before.store_name} (swept)`);
  // Exactly "Save changes". A loose /save/i also matches the plan
  // buttons ("6 months ৳1,750 save 17%"), which sit higher up the page
  // and select a plan instead of saving.
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText(/Store profile updated/);
  assertClean(watcher, "saving settings");

  // Put it back — this is the shared dev account.
  await page.request.patch(`${API_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${await apiToken(page)}` },
    data: { store_name: before.store_name },
  });
});

// ---------------------------------------------------------------- admin

test("every admin page renders, with nothing on the console", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, ADMIN.email, ADMIN.password);

  const { sellers } = await (await api(page, "/admin/sellers?limit=1")).json();
  const shop = sellers[0];
  expect(shop, "the admin needs at least one seller to look at").toBeTruthy();

  // A shop page's h1 is the shop's own name plus its plan badge, so
  // match on the name. Asserting the generic "Shop" was passing only
  // because the loading skeleton also renders an h1 "Shop" — it proved
  // the page had been requested, not that it had loaded.
  const name = new RegExp(shop.store_name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

  const routes = [
    ["/admin", page.getByRole("heading", { name: "Platform Overview" })],
    ["/admin/sellers", page.getByRole("heading", { name: /Sellers/i })],
    [`/admin/sellers/${shop.id}`, page.getByRole("heading", { level: 1, name })],
    ["/admin/requests", page.getByRole("heading", { name: "Upgrade Requests" })],
  ];

  for (const [path, landmark] of routes) {
    await test.step(path, async () => {
      await page.goto(path);
      await expect(landmark).toBeVisible();
      assertClean(watcher, path);
    });
  }
});

test("a seller is refused the admin area", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, SELLER.email, SELLER.password);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/dashboard/);
  assertClean(watcher, "seller visiting /admin");
});

test("the admin can suspend a seller and put it back", async ({ page }) => {
  const watcher = watch(page);
  await signIn(page, ADMIN.email, ADMIN.password);

  // Suspend the sweep account, never a real one.
  //
  // The search is `q`, not `search`, and the page size caps at 100
  // (app/routes/admin.py:144) — asking for 200 is a 422, not a bigger
  // page. Filter server-side instead of paging past the whole dev DB.
  const { sellers } = await (await api(page, "/admin/sellers?q=abinroy510&limit=100")).json();
  const target = sellers.find((seller) => seller.email.startsWith("abinroy510+sweep@"));
  test.skip(!target, "no sweep account in this database — run scripts/api_sweep.py first");

  await page.goto(`/admin/sellers/${target.id}`);
  await expect(page.getByRole("heading", { name: /^Shop/ })).toBeVisible();

  try {
    // Suspending asks for a reason through window.prompt, so the dialog
    // has to be answered with text — not just accepted.
    page.once("dialog", (dialog) => dialog.accept("E2E sweep — reinstated below"));
    await page.getByRole("button", { name: "Suspend shop" }).click();
    await expect(page.getByRole("button", { name: "Reinstate shop" })).toBeVisible();
    await expect(page.getByText(/This shop is suspended/)).toBeVisible();
    assertClean(watcher, "suspending a seller");
  } finally {
    // Even if an assertion above failed, never leave a seller suspended.
    // (frontend/src/pages/AdminShopDetail.jsx renders the button from
    // shop.suspended_at, so the label is the state.)
    await page.request.patch(`${API_URL}/admin/sellers/${target.id}/suspension`, {
      headers: { Authorization: `Bearer ${await apiToken(page)}` },
      data: { suspended: false },
    });
  }

  // Put back: the page offers to suspend again, and says nothing about
  // being suspended any more.
  await page.reload();
  await expect(page.getByRole("button", { name: "Suspend shop" })).toBeVisible();
  await expect(page.getByText(/This shop is suspended/)).toHaveCount(0);
  assertClean(watcher, "after reinstating");
});
