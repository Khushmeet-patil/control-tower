"""Calendar dates in the organisation's timezone (config TIMEZONE).

Use today() for anything a person reads as a date: overdue checks, "due soon", allocation on a day.
Comparing against the UTC date would make items overdue (or not) several hours early or late.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import current_app, has_app_context


def today() -> date:
    tz = current_app.config.get("TIMEZONE", "UTC") if has_app_context() else "UTC"
    return datetime.now(ZoneInfo(tz)).date()
