from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_TITLE: str = Field(default="Feasibility Analysis API")
    APP_HOST: str = Field(default="127.0.0.1")
    APP_PORT: int = Field(default=8888)

    # ── Database ───────────────────────────────────────────────────────────────
    POSTGRES_URL: str = Field(default="")

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_REQUIRED: bool = Field(default=False)

    # ── Google Search ──────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = Field(default="")
    GOOGLE_CSE_ID: str = Field(default="")

    # ── Reddit ─────────────────────────────────────────────────────────────────
    REDDIT_CLIENT_ID: str = Field(default="")
    REDDIT_CLIENT_SECRET: str = Field(default="")
    REDDIT_USER_AGENT: str = Field(default="futurex-feaser/1.0")
    REDDIT_PRAW_TIMEOUT_SECONDS: int = Field(default=8)
    REDDIT_SKIP_CRAWLER_FALLBACK: bool = Field(default=False)

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL_NAME: str = Field(default="gpt-4o-mini")
    OPENROUTER_API_KEY: str = Field(default="")
    OPENROUTER_BASE_URL: str = Field(default="https://openrouter.ai/api/v1")
    OPENROUTER_MODEL_NAME: str = Field(default="meta-llama/llama-3-70b-instruct")
    OPENROUTER_LLM_CLEANER_ENABLED: bool = Field(default=False)
    OPENROUTER_LLM_CLEANER_MAX_CHARS: int = Field(default=3000)
    OPENROUTER_LLM_CLEANER_TIMEOUT_SECONDS: int = Field(default=8)
    OPENROUTER_LLM_CLEANER_MAX_SOURCES: int = Field(default=2)

    # ── API / Legacy LLM Rate Limiting ──────────────────────────────────────
    API_RATE_LIMIT_ENABLED: bool = Field(default=True)
    API_RATE_LIMIT_REQUESTS: Optional[int] = Field(default=None)
    API_RATE_LIMIT_WINDOW_SECONDS: Optional[int] = Field(default=None)
    LLM_RATE_LIMIT_REQUESTS: int = Field(default=10)
    LLM_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    # ── Scrape Rate Limiting ─────────────────────────────────────────────────
    SCRAPE_DAILY_LIMIT: int = Field(default=6)
    SCRAPE_RUN_LOG_DIR: str = Field(default="scrape_run_logs")
    SCRAPED_LOGX_DIR: str = Field(default="scraped_logx")
    CRAWLER_URL_TIMEOUT_SECONDS: int = Field(default=5)

    # ── Noise Remover ────────────────────────────────────────────────────────
    NOISE_REMOVER_ENABLED: bool = Field(default=False)
    NOISE_REMOVER_THRESHOLD: float = Field(default=0.4)
    NOISE_REMOVER_MODEL: str = Field(default="BAAI/bge-small-en-v1.5")
    FASTEMBED_CACHE_DIR: str = Field(default="/data/cache/fastembed")
    FASTEMBED_FALLBACK_CACHE_DIR: str = Field(default="fastembed_cache")

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = Field(default="*")

    # ── Internal Service JWT Auth ─────────────────────────────────────────────
    INTERNAL_AUTH_ENABLED: bool = Field(default=True)
    INTERNAL_AUTH_ISSUER: str = Field(default="main-backend")
    INTERNAL_AUTH_AUDIENCE: str = Field(default="microservice")
    INTERNAL_AUTH_ALGORITHM: str = Field(default="HS256")
    INTERNAL_AUTH_JWT_SECRET: str = Field(default="")
    INTERNAL_AUTH_JWT_PUBLIC_KEY: str = Field(default="")
    INTERNAL_AUTH_REQUIRED_SERVICE: Optional[str] = Field(default="main-backend")

    # ── Axiom Logging ────────────────────────────────────────────────────────
    AXIOM_TOKEN: str = Field(default="")
    AXIOM_DATASET: str = Field(default="")
    LANGSMITH_TRACING: bool = Field(default=False)
    LANGSMITH_ENDPOINT: str = Field(default="https://api.smith.langchain.com")
    LANGSMITH_API_KEY: str = Field(default="")
    LANGSMITH_PROJECT: str = Field(default="default")
    QA_TOP_K: int = Field(default=5)
    QA_WINDOW_SIZE: int = Field(default=7)
    QA_SUMMARIZE_THRESHOLD: int = Field(default=14)
    QA_MAX_STORED_TURNS: int = Field(default=100)
    API_DEFAULT_PAGE_SIZE: int = Field(default=50)
    API_MAX_PAGE_SIZE: int = Field(default=200)
    QDRANT_PATH: str = Field(default="/data/qdrant")
    QDRANT_FALLBACK_PATH: str = Field(default="qdrant_data")
    RAG_LOG_CHUNK_CHARS: int = Field(default=400)
    RAG_RUN_LOG_DIR: str = Field(default="rag_run_logs")

    # ── Lecturebot merge settings ───────────────────────────────────────────
    LECTURE_LOG_LEVEL: str = Field(default="INFO")
    LECTURE_LOG_RAG_CHUNK_CHARS: int = Field(default=600)
    LECTURE_LOG_PROMPT_CHARS: int = Field(default=2000)
    LECTURE_RECENT_HISTORY_MESSAGES: int = Field(default=8)
    LECTURE_RETRIEVAL_HISTORY_MESSAGES: int = Field(default=4)
    LECTURE_SUMMARY_TRIGGER_MESSAGES: int = Field(default=10)
    LECTURE_MEMORY_SUMMARY_CHARS: int = Field(default=3000)
    LECTURE_TRANSCRIPT_SUMMARY_CHUNK_CHARS: int = Field(default=12000)
    LECTURE_TRANSCRIPT_SUMMARY_MAX_CHARS: int = Field(default=6000)
    LECTURE_OPENAI_MODEL_NAME: str = Field(default="gpt-4o-mini")
    LECTURE_TRANSCRIPT_STORAGE_PATH: str = Field(default="transcripts_data")
    LECTURE_QDRANT_COLLECTION_NAME: str = Field(default="lecture_transcripts")
    LECTURE_QDRANT_PATH: Optional[str] = Field(default=None)
    LECTURE_EMBEDDING_MODEL: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    LECTURE_VECTOR_SIZE: int = Field(default=384)

    @property
    def lecture_transcript_storage_path(self) -> str:
        raw_path = Path(self.LECTURE_TRANSCRIPT_STORAGE_PATH).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def lecture_qdrant_path(self) -> str:
        return self._resolve_path(self.LECTURE_QDRANT_PATH or self.QDRANT_PATH)

    @property
    def qdrant_path(self) -> str:
        return self._resolve_path(self.QDRANT_PATH)

    @property
    def qdrant_fallback_path(self) -> str:
        return self._resolve_path(self.QDRANT_FALLBACK_PATH)

    @property
    def fastembed_cache_dir(self) -> str:
        return self._resolve_path(self.FASTEMBED_CACHE_DIR)

    @property
    def fastembed_fallback_cache_dir(self) -> str:
        return self._resolve_path(self.FASTEMBED_FALLBACK_CACHE_DIR)

    @property
    def scrape_run_log_dir(self) -> str:
        raw_path = Path(self.SCRAPE_RUN_LOG_DIR).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def scraped_logx_dir(self) -> str:
        raw_path = Path(self.SCRAPED_LOGX_DIR).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def rag_run_log_dir(self) -> str:
        return self._resolve_path(self.RAG_RUN_LOG_DIR)

    def _resolve_path(self, path_value: str) -> str:
        raw_path = Path(path_value).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def api_rate_limit_requests(self) -> int:
        if self.API_RATE_LIMIT_REQUESTS is not None:
            return self.API_RATE_LIMIT_REQUESTS
        return self.LLM_RATE_LIMIT_REQUESTS

    @property
    def api_rate_limit_window_seconds(self) -> int:
        if self.API_RATE_LIMIT_WINDOW_SECONDS is not None:
            return self.API_RATE_LIMIT_WINDOW_SECONDS
        return self.LLM_RATE_LIMIT_WINDOW_SECONDS

    @property
    def allowed_origins(self) -> List[str]:
        parsed = [origin.strip() for origin in (self.ALLOWED_ORIGINS or "").split(",") if origin.strip()]
        return parsed or ["*"]


# Single shared instance — import this everywhere
settings = Settings()
