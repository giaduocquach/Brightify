#!/bin/bash
# App container entrypoint — runs as user 'app' (uid 1000)
set -euo pipefail

# Ensure writable directories exist (volumes may be empty on first start)
mkdir -p /app/logs /app/var/backtest /app/var/trained_models

exec "$@"
