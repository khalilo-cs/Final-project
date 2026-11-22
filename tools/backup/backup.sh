#!/bin/sh
# One backup: the database (pg_dump custom format) + the uploaded project files.
# Runs inside the `backup` service (docker-compose.yml) once a day, or by hand:
#   docker compose run --rm backup /tools/backup.sh
set -eu

: "${PGHOST:=postgres}" "${PGUSER:?}" "${PGDATABASE:?}" "${PGPASSWORD:?}"
DEST="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
WORK="$DEST/.mihakk-$STAMP.partial"

mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

pg_dump --format=custom --compress=6 --file="$WORK/database.dump" "$PGDATABASE"
# Student files (already AES-256 encrypted when STORAGE_ENCRYPTION_KEY is set).
tar -C "${DATA_DIR:-/data}" -czf "$WORK/project-files.tar.gz" .
( cd "$WORK" && sha256sum database.dump project-files.tar.gz > SHA256SUMS )

# Publish atomically: a half-written backup never looks complete.
mv "$WORK" "$DEST/mihakk-$STAMP"
trap - EXIT
echo "backup written: $DEST/mihakk-$STAMP ($(du -sh "$DEST/mihakk-$STAMP" | cut -f1))"

# Rotation: keep the last KEEP_DAYS days, but never delete the newest backup.
find "$DEST" -maxdepth 1 -type d -name 'mihakk-*' -mtime "+$KEEP_DAYS" \
  ! -name "mihakk-$STAMP" -exec rm -rf {} +
