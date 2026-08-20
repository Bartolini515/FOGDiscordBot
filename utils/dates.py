"""Date parsing helpers shared by mission and training commands."""

import datetime


def normalize_datetime(value: str) -> str:
    """Normalize a user-entered date to the existing SQLite string format."""

    parsed = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")
    return parsed.isoformat(sep=" ")
