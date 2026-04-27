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
    POSTGRES_URL: str = Field(default="")

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
    NOISE_REMOVER_MODEL: str = Field(default="BAAI/bge-small-en-v1.5")

    # ── CORS ───────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = Field(default=["*"])

    # ── Axiom Logging ────────────────────────────────────────────────────────
    AXIOM_TOKEN: str = Field(default="")
    AXIOM_DATASET: str = Field(default="")


# Single shared instance — import this everywhere
settings = Settings()
