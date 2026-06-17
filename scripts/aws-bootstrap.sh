#!/usr/bin/env bash
# Run ON the EC2 host (cd /opt/brightify) for the FIRST bring-up, after:
#   - the repo is cloned to /opt/brightify
#   - scripts/aws-sync-data.sh has been run from your laptop (S3 + serving release)
#   - .env is filled (cp .env.example .env; set POSTGRES_*, ALLOWED_ORIGINS,
#     AUDIO_CDN_BASE=https://<cloudfront_domain>, APP_IMAGE=<ecr_url>:latest)
#
# Brings the stack up, seeds the DB once, and health-checks.
# Note: APP_IMAGE must already exist in ECR. Either let CI build+push it first
# (merge to main → deploy.yml), or build/push once manually (see DEPLOY.md).
set -euo pipefail

cd /opt/brightify

[ -f .env ] || { echo "ERROR: .env missing. cp .env.example .env and fill it."; exit 1; }
[ -L var/serving_releases/current ] || { echo "ERROR: serving release missing. Run scripts/aws-sync-data.sh from your laptop first."; exit 1; }

set -a; . ./.env; set +a
: "${APP_IMAGE:?APP_IMAGE must be set in .env (ECR image)}"
REGION="${AWS_REGION:-ap-southeast-1}"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.aws.yml"

echo "[1/5] Generate local secrets (db_password, admin_key)"
make init

echo "[2/5] ECR login + pull image"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${APP_IMAGE%/*}"
$COMPOSE pull

echo "[3/5] Start stack (db, redis, migrate, app, nginx)"
$COMPOSE up -d

echo "[4/5] Seed the database (one-time)"
sleep 20
$COMPOSE run --rm app python -m db.seed

echo "[5/5] Health check"
sleep 5
make verify

echo
echo "Up. Browse http://<public-ip>/  — then set up a domain + HTTPS (DEPLOY.md Phase 5)."
