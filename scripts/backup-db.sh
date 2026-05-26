#!/bin/bash
# Daily DB backup — run from project root
# Cron: 0 3 * * * cd /opt/brightify && bash scripts/backup-db.sh >> var/logs/backup-db.log 2>&1
set -euo pipefail

BACKUPS_PATH="${BACKUPS_PATH:-./var/backups}"
DB_DIR="$BACKUPS_PATH/db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="brightify_${TIMESTAMP}.sql.gz"

mkdir -p "$DB_DIR"

echo "[$(date -Iseconds)] Starting DB backup: $FILENAME"

docker compose exec -T db pg_dump \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  --no-owner --clean --if-exists --serializable-deferrable \
  | gzip -9 > "$DB_DIR/$FILENAME"

# Verify archive integrity
gunzip -t "$DB_DIR/$FILENAME" || { echo "ERROR: Backup corrupt, aborting"; exit 1; }

SIZE=$(stat -f%z "$DB_DIR/$FILENAME" 2>/dev/null || stat -c%s "$DB_DIR/$FILENAME")
echo "OK: $FILENAME ($(numfmt --to=iec <<< $SIZE))"

# Keep last 7 days locally
find "$DB_DIR" -name "brightify_*.sql.gz" -mtime +7 -delete

# Off-site sync (requires rclone configured with remote 'brightify-backup')
if command -v rclone >/dev/null 2>&1; then
  rclone copy "$DB_DIR/$FILENAME" "brightify-backup:db/" --quiet
  echo "OK: synced to off-site storage"
fi
