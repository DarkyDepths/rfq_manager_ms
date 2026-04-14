"""
Application settings loaded from environment variables.

Uses pydantic-settings `BaseSettings` to:
- Read from .env file (via python-dotenv)
- Validate required values (DATABASE_URL)
- Provide typed access throughout the app: `settings.DATABASE_URL`
"""

from pydantic import ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy.engine import make_url


class Settings(BaseSettings):

    # ── Required ──────────────────────────────────────
    DATABASE_URL: str

    # ── Optional with defaults ────────────────────────
    APP_ENV: str = "development"
    APP_PORT: int = 8000
    APP_DEBUG: bool = False
    IAM_SERVICE_URL: str = ""
    EVENT_BUS_URL: str = ""
    FILE_STORAGE_PATH: str = "./uploads"
    CORS_ORIGINS: str = "*"
    JWT_SECRET: str = "dev-secret-change-in-production"
    MAX_FILE_SIZE_MB: int = 50  # max upload size in megabytes
    AUTH_BYPASS_ENABLED: bool = False
    AUTH_BYPASS_USER_ID: str = "v1-demo-user"
    AUTH_BYPASS_USER_NAME: str = "System"
    AUTH_BYPASS_TEAM: str = "workspace"
    AUTH_BYPASS_PERMISSIONS: str = "rfq:*,workflow:*,rfq_stage:*,subtask:*,reminder:*,file:*"
    AUTH_BYPASS_DEBUG_HEADERS_ENABLED: bool = False
    IAM_REQUEST_TIMEOUT_SECONDS: float = 3.0
    EVENT_BUS_REQUEST_TIMEOUT_SECONDS: float = 3.0

    class Config:
        env_file = ".env"


def build_settings(env_file: str | None = ".env") -> Settings:
    """Load app settings and fail fast with clear DB configuration errors."""
    try:
        cfg = Settings(_env_file=env_file)
    except ValidationError as exc:
        raise RuntimeError(
            "Configuration error: DATABASE_URL is required. "
            "Set DATABASE_URL to a valid SQLAlchemy URL, for example: "
            "postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
        ) from exc

    database_url = (cfg.DATABASE_URL or "").strip()
    if not database_url:
        raise RuntimeError(
            "Configuration error: DATABASE_URL is required and cannot be empty. "
            "Set DATABASE_URL to a valid SQLAlchemy URL, for example: "
            "postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
        )

    try:
        make_url(database_url)
    except Exception as exc:  # pragma: no cover - SQLAlchemy controls exception type/details
        raise RuntimeError(
            f"Configuration error: DATABASE_URL is not a valid SQLAlchemy URL: '{database_url}'. "
            "Example: postgresql+psycopg2://rfq_user:changeme@localhost:5432/rfq_manager_db"
        ) from exc

    return cfg


# ── Module-level instance ─────────────────────────────
settings = build_settings()
