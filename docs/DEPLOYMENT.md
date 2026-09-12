# 🚢 Deployment & Admin Guide — Docker

How to run OrderKoi with Docker, how the **first admin account** gets created on a fresh database, and how to deploy to a real server.

> **The short version:** sellers register themselves through the website's Sign up page — that's by design. The **admin** account can NEVER be created through the website (so no visitor can ever make themselves platform owner). It only exists through one command, run inside the backend container. Everything below explains this in full.

---

## 1. Who can register what

| Account type | How it's created | Who can do it |
|---|---|---|
| **Seller** | Website → **Sign up** (`/signup`) | Anyone — it's the public product flow |
| **Admin** (platform owner) | `python -m scripts.create_admin` command only | Only someone with access to the server |

The signup endpoint hard-codes the role to `seller`. There is no API endpoint, form, or parameter that can create or promote an admin — promoting requires server access by design. Admin accounts are also **excluded from the seller list** and have no shop; the admin panel is a separate area of the app.

---

## 2. Run the stack locally (fresh database)

From the repo root (requires Docker Desktop running):

```bash
docker compose up -d          # db + backend + frontend (Caddy skipped)
```

First start creates a **brand-new, empty Postgres database** inside a Docker volume, runs all Alembic migrations, and starts the servers:

| Service | Local address |
|---|---|
| Frontend | http://localhost:8090 |
| Backend API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |

**Verify the whole stack in a real browser** (landing, signup, admin login, every admin page — fails loudly on any console error or blocked request):

```bash
cd frontend && node scripts/docker-verify.mjs
```

(It expects the admin `abin@test.com / secretpass123` in the Docker volume — or edit the credentials at the top of the script.)

> Port 8090 (not 8080) because this dev machine has 8080/8081 in Windows' reserved port ranges — on a server it doesn't matter, Caddy owns the public ports.

Configuration comes from the **`.env` file in the repo root** (never committed; template: `.env.example`). If `.env` doesn't exist, copy `.env.example` and fill it in first — compose refuses to start without `POSTGRES_PASSWORD`, `SECRET_KEY`, `CORS_ORIGINS`, `FRONTEND_URL` and `VITE_API_URL`.

## 3. Create the admin on a new database

One command, run inside the running backend container:

```bash
docker compose exec backend python -m scripts.create_admin admin@yourdomain.com
```

- Prints a **random password once** — copy it into a password manager immediately
- The account is created **already email-verified**, so the login gate lets it straight in
- Want to choose the password yourself? `docker compose exec backend python -m scripts.create_admin admin@yourdomain.com "YourPassword123"` (minimum 12 characters)
- **Idempotent:** run it again with the same email and it does NOT duplicate or reset — it reports the account already exists (and can promote an existing seller account to admin by passing that account's email)

Then open http://localhost:8090/login and sign in. The admin panel link appears in the sidebar.

Resetting a lost admin password: pass the email **with** a new password — the script updates an existing account's password when one is given.

## 4. Where the data lives (and what deletes it)

- All data is in the Docker volume `orderkoi_pgdata` — it **survives** restarts, reboots, and `docker compose down`
- `docker compose down -v` **deletes the database permanently** — only run it on throwaway/test stacks
- This Docker database is **completely separate** from your local dev database (PostgreSQL 17 on port 5433). Stopping/starting Docker never touches dev data, and vice versa
- Caddy's TLS certificates live in `orderkoi_caddy_data` — same rule

Useful commands:

```bash
docker compose ps                # what's running
docker compose logs -f backend   # follow backend logs (also where console-backend emails print)
docker compose restart backend   # restart after a .env change
docker compose down              # stop everything, keep data
docker compose up -d             # start again (data intact)
```

## 5. Deploy to a real server (VPS + domain)

### 5.1 Prerequisites

- A VPS (any Linux, 2 GB RAM is plenty) with Docker installed (`curl -fsSL https://get.docker.com | sh`)
- A domain with **two DNS A-records** pointing at the VPS IP:
  - `orderkoi.example.com` → the site
  - `api.orderkoi.example.com` → the API
  (DNS must resolve BEFORE starting, or Let's Encrypt issuance fails)

### 5.2 Configure

On the server, clone the repo and create the root `.env` (copy `.env.example`):

```bash
cp .env.example .env
nano .env
```

Production values — every one matters:

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | new strong password (this is the production DB) |
| `SECRET_KEY` | new 64-hex random value: `python -c "import secrets; print(secrets.token_hex(32))"` — the app **refuses to boot** in production with the default/short key. Rotating it later logs everyone out |
| `ENVIRONMENT` | `production` (enables the boot checks) |
| `FRONTEND_URL` | `https://orderkoi.example.com` (used in reset/verification emails) |
| `VITE_API_URL` | `https://api.orderkoi.example.com` (baked into the frontend at build) |
| `CORS_ORIGINS` | `["https://orderkoi.example.com"]` (JSON array — the browser blocks API calls from anywhere else) |
| `SMTP_HOST/PORT/USERNAME/PASSWORD/EMAIL_FROM` | your email sender (empty = emails only print to logs) |
| `SITE_DOMAIN` / `API_DOMAIN` / `ACME_EMAIL` | the two domains + the email Let's Encrypt certificates are registered to |

### 5.3 Start (with the Caddy edge for automatic HTTPS)

```bash
docker compose --profile edge up --build -d
```

Caddy obtains TLS certificates automatically within a minute or two of DNS resolving. HTTP redirects to HTTPS.

### 5.4 First admin

```bash
docker compose exec backend python -m scripts.create_admin admin@orderkoi.example.com
```

Save the printed password. Done — `https://orderkoi.example.com` is live.

### 5.5 After-deploy checklist

- [ ] Make `og:image` URL absolute in `frontend/index.html` (relative today) and rebuild
- [ ] Nightly backups: cron on the host → `docker compose exec -T db pg_dump -U orderkoi orderkoi | gzip > backup-$(date +\%F).sql.gz`, copy to a second location
- [ ] Uptime monitoring on `/health` and `/ready` (UptimeRobot/BetterStack free tier)
- [ ] Try one real signup + one real order end to end

## 6. Updating to a new version

```bash
git pull
docker compose --profile edge up --build -d     # rebuilds changed images, runs new migrations on boot
```

The backend runs `alembic upgrade head` before every start — schema updates apply automatically. Data volumes are untouched by rebuilds.

## 7. Restoring a backup

```bash
gunzip -c backup-2026-09-12.sql.gz | docker compose exec -T db psql -U orderkoi -d orderkoi
```

(Run `docker compose stop backend` first so nothing writes mid-restore, then `start`.)

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Login works but admin page is blank | Fixed in `8aecfd6` — pull latest and rebuild. (Was: AdminOverview crashed on the paginated `/admin/sellers` envelope) |
| Port 8080/8081 "access forbidden" on this dev machine | Windows reserved port ranges — compose maps the frontend to **8090** locally |
| Can't log in on a fresh stack | There are no users yet — create the admin (section 3); sellers must sign up |
| Signup says "check your email" but nothing arrives | `SMTP_HOST` is empty (console backend) — the email is in `docker compose logs backend`; or your SMTP credentials are wrong |
| 429 Too Many Requests everywhere | You're going through a proxy without forwarded headers being trusted — this stack is configured correctly (uvicorn `FORWARDED_ALLOW_IPS=*`, backend port never public) |
| Backend won't boot in production | Almost always `SECRET_KEY` — must be set, not the default, ≥32 chars |
| Let's Encrypt fails on the VPS | DNS A-records not resolving yet, or ports 80/443 blocked by the VPS firewall |
