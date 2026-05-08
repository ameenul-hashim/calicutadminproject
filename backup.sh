#!/bin/bash
# EduAimsThinker Database Backup Script
# Run this manually or schedule via cron
# Example cron: 0 2 * * * /path/to/backup.sh >> /var/log/db_backup.log 2>&1

echo "Starting EduAimsThinker database backup..."

# Ensure DATABASE_URL is set, or source it from .env
if [ -z "$DATABASE_URL" ]; then
    echo "Warning: DATABASE_URL not found in environment."
    if [ -f ".env" ]; then
        echo "Sourcing from .env file..."
        export $(grep -v '^#' .env | xargs)
    fi
fi

if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL is not set. Backup failed."
    exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="backup_${TIMESTAMP}.sql"

echo "Dumping database to $BACKUP_FILE..."
pg_dump $DATABASE_URL > $BACKUP_FILE

if [ $? -eq 0 ]; then
    echo "Backup completed successfully: $BACKUP_FILE"
else
    echo "Backup failed!"
    exit 1
fi
