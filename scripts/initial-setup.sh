#!/bin/bash
# First-time setup: init dirs, start db, migrate, seed, warmup models, start stack
# Usage: bash scripts/initial-setup.sh
set -euo pipefail

echo "=== Brightify initial setup ==="

# 1. Create var/ directory structure and secrets
make init

# 2. Load env
set -a
source .env
set +a

# 3. Start DB + Redis (wait for healthy)
echo "Starting DB and Redis..."
docker compose up -d db redis

echo "Waiting for DB to be ready..."
until docker compose exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" 2>/dev/null; do
  sleep 2
done
echo "DB ready"

# 4. Run Alembic migrations
echo "Applying migrations..."
docker compose run --rm migrate
echo "Migrations applied"

# 5. Seed DB if empty
SONG_COUNT=$(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -tAc "SELECT COUNT(*) FROM songs;" 2>/dev/null || echo "0")

if [ "$SONG_COUNT" -lt "100" ]; then
  echo "Seeding database (may take several minutes)..."
  docker compose run --rm app python -m db.seed
  echo "Database seeded"
else
  echo "Database already has $SONG_COUNT songs, skipping seed"
fi

# 6. Warmup HuggingFace model cache (skip entirely when PhoBERT is disabled)
# CLIP removed: not used by the running app. PhoBERT is the only runtime model
# and is unused when SKIP_PHOBERT_LOAD=True — emotion labels are precomputed.
if [ "${SKIP_PHOBERT_LOAD:-False}" = "True" ]; then
  echo "SKIP_PHOBERT_LOAD=True — skipping model warmup (no runtime model needed)"
else
  echo "Warming up model cache (PhoBERT)..."
  docker compose run --rm app python -c "
from transformers import AutoTokenizer, AutoModel
AutoTokenizer.from_pretrained('vinai/phobert-base-v2')
AutoModel.from_pretrained('vinai/phobert-base-v2')
print('PhoBERT cached')
"
fi

# 7. Start full stack
echo "Starting full stack..."
docker compose up -d
echo ""
echo "=== Brightify is ready at http://localhost ==="
echo "Run 'make logs' to follow logs"
