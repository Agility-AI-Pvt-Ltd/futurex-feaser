#!/usr/bin/env bash

set -euo pipefail

BACKUP_CRON="${BACKUP_CRON:-0 2 * * *}"

chmod +x /backup/backup.sh

if [ "${RUN_BACKUP_ON_STARTUP:-false}" = "true" ]; then
  echo "RUN_BACKUP_ON_STARTUP=true, running an immediate backup..."
  /backup/backup.sh
fi

echo "Scheduling Qdrant full-node backup with cron: $BACKUP_CRON"
printf '%s /backup/backup.sh >> /proc/1/fd/1 2>> /proc/1/fd/2\n' "$BACKUP_CRON" > /etc/crontabs/root

exec crond -f -l 8
