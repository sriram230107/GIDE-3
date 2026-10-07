from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# gide/services/api/app/core/config.py -> parents[4] == gide/
ROOT_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Gide API"
    ENVIRONMENT: str = "development"

    # Database: set real credentials in services/api/.env (never commit them)
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/gide"
    SYNC_DATABASE_URL: str = "postgresql://postgres:postgres@127.0.0.1:5432/gide"

    REDIS_HOST: str = "127.0.0.1"
    REDIS_PORT: int = 6379

    STORAGE_DIR: str = str(ROOT_DIR / "storage")
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Auth
    JWT_SECRET: str = "dev-only-change-me"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # ============================================================
    # AI Providers
    # ============================================================
    TEXT_PROVIDER: str = "ollama"
    EMBED_PROVIDER: str = "ollama"
    VISION_PROVIDER: str = "gemini"

    # ============================================================
    # AI - Gemini
    # ============================================================

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_VERIFIER_MODEL: Optional[str] = None
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"

    # ============================================================
    # AI - Ollama
    # ============================================================

    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_TEXT_MODEL: str = "qwen2.5:3b"
    OLLAMA_TUTOR_MODEL: str = "llama3.1:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    OLLAMA_VISION_MODEL: str = "llama3.2-vision"
    OLLAMA_VERIFIER_MODEL: str = "llama3.1:8b"

    # AI runtime
    LLM_TIMEOUT_S: float = 180.0
    LLM_MAX_CONCURRENCY: int = 1

    # ============================================================
    # Ingestion
    # ============================================================

    WHISPER_MODEL: str = "small"
    MAX_VISION_CALLS_PER_SOURCE: int = 60
    KEYFRAME_THRESHOLD: float = 0.35
    KEYFRAME_MAX_GAP_S: float = 30.0
    KEYFRAME_MAX_COUNT: int = 80

    # ============================================================
    # Retrieval / Grounding
    # ============================================================

    RETRIEVAL_TOP_K: int = 6
    CALIBRATION_FILE: str = str(ROOT_DIR / "evaluation" / "calibration.json")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="allow",
    )


settings = Settings()