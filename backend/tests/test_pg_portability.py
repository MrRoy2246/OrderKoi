"""Dialect-portability tests for the PostgreSQL shift (Phase 8b).

The date-grouping SQL (BusinessDay / BusinessMonth) must compile to
correct, equivalent SQL on both dialects the app runs on: SQLite
(tests, legacy dev) and PostgreSQL (dev/prod). These tests compile
the expressions against both dialects without needing a live
PostgreSQL server — the SQL string is what we verify, plus the
config layer that builds the connection URL from PG_* variables.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql, sqlite

from app import timezone as tz
from app.config import Settings
from app.models import Order


def _compile(expr, dialect):
    return str(expr.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


class TestBusinessDay:
    def test_sqlite_compilation_uses_date_with_offset(self):
        sql = _compile(tz.BusinessDay(Order.created_at), sqlite.dialect())
        # SQLite: date(col, '+N hours' [, minutes]) — shift happens in SQL
        assert sql.startswith("date(")
        assert "hours" in sql  # the UTC→business offset modifier is present

    def test_postgresql_compilation_uses_at_time_zone(self):
        sql = _compile(tz.BusinessDay(Order.created_at), postgresql.dialect())
        # Postgres: CAST(col AT TIME ZONE '<tz>' AS DATE)
        assert "AT TIME ZONE" in sql
        assert tz.get_settings().app_timezone in sql
        assert "CAST(" in sql and "AS DATE" in sql


class TestBusinessMonth:
    def test_sqlite_compilation_uses_strftime(self):
        sql = _compile(tz.BusinessMonth(Order.created_at), sqlite.dialect())
        assert "strftime('%Y-%m'" in sql
        assert "hours" in sql

    def test_postgresql_compilation_uses_to_char(self):
        sql = _compile(tz.BusinessMonth(Order.created_at), postgresql.dialect())
        assert "TO_CHAR(" in sql
        assert "'YYYY-MM'" in sql
        assert "AT TIME ZONE" in sql


class TestToBusinessTime:
    def test_accepts_naive_utc(self):
        naive = datetime(2026, 9, 7, 18, 0)  # 18:00 UTC
        local = tz.to_business_time(naive)  # Dhaka = UTC+6
        assert local.hour == 0
        assert local.day == 8  # midnight next day

    def test_accepts_aware_utc(self):
        # PostgreSQL timestamptz columns come back timezone-aware
        aware = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)
        local = tz.to_business_time(aware)
        assert local.hour == 0
        assert local.day == 8

    def test_naive_and_aware_agree(self):
        naive = datetime(2026, 1, 15, 3, 30)
        aware = naive.replace(tzinfo=timezone.utc)
        assert tz.to_business_time(naive) == tz.to_business_time(aware)


class TestDatabaseUrlComposition:
    def test_pg_vars_compose_postgres_url(self):
        settings = Settings(
            PG_HOST="db.example.com",
            PG_PORT=5433,
            PG_DATABASE="orderkoi",
            PG_USER="orderkoi",
            PG_PASSWORD="secret-pw",
            _env_file=None,  # ignore .env on this machine
        )
        assert settings.database_url == (
            "postgresql+psycopg://orderkoi:secret-pw@db.example.com:5433/orderkoi"
        )

    def test_no_config_falls_back_to_dev_sqlite(self):
        settings = Settings(_env_file=None)
        assert settings.database_url == "sqlite:///./orderkoi.db"

    def test_explicit_database_url_wins_over_pg_vars(self):
        settings = Settings(
            DATABASE_URL="sqlite:///./custom.db",
            PG_PASSWORD="irrelevant",
            _env_file=None,
        )
        assert settings.database_url == "sqlite:///./custom.db"

    def test_password_special_characters_are_escaped(self):
        settings = Settings(
            PG_USER="u",
            PG_PASSWORD="p@ss:word/1",
            _env_file=None,
        )
        assert "p%40ss%3Aword%2F1" in settings.database_url
