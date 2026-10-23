#!/usr/bin/env bash
# Runs on the server from ~/mistake-book/deploy (deploy.ps1 uploads the code and calls this).
set -euo pipefail
cd "$(dirname "$0")"

# First deploy: random passwords; WeChat and model keys stay empty for the owner to fill in.
if [ ! -f .env ]; then
  umask 077
  sed -e "s/^MYSQL_ROOT_PASSWORD=.*/MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)/" \
      -e "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$(openssl rand -hex 16)/" \
      -e "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" \
      .env.example > .env
  echo "created deploy/.env with random passwords"
fi

dc() { sudo docker compose "$@"; }

# Optional $1: the freshly uploaded tree (deploy.ps1 passes it); removed on exit.
new="${1:-}"
if [ -n "$new" ]; then
  trap 'rm -rf "$new"' EXIT
  # deploy/web is bind-mounted into nginx: keep the directory, files were overwritten in place;
  # now drop files the new build no longer has (old hashed assets), then empty subdirectories.
  mkdir -p web
  (cd web && find . -type f | while IFS= read -r f; do [ -e "$new/deploy/web/$f" ] || rm -f "$f"; done
   find . -mindepth 1 -depth -type d -empty -delete)
fi

# Validate nginx.conf before touching any container; a bad config aborts the deploy.
sudo docker run --rm -v "$PWD/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t \
  || { echo "nginx.conf is invalid; aborting deploy"; exit 1; }

dc build --pull
dc up -d mysql redis
echo "waiting for mysql"
for _ in $(seq 1 60); do
  [ "$(sudo docker inspect -f '{{.State.Health.Status}}' "$(dc ps -q mysql)")" = healthy ] && break
  sleep 2
done
dc run --rm api alembic upgrade head
dc run --rm api sh -c 'python -m app.knowledge.loader --prune data/knowledge/*.yaml'
dc up -d --remove-orphans
dc exec -T nginx nginx -s reload  # pick up nginx.conf changes; a bind-mounted file doesn't recreate the container
sudo docker image prune -f >/dev/null

echo "health check"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1/healthz; then echo; dc ps; exit 0; fi
  sleep 2
done
echo "API did not come up"; dc logs --tail 50 api; exit 1
