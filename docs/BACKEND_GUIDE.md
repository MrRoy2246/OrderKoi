# 🐍 Backend Guide — FastAPI

The OrderKoi backend. Python 3.11 + FastAPI + SQLAlchemy + SQLite (dev).

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
- Health check: `http://localhost:8000/health`

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

- Dev: SQLite file `orderkoi.db` (auto-created in `backend/`)
- Delete it to reset all data: `rm orderkoi.db` (or delete in Explorer)
- ⚠️ `Base.metadata.create_all` does **not** add columns to existing SQLite tables — schema changes to an existing dev DB need a manual `ALTER TABLE` (see `scripts/migrate.py`)
- Free plan: one-time 15-order allowance, configured via `free_plan_orders` in `app/config.py` (defaults from `.env`)
- Production: PostgreSQL — switch via `.env` variable (Phase 8b)

## Project layout

```
backend/
├── app/
│   ├── main.py        # FastAPI app, routes registration, CORS
│   ├── config.py      # Settings from .env (incl. free_plan_orders = 15)
│   ├── database.py    # DB engine & session
│   ├── email.py       # SMTP (starttls) with console fallback
│   ├── models.py      # SQLAlchemy models (Seller, Order, UpgradeRequest, SubscriptionEvent)
│   ├── schemas.py     # Pydantic request/response schemas
│   ├── security.py    # Password hashing, JWT create/verify
│   ├── utils.py       # Timezone helpers (Asia/Dhaka business time)
│   └── routes/
│       ├── auth.py    # /auth/* — signup, login, me, password reset, subscription-history, cancel-subscription
│       ├── orders.py  # /orders CRUD + status changes + /orders/stats/summary (free-allowance gate)
│       ├── tracking.py# /track/{code} — public
│       ├── admin.py   # /admin/* — stats, sellers, upgrade requests, subscription events
│       └── public.py  # /public/stores/{slug} — order form + is_accepting_orders
├── scripts/
│   ├── seed_admin.py  # Bootstrap an admin account
│   └── migrate.py     # Manual SQLite schema migrations (ALTER TABLE)
├── tests/             # pytest suite (147 tests)
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
