import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from db.models.users import Users
from db.models.warns import Warns


logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"

class WarnsCog(commands.Cog):
    """Warns logic and commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    # /warn_add
    @app_commands.command(
        name="warn_add",
        description="Dodaje warna użytkownikowi.",
        extras={"category": "Warny"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        uzytkownik="Użytkownik, któremu chcesz dodać warna.",
        powod="Powód dodania warna."
    )
    async def warn_add(self, interaction: discord.Interaction, uzytkownik: discord.User, powod: str):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        # Add the warn to the database
        await Warns.create(self.bot.db, user_id=uzytkownik.id, reason=powod)
        logger.info(f"Added warn to user {uzytkownik} for reason: {powod}")
        
        # Get user's current warn count and send a response
        row = await Users.get_user(self.bot.db, user_id=uzytkownik.id)
        warn_count = row[8] if row else 0
        await interaction.response.send_message(f"Dodano warna użytkownikowi {uzytkownik.mention} za powód: {powod}.\nObecna liczba warnów: {warn_count}.")
        
    # /warn_remove
    @app_commands.command(
        name="warn_remove",
        description="Usuwa warna użytkownikowi.",
        extras={"category": "Warny"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        warn_id="ID warna, który chcesz usunąć."
    )
    async def warn_remove(self, interaction: discord.Interaction, warn_id: int):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        warn = await Warns.get(self.bot.db, id=warn_id)
        if not warn:
            await interaction.response.send_message(f"Nie znaleziono warna o ID {warn_id}.")
            return
        
        await Warns.delete(self.bot.db, id=warn_id)
        await interaction.response.send_message(f"Warn o ID {warn_id} został usunięty.", ephemeral=True)
        logger.info(f"Removed warn with ID {warn_id} for user ID {warn[1]}")

    # /warn_check
    @app_commands.command(
        name="warn_check",
        description="Sprawdza warny użytkownika.",
        extras={"category": "Warny"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        uzytkownik="Użytkownik, którego warny chcesz sprawdzić."
    )
    async def warn_check(self, interaction: discord.Interaction, uzytkownik: discord.User):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        await Warns.recalculate_expired(self.bot.db) # Recalculate expired warns before fetching the list
        
        rows = await Warns.get_by_user_id(self.bot.db, user_id=uzytkownik.id)
        if not rows:
            await interaction.response.send_message(f"{uzytkownik.mention} nie ma żadnych warnów.")
            return
        
        embed = discord.Embed(title=f"Warny użytkownika {uzytkownik}", color=discord.Color.orange())
        for warn in rows:
            embed.add_field(name=f"Warn ID: {warn[0]}", value=f"Powód: {warn[2]}\nDodany: {warn[3].split(' ')[0]}\nWygasł: {'Tak' if warn[4] else 'Nie'}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    # /warn_list_users
    @app_commands.command(
        name="warn_list_users",
        description="Wyświetla listę użytkowników z warnami.",
        extras={"category": "Warny"},
    )
    @app_commands.guild_only()
    async def warn_list_users(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        await Warns.recalculate_expired(self.bot.db) # Recalculate expired warns before fetching the list
        
        users_with_warns = await Users.get_warned_users(self.bot.db)
        if not users_with_warns:
            await interaction.response.send_message("Brak użytkowników z warnami.")
            return
        
        embed = discord.Embed(title="Użytkownicy z warnami", color=discord.Color.orange())
        for user_id, username, warn_count in users_with_warns:
            embed.add_field(name=username, value=f"Liczba warnów: {warn_count}", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
async def setup(bot: commands.Bot):
    await bot.add_cog(WarnsCog(bot))
