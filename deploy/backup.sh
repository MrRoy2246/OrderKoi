#!/bin/sh
# OrderKoi — automated PostgreSQL backups.
#
# Runs as the `backup` service in docker-compose.yml, on the SAME
# postgres image as the database. That matters: pg_dump refuses to
# dump a server newer than itself, so using the database's own image
# means the client can never fall behind. The backend image carries no
# pg_dump on purpose — the API has no business holding database
# credentials for dumping.
#
# Each cycle:
#   1. pg_dump in CUSTOM format (-Fc) — compressed, and the only format
#      pg_restore can --clean or partially restore from. A plain .sql
#      dump cannot be laid over an existing database (it fails with
#      "relation already exists" and psql still exits 0).
#   2. Writes to *.partial and renames only after success, so a dump
#      interrupted by a crash or a full disk can never be mistaken for
#      a good backup.
#   3. Verifies the archive is readable (pg_restore --list) before
#      trusting it — a file that exists is not a file that restores.
#   4. Prunes, keeping the newest BACKUP_KEEP.
#
# Offsite is deliberately NOT handled here: this container cannot know
# where "offsite" is. See docs/DEPLOYMENT.md for the host-side copy —
# a backup that only lives on the machine it protects is not a backup.
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP="${BACKUP_KEEP:-14}"
DIR="${BACKUP_DIR:-/backups}"

mkdir -p "$DIR"

take_backup() {
    timestamp="$(date -u +%Y%m%d-%H%M%S)"
    final="${DIR}/orderkoi-${timestamp}.dump"
    partial="${final}.partial"

    if pg_dump --format=custom --no-password --file="$partial" "$PGDATABASE" \
        && pg_restore --list "$partial" >/dev/null 2>&1; then
        mv "$partial" "$final"
        echo "backup ok: ${final} ($(wc -c <"$final") bytes)"
    else
        status=$?
        rm -f "$partial"
        echo "BACKUP FAILED (dump/verify exited ${status}) — no new backup written" >&2
    fi

    # Keep the newest $KEEP. `tail -n +N` starts AT line N, so KEEP+1
    # skips exactly the files being kept.
    ls -1t "${DIR}"/orderkoi-*.dump 2>/dev/null \
        | tail -n +"$((KEEP + 1))" \
        | while read -r old; do
            rm -f "$old"
            echo "pruned old backup: ${old}"
        done
}

echo "backup service: every ${INTERVAL_HOURS}h, keeping ${KEEP}, writing to ${DIR}"

# One-shot mode: take a backup and exit instead of looping. Used by the
# tests, and by anyone who would rather drive this from a host cron:
#     docker compose run --rm -e BACKUP_ONCE=1 backup
if [ "${BACKUP_ONCE:-}" = "1" ] || [ "${BACKUP_ONCE:-}" = "true" ]; then
    take_backup
    exit 0
fi

while true; do
    # Skip the cycle if a backup is already newer than the interval.
    # Without this, every container restart (a deploy, a reboot, a
    # `docker compose up -d`) would immediately take another dump.
    if [ -n "$(find "$DIR" -maxdepth 1 -name 'orderkoi-*.dump' \
        -mmin -"$((INTERVAL_HOURS * 60))" 2>/dev/null | head -n 1)" ]; then
        echo "a backup newer than ${INTERVAL_HOURS}h already exists — waiting"
    else
        take_backup
    fi

    sleep "$((INTERVAL_HOURS * 3600))"
done
