#!/usr/bin/env bash
# Read-only service backup before an authorized deployment. No credentials leave the server.
set -euo pipefail
umask 077
cd "$HOME/mistake-book/deploy"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="$HOME/mistake-book-backups/$stamp"
mkdir -p "$backup"
chmod 700 "$HOME/mistake-book-backups" "$backup"
tar -czf "$backup/code.tar.gz" -C "$HOME/mistake-book" backend deploy
sudo docker compose exec -T mysql sh -c \
  'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump -uroot --single-transaction --no-tablespaces --routines --events cuotiben' \
  | gzip > "$backup/database.sql.gz"
gzip -t "$backup/database.sql.gz"
tar -tzf "$backup/code.tar.gz" >/dev/null
sudo docker image tag mistake-book-backend "mistake-book-backend:rollback-$stamp"
sudo docker compose ps > "$backup/services.txt"
printf '%s\n' "$backup" > "$HOME/mistake-book-backups/latest"
echo "BACKUP_OK $backup"
