#!/bin/sh
# Daily backups at BACKUP_HOUR (UTC, default 01:00) for as long as the container runs.
set -eu
HOUR="${BACKUP_HOUR:-1}"
while true; do
  now=$(date -u +%s)
  next=$(date -u -d "@$(( now - now % 86400 + HOUR * 3600 ))" +%s 2>/dev/null || echo 0)
  [ "$next" -le "$now" ] && next=$(( next + 86400 ))
  sleep $(( next - now ))
  /tools/backup.sh || echo "backup failed; will retry tomorrow" >&2
done
