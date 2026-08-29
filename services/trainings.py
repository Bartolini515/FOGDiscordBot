"""Pure training attendance and signup-message transformations."""

import datetime
from collections.abc import Iterable


def training_message_content(training_name: str, date_str: str | None, user_ids: Iterable[int]) -> str:
    """Render the persistent training signup message."""

    header = f"📋 Zapisz się na szkolenie **{training_name}** {date_str}".strip()
    lines = [header]
    users = list(user_ids)
    if not users:
        lines.append("_Brak zapisanych._")
    else:
        for user_id in users:
            lines.append(f"- <@{user_id}>")
    return "\n".join(lines)


def normalize_training_date(value: str) -> str:
    """Normalize the command date to the existing SQLite string format."""

    parsed = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")
    return parsed.isoformat(sep=" ")


def training_present_user_ids(rows: Iterable[tuple], absent_users: Iterable[str]) -> list[int]:
    """Return signed users who are not listed as absent."""

    absent = set(absent_users)
    return [int(row[2]) for row in rows if str(row[2]) not in absent]


def format_training_attendance(
    training_name: str,
    training_date: str | None,
    rows: Iterable[tuple],
    absent_users: Iterable[str],
) -> str:
    """Render the training attendance report while listing every signup."""

    absent = set(absent_users)
    all_user_ids = [int(row[2]) for row in rows if row[2] is not None]
    lines = [f"📌 Obecność na szkoleniu **{training_name}** {training_date}".strip()]
    for user_id in all_user_ids:
        status = "✅ obecny" if str(user_id) not in absent else "❌ nieobecny"
        lines.append(f"- <@{user_id}> — {status}")
    return "\n".join(lines)
