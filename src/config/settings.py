"""
Application settings loaded from environment variables.

Uses pydantic-settings `BaseSettings` to:
- Read from .env file (via python-dotenv)
- Validate required values (DATABASE_URL, JWT_SECRET, etc.)
- Provide typed access throughout the app: `settings.DATABASE_URL`
"""

from pydantic_settings import BaseSettings


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
    AUTH_BYPASS_ENABLED: bool = True
    AUTH_BYPASS_USER_ID: str = "v1-demo-user"
    AUTH_BYPASS_USER_NAME: str = "System"
    AUTH_BYPASS_TEAM: str = "workspace"

    class Config:
        env_file = ".env"


# ── Module-level instance ─────────────────────────────
settings = Settings()
