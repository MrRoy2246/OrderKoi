# Backup image — the database's own postgres image, plus one tool.
#
# The base image is deliberate and load-bearing: pg_dump refuses to dump
# a server NEWER than itself, so running the backup on the same image as
# the database means the client version can never fall behind.
#
# What that image doesn't carry is openssl, and backups are encrypted
# with it before they are written (see deploy/backup.sh). Encrypting
# here rather than during the host-side offsite copy is the difference
# between "the copy in the bucket is useless without the passphrase" and
# "a plaintext dump of every customer's name, phone and address sits in
# ./backend/backups for BACKUP_KEEP days".
FROM postgres:17-alpine

# ~2MB: the CLI only. The base image already links libssl for Postgres's
# own TLS, but the binary lives in a package of its own.
RUN apk add --no-cache openssl
