"""Backup the dev SQLite database to a timestamped file.

Uses sqlite3's online backup API (not a file copy), so a WAL checkpoint
is included and a backup taken while the server is running is still
consistent.

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

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BACKEND_DIR / "orderkoi.db"
DEFAULT_BACKUP_DIR = BACKEND_DIR / "backups"
KEEP_BACKUPS = 14


def backup(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"orderkoi-{timestamp}.db"

    # The backup API copies page-by-page inside SQLite — consistent even
    # with WAL journaling and a live writer, unlike a raw file copy.
    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(dest)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    return dest


def prune(backup_dir: Path = DEFAULT_BACKUP_DIR, keep: int = KEEP_BACKUPS) -> list[Path]:
    """Delete all but the newest `keep` backups. Returns deleted paths."""
    backups = sorted(backup_dir.glob("orderkoi-*.db"))
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
