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

Pro prices, the free-plan allowance, bKash details, and the support email are **not hard-coded**: `src/utils/proPricing.js` fetches `GET /public/stores/pricing` at runtime (module-level cache, fallbacks if the backend is down) and exposes `getProOptions()`, `proPriceFor(months)`, `getFreePlanOrders()`, `getBkash()`, `getSupportEmail()`. Pages call `fetchPublicConfig()` on mount, then bump a state counter to re-render once it lands. **Offers change in `backend/.env` + backend restart — no frontend rebuild.** If you add a new business value: extend `PublicConfigOut` (backend) → the fallback object in `proPricing.js` → a getter → consumers.

## Production build

```bash
npm run build     # outputs optimized files to dist/
npm run preview   # serves the build locally to verify it
```

The `dist/` folder is what gets deployed to your domain (Phase 8).

## E2E smoke tests (Playwright)

Five end-to-end tests cover the critical paths: landing renders, 404 page, signup check-your-email screen, login → dashboard, and public order form → confirmation → tracking.

```bash
# Both dev servers must be running first (backend 8000, frontend 5173)
npx playwright test
```

- Runs one test at a time (`workers: 1`) — the dev backend rate-limits by IP, and parallel tests would trip it
- Uses the long-lived dev seller account (`test@gmail.com`) — no email-verification round trip needed
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
│   ├── components/        # Reusable UI (badges, meters, modals, charts, skeletons)
│   └── utils/             # Date/business-time, order formatting, live business config (proPricing.js), hooks
├── e2e/                   # Playwright smoke tests (smoke.spec.js)
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
