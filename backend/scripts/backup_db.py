"""Backup the dev/production database to a timestamped file.

PostgreSQL (DATABASE_URL / PG_* in .env): pg_dump in custom format
(-Fc) — consistent snapshot, restore with pg_restore. Credentials and
host/port come from the same .env the app reads, so rotating the DB
user or password needs no change here.

SQLite (legacy / zero-setup dev): sqlite3's online backup API (not a
file copy), so a WAL checkpoint is included and a backup taken while
the server is running is still consistent.

Usage (from backend/):
    python -m scripts.backup_db [backup_dir]

Defaults to backend/backups/ (gitignored). Keeps the newest KEEP_BACKUPS
backups and deletes older ones. Exits non-zero if the backup fails so a
scheduled task can surface the problem instead of failing silently.

Windows Task Scheduler (daily 3am):
    schtasks /create /tn "OrderKoi DB backup" /sc daily /st 03:00 ^
      /tr "\"C:\\...\\backend\\venv\\Scripts\\python.exe\" -m scripts.backup_db" ^
      /sd 2026/09/07
    (run from the backend/ directory — set "Start in" if using the GUI)
"""

import os
import shutil
import subprocess
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_DIR = BACKEND_DIR / "backups"
KEEP_BACKUPS = 14

# Where pg_dump lives when it isn't on PATH: the standard Windows
# install layout, newest version first.
_PG_INSTALL_ROOT = Path("C:/Program Files/PostgreSQL")


def _find_pg_dump() -> str:
    """Locate pg_dump: $PG_BINDIR, then PATH, then standard installs."""
    bindir = os.environ.get("PG_BINDIR")
    if bindir and (Path(bindir) / "pg_dump.exe").exists():
        return str(Path(bindir) / "pg_dump.exe")
    found = shutil.which("pg_dump")
    if found:
        return found
    if _PG_INSTALL_ROOT.exists():
        candidates = sorted(_PG_INSTALL_ROOT.iterdir(), reverse=True)
        for version_dir in candidates:
            exe = version_dir / "bin" / "pg_dump.exe"
            if exe.exists():
                return str(exe)
    raise FileNotFoundError(
        "pg_dump not found — set PG_BINDIR in .env to your PostgreSQL "
        "bin directory (e.g. C:/Program Files/PostgreSQL/17/bin)"
    )


def _backup_postgres(database_url: str, backup_dir: Path) -> Path:
    url = make_url(database_url)
    dest = backup_dir / f"orderkoi-{datetime.now().strftime('%Y%m%d-%H%M%S')}.dump"
    env = {**os.environ, "PGPASSWORD": url.password or ""}
    command = [
        _find_pg_dump(),
        "--format=custom",
        "--no-password",
        f"--host={url.host or 'localhost'}",
        f"--port={url.port or 5432}",
        f"--username={url.username or ''}",
        f"--file={dest}",
        url.database,
    ]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
    return dest


def _backup_sqlite(backup_dir: Path) -> Path:
    db_path = BACKEND_DIR / "orderkoi.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    dest = backup_dir / f"orderkoi-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"

    # The backup API copies page-by-page inside SQLite — consistent even
    # with WAL journaling and a live writer, unlike a raw file copy.
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return dest


def backup(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    from app.config import get_settings

    database_url = get_settings().database_url

    backup_dir.mkdir(parents=True, exist_ok=True)
    if database_url.startswith("postgresql"):
        return _backup_postgres(database_url, backup_dir)
    return _backup_sqlite(backup_dir)


def prune(backup_dir: Path = DEFAULT_BACKUP_DIR, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Delete all but the newest `keep` backups. Returns deleted paths."""
    backups = sorted(backup_dir.glob("orderkoi-*.dump")) + sorted(backup_dir.glob("orderkoi-*.db"))
    backups = sorted(set(backups), key=lambda p: p.name)
    stale = backups[:-keep] if len(backups) > keep else []
    for old in stale:
        old.unlink()
    return stale


def main() -> int:
    backup_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BACKUP_DIR
    try:
        dest = backup(backup_dir)
    except Exception as error:  # noqa: BLE001 — a scheduled job must report, not crash silently
        print(f"BACKUP FAILED: {error}")
        return 1

    size_kb = dest.stat().st_size / 1024
    print(f"Backed up to {dest} ({size_kb:.0f} KB)")

    deleted = prune(backup_dir)
    if deleted:
        print(f"Pruned {len(deleted)} old backup(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
