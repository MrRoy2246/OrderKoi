# OrderKoi — Project Status

_Last updated: 2026-09-02_

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
| **Phase 7 — Testing & Hardening**                 | Test suite (126/126 passing), rate limiting, security review                                                                                                                                                                                                                                                                        |
| **Phase 7.5 — Admin Panel & Plans**               | Admin overview, sellers & plans management, upgrade requests                                                                                                                                                                                                                                                                        |
| **Phase 7.6 — Admin as pure platform account**    | Admin has no shop; separate admin panel                                                                                                                                                                                                                                                                                             |
| **Phase 7.7 — Forgot / Reset Password**           | Email reset links, 30-min tokens                                                                                                                                                                                                                                                                                                    |
| **Phase 7.8 — Public Order Form**                 | `/order/:slug` — customers submit orders without login                                                                                                                                                                                                                                                                              |
| **Phase 7.9 — Dashboard polish**                  | Date ranges (today/7d/30d/all/custom), clickable stat cards                                                                                                                                                                                                                                                                         |
| **Phase 7.10 — Pro durations & upgrade workflow** | 1/6/12-month Pro options, bKash/Nagad payment instructions, request → approve/reject flow, subscription ledger, admin duration-grant modal, granted-until snapshots on past requests, unified store-history modal                                                                                                                    |
| **Audit remediation**                             | 9/10 issues fixed, 1 skipped by decision (seller order-editing); timezone-correct stats (Asia/Dhaka), CSV export, POST-scoped rate limits                                                                                                                                                                                           |
| **Frontend redesign (A–F)**                       | New design system "Koi vermilion on warm paper" — tokens, Manrope font, SVG icon set, koi logo/favicon, shared badge/timeline/skeleton/empty-state components, sidebar + mobile drawer, mobile order cards, redesigned all 14 pages, landing page with product mock, full CSS rewrite, a11y + reduced-motion, responsive 320px→wide |
| **Production-readiness review (2026-09-02)**      | Full backend + frontend audit for real-life readiness — findings and the agreed roadmap are below. Git initialized (`.gitignore` + first commit) protecting `.env`/DB/node_modules.                                                                                                                                                  |

**Current state:** fully working product on dev servers. Backend tests 126/126. Frontend build + lint clean. Git repo initialized (`main`, initial commit `b128f1d`).

**Agreed launch order (decided 2026-09-02):** ① real SMTP with personal email + test everything → ② shift to PostgreSQL → ③ if all OK, Dockerize + deploy.

---

## 🔴 Phase 8a — Real SMTP email (next session, start here)

- [ ] Get SMTP credentials for a personal email (Gmail app-password is the usual route; Brevo/Resend also work) and put them in `backend/.env` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`) — the code path already exists in `app/email.py` (starttls + login, console fallback when host is empty)
- [ ] Test password-reset email end-to-end (request link → receive email → reset works)
- [ ] Test Pro approval/rejection emails and new-form-order notification emails
- [ ] Confirm emails don't slow down requests noticeably (they're sent inline today — if slow, move to a background thread/task later)

## 🔴 Phase 8b — PostgreSQL shift

- [ ] Add `psycopg[binary]` to `backend/requirements.txt`
- [ ] Change `DATABASE_URL` to `postgresql+psycopg://…` in `.env` (config already supports it — `app/database.py` only special-cases `sqlite://` URLs)
- [ ] Verify the aware/naive datetime handling against Postgres (SQLite returns naive datetimes; Postgres with `DateTime(timezone=True)` returns aware — `as_aware()` and the timezone helpers must still line up)
- [ ] Run the full test suite against Postgres (tests currently use in-memory SQLite — decide whether to keep SQLite for tests, which is fine)
- [ ] Check `scripts/migrate.py` is SQLite-only and not needed once on Postgres (fresh schema via `create_all`; Alembic remains the future proper answer)

## 🔴 Phase 8c — Dockerize + deploy

- [ ] `backend/Dockerfile` — Python slim image, requirements, gunicorn running uvicorn workers (**1 worker** — the in-memory rate limiter is per-process; Redis-backed limiter is the scale-out upgrade)
- [ ] `frontend/Dockerfile` — node build stage passing `VITE_API_URL` as a build arg (the API base is baked at build time in `src/api/client.js`), then nginx serving `dist/`
- [ ] `docker-compose.yml` — backend + frontend(nginx) + Postgres with a volume + Caddy reverse proxy for auto-TLS (recommended; handles HTTPS certificates for the domain)
- [ ] `.dockerignore` files — backend `venv/` and frontend `node_modules/`/`dist/` must not bake into images
- [ ] Production `.env` — fresh strong `SECRET_KEY` (boot validation already refuses the default), real `CORS_ORIGINS` (production domain), `FRONTEND_URL` = real domain (reset-link emails use it), `ENVIRONMENT=production`
- [ ] Bootstrap the admin account in the fresh DB (`backend/scripts/seed_admin.py` exists) with a strong password
- [ ] VPS or managed host + domain; nightly DB backups (cron `pg_dump` to a second location); uptime monitoring
- [ ] Decide: point `docker-compose` at the existing dev Postgres data (migrated) or start clean

## 🟠 Before/just after launch

- [ ] Real bKash/Nagad numbers in `frontend/src/components/PlanSection.jsx` — _owner task_
- [ ] Legal & trust pages — Privacy Policy, Terms of Service, contact email (landing footer + tracking pages)
- [ ] 404 page (unknown URLs currently redirect to landing)
- [ ] Favicon fallbacks (`favicon.ico`, `apple-touch-icon.png`) + delete unused `public/icons.svg`
- [ ] `og:image` social share card + `robots.txt`
- [ ] Error tracking (Sentry free tier) + frontend smoke test (Playwright: login → create order → track)
- [ ] Session security revisit (token expiry / server-side invalidation)

## 🟡 Product roadmap (post-launch)

- [ ] Customer notifications on status change (email/SMS) — the core "order koi?" killer feature
- [ ] Tracking page auto-refresh / polling
- [ ] Email verification at signup
- [ ] Admin seller drill-down (view one seller's orders)
- [ ] Help / FAQ page + WhatsApp support link
- [ ] Bengali localization
- [ ] Online payment gateway (bKash API instead of manual TrxID verification)
- [ ] Seller account/data deletion (data protection)
- [ ] Alembic migrations (replaces `create_all` + `scripts/migrate.py`)
- [ ] Redis-backed rate limiting (needed only when running multiple backend workers)

---

## 📋 Production-readiness review (2026-09-02) — what the audit found

**Already real-project quality:** SECRET_KEY boot validation in production; per-IP sliding-window rate limits on login/signup/forgot-password/tracking/public-form; generic 500s (no stack traces leak); `/health` endpoint; Pydantic validation on every input; tracking page hides addresses/phones; admin routes 403 (not discoverable); 126 tests; WAL mode; email failures never crash requests; `seed_admin.py` exists.

**Gaps (each addressed by a Phase 8 step above):** no Docker files; frontend API URL baked at build time (needs Docker build arg); `FRONTEND_URL` in email links must point at the real domain; CORS defaults to localhost; no production WSGI server or Postgres driver in requirements; SMTP console-only until Phase 8a; in-memory rate limiter assumes a single worker; no backups; no migrations tool; no TLS termination (→ Caddy).

**Dev quirks on this machine:** `uvicorn --reload` hangs — run the backend without `--reload` and restart it manually after every backend edit. Test accounts: `abin@test.com / secretpass123` (admin) · `other@test.com / newotherpass77` (seller, Free plan). Dev servers: backend `http://localhost:8000` · frontend `http://localhost:5173`.
