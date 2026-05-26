#!/bin/bash
# Weekly runtime snapshot (processed/, annotations/, trained_models/, backtest ground_truth)
# Cron: 0 4 * * 0 cd /opt/brightify && bash scripts/backup-snapshot.sh >> var/logs/backup-snapshot.log 2>&1
set -euo pipefail

BACKUPS_PATH="${BACKUPS_PATH:-./var/backups}"
RUNTIME_PATH="${RUNTIME_PATH:-./var/runtime}"
SNAP_DIR="$BACKUPS_PATH/snapshots"
TIMESTAMP=$(date +%Y%m%d)
FILENAME="runtime_${TIMESTAMP}.tar.zst"

mkdir -p "$SNAP_DIR"

echo "[$(date -Iseconds)] Starting runtime snapshot: $FILENAME"

tar --use-compress-program='zstd -19 -T0' \
    -cf "$SNAP_DIR/$FILENAME" \
    -C "$RUNTIME_PATH" \
    processed annotations trained_models backtest/ground_truth backtest/baselines 2>/dev/null || true

echo "OK: $FILENAME"

# Keep last 4 weeks locally
find "$SNAP_DIR" -name "runtime_*.tar.zst" -mtime +28 -delete

if command -v rclone >/dev/null 2>&1; then
  rclone copy "$SNAP_DIR/$FILENAME" "brightify-backup:snapshots/" --quiet
  echo "OK: synced to off-site storage"
fi
