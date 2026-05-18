#!/usr/bin/env bash

set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/backups}"
GCS_BACKUP_PREFIX="${GCS_BACKUP_PREFIX:-qdrant/full-node}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-auto}"

export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-${GCS_ACCESS_KEY_ID:-}}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-${GCS_SECRET_ACCESS_KEY:-}}"
export AWS_DEFAULT_REGION

if [ -z "${GCS_BUCKET_NAME:-}" ]; then
  echo "GCS_BUCKET_NAME is required." >&2
  exit 1
fi

if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
  echo "GCS_ACCESS_KEY_ID/GCS_SECRET_ACCESS_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are required." >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date -u +"%Y-%m-%d-%H-%M-%S")"
AUTH_HEADER=()
if [ -n "${QDRANT_API_KEY:-}" ]; then
  AUTH_HEADER=(-H "api-key: ${QDRANT_API_KEY}")
fi

echo "Creating full-node Qdrant snapshot from ${QDRANT_URL}..."
SNAPSHOT_RESPONSE="$(
  curl -fsS -X POST "${AUTH_HEADER[@]}" \
    "$QDRANT_URL/snapshots"
)"
SNAPSHOT_NAME="$(printf '%s' "$SNAPSHOT_RESPONSE" | jq -r '.result.name')"

if [ -z "$SNAPSHOT_NAME" ] || [ "$SNAPSHOT_NAME" = "null" ]; then
  echo "Could not read snapshot name from Qdrant response:" >&2
  printf '%s\n' "$SNAPSHOT_RESPONSE" >&2
  exit 1
fi

SNAPSHOT_PATH="$BACKUP_DIR/$SNAPSHOT_NAME"
GZIP_PATH="$SNAPSHOT_PATH.gz"
GCS_DESTINATION="s3://$GCS_BUCKET_NAME/$GCS_BACKUP_PREFIX/$TIMESTAMP-$SNAPSHOT_NAME.gz"

echo "Snapshot created: $SNAPSHOT_NAME"
echo "Downloading snapshot..."
curl -fSL "${AUTH_HEADER[@]}" \
  "$QDRANT_URL/snapshots/$SNAPSHOT_NAME" \
  -o "$SNAPSHOT_PATH"

echo "Compressing snapshot..."
gzip -f "$SNAPSHOT_PATH"

echo "Uploading snapshot to GCS: $GCS_DESTINATION"
aws s3 cp \
  "$GZIP_PATH" \
  "$GCS_DESTINATION" \
  --endpoint-url=https://storage.googleapis.com

echo "Cleaning local backup file..."
rm -f "$GZIP_PATH"

echo "Full-node Qdrant backup complete."
