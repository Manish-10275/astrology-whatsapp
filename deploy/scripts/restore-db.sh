#!/usr/bin/env bash
# ==============================================================================
# SAFE DATABASE RESTORATION SCRIPT
# ==============================================================================
# Usage:
#   ./deploy/scripts/restore-db.sh /var/backups/astrology/astrology_20261024_120000.sql.gz
# ==============================================================================
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path-to-backup.sql.gz>"
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "${BACKUP_FILE}" ]; then
    echo "Error: Backup file '${BACKUP_FILE}' does not exist."
    exit 1
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-astrology_postgres}"
POSTGRES_USER="${POSTGRES_USER:-astrology_user}"
POSTGRES_DB="${POSTGRES_DB:-astrology_prod}"

echo "=================================================================="
echo "WARNING: DESTRUCTIVE ACTION"
echo "This will restore the database from: ${BACKUP_FILE}"
echo "Target Container: ${POSTGRES_CONTAINER}"
echo "Target Database:  ${POSTGRES_DB}"
echo "=================================================================="
read -r -p "Are you sure you want to proceed? Type 'RESTORE' to confirm: " CONFIRMATION

if [ "${CONFIRMATION}" != "RESTORE" ]; then
    echo "Restoration aborted."
    exit 0
fi

echo "==> Terminating active connections to '${POSTGRES_DB}'..."
docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();"

echo "==> Streaming backup data into database..."
gunzip -c "${BACKUP_FILE}" | docker exec -i "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

echo "==> Restoration complete! Running health check..."
docker exec "${POSTGRES_CONTAINER}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
echo "==> Database is ready."
