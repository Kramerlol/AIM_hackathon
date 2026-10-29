#!/usr/bin/env bash
# Starts Synapse + Element + Mailpit, creates the users and an UNENCRYPTED room, prints the env for the app.
set -euo pipefail
cd "$(dirname "$0")"
PY=../../.venv/bin/python
HOFER_PASSWORD=${HOFER_PASSWORD:-hofer-dev-password}
BOT_PASSWORD=${BOT_PASSWORD:-bot-dev-password}

if [ ! -f synapse-data/homeserver.yaml ]; then
  mkdir -p synapse-data
  docker run --rm -v "$PWD/synapse-data:/data" -e SYNAPSE_SERVER_NAME=klinikum.example \
    -e SYNAPSE_REPORT_STATS=no matrixdotorg/synapse:latest generate
fi
if ! grep -q "dev only" synapse-data/homeserver.yaml; then
  # the data folder belongs to the container's user, so append from inside a container
  docker run --rm -i -v "$PWD/synapse-data:/data" --entrypoint sh matrixdotorg/synapse:latest \
    -c 'cat >> /data/homeserver.yaml' <<'YAML'

# dev only: no federation, relaxed rate limits so tests do not hit 429
federation_domain_whitelist: []
rc_message: {per_second: 100, burst_count: 100}
rc_login:
  address: {per_second: 100, burst_count: 100}
  account: {per_second: 100, burst_count: 100}
  failed_attempts: {per_second: 100, burst_count: 100}
YAML
fi

docker compose up -d
echo -n "Waiting for Synapse"
until curl -sf localhost:8008/_matrix/client/versions >/dev/null; do echo -n .; sleep 2; done; echo

register() {
  docker compose exec -T synapse register_new_matrix_user -u "$1" -p "$2" --no-admin \
    -c /data/homeserver.yaml http://localhost:8008 >/dev/null 2>&1 && echo "created $1" || echo "$1 exists"
}
register lena.hofer "$HOFER_PASSWORD"
register pgk-bot "$BOT_PASSWORD"

ROOM=$($PY make_room.py "$HOFER_PASSWORD")
cat <<ENV

Put this in your shell, then start the app (one worker):
export MATRIX_HOMESERVER=http://localhost:8008
export MATRIX_BOT_USER=@pgk-bot:klinikum.example
export MATRIX_BOT_PASSWORD=$BOT_PASSWORD
export MATRIX_DEFAULT_ROOM=$ROOM
.venv/bin/uvicorn app.main:app

Element: http://localhost:8088  (log in as lena.hofer / $HOFER_PASSWORD, open the room 'PGK requests')
Mailpit: http://localhost:8025
ENV
