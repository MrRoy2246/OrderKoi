#!/bin/sh
# OrderKoi — automated PostgreSQL backups.
#
# Runs as the `backup` service in docker-compose.yml, on the SAME
# postgres image as the database (see deploy/backup.Dockerfile). That
# matters: pg_dump refuses to dump a server newer than itself, so using
# the database's own image means the client can never fall behind. The
# backend image carries no pg_dump on purpose — the API has no business
# holding database credentials for dumping.
#
# Each cycle:
#   1. pg_dump in CUSTOM format (-Fc) — compressed, and the only format
#      pg_restore can --clean or partially restore from. A plain .sql
#      dump cannot be laid over an existing database (it fails with
#      "relation already exists" and psql still exits 0).
#   2. Encrypts it (BACKUP_ENCRYPTION, on by default) — see below.
#   3. Writes to *.partial and renames only after success, so a file
#      interrupted by a crash or a full disk can never be mistaken for
#      a good backup.
#   4. Verifies the archive is readable (pg_restore --list) before
#      trusting it — a file that exists is not a file that restores.
#   5. Prunes, keeping the newest BACKUP_KEEP.
#
# Why encryption is on by default: a dump holds bcrypt password hashes
# and every customer's name, phone and address. The offsite copy is the
# whole point of backing up (see docs/DEPLOYMENT.md), and a file like
# that arriving on a NAS, in an object bucket or on someone's laptop is
# one mis-set permission away from being a data breach. Encrypting here
# means the artifact that leaves this machine is already useless without
# the passphrase. The plaintext intermediate is deleted in the same
# cycle, and never survives into ./backend/backups.
#
# Offsite is deliberately NOT handled here: this container cannot know
# where "offsite" is. See docs/DEPLOYMENT.md for the host-side copy — a
# backup that only lives on the machine it protects is not a backup.
set -eu

INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
KEEP="${BACKUP_KEEP:-14}"
DIR="${BACKUP_DIR:-/backups}"

# Encryption. "on" (default) requires BACKUP_PASSPHRASE; "off" writes
# plain .dump files and says so on every cycle, because the only reason
# to turn it off is that you have encryption somewhere else in the path
# — and that decision should be visible in the log, not silent.
ENCRYPTION="${BACKUP_ENCRYPTION:-on}"
# PBKDF2 rounds. 200k is a sane 2020s default for a passphrase-derived
# key; raise it on faster hardware, and note that a restore needs the
# same value (it is stored in no header — see the docs).
PBKDF2_ITER="${BACKUP_PBKDF2_ITER:-200000}"

mkdir -p "$DIR"

case "$ENCRYPTION" in
    on)
        if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
            echo "BACKUP FAILED: BACKUP_ENCRYPTION is on but BACKUP_PASSPHRASE is empty." >&2
            echo "  Set it in .env (long and random — it is the only thing protecting the dumps)," >&2
            echo "  or set BACKUP_ENCRYPTION=off to store them unencrypted and take" >&2
            echo "  responsibility for encrypting them before they leave this machine." >&2
            exit 1
        fi
        ;;
    off)
        echo "WARNING: BACKUP_ENCRYPTION=off — dumps are written UNENCRYPTED." >&2
        echo "  They contain password hashes and customer PII. Encrypt the offsite copy." >&2
        ;;
    *)
        echo "BACKUP FAILED: BACKUP_ENCRYPTION must be 'on' or 'off', got '${ENCRYPTION}'." >&2
        exit 1
        ;;
esac

# Every complete backup, either suffix, never a partial. Used by both
# the freshness check and the pruner so the two cannot disagree about
# what counts as a backup.
backup_files() {
    ls -1t "${DIR}"/orderkoi-* 2>/dev/null | grep -v '\.partial$' || true
}

# Write one backup. Non-zero if anything went wrong, having cleaned up
# after itself; the caller reports and prunes either way.
_attempt_backup() {
    timestamp="$(date -u +%Y%m%d-%H%M%S)"
    plain="${DIR}/orderkoi-${timestamp}.dump"
    staged="${plain}.partial"
    if [ "$ENCRYPTION" = "on" ]; then
        final="${plain}.enc"
    else
        final="$plain"
    fi
    # Where the finished artifact currently sits; it is renamed into
    # place at the end. The encrypted path writes a separate file, the
    # plain path is already at its staging name.
    produced="$staged"

    if ! pg_dump --format=custom --no-password --file="$staged" "$PGDATABASE"; then
        echo "BACKUP FAILED: pg_dump could not write the dump — no new backup written" >&2
        rm -f "$staged"
        return 1
    fi

    if ! pg_restore --list "$staged" >/dev/null 2>&1; then
        echo "BACKUP FAILED: the dump is not a readable archive — discarded, no new backup" >&2
        rm -f "$staged"
        return 1
    fi

    if [ "$ENCRYPTION" = "on" ]; then
        # Encrypted into a .partial of its own, then renamed — a half
        # written .enc must never look like a finished backup, the same
        # rule the dump follows. -salt is on by default and is what
        # keeps two identical dumps from producing identical ciphertext.
        if ! openssl enc -aes-256-cbc -pbkdf2 -iter "$PBKDF2_ITER" -salt \
            -pass env:BACKUP_PASSPHRASE <"$staged" >"${final}.partial"; then
            echo "BACKUP FAILED: encryption failed — no new backup written" >&2
            rm -f "$staged" "${final}.partial"
            return 1
        fi
        # The plaintext goes now, not later. Keeping it would defeat the
        # whole exercise.
        rm -f "$staged"
        produced="${final}.partial"
    fi

    # Checked, not assumed. This function is called from an `if`, and
    # the shell turns off `set -e` for the whole body of a function
    # called that way — so any command here that fails would otherwise
    # fall through to "backup ok" over a file that isn't there.
    if ! mv "$produced" "$final"; then
        echo "BACKUP FAILED: could not install ${final} — no new backup written" >&2
        rm -f "$produced"
        return 1
    fi
    if [ ! -s "$final" ]; then
        echo "BACKUP FAILED: ${final} is empty — removed" >&2
        rm -f "$final"
        return 1
    fi

    echo "backup ok: ${final} ($(wc -c <"$final") bytes)"
    return 0
}

take_backup() {
    if _attempt_backup; then
        :
    else
        echo "  (no new backup on disk for this cycle)" >&2
    fi

    # Keep the newest $KEEP. `tail -n +N` starts AT line N, so KEEP+1
    # skips exactly the files being kept.
    backup_files | tail -n +"$((KEEP + 1))" | while read -r old; do
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
    if [ -n "$(find "$DIR" -maxdepth 1 -name 'orderkoi-*' ! -name '*.partial' \
        -mmin -"$((INTERVAL_HOURS * 60))" 2>/dev/null | head -n 1)" ]; then
        echo "a backup newer than ${INTERVAL_HOURS}h already exists — waiting"
    else
        take_backup
    fi

    sleep "$((INTERVAL_HOURS * 3600))"
done
