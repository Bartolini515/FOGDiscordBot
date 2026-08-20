"""Pure command help filtering and categorization."""

import discord
from discord import app_commands


def command_category(command: app_commands.Command) -> str:
    """Return the configured command category or its fallback."""

    extras = getattr(command, "extras", None)
    if extras:
        category = extras.get("category")
        if isinstance(category, str) and category.strip():
            return category

    if isinstance(command.parent, app_commands.Group):
        return command.parent.name

    return "Inne"


def user_can_see_command(interaction: discord.Interaction, command: app_commands.Command) -> bool:
    """Return whether a member satisfies a command's default permissions."""

    default_permissions: discord.Permissions | None = getattr(command, "default_permissions", None)
    if default_permissions is None:
        return True
    return default_permissions.is_subset(getattr(interaction.user, "guild_permissions", discord.Permissions.none()))
