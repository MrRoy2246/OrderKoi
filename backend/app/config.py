"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # An env var set to the empty string counts as "not set" — this
        # lets the compose file pass optional knobs through as
        # `VAR: ${VAR:-}` without tripping validation on the blank.
        env_ignore_empty=True,
    )

    # App identity
    app_name: str = "OrderKoi API"
    api_version: str = "1.0.0"
    # Literal, not str: a typo like "prod" or "Production" would
    # otherwise disable every production safety check in app/main.py
    # while still looking correct in .env — the single most dangerous
    # way to misconfigure this file.
    environment: Literal["development", "test", "production"] = "development"

    # Database (PostgreSQL) — two ways to configure, in priority order:
    #
    #   1. DATABASE_URL — one full connection string, e.g.
    #      postgresql+psycopg://user:pass@localhost:5433/orderkoi
    #
    #   2. The discrete PG_* variables below — composed into a URL
    #      automatically. Change the user, password, host, or port in
    #      .env and the app follows without any code change.
    #
    # One of the two must be set; the app refuses to boot otherwise.
    database_url: str = ""
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "orderkoi"
    pg_user: str = "orderkoi"
    pg_password: str = ""

    @model_validator(mode="after")
    def _compose_database_url(self) -> "Settings":
        """Resolve the final connection URL: an explicit DATABASE_URL
        wins, else the PG_* parts are composed. Missing both is a
        configuration error — fail at boot, not at first query."""
        if not self.database_url:
            if not self.pg_password:
                raise ValueError(
                    "No database configured: set PG_PASSWORD "
                    "(+ PG_HOST/PG_PORT/PG_DATABASE/PG_USER) or DATABASE_URL "
                    "in .env — see .env.example"
                )
            self.database_url = (
                f"postgresql+psycopg://{quote_plus(self.pg_user)}:{quote_plus(self.pg_password)}"
                f"@{self.pg_host}:{self.pg_port}/{self.pg_database}"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def api_docs_enabled(self) -> bool:
        """Serve /docs, /redoc and /openapi.json?

        None (the default) means automatic: on in development and
        test, OFF in production — an open /docs advertises every admin
        route to anyone who asks for it. Force either way with
        ENABLE_API_DOCS=true/false.
        """
        if self.enable_api_docs is not None:
            return self.enable_api_docs
        return not self.is_production

    @property
    def uses_console_email(self) -> bool:
        """True when email is logged instead of sent — see email_backend.

        'auto' falls back to console only when smtp_host is empty, which
        keeps development and the test suite offline by default.
        """
        if self.email_backend == "console":
            return True
        if self.email_backend == "smtp":
            return False
        return not self.smtp_host

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

    # Pro prices per duration (taka). Env-driven so a price change is
    # an .env edit + restart — no code, no frontend rebuild: the
    # backend serves them at GET /pricing and both UIs follow. Change
    # one duration only if you want (e.g. run an offer on 1 month).
    pro_price_1m: int = 350
    pro_price_6m: int = 1750
    pro_price_12m: int = 2900

    # --- Business configuration (all env-driven, served at the public
    # /pricing endpoint so the frontend follows without a rebuild) ---

    # Where sellers send their bKash payment for Pro (shown in the
    # Settings payment instructions and emails refer to it).
    bkash_number: str = "01736060259"
    # bKash account type shown next to the number ("Personal"/"Agent")
    bkash_type: str = "Personal"

    # Public contact address for legal pages and support questions.
    support_email: str = "abinroy510@gmail.com"

    # Password reset
    frontend_url: str = "http://localhost:5173"
    reset_token_expire_minutes: int = 30

    # Email verification — how long the signup verify link is valid
    email_verification_expire_minutes: int = 60 * 24

    # Email (SMTP).
    #
    # email_backend decides where mail actually goes:
    #   auto    (default) — SMTP if smtp_host is set, else the console
    #                       backend (emails printed to the server log)
    #   console — always log, never touch the network
    #   smtp    — always send, and log a loud failure if smtp_host is
    #             empty rather than silently falling back to console
    #
    # console exists as a setting of its own because "leave smtp_host
    # empty" is NOT expressible from the environment: env_ignore_empty
    # treats an empty value as unset, so `.env` would win and the real
    # credentials would be used anyway. That is precisely how the test
    # suite ended up sending live Gmail on every fixture signup — see
    # the EMAIL_BACKEND line in tests/conftest.py.
    email_backend: Literal["auto", "console", "smtp"] = "auto"
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

    @model_validator(mode="after")
    def _validate_cors_origins(self) -> "Settings":
        """Reject a wildcard, and an empty list in production.

        `*` is never safe here: browsers attach the bearer token to
        credentialed requests, so a wildcard would let any website on
        the internet call this API as a signed-in user. Browsers
        reject `*` for credentialed requests anyway, so allowing it
        buys nothing and hides the mistake until runtime.

        An empty list is the opposite failure — nobody can reach the
        API at all — and is only caught in production, so local
        tooling that deliberately talks server-to-server still works.
        """
        if "*" in self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS must not contain '*'. The API sends "
                "credentials, so a wildcard would let any website call "
                "it as a signed-in user. List exact origins, e.g. "
                '["https://orderkoi.example.com"]'
            )
        if self.is_production and not self.cors_origins:
            raise ValueError(
                "CORS_ORIGINS is empty — no browser origin could call "
                "the API. Set it to the frontend URL, e.g. "
                '["https://orderkoi.example.com"]'
            )
        return self

    # ------------------------------------------------------------------
    # Operational tunables
    #
    # Everything below is a knob an operator may need to turn without a
    # code change. Defaults are the values the app shipped with, so an
    # unset variable changes nothing. Override any of them in .env (or
    # the docker-compose environment block) and restart.
    # ------------------------------------------------------------------

    # --- Logging ---
    log_level: str = "INFO"

    # --- API docs ---
    # None = automatic: enabled in development/test, disabled in
    # production (an unauthenticated /docs + /openapi.json advertises
    # every admin route). Force with ENABLE_API_DOCS=true/false.
    enable_api_docs: bool | None = None

    # --- Rate limiting (per-IP sliding window) ---
    # Each rule is "<max requests> per <window seconds>". Raise these if
    # legitimate users share an IP (mobile-carrier CGNAT) and hit the
    # limiter. Set RATE_LIMIT_ENABLED=false to disable entirely — for
    # load testing only, never in production.
    rate_limit_enabled: bool = True
    rate_limit_login_max: int = 10
    rate_limit_login_window: int = 60
    rate_limit_signup_max: int = 5
    rate_limit_signup_window: int = 60
    rate_limit_forgot_password_max: int = 5
    rate_limit_forgot_password_window: int = 60
    rate_limit_resend_verification_max: int = 5
    rate_limit_resend_verification_window: int = 60
    rate_limit_track_max: int = 60
    rate_limit_track_window: int = 60
    rate_limit_public_form_max: int = 10
    rate_limit_public_form_window: int = 60
    rate_limit_public_max: int = 30
    rate_limit_public_window: int = 60

    # --- Per-account login lockout (app/login_throttle.py) ---
    # Failures before lockout, the window they're counted over, and how
    # long the lock lasts.
    login_max_failures: int = 5
    login_failure_window_minutes: int = 15
    login_lockout_minutes: int = 15

    # --- Database connection pool ---
    # Size the pool to comfortably cover the sync route threadpool (40)
    # so concurrent requests never wait on a checkout. pool_recycle
    # guards against NAT/firewall idle drops and PG-side timeouts.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 1800
    db_pool_timeout_seconds: int = 30

    # --- Email delivery ---
    email_workers: int = 4
    email_send_attempts: int = 3
    email_retry_delays_seconds: list[int] = [2, 10]
    smtp_timeout_seconds: int = 10
    # Console backend only (no SMTP_HOST): log the full message body?
    # None = automatic (True in development, False otherwise) — reset
    # and verification links must never reach a production log.
    email_console_logs_body: bool | None = None

    # --- Request / response limits ---
    # Seller CSV export row cap, and the higher cap for the admin export.
    export_max_rows: int = 10_000
    admin_export_max_rows: int = 20_000
    # Page size ceilings for the list endpoints.
    max_page_size: int = 100
    max_admin_page_size: int = 200
    # Ceiling on a single item's unit price and on a computed order
    # total — without these, a huge value overflows Numeric(12,2) and
    # 500s on an unauthenticated endpoint.
    max_item_price: float = 10_000_000.0
    max_order_total: float = 9_999_999_999.99


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (created once per process)."""
    return Settings()
