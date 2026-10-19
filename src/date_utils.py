"""
Shared date and time helpers for AI-Powered Personal Task Manager.

Centralizes normalization and display rules so the repository, service,
tool validation, mock LLM, and formatters all agree.

Storage conventions:
- ``due_date``: ISO date string ``YYYY-MM-DD``
- ``due_time``: normalized 24-hour time string ``HH:MM`` (nullable)
- ``due_period``: one of ``morning``, ``afternoon``, ``evening``, ``night``
  (nullable).  An approximate period is never converted into an exact time.
"""

import re
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIME_PERIODS = ("morning", "afternoon", "evening", "night")

_PERIOD_ALIASES = {
    "morning": "morning",
    "am": "morning",
    "afternoon": "afternoon",
    "pm": "afternoon",
    "evening": "evening",
    "tonight": "evening",
    "night": "night",
}

_TIME_12H_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?$")
_TIME_24H_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def timezone_object(timezone_name: str) -> ZoneInfo:
    """Return a ZoneInfo for ``timezone_name`` or raise a clear ValueError."""
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"Unknown TIMEZONE {timezone_name!r}. "
            "Use an IANA name such as 'UTC' or 'Asia/Kolkata'."
        ) from exc


def today_in_timezone(timezone_name: str) -> date:
    """Return today's date in the explicitly configured timezone."""
    return datetime.now(timezone_object(timezone_name)).date()


def normalize_time_value(value: object) -> Optional[str]:
    """
    Normalize a time value to ``HH:MM`` (24-hour).

    Accepts ``3 PM``, ``3:30 PM``, ``15:00``, ``10 AM``, and ``15:00:00``.
    Returns ``None`` for ``None`` or an empty string.  Raises ValueError with
    a user-safe message for invalid or ambiguous values.
    """
    if value is None:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    match = _TIME_12H_RE.match(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if not 1 <= hour <= 12:
            raise ValueError(
                f"Invalid time {value!r}: 12-hour clock hours must be 1-12."
            )
        if minute > 59:
            raise ValueError(f"Invalid time {value!r}: minutes must be 00-59.")
        if meridiem == "p" and hour != 12:
            hour += 12
        elif meridiem == "a" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    match = _TIME_24H_RE.match(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            raise ValueError(f"Invalid time {value!r}: use 00:00-23:59.")
        return f"{hour:02d}:{minute:02d}"

    if text in {"noon", "midday"}:
        return "12:00"
    if text == "midnight":
        return "00:00"

    raise ValueError(
        f"Invalid time {value!r}. Use a 12-hour value such as '3 PM' or a "
        "24-hour value such as '15:00'."
    )


def normalize_period_value(value: object) -> Optional[str]:
    """
    Normalize an approximate period to one of TIME_PERIODS.

    Returns ``None`` for ``None`` or an empty string.  Raises ValueError for
    anything outside the supported set.
    """
    if value is None:
        return None

    text = str(value).strip().lower().rstrip(".")
    if not text:
        return None

    period = _PERIOD_ALIASES.get(text)
    if period is None:
        allowed = ", ".join(TIME_PERIODS)
        raise ValueError(
            f"Invalid period {value!r}. Expected one of: {allowed}."
        )
    return period


def format_time_12h(value: str) -> str:
    """Display a normalized ``HH:MM`` value as a readable 12-hour time."""
    normalized = normalize_time_value(value)
    if normalized is None:
        return ""
    hour, minute = (int(part) for part in normalized.split(":"))
    meridiem = "AM" if hour < 12 else "PM"
    hour_12 = hour % 12 or 12
    return f"{hour_12}:{minute:02d} {meridiem}"


def format_due(
    due_date: object,
    due_time: Optional[str] = None,
    due_period: Optional[str] = None,
) -> str:
    """
    Format a due date plus optional time/period for display.

    Examples:
        2026-10-20
        2026-10-20 at 3:00 PM
        2026-10-20 (evening)
    """
    base = due_date.isoformat() if isinstance(due_date, date) else str(due_date)

    if due_time:
        try:
            return f"{base} at {format_time_12h(str(due_time))}"
        except ValueError:
            return f"{base} at {due_time}"
    if due_period:
        return f"{base} ({due_period})"
    return base
