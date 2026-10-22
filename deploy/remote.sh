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

dc build --pull
dc up -d mysql redis
echo "waiting for mysql"
for _ in $(seq 1 60); do
  [ "$(sudo docker inspect -f '{{.State.Health.Status}}' "$(dc ps -q mysql)")" = healthy ] && break
  sleep 2
done
dc run --rm api alembic upgrade head
dc up -d --remove-orphans
dc exec -T nginx nginx -s reload  # pick up nginx.conf changes; a bind-mounted file doesn't recreate the container
sudo docker image prune -f >/dev/null

echo "health check"
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1/healthz; then echo; dc ps; exit 0; fi
  sleep 2
done
echo "API did not come up"; dc logs --tail 50 api; exit 1
