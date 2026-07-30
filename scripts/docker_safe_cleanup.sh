#!/usr/bin/env bash
set -Eeuo pipefail

BUILDER_UNTIL="${DOCKER_CLEANUP_BUILDER_UNTIL:-30m}"
IMAGE_UNTIL="${DOCKER_CLEANUP_IMAGE_UNTIL:-24h}"
CONTAINER_UNTIL="${DOCKER_CLEANUP_CONTAINER_UNTIL:-1h}"
LOG_MAX_SIZE="${DOCKER_CLEANUP_LOG_MAX_SIZE:-100M}"

echo "[$(date -Is)] docker cleanup started"

docker builder prune -af --filter "until=${BUILDER_UNTIL}"
docker image prune -af --filter "until=${IMAGE_UNTIL}"
docker container prune -f --filter "until=${CONTAINER_UNTIL}"

if [ -d /var/lib/docker/containers ]; then
  find /var/lib/docker/containers \
    -name '*-json.log' \
    -size +"${LOG_MAX_SIZE}" \
    -exec truncate -s 0 {} \;
fi

docker system df

echo "[$(date -Is)] docker cleanup finished"
