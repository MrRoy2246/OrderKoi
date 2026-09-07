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
uvicorn app.main:app
```

- API base URL: `http://localhost:8000`
- **Swagger UI (interactive docs):** `http://localhost:8000/docs` ← your main testing tool
- ReDoc docs: `http://localhost:8000/redoc`
- Health check: `http://localhost:8000/health` (liveness) · `http://localhost:8000/ready` (checks the DB too — returns 503 if the DB is down)

> ⚠️ **On this machine, do NOT use `--reload` — it hangs.** Run the plain command above and restart the server manually after every backend edit.

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
- All connection settings live in `.env` (`PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`) — change the user, password, host, or port there and the app follows, no code change. A full `DATABASE_URL` overrides the parts; one of the two must be set (the app refuses to boot without a database).
- Schema is managed by **Alembic**: set up or update a database with `alembic upgrade head` (from `backend/`). After changing a model in `app/models.py`, generate a migration with `alembic revision --autogenerate -m "..."`, review it, then `upgrade head`.
- Free plan: one-time 15-order allowance, configured via `free_plan_orders` in `app/config.py` (defaults from `.env`)
- Tests run on the same engine as production, in a dedicated **`orderkoi_test`** database (selected via `PG_DATABASE` env override in `tests/conftest.py`; auto-created on first run — needs `CREATEDB` on the role, granted once: `ALTER ROLE orderkoi CREATEDB;`). Dev data is never touched; the schema is created/dropped per session.

## Backups

```bash
python -m scripts.backup_db        # from backend/ — also run by Task Scheduler daily at 3:07 AM
```

- `pg_dump` custom format → `backend/backups/orderkoi-YYYYMMDD-HHMMSS.dump` (restore with `pg_restore`). Credentials come from `.env`; `pg_dump` is located via `PG_BINDIR`, PATH, or the standard install dir.
- Keeps the newest 14 backups, deletes older ones automatically
- The Windows scheduled task is **"OrderKoi DB backup"** — view it in Task Scheduler or `schtasks /query /tn "OrderKoi DB backup"`

## Email

- All SMTP settings live in `.env` (never commit it). Empty `SMTP_HOST` = emails print to the console instead of sending.
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
│   ├── config.py      # Settings from .env (incl. free_plan_orders = 15)
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
│       └── public.py  # /public/stores/{slug} — order form + is_accepting_orders (honeypot)
├── scripts/
│   ├── create_admin.py # Bootstrap/promote the platform admin (idempotent) - run after alembic upgrade head on a fresh DB
│   ├── backup_db.py   # Timestamped pg_dump backup (keep 14) - runs daily via Task Scheduler
│   └── audit_probe.py # Manual audit helpers
├── backups/           # Backup output (gitignored)
├── tests/             # pytest suite (177 tests)
├── requirements.txt
├── .env.example       # Template for secrets — copy to .env
└── venv/              # Virtual environment (never commit)
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Reinstall Python with "Add to PATH" checked |
| `ModuleNotFoundError` | Venv not activated, or `pip install -r requirements.txt` not run |
| Port 8000 busy | `uvicorn app.main:app --port 8001` |
| `uvicorn --reload` hangs | Known on this machine — run without `--reload`, restart manually after edits |
| `pip` slow | `pip install -r requirements.txt -i https://pypi.org/simple` |
