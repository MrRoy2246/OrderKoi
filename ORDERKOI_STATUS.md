# OrderKoi — Project Status

_Last updated: 2026-09-07_

## ✅ Completed

| Phase                                             | What was built                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Phase 0 — Setup & Scaffold**                    | FastAPI backend + React 19 / Vite frontend, SQLite dev database, dev servers                                                                                                                                                                                                                                                        |
| **Phase 1 — Database & Seller Auth**              | Seller model, JWT login/signup, password hashing, slugs                                                                                                                                                                                                                                                                             |
| **Phase 2 — Orders Core API**                     | Orders CRUD, items, status workflow (placed → confirmed → shipped → delivered / cancelled), tracking codes, public tracking endpoint                                                                                                                                                                                                |
| **Phase 3 — Frontend Auth & App Shell**           | Login/signup pages, AuthContext, route guards, app layout                                                                                                                                                                                                                                                                           |
| **Phase 4 — Seller Dashboard**                    | Orders list (search, filter, pagination), order detail, status changes, create-order modal                                                                                                                                                                                                                                          |
| **Phase 5 — Public Tracking Page**                | `/track/:code` — customer-facing status page, no login                                                                                                                                                                                                                                                                              |
| **Phase 6 — Analytics & Store Settings**          | Dashboard stats, daily chart, status breakdown, store settings                                                                                                                                                                                                                                                                      |
| **Phase 7 — Testing & Hardening**                 | Test suite, rate limiting, security review (now 165/165 passing)                                                                                                                                                                                                                                                                    |
| **Phase 7.5 — Admin Panel & Plans**               | Admin overview, sellers & plans management, upgrade requests                                                                                                                                                                                                                                                                        |
| **Phase 7.6 — Admin as pure platform account**    | Admin has no shop; separate admin panel                                                                                                                                                                                                                                                                                             |
| **Phase 7.7 — Forgot / Reset Password**           | Email reset links, 30-min tokens                                                                                                                                                                                                                                                                                                    |
| **Phase 7.8 — Public Order Form**                 | `/order/:slug` — customers submit orders without login; store shows a paused page up front when the free allowance is exhausted                                                                                                                                                                                                     |
| **Phase 7.9 — Dashboard polish**                  | Date ranges (today/7d/30d/all/custom), clickable stat cards                                                                                                                                                                                                                                                                         |
| **Phase 7.10 — Pro durations & upgrade workflow** | 1/6/12-month Pro options, bKash payment instructions, request → approve/reject flow, subscription ledger, admin duration-grant modal, granted-until snapshots on past requests, unified store-history modal                                                                                                                    |
| **Audit remediation**                             | 9/10 issues fixed, 1 skipped by decision (seller order-editing); timezone-correct stats (Asia/Dhaka), CSV export, POST-scoped rate limits                                                                                                                                                                                           |
| **Frontend redesign (A–F)**                       | New design system "Koi vermilion on warm paper" — tokens, Manrope font, SVG icon set, koi logo/favicon, shared badge/timeline/skeleton/empty-state components, sidebar + mobile drawer, mobile order cards, redesigned all 14 pages, landing page with product mock, full CSS rewrite, a11y + reduced-motion, responsive 320px→wide |
| **Production-readiness review (2026-09-02)**      | Full backend + frontend audit for real-life readiness — findings and the agreed roadmap are below. Git initialized (`.gitignore` + first commit) protecting `.env`/DB/node_modules.                                                                                                                                                  |
| **Free plan one-time allowance (2026-09-05)**     | Free plan = **15 orders, one-time** (config `free_plan_orders`), not monthly. Lifetime non-cancelled order count gates both dashboard creation and the public form (402 + upgrade prompt when exhausted; cancelled orders return their unit). `stats/summary` returns the usage meter (`month_orders` = lifetime used, `plan_limit`). Focused limit-reached banner (seller) + paused-store page (customer, via `PublicStoreOut.is_accepting_orders`). |
| **Allowance meter + unified subscription card (2026-09-05)** | Free meter and Pro days-left meter share ONE footer-strip style in the subscription card (single line: label · bar · trailing slot); compact variant on the Orders page; Pro bar turns red inside the final week before expiry. |
| **Seller subscription history (2026-09-05)**      | `GET /auth/subscription-history` — the seller sees their own ledger in Settings (date + time). `SubscriptionEvent.request_id` links events to the approved request that caused them, so "Approved" + "Pro activated" collapse into ONE history row; admin approval stamps it. |
| **Admin overview KPI scoping (2026-09-05)**       | All six admin KPI cards now follow the global date filter — window-scoped figures summed from the same series the charts plot; all-time context lives in the hint line. |
| **Full email system (2026-09-06)**                | Every account/email-touching event now sends real mail via `app/emails.py` templates + SMTP from `backend/.env`: signup welcome+verification (single-use 24h token, login blocked until verified, resend endpoint w/ anti-enumeration), password reset (already existed), customer "order received" on public form submission, and customer status-change emails on every dashboard status advance. Existing accounts backfilled `email_verified=1`. Switching senders = edit `.env` only. |
| **Pre-deploy hardening batch (2026-09-06)**       | Audit remediations that don't need Postgres/Docker: SMTP sends moved to background threads with retry+backoff (API responses no longer wait on Gmail); password reset now invalidates pre-reset JWTs (`sellers.token_invalid_before` + `iat` claim — `scripts/migrate.py` adds the column); per-account login lockout (5 fails / 15 min → 15 min lock, `app/login_throttle.py`, IP-rotation-proof); security headers middleware (nosniff/DENY/referrer/permissions); `/ready` DB-touching readiness probe; public-form honeypot (bots get fake 201, nothing stored); frontend 404 page; Privacy Policy + Terms pages (linked from landing footer); strong 64-hex dev `SECRET_KEY`; Playwright E2E smoke (5 tests: landing, 404, signup screen, login→dashboard, public order→tracking). Backend 177/177. |
| **Phase 8b — PostgreSQL shift (2026-09-07)**      | Dev database moved from SQLite to local **PostgreSQL 17.4** (port 5433; PG 15 owns 5432). All DB credentials in `backend/.env` via `PG_*` vars (`PG_HOST/PORT/DATABASE/USER/PASSWORD`) that compose into the URL — a full `DATABASE_URL` overrides. Dedicated `orderkoi` role + database (no superuser in the app). Driver `psycopg[binary]` (psycopg3); engine pools connections, `pool_pre_ping`, session pinned to `TimeZone=UTC`. **Alembic adopted** (`backend/migrations/`, initial schema `faeac3112e6b`); `create_all` removed from startup — schema changes are `alembic revision --autogenerate` + `upgrade head`. Existing dev data migrated id-preserving with sequence resets. `scripts/backup_db.py` pg_dumps (the 3:07 AM task needs no change). **Same day — SQLite fully removed:** no dialect branches anywhere; `business_day()`/`business_month()` plain Postgres expressions; all datetimes aware end-to-end (`as_aware`/`as_naive_utc` and every naive-UTC special case deleted); tests now run on PostgreSQL in a dedicated `orderkoi_test` database (auto-created, `CREATEDB` granted); legacy scripts (`migrate.py`, `sqlite_to_postgres.py`, `bench_stats.py`) and the dead `orderkoi.db` deleted (git history + one pre-shift `.db` backup retain them). Backend tests **187/187 on PostgreSQL**; Playwright E2E 5/5; live-verified login, seller stats, admin stats (daily + monthly paths), CSV export, order writes, public tracking, pg_dump backup. |

**Current state:** fully working product on dev servers, on PostgreSQL 17. Backend tests 187/187 (run on PostgreSQL, `orderkoi_test` database). Playwright E2E smoke 5/5 (`frontend/e2e/smoke.spec.js` — dev servers must be running: `npx playwright test`). Frontend build + lint clean. Gmail SMTP live (app password in `backend/.env`, sends are background now).

**Agreed launch order (revised 2026-09-06):** ① pre-deploy code fixes (DONE — see hardening batch above) → ② shift to PostgreSQL (DONE 2026-09-07 — see Phase 8b row) → ③ Dockerize + deploy after ② is verified.

---

## ✅ Phase 8a — Real SMTP email (DONE 2026-09-06)

- [x] `backend/.env` + `backend/.env.example` — all SMTP credentials live in env (Gmail: `smtp.gmail.com:587` STARTTLS, app password; empty `SMTP_HOST` = console backend). Switching senders = edit `.env`/compose env only.
- [x] Signup sends welcome + verification email (combined); `EmailVerificationToken` model (SHA-256 hashed, single-use, 24h); `GET /auth/verify-email?token=…` activates; login 403-blocked until verified; `POST /auth/resend-verification` (anti-enumeration, rate-limited); existing accounts backfilled verified. Frontend: `/verify-email` page, Signup "check your email" state, Login resend button.
- [x] Customer emails: "order received" on public form submission + status-change email on every dashboard status advance (skipped silently when order has no customer email; failures never break the API).
- [x] Backend tests 165/165 incl. 18 new email tests (`test_email_verification.py` + additions).
- [x] ~~**← waiting on user:** Gmail app password~~ DONE 2026-09-06 — live SMTP verified end-to-end (signup+verify, login gate, resend, order emails).

## ✅ Phase 8b — PostgreSQL shift (DONE 2026-09-07)

- [x] `psycopg[binary]` + `alembic` in `backend/requirements.txt`
- [x] DB credentials fully env-driven: `PG_*` vars in `.env` compose into the connection URL (`DATABASE_URL` overrides if set). Changing user/password/host/port = edit `.env` only. Missing both = boot error.
- [x] Dedicated `orderkoi` role + database on the local PostgreSQL 17 (port **5433** — PG 15 owns 5432); the app never uses the superuser.
- [x] Alembic schema management (`backend/migrations/`); startup `create_all` removed; `alembic upgrade head` sets up a fresh DB.
- [x] SQLite removed entirely (2026-09-07, same day): Postgres-only engine/config with no dialect branches; `business_day()`/`business_month()` plain PG expressions; datetimes aware end-to-end (`as_aware`/`as_naive_utc` and the naive-UTC special cases deleted).
- [x] Existing dev data migrated id-preserving with sequence resets (one-off script, retained in git history); the dead `orderkoi.db` deleted.
- [x] Tests run on PostgreSQL in a dedicated `orderkoi_test` database (auto-created; `CREATEDB` granted to the role) — full suite **187/187**; E2E and live endpoints verified against PG.
- [x] `scripts/backup_db.py` → pg_dump custom format (Task Scheduler job unchanged); SQLite-era scripts deleted.
- [ ] **Follow-up (deferred, before/with 8c):** `Float` → `Numeric(12,2)` money columns (exact taka). Orthogonal to the DB shift — floats drift the same on any engine — deferred to avoid destabilizing the verified migration; needs its own Alembic revision + Decimal handling in schemas/CSV.

## 🔴 Phase 8c — Dockerize + deploy

- [ ] `backend/Dockerfile` — Python slim image, requirements, gunicorn running uvicorn workers (**1 worker** — the in-memory rate limiter is per-process; Redis-backed limiter is the scale-out upgrade)
- [ ] `frontend/Dockerfile` — node build stage passing `VITE_API_URL` as a build arg (the API base is baked at build time in `src/api/client.js`), then nginx serving `dist/`
- [ ] `docker-compose.yml` — backend + frontend(nginx) + Postgres with a volume + Caddy reverse proxy for auto-TLS (recommended; handles HTTPS certificates for the domain)
- [ ] `.dockerignore` files — backend `venv/` and frontend `node_modules/`/`dist/` must not bake into images
- [ ] Production `.env` — fresh strong `SECRET_KEY` (boot validation already refuses the default), real `CORS_ORIGINS` (production domain), `FRONTEND_URL` = real domain (reset-link emails use it), `ENVIRONMENT=production`
- [ ] Bootstrap the admin account in the fresh DB (`python -m scripts.create_admin admin@yourdomain.com` — idempotent, prints a random password once, account is email-verified so the login gate lets it in; promote an existing account by passing that email)
- [ ] VPS or managed host + domain; nightly DB backups (cron `pg_dump` to a second location); uptime monitoring
- [ ] Decide: point `docker-compose` at the existing dev Postgres data (migrated) or start clean

## 🟠 Before/just after launch (Phase 8d — launch guardrails)

- [x] Real bKash number in `frontend/src/components/PlanSection.jsx` — 01736060259 (Personal), done 2026-09-06
- [x] Legal & trust pages — Privacy Policy, Terms of Service, contact email (landing footer) — done 2026-09-06 (`/privacy`, `/terms`)
- [x] 404 page — done 2026-09-06 (`NotFound.jsx`)
- [x] Favicon fallbacks (`favicon.ico`, `apple-touch-icon.png`) + delete unused `public/icons.svg` — done 2026-09-06 (regenerable via `frontend/scripts/generate-assets.mjs`; also removed unused `src/assets/hero.png` + `vite.svg`)
- [x] `og:image` social share card + `robots.txt` — done 2026-09-06 (`public/og-image.png` 1200×630 with brand font; robots.txt disallows `/track/`; og:image URL must be made absolute at deploy)
- [x] Frontend smoke test — done 2026-09-06 (Playwright E2E, 5 tests)
- [x] Session security revisit — server-side invalidation done 2026-09-06 (password reset invalidates pre-reset JWTs via `sellers.token_invalid_before`)
- [x] DB backups (SQLite era) — done 2026-09-06: `backend/scripts/backup_db.py` (daily 3:07 AM via Windows Task Scheduler "OrderKoi DB backup", keeps 14, WAL-safe)
- [ ] **Real email provider** (Brevo/Resend free tier) — personal Gmail app password is not a production sender (500/day cap, spam risk); swap is a `.env` edit only
- [ ] Error tracking — Sentry free tier (backend + frontend SDKs, DSN in `.env`)
- [ ] Uptime monitoring (UptimeRobot/BetterStack free) pinging `/health` + `/ready`
- [ ] Real domain + DNS; make `og:image` URL absolute in `index.html`

## 🟠 Fast-follow hardening (Phase 8e — first weeks after launch)

- [ ] Admin MFA (the admin account is the most powerful login)
- [ ] Admin endpoint pagination (breaks only at hundreds of sellers)
- [ ] Free-plan TOCTOU race fix (1-order edge case)
- [ ] `month_orders` field rename (breaking API change — coordinate with frontend)
- [ ] Load test before any marketing push

## 🟡 Product roadmap (post-launch)

- [ ] Tracking page auto-refresh / polling
- [ ] Admin seller drill-down (view one seller's orders)
- [ ] Help / FAQ page + WhatsApp support link
- [ ] Bengali localization
- [ ] Online payment gateway (bKash API instead of manual TrxID verification)
- [ ] Seller account/data deletion (data protection)
- [ ] Redis-backed rate limiting (needed only when running multiple backend workers)

---

## 📋 Production-readiness review (2026-09-02) — what the audit found

**Already real-project quality:** SECRET_KEY boot validation in production; per-IP sliding-window rate limits on login/signup/forgot-password/tracking/public-form; generic 500s (no stack traces leak); `/health` endpoint; Pydantic validation on every input; tracking page hides addresses/phones; admin routes 403 (not discoverable); 165 tests; WAL mode; email failures never crash requests; `create_admin.py` exists.

**Gaps (each addressed by a Phase 8 step above):** no Docker files; frontend API URL baked at build time (needs Docker build arg); `FRONTEND_URL` in email links must point at the real domain; CORS defaults to localhost; no production WSGI server or Postgres driver in requirements; SMTP console-only until Phase 8a; in-memory rate limiter assumes a single worker; no backups; no migrations tool; no TLS termination (→ Caddy).

**Dev quirks on this machine:** `uvicorn --reload` hangs — run the backend without `--reload` and restart it manually after every backend edit. Test accounts (dev DB): `abin@test.com / secretpass123` (admin) · `test@gmail.com / test123456789` (seller, Pro, ~165 seeded orders) · `demo.seller@example.com / DemoSeller#2026` (seller, free, 15/15 — shows the limit-reached state) · `meter.check@example.com / metercheck12345` (free, 12/15 — shows the meter) · `ruby.boutique@example.com / rubypass12345` (Pro) · `expiring.pro@example.com / ExpiringPro#1` (Pro, expires in 3 days — shows the red near-expiry meter). Dev servers: backend `http://localhost:8000` · frontend `http://localhost:5173`.
