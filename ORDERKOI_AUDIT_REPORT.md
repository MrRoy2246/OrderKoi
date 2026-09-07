# OrderKoi Audit Report

**Date:** 1 September 2026 — *historical document: every P0/P1/P2 item it recommended has since landed (Phase 7.x remediations + Phase 8a/8a+/8b/8b+); the P3 list is the post-launch roadmap in ORDERKOI_STATUS.md. A fresh pre-Docker audit (2026-09-07, no findings) is summarized in ORDERKOI_STATUS.md.*
**Scope:** Full codebase review (backend + frontend), live API security probing, database inspection, test-suite review, UX/product analysis.
**Method:** Every backend and frontend file was read. Live probes were run against the running dev server (auth edge cases, JWT tampering, IDOR, privilege escalation, injection, validation, rate limits, concurrency). The full backend suite (103 tests) and the frontend production build were executed.

---

## Remediation Progress

Fixes are applied one by one, each verified before moving to the next.

| # | Problem | Status | Verified how |
|---|---------|--------|--------------|
| 1 | Order-number race condition (C1) | ✅ **FIXED** | Unique constraint + retry loop; live stress test 4×10 concurrent creates → 40/40 unique, 0 errors; 3 regression tests; 106/106 suite passing |
| 2 | Tracking-code collision → 500 (C2) | ✅ **FIXED** (came free with #1) | Same retry helper catches tracking-code `IntegrityError` and regenerates the code |
| 3 | Default SECRET_KEY startup guard (C3) | ✅ **FIXED** | App refuses to boot in production with default/short key (verified live: `RuntimeError: REFUSING TO START`); dev/test unaffected; 2 tests added |
| 4 | `customer_phone` not editable (B1) | ✅ **FIXED** (backend) | `PATCH /orders/{id}` accepts `customer_phone` (same 6–20 validation); verified live on dev server; 1 test added. Frontend edit UI is fix #9 |
| 5 | Frontend 401 auto-redirect (F1) | ✅ **FIXED** | `request()` intercepts 401 on protected endpoints → clears token + redirects to `/login`; auth-form 401s excluded (wrong password stays a visible error); production build clean. Manual browser check suggested: garbage token + refresh → login page |
| 6 | Stats O(n) full-table scan (B4) | ✅ **FIXED** | Replaced load-all-into-Python loop with SQL `GROUP BY` aggregates (status counts + revenue in 1 query, daily counts in 1, today + pending as cheap `COUNT`s); response shape unchanged, zero frontend changes; all 25 stats tests pass; benchmark @ 50k orders: **58ms vs 2,087ms (36× faster)** |
| 7 | Timezone mixing (B3) | ✅ **FIXED** | New `app/timezone.py` single source of truth (business tz = `APP_TIMEZONE`, default Asia/Dhaka); "today"/month-quota windows and daily chart bars all computed in Dhaka time while storage stays UTC; boundary regression test proves an order at 00:30 Dhaka (= 18:30 UTC previous day) counts on the right bar and NOT on yesterday's; 110/110 suite passing; live stats verified on all ranges |
| 8 | Quota counts cancelled/spam orders (B2) | ✅ **FIXED** | `_month_order_count` excludes `cancelled` — verified live: create → month 2, cancel → month 1 (quota unit refunded); public-form submissions now have a dedicated tight per-IP limit (10/min, POST-scoped) verified live: 10 POSTs pass, 11th → 429 + `Retry-After`, GET form loads unaffected; 112/112 suite passing |
| 9 | Order-edit UI (F2) | ⛔ **SKIPPED (product decision)** | Owner decided sellers should not edit customer-entered info — customer data as submitted is preserved. Backend `PATCH` capability (fix #4) remains available but no edit UI will be built |
| 10 | CSV export | ✅ **FIXED** | `GET /orders/export` (seller-scoped, honors the list's status/search filters, 10k-row cap, UTF-8 BOM for Excel, proper CSV escaping, Dhaka-local dates) + "Export CSV" button on the Orders page downloading exactly what's on screen; verified live: correct headers/filename/rows, filter respected, 401 without token; 4 new tests, 116/116 passing |

**Fix #1 details (applied 1 Sep 2026):**
- `models.py`: `UniqueConstraint("seller_id", "order_number")` on `orders` — the DB itself refuses duplicates
- `orders.py`: new `_insert_order_with_retry()` — on `IntegrityError`, rebuilds the order with a fresh number/code, up to 5 attempts with growing jitter (503 only if it loses 5 races in a row — astronomically unlikely)
- Both creation paths (dashboard `POST /orders` and public form) now use it
- `database.py`: SQLite WAL mode + `busy_timeout=5000` in non-test environments — writers no longer block readers, commits contend far less
- `scripts/migrate.py`: creates the unique index on existing DBs (refuses + warns if old duplicates exist; dev DB was clean)
- Tests: `test_duplicate_order_number_rejected_by_db`, `test_insert_retry_resolves_number_collision`, `test_sequential_orders_get_sequential_numbers`

**Fix #3 details (applied 1 Sep 2026):**
- `main.py`: `_validate_production_config()` runs at startup — production + default/short (`<32` chars) `SECRET_KEY` → `RuntimeError`, app refuses to boot with instructions to generate a real key
- Verified live: booting with `ENVIRONMENT=production SECRET_KEY=dev-only-change-me` crashes with `REFUSING TO START`; dev server boots normally
- Tests: `test_production_refuses_default_secret_key`, `test_dev_and_test_environments_skip_the_guard`

**Fix #4 details (applied 1 Sep 2026):**
- `schemas.py`: `OrderUpdate` now includes `customer_phone` (optional, 6–20 chars, same rules as create) — the update endpoint's `exclude_unset`/`setattr` loop applies it automatically
- Verified live: `PATCH /orders/{id}` with a new phone returns 200 and persists; too-short phone rejected 422
- Test: `test_update_order_phone`

**Fix #5 details (applied 1 Sep 2026):**
- `api/client.js`: `request()` intercepts 401 on any non-auth-form endpoint → clears the stored token and hard-redirects to `/login` (full reload resets React state cleanly)
- Auth endpoints (`/auth/login`, `/auth/signup`, `/auth/forgot-password`, `/auth/reset-password`) excluded so wrong-password 401s remain visible form errors, no redirect loop
- `npm run build` passes; Vite hot-reloaded the dev server

**Fix #6 details (applied 1 Sep 2026):**
- `routes/orders.py` `stats_summary` rewritten: windowed status counts + revenue via one `GROUP BY status` query, daily counts via one `GROUP BY date(created_at)`, today/pending as cheap `COUNT` queries — the seller's order history is never loaded into Python
- Response shape identical → zero frontend changes
- Benchmarked with 50,000 synthetic orders (`scripts/bench_stats.py`): SQL aggregate 58ms vs old approach 2,087ms — 36× faster, and constant memory instead of 50k ORM objects
- All 25 stats-range tests (today/7d/30d/all/custom, past-end exclusion, single-day, validation) pass unchanged — the strongest possible regression signal that semantics are preserved

**Fix #7 details (applied 1 Sep 2026):**
- New `app/timezone.py` — the *only* place zone math happens: `business_today()`, `day_bounds_utc()` (returns naive-UTC bounds, matching exactly how SQLite stores `created_at`), `month_start_utc()`, `sqlite_shift_modifiers()` (SQL-side `date(created_at, '+6 hours')` shift so the daily chart groups by Dhaka date, not UTC date)
- `APP_TIMEZONE` setting added (`config.py`, `.env.example`) — defaults to Asia/Dhaka, any IANA name works; `tzdata` added to requirements (Windows lacks the IANA database)
- `stats_summary`: `date.today()` (server-local, wrong zone) → `business_today()`; window bounds built via `day_bounds_utc()`; daily `GROUP BY` now shifted into the business timezone
- `_month_order_count`: free-plan quota window now starts at Dhaka midnight on the 1st, consistent with the stats page
- Behavior change (intended): "today" flips at Dhaka midnight instead of 6am; the daily chart bar at 20:00 UTC lands on the next Dhaka day
- Test: `test_business_timezone_day_boundary` — backdates an order to 00:30 Dhaka (18:30 UTC the previous day) and asserts it counts in `today`, on today's bar, and NOT in yesterday's custom window. Also updated `test_stats_custom_range` to use `business_today()` instead of server-local `date.today()`
- Note for Phase 8 (PostgreSQL): the daily grouping uses SQLite `date()` modifiers; switch to `created_at AT TIME ZONE :tz` when the DB moves to Postgres

**Fix #8 details (applied 1 Sep 2026):**
- `orders.py` `_month_order_count`: added `Order.status != 'cancelled'` — cancelling a mistaken or spam order refunds its quota unit (dashboard stat `month_orders` and the free-plan check both use the same count, so the "X / 50" bar the seller sees always matches what's actually enforced)
- Together with the tighter form limit this closes the quota-DoS loop: a troll burning quota via the form can be neutralised by the seller cancelling the junk orders (each cancel restores the unit)
- `rate_limit.py`: rules are now method-scoped `(prefix, method, limit, window)`. New rule `("/public/stores/", "POST", 10, 60)` — form *submissions* (which burn quota + trigger a notification email) get 10/min per IP, while loading the form (GET) keeps a generous 30/min. Chose 10 over 5 deliberately: Bangladeshi mobile carriers use CGNAT, so many real customers can share one IP — 5/min could block legitimate buyers during a live sale
- Tests: `test_cancelled_orders_dont_burn_quota` (quota 1 → blocked → cancel → create succeeds), `test_public_submission_limit_is_tight_and_post_scoped` (rule shape + `enforce_rate_limits` with synthetic Requests: 10 POSTs pass, 11th → 429 with `Retry-After`, GETs unaffected); `test_forgot_password_has_rate_limit_rule` updated for the 4-tuple rule shape
- Verified live on the dev server (hard restart): `month_orders` 1 → create → 2 → cancel → 1; 12 rapid POSTs to `/public/stores/{slug}/orders` → ten 4xx + 429 on #11/#12 with `Retry-After: 60`; 12 GETs on the same path all passed

**Fix #10 details (applied 1 Sep 2026):**
- `routes/orders.py`: new `GET /orders/export` — returns `text/csv` as a download (`orderkoi-orders-YYYY-MM-DD.csv`, business date). Columns: order #, date (Dhaka-local), customer name/phone/address, items summary, total, status, source, tracking code, notes. Registered before `/{order_id}` so "export" isn't parsed as an id
- Shares the list endpoint's exact filter logic via `_apply_order_filters()` (extracted from `list_orders`) — the export always matches what's on screen
- Hardening: 10,000-row cap (`EXPORT_MAX_ROWS`), UTF-8 BOM so Excel detects encoding (Bengali names), `csv.writer` escaping (commas/quotes in addresses round-trip), auth required, seller-scoped
- Frontend: `downloadFile()` helper in `api/client.js` (auth header, blob download, server filename from `Content-Disposition`); "Export CSV" button on the Orders page passing the current search/status filters; disabled while loading/exporting or when there's nothing to export
- Tests: auth required (401), CSV round-trip with comma+quote address, status filter respected, second seller's export contains none of the first's orders
- Verified live: 200 + `attachment; filename="orderkoi-orders-2026-09-01.csv"` + BOM + Dhaka-local timestamps; `?status=placed` filters correctly; no token → 401. Frontend production build clean

---

## Executive Summary

**Honest assessment:** OrderKoi is a genuinely well-built MVP. The security fundamentals that most solo-built SaaS apps get wrong are done correctly here — and they were verified by live attack simulation, not just code reading:

- Cross-tenant access (IDOR) is blocked on every order endpoint (404, not even confirming existence)
- JWT forgery, `alg=none`, role-claim injection all rejected
- Mass assignment on signup is impossible (`role`/`plan` silently ignored)
- No SQL injection surface (ORM-parameterized throughout, verified live)
- No XSS surface (React auto-escaping; zero `dangerouslySetInnerHTML` in the codebase)
- Public tracking and public form responses expose deliberately minimal fields
- Rate limiting works (429 + `Retry-After` confirmed live)
- Anti-enumeration on login and password reset
- 103 backend tests passing; frontend production build clean

**Biggest problems found (all verified, not speculative):**

1. **Race condition on order numbers — confirmed live.** 8 concurrent order creations produced five orders with the same number `#3`. No unique constraint on `(seller_id, order_number)`.
2. **Quota-DoS via the public form.** Any anonymous visitor can spend a Free seller's entire 50-order monthly quota with fake submissions (rate limit is 20/min = 1,200/hour).
3. **Customer phone cannot be edited.** `OrderUpdate` is missing `customer_phone` — sellers can fix a name, address, and items, but not the single most important mistyped field.
4. **Stats endpoint loads every order into memory.** `stats_summary` does `.all()` on the seller's entire order history on every dashboard view. Fine at 100 orders; a real problem at 50k.
5. **Timezone inconsistency.** UTC timestamps are compared against local-time dates, so "today" and monthly quota windows are wrong by 6 hours for Bangladesh users.

**Biggest strengths:** Security model (tenant isolation, minimal public contracts), the subscription business loop (request → verify → approve → audit ledger), test discipline, and the product concept itself — a no-login order form + tracking link solves a real, daily pain for F-commerce sellers.

**Production readiness:** ~65%. The core is solid; the gaps are data integrity (P0 below), deployment hardening (Phase 8), and a few functional holes.
**MVP readiness (first 10 real sellers):** ~80%. Fix the P0 list and it is genuinely usable today.

---

## Critical Issues

### C1. Order-number race condition (data integrity)
- **Severity:** Critical
- **Location:** `backend/app/routes/orders.py:100-106` (create), `backend/app/routes/public.py:91-97` (public form)
- **Problem:** `order_number = max(existing) + 1` computed with a SELECT then INSERT, outside any uniqueness guarantee.
- **Why it matters:** Order numbers are what sellers and customers say to each other ("where is order #3?"). Duplicate numbers destroy that trust and break per-seller reference.
- **How to reproduce (done during this audit):** Fire 8 concurrent `POST /orders` as one seller → observed numbers `[2, 3, 3, 3, 3, 3, 4, 4]`.
- **Recommended fix:** Add `UniqueConstraint("seller_id", "order_number")` to the Order model, catch `IntegrityError` and retry (or use a per-seller counter row with `UPDATE ... RETURNING`). Same pattern protects the public form path.

### C2. Tracking-code collision → HTTP 500
- **Severity:** Critical at scale, Low today
- **Location:** `backend/app/routes/orders.py:33-35`
- **Problem:** Codes are 8 hex chars (4.3 billion space) with no collision retry. The column is unique, so a collision raises `IntegrityError` → unhandled → 500, and the customer's submission is lost.
- **Why it matters:** By the birthday bound, ~50% collision odds around 65k orders platform-wide. The failure mode is the worst one: a paying customer's form submission dying.
- **How to reproduce:** Not reproduced live (would require ~77k inserts); verified by code path.
- **Recommended fix:** Generate + insert with retry loop on `IntegrityError` (3 attempts), or lengthen the code. Five minutes of work.

### C3. Default `SECRET_KEY` ships in code
- **Severity:** Critical *if deployed as-is*
- **Location:** `backend/app/config.py:25`
- **Problem:** `secret_key: str = "dev-only-change-me"`. If the app ever starts without `.env`, every JWT is forgeable by anyone who reads the public source/pattern.
- **Why it matters:** Total account takeover, including admin.
- **How to reproduce:** Run without `.env` → tokens signed with a known key.
- **Recommended fix:** Refuse to start in production when `environment=production` and the key is the default (a 3-line startup check in `main.py` lifespan).

---

## Backend Findings

### Verified by live probing (all passing)
| Probe | Result |
|---|---|
| Unknown email + wrong password | 401, identical message for both cases |
| Empty / invalid / 5000-char credentials | 422 |
| No token / garbage token / forged token with `role=admin` / `alg=none` | 401 |
| Signup with injected `role`, `plan` | 201 — extras silently ignored |
| GET/PATCH/DELETE another seller's order | 404 (existence not revealed) |
| Seller hitting `/admin/*` | 403 |
| Negative price/quantity, qty=1000, 500-char name, empty items | 422 |
| SQLi payloads in search `q`, store slug, tracking code | No effect (parameterized) |
| XSS payloads stored, then fetched via `/track` | Stored, but response is JSON consumed by React text nodes — no execution path |
| `/track/ZZZZZZZZ`, 500-char code | 404 |
| Admin's slug via public form | 404 (admins have no store) |
| Public form flood | 429 at request #18 with `Retry-After` |

### B1. `OrderUpdate` is missing `customer_phone` — functional bug
- **Severity:** High
- **Location:** `backend/app/schemas.py:164-169`
- Sellers can edit name, address, notes, items — but not the phone number, the field customers mistype most. The UI has no phone field on the edit path either (there is no edit UI at all yet — see F2).

### B2. Free-plan quota counts cancelled and junk orders
- **Severity:** Medium (product fairness)
- **Location:** `backend/app/routes/orders.py:57-65`
- `_month_order_count` counts *all* orders including cancelled ones and unconfirmed form spam. A seller who cancels 10 mistaken orders still burned 10 units of quota. Recommendation: count only non-cancelled orders, and consider excluding deleted/spam form submissions.

### B3. Timezone mixing
- **Severity:** Medium
- **Locations:** `orders.py` `stats_summary` (`date.today()` local vs `created_at` UTC), `models.py` naive datetimes from SQLite.
- For UTC+6 (Bangladesh), "today" and the monthly quota window are wrong for orders placed between midnight and 6am local. Fix: derive "today" from `utcnow().date()` consistently (or store/compare everything in one zone). Note `_month_order_count` already uses `utcnow` — make `stats_summary` match it.

### B4. `stats_summary` is O(all orders) in Python
- **Severity:** High (scaling)
- **Location:** `backend/app/routes/orders.py:190`
- Loads the seller's entire order history into memory on every dashboard load and iterates it. At 100k orders: seconds of CPU per page view and hundreds of MB of RAM per concurrent seller. Fix: SQL aggregates (`GROUP BY date`, `COUNT FILTER`) — the same endpoint, ~30 lines.

### B5. Synchronous email inside the request
- **Severity:** Medium
- **Location:** `backend/app/email.py` (`timeout=10`), called from `public.py`, `auth.py`, `admin.py`
- A slow SMTP server adds up to 10s to order submission / login flows. Fix when scaling: a background task queue (or FastAPI `BackgroundTasks` as a zero-infra first step).

### B6. `list_upgrade_requests` / `list_subscription_events` do N+1 `db.get(Seller)` per row
- **Severity:** Low-Medium
- **Location:** `backend/app/routes/admin.py:153, 299`
- Fine at current scale; use a JOIN when seller count grows.

### B7. Unbounded price on public form
- **Severity:** Low
- `OrderItem.price` has `ge=0` but no ceiling — a customer entering `1e308` makes the total overflow to `inf`, which breaks JSON serialization → 500. Add `le=10_000_000`.

### B8. Phone "validation" is length-only
- **Severity:** Low
- `"abcdef"` passes as a phone. Fine for MVP; a simple digit/`+` regex would raise data quality for sellers who call customers.

### B9. Admin plan-change endpoint double-commits
- **Severity:** Low (cosmetic)
- `update_seller_plan` commits the plan, then commits the ledger event. A crash between them loses the ledger row. Wrap in one transaction.

### B10. Rate limiter keys on `request.client.host`
- **Severity:** High *behind a reverse proxy*
- **Location:** `backend/app/rate_limit.py:74`
- Behind nginx/a platform proxy, every visitor shares one IP → one busy customer 429s everyone (self-DoS), and attackers behind the proxy are never limited individually. Must be solved in Phase 8 (trusted `X-Forwarded-For` or proxy-level limiting). Also in-memory = per-process only — already documented in the code, correct call for now.

### B11. No token revocation / session invalidation
- **Severity:** Medium
- Password reset does not invalidate outstanding JWTs (24h lifetime). A compromised session survives a password change. Fix: add a `token_version` column, bump on password change, check in `decode`.

### B12. No email verification at signup
- **Severity:** Medium (business)
- Anyone can register any email. Since Pro activation is communicated by email, a seller with a typo'd email pays, gets approved, and never learns about it. At minimum, warn the admin panel when a Pro email has never been verified.

---

## Frontend Findings

### F1. No global 401 handling — expired sessions degrade confusingly
- **Severity:** High (UX)
- **Location:** `frontend/src/api/client.js`
- After 24h the token expires; every page then shows "Not authenticated. Provide a valid bearer token." in an error banner instead of redirecting to login. Fix: in `request()`, on 401 clear the token and redirect to `/login` (except on auth endpoints themselves).

### F2. Orders cannot be edited from the UI at all
- **Severity:** High (product)
- The backend supports `PATCH /orders/{id}` (items, name, address, notes) but there is no edit UI — sellers must delete and recreate an order to fix a typo. Combined with B1 (phone missing from the schema), the "fix a wrong entry" flow is the biggest day-to-day gap versus a spreadsheet.

### F3. Modal accessibility is partial
- **Severity:** Medium
- `OrderFormModal` has `role="dialog" aria-modal="true"` (good) but: no focus trap, no Escape-to-close, focus is not restored on close. Keyboard users can tab behind the overlay.

### F4. `window.confirm` for destructive actions
- **Severity:** Low
- Functional but jarring and unstyled; blocks the main thread. Acceptable for MVP.

### F5. Destructive-status confirm missing on "shipped/delivered" but present on cancel — inconsistent (fine), however **no undo** for accidental "Delivered" (terminal state, no transitions out). Consider allowing `delivered → cancelled` for mistake recovery, or a 5-second undo toast.

### F6. Landing page undersells the product's best feature
- **Severity:** Medium (conversion)
- The landing "How it works" says *"Type in each order"* — the exact chore OrderKoi's public form eliminates. The strongest hook (share one link, customers order themselves) is absent from the marketing page.

### F7. No onboarding after signup
- **Severity:** Medium
- A new seller lands on an empty dashboard. The single most important next action — "copy your form link and pin it on your Facebook page" — is buried in Settings. Add a getting-started card: 1) copy form link, 2) place first order, 3) share tracking link.

### F8. Chart/accessibility details
- `DailyChart` has `role="img"` with an aria-label but conveys no data to screen readers (fine — supplementary). Subscription-card meter uses `days/365` for width, so a 1-month Pro bar always looks ~8% full (cosmetic).

### F9. Verified good
- Loading states everywhere, empty states with clear next actions, human-readable error messages via `getErrorMessage` (no raw `AxiosError`/`undefined` anywhere), debounced search, URL-shareable status filter, `aria-label`s on icon-only controls, labeled inputs throughout, `type="tel"` + `inputMode` on mobile-critical fields.

---

## Security Findings (summary)

Verified secure: tenant isolation (IDOR), authn/authz, JWT verification (alg pinned, signature enforced), mass assignment, SQLi, XSS (stored-but-inert; React escaping), public contract minimality (`TrackingOut` exposes no phone/address/ids; `PublicStoreOut` is name+slug only), anti-enumeration, password reset (hashed single-use tokens, 30-min expiry, same-response enumeration defense), bcrypt, secrets in gitignored `.env`.

Outstanding, in priority order:
1. **C3** default secret key (startup guard) — Critical if misconfigured
2. **B10** proxy-aware rate limiting — High at deployment
3. **B11** no session invalidation on password change — Medium
4. **Token in localStorage** — Medium/accepted tradeoff (XSS-stealable; standard for this architecture; `httpOnly` cookie + CSRF would be the upgrade path if the threat model grows)
5. **CORS** `allow_methods=["*"]` with credentials — Low (origins are pinned; tighten methods to GET/POST/PATCH/DELETE for hygiene)
6. **CSRF** — not applicable to Bearer-token APIs (no cookies); becomes relevant only if moving to cookie auth
7. **No security headers** (CSP, HSTS, X-Frame-Options) — expected to be added at the reverse-proxy layer in Phase 8

---

## Database Findings

- **Missing constraint:** no unique index on `(seller_id, order_number)` — root cause of C1.
- **Cascade correctness:** `Order`, `UpgradeRequest`, `SubscriptionEvent`, `PasswordResetToken` all `ON DELETE CASCADE` from `Seller` — correct; deleting a seller cleans up.
- **Indexes:** good coverage on hot paths (`seller_id` on orders, `tracking_code` unique, `status`, `phone`, email unique, slug unique).
- **JSON columns** for `items`/`status_history`: pragmatic for SQLite/Postgres portability; unqueryable/aggregate-hostile — acceptable until analytics need SQL over items.
- **No real migrations:** `create_all` + ad-hoc `scripts/migrate.py`. Works for dev; Phase 8 must adopt Alembic or every future column change becomes hand-written SQL.
- **`total_price` Float:** for money. In BDT with 2-decimal prices this is fine in practice; document a decision to switch to integer paisa or `Numeric` if ever multi-currency.
- **Seller = store = tenant (1:1).** Correct for MVP; see "Integration readiness" for the future split.

---

## UI/UX Findings

- **5-second test (dashboard):** passes — headline, subscription state, pending count, and chart are above the fold.
- **"Would a seller prefer this over a spreadsheet?"** Today: roughly parity for order entry, clearly better for tracking links and the public form. It becomes strictly better once edit (F2), CSV export, and customer notifications exist — those three are what a notebook can't do.
- **Consistency:** status badge system, button hierarchy, and card patterns are used consistently across seller/admin pages.
- **Information density:** Orders table columns (8) are well-chosen; the 📝 Form badge is a nice touch.
- **Mobile:** responsive breakpoints exist at 800/720/640/480px and tables are wrapped in `.table-wrap` (horizontal scroll pattern). **Not visually verified in a browser during this audit** — recommend a manual pass at 320px and 375px before launch, especially the Orders table and the item-rows grid in the public form.
- **Copy quality:** human, on-brand ("Order koi? — ask no more"), error messages are consistently helpful.

---

## Performance Findings

| Concern | Today (10 sellers) | 1,000 sellers / 100k orders |
|---|---|---|
| `stats_summary` full-table scan per dashboard view (B4) | fine | **broken** — fix first |
| In-memory rate limiter (B10) | fine | per-process only; moves to Redis |
| Sync SMTP (B5) | fine | every order email blocks a worker |
| N+1 admin queries (B6) | fine | sluggish admin pages |
| Frontend bundle | 307 kB (91 kB gzip) | fine — code-splitting unnecessary |
| Search `ilike '%term%'` | fine | full scan; needs FTS or trigram index later |

No unnecessary duplicate API calls were found in the frontend (debounced search, `useCallback` discipline throughout).

---

## Multi-Tenant / SaaS Findings

Tenant isolation is **architecturally sound**: every seller-scoped query filters by `seller_id` from the verified token, ownership checks 404, public endpoints resolve tenants by unguessable slugs/codes, and admin is a separate role with no shop. Verified by live cross-tenant probes. This is the correct simple multi-tenant design for the current stage (shared schema + row scoping).

Weak points to watch:
- No DB-level defense-in-depth for tenant bugs (the app-level 404s are the only wall). Optional hardening: Postgres Row-Level Security later.
- All tenant scoping is manual discipline — a linter/test convention ("every Order query must join seller_id") would prevent regressions. The test suite already covers the key paths; keep adding one IDOR test per new endpoint.

---

## Automation & Integration Readiness (Facebook/Messenger, channels)

**Current architecture position:** the public order form (`/order/{slug}` → `POST /public/stores/{slug}/orders`) is already a clean, unauthenticated, rate-limited intake webhook. That's the right primitive — a Messenger bot, a website widget, or Shopify all become *producers* that call the same intake.

**What must change before channel integrations (design, not implementation):**

1. **Split Seller → Store → Channel.** Today one seller *is* one store with one slug. Model:
   ```
   Seller (account, login, billing)
     └── Store (name, slug, plan)          ← plan moves here
           ├── Order (store_id, source/channel_id)
           ├── OrderForm (store's public form, custom fields)
           └── Integration (provider="messenger", credentials, status)
   ```
2. **Integration model:** `store_id`, `provider`, `external_page_id`, `access_token` (encrypted at rest), `status`, `last_synced_at`. One seller can connect multiple Pages → multiple Integration rows under one Store.
3. **Webhook ingress:** `POST /webhooks/{provider}` — signature-verified (Meta signs with a shared secret), async processing, persistent `WebhookEvent` table with retry counters. Never do OAuth/verification work inside the webhook request.
4. **Async + retries:** a simple worker queue (even `apscheduler` + a jobs table to start). Retries with exponential backoff; dead-letter after N attempts.
5. **Isolation:** a failing Facebook integration must never affect order intake from other channels — process per-integration, catch per-integration.
6. **Don't guess Meta's API** — when the time comes, verify against current Graph API docs for Pages, webhooks, and token expiry; plan for re-auth flows.

None of this blocks MVP. The current `source` column ("dashboard" | "form") is the right seed — extend it to reference a channel.

---

## Product/Business Improvements

1. **CSV export of orders** — the #1 seller request you'll get. Low effort, high retention value.
2. **Customer notification on status change** (SMS/email to the customer) — right now the customer must *remember* the tracking link. Even a "your order shipped" email closes the loop the product promises. This is the difference between "tracker" and "OrderKoi" as a habit.
3. **Bangla UI toggle** — the target market is Bangladesh; the winning product will speak the seller's language.
4. **Revenue honesty** — revenue currently includes unconfirmed form orders with customer-copied prices. Either exclude `placed` form-sourced orders from revenue, or label it "expected revenue."
5. **Change password / change email** in Settings (currently "contact support").
6. **Admin: seller detail view + account disable** — today the admin can flip plans but not see one seller's orders or suspend an abusive account.
7. **Form customization** — a short store description/logo on the public form builds customer trust at zero complexity cost.

---

## Missing Features (MVP → future)

| Priority | Feature |
|---|---|
| Now | Order editing UI (+ phone in `OrderUpdate`) |
| Now | CSV export |
| Soon | Customer status-change notifications, 401 auto-redirect, admin seller detail |
| Later | Facebook/Messenger integration, custom form fields, multi-store, SMS gateway, Bangla UI |

---

## Recommended Database Changes

```python
# 1. C1 fix — order numbers unique per seller
class Order(Base):
    __table_args__ = (
        UniqueConstraint("seller_id", "order_number", name="uq_orders_seller_number"),
    )

# 2. B11 — session invalidation
class Seller(Base):
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

# 3. Integration-ready (future, don't build yet)
# Store(id, seller_id, name, slug, plan, ...) — plan moves from Seller
# Integration(id, store_id, provider, external_id, credentials_encrypted, status)
```

## Recommended API Changes

- `PATCH /orders/{id}` — add `customer_phone` to `OrderUpdate` (B1)
- `GET /orders/export.csv` — CSV dump with same filters as list (new)
- `POST /auth/change-password` — current + new password; bumps `token_version`
- `GET /admin/sellers/{id}` — one seller's orders + ledger (admin visibility)
- Keep everything else as-is — the API surface is appropriately small.

## Recommended Frontend Changes

1. 401 interceptor → auto-redirect to login (F1)
2. Order edit screen/modal (F2)
3. Getting-started onboarding card on the empty dashboard (F7)
4. Landing page: lead with the public form (F6)
5. Focus trap + Esc in the create-order modal (F3)
6. Manual mobile QA pass at 320–390px before launch

---

## Testing Gaps

**Backend (good: 103 tests, real coverage of auth, IDOR, workflow, plans, public form, rate limits). Missing:**
- Concurrency tests (would have caught C1 — reproduce with threads against a real SQLite file, not just the in-memory shared connection)
- Tracking-code collision / retry path
- Expired-JWT behavior (set `access_token_expire_minutes=0` in a test setting)
- `PATCH /orders/{id}` field-by-field (would have caught B1)
- Timezone boundary test (order created 00:30 local vs UTC "today")

**Frontend: zero tests.** Acceptable for this stage; when added, start with: form validation unit tests (`Signup`, `OrderForm`), route-guard tests, and one E2E happy path (Playwright): signup → copy form link → submit public order → see it in dashboard → advance status → open tracking link → see status. That single E2E test is the product's entire promise in one line.

---

## Production Readiness Checklist

- [x] Authentication secure (probed)
- [x] Authorization secure (probed)
- [x] Tenant isolation verified (probed, cross-tenant read/write/delete all 404)
- [x] Order CRUD tested (21 tests)
- [x] Public tracking secured (minimal response contract, 404 uniformity)
- [x] Input validation complete (minor gaps: price ceiling, phone format)
- [x] Rate limiting implemented (single-process caveat documented)
- [x] Error handling consistent (no stack traces leak; human messages end-to-end)
- [ ] Order-number uniqueness (C1 — must fix)
- [ ] Tracking-code retry (C2 — must fix)
- [ ] Startup secret-key guard (C3 — must fix)
- [ ] Mobile responsive — needs a visual verification pass
- [ ] Accessibility acceptable — good baseline, modal focus trap missing
- [x] Automated tests passing (103/103)
- [ ] Production configuration (PostgreSQL, Alembic, proxy-aware rate limit, security headers, SMTP, backups) — Phase 8
- [ ] Email verification / notification delivery confirmed with real SMTP

---

## Priority Roadmap

**P0 — before the first real seller (all small fixes, ~1 day together):**
1. C1 unique constraint + retry on `(seller_id, order_number)`
2. C2 tracking-code collision retry
3. C3 startup guard for default SECRET_KEY
4. B1 add `customer_phone` to `OrderUpdate`
5. F1 frontend 401 auto-redirect

**P1 — before charging money / inviting a cohort (~1 week):**
6. B4 SQL-aggregate stats
7. B3 timezone consistency pass
8. B2 quota counting excludes cancelled orders; spam mitigation for public form (e.g., per-phone rate limit, form-order flagging)
9. F2 order edit UI
10. CSV export
11. F7 onboarding card; F6 landing rewrite
12. Phase 8 deployment essentials: PostgreSQL, Alembic, proxy-aware rate limiting, security headers, backups

**P2 — first months with real users:**
13. Customer notifications on status change
14. B11 session invalidation, B12 email verification
15. Admin seller detail + account disable
16. B5 background email, B6 JOINs
17. Modal a11y, mobile QA pass, Playwright E2E

**P3 — future:**
18. Facebook/Messenger integration (per architecture above)
19. Multi-store, custom form fields, Bangla UI, SMS gateway

---

## Final Verdict

If I were responsible for launching OrderKoi, I would fix **exactly the five P0 items** — the order-number race, the tracking-code 500, the secret-key guard, the un-editable phone number, and the expired-session UX — and then let real sellers in. Everything else can be fixed with users in the building; those five are trust-destroyers if a seller hits them in week one.

The honest summary: the security architecture is better than most funded startups ship, the product loop is real, and the codebase is disciplined (tests, docs, consistent patterns). The weaknesses are classic pre-launch ones — a concurrency bug the test suite can't see, one missing schema field, and everything deployment-related still ahead in Phase 8. OrderKoi is not a demo; it's an unfinished product that is genuinely close to being a business.

---

*Audit artifacts: `backend/scripts/audit_probe.py` (re-runnable probe suite). All probe data was cleaned from the dev database after testing.*
