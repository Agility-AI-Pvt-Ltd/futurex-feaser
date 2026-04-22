# Backend Integration Documentation

This document is for the frontend/full-stack developer integrating with the backend API in this repository.

Base URL examples:

- Local backend: `http://localhost:8000`
- API prefix: `/api`

Full local API base:

```txt
http://localhost:8000/api
```

## Overview

The backend supports a 2-phase product flow:

1. Idea intake and feasibility generation via `POST /api/chat`
2. Follow-up Q&A over the generated report via `POST /api/qa`

The backend is stateful. The main state key the frontend must preserve is:

```txt
conversation_id
```

This `conversation_id` is returned by `/api/chat` and must be reused for:

- the second `/api/chat` call after the user answers the clarifying question
- all later `/api/qa` requests

## High-Level Frontend Flow

Recommended UI flow:

1. User submits idea details
2. Frontend calls `POST /api/chat` without `conversation_id`
3. Backend returns a `conversation_id` and usually a clarifying question in `analysis`
4. Frontend stores that `conversation_id`
5. User answers the clarifying question
6. Frontend calls `POST /api/chat` again with the same `conversation_id`
7. Backend returns the final feasibility report in `analysis`
8. Frontend renders the report
9. User asks follow-up questions through `POST /api/qa` using the same `conversation_id`

## Health Check

### `GET /`

Simple liveness endpoint.

Response:

```json
{
  "status": "ok",
  "message": "Feasibility Check API is running"
}
```

## Main Chat Endpoint

### `POST /api/chat`

This endpoint is used for both:

- the initial idea submission
- the second-turn clarification answer

### Request body

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

### Fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `idea` | string | yes | On first request this is the startup idea. On follow-up, this becomes the user's answer to the clarifying question. |
| `user_name` | string | yes | User display name/context for the LLM. |
| `ideal_customer` | string | yes | Target user/customer segment. |
| `problem_solved` | string | yes | Problem statement. |
| `authorId` | string | yes | Frontend/user identifier stored in `chat_sessions.authorId`. |
| `conversation_id` | string or null | no | Omit or send `null` for a new flow. Reuse returned value for follow-up calls. |

### Response body

```json
{
  "response": "Researching your idea...",
  "conversation_id": "46bf4e97-cd77-414d-a34f-066f677fdc71",
  "analysis": "What specific user behavior or signal would the system use to identify someone at risk?"
}
```

### Response fields

| Field | Type | Notes |
|---|---|---|
| `response` | string | Status-like message. Usually `"Researching your idea..."` for the first turn and `"Analysis Complete"` for the second turn. |
| `conversation_id` | string | Persist this in frontend state immediately. |
| `analysis` | string or null | On first turn this is typically the clarifying question. On second turn this is the final feasibility report JSON as a string. |

## Important `/api/chat` Behavior

### First call

When `conversation_id` is missing:

- backend creates a new `conversation_id`
- backend treats the request as a new conversation
- backend usually returns a clarifying question in `analysis`

### Second call

When the same `conversation_id` is sent back:

- backend loads the original conversation context from the database
- backend treats the new `idea` value as the user's reply to the clarifying question
- backend runs research, analysis, persistence, and background embedding
- backend returns the full report in `analysis`

### Important frontend note

Do not overwrite or drop `conversation_id` between the first and second `/api/chat` calls.

That is the single most important state value in the client flow.

## Final Report Format

The final `analysis` returned by the second `/api/chat` call is expected to be a JSON string.

Typical structure:

```json
{
  "chain_of_thought": [
    "step 1",
    "step 2"
  ],
  "idea_fit": "Strong fit for early validation...",
  "competitors": "Competitor summary...",
  "opportunity": "Market opportunity summary...",
  "score": "7.5/10",
  "targeting": "Start with college counseling centers...",
  "next_step": "Run 20 interviews and validate user trust..."
}
```

### Frontend recommendation

Parse `analysis` defensively:

- first try `JSON.parse(analysis)`
- if parsing fails, show the raw text instead of crashing

This is important because LLM output can occasionally contain formatting noise.

## QA Endpoint

### `POST /api/qa`

Use this only after a report has been generated for the conversation.

### Request body

```json
{
  "conversation_id": "46bf4e97-cd77-414d-a34f-066f677fdc71",
  "question": "Who had exhibited symptoms of depression?"
}
```

### Response body

```json
{
  "answer": "The retrieved context suggests that ...",
  "top_chunks": [
    {
      "source": "web_research",
      "text": "Some retrieved supporting text...",
      "score": 0.82
    }
  ],
  "trace": [
    {
      "ts": "2026-04-17T04:54:46.391694+00:00",
      "step": "qa_retrieve_context",
      "message": "Retrieved RAG context for the user question.",
      "metadata": {
        "question": "Who had exhibited symptoms of depression?",
        "retrieval_query": "who among potential users has exhibited symptoms of depression",
        "persisted_chunk_count": 99,
        "top_chunks": 1,
        "used_fallback": false
      }
    }
  ]
}
```

### Response fields

| Field | Type | Notes |
|---|---|---|
| `answer` | string | Final answer to the user’s QA message. |
| `top_chunks` | array | Retrieved source chunks used for answer grounding. Can be empty. |
| `trace` | array | Debug/observability metadata from the QA graph. Useful during development. |

## Important `/api/qa` Behavior

- Server-side QA memory is persisted in the database
- Recent QA turns are kept verbatim
- Older turns are summarized automatically
- RAG retrieval is filtered by `conversation_id`
- If no vector chunks are available or retrieval yields nothing, backend falls back to persisted `analysis` and `search_results`

This means QA should still return a useful answer even if vector retrieval is unavailable.

## QA Graph Debug Endpoint

### `GET /api/qa/graph`

Returns a Mermaid graph definition for the QA pipeline.

Example response:

```json
{
  "name": "qa_langgraph",
  "mermaid": "graph TD; ..."
}
```

Useful for:

- debugging the QA flow
- visualizing the backend state machine
- internal tooling

## Suggested Frontend State Shape

Example client-side state:

```js
{
  conversation_id: null,
  idea: "",
  user_name: "",
  ideal_customer: "",
  problem_solved: "",
  authorId: "",
  currentStep: "initial",
  clarifyingQuestion: "",
  report: null,
  qaMessages: []
}
```

## Recommended Frontend Integration Pattern

### Step 1: Initial idea submission

Send:

```json
{
  "idea": "...",
  "user_name": "...",
  "ideal_customer": "...",
  "problem_solved": "...",
  "authorId": "...",
  "conversation_id": null
}
```

Then:

- store `conversation_id`
- show `analysis` as the clarifying question
- move UI to clarification step

### Step 2: Clarifying answer submission

Send:

```json
{
  "idea": "user answer to clarifying question",
  "user_name": "...",
  "ideal_customer": "...",
  "problem_solved": "...",
  "authorId": "...",
  "conversation_id": "same-id-from-step-1"
}
```

Then:

- parse the returned `analysis`
- render the report dashboard
- enable QA chat

### Step 3: QA follow-ups

Send:

```json
{
  "conversation_id": "same-id-from-before",
  "question": "What competitor is closest to this idea?"
}
```

Then:

- render `answer`
- optionally show `top_chunks` as expandable citations/debug cards
- optionally log or inspect `trace` in development mode

## Error and Edge Cases

Frontend should handle these cases gracefully.

### 1. `analysis` is not valid JSON

Expected behavior:

- show raw response text
- do not block the user

### 2. `/api/qa` before report exists

Possible response:

```json
{
  "answer": "Could not find a feasibility report for this idea."
}
```

### 3. `/api/qa` for missing conversation

Possible response:

```json
{
  "answer": "Could not find chat history for this conversation."
}
```

### 4. Backend-side QA error

Possible response:

```json
{
  "answer": "I'm sorry, I encountered an error while trying to answer your question.",
  "top_chunks": [],
  "trace": [
    {
      "step": "qa_error",
      "message": "..."
    }
  ]
}
```

## CORS

CORS is currently wide open in development:

- `allow_origins=["*"]`
- all methods allowed
- all headers allowed

No special frontend CORS handling should be required in local development.

## Backend Startup Notes

The backend:

- initializes database tables on startup
- uses lazy Qdrant startup by default
- loads the local vector database only when RAG is first needed

Useful environment flags:

```env
PRELOAD_RAG_ON_STARTUP=false
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING_LOCAL_FILES_ONLY=false
```

## Local Dev Examples

### Example `fetch` for first `/api/chat`

```js
const res = await fetch("http://localhost:8000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    idea: "AI companion for early depression screening",
    user_name: "Krishna",
    ideal_customer: "young adults and college students",
    problem_solved: "helps identify mental health risk early",
    authorId: "user_123",
    conversation_id: null
  })
});

const data = await res.json();
```

### Example `fetch` for clarification answer

```js
const res = await fetch("http://localhost:8000/api/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    idea: "The product would monitor journal entries and self-reported mood patterns",
    user_name: "Krishna",
    ideal_customer: "young adults and college students",
    problem_solved: "helps identify mental health risk early",
    authorId: "user_123",
    conversation_id: storedConversationId
  })
});

const data = await res.json();
const report = safeParseJson(data.analysis);
```

### Example `fetch` for QA

```js
const res = await fetch("http://localhost:8000/api/qa", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    conversation_id: storedConversationId,
    question: "Which user segment looks most promising?"
  })
});

const data = await res.json();
```

### Example safe parser

```js
function safeParseJson(value) {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}
```

## Practical Hand-Off Notes

When handing this backend to a frontend/full-stack developer, make sure they understand:

- `conversation_id` must be saved immediately after the first `/api/chat` call
- the second `/api/chat` call is not a new idea submission, it is the clarifying answer
- the report comes back as a JSON string in `analysis`
- `/api/qa` depends on the same `conversation_id`
- `top_chunks` and `trace` are optional but very useful during development

## Source Files

Main files relevant to integration:

- [backend/api/routes.py](/Users/krishnakumar/Downloads/RESUME/AGILITY_AI/fesebility_check/backend/api/routes.py)
- [backend/app.py](/Users/krishnakumar/Downloads/RESUME/AGILITY_AI/fesebility_check/backend/app.py)
- [backend/main.py](/Users/krishnakumar/Downloads/RESUME/AGILITY_AI/fesebility_check/backend/main.py)
