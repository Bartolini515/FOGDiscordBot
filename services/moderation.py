"""Pure moderation and role-policy decisions."""

from datetime import datetime, timedelta
from collections.abc import Iterable
from typing import Protocol

from discord import app_commands
from discord.ext import commands


class RoleLike(Protocol):
    id: int

    def is_default(self) -> bool:
        """Return whether this is the guild default role."""


def blacklist_expiration(duration_days: int | None, *, now: datetime | None = None) -> tuple[datetime | None, str | None]:
    """Return the expiration datetime and stored string used by blacklist writes."""

    current_time = datetime.now() if now is None else now
    expiration = current_time + timedelta(days=duration_days) if duration_days else None
    return expiration, expiration.strftime("%Y-%m-%d %H:%M") if expiration else None


def format_blacklist_time_left(end_at: str | None, *, now: datetime | None = None) -> str:
    """Format remaining blacklist days using the current ``-1`` expired rule."""

    if not end_at:
        return "Nieskończony"
    end_date = datetime.fromisoformat(end_at)
    current_time = datetime.now() if now is None else now
    delta = end_date - current_time
    return str(delta.days) if delta.days > 0 else "-1"


def should_enforce_role_whitelist(before_roles: Iterable[RoleLike], candidate_role_id: int, other_group_role_id: int) -> bool:
    """Return whether the previous roles include a protected group role."""

    return any(role.id in (candidate_role_id, other_group_role_id) for role in before_roles)


def roles_to_remove(after_roles: Iterable[RoleLike], whitelist_role_ids: Iterable[int]) -> list[RoleLike]:
    """Select non-default roles outside the configured whitelist."""

    allowed = set(whitelist_role_ids)
    return [role for role in after_roles if not role.is_default() and role.id not in allowed]


def command_error_message(error: Exception) -> str | None:
    """Map known command failures to the existing user-facing messages."""

    if isinstance(error, commands.CommandNotFound):
        return "Ta komenda nie istnieje."
    if isinstance(error, commands.DisabledCommand):
        return "Ta komenda jest obecnie niedostępna."
    if isinstance(error, commands.MissingPermissions) or isinstance(error, app_commands.CheckFailure):
        return "Nie masz wymaganych uprawnień do uruchomienia tej komendy."
    if isinstance(error, commands.CommandOnCooldown):
        return f"Ta komenda jest na cooldownie. Spróbuj ponownie za {error.retry_after:.1f}s."
    return None
