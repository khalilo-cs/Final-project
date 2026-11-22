#!/bin/sh
# Restore a backup made by backup.sh (target: under one hour, NFR-05).
#   docker compose stop project-service auth-service viva-engine report-analyzer fraud-detector
#   docker compose run --rm backup /tools/restore.sh /backups/mihakk-YYYYMMDD-HHMMSS
#   docker compose up -d
set -eu

SRC="${1:?usage: restore.sh /backups/mihakk-YYYYMMDD-HHMMSS}"
: "${PGHOST:=postgres}" "${PGUSER:?}" "${PGDATABASE:?}" "${PGPASSWORD:?}"

( cd "$SRC" && sha256sum -c SHA256SUMS )
echo "restoring database $PGDATABASE from $SRC ..."
pg_restore --clean --if-exists --no-owner --dbname="$PGDATABASE" "$SRC/database.dump"
echo "restoring project files ..."
find "${DATA_DIR:-/data}" -mindepth 1 -delete
tar -C "${DATA_DIR:-/data}" -xzf "$SRC/project-files.tar.gz"
echo "restore complete"
