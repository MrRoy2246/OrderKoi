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
- 💳 Free plan (15 orders, one time) → Pro (unlimited; 1/6/12 months, bKash/Nagad)
- 🔐 Secure JWT authentication

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · SQLAlchemy · SQLite (dev) / PostgreSQL (prod) |
| Frontend | React (Vite) · JavaScript |
| Auth | JWT (access tokens) |
| API Docs | Auto-generated Swagger UI at `/docs` |

## Documentation

- 📋 **[PHASES.md](./PHASES.md)** — the full build plan with self-testing checklists
- 🐍 **[docs/BACKEND_GUIDE.md](./docs/BACKEND_GUIDE.md)** — backend setup, run & test guide
- ⚛️ **[docs/FRONTEND_GUIDE.md](./docs/FRONTEND_GUIDE.md)** — frontend setup, run & test guide

## Status

- [x] Phase 0 — Setup & Scaffold
- [x] Phase 1 — Database & Seller Authentication (backend)
- [x] Phase 2 — Orders Core API (backend)
- [x] Phase 3 — Frontend Auth & App Shell
- [x] Phase 4 — Seller Dashboard: Order Management
- [x] Phase 5 — Public Tracking Page
- [x] Phase 6 — Analytics & Store Settings
- [x] Phase 7 — Testing & Hardening (147/147 tests)
- [x] Phase 7.5–7.7 — Admin Panel, Plans, Password Reset
- [x] Phase 7.8 — Public Order Form (customers order without any login)
- [x] Phase 7.9–7.10 — Dashboard date ranges, Pro durations & upgrade requests
- [x] Phase 7.11–7.12 — Subscription card, custom reports & admin subscription history
- [x] Phase 7.13 — Free-plan allowance (15 one-time), limit experience, seller history (2026-09-05)
- [ ] Phase 8 — Production Ready & Deployment (next: SMTP → PostgreSQL → Docker)
