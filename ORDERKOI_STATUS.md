# OrderKoi — Project Status

_Last updated: 2026-09-01_

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
| **Phase 7 — Testing & Hardening**                 | Test suite (116/116 passing), rate limiting, security review                                                                                                                                                                                                                                                                        |
| **Phase 7.5 — Admin Panel & Plans**               | Admin overview, sellers & plans management, upgrade requests                                                                                                                                                                                                                                                                        |
| **Phase 7.6 — Admin as pure platform account**    | Admin has no shop; separate admin panel                                                                                                                                                                                                                                                                                             |
| **Phase 7.7 — Forgot / Reset Password**           | Email reset links, 30-min tokens                                                                                                                                                                                                                                                                                                    |
| **Phase 7.8 — Public Order Form**                 | `/order/:slug` — customers submit orders without login                                                                                                                                                                                                                                                                              |
| **Phase 7.9 — Dashboard polish**                  | Date ranges (today/7d/30d/all/custom), clickable stat cards                                                                                                                                                                                                                                                                         |
| **Phase 7.10 — Pro durations & upgrade workflow** | 1/6/12-month Pro options, bKash/Nagad payment instructions, request → approve/reject flow, subscription ledger                                                                                                                                                                                                                      |
| **Audit remediation**                             | 9/10 issues fixed, 1 skipped by decision (seller order-editing); timezone-correct stats (Asia/Dhaka), CSV export, POST-scoped rate limits                                                                                                                                                                                           |
| **Frontend redesign (A–F)**                       | New design system "Koi vermilion on warm paper" — tokens, Manrope font, SVG icon set, koi logo/favicon, shared badge/timeline/skeleton/empty-state components, sidebar + mobile drawer, mobile order cards, redesigned all 14 pages, landing page with product mock, full CSS rewrite, a11y + reduced-motion, responsive 320px→wide |

**Current state:** fully working product on dev servers. Backend tests 116/116. Frontend build + lint clean.

---

## 🔴 TODO — Launch blockers (Phase 8)

- [ ] **Deployment** — PostgreSQL, VPS or managed hosting, domain + HTTPS, gunicorn workers, hardened `.env` (fresh `SECRET_KEY`, real `CORS_ORIGINS`)
- [ ] **Configure real email (SMTP)** — password resets and Pro approval emails currently only print to the server log; get SMTP credentials (Resend / Brevo / Gmail app-password) into `.env`
- [ ] **Legal & trust pages** — Privacy Policy, Terms of Service, contact email (landing footer + tracking pages)
- [ ] **Real bKash/Nagad numbers** in `frontend/src/components/PlanSection.jsx` (`PAYMENT_INSTRUCTIONS` + `PRO_OPTIONS`) — _owner task_

## 🟠 TODO — Week one after deploy

- [ ] 404 page (unknown URLs currently redirect to landing)
- [ ] Database backups (nightly) + uptime monitoring + error tracking (Sentry free tier)
- [ ] Favicon fallbacks (`favicon.ico`, `apple-touch-icon.png`) + delete unused `public/icons.svg`
- [ ] `og:image` social share card + `robots.txt`
- [ ] Frontend smoke test (Playwright: login → create order → track)
- [ ] Session security revisit (token expiry / server-side invalidation)

## 🟡 TODO — Product roadmap (post-launch)

ok

- [ ] Customer notifications on status change (email/SMS) — the core "order koi?" killer feature
- [ ] Tracking page auto-refresh / polling
- [ ] Email verification at signup
- [ ] Admin seller drill-down (view one seller's orders)
- [ ] Help / FAQ page + WhatsApp support link
- [ ] Bengali localization
- [ ] Online payment gateway (bKash API instead of manual TrxID verification)
- [ ] Seller account/data deletion (data protection)

---

**Test accounts (dev):** `abin@test.com / secretpass123` (admin) · `other@test.com / newotherpass77` (seller, Free plan)
**Dev servers:** backend `http://localhost:8000` · frontend `http://localhost:5173`
