# ⚛️ Frontend Guide — React

The OrderKoi seller dashboard & tracking pages. React + Vite.

## Requirements

- Node.js 18+ installed (`node --version`)
- If not installed: download LTS from https://nodejs.org/

## First-time setup

Open a terminal in `OrderKoi/frontend/` and run:

```bash
npm install
```

This downloads all dependencies into `node_modules/` (takes a few minutes on first run — normal).

> ⚠️ The **backend must be running** (`localhost:8000`) for the frontend to load real data. Start it first.

## Running the dev server

```bash
npm run dev
```

- App URL: `http://localhost:5173`
- Auto-reloads when code changes — keep it running while developing

> Configuration comes from the single `.env` at the **repo root**, one directory up — Vite's
> `envDir` points there. Only `VITE_`-prefixed keys reach browser code; see
> **[ENVIRONMENT.md](./ENVIRONMENT.md)**.

## Key pages

| Route | What | Who |
|---|---|---|
| `/` | Landing page | Everyone |
| `/login`, `/signup`, `/forgot-password`, `/reset-password` | Auth | Sellers |
| `/verify-email` | Opens from the verification email link | Sellers (via email) |
| `/dashboard` | Overview: stats, charts, subscription card | Sellers (login required) |
| `/dashboard/orders`, `/dashboard/orders/:id` | Order list + detail | Sellers (login required) |
| `/dashboard/settings` | Store settings + Plan & subscription (history) | Sellers (login required) |
| `/admin` | Platform overview (KPIs follow the date filter) | Admin only |
| `/admin/sellers`, `/admin/sellers/:id`, `/admin/requests` | Seller & plan management, upgrade queue | Admin only |
| `/order/:slug` | **Public order form** (paused page when free limit hit) | Customers — no login |
| `/track/:code` | **Public tracking page** | Customers — no login |
| `/privacy`, `/terms` | Privacy Policy & Terms of Service | Everyone |
| anything else | 404 page | Everyone |

## Live business config (prices, allowance, bKash, contact)

Pro prices, the free-plan allowance, bKash details, and the support email are **not hard-coded**: `src/utils/proPricing.js` fetches `GET /public/stores/pricing` at runtime (module-level cache, fallbacks if the backend is down) and exposes `getProOptions()`, `proPriceFor(months)`, `getFreePlanOrders()`, `getBkash()`, `getSupportEmail()`. Pages call `fetchPublicConfig()` on mount, then bump a state counter to re-render once it lands. **Offers change in the repo-root `.env` + backend restart — no frontend rebuild.** If you add a new business value: extend `PublicConfigOut` (backend) → the fallback object in `proPricing.js` → a getter → consumers.

## Production build (Docker)

The deployed frontend is the `frontend/Dockerfile` build: `VITE_API_URL` is passed as a **build arg** (the API base is baked into the JS bundle — `src/api/client.js`), and the result is served by nginx with a CSP header, SPA fallback, and immutable asset caching. Everything is orchestrated by the repo-root `docker-compose.yml` — see **[DEPLOYMENT.md](./DEPLOYMENT.md)**.

## Plain production build

```bash
npm run build     # outputs optimized files to dist/
npm run preview   # serves the build locally to verify it
```

The `dist/` folder is what gets deployed to your domain (Phase 8).

## E2E tests (Playwright)

Two specs, 18 tests. `smoke.spec.js` covers the critical paths (landing renders, 404 page, signup check-your-email screen, login → dashboard, public order form → confirmation → tracking, admin overview + sellers). `pages.spec.js` walks every route in `App.jsx` — public, seller, and admin — with a console/network watcher attached, so a page that renders but throws fails with the source file and line that caused it.

```bash
# Both dev servers must be running first (backend 8000, frontend 5173)
npx playwright test
```

- Runs one test at a time (`workers: 1`) — the dev backend rate-limits by IP, and parallel tests would trip it
- **The full suite needs the IP rate limiter off.** The suite logs in a dozen times in under a minute against the `10/min` login bucket, so a single `npx playwright test` ends with `429 Too many requests` on whichever test got there last. Start the dev backend with `RATE_LIMIT_ENABLED=false` for a suite run:

  ```bash
  cd backend && RATE_LIMIT_ENABLED=false uvicorn app.main:app --port 8000
  ```

  The limiter is off for the run, not for the app — see the rate-limit table in **[ENVIRONMENT.md](./ENVIRONMENT.md)** for the real values. (Running the two spec files individually with a minute between them also works, and keeps the limiter on.) The per-account login lockout (`LOGIN_MAX_FAILURES`, 5 wrong passwords in 15 minutes) is separate and still applies — the suite never uses a wrong password, so it does not trip it.
- Uses the long-lived dev seller account (`test@gmail.com`) — no email-verification round trip needed
- Tests clean up their own orders through the API. `smoke.spec.js` still leaves one unverified `e2e-<timestamp>@example.com` account per run (there is no delete-seller endpoint by design) — harmless, but the dev database accumulates them.
- First run only: `npx playwright install chromium`

## Testing it yourself

- **Browser dev tools (F12) are your friend:**
  - *Console* tab → red errors mean something broke
  - *Network* tab → check API calls to `localhost:8000` (status 200 = good, 4xx/5xx = problem)
- **Test mobile view:** F12 → toggle device toolbar (Ctrl+Shift+M) → pick a phone
- **Reset login state:** F12 → Application → Local Storage → clear the token key

## Project layout

```
frontend/
├── src/
│   ├── main.jsx           # App bootstrap
│   ├── App.jsx            # Router setup (incl. 404 catch-all, /privacy, /terms)
│   ├── index.css          # Design system + all component styles (tokens: koi vermilion on warm paper)
│   ├── api/client.js      # API wrapper → talks to backend
│   ├── auth/AuthContext.jsx  # Token storage, login state (signup does NOT auto-login — email must be verified first)
│   ├── pages/             # One file per page (dashboard, orders, settings, admin/*, public form, tracking, verify-email, legal, 404)
│   ├── components/        # Reusable UI (badges, meters, modals, charts, skeletons, pagination)
│   └── utils/             # Date/business-time, order formatting, live business config (proPricing.js), hooks
├── e2e/                   # Playwright tests — smoke.spec.js (critical paths) + pages.spec.js (every route, console watched), watch.js
├── scripts/
│   └── generate-assets.mjs  # Regenerates favicon.ico / apple-touch-icon / og-image from the SVG logo
├── public/                # Static files served as-is: favicon, apple-touch-icon, og-image, robots.txt
├── package.json           # lint (oxlint) + build scripts
├── playwright.config.js   # E2E config (workers: 1 — dev backend rate-limits by IP)
├── vite.config.js         # Dev proxy → backend
└── index.html             # Meta tags: SEO description, Open Graph (share card), icons
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `npm` not found | Install Node.js LTS, reopen terminal |
| Blank page + console errors | Check backend is running on port 8000 |
| Login "network error" | Backend down, or CORS issue — restart backend |
| Port 5173 busy | Vite auto-picks 5174 — check terminal output |
| Weird stale behavior | Stop server, delete `node_modules/.vite`, `npm run dev` again |
