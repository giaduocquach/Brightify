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

# 6. Warmup HuggingFace model cache
echo "Warming up model cache (PhoBERT + CLIP)..."
docker compose run --rm app python -c "
from transformers import AutoTokenizer, AutoModel, CLIPModel, CLIPProcessor
AutoTokenizer.from_pretrained('vinai/phobert-base-v2')
AutoModel.from_pretrained('vinai/phobert-base-v2')
CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
CLIPModel.from_pretrained('openai/clip-vit-base-patch32')
print('Models cached')
"

# 7. Start full stack
echo "Starting full stack..."
docker compose up -d
echo ""
echo "=== Brightify is ready at http://localhost ==="
echo "Run 'make logs' to follow logs"
