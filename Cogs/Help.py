from collections import defaultdict
import discord
from discord.ext import commands
from discord import app_commands


class Help(commands.Cog):
    """Help command to display available commands."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        
    def _category_for(self, command: app_commands.Command) -> str:
        # Try to get category from command extras
        if getattr(command, "extras", None):
            category = command.extras.get("category")
            if isinstance(category, str) and category.strip():
                return category

        # Else if command is part of a group, return the group name
        if isinstance(command.parent, app_commands.Group):
            return command.parent.name

        return "Inne"

    # TODO: Test if works
    def _user_can_see(self, interaction: discord.Interaction, command: app_commands.Command) -> bool:
        dp: discord.Permissions | None = getattr(command, "default_permissions", None)
        if dp is None:
            return True

        user_perms = interaction.user.guild_permissions
        return dp.is_subset(user_perms)


    @app_commands.command(
        name="help",
        description="Pokazuje listę dostępnych komend",
    )
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Dostępne komendy", color=discord.Color.blue())

        guild = discord.Object(id=self.bot.guild_id)
        grouped: dict[str, list[app_commands.Command]] = defaultdict(list)

        for cmd in self.bot.tree.walk_commands(guild=guild):
            if not isinstance(cmd, app_commands.Command):
                continue
            if not self._user_can_see(interaction, cmd):
                continue

            grouped[self._category_for(cmd)].append(cmd)

        if not grouped:
            embed.description = "Brak dostępnych komend."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        for category in sorted(grouped.keys(), key=str.lower):
            cmds = sorted(grouped[category], key=lambda c: c.qualified_name.lower())
            lines = [f"`/{c.qualified_name}` — {c.description or '—'}" for c in cmds]
            embed.add_field(name=category, value="\n".join(lines), inline=False)
        
        embed.description = "Aby uzyskać więcej informacji skorzystaj z dokumentacji klikając [tutaj](https://docs.google.com/document/d/1WYjFjQWeEHbatsnRmbGqsi6jPRKrT3yajF-v5BlGVEw/edit?usp=sharing)"

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot:commands.Bot):
    await bot.add_cog(Help(bot))