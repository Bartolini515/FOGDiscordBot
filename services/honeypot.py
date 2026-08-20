"""Pure honeypot counter state transformations."""

from collections.abc import Iterable
from typing import Any


def valid_counter_entries(entries: Iterable[object]) -> list[dict[str, Any]]:
    """Keep only counter records with both required IDs."""

    return [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("channel_id") is not None
        and entry.get("message_id") is not None
    ]


def counter_entries_for_channel(entries: Iterable[dict[str, Any]], channel_id: int) -> list[dict[str, Any]]:
    """Return counter records excluding the selected channel."""

    return [
        entry
        for entry in entries
        if entry.get("channel_id") != channel_id
    ]
