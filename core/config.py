from pathlib import Path
from typing import List
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

    # ── Google Search ──────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = Field(default="")
    GOOGLE_CSE_ID: str = Field(default="")

    # ── Reddit ─────────────────────────────────────────────────────────────────
    REDDIT_CLIENT_ID: str = Field(default="")
    REDDIT_CLIENT_SECRET: str = Field(default="")
    REDDIT_USER_AGENT: str = Field(default="futurex-feaser/1.0")

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL_NAME: str = Field(default="gpt-4o-mini")

    # ── Legacy LLM Rate Limiting ─────────────────────────────────────────────
    LLM_RATE_LIMIT_REQUESTS: int = Field(default=10)
    LLM_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60)

    # ── Scrape Rate Limiting ─────────────────────────────────────────────────
    SCRAPE_DAILY_LIMIT: int = Field(default=6)
    SCRAPE_RUN_LOG_DIR: str = Field(default="scrape_run_logs")

    # ── Noise Remover ────────────────────────────────────────────────────────
    NOISE_REMOVER_ENABLED: bool = Field(default=False)
    NOISE_REMOVER_THRESHOLD: float = Field(default=0.4)
    NOISE_REMOVER_MODEL: str = Field(default="BAAI/bge-small-en-v1.5")

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = Field(default=["*"])

    # ── Axiom Logging ────────────────────────────────────────────────────────
    AXIOM_TOKEN: str = Field(default="")
    AXIOM_DATASET: str = Field(default="")
    QA_TOP_K: int = Field(default=5)
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
    LECTURE_OPENAI_MODEL_NAME: str = Field(default="gpt-4o-mini")
    LECTURE_TRANSCRIPT_STORAGE_PATH: str = Field(default="transcripts_data")
    LECTURE_QDRANT_COLLECTION_NAME: str = Field(default="lecture_transcripts")
    LECTURE_QDRANT_PATH: str = Field(default="lecture_qdrant")
    LECTURE_EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2")
    LECTURE_VECTOR_SIZE: int = Field(default=384)

    @property
    def lecture_transcript_storage_path(self) -> str:
        raw_path = Path(self.LECTURE_TRANSCRIPT_STORAGE_PATH).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def lecture_qdrant_path(self) -> str:
        raw_path = Path(self.LECTURE_QDRANT_PATH).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def scrape_run_log_dir(self) -> str:
        raw_path = Path(self.SCRAPE_RUN_LOG_DIR).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())

    @property
    def rag_run_log_dir(self) -> str:
        raw_path = Path(self.RAG_RUN_LOG_DIR).expanduser()
        if raw_path.is_absolute():
            return str(raw_path)
        return str((BASE_DIR / raw_path).resolve())


# Single shared instance — import this everywhere
settings = Settings()
