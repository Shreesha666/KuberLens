#!/usr/bin/env bash
# PostgreSQL Automated Backup Script
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/stock_intel_${TIMESTAMP}.dump"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Initiating PostgreSQL database backup to ${BACKUP_FILE}..."

if [[ "${DATABASE_URL:-}" =~ postgresql://([^:]+):([^@]+)@([^:]+):([0-9]+)/(.+) ]]; then
    DB_USER="${BASH_REMATCH[1]}"
    DB_PASS="${BASH_REMATCH[2]}"
    DB_HOST="${BASH_REMATCH[3]}"
    DB_PORT="${BASH_REMATCH[4]}"
    DB_NAME="${BASH_REMATCH[5]}"

    PGPASSWORD="${DB_PASS}" pg_dump -Fc --no-acl --no-owner -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}" > "${BACKUP_FILE}"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup completed successfully. File: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"
else
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Non-PostgreSQL or local environment detected. Creating SQLite file snapshot if present..."
    if [ -f "db.sqlite3" ]; then
        cp db.sqlite3 "${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"
        echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] SQLite snapshot saved to ${BACKUP_DIR}/db_${TIMESTAMP}.sqlite3"
    fi
fi
