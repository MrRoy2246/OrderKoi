"""Timezone handling — one source of truth for "which day is it".

Timestamps are stored in UTC. Every question of the form "today",
"this month", or "which date does this order belong to" is answered
in the business timezone (APP_TIMEZONE, default Asia/Dhaka), so a
Bangladeshi seller's day flips at Dhaka midnight — not at 6am.

Never call date.today() or construct timezone-aware datetimes ad hoc
in route code; use these helpers so the zones can't get mixed again.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Date, String
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from app.config import get_settings

_tz = ZoneInfo(get_settings().app_timezone)

# Exposed for route code that needs to build local datetimes itself
# (e.g. month boundaries for chart buckets) — still one source of truth.
business_tz = _tz


def business_now() -> datetime:
    """Current instant, aware, in the business timezone."""
    return datetime.now(_tz)


def business_today() -> date:
    """What day it is for the seller (business-timezone date)."""
    return business_now().date()


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """UTC instants [start, end) covering a calendar day in the
    business timezone.

    Returned naive on purpose: SQLite stores created_at as naive-UTC
    strings and query-side comparisons must stay string-exact, and on
    PostgreSQL the session timezone is pinned to UTC (see
    app/database.py) so naive parameters are interpreted as UTC on
    both dialects.
    """
    start_local = datetime(day.year, day.month, day.day, tzinfo=_tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def month_start_utc() -> datetime:
    """UTC instant of the start of the current business-timezone month
    (where the free-plan monthly quota meter resets)."""
    now_local = business_now()
    start_local = datetime(now_local.year, now_local.month, 1, tzinfo=_tz)
    return start_local.astimezone(timezone.utc).replace(tzinfo=None)


def to_business_time(utc: datetime) -> datetime:
    """Convert a stored UTC timestamp to business-local time — for
    display to the seller (e.g. CSV export dates).

    Accepts both shapes a column can come back in: the naive UTC
    datetimes SQLite returns and the aware ones PostgreSQL returns
    (DateTime(timezone=True) maps to timestamptz).
    """
    if utc.tzinfo is None:
        utc = utc.replace(tzinfo=timezone.utc)
    return utc.astimezone(_tz)


def as_naive_utc(value: datetime) -> datetime:
    """Naive-UTC twin of a stored timestamp.

    The inverse of the normalization in to_business_time: Python-side
    comparisons against the naive bounds from day_bounds_utc() /
    month_start_utc() must work no matter which dialect produced the
    value (SQLite → naive, PostgreSQL → aware).
    """
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# SQL-side date grouping — same expression, per-dialect SQL.
#
# Route code groups rows by business-local day/month with
# business_day(Order.created_at) / business_month(...). Each dialect
# compiles it to its own SQL, so charts stay correct on SQLite (tests,
# zero-setup dev) and PostgreSQL (dev/prod) without branching in the
# routes.
# ---------------------------------------------------------------------------


class BusinessDay(FunctionElement):
    """Business-local calendar date of a stored UTC timestamp.

    Postgres: CAST(created_at AT TIME ZONE '<tz>' AS DATE) — returns a
    date object. SQLite: date(created_at, '+6 hours', ...) — returns a
    'YYYY-MM-DD' string. str() of either matches the chart day keys.
    """

    name = "business_day"
    type = Date()
    inherit_cache = True


class BusinessMonth(FunctionElement):
    """Business-local 'YYYY-MM' of a stored UTC timestamp."""

    name = "business_month"
    type = String()
    inherit_cache = True


def _tz_sql_literal() -> str:
    """The business timezone as a safely-quoted SQL string literal."""
    return "'" + get_settings().app_timezone.replace("'", "''") + "'"


def _utc_offset_modifiers() -> list[str]:
    """SQLite date() modifiers that shift a UTC timestamp into the
    business timezone.

    Exact for fixed-offset zones like Asia/Dhaka (no DST since 2009).
    """
    offset = business_now().utcoffset() or timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    modifiers = [f"{sign}{hours} hours"]
    if mins:
        modifiers.append(f"{sign}{mins} minutes")
    return modifiers


@compiles(BusinessDay, "postgresql")
def _business_day_postgresql(element, compiler, **kw):
    column = compiler.process(element.clauses, **kw)
    # timestamptz AT TIME ZONE '<tz>' → naive local timestamp; the
    # server (not Python) owns the calendar math.
    return f"CAST(({column}) AT TIME ZONE {_tz_sql_literal()} AS DATE)"


@compiles(BusinessDay, "sqlite")
def _business_day_sqlite(element, compiler, **kw):
    column = compiler.process(element.clauses, **kw)
    modifiers = "".join(f", '{m}'" for m in _utc_offset_modifiers())
    return f"date({column}{modifiers})"


@compiles(BusinessMonth, "postgresql")
def _business_month_postgresql(element, compiler, **kw):
    column = compiler.process(element.clauses, **kw)
    return f"TO_CHAR(({column}) AT TIME ZONE {_tz_sql_literal()}, 'YYYY-MM')"


@compiles(BusinessMonth, "sqlite")
def _business_month_sqlite(element, compiler, **kw):
    column = compiler.process(element.clauses, **kw)
    modifiers = "".join(f", '{m}'" for m in _utc_offset_modifiers())
    return f"strftime('%Y-%m', {column}{modifiers})"
