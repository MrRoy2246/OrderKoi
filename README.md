# OrderKoi 🟢

> **"Order koi?"** — the question every F-commerce seller hears 50 times a day. Not anymore.

OrderKoi is an order-tracking platform for small online sellers (F-commerce / Facebook sellers) in Bangladesh and worldwide. Sellers manage orders in a simple dashboard; customers check their order status themselves via a tracking link — no more "where's my order?" messages.

## The Problem We Solve

- Facebook sellers receive orders in Messenger and track them in notebooks/Excel
- Customers constantly message asking for order status
- Sellers waste hours every day repeating the same answer
- Orders get lost, forgotten, or mixed up

## The Solution

- 🏪 Seller dashboard: create & manage orders, update status
- 🔗 Public tracking page: customer checks status via a link + tracking code
- 📝 Public order form: customers submit orders themselves — no login, no Messenger retyping
- 📊 Analytics: order counts, status breakdown, revenue (all scoped by date range)
- 💳 Free plan (15 orders, one time) → Pro (unlimited; 1/6/12 months, bKash) — **all prices and business values served live from the backend env, changeable without a deploy**
- 🔐 Secure JWT authentication

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 17 (psycopg3) |
| Frontend | React (Vite) · JavaScript |
| Auth | JWT (access tokens) |
| API Docs | Auto-generated Swagger UI at `/docs` |

## Documentation

- 📋 **[PHASES.md](./PHASES.md)** — the full build plan with self-testing checklists
- 📊 **[ORDERKOI_STATUS.md](./ORDERKOI_STATUS.md)** — current state, launch order, open items
- 🐍 **[docs/BACKEND_GUIDE.md](./docs/BACKEND_GUIDE.md)** — backend setup, run & test guide
- ⚛️ **[docs/FRONTEND_GUIDE.md](./docs/FRONTEND_GUIDE.md)** — frontend setup, run & test guide
- 🚢 **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)** — run with Docker, create the admin account, deploy to a server

## Status

- [x] Phase 0 — Setup & Scaffold
- [x] Phase 1 — Database & Seller Authentication (backend)
- [x] Phase 2 — Orders Core API (backend)
- [x] Phase 3 — Frontend Auth & App Shell
- [x] Phase 4 — Seller Dashboard: Order Management
- [x] Phase 5 — Public Tracking Page
- [x] Phase 6 — Analytics & Store Settings
- [x] Phase 7 — Testing & Hardening
- [x] Phase 7.5–7.7 — Admin Panel, Plans, Password Reset
- [x] Phase 7.8 — Public Order Form (customers order without any login)
- [x] Phase 7.9–7.10 — Dashboard date ranges, Pro durations & upgrade requests
- [x] Phase 7.11–7.12 — Subscription card, custom reports & admin subscription history
- [x] Phase 7.13 — Free-plan allowance (15 one-time), limit experience, seller history (2026-09-05)
- [x] Phase 8a — Real SMTP email: verification, order & status emails, background send with retry (2026-09-06)
- [x] Phase 8a+ — Pre-deploy hardening: JWT invalidation on reset, login lockout, security headers, /ready, honeypot, 404, Privacy/Terms, Playwright E2E, daily DB backups, favicon/og-image/robots.txt (2026-09-06)
- [x] Phase 8b — PostgreSQL shift: dedicated orderkoi DB + env-driven credentials, Alembic migrations, dev data migrated, pg_dump backups, SQLite fully removed incl. tests-on-PG (2026-09-07)
- [x] Phase 8b+ — create_admin bootstrap script, pre-deploy audit, gunicorn; Pro repriced ৳350/৳1,750/৳2,900; all business values env-driven via public config endpoint (no rebuild to change an offer); full docstring sweep (2026-09-07)
- [x] Phase 8c — Docker packaging: full stack compose (Postgres 17 + backend + frontend + optional Caddy auto-TLS), verified end-to-end locally (2026-09-12); deploy to a VPS + domain remains
- [ ] Phase 8d — Launch guardrails: real email provider, Sentry, uptime monitoring, domain
- [ ] Phase 8e — Fast-follow hardening: admin MFA, Redis limiter, load test (admin pagination + SQL aggregation + indexes done 2026-09-12)

**Test health:** backend 193/193 · Playwright E2E 7/7 · build + lint clean.

## Run with Docker

```bash
cp .env.example .env      # fill in the values (see docs/DEPLOYMENT.md)
docker compose up -d      # http://localhost:8090 (frontend) + http://localhost:8000 (API)
docker compose exec backend python -m scripts.create_admin admin@example.com   # first admin — sellers sign up via the website
```

Full guide — fresh databases, the admin account, VPS deployment, backups, restore: **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)**.

## Local development (without Docker)

- Backend: `cd backend && venv/Scripts/python -m uvicorn app.main:app` → http://localhost:8000 (uses local PostgreSQL 17 on port 5433 — see `docs/BACKEND_GUIDE.md`)
- Frontend: `cd frontend && npm run dev` → http://localhost:5173
