"""Backup the PostgreSQL database to a timestamped file.

pg_dump in custom format (-Fc) — a consistent snapshot, restore with:
    pg_restore -h <host> -U <user> -d <db> --clean orderkoi-<timestamp>.dump

Credentials and host/port come from the same .env the app reads
(DATABASE_URL / PG_*), so rotating the DB user or password needs no
change here. pg_dump is located via PG_BINDIR, PATH, or the standard
Windows install directory.

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
        for version_dir in sorted(_PG_INSTALL_ROOT.iterdir(), reverse=True):
            exe = version_dir / "bin" / "pg_dump.exe"
            if exe.exists():
                return str(exe)
    raise FileNotFoundError(
        "pg_dump not found — set PG_BINDIR in .env to your PostgreSQL "
        "bin directory (e.g. C:/Program Files/PostgreSQL/17/bin)"
    )


def backup(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    from app.config import get_settings

    url = make_url(get_settings().database_url)

    backup_dir.mkdir(parents=True, exist_ok=True)
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
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
    return dest


def prune(backup_dir: Path = DEFAULT_BACKUP_DIR, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Delete all but the newest `keep` backups. Returns deleted paths."""
    backups = sorted(backup_dir.glob("orderkoi-*.dump"), key=lambda p: p.name)
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
