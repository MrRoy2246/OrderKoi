"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App identity
    app_name: str = "OrderKoi API"
    api_version: str = "1.0.0"
    environment: str = "development"

    # Database
    # Dev: SQLite (zero setup). Production (Phase 8): postgresql://...
    database_url: str = "sqlite:///./orderkoi.db"

    # Security
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"

    # Business timezone — "today"/"this month" boundaries for sellers
    # (Asia/Dhaka: their day flips at local midnight, not 6am UTC)
    app_timezone: str = "Asia/Dhaka"

    # Subscriptions — plans are uncapped (Pro is comped via the admin
    # panel; Free sellers are not throttled)

    # Password reset
    frontend_url: str = "http://localhost:5173"
    reset_token_expire_minutes: int = 30

    # Email (SMTP). Empty host = development "console" backend:
    # emails are printed to the server log instead of being sent.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = "OrderKoi <no-reply@orderkoi.local>"

    # CORS — origins allowed to call the API from a browser
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (created once per process)."""
    return Settings()
