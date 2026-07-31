---
title: Futurex Feaser
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

Legacy single-EC2 note: when changing `.env` on an old Docker Compose host, recreate the app container with:

```bash
docker compose up -d --force-recreate futurex
```

Current AWS production uses ECR + EC2 Auto Scaling Group. Change runtime env through the launch template or, preferably, AWS Systems Manager Parameter Store / Secrets Manager, then start an ASG instance refresh.

# Futurex Feaser

Merged FastAPI backend for the Future X product. This repo serves two independent workflows from one unified API and database architecture:

1. **Startup Feasibility Analysis**: AI-powered web research, analysis, and follow-up QA.
2. **ClassCatchup AI (Lecture Flow)**: Upload lecture transcripts and ask questions grounded exclusively in the transcript context.

Both flows are securely isolated into separate PostgreSQL table namespaces, maintaining clean data boundaries while leveraging a shared backend engine.

---

## Current AWS DevOps Architecture

The production deployment has moved from a single EC2 Docker Compose host toward a scalable AWS layout. The app is stateless and runs behind an internet-facing Application Load Balancer. Qdrant has been moved out of the app host and now runs on a separate private EC2 instance behind an internal Network Load Balancer.

```text
Users
  |
  v
Route 53 + ACM HTTPS
  pending / next step
  |
  v
Public Application Load Balancer
futurex-public-alb
DNS: futurex-public-alb-1328654668.ap-south-1.elb.amazonaws.com
  |
  v
Target Group: futurex-app-tg
HTTP :7860
Health check: GET /
Current status: Healthy
  |
  v
EC2 Auto Scaling Group: futurex-app-asg
Min: 1
Desired: 1
Max: 3
  |
  v
FutureX app EC2 instances
Private subnets only
Docker image: 429965675866.dkr.ecr.ap-south-1.amazonaws.com/futurex-app:latest
Container port: 7860
  |
  +--> Neon PostgreSQL
  |    Current production database
  |    Planned migration target: Amazon Aurora PostgreSQL in the same VPC/region
  |
  +--> Upstash Redis
  |    Current Redis provider
  |    Planned migration target: AWS ElastiCache Redis in private subnets
  |
  +--> Internal Qdrant Network Load Balancer
       futurex-qdrant-nlb
       DNS: futurex-qdrant-nlb-cbe793c9289264f0.elb.ap-south-1.amazonaws.com
       TCP :6333
       |
       v
       Qdrant EC2
       futurex-qdrant-1
       Private IP: 10.0.2.93
       Data stored on EBS
```

### AWS Network Layout

```text
VPC: futurex-prod
VPC ID: vpc-0aa0545a814843f78
Region: ap-south-1

Public subnets
  - public-subnet-a: ALB node, NAT Gateway
  - public-subnet-b: ALB node

Private subnets
  - private-subnet-a: app ASG instances
  - private-subnet-b: app ASG instances
  - private-subnet-c: private services / future capacity
```

Only the public ALB is internet-facing. FutureX app instances and Qdrant should stay in private subnets. Current PostgreSQL is Neon and current Redis is Upstash. When migrated to AWS, Aurora PostgreSQL and ElastiCache Redis should also stay in private subnets.

### Security Group Flow

```text
Internet
  |
  | HTTP 80 / HTTPS 443
  v
alb-sg
  |
  | TCP 7860
  v
app-sg
  |
  | TCP 6333
  v
qdrant-nlb-sg
  |
  | TCP 6333
  v
qdrant-sg
  |
  v
Qdrant EC2
```

Current key security group rules:

- `alb-sg`: inbound `80` and future `443` from internet.
- `app-sg`: inbound `7860` from `alb-sg`.
- `app-sg`: optional inbound `22` from `BASTION-SG` for private SSH debugging.
- `qdrant-nlb-sg`: inbound `6333` from `app-sg`.
- `qdrant-sg`: inbound `6333` from `qdrant-nlb-sg`.
- `futurex-db-sg` target: inbound `5432` from `app-sg`, and temporary `5432` from `BASTION-SG` during migration only.

### Current Production Backend URL

Until Route 53 and ACM are added, the public backend URL is:

```text
http://futurex-public-alb-1328654668.ap-south-1.elb.amazonaws.com
```

API docs:

```text
http://futurex-public-alb-1328654668.ap-south-1.elb.amazonaws.com/docs
```

### Deployment Flow

```text
Developer pushes to GitHub main
  |
  v
GitHub Actions
  |
  +-- Build Docker image
  +-- Validate docker-compose config
  +-- Run smoke-test container on port 7860
  +-- Push image to Amazon ECR
      Tags: latest and commit SHA
  |
  v
EC2 Auto Scaling Group instance refresh
  |
  v
New app EC2 pulls image from ECR
  |
  v
Container starts on port 7860
  |
  v
ALB health check passes
```

### Production Runtime Principles

- App instances must be stateless.
- Do not store persistent app data on local EC2 disks.
- Store metadata and chat state in PostgreSQL. Current provider: Neon. Planned AWS target: Aurora PostgreSQL.
- Store cache/rate-limit/session state in Redis. Current provider: Upstash. Planned AWS target: ElastiCache Redis.
- Store vectors only in Qdrant.
- Store transcript/file uploads in S3 when the upload flow is moved off local disk.
- Keep Qdrant data on the dedicated Qdrant EC2/EBS volume.
- Do not run local Qdrant inside each app instance.
- Do not put secrets directly in launch template user data long term; move them to AWS Systems Manager Parameter Store or AWS Secrets Manager.

---

## 🚀 Key Features & Runtime Behavior

### 1. Feasibility Flow
- **Idea Analysis**: The user submits a startup idea via `POST /api/chat`. The LangGraph AI checks if the idea is actionable or too vague. If actionable, it returns a clarifying question.
- **Deep Research**: The second `POST /api/chat` call triggers an automated web scraping job to research competitors, market fit, and opportunities. A comprehensive JSON report is generated and persisted.
- **Scraping Limits**: `AuthorDailyUsage` enforces limits on how many times a user can trigger full web scrapes per day (to control costs).
- **Interactive QA**: Follow-up questions via `POST /api/qa` are answered by querying the saved feasibility report and searching the cached web research using Qdrant.
- **Memory Management**: The `AgentStateModel` tracks `qa_history` and maintains an LLM-generated rolling `qa_summary` to prevent context overflow in long Q&A sessions.

### 2. ClassCatchup AI (Lecture Flow)
- **Transcript Ingestion**: `POST /api/upload` handles `.txt` or `.vtt` formats. Transcripts are converted, cleaned, and embedded in chunks into a dedicated Qdrant vector database collection.
- **Multi-Tenant History**: `POST /api/chat` handles lecture questions. It associates each chat session with the user (`author_id`) and the specific transcript (`transcript_id`), enabling seamless persistence.
- **Resumable UI**: Users can fetch their past conversations via `GET /api/sessions?author_id=...` and seamlessly resume asking questions about an older transcript.
- **Metadata Management**: `PATCH /api/transcripts/{transcript_id}` allows users to update course, instructor, and description details after the initial upload.
- **Re-Processing**: `POST /api/transcripts/{transcript_id}/reprocess` enables cleaning and re-indexing the transcript chunks in the vector DB without requiring re-uploading.

---

## 🔌 API Endpoints

### Health & Shared Entrypoint
- `GET /` - Health check.
- `POST /api/chat` - The shared entrypoint. The route dispatches dynamically based on the payload:
  - If `session_id` and `transcript_id` are provided, it routes to **Lecture Chat**.
  - If `idea`, `user_name`, and `authorId` are provided, it routes to **Feasibility Analysis**.

### Feasibility Endpoints
- `POST /api/chat` (Feasibility payload)
- `POST /api/qa` (Follow-up questions)
- `GET /api/score/{conversation_id}` (Read the stored `feasibility_reports.score` value)
- `GET /api/history?author_id=<authorId>` (List past startup analyses)
- `GET /api/history/{conversation_id}` (Fetch specific analysis details)
- `GET /api/qa/graph` (Returns Mermaid chart of the LangGraph QA architecture)

### ClassCatchup Endpoints
- `POST /api/upload` (Upload and embed transcripts)
- `POST /api/chat` (Lecture payload)
- `GET /api/sessions?author_id=<author_id>` (List persistent user chat sessions)
- `GET /api/history/{session_id}` (Fetch messages for a specific session)
- `GET /api/transcripts` (List all available transcripts)
- `PATCH /api/transcripts/{transcript_id}` (Update transcript metadata)
- `POST /api/transcripts/{transcript_id}/reprocess` (Re-index an existing transcript)

---

## 🗄️ Database Schema

### Feasibility Tables
- `chat_sessions` (Raw message logs)
- `agent_states` (LangGraph state persistence, `qa_history`, and `qa_summary`)
- `feasibility_reports` (Final JSON report output)
- `author_daily_usage` (Rate limiting for web scraping)

### Lecture Tables
- `lecture_chat_sessions` (Tracks `author_id` and `transcript_id` to link users to content)
- `lecture_messages` (Chat messages)
- `lecture_transcript_assets` (File metadata and Qdrant chunk count)
- `lecture_transcript_metadata` (Editable metadata like course name and instructor)

---

## ⚙️ Environment Variables

The backend relies on the `.env` file for configuration. Notable variables include:

```env
# Server
APP_HOST=127.0.0.1
APP_PORT=8888

# Database
POSTGRES_URL=postgresql://...

# Redis
REDIS_ENABLED=false
REDIS_REQUIRED=false
REDIS_MAX_CONNECTIONS=20
REDIS_POOL_TIMEOUT_SECONDS=5
REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=3
REDIS_SOCKET_TIMEOUT_SECONDS=3
REDIS_HEALTH_CHECK_INTERVAL_SECONDS=30

# LLM
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o-mini

# Feasibility Settings
SCRAPE_DAILY_LIMIT=2
NOISE_REMOVER_ENABLED=false
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=BAAI/bge-small-en-v1.5
FASTEMBED_CACHE_DIR=/data/cache/fastembed
FASTEMBED_FALLBACK_CACHE_DIR=fastembed_cache
RAG_LOG_CHUNK_CHARS=400

# Production app instances should use the internal Qdrant NLB URL.
QDRANT_BACKEND=remote
QDRANT_URL=http://futurex-qdrant-nlb-cbe793c9289264f0.elb.ap-south-1.amazonaws.com:6333

# Optional only when using Qdrant Cloud.
# QDRANT_API_KEY=
# QDRANT_CLOUD_URL=
# QDRANT_CLOUD_API_KEY=

# Lecture Settings
LECTURE_TRANSCRIPT_STORAGE_PATH=transcripts_data
LECTURE_QDRANT_COLLECTION_NAME=lecture_transcripts
LECTURE_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
LECTURE_VECTOR_SIZE=384

# Optimization
PRELOAD_RAG_ON_STARTUP=false
PRELOAD_NOISE_REMOVER_ON_STARTUP=false

# Observability
AXIOM_TOKEN=...
AXIOM_DATASET=...
```

*Note: Axiom is integrated to provide remote observability and telemetry for both web scraping operations and RAG vector retrieval metrics.*

---

## Qdrant Vector Storage

New Qdrant collections are created with `on_disk=True` in their `VectorParams`. This stores the raw vector data on disk instead of keeping all vectors resident in RAM. The HNSW graph index remains memory-resident, so RAM usage scales mostly with the index graph rather than the full vector matrix.

When `QDRANT_BACKEND=remote`, the app connects only to `QDRANT_URL` or `QDRANT_CLOUD_URL`. `QDRANT_PATH`, `QDRANT_FALLBACK_PATH`, and `LECTURE_QDRANT_PATH` are used only for embedded/local Qdrant mode.

In production, Qdrant is no longer part of the app Docker Compose stack. App instances connect to:

```env
QDRANT_BACKEND=remote
QDRANT_URL=http://futurex-qdrant-nlb-cbe793c9289264f0.elb.ap-south-1.amazonaws.com:6333
```

Example estimate for 100k vectors with 384 dimensions:

- Raw vectors: `100,000 x 384 x 4 bytes = about 153 MB` before Qdrant storage overhead.
- HNSW index: roughly `num_vectors x 50-100 bytes`, so `100k x 100 bytes = about 10 MB`.
- Practical result: much lower RAM pressure, with more data shifted to disk. Exact disk usage depends on Qdrant segment metadata, payload size, and optimizer settings.

This setting applies when a collection is created. Existing Qdrant collections may need to be recreated or updated through Qdrant tooling before they use on-disk vector storage.

---

## Qdrant Backups

This repo supports full-node backups for a self-hosted single-node Qdrant service running in Docker Compose.

Production Qdrant is now on a separate private EC2 instance behind the internal Qdrant NLB. Run Qdrant backup/restore automation from the Qdrant host, not from every app instance in the Auto Scaling Group.

- `qdrant` stores the live vector data
- `qdrant-backup` is a sidecar that runs `cron`
- `backup/backup.sh` calls `POST /snapshots` on the local Qdrant node
- the snapshot is downloaded, gzipped, and uploaded to GCS

Relevant environment variables:

- `GCS_BUCKET_NAME`
- `GCS_ACCESS_KEY_ID`
- `GCS_SECRET_ACCESS_KEY`
- `GCS_BACKUP_PREFIX`
- `BACKUP_CRON`
- `RUN_BACKUP_ON_STARTUP`

The current backup path is for self-hosted/local Qdrant. It is not the same as Qdrant Cloud managed backups.

### Restore From GCS

To restore the latest Qdrant full-node snapshot from GCS back into the local Docker Qdrant volume, run:

```bash
./backup/restore_from_gcs.sh
```

To restore a specific snapshot object instead of the latest one:

```bash
./backup/restore_from_gcs.sh "qdrant/full-node/<snapshot-file>.snapshot.gz"
```

The restore script will:

- find or use the requested snapshot key
- download it from GCS
- extract the `.snapshot`
- stop the running app/Qdrant services
- restore the full Qdrant storage snapshot
- start the normal services again

Important notes:

- This restore flow is intended for a self-hosted single-node Qdrant setup.
- It restores the whole local Qdrant storage state, not just one collection.
- Idea Lab and Lecturebot data are both included if both collections exist in that local Qdrant node.

---

## 🧠 Redis Usage

Redis is optional in this backend, but when `REDIS_ENABLED=true` it is used for the following runtime features:

- **API rate limiting**: All routes on the main API router pass through a shared rate limiter. Redis stores counters under keys like `futurex:api-rate-limit:{identity}`.
- **History response caching**: `GET /api/history?author_id=...` caches paginated conversation history in Redis for 60 seconds using keys like `idealab:history:{author_id}:{offset}:{limit}`.
- **History cache invalidation**: After a feasibility conversation/report is updated, matching `idealab:history:{author_id}:*` cache keys are deleted so the next history fetch is fresh.
- **Startup health check**: On app startup, the backend pings Redis and logs `redis.ping_ok` when the connection is healthy.
- **Connection lifecycle**: A shared async Redis client is created lazily and closed during app shutdown.

Fallback behavior when Redis is unavailable:

- API rate limiting falls back to PostgreSQL.
- History caching is skipped and the endpoint reads directly from PostgreSQL.

If both Redis and PostgreSQL rate-limit backends are unavailable, the request is allowed and a warning is logged instead of using in-process RAM state.

Redis is **not** used for:

- Qdrant / vector search
- Daily scrape usage limits (`AuthorDailyUsage` uses PostgreSQL)

---

## Current PostgreSQL and Redis State

Current production still uses:

```text
PostgreSQL: Neon
Redis: Upstash
```

These are external managed services and are not yet inside the `futurex-prod` VPC.

## Planned AWS PostgreSQL and Redis Target State

The planned database migration is from Neon PostgreSQL to Amazon Aurora PostgreSQL in the same AWS region and VPC as the app.

Recommended target:

```text
FutureX app ASG
  |
  v
RDS Proxy
  |
  v
Amazon Aurora PostgreSQL
VPC: futurex-prod
Region: ap-south-1
Private subnets only
```

Use Aurora PostgreSQL Serverless v2 if the workload is variable and the database should scale capacity automatically. Aurora storage grows automatically; RDS/Aurora compute scaling is not the same as EC2 Auto Scaling. For high connection counts, put RDS Proxy in front of Aurora so app instances do not overwhelm PostgreSQL with direct connections.

Recommended Aurora settings:

- Engine: Amazon Aurora PostgreSQL-Compatible Edition.
- Capacity: Serverless v2.
- Initial min ACU: `0.5` or `1`.
- Initial max ACU: `4`.
- Public access: `No`.
- VPC: `futurex-prod`.
- Security group: `futurex-db-sg`.
- Inbound: PostgreSQL `5432` from `app-sg`.
- Temporary migration inbound: PostgreSQL `5432` from `BASTION-SG`.

After Aurora is created, update production app env:

```env
POSTGRES_URL=postgresql://futurex_admin:PASSWORD@futurex-postgres.cluster-xxxxx.ap-south-1.rds.amazonaws.com:5432/futurex
```

Migration from Neon:

```bash
pg_dump "$NEON_POSTGRES_URL" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file=futurex_neon.dump

pg_restore \
  --dbname="$AURORA_POSTGRES_URL" \
  --no-owner \
  --no-acl \
  --verbose \
  futurex_neon.dump
```

Then verify:

```bash
psql "$AURORA_POSTGRES_URL" -c "\\dt"
```

Current Redis is Upstash. The planned AWS Redis target is AWS ElastiCache Redis in private subnets:

```text
FutureX app ASG
  |
  v
ElastiCache Redis
Private subnets
Security group allows 6379 from app-sg
```

Production Redis env:

```env
REDIS_ENABLED=true
REDIS_REQUIRED=false
REDIS_URL=redis://futurex-redis.xxxxxx.0001.aps1.cache.amazonaws.com:6379
REDIS_MAX_CONNECTIONS=50
REDIS_POOL_TIMEOUT_SECONDS=5
```

---

## 💻 Local Development

1. **Create and activate venv:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run database migrations when schema changes:**
   ```bash
   ./.venv/bin/python -m alembic revision -m "your change"
   ./.venv/bin/python -m alembic upgrade head
   ```
   **Migrations workflow:**
   After pulling new code, run:
   ```bash
   ./.venv/bin/python -m alembic upgrade head
   ```
   Only create a new revision when you are intentionally changing the schema.

4. **Start the backend:**
   ```bash
   python app.py
   ```
   *The local app runs on `http://127.0.0.1:8888` by default.*

---

## 🐳 Docker & CI/CD

### Docker
The current Docker setup in `Dockerfile` exposes port `7860`.
```bash
docker build -t futurex-app .
docker run -p 7860:7860 futurex-app
```
*(Note: Local Python defaults to `8888`, Docker defaults to `7860`)*

Production app instances should run only the FutureX app container. Do not run the `local-qdrant` Docker Compose profile on app ASG instances.

Production deploys install `/usr/local/bin/futurex-docker-safe-cleanup` as a root cron job every 5 minutes. It prunes old Docker build cache, dangling/old unused images, stopped containers, and oversized Docker JSON logs. It does not prune Docker volumes or Qdrant storage.

### CI/CD
A GitHub Actions workflow (`.github/workflows/ci-cd.yml`) handles deployments:
- Builds the Docker image.
- Runs a smoke-test container on port `7860`.
- Pushes the image to Amazon ECR on `push` to the `main` branch.
- Tags each image with both the commit SHA and `latest`.
- Optionally starts an EC2 Auto Scaling Group instance refresh after pushing.

Required GitHub Actions secrets:

```text
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
POSTGRES_URL
OPENAI_API_KEY
```

Optional GitHub Actions repository variable:

```text
APP_ASG_NAME=futurex-app-asg
```

If `APP_ASG_NAME` is not set, the workflow still pushes the image to ECR but skips the Auto Scaling Group refresh.

The app Launch Template should pull:

```text
429965675866.dkr.ecr.ap-south-1.amazonaws.com/futurex-app:latest
```

---

## 📚 Related Documentation
- `DOCUMENTATION.md`: Frontend/backend integration notes, focusing on the Feasibility flow.

## License
MIT
