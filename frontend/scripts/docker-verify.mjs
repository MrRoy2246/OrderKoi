// Full-stack verification of the DOCKERIZED app (localhost:8090 + :8000):
// every admin page (both previously-broken ones), signup flow, console and
// network errors captured. Run: node scripts/docker-verify.mjs
import { chromium } from "@playwright/test";

const errors = [];
const failed = [];
const browser = await chromium.launch();
const page = await browser.newPage();
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)); });
page.on("pageerror", (e) => errors.push(`PAGE ERROR: ${e.message}`));
page.on("response", (r) => {
  if (r.status() >= 400) failed.push(`${r.request().method()} ${new URL(r.url()).pathname} — ${r.status()}`);
});

async function check(label, url, expectText) {
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  const text = ((await page.textContent("body")) || "").replace(/\s+/g, " ");
  const ok = expectText.every((t) => text.includes(t));
  const rows = await page.locator("table tbody tr").count();
  console.log(`${ok ? "PASS" : "FAIL"}  ${label}  (rows: ${rows})`);
  if (!ok) console.log("   missing:", expectText.filter((t) => !text.includes(t)));
}

console.log("== Docker stack verification ==");

await check("landing page", "http://localhost:8090/", ["OrderKoi", "Privacy Policy"]);

console.log("-- signup (creates a seller in the Docker DB) --");
await page.goto("http://localhost:8090/signup", { waitUntil: "networkidle" });
await page.getByLabel("Store name").fill("Docker Verify Shop");
await page.getByLabel("Email").fill(`docker-verify-${Date.now()}@example.com`);
await page.getByLabel("Password", { exact: true }).fill("dockerverify123");
await page.getByLabel("Confirm password").fill("dockerverify123");
await page.getByRole("button", { name: "Create account" }).click();
await page.waitForTimeout(1500);
const body = ((await page.textContent("body")) || "").replace(/\s+/g, " ");
console.log(body.includes("Check your email") ? "PASS  signup → check-your-email screen" : "FAIL  signup screen");

console.log("-- seller cannot log in until verified (expected) / admin login --");
await page.goto("http://localhost:8090/login", { waitUntil: "networkidle" });
await page.getByLabel("Email").fill("abin@test.com");
await page.getByLabel("Password").fill("secretpass123");
await page.getByRole("button", { name: "Log in" }).click();
await page.waitForURL(/\/admin/, { timeout: 10000 }).catch(() => {});
console.log(page.url().endsWith("/admin") ? "PASS  admin login → /admin" : `FAIL  admin login (at ${page.url()})`);
await page.waitForTimeout(1500);
let text = ((await page.textContent("body")) || "").replace(/\s+/g, " ");
console.log(text.includes("Platform Overview") ? "PASS  admin overview renders" : "FAIL  admin overview blank");
const rows = await page.locator("table tbody tr").count();
console.log(rows > 0 ? `PASS  newest-sellers table has rows (${rows})` : "FAIL  overview table empty");

await check("admin sellers page (was blank before)", "http://localhost:8090/admin/sellers",
  ["Sellers & Plans", "accounts on your platform"]);
const sellerRows = await page.locator("table tbody tr").count();
console.log(sellerRows > 0 ? `PASS  sellers table lists accounts (${sellerRows})` : "FAIL  sellers table empty");

await check("admin requests page", "http://localhost:8090/admin/requests", ["Upgrade Requests"]);

console.log("\n== RESULT ==");
console.log("Console/page errors:", errors.length ? errors : "NONE");
console.log("Failed requests (>=400):", failed.length ? failed : "NONE");

await browser.close();
process.exit(errors.length || failed.length ? 1 : 0);
