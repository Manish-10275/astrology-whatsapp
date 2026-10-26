#!/usr/bin/env bash
# ==============================================================================
# SAFE PRODUCTION MIGRATION RUNNER
# ==============================================================================
set -euo pipefail

echo "==> Running Alembic database migrations inside container..."
docker compose run --rm --no-deps api python -m alembic upgrade head

echo "==> Migrations applied successfully."
