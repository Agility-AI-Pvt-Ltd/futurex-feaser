import os
import sys
import threading
import traceback
from time import perf_counter
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from api.routes import router
from core.config import settings
from core.database import init_db
from core.logging import (
    configure_logging,
    log_event,
    serialize_http_body,
    sanitize_headers,
)

logger = configure_logging().getChild("http")


def _initialize_database():
    print("Starting up... initializing database")
    try:
        from core.database import engine

        with engine.connect() as connection:
            print("Successfully connected to the PostgreSQL database!")
        init_db()
        print("Database tables verified/initialized!")
    except Exception as e:
        print("ERROR: Failed to connect to or initialize the database. Please check your POSTGRES_URL.")
        print(f"Details: {e}")


def _preload_runtime_models() -> None:
    if settings.NOISE_REMOVER_ENABLED:
        print(f"Preloading noise-remover model: {settings.NOISE_REMOVER_MODEL}")
        try:
            from noiseremover.chunk_filter import preload_text_embedding_model

            preload_text_embedding_model(settings.NOISE_REMOVER_MODEL)
            print("Noise-remover FastEmbed model loaded.")
        except Exception as e:
            print(f"Noise-remover preload error: {e}")

    preload_rag = os.getenv("PRELOAD_RAG_ON_STARTUP", "").lower() in {"1", "true", "yes"}
    if preload_rag:
        print("Starting up RAG embedding models...")
        try:
            from rag.embedder import _init_qdrant

            _init_qdrant()
            print("BAAI/bge-small-en-v1.5 embedder and Qdrant initialized locally.")
        except ImportError as e:
            print(f"RAG packages missing: {e}")
        except Exception as e:
            print(f"Qdrant initialization error: {e}")
    else:
        print("Skipping eager RAG startup; Qdrant will initialize lazily on first RAG request.")


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_initialize_database, daemon=True).start()
    _preload_runtime_models()

    yield

    try:
        from rag.embedder import close_qdrant

        close_qdrant()
    except Exception:
        pass
    print("Shutting down...")

app = FastAPI(
    title="Feasibility Check - AI Analysis System",
    description="AI-powered startup feasibility analysis using LangGraph & OpenAI",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_http_traffic(request: Request, call_next):
    started_at = perf_counter()
    request_body = await request.body()

    log_event(
        logger,
        "http_request",
        method=request.method,
        path=request.url.path,
        query=str(request.url.query),
        client_ip=request.client.host if request.client else None,
        headers=sanitize_headers(request.headers),
        request_body=serialize_http_body(request_body, request.headers.get("content-type")),
    )

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - started_at) * 1000, 3)
        logger.exception(
            "http_response_error",
            extra={
                "event": "http_response_error",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        raise

    response_body = b""
    if hasattr(response, "body") and response.body is not None:
        response_body = response.body
    else:
        async for chunk in response.body_iterator:
            response_body += chunk

    duration_ms = round((perf_counter() - started_at) * 1000, 3)
    response_headers = dict(response.headers)
    response_headers.pop("content-length", None)

    log_event(
        logger,
        "http_response",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        headers=sanitize_headers(response.headers),
        response_body=serialize_http_body(response_body, response.headers.get("content-type")),
    )

    return Response(
        content=response_body,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.media_type,
        background=response.background,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print("--- INTERNAL SERVER ERROR ---")
    traceback.print_exc(file=sys.stdout)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"},
    )


# ── CORS Middleware ───────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")

# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "message": "Feasibility Check API is running"}


def run() -> None:
    port = int(os.getenv("PORT") or os.getenv("APP_PORT") or str(settings.APP_PORT))
    host = os.getenv("APP_HOST", settings.APP_HOST)
    reload_enabled = os.getenv("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"}

    print(f"Binding FastAPI server on {host}:{port}")
    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=reload_enabled,
        log_level="info",
    )


if __name__ == "__main__":
    run()
