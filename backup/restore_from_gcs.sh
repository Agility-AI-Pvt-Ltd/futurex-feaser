#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESTORE_DIR="${RESTORE_DIR:-$ROOT_DIR/restore}"
QDRANT_IMAGE="${QDRANT_IMAGE:-qdrant/qdrant:latest}"

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "Missing $ROOT_DIR/.env" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. "$ROOT_DIR/.env"
set +a

if [ -z "${GCS_BUCKET_NAME:-}" ] || [ -z "${GCS_ACCESS_KEY_ID:-}" ] || [ -z "${GCS_SECRET_ACCESS_KEY:-}" ]; then
  echo "GCS_BUCKET_NAME, GCS_ACCESS_KEY_ID, and GCS_SECRET_ACCESS_KEY must be set in .env" >&2
  exit 1
fi

mkdir -p "$RESTORE_DIR"

echo "Building backup helper image if needed..."
docker compose -f "$ROOT_DIR/docker-compose.yml" build qdrant-backup >/dev/null

snapshot_key="${1:-}"
if [ -z "$snapshot_key" ]; then
  echo "Finding latest snapshot in gs://$GCS_BUCKET_NAME/${GCS_BACKUP_PREFIX:-qdrant/full-node}/ ..."
  snapshot_key="$(
    docker compose -f "$ROOT_DIR/docker-compose.yml" run --rm --build --entrypoint bash qdrant-backup -lc \
      "aws s3 ls \"s3://\$GCS_BUCKET_NAME/\$GCS_BACKUP_PREFIX/\" --recursive --endpoint-url=https://storage.googleapis.com | awk '{print \$4}' | sort | tail -n 1"
  )"
  snapshot_key="$(printf '%s' "$snapshot_key" | tr -d '\r' | tail -n 1)"
fi

if [ -z "$snapshot_key" ]; then
  echo "No snapshot key found in GCS." >&2
  exit 1
fi

snapshot_filename="$(basename "$snapshot_key")"
snapshot_gz_path="$RESTORE_DIR/$snapshot_filename"
snapshot_path="$RESTORE_DIR/${snapshot_filename%.gz}"

echo "Ensuring local Qdrant volume exists..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d qdrant >/dev/null
qdrant_volume="$(
  docker inspect qdrant --format '{{range .Mounts}}{{if eq .Destination "/qdrant/storage"}}{{.Name}}{{end}}{{end}}'
)"

if [ -z "$qdrant_volume" ]; then
  echo "Could not determine the Docker volume backing /qdrant/storage." >&2
  exit 1
fi

echo "Stopping app and Qdrant services before restore..."
docker compose -f "$ROOT_DIR/docker-compose.yml" stop futurex qdrant-backup qdrant >/dev/null

echo "Downloading snapshot: gs://$GCS_BUCKET_NAME/$snapshot_key"
docker compose -f "$ROOT_DIR/docker-compose.yml" run --rm --build \
  -v "$RESTORE_DIR:/restore" \
  --entrypoint bash qdrant-backup -lc \
  "aws s3 cp \"s3://\$GCS_BUCKET_NAME/$snapshot_key\" \"/restore/$snapshot_filename\" --endpoint-url=https://storage.googleapis.com"

echo "Extracting snapshot..."
docker compose -f "$ROOT_DIR/docker-compose.yml" run --rm --build \
  -v "$RESTORE_DIR:/restore" \
  --entrypoint bash qdrant-backup -lc \
  "gzip -dkf \"/restore/$snapshot_filename\""

if [ ! -f "$snapshot_path" ]; then
  echo "Expected extracted snapshot not found at $snapshot_path" >&2
  exit 1
fi

echo "Restoring full Qdrant storage snapshot into volume: $qdrant_volume"
docker run --rm \
  --name qdrant-restore \
  -p 6333:6333 \
  -v "$qdrant_volume:/qdrant/storage" \
  -v "$RESTORE_DIR:/qdrant/snapshots" \
  "$QDRANT_IMAGE" \
  ./qdrant --storage-snapshot "/qdrant/snapshots/$(basename "$snapshot_path")"

echo "Starting normal services again..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d qdrant qdrant-backup futurex >/dev/null

echo "Restore complete."
echo "Restored snapshot file: $snapshot_path"
echo "Run this to verify collections:"
echo "curl http://127.0.0.1:6333/collections"
