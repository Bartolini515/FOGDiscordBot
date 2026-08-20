"""Pure configuration and SQL helpers used by administration commands."""

from collections.abc import MutableMapping, MutableSequence, Sequence
from typing import Any

from utils.text import split_response


async def is_bot_owner(interaction: Any) -> bool:
    """Return whether an interaction user matches the configured owner ID."""

    return interaction.user.id == getattr(interaction.client, "owner_id", None)


def format_sql_result(
    description: Sequence[tuple] | None,
    rows: Sequence[tuple],
    rowcount: int,
) -> str:
    """Format a cursor result using the current command output."""

    if description:
        columns = " | ".join(str(column[0]) for column in description)
        if not rows:
            return f"Columns: {columns}\nNo rows returned."
        return "\n".join([f"Columns: {columns}", *(repr(tuple(row)) for row in rows)])
    if rowcount >= 0:
        return f"Statement executed successfully. Rows affected: {rowcount}."
    return "Statement executed successfully."


def split_sql_response(content: str, limit: int = 2_000) -> list[str]:
    """Split SQL output at the Discord message limit."""

    return split_response(content, limit=limit)


def add_permission_entry(
    permissions: MutableMapping[str, list[int]],
    category: str,
    *,
    user_id: int | None = None,
    role_id: int | None = None,
) -> str | None:
    """Append permission IDs and return a status for the cog response."""

    if category not in permissions:
        return "missing_category"
    if user_id is None and role_id is None:
        return "missing_target"
    if user_id is not None:
        if user_id in permissions[category]:
            return "user_exists"
        permissions[category].append(user_id)
    if role_id is not None:
        if role_id in permissions[category]:
            return "role_exists"
        permissions[category].append(role_id)
    return None


def remove_permission_entry(
    permissions: MutableMapping[str, list[int]],
    category: str,
    *,
    user_id: int | None = None,
    role_id: int | None = None,
) -> str | None:
    """Remove permission IDs and return a status for the cog response."""

    if category not in permissions:
        return "missing_category"
    if user_id is None and role_id is None:
        return "missing_target"
    if user_id is not None:
        if user_id not in permissions[category]:
            return "user_missing"
        permissions[category].remove(user_id)
    if role_id is not None:
        if role_id not in permissions[category]:
            return "role_missing"
        permissions[category].remove(role_id)
    return None


def set_channel_mapping(channels: MutableMapping[str, Any], category: str, channel_id: int) -> bool:
    """Set a configured channel ID and report whether the category exists."""

    if category not in channels:
        return False
    channels[category] = channel_id
    return True


def remove_channel_mapping(channels: MutableMapping[str, Any], category: str) -> bool:
    """Clear a configured channel ID and report whether the category exists."""

    if category not in channels:
        return False
    channels[category] = None
    return True


def add_ticket_category(categories: MutableSequence[dict[str, Any]], category: dict[str, Any]) -> None:
    """Append a ticket category to the existing mutable list."""

    categories.append(category)


def remove_ticket_category(categories: MutableSequence[dict[str, Any]], name: str) -> str | None:
    """Remove a custom ticket category, preserving protected/missing statuses."""

    for category in categories:
        if category.get("name") == name:
            if category.get("type") != "custom":
                return "protected"
            categories.remove(category)
            return None
    return "missing"


def edit_trigger(
    triggers: MutableSequence[dict[str, Any]],
    keyword: str,
    *,
    response: str | None = None,
    case_sensitive: bool | None = None,
    whole_word: bool | None = None,
    enabled: bool | None = None,
    cooldown_seconds: int | None = None,
    description: str | None = None,
) -> bool:
    """Edit one trigger in place and report whether it was found."""

    for trigger in triggers:
        if trigger.get("keyword") == keyword:
            if response is not None:
                trigger["response"] = response
            if case_sensitive is not None:
                trigger["case_sensitive"] = case_sensitive
            if whole_word is not None:
                trigger["whole_word"] = whole_word
            if enabled is not None:
                trigger["enabled"] = enabled
            if cooldown_seconds is not None:
                trigger["cooldown_seconds"] = cooldown_seconds
            if description is not None:
                trigger["description"] = description
            return True
    return False


def remove_trigger(triggers: MutableSequence[dict[str, Any]], keyword: str) -> bool:
    """Remove the first trigger with ``keyword`` in place."""

    for trigger in triggers:
        if trigger.get("keyword") == keyword:
            triggers.remove(trigger)
            return True
    return False
