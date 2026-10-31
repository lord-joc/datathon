#!/bin/sh
# Daily database backup on the server (NF09): keeps the newest 7 dumps in /var/backups/prostoriq.
# cron (as root): 30 3 * * * cd /opt/prostoriq && sh scripts/backup.sh >> /var/log/prostoriq-backup.log 2>&1
# Copy the folder off the server as well; a backup on the same disk is not a backup.
set -eu

dir="${BACKUP_DIR:-/var/backups/prostoriq}"
mkdir -p "$dir"
chmod 700 "$dir"
export COMPOSE_FILE="compose.yaml:compose.prod.yaml"
sh scripts/db-export.sh "$dir/prostoriq-$(date -u +%Y%m%dT%H%MZ).dump"
ls -1t "$dir"/prostoriq-*.dump | tail -n +8 | xargs -r rm -f
