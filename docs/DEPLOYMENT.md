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

Configuration comes from the **`.env` file in the repo root** (never committed; template: `.env.example`). If `.env` doesn't exist, copy `.env.example` and fill it in first — compose refuses to start without `POSTGRES_PASSWORD`, `SECRET_KEY`, `CORS_ORIGINS`, `FRONTEND_URL`, `VITE_API_URL`, `BKASH_NUMBER` and `SUPPORT_EMAIL`. (`SITE_DOMAIN`/`API_DOMAIN`/`ACME_EMAIL` must be *set* even if you never use the edge profile — compose substitutes the whole file before it filters by profile, so leaving them blank aborts startup over a service you aren't running.)

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
- [ ] Confirm backups are running: `docker compose ps` shows `backup` Up, and `backend/backups/` has a fresh `.dump.enc` (section 7)
- [ ] Store `BACKUP_PASSPHRASE` somewhere that is **not** this VPS — without it the backups cannot be read (section 7)
- [ ] Point the offsite copy at `backend/backups/` — a backup that only lives on this VPS is not a backup (section 7)
- [ ] Test one restore into a scratch database (section 8) — before you need it, not during an outage
- [ ] Uptime monitoring on `/health` and `/ready` (UptimeRobot/BetterStack free tier)
- [ ] Try one real signup + one real order end to end

## 6. Updating to a new version

```bash
git pull
docker compose --profile edge up --build -d     # rebuilds changed images, runs new migrations on boot
```

The backend runs `alembic upgrade head` before every start — schema updates apply automatically. Data volumes are untouched by rebuilds.

**Prune the old images.** Every `--build` leaves the previous image dangling. On
a small VPS that adds up quietly until the disk fills — and a full disk is not a
clean failure, it corrupts Postgres writes. Check and clean up:

```bash
docker system df -v          # what is actually using the space
docker image prune -f        # dangling images from previous builds — always safe
docker builder prune -f      # build cache (rebuilds get slower afterwards)
```

Neither touches `orderkoi_pgdata` or any named volume — images and volumes are
separate, so a mistyped prune cannot delete your data. `docker system prune -a
--volumes` **would**, so don't run that one on this host.

A cron line keeps it tidy without you remembering:

```bash
# /etc/cron.d/orderkoi-prune
0 4 * * 0 root docker image prune -f >/dev/null 2>&1
```


## 7. Backups

The stack runs its own backup container — **there is no cron job to set up.**

```bash
docker compose ps                             # `backup` should be Up
ls -lh backend/backups/                       # the dumps land here
docker compose logs --tail=20 backup          # what it has been doing
```

Every `BACKUP_INTERVAL_HOURS` (default 24) it dumps the database to
`./backend/backups/orderkoi-<UTC timestamp>.dump.enc`, keeps the newest
`BACKUP_KEEP` (default 14), and prunes the rest. Both are `.env` values — no
code change:

```bash
BACKUP_INTERVAL_HOURS=6
BACKUP_KEEP=30
```

Four details make the difference between "a file exists" and "a backup":

| | Why |
|---|---|
| It is **encrypted** (AES-256) before it is written | A dump holds bcrypt password hashes and every customer's name, phone and address. The offsite copy is the point of backing up, and that file arriving on a NAS, in an object bucket or on a laptop is one mis-set permission away from a breach |
| It writes `*.partial` and renames only after success | A dump cut short by a crash or a full disk can never be mistaken for a good one |
| It verifies each dump with `pg_restore --list` before keeping it | An unreadable archive is deleted and the failure is logged, rather than discovered years later |
| It is built on `postgres:17-alpine`, the database's own image | `pg_dump` refuses to dump a server **newer** than itself, so the client can never fall behind |

### The backup passphrase

Encryption is on by default and needs `BACKUP_PASSPHRASE` — a **required**
`.env` value. The backup service refuses to start without it and says so:

```bash
# generate one
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

```bash
BACKUP_PASSPHRASE=<long random string>
```

> **There is no recovery path.** The passphrase is not stored in the dump, and
> nothing on the server can derive it. Keep a copy in your password manager
> **and** in whatever you use to bootstrap a new VPS — not on the VPS itself.
> Without it the backups are noise, and this is the one operational mistake in
> this guide that destroys data instead of exposing it.

`BACKUP_ENCRYPTION=off` writes plain `.dump` files instead. Only do that if
something further down the path (an encrypted bucket, `rclone crypt`) encrypts
them, and note the log shouts `WARNING: … UNENCRYPTED` on every cycle so the
choice stays visible.

The plaintext intermediate is deleted in the same cycle it is created — it
never lands in `./backend/backups`.

A backup that only exists on the machine it protects is not a backup. Add a
host-side copy to a different provider — a cron line is enough:

```bash
# /etc/cron.d/orderkoi-offsite — adjust the path and destination
30 3 * * * root rsync -a --delete /opt/orderkoi/backend/backups/ user@other-host:/backups/orderkoi/
```

(or `rclone copy` to S3/B2/Drive — anything that isn't this VPS.) The files are
already encrypted, so this step is a copy and nothing more.

**Test a restore before you need one.** An untested backup is a guess. Do it
against a throwaway database, never the live one — section 8 covers the
mechanics, and the cheap version is: restore the newest dump into a scratch
database and check the row counts.

Want a dump right now, without waiting for the interval?

```bash
docker compose run --rm -e BACKUP_ONCE=1 backup
```

## 8. Restoring a backup

Stop the API first so nothing writes mid-restore, then put it back afterwards:

```bash
docker compose stop backend
```

**Step 1 — decrypt it.** Dumps are encrypted (section 7), so the first command
of any restore turns the artifact back into something `pg_restore` can read:

```bash
docker compose exec backup sh -c \
  'openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE \
   < /backups/orderkoi-20260916-064156.dump.enc \
   > /backups/orderkoi-20260916-064156.dump'
```

The passphrase comes from the container's own environment — the same
`BACKUP_PASSPHRASE` the backup was written with, so no secret is typed on the
command line where it would land in your shell history.

`-iter 200000` must match `BACKUP_PBKDF2_ITER` (the default). It is **not**
recorded in the file: a restore with the wrong iteration count fails with
`bad decrypt`, and the fix is to use the value the dumps were written with.

A wrong passphrase fails here too (`bad decrypt`), which is the honest
outcome — you get an error, not a truncated database. Delete the decrypted
`.dump` when the restore is done; it is the one file that shouldn't linger.

**Option A — restore over the existing database** (drops and recreates the
objects the dump contains; anything the dump doesn't know about is left alone):

```bash
docker compose exec backup pg_restore \
  --clean --if-exists --single-transaction \
  -d orderkoi /backups/orderkoi-20260916-064156.dump
```

`docker compose exec backup …` is the right container: it holds the dumps
(mounted at `/backups`) and already carries the `PGHOST`/`PGUSER`/`PGPASSWORD`
for the database. `--single-transaction` makes the whole restore atomic — it
either completes or changes nothing, so a half-restored database is not a state
you can end up in.

**Option B — guaranteed-exact state** (wipe the database, then restore into it).
Use this when you want the server to match the dump and nothing else:

```bash
docker compose exec -T db psql -U orderkoi -d postgres -c "DROP DATABASE orderkoi WITH (FORCE);"
docker compose exec -T db psql -U orderkoi -d postgres -c "CREATE DATABASE orderkoi OWNER orderkoi;"
docker compose exec backup pg_restore -d orderkoi /backups/orderkoi-20260916-064156.dump
```

Then bring the API back and **verify it actually restored**:

```bash
docker compose start backend
docker compose exec -T db psql -U orderkoi -d orderkoi \
  -c "SELECT version_num FROM alembic_version;" \
  -c "SELECT count(*) AS sellers FROM sellers;" \
  -c "SELECT count(*) AS orders FROM orders;"
```

If the row counts look like your data and `alembic_version` matches the deployed
revision, the restore worked. If `alembic_version` is *ahead* of your code,
`git pull` — the dump came from a newer deploy.

> **Do not restore a `.dump` by piping it through `psql`.** These dumps are in
> PostgreSQL's custom format (`-Fc`) — compressed, and the only format
> `pg_restore` can `--clean` or partially restore from. Feeding one to `psql`
> fails immediately. (The reverse mistake is worse: laying a *plain SQL* dump
> over a live database prints dozens of `relation already exists` errors while
> `psql` still exits **0** — a silent, partial restore that looks like success.
> That is why this guide no longer documents the `gunzip … | psql` form.)

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
| `backend/backups/` stays empty | `docker compose logs backup` — usually `POSTGRES_PASSWORD` doesn't match the database's, or (with encryption on) `BACKUP_PASSPHRASE` is unset. The log says `BACKUP FAILED … no new backup written`, and no file is left behind on purpose |
| Backup log says `UNENCRYPTED` every cycle | `BACKUP_ENCRYPTION=off` is set in `.env`. Fine only if something further down the path encrypts the copy — otherwise set it back to `on` and set a passphrase |
| Restore fails with `bad decrypt` | Wrong passphrase, or `-iter` doesn't match the `BACKUP_PBKDF2_ITER` the dumps were written with (it is not stored in the file) — section 8 |
| Restore prints `relation already exists` warning spam | The dump was piped through `psql` instead of `pg_restore` (section 8). Note `psql` still exits **0** in that case — the restore half-failed and reported success |
