# Futurex Feaser

Merged FastAPI backend for the Future X product. This repo now serves two workflows from one codebase:

- startup feasibility analysis with web research and report QA
- transcript upload plus lecture-grounded chat

The merge keeps one API service, one PostgreSQL database, and separate table namespaces so the two products can coexist safely.

## What This Backend Does

### 1. Feasibility flow

- `POST /api/chat` with the feasibility payload starts a startup analysis
- first call returns a clarifying question
- second call with the same `conversation_id` runs research and generates the report
- `POST /api/qa` answers follow-up questions using saved report state plus Qdrant retrieval

### 2. Lecture flow

- `POST /api/upload` uploads and indexes `.txt` or `.vtt` transcripts
- `POST /api/chat` with the lecture payload runs transcript-grounded chat
- `GET /api/sessions`, `GET /api/transcripts`, and `GET /api/history/{session_id}` support the lecture UI

## Key Merge Rule

Both original projects had a `POST /api/chat` endpoint. In this merged backend, the route is shared and dispatches by request shape:

- feasibility payload:

```json
{
  "idea": "AI therapist for Gen Z",
  "user_name": "Krishna",
  "ideal_customer": "college students",
  "problem_solved": "early mental health screening",
  "authorId": "user_123",
  "conversation_id": null
}
```

- lecture payload:

```json
{
  "session_id": "lecture-session-1",
  "message": "What did the speaker say about recursion?",
  "transcript_id": 12
}
```

This keeps the endpoint path the same while avoiding duplicate APIs.

## Repository Layout

```text
futurex-feaser/
├── api/
├── core/
├── lecturebot/
├── models/
├── noiseremover/
├── pipeline/
├── rag/
├── scraper/
├── sandbox/
├── app.py
├── main.py
├── Dockerfile
├── README.md
└── requirements.txt
```

Important files:

- [app.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/app.py): FastAPI app, startup lifecycle, logging, CORS, boot logic
- [api/routes.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/api/routes.py): merged API routes for both flows
- [models/conversation.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/models/conversation.py): feasibility and lecture SQLAlchemy models
- [pipeline/](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/pipeline): feasibility analysis and QA graphs
- [lecturebot/](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/lecturebot): transcript chat pipeline, local storage, transcript RAG
- [scraper/web.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/scraper/web.py): crawl and extraction logic used by feasibility analysis
- [noiseremover/chunk_filter.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/noiseremover/chunk_filter.py): semantic filter model wrapper

## Database Tables

### Feasibility tables

- `chat_sessions`
- `agent_states`
- `feasibility_reports`
- `author_daily_usage`

### Lecture tables

- `lecture_chat_sessions`
- `lecture_messages`
- `lecture_transcript_assets`
- `lecture_transcript_metadata`

This separation is intentional. Before the merge, both projects had a `chat_sessions` table name collision.

## API Endpoints

### Health

- `GET /`

### Shared chat entrypoint

- `POST /api/chat`

Behavior:

- if the body has `session_id` and `message`, it runs the lecture flow
- otherwise it validates the feasibility payload and runs the startup analysis flow

### Feasibility endpoints

- `POST /api/chat`
- `POST /api/qa`
- `GET /api/history?author_id=<authorId>`
- `GET /api/history/{conversation_id}`
- `GET /api/qa/graph`

### Lecture endpoints

- `POST /api/upload`
- `POST /api/chat`
- `GET /api/sessions`
- `GET /api/transcripts`
- `POST /api/transcripts/{transcript_id}/reprocess`
- `GET /api/history/{session_id}`

## Runtime Behavior

### Feasibility startup analysis

1. First `POST /api/chat` call creates a `conversation_id`
2. The main LangGraph returns a clarifying question in `analysis`
3. Second `POST /api/chat` call with the same `conversation_id` performs web research and generates the final report
4. Report state is persisted to Postgres
5. Report context is embedded to local Qdrant for later QA

### Feasibility QA

- `POST /api/qa` loads saved state from Postgres
- retrieves relevant chunks from local Qdrant filtered by `conversation_id`
- falls back to persisted `analysis` and `search_results` if vector retrieval is empty
- maintains rolling `qa_history` and `qa_summary`

### Lecture chat

- transcripts are uploaded to local disk via [lecturebot/storage.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/lecturebot/storage.py)
- transcript chunks are indexed into a lecture-specific Qdrant collection
- lecture chat loads the relevant transcript chunks and answers from transcript context first

## Model and RAG Preloading

Startup now supports eager model loading:

- if `NOISE_REMOVER_ENABLED=true`, the sentence-transformer used by the noise remover is loaded during server startup
- if `PRELOAD_RAG_ON_STARTUP=true`, the feasibility RAG embedder/Qdrant path is also initialized during startup

That logic lives in [app.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/app.py:39).

## Environment Variables

This repo loads settings from `.env`.

Common variables in active use:

```env
APP_HOST=127.0.0.1
APP_PORT=8888
POSTGRES_URL=postgresql://...
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o-mini
SCRAPE_DAILY_LIMIT=2
NOISE_REMOVER_ENABLED=true
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=BAAI/bge-small-en-v1.5
AXIOM_TOKEN=
AXIOM_DATASET=
QDRANT_COLLECTION_NAME=transcripts
LECTURE_TRANSCRIPT_STORAGE_PATH=transcripts_data
LECTURE_QDRANT_COLLECTION_NAME=lecture_transcripts
LECTURE_QDRANT_PATH=lecture_qdrant
LECTURE_EMBEDDING_MODEL=all-MiniLM-L6-v2
LECTURE_VECTOR_SIZE=384
PRELOAD_RAG_ON_STARTUP=false
```

Notes:

- feasibility RAG currently uses local Qdrant storage under `qdrant_data/`
- lecture RAG uses `LECTURE_QDRANT_PATH`
- lecture transcript files are stored under `LECTURE_TRANSCRIPT_STORAGE_PATH`

## Local Development

### 1. Create and activate venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the backend

```bash
python3 app.py
```

or

```bash
.venv/bin/python app.py
```

By default the local app runs on `http://127.0.0.1:8888`.

## Docker

The current Docker setup in [Dockerfile](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/Dockerfile) exposes port `7860`.

Build and run:

```bash
docker build -t futurex-app .
docker run -p 7860:7860 futurex-app
```

Important note:

- local Python startup defaults to port `8888`
- the Docker image starts Uvicorn on port `7860`

If you want parity between local and Docker, update one side so both use the same port.

## CI/CD

GitHub Actions workflow:

- [ci-cd.yml](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/.github/workflows/ci-cd.yml)

Current pipeline:

- builds the Docker image
- runs a smoke-test container on port `7860`
- deploys to EC2 on push to `main`

Current EC2 deploy behavior:

- fetches latest code
- does `git reset --hard origin/main`
- rebuilds the Docker image
- restarts the `futurex` container

## Known Notes

- CORS in [app.py](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/app.py) is currently wide open with `allow_origins=["*"]`
- feasibility RAG and lecture RAG use different local collections and storage paths
- `GET /api/history/{identifier}` serves two roles:
  - feasibility conversation details when `{identifier}` is a feasibility `conversation_id`
  - lecture message history when `{identifier}` is a lecture `session_id`
- `cookies.txt` exists in the repo root and is currently untracked

## Related Docs

- [DOCUMENTATION.md](/Users/krishnakumar/Desktop/AGILITY/futurex-feaser/DOCUMENTATION.md): frontend/backend integration notes, especially for the feasibility flow

## License

MIT
