#!/bin/bash
# SMScores Backup Script
# Backs up: PostgreSQL database + app.py
# Keeps last 4 backups with rotation
# Usage: sudo /opt/smscores/backup.sh

set -e

BACKUP_DIR="/opt/smscores/backups"
APP_DIR="/opt/smscores"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_NAME="smscores-backup-${TIMESTAMP}"
TEMP_DIR="/tmp/${BACKUP_NAME}"
KEEP_COUNT=4

echo "=== SMScores Backup: ${TIMESTAMP} ==="

# Create backup directories
mkdir -p "${BACKUP_DIR}"
mkdir -p "${TEMP_DIR}"

# 1. Database dump
echo "Dumping PostgreSQL database..."
PGPASSWORD="smscores123" pg_dump -U smscores -h localhost smscores > "${TEMP_DIR}/database.sql"
echo "  Database dump: $(wc -l < "${TEMP_DIR}/database.sql") lines"

# 2. App code
echo "Backing up app.py..."
cp "${APP_DIR}/app.py" "${TEMP_DIR}/app.py"

# Bundle into tar.gz
echo "Creating archive..."
tar -czf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" -C /tmp "${BACKUP_NAME}"

# Update latest symlink
ln -sf "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" "${BACKUP_DIR}/latest.tar.gz"

# Cleanup temp
rm -rf "${TEMP_DIR}"

# Rotate — keep only the last 4 backups
echo "Rotating old backups (keeping last ${KEEP_COUNT})..."
ls -t "${BACKUP_DIR}"/smscores-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_COUNT + 1)) | xargs -r rm

# Summary
BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_NAME}.tar.gz" | cut -f1)
BACKUP_COUNT=$(ls "${BACKUP_DIR}"/smscores-backup-*.tar.gz 2>/dev/null | wc -l)
echo ""
echo "=== Backup Complete ==="
echo "  File: ${BACKUP_DIR}/${BACKUP_NAME}.tar.gz"
echo "  Size: ${BACKUP_SIZE}"
echo "  Total backups: ${BACKUP_COUNT}"
echo ""
echo "To download: scp root@134.199.153.50:${BACKUP_DIR}/latest.tar.gz ./"
