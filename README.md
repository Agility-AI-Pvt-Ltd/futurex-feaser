# Futurex Feaser

Merged FastAPI backend for the Future X product. This repo serves two independent workflows from one unified API and database architecture:

1. **Startup Feasibility Analysis**: AI-powered web research, analysis, and follow-up QA.
2. **ClassCatchup AI (Lecture Flow)**: Upload lecture transcripts and ask questions grounded exclusively in the transcript context.

Both flows are securely isolated into separate PostgreSQL table namespaces, maintaining clean data boundaries while leveraging a shared backend engine.

---

## 🚀 Key Features & Runtime Behavior

### 1. Feasibility Flow
- **Idea Analysis**: The user submits a startup idea via `POST /api/chat`. The LangGraph AI checks if the idea is actionable or too vague. If actionable, it returns a clarifying question.
- **Deep Research**: The second `POST /api/chat` call triggers an automated web scraping job to research competitors, market fit, and opportunities. A comprehensive JSON report is generated and persisted.
- **Scraping Limits**: `AuthorDailyUsage` enforces limits on how many times a user can trigger full web scrapes per day (to control costs).
- **Interactive QA**: Follow-up questions via `POST /api/qa` are answered by querying the saved feasibility report and searching the cached web research using local Qdrant. 
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

# LLM
OPENAI_API_KEY=sk-...
OPENAI_MODEL_NAME=gpt-4o-mini

# Feasibility Settings
SCRAPE_DAILY_LIMIT=2
NOISE_REMOVER_ENABLED=true
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=BAAI/bge-small-en-v1.5
RAG_LOG_CHUNK_CHARS=400
QDRANT_COLLECTION_NAME=transcripts

# Lecture Settings
LECTURE_TRANSCRIPT_STORAGE_PATH=transcripts_data
LECTURE_QDRANT_COLLECTION_NAME=lecture_transcripts
LECTURE_QDRANT_PATH=lecture_qdrant
LECTURE_EMBEDDING_MODEL=all-MiniLM-L6-v2
LECTURE_VECTOR_SIZE=384

# Optimization
PRELOAD_RAG_ON_STARTUP=false

# Observability
AXIOM_TOKEN=...
AXIOM_DATASET=...
```

*Note: Axiom is integrated to provide remote observability and telemetry for both web scraping operations and RAG vector retrieval metrics.*

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

3. **Start the backend:**
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

### CI/CD
A GitHub Actions workflow (`.github/workflows/ci-cd.yml`) handles deployments:
- Builds the Docker image.
- Runs a smoke-test container on port `7860`.
- Deploys directly to EC2 on `push` to the `main` branch.

---

## 📚 Related Documentation
- `DOCUMENTATION.md`: Frontend/backend integration notes, focusing on the Feasibility flow.

## License
MIT
