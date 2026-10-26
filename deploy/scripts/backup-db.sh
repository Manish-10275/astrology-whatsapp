#!/usr/bin/env bash
# ==============================================================================
# AUTOMATED POSTGRESQL DATABASE BACKUP SCRIPT
# ==============================================================================
# Usage:
#   Add to crontab: 0 2 * * * /opt/astrology/deploy/scripts/backup-db.sh >> /var/log/astrology-backup.log 2>&1
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/astrology}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/astrology_${TIMESTAMP}.sql.gz"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting database backup..."

# Extract DB credentials from running container or default
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-astrology_postgres}"
POSTGRES_USER="${POSTGRES_USER:-astrology_user}"
POSTGRES_DB="${POSTGRES_DB:-astrology_prod}"

# Execute pg_dump from inside container and stream through gzip
if docker exec "${POSTGRES_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${BACKUP_FILE}"; then
    FILE_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup successful: ${BACKUP_FILE} (${FILE_SIZE})"
else
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] ERROR: Database backup failed!" >&2
    rm -f "${BACKUP_FILE}"
    exit 1
fi

# Clean up backups older than retention window
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Purging backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_DIR}" -name "astrology_*.sql.gz" -type f -mtime +"${RETENTION_DAYS}" -delete

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup routine finished."
