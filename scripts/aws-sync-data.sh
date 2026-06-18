#!/usr/bin/env bash
# Run LOCALLY (your laptop) after `terraform apply`. One shot:
#   1. generate the audio manifest
#   2. build a data-only serving release
#   3. upload the 17GB MP3 catalog to S3 (resumable)
#   4. rsync the serving release + data to the EC2 host
#
# Usage: scripts/aws-sync-data.sh <audio_bucket> <ec2_ip> [ssh_user]
#   audio_bucket / ec2_ip come from `terraform output` (audio_bucket, app_public_ip)
set -euo pipefail

BUCKET="${1:?usage: aws-sync-data.sh <audio_bucket> <ec2_ip> [ssh_user]}"
HOST="${2:?ec2 ip required}"
SSH_USER="${3:-ubuntu}"
REL="aws_release"

cd "$(cd "$(dirname "$0")/.." && pwd)"   # repo root
[ -f .venv/bin/activate ] && . .venv/bin/activate || true

# Use the Terraform-generated key if present (so SSH/rsync just work).
PEM="infra/terraform/brightify-ec2.pem"
SSH_OPTS="-o StrictHostKeyChecking=accept-new"
[ -f "$PEM" ] && SSH_OPTS="$SSH_OPTS -i $PEM"
SSH="ssh $SSH_OPTS"

echo "[1/5] Audio manifest"
make audio-manifest

echo "[2/5] Build data-only serving release (local)"
rm -rf "var/serving_releases/$REL"
PYTHONPATH=. python3 tools/build_serving_release.py --no-music --copy --release-name "$REL"

echo "[3/5] Upload MP3s to S3 (resumable; ~17GB, can take a while)"
aws s3 sync music_files/ "s3://$BUCKET/" --content-type audio/mpeg

echo "[4/5] rsync serving release -> EC2 (~200MB)"
$SSH "$SSH_USER@$HOST" 'sudo mkdir -p /opt/brightify/var/serving_releases && sudo chown -R ubuntu:ubuntu /opt/brightify'
rsync -avz --delete -e "$SSH" "var/serving_releases/$REL/" \
  "$SSH_USER@$HOST:/opt/brightify/var/serving_releases/$REL/"

echo "[5/6] Point 'current' symlink on EC2"
$SSH "$SSH_USER@$HOST" "ln -sfn $REL /opt/brightify/var/serving_releases/current"

# Crossfade backfill inputs (vocal_regions.csv + clean_durations.csv) are part of the
# serving release (build_serving_release.py _RUNTIME_SPEC) → already rsynced in step [4/5]
# under data/. deploy-remote.sh runs tools.backfill_vocal_regions + tools.backfill_durations
# after migrate, reading them via config.DATA_DIR (/app/serving/current/data). The app
# container has no /app/data mount, so the serving release is the only path that reaches it.

echo
echo "Done. Next: ssh $SSH_USER@$HOST, fill /opt/brightify/.env, run scripts/aws-bootstrap.sh."
echo "Crossfade backfills (vocal regions + reconciled durations) run automatically in deploy-remote.sh,"
echo "reading the CSVs that ride in the serving release."
