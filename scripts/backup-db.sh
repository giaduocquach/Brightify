#!/bin/bash
# Daily DB backup — run from project root
# Cron: 0 3 * * * cd /opt/brightify && bash scripts/backup-db.sh >> var/logs/backup-db.log 2>&1
set -euo pipefail

# Pick up AUDIO_BUCKET / AWS_REGION written by cloud-init (used as the default
# S3 backup target on the EC2 host).
# shellcheck disable=SC1091
[ -f /opt/brightify/deploy.env ] && . /opt/brightify/deploy.env

BACKUPS_PATH="${BACKUPS_PATH:-./var/backups}"
# S3 destination: explicit BACKUP_S3_BUCKET, else reuse the audio bucket under a prefix.
BACKUP_S3_BUCKET="${BACKUP_S3_BUCKET:-${AUDIO_BUCKET:-}}"
BACKUP_S3_PREFIX="${BACKUP_S3_PREFIX:-db-backups}"
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

# Off-site sync to S3 (EC2 instance role grants write to the bucket).
if [ -n "$BACKUP_S3_BUCKET" ] && command -v aws >/dev/null 2>&1; then
  aws s3 cp "$DB_DIR/$FILENAME" "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$FILENAME" --only-show-errors
  echo "OK: uploaded to s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$FILENAME"
  # Prune S3 copies older than 30 days
  CUTOFF=$(date -u -d '30 days ago' +%Y-%m-%d 2>/dev/null || date -u -v-30d +%Y-%m-%d)
  aws s3 ls "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/" | while read -r line; do
    FILE_DATE=$(echo "$line" | awk '{print $1}')
    FILE_NAME=$(echo "$line" | awk '{print $4}')
    if [ -n "$FILE_NAME" ] && [[ "$FILE_DATE" < "$CUTOFF" ]]; then
      aws s3 rm "s3://$BACKUP_S3_BUCKET/$BACKUP_S3_PREFIX/$FILE_NAME" --only-show-errors
    fi
  done
# Fallback: rclone off-site if configured (legacy)
elif command -v rclone >/dev/null 2>&1; then
  rclone copy "$DB_DIR/$FILENAME" "brightify-backup:db/" --quiet
  echo "OK: synced to off-site storage (rclone)"
fi
