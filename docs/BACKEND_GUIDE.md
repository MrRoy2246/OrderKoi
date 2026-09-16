# 🐍 Backend Guide — FastAPI

The OrderKoi backend. Python 3.11 + FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL 17.

## Requirements

- Python 3.11 installed (`python --version` should show 3.11.x)
- If not installed: download from https://www.python.org/downloads/ (check "Add to PATH" during install)

## First-time setup

Open a terminal in `OrderKoi/backend/` and run:

```bash
# 1. Create virtual environment
python -m venv venv

# 2. Activate it (Windows PowerShell)
venv\Scripts\activate
#    ...or Windows Git Bash:
source venv/Scripts/activate
#    ...or Windows CMD:
venv\Scripts\activate.bat

# 3. Install dependencies
pip install -r requirements.txt
```

> ⚠️ You must activate the venv **every time** you open a new terminal. You'll know it's active when you see `(venv)` at the start of your prompt.

## Running the server

```bash
uvicorn app.main:app            # dev
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 1   # production (gunicorn is in requirements.txt)
```

- API base URL: `http://localhost:8000`
- **Swagger UI (interactive docs):** `http://localhost:8000/docs` ← your main testing tool
- ReDoc docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health` (liveness) · `http://localhost:8000/ready` (checks the DB too — returns 503 if the DB is down)
- Public business config: `http://localhost:8000/public/stores/pricing` (env-driven prices/allowance/bKash/support — see the Business config section)

> ⚠️ **On this machine, do NOT use `--reload` — it hangs.** Run the plain command above and restart the server manually after every backend edit.

## Running with Docker (production shape)

```bash
docker compose up -d          # from the repo root: db + backend + frontend
```

The backend container runs `alembic upgrade head` on boot, then gunicorn with **one** uvicorn worker (the rate limiter and login throttle are in-memory — see `docker-compose.yml`). Full guide incl. the admin account and VPS deploy: **[DEPLOYMENT.md](./DEPLOYMENT.md)**.

### The admin account

Sellers register through the website; the admin exists **only** via the bootstrap script — there is deliberately no way to create or promote an admin through the API or UI:

```bash
# locally (dev DB):          in Docker:
python -m scripts.create_admin admin@example.com
docker compose exec backend python -m scripts.create_admin admin@example.com
```

Idempotent; prints a random password once; the account is created email-verified. With a password argument it creates *or resets* that account. Full reference: **[DEPLOYMENT.md](./DEPLOYMENT.md)**.

## Using Swagger UI to test endpoints

1. Open `http://localhost:8000/docs`
2. Click an endpoint → "Try it out" → fill parameters → "Execute"
3. For protected endpoints: click the **Authorize 🔒** button, paste your JWT token (from login/signup), then execute

## Running tests

```bash
pytest
```

- All tests green = ✅ safe to continue
- Run a single file: `pytest tests/test_orders.py`
- See verbose output: `pytest -v`

## Database

- Dev: **PostgreSQL 17** (local install, port **5433** — PG 15 owns 5432). Dedicated `orderkoi` role + database; the app never uses the postgres superuser.
- All connection settings live in the **repo-root `.env`** (`PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`) — change the user, password, host, or port there and the app follows, no code change. A full `DATABASE_URL` overrides the parts; one of the two must be set (the app refuses to boot without a database).
- Schema is managed by **Alembic**: set up or update a database with `alembic upgrade head` (from `backend/`). After changing a model in `app/models.py`, generate a migration with `alembic revision --autogenerate -m "..."`, review it, then `upgrade head`.
- Tests run on the same engine as production, in a dedicated **`orderkoi_test`** database (selected via `PG_DATABASE` env override in `tests/conftest.py`; auto-created on first run — needs `CREATEDB` on the role, granted once: `ALTER ROLE orderkoi CREATEDB;`). Dev data is never touched; the schema is created/dropped per session.

## Business config (prices, allowance, bKash, contact) — all env-driven

Every public business value lives in the **repo-root `.env`** and is served live by **`GET /public/stores/pricing`** (no auth):

| Env var | Default | Controls |
|---|---|---|
| `PRO_PRICE_1M / PRO_PRICE_6M / PRO_PRICE_12M` | 350 / 1750 / 2900 | Pro plan prices (frontend plan cards, upgrade request amount, admin revenue math) |
| `FREE_PLAN_ORDERS` | 15 | One-time free-plan allowance |
| `BKASH_NUMBER` / `BKASH_TYPE` | 01736060259 / Personal | Payment instructions shown to sellers |
| `SUPPORT_EMAIL` | abinroy510@gmail.com | Contact email on the Terms & Privacy pages |

**To change any offer: edit `.env`, restart the backend.** No rebuild, no frontend deploy — the frontend fetches this endpoint at runtime (with safe fallbacks if the backend is unreachable or stale). The endpoint reads settings per-request, so env changes apply on restart. Prices feed `app/schemas.py:pro_prices()` (used by orders/auth/admin routes); admin revenue figures re-price ledger events at the *current* rates — a price change shifts those totals (accepted, documented behavior).

## Backups

```bash
python -m scripts.backup_db        # from backend/ — also run by Task Scheduler daily at 3:07 AM
```

- `pg_dump` custom format → `backend/backups/orderkoi-YYYYMMDD-HHMMSS.dump` (restore with `pg_restore`). Credentials come from the repo-root `.env`; `pg_dump` is located via `PG_BINDIR`, PATH, or the standard install dir.
- Keeps the newest 14 backups, deletes older ones automatically
- The Windows scheduled task is **"OrderKoi DB backup"** — view it in Task Scheduler or `schtasks /query /tn "OrderKoi DB backup"`
- This script's dumps are **plaintext**, and it only ever touches `*.dump`. The Docker `backup` service writes **encrypted** `*.dump.enc` files into the same directory and the two never prune each other — see section 7 of `docs/DEPLOYMENT.md` for the container and the passphrase it needs.

## Email

- All SMTP settings live in the repo-root `.env` (never commit it). Empty `SMTP_HOST` = emails print to the console instead of sending. Force that with `EMAIL_BACKEND=console` — an empty `SMTP_HOST` cannot express it once `.env` sets a real host.
- Sends happen in **background threads** — the API never waits for Gmail, and a failed send retries 3 times (2s/10s backoff) before logging `EMAIL DELIVERY FAILED`. A total failure never breaks the request.
- Email templates (welcome/verification, password reset, order received, status change) are in `app/emails.py`.

## Built-in protections (know they exist)

- **Per-IP rate limits** on login/signup/forgot-password/tracking/public form (`app/rate_limit.py`)
- **Per-account login lockout**: 5 wrong passwords in 15 min → account locked 15 min, even if the attacker switches IPs (`app/login_throttle.py`)
- **Password reset invalidates old JWTs** — tokens minted before a reset stop working (`sellers.token_invalid_before`)
- **Honeypot** on the public order form — bots that fill the hidden `website` field get a fake success, nothing is stored
- **Security headers** on every response (nosniff, frame-deny, referrer, permissions)


## Project layout

```
backend/
├── app/
│   ├── main.py        # FastAPI app, routes registration, CORS, security headers, /health + /ready
│   ├── config.py      # Settings from the repo-root .env (resolved by absolute path)
│   ├── csv_export.py  # CSV rendering shared by the seller and admin exports (BOM, columns, dates)
│   ├── database.py    # DB engine & session (PostgreSQL pool, UTC-pinned sessions)
│   ├── email.py       # SMTP send — background threads + retry, console fallback
│   ├── emails.py      # Email templates (welcome/verify, reset, order received, status change)
│   ├── login_throttle.py  # Per-account lockout after repeated failed logins
│   ├── rate_limit.py  # Per-IP sliding-window rate limits
│   ├── models.py      # SQLAlchemy models (Seller, Order, UpgradeRequest, SubscriptionEvent, tokens)
│   ├── schemas.py     # Pydantic request/response schemas
│   ├── security.py    # Password hashing, JWT create/verify (incl. iat + token_invalid_before)
│   ├── deps.py        # Shared dependencies — get_db, get_current_seller (JWT + revocation check)
│   ├── utils.py       # Timezone helpers (Asia/Dhaka business time)
│   └── routes/
│       ├── auth.py    # /auth/* — signup, login, me, email verify/resend, password reset, subscription-history, cancel-subscription
│       ├── orders.py  # /orders CRUD + status changes + /orders/stats/summary (free-allowance gate)
│       ├── tracking.py# /track/{code} — public
│       ├── admin.py   # /admin/* — stats, sellers, upgrade requests, subscription events
│       └── public.py  # /public/stores/{slug} + /public/stores/pricing (env-driven business config; honeypot)
├── scripts/
│   ├── create_admin.py # Bootstrap/promote the platform admin (idempotent) - run after alembic upgrade head on a fresh DB
│   ├── backup_db.py   # Timestamped pg_dump backup (keep 14) - runs daily via Task Scheduler
│   └── audit_probe.py # Manual audit helpers
├── backups/           # Backup output (gitignored)
├── tests/             # pytest suite (189 tests)
├── requirements.txt
└── venv/              # Virtual environment (never commit)
```

> **There is no `backend/.env`.** All configuration lives in the single `.env` at the repo root —
> see **[ENVIRONMENT.md](./ENVIRONMENT.md)** for every variable, its default, and what changing it
> does.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Reinstall Python with "Add to PATH" checked |
| `ModuleNotFoundError` | Venv not activated, or `pip install -r requirements.txt` not run |
| Port 8000 busy | `uvicorn app.main:app --port 8001` |
| `uvicorn --reload` hangs | Known on this machine — run without `--reload`, restart manually after edits |
| `pip` slow | `pip install -r requirements.txt -i https://pypi.org/simple` |
