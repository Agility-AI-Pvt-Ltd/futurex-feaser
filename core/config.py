import os
from typing import Dict, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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
    POSTGRES_URL: str = Field(default="postgresql://neondb_owner:npg_PC1qtQLI3DUB@ep-quiet-breeze-anavmbd1-pooler.c-6.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")

    # ── Google Search ──────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = Field(default="")
    GOOGLE_CSE_ID: str = Field(default="")

    # ── Reddit ─────────────────────────────────────────────────────────────────
    REDDIT_CLIENT_ID: str = Field(default="")
    REDDIT_CLIENT_SECRET: str = Field(default="")

    # ── OpenAI ───────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="")

    # ── Noise Remover ────────────────────────────────────────────────────────
    NOISE_REMOVER_ENABLED: bool = Field(default=False)
    NOISE_REMOVER_THRESHOLD: float = Field(default=0.4)
    NOISE_REMOVER_MODEL: str = Field(default="all-MiniLM-L6-v2")

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = Field(default=["*"])


# Single shared instance — import this everywhere
settings = Settings()
