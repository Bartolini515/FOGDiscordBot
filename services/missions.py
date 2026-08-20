"""Pure mission date, roster, slot, and persistent-ID helpers."""

import datetime
from collections.abc import Iterable


def mission_message_content(slots_dict: dict[int, tuple[int, str, int | None]], squad: str) -> str:
    """Render one squad's positional slot rows as the Discord roster message."""

    header = f"📋 Zapisz się do drużyny **{squad}**:"
    lines = [header]
    for _, (_, label, user) in slots_dict.items():
        mention = f"<@{user}>" if user else "_wolny_"
        status = "✅" if user else "❌"
        lines.append(f"- {label}  {status} - {mention}")
    return "\n".join(lines)


def parse_mission_date(value: str) -> datetime.datetime:
    """Parse the command's minute-precision mission date."""

    return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")


def parse_stored_mission_date(value: str) -> datetime.datetime:
    """Parse either stored mission date precision accepted by the cog."""

    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M")


def signout_is_too_close(mission_date: datetime.datetime, *, now: datetime.datetime | None = None) -> bool:
    """Return whether self-service sign-out is inside the 12-hour cutoff."""

    current_time = datetime.datetime.now() if now is None else now
    return mission_date < current_time + datetime.timedelta(hours=12)


def parse_signup_slots(value: str) -> list[str]:
    """Normalize semicolon-delimited signup slot names."""

    return [slot.strip() for slot in value.split(";") if slot.strip()]


def build_slot_mapping(slots: Iterable[str], max_slot_id: int | None) -> dict[int, tuple[int, str, None]]:
    """Build the same temporary slot mapping used before the DB write."""

    start = max_slot_id + 1 if max_slot_id else 0
    return {slot_id: (slot_id, slot, None) for slot_id, slot in enumerate(slots, start=start)}


def mission_select_custom_id(message_id: int) -> str:
    """Build the persistent mission selector custom ID."""

    return f"mission_select_{message_id}"


def signout_custom_id(message_id: int) -> str:
    """Build the persistent mission sign-out custom ID."""

    return f"signout_button_{message_id}"
