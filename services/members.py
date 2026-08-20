"""Reusable member and guild workflow decisions."""

from collections.abc import Collection, Iterable, Mapping
from typing import Any, Protocol


class InviteLike(Protocol):
    code: str
    uses: int


def is_target_guild(guild: object | None, guild_id: int) -> bool:
    """Return whether a Discord guild-like value has the configured ID."""

    return guild is not None and getattr(guild, "id", None) == guild_id


def invite_snapshot(invites: Iterable[InviteLike]) -> dict[str, int]:
    """Capture invite use counts keyed by invite code."""

    return {str(invite.code): int(invite.uses) for invite in invites}


def find_used_invite(before: Mapping[str, int], after: Iterable[InviteLike]) -> InviteLike | None:
    """Find the first invite whose use count increased or was newly created."""

    for invite in after:
        if invite.code in before:
            if invite.uses > before[invite.code]:
                return invite
        elif invite.uses > 0:
            return invite
    return None


def has_configured_permission(user: object, allowed: Collection[int]) -> bool:
    """Allow a user ID, one of their role IDs, or an administrator."""

    if getattr(user, "id", None) in allowed:
        return True
    if any(role.id in allowed for role in getattr(user, "roles", ())):
        return True
    permissions = getattr(user, "guild_permissions", None)
    return bool(getattr(permissions, "administrator", False))


def format_member_message(template: str, member: Any) -> str:
    """Format a configured member message with the existing placeholders."""

    guild = member.guild
    return template.format(
        mention=member.mention,
        name=member.name,
        id=member.id,
        guild=guild.name,
        display_name=member.display_name,
    )
