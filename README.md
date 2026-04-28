# Futurex Feaser

AI-powered startup feasibility analysis backend built with FastAPI, LangGraph, PostgreSQL, live web research, optional semantic filtering, and local Qdrant-backed retrieval for post-report Q&A.

## Overview

This service runs a stateful two-phase startup analysis workflow:

1. A first `POST /api/chat` call collects the idea and returns one clarifying question.
2. A second `POST /api/chat` call uses the same `conversation_id`, performs live research, generates a feasibility report, persists it, and prepares retrieval context for later Q&A.
3. `POST /api/qa` lets the user ask follow-up questions grounded in the saved report and scraped context.

The backend stores long-lived state in PostgreSQL and retrieval chunks in a local Qdrant collection under `qdrant_data/`.

## Current Capabilities

- Stateful conversation flow backed by PostgreSQL
- LangGraph-based orchestration for both analysis and QA
- LLM-generated targeted search queries
- DuckDuckGo search plus a dedicated Reddit search lane
- Web crawling and content extraction with `crawl4ai`
- Junk-page filtering and URL deduplication
- Optional semantic chunk filtering with `sentence-transformers`
- Structured feasibility report persisted both raw and parsed
- Local Qdrant retrieval for follow-up Q&A
- Sliding-window QA memory with rolling summary compression
- HTTP request/response and SQL query logging
- Optional Axiom log export
- Postgres-backed per-author daily scrape quota

## Runtime Flow

### First `POST /api/chat`

- Request does not include `conversation_id`
- Backend creates a new UUID conversation
- LangGraph routes to `cross_question_node`
- LLM returns exactly one clarifying question in `analysis`
- Response includes the new `conversation_id`

This call does not trigger scraping.

### Second `POST /api/chat`

- Request reuses the same `conversation_id`
- Backend reloads prior conversation context from Postgres
- Backend enforces the daily scrape quota for the effective author
- LangGraph routes through:
  - `modify_query_node`
  - `web_research_node`
  - `llm_agent_node`
- Search results and final report are persisted
- Parsed report fields are upserted into `feasibility_reports`
- Embedding runs in the background for later QA

This is the call that consumes daily scrape usage.

### `POST /api/qa`

- Loads saved `analysis`, `search_results`, `qa_history`, and `qa_summary`
- Runs a dedicated QA graph
- Rewrites the user’s question into a retrieval-friendly query
- Retrieves chunks from Qdrant filtered by `conversation_id`
- Falls back to persisted report text and scraped text if retrieval is empty
- Persists the new QA turn and any updated rolling summary

## LangGraph Design

### Main analysis graph

```text
START
  -> load_context
  -> route_chat
     -> cross_question -> END
     -> modify_query -> web_research -> analyzer -> END
```

### QA graph

```text
START
  -> qa_load_state
  -> qa_memory
  -> qa_modify_query
  -> qa_retrieve_context
  -> qa_generate_answer
  -> END
```

## Repository Structure

```text
futurex-feaser/
├── api/
│   ├── __init__.py
│   ├── dependencies.py
│   └── routes.py
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── llm_factory.py
│   ├── logging.py
│   ├── rate_limiter.py
│   └── scrape_usage.py
├── models/
│   ├── __init__.py
│   └── conversation.py
├── noiseremover/
│   ├── __init__.py
│   └── chunk_filter.py
├── pipeline/
│   ├── __init__.py
│   ├── graph.py
│   ├── qa_graph.py
│   ├── state.py
│   ├── tools.py
│   └── prompts/
│       ├── __init__.py
│       ├── cross_question.py
│       ├── feasibility.py
│       └── qa.py
├── rag/
│   ├── __init__.py
│   ├── embedder.py
│   └── retriever.py
├── scraper/
│   ├── __init__.py
│   └── web.py
├── sandbox/
│   ├── draw_graph.py
│   ├── langgraph_flow.png
│   └── test_qa_rag.py
├── log/
│   └── noise_remover.log
├── qdrant_data/
├── .env.example
├── Dockerfile
├── DOCUMENTATION.md
├── app.py
├── main.py
├── qa_summary.py
└── requirements.txt
```

## Important Files

- [app.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/app.py): FastAPI app, lifespan, CORS, health check, HTTP logging, uvicorn entrypoint.
- [api/routes.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/api/routes.py): API routes, DB persistence, scrape-limit enforcement, QA persistence.
- [pipeline/tools.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/pipeline/tools.py): main graph nodes for clarifying question, query generation, research, and analysis.
- [pipeline/qa_graph.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/pipeline/qa_graph.py): QA graph, retrieval, memory windowing, and trace generation.
- [scraper/web.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/scraper/web.py): DDGS search, crawl pipeline, filtering, semantic noise-remover integration.
- [rag/embedder.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/rag/embedder.py): local Qdrant init, chunking, embedding, upsert.
- [rag/retriever.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/rag/retriever.py): chunk-count lookup and similarity search by `conversation_id`.
- [models/conversation.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/models/conversation.py): SQLAlchemy models.
- [core/logging.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/core/logging.py): console logging, SQL logging, optional Axiom sink.

## Database Schema

### `chat_sessions`

Stores all human/AI turns and the main idea context.

Key fields:
- `authorId`
- `conversation_id`
- `idea`
- `what_problem_it_solves`
- `ideal_customer`
- `human_message`
- `ai_message`
- `timestamp`

### `agent_states`

Stores the durable agent state for a conversation.

Key fields:
- `conversation_id`
- `optimized_query`
- `search_results`
- `analysis`
- `qa_history`
- `qa_summary`

### `feasibility_reports`

Stores the parsed structured report fields extracted from `analysis`.

Key fields:
- `conversation_id`
- `chain_of_thought`
- `idea_fit`
- `competitors`
- `opportunity`
- `score`
- `targeting`
- `next_step`

### `author_daily_usage`

Tracks scrape-triggering usage by author and UTC day.

Key fields:
- `author_id`
- `usage_date`
- `scrape_requests_count`

## API Endpoints

### `GET /`

Health check.

Example response:

```json
{
  "status": "ok",
  "message": "Feasibility Check API is running"
}
```

### `POST /api/chat`

Request body:

```json
{
  "idea": "AI companion for early depression screening",
  "user_name": "Krishna",
  "ideal_customer": "young adults and college students",
  "problem_solved": "helps identify mental health risk early",
  "authorId": "user_123",
  "conversation_id": null
}
```

Behavior:
- first call returns a clarifying question
- second call returns the final report JSON string in `analysis`

Example response on first call:

```json
{
  "response": "Researching your idea...",
  "conversation_id": "46bf4e97-cd77-414d-a34f-066f677fdc71",
  "analysis": "What specific user behavior or signal would the system use to identify someone at risk?"
}
```

Example response on second call:

```json
{
  "response": "Analysis Complete",
  "conversation_id": "46bf4e97-cd77-414d-a34f-066f677fdc71",
  "analysis": "{\"chain_of_thought\":[...],\"idea_fit\":\"...\"}"
}
```

### `POST /api/qa`

Request body:

```json
{
  "conversation_id": "46bf4e97-cd77-414d-a34f-066f677fdc71",
  "question": "Which competitors are closest to this idea?"
}
```

Example response:

```json
{
  "answer": "The closest competitors appear to be ...",
  "top_chunks": [
    {
      "source": "web_research",
      "text": "Retrieved supporting text...",
      "score": 0.82
    }
  ],
  "trace": []
}
```

### `GET /api/history`

Query param:
- `author_id`

Returns one row per conversation for the history sidebar.

### `GET /api/history/{conversation_id}`

Returns saved report state and QA history for one conversation.

### `GET /api/qa/graph`

Returns a Mermaid graph string for the QA flow.

## Scrape Quota

The backend enforces a Postgres-backed quota for scrape-triggering follow-up analysis calls.

- controlled by `SCRAPE_DAILY_LIMIT`
- default is `2`
- keyed by `authorId`
- counted only when the request is a non-new `/api/chat` run
- reset boundary is UTC midnight
- overflow returns `429` with `Retry-After`

Important detail:
- for an existing conversation, the backend uses the stored conversation author, not just the incoming request body, to avoid quota bypass by changing `authorId`

## Retrieval and Memory Behavior

### Qdrant retrieval

- chunks are stored in the `feasibility_context` collection
- each point payload includes:
  - `conversation_id`
  - `source`
  - `text`
- retrieval is filtered by `conversation_id`

### QA memory

- full QA history is stored in Postgres
- last `7` turns are kept verbatim in prompt context
- once total QA turns exceed `14`, older turns are compressed into `qa_summary`
- the QA route persists the updated full history after each answer

### Fallback path

If vector retrieval returns no chunks, the QA graph falls back to:
- persisted `analysis`
- persisted `search_results`

## Crawling and Content Processing

The crawler pipeline currently uses `ddgs` and `crawl4ai`.

General behavior:
- DDGS returns up to `10` results per query
- general search results are filtered and capped to `6` per query
- Reddit results are searched separately and intentionally kept
- URLs are deduplicated before crawl
- links are stripped from crawled markdown before extraction
- `extract_core()` keeps the first 30 meaningful lines and caps output to 1500 chars
- `is_useful_content()` removes short or junk pages such as login walls, CAPTCHA pages, and timeouts

### Blocked or filtered domains

General-query results filter out:
- `reddit.com`
- `quora.com`
- `zhihu.com`

Reddit still appears through the dedicated Reddit search lane.

## Optional Noise Remover

If `NOISE_REMOVER_ENABLED=true`, the crawler sends extracted chunks through a semantic filter:

- model defaults to `BAAI/bge-small-en-v1.5`
- threshold defaults to `0.4`
- seed text is built from the idea, problem statement, and generated search queries
- chunk decisions are logged to `log/noise_remover.log`

The noise remover is optional. If it fails, crawling continues with unfiltered content.

## Logging and Observability

### HTTP logging

Configured in [app.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/app.py):
- request method, path, query, headers, and body
- response status, duration, headers, and body
- sensitive headers such as `authorization`, `cookie`, and `x-api-key` are redacted

### SQL logging

Configured in [core/logging.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/core/logging.py):
- statement
- parameters
- duration
- row count
- query errors

### File logs

- `scraper.log`: crawler and search activity
- `log/noise_remover.log`: semantic filter keep/drop decisions

### Axiom

If both `AXIOM_TOKEN` and `AXIOM_DATASET` are set and `axiom-py` is installed, logs are also shipped to Axiom.

## Environment Variables

Use `.env.example` as the starting point, then add the optional settings below as needed.

### Core runtime

```env
APP_TITLE="Feasibility Analysis API"
APP_HOST="0.0.0.0"
APP_PORT=8000
POSTGRES_URL="postgresql://user:password@hostname:5432/dbname?sslmode=require"
OPENAI_API_KEY="sk-..."
ALLOWED_ORIGINS="http://localhost:3000,http://127.0.0.1:3000"
SCRAPE_DAILY_LIMIT=2
```

### RAG and model-loading

```env
PRELOAD_RAG_ON_STARTUP=false
EMBEDDING_MODEL_NAME=BAAI/bge-small-en-v1.5
EMBEDDING_LOCAL_FILES_ONLY=false
```

### Noise remover

```env
NOISE_REMOVER_ENABLED=false
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=BAAI/bge-small-en-v1.5
```

### Logging

```env
AXIOM_TOKEN=
AXIOM_DATASET=
```

### Present in config but not active on the main runtime path

These variables exist in `core/config.py` or `.env.example`, but the current main scraping flow does not depend on them:

```env
GOOGLE_API_KEY=
GOOGLE_CSE_ID=
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
LLM_RATE_LIMIT_REQUESTS=10
LLM_RATE_LIMIT_WINDOW_SECONDS=60
```

Notes:
- current search is done through `ddgs`, not Google Custom Search
- current Reddit discovery is via search query + crawl, not the Reddit API
- `core/rate_limiter.py` exists but is not currently enforced by the API routes

## Local Setup

### 1. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create your `.env`

```bash
cp .env.example .env
```

Then add your real credentials and optional flags.

### 4. Start the API

```bash
python3 app.py
```

You can also run:

```bash
python3 main.py
```

The app binds using:
1. `PORT`
2. `APP_PORT`
3. config default

Database initialization runs automatically during startup.

## Docker

The included [Dockerfile](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/Dockerfile):

- uses `python:3.11-slim`
- installs Python dependencies
- installs Playwright Chromium dependencies
- exposes port `7860`
- starts `uvicorn app:app --host 0.0.0.0 --port 7860`

Build and run locally:

```bash
docker build -t futurex-app .
docker run -p 7860:7860 futurex-app
```

## CI/CD

GitHub Actions workflow: [.github/workflows/ci-cd.yml](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/.github/workflows/ci-cd.yml)

Current pipeline:
- builds the Docker image on pushes and PRs to `main`
- runs a smoke-test container on port `7860`
- on push to `main`, deploys to EC2 over SSH
- deployment script rebuilds the Docker image and restarts the `futurex` container

Important deployment note:
- the EC2 deployment currently does a hard reset to `origin/main` on the server

## Diagnostics and Utilities

### QA RAG diagnostic

[sandbox/test_qa_rag.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/sandbox/test_qa_rag.py) can inspect retrieval and optionally run the full QA graph:

```bash
python3 sandbox/test_qa_rag.py \
  --conversation-id <conversation_id> \
  --question "Who are the main competitors?" \
  --retrieval-query "main competitors for this startup idea"
```

With full graph:

```bash
python3 sandbox/test_qa_rag.py \
  --conversation-id <conversation_id> \
  --question "Who are the main competitors?" \
  --retrieval-query "main competitors for this startup idea" \
  --full-graph
```

### Graph export helper

[sandbox/draw_graph.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/sandbox/draw_graph.py) generates a Mermaid PNG for the main LangGraph flow.

### Legacy migration helper

[qa_summary.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/qa_summary.py) is a small ad hoc SQL helper for adding `qa_summary` to `agent_states`. It is not part of the normal runtime.

## Known Implementation Notes

- CORS is effectively wide open in `app.py` right now via `allow_origins=["*"]`.
- `ALLOWED_ORIGINS` exists in settings but is not currently wired into `CORSMiddleware`.
- `EMBEDDING_LOCAL_FILES_ONLY` is defined in `rag/embedder.py` but is not currently passed into the embedder constructor.
- `core/rate_limiter.py` remains in the repo as legacy logic, while the active scrape quota is implemented in `core/scrape_usage.py`.
- `DOCUMENTATION.md` is the frontend-oriented integration guide; this README is the broader backend/project guide.

## Related Docs

- Backend/frontend integration guide: [DOCUMENTATION.md](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/DOCUMENTATION.md)

## License

MIT
