"""Timezone handling — one source of truth for "which day is it".

Timestamps are stored in UTC (timestamptz). Every question of the form
"today", "this month", or "which date does this order belong to" is
answered in the business timezone (APP_TIMEZONE, default Asia/Dhaka),
so a Bangladeshi seller's day flips at Dhaka midnight — not at 6am.

Never call date.today() or construct timezone-aware datetimes ad hoc
in route code; use these helpers so the zones can't get mixed again.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, literal_column

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
    """Aware-UTC instants [start, end) covering a calendar day in the
    business timezone."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=_tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def month_start_utc() -> datetime:
    """Aware-UTC instant of the start of the current business-timezone
    month (where the free-plan monthly quota meter resets)."""
    now_local = business_now()
    start_local = datetime(now_local.year, now_local.month, 1, tzinfo=_tz)
    return start_local.astimezone(timezone.utc)


def to_business_time(utc: datetime) -> datetime:
    """Convert a stored UTC timestamp to business-local time — for
    display to the seller (e.g. CSV export dates). Every datetime the
    database returns is timezone-aware (timestamptz)."""
    return utc.astimezone(_tz)


# ---------------------------------------------------------------------------
# SQL-side date grouping.
#
# Route code groups rows by business-local day/month with
# business_day(Order.created_at) / business_month(...). The server (not
# Python) owns the calendar math, so an order at 20:00 UTC lands on the
# seller's next local day in the chart.
# ---------------------------------------------------------------------------


def _tz_sql_literal() -> str:
    """The business timezone as a safely-quoted SQL string literal."""
    return "'" + get_settings().app_timezone.replace("'", "''") + "'"


def _at_business_tz(column):
    """SQL: a stored timestamptz shifted to a naive business-local
    timestamp (timestamptz AT TIME ZONE '<tz>')."""
    return column.op("AT TIME ZONE")(literal_column(_tz_sql_literal()))


def business_day(column):
    """SQL: the business-local calendar date of a stored UTC timestamp
    — CAST(created_at AT TIME ZONE '<tz>' AS DATE)."""
    return cast(_at_business_tz(column), Date)


def business_month(column):
    """SQL: the business-local 'YYYY-MM' of a stored UTC timestamp
    — TO_CHAR(created_at AT TIME ZONE '<tz>', 'YYYY-MM')."""
    return func.to_char(_at_business_tz(column), "YYYY-MM")
