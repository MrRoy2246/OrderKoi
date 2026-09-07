"""PostgreSQL-shift unit tests: date-grouping SQL, aware datetime
helpers, and the env-driven connection-URL composition.

The suite itself runs on PostgreSQL (tests/conftest.py), so the SQL
here is also exercised for real by the API tests — these pin the exact
compiled shape and the config rules.
"""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app import timezone as tz
from app.config import Settings
from app.models import Order


def _compile(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestBusinessDaySql:
    def test_compiles_to_at_time_zone_cast(self):
        sql = _compile(select(tz.business_day(Order.created_at)))
        # CAST(created_at AT TIME ZONE 'Asia/Dhaka' AS DATE)
        assert "AT TIME ZONE 'Asia/Dhaka'" in sql
        assert "AS DATE" in sql

    def test_no_sqlite_left_behind(self):
        # The SQLite-era date()/strftime() modifiers are gone for good
        sql = _compile(select(tz.business_day(Order.created_at)))
        assert "date(" not in sql.replace("AS DATE", "")
        assert "strftime" not in sql


class TestBusinessMonthSql:
    def test_compiles_to_to_char(self):
        sql = _compile(select(tz.business_month(Order.created_at)))
        assert "to_char(" in sql.lower()
        assert "'YYYY-MM'" in sql
        assert "AT TIME ZONE 'Asia/Dhaka'" in sql


class TestAwareDatetimes:
    def test_day_bounds_are_aware_utc(self):
        start, end = tz.day_bounds_utc(date(2026, 9, 7))
        assert start.tzinfo is not None and end.tzinfo is not None
        # Dhaka is UTC+6: local midnight is 18:00 UTC the previous day
        assert (start.hour, start.day) == (18, 6)

    def test_month_start_is_aware_utc(self):
        assert tz.month_start_utc().tzinfo is not None

    def test_to_business_time(self):
        aware = datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc)
        local = tz.to_business_time(aware)  # Dhaka = UTC+6
        assert local.hour == 0
        assert local.day == 8  # midnight next day


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

    def test_missing_password_is_a_boot_error(self):
        with pytest.raises(ValidationError):
            Settings(PG_PASSWORD="", _env_file=None)

    def test_explicit_database_url_wins_over_pg_vars(self):
        settings = Settings(
            DATABASE_URL="postgresql+psycopg://other:pw@db:5432/otherdb",
            PG_PASSWORD="irrelevant",
            _env_file=None,
        )
        assert settings.database_url == "postgresql+psycopg://other:pw@db:5432/otherdb"

    def test_password_special_characters_are_escaped(self):
        settings = Settings(
            PG_USER="u",
            PG_PASSWORD="p@ss:word/1",
            _env_file=None,
        )
        assert "p%40ss%3Aword%2F1" in settings.database_url
