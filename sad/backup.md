# Qdrant Backup Snapshot Flow

## Overview

The backup system is a separate sidecar container that talks to the same Qdrant node the app uses.

In `docker-compose.yml`, there are three services:

- `qdrant`: the actual vector database, with storage mounted at `/qdrant/storage`
- `futurex`: the app, configured to talk to Qdrant at `http://qdrant:6333`
- `qdrant-backup`: the backup worker, also talking to `http://qdrant:6333`

That means both the app and the backup job point at the same Qdrant container, not two different databases.

## Runtime Flow

The backup image is built from `backup/Dockerfile`.

It installs only the tools needed for backup:

- `curl` to call Qdrant's HTTP API
- `jq` to parse JSON
- `gzip` to compress
- `aws-cli` to upload to GCS through the S3-compatible endpoint
- `bash` to run the scripts

When the `qdrant-backup` container starts, `backup/entrypoint.sh` runs.

Its job is:

1. Read `BACKUP_CRON` from env, default `0 2 * * *`
2. Optionally run one backup immediately if `RUN_BACKUP_ON_STARTUP=true`
3. Write a cron entry that runs `/backup/backup.sh`
4. Start `crond` in the foreground so the container stays alive

So the sidecar mostly sits idle, waiting for cron.

## What backup.sh Does

The real backup logic is in `backup/backup.sh`.

Step by step:

1. It reads config:
   - `QDRANT_URL`
   - `GCS_BUCKET_NAME`
   - `GCS_BACKUP_PREFIX`
   - `GCS_ACCESS_KEY_ID`
   - `GCS_SECRET_ACCESS_KEY`

2. It maps the GCS HMAC keys into standard AWS env vars:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

This works because GCS exposes an S3-compatible API endpoint for HMAC auth.

3. It creates a timestamp and temp backup directory.

4. It calls Qdrant's full-node snapshot endpoint:

```bash
POST http://qdrant:6333/snapshots
```

This is important: it is not backing up one collection. It asks Qdrant to create a snapshot of the whole node.

5. Qdrant responds with a snapshot name. The script extracts it with `jq`.

6. It downloads that snapshot file from:

```bash
GET http://qdrant:6333/snapshots/<snapshot-name>
```

7. It compresses the downloaded file with `gzip`.

8. It uploads the compressed file to GCS using:

```bash
aws s3 cp ... --endpoint-url=https://storage.googleapis.com
```

9. It deletes the local temp `.gz` file after upload.

So the backup lifecycle is:

```text
Qdrant creates snapshot
-> backup container downloads snapshot
-> compresses it
-> uploads to GCS
-> removes local temp file
```

## Why This Backs Up Everything

Because the script uses:

```text
/snapshots
```

instead of:

```text
/collections/<collection>/snapshots
```

it captures the whole Qdrant node, including:

- all collections
- vectors
- payloads
- metadata
- indexes

## Environment Variables

The expected backup env vars are documented in `.env.example`:

- `GCS_BUCKET_NAME`
- `GCS_ACCESS_KEY_ID`
- `GCS_SECRET_ACCESS_KEY`
- `GCS_BACKUP_PREFIX`
- `BACKUP_CRON`
- `RUN_BACKUP_ON_STARTUP`

Compose passes only the backup-related ones into `qdrant-backup` in `docker-compose.yml`.

## Deployment Flow

The existing deploy job already runs:

```bash
docker compose up -d --build --remove-orphans
```

So once this stack is deployed, the backup sidecar comes up automatically with the app and Qdrant. No manual SSH steps are needed beyond the normal deploy flow already in place.

## End-to-End Summary

The complete flow is:

```text
CI/CD deploys docker-compose
-> qdrant starts
-> futurex app connects to qdrant
-> qdrant-backup sidecar starts
-> entrypoint schedules cron
-> cron runs backup.sh
-> backup.sh calls Qdrant /snapshots
-> snapshot is downloaded
-> snapshot is gzipped
-> gzipped snapshot is uploaded to GCS
-> temp file is deleted
```
