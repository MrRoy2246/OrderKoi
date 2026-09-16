# 🔧 Environment Reference

Every knob OrderKoi has, what it does, and what breaks if you change it.

**There is exactly one environment file: `.env` at the repository root.**
The backend, the frontend build, and Docker Compose all read that same file.

```
OrderKoi/.env          ← yours, gitignored, never committed
OrderKoi/.env.example  ← the committed template: same keys, no secrets
```

- **Local development:** copy `.env.example` → `.env` once, then edit freely.
- **Deploying:** the same file, with production values — see [DEPLOYMENT.md](./DEPLOYMENT.md).

---

## How configuration resolves

OrderKoi reads configuration in this order, first match winning:

| Priority | Source | Example |
|---|---|---|
| 1 | A real environment variable | `RATE_LIMIT_ENABLED=false uvicorn app.main:app` |
| 2 | The `KEY=value` lines in `.env` | `RATE_LIMIT_ENABLED=false` in the file |
| 3 | The built-in default in `backend/app/config.py` | `rate_limit_enabled: bool = True` |

Two rules that surprise people:

- **An empty value means "not set".** `SMTP_HOST=` does *not* disable email — it falls through
  to priority 3, and if `.env` sets a real host, the real host wins. To force behaviour off, use
  a setting that says so (`EMAIL_BACKEND=console`, `ENABLE_API_DOCS=false`), not a blank.
- **`ENVIRONMENT` is validated at boot.** It accepts `development`, `test`, `production` and
  nothing else. A typo like `Production` would silently switch off every production safety
  check, so it is rejected outright instead.

## Who reads the file

| Consumer | How |
|---|---|
| Backend (`uvicorn`, `alembic`, `pytest`, `scripts/`) | `backend/app/config.py` resolves the path from its own location, so it works from any working directory |
| Frontend (`npm run dev`, `npm run build`) | `frontend/vite.config.js` sets `envDir` to the repo root; only `VITE_`-prefixed keys reach browser code |
| Docker Compose | `docker-compose.yml` substitutes `${VAR}`; the images themselves ship no `.env` |

## Changing a value — restart or rebuild?

| Variable | How to apply it |
|---|---|
| `VITE_API_URL` | **Rebuild the frontend.** It is compiled into the JS bundle at build time. |
| Everything else | **Restart the backend.** Most are read once at process start. |
| Business config (`BKASH_*`, `SUPPORT_EMAIL`, `FREE_PLAN_ORDERS`, `PRO_PRICE_*`) | Restart the backend. These are served live at `GET /public/stores/pricing`, so the frontend follows with **no rebuild at all**. |

With Docker: `docker compose restart backend` (or `up -d --build frontend` for `VITE_API_URL`).

---

## Database

The app talks to PostgreSQL. Two independent consumers exist, which is why there are two sets of names.

| Variable | Default | What it does |
|---|---|---|
| `PG_HOST` | `localhost` | Host the **app on your machine** connects to |
| `PG_PORT` | `5432` | Port. Local dev installs often use **5433** — PG 15 may already own 5432 |
| `PG_DATABASE` | `orderkoi` | Database name |
| `PG_USER` | `orderkoi` | Role |
| `PG_PASSWORD` | *(none)* | **Required.** With no `DATABASE_URL` and no password, the app refuses to boot |
| `DATABASE_URL` | *(empty)* | One full connection string. If set, it **overrides** all five `PG_*` values |
| `POSTGRES_USER` | `orderkoi` | Role the **database container** creates on first boot |
| `POSTGRES_PASSWORD` | *(none)* | Password for that container role |
| `POSTGRES_DB` | `orderkoi` | Database the container creates |

**Changing it affects:** every query and every migration. `alembic upgrade head` targets whatever
these point at, so a wrong host means you migrate the wrong database.

> Inside Docker Compose the app is always handed `PG_HOST=db` and `PG_PORT=5432`; only the user,
> password and database name need to match between the `PG_*` and `POSTGRES_*` sets.

---

## Security

| Variable | Default | What it does |
|---|---|---|
| `SECRET_KEY` | `dev-only-change-me` | Signs every JWT. **Rotating it signs out every user on every device.** In production the app refuses to boot with the default or with anything under 32 characters |

Generate one:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## App and URLs

| Variable | Default | What it does |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` \| `test` \| `production`. Validated at boot. `production` enables the safety checks below and turns `/docs` off |
| `APP_TIMEZONE` | `Asia/Dhaka` | The business day boundary. A seller's "today" and "this month" flip at local midnight, not at 06:00 UTC. Any IANA name works |
| `FRONTEND_URL` | `http://localhost:5173` | Where the browser app is served. **Password-reset and verification links point here.** In production it may not be `localhost` — the app refuses to boot, because every emailed link would be dead on arrival |
| `VITE_API_URL` | *(none)* | The API's public origin, **compiled into the bundle at build time**. A production build refuses to run without it. Docker Compose passes it as a build arg |
| `CORS_ORIGINS` | `["http://localhost:5173","http://127.0.0.1:5173"]` | JSON array of browser origins allowed to call the API. `*` is **rejected at boot** — the API sends credentials, so a wildcard would let any website call it as a signed-in user. An empty list is rejected in production |

**Changing it affects:** `FRONTEND_URL` changes where emailed links go. `VITE_API_URL` needs a
frontend rebuild. `CORS_ORIGINS` changes which sites' browsers may call the API — too narrow and
the app "cannot reach the server" while the server is perfectly healthy.

---

## Business configuration

All of this is served live at `GET /public/stores/pricing` and read per-request, so an edit plus a
backend restart is enough — **no frontend rebuild, no redeploy.**

| Variable | Default | What it does |
|---|---|---|
| `BKASH_NUMBER` | `01736060259` | Where sellers send their bKash payment for Pro. Shown in Settings and in upgrade emails. **Required in production** — otherwise a live site advertises the developer's personal number |
| `BKASH_TYPE` | `Personal` | Label shown next to the number: `Personal` or `Agent` |
| `SUPPORT_EMAIL` | `abinroy510@gmail.com` | Public contact address on the legal pages. **Required in production**, same reason |
| `FREE_PLAN_ORDERS` | `15` | Free plan allowance — a **one-time lifetime** order count, not monthly. A seller at the cap cannot take new orders until they upgrade |
| `PRO_PRICE_1M` | `350` | Pro price in taka for 1 month |
| `PRO_PRICE_6M` | `1750` | Pro price in taka for 6 months |
| `PRO_PRICE_12M` | `2900` | Pro price in taka for 12 months |

**Changing it affects:** prices shown on the landing page, in Settings, and on the upgrade queue —
and the revenue figures in the admin panel, which re-price past subscription events at the
*current* rates. Changing a price therefore shifts historical revenue totals too. That is
deliberate and documented; it is not a bug.

Run an offer on one duration by changing only that one line.

---

## Email (SMTP)

| Variable | Default | What it does |
|---|---|---|
| `EMAIL_BACKEND` | `auto` | `auto` — send via SMTP if `SMTP_HOST` is set, otherwise log to the console. `console` — always log, never touch the network. `smtp` — always send, and fail loudly if `SMTP_HOST` is empty |
| `SMTP_HOST` | *(empty)* | Mail server. Gmail: `smtp.gmail.com`. **Required in production** — login needs a verified email, so with no mail path nobody could ever sign in |
| `SMTP_PORT` | `587` | 587 = STARTTLS |
| `SMTP_USERNAME` | *(empty)* | Usually the full email address |
| `SMTP_PASSWORD` | *(empty)* | For Gmail this is a 16-character **App Password**, not the account password: <https://myaccount.google.com/apppasswords> |
| `EMAIL_FROM` | `OrderKoi <no-reply@orderkoi.local>` | The `From:` header. For Gmail it must be the same address as `SMTP_USERNAME` |

**Changing it affects:** signup verification, password reset, order-status notifications, and
upgrade-request emails. If mail is misconfigured in production, **nobody can sign in** — which is
why the app refuses to boot rather than start up silently broken.

> `console` exists as its own value because leaving `SMTP_HOST` empty cannot turn sending off once
> the file sets a real host — an empty value counts as "not set", so the real host wins. That is
> exactly how the test suite once sent live Gmail on every fixture signup. The suite now forces
> `EMAIL_BACKEND=console` in `backend/tests/conftest.py`.

**Planned:** the personal Gmail sender is capped at roughly 500 messages/day. Move to a
transactional service (Brevo, Resend) before real traffic — it is an `.env` edit only.

---

## Operational tunables

Every one of these has a default that is already correct for a small deployment. They are written
out in `.env` so the knob you need is there to turn — deleting a line changes nothing.

### Logging

| Variable | Default | What it does |
|---|---|---|
| `LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. Every log line carries `filename:lineno`, so `DEBUG` is usable when diagnosing |

### Session and token lifetimes (minutes)

| Variable | Default | What it does |
|---|---|---|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` (24 h) | How long a login lasts before the user must sign in again |
| `RESET_TOKEN_EXPIRE_MINUTES` | `30` | How long a password-reset link stays valid |
| `EMAIL_VERIFICATION_EXPIRE_MINUTES` | `1440` (24 h) | How long a signup verification link stays valid |

### Rate limiting — per client IP

A sliding window per IP: at most `MAX` requests per `WINDOW` seconds. Raising the window without
raising the max makes it stricter, not looser.

| Variable | Default | Applies to |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | The whole limiter |
| `RATE_LIMIT_LOGIN_MAX` / `_WINDOW` | `10` / `60` | `POST /auth/login` |
| `RATE_LIMIT_SIGNUP_MAX` / `_WINDOW` | `5` / `60` | `POST /auth/signup` |
| `RATE_LIMIT_FORGOT_PASSWORD_MAX` / `_WINDOW` | `5` / `60` | Password-reset requests |
| `RATE_LIMIT_RESEND_VERIFICATION_MAX` / `_WINDOW` | `5` / `60` | Resending the verify link |
| `RATE_LIMIT_TRACK_MAX` / `_WINDOW` | `60` / `60` | Public tracking lookups |
| `RATE_LIMIT_PUBLIC_FORM_MAX` / `_WINDOW` | `10` / `60` | The public order form (unauthenticated orders) |
| `RATE_LIMIT_PUBLIC_MAX` / `_WINDOW` | `30` / `60` | Other public endpoints |

**Raise these where many real users share one IP** — Bangladeshi mobile carriers put large numbers
of subscribers behind a single CGNAT address, and a default-sized bucket will lock out a whole
carrier's customers. `RATE_LIMIT_ENABLED=false` is for load testing and full Playwright runs only.

> Needs `--proxy-headers --forwarded-allow-ips` (already set in the Docker image). Behind a proxy
> without it, every request appears to come from the proxy's IP and all users share one bucket.

### Per-account login lockout

Separate from the IP limiter above: this one follows the **account**, so an attacker rotating
through proxies is still stopped.

| Variable | Default | What it does |
|---|---|---|
| `LOGIN_MAX_FAILURES` | `5` | Wrong passwords before the account locks |
| `LOGIN_FAILURE_WINDOW_MINUTES` | `15` | Window those failures are counted over |
| `LOGIN_LOCKOUT_MINUTES` | `15` | How long the lock lasts |

A locked-out user gets a different message from a rate-limited one ("Too many failed attempts"),
which is how you tell the two apart when diagnosing.

### Database connection pool

| Variable | Default | What it does |
|---|---|---|
| `DB_POOL_SIZE` | `5` | Persistent connections kept open |
| `DB_MAX_OVERFLOW` | `10` | Extra connections allowed under burst |
| `DB_POOL_RECYCLE_SECONDS` | `1800` | Recycle a connection after this long, against NAT/firewall idle drops |
| `DB_POOL_TIMEOUT_SECONDS` | `30` | How long a request waits for a free connection before erroring |

Size these to cover the synchronous route threadpool (40) so concurrent requests never queue on a
checkout.

### Email delivery

| Variable | Default | What it does |
|---|---|---|
| `EMAIL_WORKERS` | `4` | Threads used to send mail |
| `EMAIL_SEND_ATTEMPTS` | `3` | Attempts per message before giving up |
| `EMAIL_RETRY_DELAYS_SECONDS` | `[2,10]` | JSON array — backoff between attempts |
| `SMTP_TIMEOUT_SECONDS` | `10` | Socket timeout |

### Request and response limits

| Variable | Default | What it does |
|---|---|---|
| `EXPORT_MAX_ROWS` | `10000` | Row cap on a seller's own CSV export |
| `ADMIN_EXPORT_MAX_ROWS` | `20000` | Row cap on the admin's per-seller export |
| `MAX_PAGE_SIZE` | `100` | Largest `limit` any seller-facing list accepts. Asking for more is a **422**, not a bigger page |
| `MAX_ADMIN_PAGE_SIZE` | `200` | The same ceiling for admin list endpoints |
| `MAX_ITEM_PRICE` | `10000000` | Ceiling on one item's unit price |
| `MAX_ORDER_TOTAL` | `9999999999.99` | Ceiling on a computed order total |

`MAX_ITEM_PRICE` and `MAX_ORDER_TOTAL` are not just politeness: without them a huge value
overflows the `Numeric(12,2)` money column and produces a 500 on an **unauthenticated** endpoint.

> `MAX_PAGE_SIZE` / `MAX_ADMIN_PAGE_SIZE` are read when the API starts, so a change needs a
> backend restart. The frontend's page-size options are built from what the API accepts.

---

## Automatic-by-default settings

These are **deliberately left unset** in `.env`. Each has a meaningful "choose for me" behaviour,
and any value written down — even one that looks harmless — pins it.

| Variable | Unset means | Set it only to |
|---|---|---|
| `ENABLE_API_DOCS` | On in development and test, **off in production**. An open `/docs` advertises every admin route to anyone who asks | `true` if you really want docs in production |
| `EMAIL_CONSOLE_LOGS_BODY` | On in development, off everywhere else. Never in production — bodies carry password-reset and verification links | `true` to log full bodies on a console backend |
| `APP_NAME` | `OrderKoi API` | Cosmetic |
| `API_VERSION` | `1.0.0` | Cosmetic |
| `JWT_ALGORITHM` | `HS256` | **Don't.** The verifier pins it; changing it invalidates every issued token and locks out every user |

---

## Docker Compose only

These are read by `docker-compose.yml`. The app running on your host ignores them.

### Encrypted backups (the `backup` service)

A containerised `pg_dump` runs on the *database's own image*, so the client version can never fall
behind the server. Dumps land in `./backend/backups` on the host, are verified before being kept,
and are pruned to the newest `BACKUP_KEEP`.

| Variable | Default | What it does |
|---|---|---|
| `BACKUP_PASSPHRASE` | *(none)* | **Required while encryption is on** — the backup service refuses to start without it. There is no recovery path for a lost passphrase |
| `BACKUP_ENCRYPTION` | `on` | AES-256 at the point the dump is written. A dump holds password hashes and every customer's name, phone, and address |
| `BACKUP_PBKDF2_ITER` | `200000` | Key-derivation rounds. **A restore must use the same value** — it is not stored in the dump |
| `BACKUP_INTERVAL_HOURS` | `24` | How often to dump |
| `BACKUP_KEEP` | `14` | How many dumps to keep on disk |

Keep the passphrase in a password manager and in whatever bootstraps a new server — **not** on the
machine it protects, and not in git. Offsite copying is manual on purpose: a container cannot know
where "offsite" is, and a backup that only exists on the machine it protects is not a backup. See
[DEPLOYMENT.md](./DEPLOYMENT.md).

### Caddy edge proxy (`--profile edge` only)

| Variable | Default | What it does |
|---|---|---|
| `SITE_DOMAIN` | *(none)* | Apex domain for the frontend; Caddy gets a Let's Encrypt certificate for it |
| `API_DOMAIN` | *(none)* | Domain for the API |
| `ACME_EMAIL` | *(none)* | Contact address for Let's Encrypt expiry notices |
| `HSTS_MAX_AGE` | `31536000` | HSTS max-age in seconds (1 year). `includeSubDomains` is set in the `Caddyfile` — every subdomain of the apex must then serve HTTPS |

> Compose substitutes the whole file *before* it filters by profile, so these three must still be
> **set** even for a deployment that never runs Caddy. An unset one aborts `docker compose up` with
> "required variable is missing" for a service you are not using.

### Proxy trust (advanced)

| Variable | Default | What it does |
|---|---|---|
| `FORWARDED_ALLOW_IPS` | `*` (in compose) | Which peers' `X-Forwarded-For` the API believes. `*` is safe *only* because Caddy sets that header and the API port is never published publicly. Pin it to the compose network CIDR (e.g. `172.28.0.0/24`) before putting a CDN in front or exposing port 8000 |

---

## Production checklist

These are enforced — the app refuses to boot rather than run misconfigured:

- [ ] Fresh `SECRET_KEY` (32+ chars, not the default)
- [ ] `ENVIRONMENT=production`
- [ ] `FRONTEND_URL` set to the real domain, **not** localhost
- [ ] `CORS_ORIGINS` lists that domain, non-empty, **no `*`**
- [ ] `SMTP_HOST` set and working — otherwise nobody can sign in
- [ ] `BKASH_NUMBER` and `SUPPORT_EMAIL` are the real business values
- [ ] `POSTGRES_PASSWORD` strong and different from any development value

See also: [DEPLOYMENT.md](./DEPLOYMENT.md) · [BACKEND_GUIDE.md](./BACKEND_GUIDE.md) · [FRONTEND_GUIDE.md](./FRONTEND_GUIDE.md)
