import { defineConfig } from "@playwright/test";

/**
 * E2E smoke tests — run against the local dev servers.
 *
 * Start them first:
 *   backend:  cd backend && ./venv/Scripts/uvicorn.exe app.main:app --port 8000
 *   frontend: cd frontend && npm run dev
 *
 * Then:  npx playwright test
 *
 * The suite uses the long-lived dev seller account (test@gmail.com,
 * Pro plan) so it can log in without an email-verification round trip.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: 0,
  workers: 1, // one at a time — the dev backend rate-limits by IP
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    headless: true,
    trace: "retain-on-failure",
  },
});
