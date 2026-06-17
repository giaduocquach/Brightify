#!/usr/bin/env bash
# Run ON the EC2 host by the GitHub Actions deploy (via SSM Run Command).
# Syncs the repo to the deployed commit, pulls the new image, migrates, restarts.
#
# Usage: deploy-remote.sh <APP_IMAGE> <GIT_SHA>
set -euo pipefail

APP_IMAGE="${1:?APP_IMAGE required}"
GIT_SHA="${2:-origin/main}"

cd /opt/brightify

# deploy.env (written by cloud-init) provides AWS_REGION / AUDIO_CDN_BASE / etc.
# shellcheck disable=SC1091
[ -f /opt/brightify/deploy.env ] && . /opt/brightify/deploy.env

# Sync compose/nginx/scripts to the exact deployed commit (.env + var/ are gitignored, untouched).
# SSM runs this as root on an ubuntu-owned repo → trust the dir so git won't refuse.
git config --global --add safe.directory /opt/brightify 2>/dev/null || true
git fetch origin --quiet
git reset --hard "${GIT_SHA}"

export APP_IMAGE
REGISTRY="${APP_IMAGE%/*}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.aws.yml"
$COMPOSE pull app migrate
$COMPOSE run --rm migrate          # alembic upgrade head
$COMPOSE up -d

# nginx config is bind-mounted (compose up won't recreate it) — reload so any
# conf.d.aws change from this commit takes effect. Ignore if nginx isn't up yet.
docker exec brightify_nginx nginx -s reload 2>/dev/null || true

# Health gate — fail the deploy if the app does not come up.
for i in $(seq 1 12); do
  if curl -fsS http://localhost/api/health >/dev/null; then
    echo "deploy ok: $(curl -fsS http://localhost/api/health)"
    exit 0
  fi
  sleep 10
done
echo "health check failed after deploy" >&2
$COMPOSE logs --tail=50 app >&2 || true
exit 1
