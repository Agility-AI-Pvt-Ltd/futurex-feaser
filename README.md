---
title: Feasibility Check
emoji: 🚀
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# 🚀 Feasibility Check — AI-Powered Startup Idea Analyser

An agentic, multi-step feasibility analysis system that researches your startup idea live on the web, gathers community sentiment from Reddit, and produces a structured JSON report — all powered by a **LangGraph stateful pipeline**, **Groq / OpenAI LLM**, **crawl4ai**, and a **local Qdrant RAG engine**.

![Backend](https://img.shields.io/badge/Backend-FastAPI-009688)
![Pipeline](https://img.shields.io/badge/Pipeline-LangGraph-blueviolet)
![LLM](https://img.shields.io/badge/LLM-Groq%20%2F%20GPT--4o--mini-412991)
![DB](https://img.shields.io/badge/Database-PostgreSQL%20%2F%20Neon-4169E1)
![Vector](https://img.shields.io/badge/VectorDB-Qdrant%20(local)-red)
![Frontend](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB)
![Search](https://img.shields.io/badge/Search-DDGS%20%2B%20crawl4ai-orange)

---

## ✨ Features

| Feature | Description |
|---|---|
| **Stateful Conversations** | Persistent multi-turn chat via PostgreSQL — resume any idea analysis across sessions |
| **LangGraph Pipeline** | Modular, graph-based agent with conditional routing (clarify → research → analyse) |
| **Smart Multi-Query Search** | LLM generates 3 targeted queries (competitors, market, YC-funded) instead of one broad query |
| **Reddit Intelligence** | Dedicated Reddit search lane captures real community opinions and pain points |
| **Content Quality Filtering** | Strips nav/header boilerplate; skips login walls, CAPTCHAs, and timeout pages |
| **Optional Semantic Noise Remover** | Can semantically drop low-relevance scraped chunks using `sentence-transformers`, controlled from `.env` |
| **URL Deduplication** | All URLs from all queries are deduplicated before crawling |
| **Structured JSON Report** | 7-field feasibility report: score, idea fit, competitors, opportunity, targeting, next step, reasoning chain |
| **Local RAG Engine** | Scraped data + report embedded via MiniLM-L6-v2 into a local Qdrant vector store with lazy client initialization |
| **Post-Report QA Chat** | Chat interactively with your report using the RAG Q&A pipeline |
| **QA Sliding-Window Memory** | Last 7 Q&A turns kept verbatim; older turns auto-compressed into a rolling LLM summary |
| **Parallel Background Embedding** | Search results are embedded in a background thread while the LLM analyses concurrently |
| **Safer QA Retrieval** | QA checks persisted chunk availability for the active `conversation_id` before falling back to DB-backed context |
| **Premium Glassmorphic UI** | Dark-mode React app with a 3-step conversational state machine |

---

## 🧠 Main Pipeline — `POST /api/chat`

```
POST /api/chat
     │
     ▼
load_context_node          → history pre-fetched in routes.py; node is a no-op pass-through
     │
     ▼ (router: is_new_chat?)
  YES → cross_question_node    → asks 1 critical clarifying question → END (200 OK)
  NO  → modify_query_node      → LLM generates 3 targeted JSON search queries
              │
              ▼
      web_research_node
        ├── Query 1: "{idea} startup competitors"      → filter_urls (max 6)
        ├── Query 2: "{idea} existing products market" → filter_urls (max 6)
        ├── Query 3: "{idea} Y Combinator funded"      → filter_urls (max 6)
        └── Reddit:  "{q1} site:reddit.com"            → unfiltered (keep reddit URLs)
              │
        crawler_service (async, per URL):
          ├── extract_core()       → first 30 meaningful lines, cap 1500 chars
          └── is_useful_content()  → rejects login walls, timeouts, CAPTCHAs
              │
              └── optional noise remover → semantic keep/drop filter using idea/query seed texts
              │
              ▼
      llm_agent_node
        ├── (Background Thread) search_results → MiniLM-L6-v2 → Qdrant  ← parallel embed
        └── feasibility prompt (general + Reddit context-aware) → LLM → JSON report
              │
              ▼
      PostgreSQL upsert  (ChatSession + AgentStateModel + FeasibilityReport)
      Background Task    (analysis text → Qdrant embed, if not already done inline)
              │
              ▼
      → frontend renders structured report
```

---

## 🤖 QA Pipeline — `POST /api/qa`

Activated after the report is generated. Supports stateful multi-turn conversation.

```
POST /api/qa  { conversation_id, question }
     │
     ▼
routes.py: load full qa_history + qa_summary from AgentStateModel (DB)
     │
     ▼
[qa_load_state_node]   → logs state metadata
     │
     ▼
[qa_memory_node]       ← NEW — sliding-window memory manager
  ├── total turns ≤ 14 → clip to last 7 for prompt context (no LLM call)
  └── total turns > 14 → LLM compresses oldest turns into rolling summary
                          window = last 7 turns; summary updated in state
     │
     ▼
[qa_modify_query_node] → rewrites follow-up question into standalone retrieval query
     │
     ▼
[qa_retrieve_context_node]
  ├── Count persisted Qdrant chunks for the current conversation_id
  ├── If chunks exist → Qdrant vector similarity search (top 5 chunks)
  └── Fallback: persisted analysis + search_results text if no chunks or no vector hits
     │
     ▼
[qa_generate_answer_node]
  └── Prompt includes: summary of old turns + last 7 turns verbatim + RAG context
     │
     ▼
routes.py: append new {q, a} turn to full DB list; save updated summary → db.commit()
     │
     ▼
→ frontend renders answer + source chunks + trace
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Groq (primary) / OpenAI GPT-4o-mini (fallback) |
| **Agent Orchestration** | LangGraph (StateGraph) |
| **Web Search** | DDGS (`ddgs` package) |
| **Web Crawler** | crawl4ai (async, headless) |
| **Vector Database** | Qdrant local disk collection `feasibility_context` with lazy initialization |
| **Embeddings** | SentenceTransformers `all-MiniLM-L6-v2` |
| **Backend API** | FastAPI + Uvicorn |
| **Database** | PostgreSQL via Neon (SQLAlchemy ORM) |
| **Frontend** | React + Vite |
| **Styling** | Vanilla CSS — Glassmorphic dark-mode design system |

---

## 📂 Project Structure

```
fesebility_check/
├── backend/
│   ├── api/
│   │   ├── routes.py          # POST /chat, POST /qa, GET /qa/graph
│   │   └── dependencies.py    # DB session injection
│   ├── core/
│   │   ├── config.py          # Pydantic settings (env vars)
│   │   ├── database.py        # SQLAlchemy engine + session factory
│   │   └── llm_factory.py     # LLM factory (Groq / OpenAI)
│   ├── models/
│   │   └── conversation.py    # ChatSession, AgentStateModel, FeasibilityReport
│   ├── pipeline/
│   │   ├── graph.py           # Main LangGraph StateGraph (/chat flow)
│   │   ├── qa_graph.py        # QA LangGraph (5 nodes incl. qa_memory_node)
│   │   ├── state.py           # Shared AgentState TypedDict
│   │   ├── tools.py           # All /chat node functions
│   │   └── prompts/
│   │       ├── cross_question.py  # Clarifying question prompt
│   │       ├── feasibility.py     # Main 7-field JSON report prompt
│   │       └── qa.py              # QA prompt (with memory + RAG context)
│   ├── rag/
│   │   ├── embedder.py        # SentenceTransformers chunking, lazy Qdrant init, clean shutdown
│   │   └── retriever.py       # Chunk count check + Qdrant retrieval compatibility wrapper
│   ├── noiseremover/
│   │   ├── __init__.py
│   │   └── chunk_filter.py    # Semantic chunk scorer / filter using sentence-transformers
│   ├── scraper/
│   │   └── web.py             # ddgs_url_scrapper, extract_core,
│   │                          # filter_urls, is_useful_content, crawler_service,
│   │                          # dedicated noise remover logger
│   ├── log/
│   │   └── noise_remover.log  # Separate keep/drop logs for semantic filtering
│   ├── qdrant_data/           # Local Qdrant persistence (gitignored in prod)
│   ├── sandbox/
│   │   └── test_qa_rag.py     # QA RAG diagnostic harness for retrieval/full-graph checks
│   ├── app.py                 # FastAPI app + CORS + router mount
│   ├── main.py                # Uvicorn entrypoint + DB init lifespan + lazy RAG startup
│   └── requirements.txt
└── frontend/
    └── src/
        ├── App.jsx            # 3-step state machine (initial → cross_question → report)
        │                      # Fixed: conversation_id race condition in React state
        ├── index.css          # Design system (glassmorphic dark mode)
        └── main.jsx
```

---

## 🗄️ Database Schema

| Table | Column | Purpose |
|---|---|---|
| `chat_sessions` | all | Every human/AI turn with idea, problem, customer context |
| `agent_states` | `optimized_query` | Last LLM-generated search query string |
| | `search_results` | Raw scraped web text |
| | `analysis` | Final feasibility JSON string |
| | `qa_history` | JSON list of all `{q, a}` QA turns (full, uncompressed) |
| | `qa_summary` | LLM rolling summary of turns older than the 7-turn window |
| `feasibility_reports` | all | Parsed structured fields: score, idea_fit, competitors, opportunity, targeting, next_step, chain_of_thought |

---

## 🔑 QA Memory Design

```
DB: qa_history = [{q, a}, {q, a}, ... N turns]   ← full history, never trimmed in DB
DB: qa_summary = "..."                             ← rolling LLM summary of old turns

Each /api/qa call:
  1. Load full qa_history from DB → pass to graph
  2. qa_memory_node:
       if N <= 14 → use last 7 as context window (no LLM)
       if N  > 14 → LLM compresses turns[:-7] → new qa_summary; window = turns[-7:]
  3. qa_retrieve_context_node checks persisted chunk count for conversation_id
  4. Prompt = summary (if any) + window + RAG context + question
  5. Save: qa_history.append({q, a}); qa_summary = new_summary
```

This means the prompt context is **always bounded** regardless of how long the session runs.

If Qdrant has no chunks for that conversation, QA falls back to persisted
`analysis` + `search_results` from `agent_states` so the assistant can still answer.

---

## 🚦 Getting Started

### 1. Clone & Configure

```bash
git clone https://github.com/narayan0910/fesebility_check.git
cd fesebility_check
```

Create `backend/.env`:

```env
OPENAI_API_KEY=your_openai_key_here        # or GROQ_API_KEY if using Groq
POSTGRES_URL=postgresql://user:password@host/dbname?sslmode=require
NOISE_REMOVER_ENABLED=false
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=all-MiniLM-L6-v2
```

### 2. Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

If you enable the noise remover, make sure you start the app with the same
virtual environment where `requirements.txt` was installed. Running the app
with system `python3` can cause `sentence_transformers` import errors even if
it is installed inside `.venv`.

Backend runs at → **http://localhost:8000**

> On first startup, `main.py` auto-creates all DB tables (including the new
> `qa_history` and `qa_summary` columns added to `agent_states`).
>
> RAG now initializes lazily by default. This avoids local-disk Qdrant lock
> errors when another process already has `backend/qdrant_data` open.
> Set `PRELOAD_RAG_ON_STARTUP=true` only if you explicitly want eager startup.

### 2.1 Optional RAG Environment Flags

```env
PRELOAD_RAG_ON_STARTUP=false
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING_LOCAL_FILES_ONLY=false
```

- `PRELOAD_RAG_ON_STARTUP=false` keeps Qdrant lazy-loaded and avoids startup lock contention.
- `EMBEDDING_LOCAL_FILES_ONLY=true` is useful in offline environments if the MiniLM model is already cached locally.

### 2.2 Optional Noise Remover Flags

```env
NOISE_REMOVER_ENABLED=false
NOISE_REMOVER_THRESHOLD=0.4
NOISE_REMOVER_MODEL=all-MiniLM-L6-v2
```

- `NOISE_REMOVER_ENABLED=true` turns on semantic filtering after crawl + `extract_core()`.
- `NOISE_REMOVER_THRESHOLD` controls how aggressively chunks are dropped.
- `NOISE_REMOVER_MODEL` lets you switch the sentence-transformer model if needed.
- Noise-remover decisions are written to `log/noise_remover.log`, separate from `scraper.log`.

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at → **http://localhost:5173** (proxies `/api` to backend)

---

## 🧪 QA RAG Diagnostics

Use the sandbox diagnostic to inspect the same retrieval path used by the QA graph:

```bash
backend/.venv/bin/python backend/sandbox/test_qa_rag.py \
  --conversation-id <conversation_id> \
  --question "who had exhibited symptoms of depression" \
  --retrieval-query "who among potential users has exhibited symptoms of depression"
```

Run the full QA graph with persisted DB state:

```bash
backend/.venv/bin/python backend/sandbox/test_qa_rag.py \
  --conversation-id <conversation_id> \
  --question "who had exhibited symptoms of depression" \
  --retrieval-query "who among potential users has exhibited symptoms of depression" \
  --full-graph
```

This script prints:
- the persisted chunk count for the conversation
- whether QA used vector chunks or fallback context
- the retrieved context preview
- the generated answer preview when `--full-graph` is enabled

---

## 🔁 Conversation Flow (UI)

```
Step 1 — Initial Form
  User fills: Idea Name, Your Name, Ideal Customer, Problem Statement
  → Agent asks ONE clarifying question

Step 2 — Cross Question
  User answers the clarifying question
  → Agent runs full web research pipeline (15-30 sec)
  → Returns structured feasibility report

Step 3 — Report Dashboard
  Displays: Score, Idea Fit, Market Opportunity,
            Competitor Landscape, Targeting, Next Step,
            Agent Reasoning Chain

  + QA Chat (post-report):
      Ask unlimited follow-up questions grounded in your
      scraped research data. Memory window: 7 turns verbatim
      + rolling LLM summary of older turns.
```

---

## 🔍 Scraper Utilities (`scraper/web.py`)

| Function | Purpose |
|---|---|
| `ddgs_url_scrapper(query)` | Fetches up to 10 results from DuckDuckGo (region: `in-en`) |
| `filter_urls(urls, max=6)` | Removes `reddit.com`, `quora.com`, `zhihu.com`; caps list |
| `extract_core(markdown)` | Keeps first 30 lines > 40 chars; hard cap 1500 chars |
| `is_useful_content(text)` | Rejects pages with login walls, CAPTCHAs, timeouts |
| `crawler_service(urls, seed_texts=None)` | Async crawl of all URLs; applies `extract_core`, quality checks, and optional semantic noise removal |

### Noise Remover Logging

When `NOISE_REMOVER_ENABLED=true`, semantic filter decisions are logged to:

```text
log/noise_remover.log
```

Each chunk decision includes:
- similarity score
- source URL
- source title
- kept/dropped status
- chunk preview

Example log lines:

```text
[NOISE_REMOVER][KEEP] score=0.6123 | url=... | title=... | chunk=...
[NOISE_REMOVER][DROP] score=0.1842 | url=... | title=... | chunk=...
```

---

## 📝 License

MIT
