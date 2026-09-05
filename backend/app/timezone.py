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

    Returned naive: SQLite stores created_at as naive-UTC strings, and
    naive bounds keep query-side string comparisons exact (no "+00:00"
    suffix mismatch at the boundary second).
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


def to_business_time(utc_naive: datetime) -> datetime:
    """Convert a stored naive-UTC timestamp to business-local time —
    for display to the seller (e.g. CSV export dates)."""
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(_tz)


def sqlite_shift_modifiers() -> list[str]:
    """SQLite date() modifiers that shift a UTC timestamp into the
    business timezone — lets SQL group rows by business-local date.

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
