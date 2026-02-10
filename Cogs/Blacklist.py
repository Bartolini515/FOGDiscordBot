import discord
from discord.ext import commands
from discord import app_commands
from db.models import Blacklist
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("fogbot")

class BlacklistCog(commands.Cog):
    """Actions for departure of members."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot

    
    # /blacklist_dodaj
    @app_commands.command(
        name="blacklist_dodaj",
        description="Dodaje użytkownika do blacklisty oraz wyrzuca go z serwera.",
        extras={"category": "Blacklist"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(uzytkownik="Użytkownik do dodania do blacklisty.", powod="Powód dodania do blacklisty.", czas_trwania="Czas trwania w dniach (opcjonalnie).")
    async def blacklist_dodaj(self, interaction: discord.Interaction, uzytkownik: discord.User, powod: str, czas_trwania: int | None = None):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        czas_trwania_date = datetime.now() + timedelta(days=czas_trwania) if czas_trwania else None
        await Blacklist.add_to_blacklist(self.bot.db, uzytkownik.id, powod, czas_trwania_date.strftime("%Y-%m-%d %H:%M:%S") if czas_trwania_date else None)
        await interaction.response.send_message(f"Użytkownik {uzytkownik.name} został dodany do blacklisty.", ephemeral=True)
        try:
            await uzytkownik.send(f"Zostałeś dodany do blacklisty FOG.\nPowód: {powod}.\nKoniec blokady: {czas_trwania_date.strftime('%Y-%m-%d %H:%M:%S') if czas_trwania_date else 'Nieskończony'}.")
            await uzytkownik.kick(reason=f"Użytkownik został dodany do blacklisty. Powód: {powod}.")
        except Exception as e:
            logger.warning(f"Could not send blacklist notification and kick {uzytkownik.name}: {e}")
        logger.info(f"User {uzytkownik.name} added to blacklist by {interaction.user.name} for reason: {powod}, duration: {czas_trwania} days.")
        
    # /blacklist_usun
    @app_commands.command(
        name="blacklist_usun",
        description="Usuwa użytkownika z blacklisty.",
        extras={"category": "Blacklist"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user_id="ID użytkownika do usunięcia z blacklisty.")
    async def blacklist_usun(self, interaction: discord.Interaction, user_id: str):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        await Blacklist.remove_from_blacklist(self.bot.db, int(user_id))
        await interaction.response.send_message(f"Użytkownik o id **{user_id}** został usunięty z blacklisty.", ephemeral=True)
        logger.info(f"User {user_id} removed from blacklist by {interaction.user.name}.")
        
    # /blacklist_pokaz
    @app_commands.command(
        name="blacklist_pokaz",
        description="Pokazuje wszystkich użytkowników na blacklistie.",
        extras={"category": "Blacklist"},
    )
    @app_commands.guild_only()
    async def blacklist_pokaz(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        blacklist_entries = await Blacklist.list(self.bot.db)
        if not blacklist_entries:
            await interaction.response.send_message("Blacklista jest pusta.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Blacklista użytkowników",
            color=discord.Color.red()
        )
        for entry in blacklist_entries:
            user_id, reason, added_at, expires_at, username = entry
            username = f"{username} ({user_id})"
            expires_str = expires_at if expires_at else "Nigdy"
            embed.add_field(name=username, value=f"Powód: {reason}\nDodany: {str(added_at).split( )[0]}\nWygasa: {expires_str}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot:commands.Bot):
    await bot.add_cog(BlacklistCog(bot))