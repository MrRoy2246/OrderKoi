"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import model_validator
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

    # Database — two ways to configure, in priority order:
    #
    #   1. DATABASE_URL — one full connection string, e.g.
    #      postgresql+psycopg://user:pass@localhost:5433/orderkoi
    #      (or sqlite:///./orderkoi.db for zero-setup development)
    #
    #   2. The discrete PG_* variables below — composed into a URL
    #      automatically. Change the user, password, host, or port in
    #      .env and the app follows without any code change.
    database_url: str = ""
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "orderkoi"
    pg_user: str = "orderkoi"
    pg_password: str = ""

    @model_validator(mode="after")
    def _compose_database_url(self) -> "Settings":
        """Resolve the final DATABASE_URL: explicit URL wins, else the
        PG_* parts are composed. Default (nothing set) is dev SQLite."""
        if not self.database_url:
            if self.pg_password:
                self.database_url = (
                    f"postgresql+psycopg://{quote_plus(self.pg_user)}:{quote_plus(self.pg_password)}"
                    f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
                )
            else:
                self.database_url = "sqlite:///./orderkoi.db"
        return self

    # Security
    secret_key: str = "dev-only-change-me"
    access_token_expire_minutes: int = 60 * 24
    jwt_algorithm: str = "HS256"

    # Business timezone — "today"/"this month" boundaries for sellers
    # (Asia/Dhaka: their day flips at local midnight, not 6am UTC)
    app_timezone: str = "Asia/Dhaka"

    # Subscriptions — the free plan is a one-time trial allowance (15
    # orders, ever); after that sellers need Pro. Admin-comped Pro is
    # the override path.
    free_plan_orders: int = 15

    # Password reset
    frontend_url: str = "http://localhost:5173"
    reset_token_expire_minutes: int = 30

    # Email verification — how long the signup verify link is valid
    email_verification_expire_minutes: int = 60 * 24

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
