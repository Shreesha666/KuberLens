#!/usr/bin/env bash
# PostgreSQL Automated Restore Script
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <path_to_backup_dump_file>"
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Restoring database from ${BACKUP_FILE}..."

if [[ "${DATABASE_URL:-}" =~ postgresql://([^:]+):([^@]+)@([^:]+):([0-9]+)/(.+) ]]; then
    DB_USER="${BASH_REMATCH[1]}"
    DB_PASS="${BASH_REMATCH[2]}"
    DB_HOST="${BASH_REMATCH[3]}"
    DB_PORT="${BASH_REMATCH[4]}"
    DB_NAME="${BASH_REMATCH[5]}"

    PGPASSWORD="${DB_PASS}" pg_restore --clean --if-exists --no-acl --no-owner -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" "${BACKUP_FILE}"
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] PostgreSQL restoration completed successfully."
else
    echo "Restoration for custom DB formats requires specific driver configuration."
fi
