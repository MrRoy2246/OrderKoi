# 📋 OrderKoi — Build Phases Plan

This is our roadmap from zero to production. **After every phase you get a testing checklist** so you can verify everything works yourself before we move on.

**Rule:** we never start a new phase until the current phase's checklist passes 100%.

---

## Phase 0 — Setup & Scaffold
**Goal:** Both apps run on your machine and talk to each other.

**We build:**
- Backend: Python 3.11 venv, FastAPI installed, app skeleton, health endpoint
- Frontend: React (Vite) scaffold, API client pointing at backend
- CORS configured so frontend can call backend

**✅ You test it yourself:**
1. Backend runs: open `http://localhost:8000/docs` → Swagger UI loads
2. `http://localhost:8000/health` returns `{"status": "ok"}`
3. Frontend runs: open `http://localhost:5173` → React welcome page loads
4. Frontend page shows live data fetched from the backend health endpoint

---

## Phase 1 — Database & Seller Authentication (backend)
**Goal:** Sellers can sign up and log in securely.

**We build:**
- SQLite database + SQLAlchemy models (`Seller`)
- Password hashing (bcrypt)
- JWT auth: `POST /auth/signup`, `POST /auth/login`
- Protected test route (`GET /auth/me`) that only works with a valid token

**✅ You test it yourself:**
1. Open `http://localhost:8000/docs`
2. Signup with your email + password → success response with token
3. Login → get access token back
4. Call `GET /auth/me` with token → your info; without token → `401` error
5. Try login with wrong password → clean error message

---

## Phase 2 — Orders Core API (backend)
**Goal:** Complete order management + public tracking API.

**We build:**
- `Order` model: order number, customer name, phone, address, items, total price, notes, status, unique tracking code
- Status workflow: `placed → confirmed → shipped → delivered` (+ `cancelled`)
- Endpoints (auth required): create, list (with filters/search), update, change status
- **Public endpoint (no login):** `GET /track/{tracking_code}` — returns status info for customers

**✅ You test it yourself:**
1. Login in Swagger, create 3–4 test orders
2. List them, filter by status, search by phone
3. Change one order's status step by step
4. Open `http://localhost:8000/track/<code>` in a browser **without logging in** → see order status
5. Try an invalid tracking code → clean `404`

---

## Phase 3 — Frontend Auth & App Shell
**Goal:** Working login/signup pages and app layout.

**We build:**
- Signup & Login pages with validation and error messages
- Token storage + automatic logout on expiry
- Protected dashboard layout (sidebar/topbar), routing
- Nice landing page explaining OrderKoi

**✅ You test it yourself:**
1. `http://localhost:5173` → landing page
2. Sign up a new account → redirected to dashboard
3. Log out → try to visit `/dashboard` directly → kicked back to login
4. Wrong password → clear error message shown

---

## Phase 4 — Seller Dashboard: Order Management
**Goal:** Full order management UI — the seller's daily tool.

**We build:**
- Orders table: list, search, filter by status
- Create order form (modal/page) with validation
- Order detail view with full info
- Status update buttons following the workflow
- Copy tracking link button per order

**✅ You test it yourself:**
1. Create an order from the UI → appears in table instantly
2. Search by customer name/phone → table filters
3. Advance an order `placed → delivered` → status badge updates
4. Click "Copy tracking link" → paste in browser → tracking page opens (Phase 5 makes it pretty)

---

## Phase 5 — Public Tracking Page
**Goal:** The customer-facing page — the reason this product exists.

**We build:**
- `/track/:code` public page (no login)
- Status timeline (Placed ✓ → Confirmed ✓ → Shipped • → Delivered ○)
- Store name, order summary (no sensitive data leaked)
- Mobile-first design (most customers are on phones)
- Nice "order not found" page for bad codes

**✅ You test it yourself:**
1. Open a tracking link on your phone (or browser dev tools mobile view)
2. See live status of the order you created in Phase 4
3. Update status in dashboard → refresh tracking page → new status shows
4. Type a random fake code → friendly "not found" page

---

## Phase 6 — Analytics & Store Settings
**Goal:** Insights + customization = the paid-plan features.

**We build:**
- Dashboard stats: today's orders, pending orders, delivered, revenue
- Simple charts (orders per day, status breakdown)
- Store settings page: store name, phone, logo
- Plan limits structure (free plan: max 50 orders/month — ready for monetization)

**✅ You test it yourself:**
1. Dashboard shows correct counts matching your orders table
2. Charts render with your data
3. Change store name in settings → reflects on the public tracking page

---

## Phase 7 — Testing & Hardening
**Goal:** Confidence — nothing breaks in real usage.

**We build:**
- pytest suite: auth, orders CRUD, tracking endpoint, edge cases
- Input validation everywhere (bad phone numbers, negative prices, oversized inputs)
- Rate limiting on auth & tracking endpoints (brute-force protection)
- Consistent error format, logging

**✅ You test it yourself:**
1. Run `pytest` → all tests green
2. Try to break it: submit empty forms, huge text, negative prices → clean errors
3. Hit login with 10 wrong passwords → temporarily blocked

---

## Phase 7.5–7.7 — Admin Panel, Plans & Password Reset ✅
**Goal:** A platform owner account, free/Pro plans, and self-serve password recovery.

**We built:**
- **Admin as a pure platform account** (no shop of its own) — separate `/admin` panel: platform overview, sellers & plans management, upgrade request queue, subscription ledger
- Free/Pro plans with expiry enforcement; admin can grant durations manually
- **Forgot / reset password** flow — emailed reset links with 30-min single-use tokens
- Admin routes return 403 for sellers/anonymous users (not discoverable)

**✅ You test it yourself:**
1. Log in as admin → `/admin` overview, sellers, requests pages all work; as a seller → `/admin` is blocked
2. Forgot password → email link → set new password → old password rejected, new one works

---

## Phase 7.8 — Public Order Form
**Goal:** Customers order by themselves — no more retyping Messenger messages.

Every seller gets a shareable form link (e.g. `/order/abin-fashion`) to pin on
their Facebook page. The customer fills name/phone/address/items, gets a
tracking code instantly, and the order lands in the seller's dashboard with a
📝 Form badge + an email notification. Prices are what the customer copied
from the seller's Facebook post — the seller reviews and can edit them before
confirming (the natural F-commerce flow).

**We build:**
- `store_slug` on every seller (auto-generated, unique) — the form link
- Public endpoints (no login): `GET /public/stores/{slug}`, `POST /public/stores/{slug}/orders`
- Orders are tagged `source: "form"` vs `"dashboard"`; free-plan limits apply to form orders too
- Seller email notification on every new form order
- Rate limiting on `/public/` endpoints (spam protection)
- Customer form page with live total, validation, success screen with tracking link + WhatsApp share
- "Your public order form" card with copy/preview in Settings; 📝 Form badge in the Orders table

**✅ You test it yourself:**
1. Log in → Settings → copy your order form link → open it in an incognito window
2. Fill the form as a fake customer → "Place order" → see the tracking code
3. Back in your dashboard → Orders → the new order is there with a 📝 Form badge
4. Check the backend terminal → an email notification was logged (console backend)
5. Open the tracking link from the success screen → status shows Placed
6. Edit the order's price (customer may have typed it wrong) → Confirm it → the tracking page updates

---

## Phase 7.9 — Dashboard Polish
**Goal:** The dashboard feels like a real analytics tool.

**We build:**
- Date-range tabs on the dashboard: **Today / 7 days / 30 days / All time** — stats and the chart follow the selection
- **Clickable stat cards** — tap "Pending orders" to see exactly those orders, tap "Delivered" for delivered ones
- New "Pending" filter in the Orders page (= placed + confirmed, the seller's to-do list), and the filter is shareable via URL (`/dashboard/orders?status=pending`)
- Plan banner: free sellers see their upgrade path; Pro sellers see their expiry date

**✅ You test it yourself:**
1. Dashboard → switch between Today / 7 days / 30 days / All time → numbers and chart change
2. Click the "Pending orders" card → Orders page opens, filtered to pending
3. In Orders, pick "Pending (awaiting action)" in the dropdown → only placed + confirmed orders

---

## Phase 7.10 — Pro Durations & Upgrade Requests
**Goal:** Real subscription business with manual bKash payments.

Pro now has durations: **1 month (৳350) · 6 months (৳1,750) · 12 months (৳2,900)**. The flow:
seller pays via bKash → submits an upgrade request with the transaction ID →
admin gets an email → admin verifies the payment and approves → Pro activates until
the paid-for date (renewals stack on remaining time). Expired Pro automatically
falls back to Free limits.

**We build:**
- Seller side (Settings → "Plan & subscription"): current plan + expiry, duration picker, payment instructions, request with transaction ID, request history
- Admin side: "Upgrade Requests" page — pending queue with Approve/Reject, history table; overview shows a red banner when requests are waiting
- Emails: admins are notified of new requests; sellers are notified on approve/reject
- API: upgrade request endpoints, plan expiry enforcement everywhere (dashboard + public form limits), admin stats include pending request count

**✅ You test it yourself:**
1. Log in as a **seller** → Settings → pick 6 months → enter a fake transaction ID → "Request Pro"
2. Log in as **admin** (separate browser/incognito) → red banner on Platform Overview → "Review requests"
3. Verify the TrxID → **Approve — activate Pro** → the seller's banner becomes "⭐ Pro active — unlimited orders until <date>"
4. Back as the seller → Settings shows the request history with "Approved"
5. Admin → Sellers & Plans → the store now shows "⭐ Pro until <date>"

---

## Phase 7.11 — Subscription Card & Custom Reports
**Goal:** Pro-grade polish: always-visible subscription status and fully flexible reports.

**We build:**
- **Subscription card** on the dashboard (clickable → Settings):
  - Pro: "⭐ Pro — unlimited orders until 1 Mar 2027" + a days-left meter
  - Free: live one-time allowance meter ("N of 15 free orders used") — same footer-strip style as the Pro meter, amber past 75% used
  - Expired: "Your subscription ended <date> — you're back on Free limits"
- **Custom date range**: a "Custom" tab beside Today/7d/30d/All with From → To date
  pickers (max one year, validated on both frontend and backend)
- Chart and every stat card follow the selected range; chart labels thin out
  automatically for long ranges

**✅ You test it yourself:**
1. Dashboard → the subscription card shows your plan, exact expiry date, and usage/days-left meter
2. Click the card → opens the plan options in Settings
3. Range tabs → "Custom" → pick e.g. 1 Aug → 31 Aug → Apply → stats and chart show exactly that window
4. Try an invalid range (start after end, or 2 years) → clean error, no crash

---

## Phase 7.12 — Subscription History (Admin Ledger)
**Goal:** The admin always knows who subscribed, renewed or cancelled — and exactly when.**We build:**
- **Subscription ledger** (`subscription_events` table): every plan change leaves a permanent entry
  - From approved upgrade requests: "Subscribed" (first time) or "Renewed" (extension), with the paid-for months
  - From seller cancellations: "Cancelled", marked "cancelled by seller"
  - From manual admin plan changes: noted as "activated/downgraded manually by admin"
- **Admin → Upgrade Requests page → "Subscription history" table**: When (date + time) | Store | Event badge | Duration | Note — newest first
- `GET /admin/subscription-events` (admin-only) powers it

**✅ You test it yourself:**
1. As a seller: request a Pro upgrade → as admin, approve it → as the seller again, cancel it
2. Admin → Upgrade Requests → scroll to "Subscription history" → you see three moments in order: Subscribed, then Cancelled, with timestamps
3. Try `/admin/subscription-events` while logged out or as a seller → 401/403

---

## Phase 7.13 — Free-Plan Allowance & Limit Experience ✅ (2026-09-05)
**Goal:** A clear, professional free plan: sellers get a taste, then upgrade. Nobody is surprised.

The free plan is a **one-time allowance of 15 orders** (not monthly). After it's used, the
store is paused for new orders — dashboard AND public form — until the seller upgrades
to Pro (unlimited). Existing data is never touched; cancelled orders return their unit
to the allowance.

**We build:**
- Lifetime (not monthly) order count gates order creation: dashboard + public form → `402` with an upgrade message
- `GET /stats/summary` returns the meter data (`month_orders` = lifetime used, `plan_limit` = 15 or `null` on Pro)
- Free-order meter — one line (label · bar · remaining count) in the subscription card's footer strip; compact variant on the Orders page; amber past 75% used
- Pro card uses the **same footer-strip meter** for days-left ("Pro active — N days left · expires …"), red inside the last week before expiry
- Limit-reached: focused amber banner on Dashboard + Orders (seller), paused-store card on the public form (customer) — shown up front via `PublicStoreOut.is_accepting_orders`, and mid-fill on 402
- `GET /auth/subscription-history` — the seller's own ledger in Settings (date + time); `SubscriptionEvent.request_id` dedupes "Approved" + "Pro activated" into one row
- Admin overview: all six KPI cards follow the global date filter (window figures; all-time in the hints)

**✅ You test it yourself:**
1. Fresh seller → create 15 orders (dashboard or form) → 16th gets a clean upgrade prompt
2. The customer form link now shows a "temporarily paused" card up front
3. Log in as `demo.seller@example.com` (15/15) → see the banner; `meter.check@example.com` (12/15) → see the meter
4. Upgrade to Pro → unlimited; the card shows the days-left footer strip (red near expiry: `expiring.pro@example.com`)
5. Settings → subscription history shows one row per lifecycle moment (approved, cancelled, renewed)

---

## Phase 8 — Production Ready & Deployment
**Goal:** Live on your domain — with real email, backups, monitoring, and nothing that dies on day 2.

Broken into sub-phases so progress stays trackable. Launch order was revised
after the 2026-09-06 production-readiness audit: **code fixes first →
PostgreSQL → Docker/deploy → launch guardrails → fast-follow hardening.**

---

### Phase 8a — Real SMTP Email ✅ (2026-09-06)

**We built:**
- All SMTP settings in `.env` (empty `SMTP_HOST` = console backend for tests/dev)
- Signup → welcome + verification email (single-use 24h token; login blocked until verified; resend endpoint with anti-enumeration)
- Customer emails: "order received" on public form submission + status-change email on every dashboard status advance
- Sends moved to **background threads with retry/backoff** (3 attempts) — the API never waits on Gmail, and a failed send never breaks a request

**✅ Verified:**
- [x] Live SMTP end-to-end: signup → click email link → verified → login works
- [x] Wrong/expired/consumed verification links give clean messages
- [x] Order emails arrive for customer and on status changes
- [x] 18 new tests (test_email_verification.py) — suite now 177/177

---

### Phase 8a+ — Pre-Deploy Hardening Batch ✅ (2026-09-06)

The audit fixes that need **no Postgres and no Docker** — all landed:

- [x] Password reset now **invalidates pre-reset JWTs** (`sellers.token_invalid_before` + `iat` claim)
- [x] Per-account **login lockout**: 5 wrong passwords / 15 min → 15-min lock, IP-rotation-proof (`app/login_throttle.py`)
- [x] **Security headers** middleware (nosniff, frame-deny, referrer, permissions)
- [x] `/ready` DB-touching readiness probe (503 when the DB is down) alongside `/health`
- [x] **Honeypot** on the public order form — bots get a fake success, nothing stored
- [x] Frontend **404 page**, **Privacy Policy** + **Terms of Service** pages (landing footer links)
- [x] Strong 64-hex dev `SECRET_KEY` (production gets a fresh one at deploy)
- [x] **Playwright E2E smoke suite** — 5 tests: landing, 404, signup screen, login→dashboard, public order→tracking
- [x] **DB backups**: `backend/scripts/backup_db.py` (WAL-safe, keeps 14) running daily 3:07 AM via Windows Task Scheduler
- [x] **Public assets**: favicon.ico + apple-touch-icon fallbacks, 1200×630 og-image share card (brand font), robots.txt (disallows `/track/`) — regenerable via `frontend/scripts/generate-assets.mjs`
- [x] Docs refreshed (BACKEND_GUIDE, FRONTEND_GUIDE), unused assets removed

**✅ Verified:** backend 177/177 · Playwright 5/5 · build clean · backup integrity-checked while server live.

---

### Phase 8b — PostgreSQL Shift ✅ (2026-09-07)

**Goal:** The production database, with real migrations.

**We built:**
- `psycopg[binary]` driver; dedicated `orderkoi` role + database on local PostgreSQL 17 (port **5433**); all credentials env-driven (`PG_*` vars compose the URL, `DATABASE_URL` overrides)
- **Alembic** owns the schema (`backend/migrations/`, initial `faeac3112e6b`); startup `create_all` removed — fresh DB = `alembic upgrade head`
- Existing dev data migrated id-preserving with sequence resets
- **SQLite fully removed the same day:** no dialect branches, Postgres-native date expressions, aware datetimes end-to-end, legacy scripts deleted
- Tests run on PostgreSQL in a dedicated `orderkoi_test` database — suite **187/187**; E2E and live endpoints verified against PG
- `scripts/backup_db.py` → pg_dump custom format (Task Scheduler job unchanged)

**Deferred (before/with 8c):** `Float` → `Numeric(12,2)` money columns — orthogonal to the DB shift, needs its own Alembic revision + Decimal handling.

**✅ You test it yourself:**
1. Backend starts against Postgres; signup → create order → track works
2. Old JWTs still valid; login lockout still locks
3. `pytest` green against the Postgres-backed app
4. Stats/charts numbers match the SQLite run exactly

---

### Phase 8b+ — Admin Bootstrap, Pre-Deploy Audit & Env-Driven Config ✅ (2026-09-07)

**Goal:** Everything between "Postgres works" and "put it in containers" — plus the ability to change any offer without touching code.

**We built:**
- **`scripts/create_admin.py`** (replaced seed_admin + make_admin) — idempotent: `python -m scripts.create_admin <email> [password]`; sets `email_verified=True` (login gate), promotes existing accounts, 12+ char passwords
- **Full pre-Docker audit** of backend + frontend: no code bugs found; dead code removed, gunicorn added; deploy gotchas captured (proxy headers, CSP, 1-worker)
- **Repricing:** Pro = **৳350 / ৳1,750 / ৳2,900** (1/6/12 months) everywhere
- **Env-driven business config:** `GET /public/stores/pricing` serves Pro prices, free-plan allowance, bKash number/type, support email — all from `.env` (`PRO_PRICE_1M/6M/12M`, `FREE_PLAN_ORDERS`, `BKASH_NUMBER`, `BKASH_TYPE`, `SUPPORT_EMAIL`), read per-request. Frontend fetches live with fallbacks (PlanSection, Dashboard, OrderFormModal, Terms, Privacy, AdminRequests). **Changing an offer = `.env` edit + backend restart — no rebuild, no deploy.**
- **Comment/docstring sweep:** professional file-level docs across every backend module and frontend page

**✅ Verified:** backend 189/189 · build + lint clean · live config endpoint checked · env-override test proves a flipped price flows end-to-end.

---

### Phase 8c — Dockerize & Deploy ⏳ (NEXT)

**Goal:** The whole stack in containers, HTTPS on your domain.

**We build:**
- `backend/Dockerfile` — Python slim, gunicorn + uvicorn workers (**1 worker** — rate limiter & login throttle are in-memory; Redis is the scale-out upgrade)
- `frontend/Dockerfile` — node build stage with `VITE_API_URL` build arg, then nginx serving `dist/`
- `docker-compose.yml` — backend + frontend + **Postgres with a volume** + **Caddy** reverse proxy (auto-TLS; CSP header gets set here)
- `.dockerignore` files (venv, node_modules, dist must not bake into images)
- Production `.env`: fresh strong `SECRET_KEY`, real `CORS_ORIGINS`, `FRONTEND_URL` = real domain, `ENVIRONMENT=production`
- Bootstrap admin with a strong password (`python -m scripts.create_admin admin@yourdomain.com` — idempotent, account arrives email-verified)
- **Nightly `pg_dump` backups to a second location** (a backup on the same disk is not a backup)

**✅ You test it yourself:**
1. `docker compose up` → whole stack runs in containers
2. Full walkthrough on the deployed URL: signup → create order → track order
3. HTTPS padlock works; email links point at the real domain
4. Share your tracking link with a friend → they see it working 🎉

---

### Phase 8d — Launch Guardrails ⏳ (at/just before launch)

Small items, mostly account signups — but without them you're flying blind:

- [ ] **Real email provider** (Brevo/Resend free tier) — personal Gmail app password is not a production sender (500/day cap, spam-folder risk). Swap is a `.env` edit only
- [ ] **Sentry** (free tier) — backend + frontend SDKs, DSN in `.env`; otherwise the first real bug is invisible
- [ ] **Uptime monitoring** (UptimeRobot/BetterStack free) pinging `/health` + `/ready`, alerting your email/Telegram
- [ ] Real **domain + DNS**
- [ ] `og:image` URL made **absolute** in `index.html` (one line, once the domain exists)

---

### Phase 8e — Fast-Follow Hardening ⏳ (first weeks after launch)

Safe to launch without; schedule soon after:

- [ ] Admin **MFA** (the admin account is the most powerful login)
- [ ] Admin endpoint **pagination** (breaks only at hundreds of sellers)
- [ ] Free-plan **TOCTOU race** fix (1-order edge case)
- [ ] `month_orders` field rename (breaking API change — coordinate with frontend)
- [ ] **Redis-backed** rate limiting + login throttle (needed when running >1 worker)
- [ ] **Load test** before any marketing push
- [ ] Bengali localization, tracking auto-refresh, bKash API, seller self-serve deletion → product roadmap (post-launch)

---

## 📅 Suggested pace

| Phase | Rough effort |
|---|---|
| 0 | 1 session |
| 1–2 | 1–2 sessions each |
| 3–5 | 1–2 sessions each |
| 6 | 1 session |
| 7 | 1 session |
| 8a + 8a+ | ✅ done |
| 8b + 8b+ | ✅ done (2026-09-07) |
| 8c + 8d | 1 session + deployment |
| 8e | spread over the first weeks |

After Phase 8 → **find 3 real sellers** to use it free for feedback. That's Phase 9 — the real world. 🚀
