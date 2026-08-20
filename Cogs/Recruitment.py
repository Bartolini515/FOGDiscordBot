import os
import discord
from discord.ext import commands
from discord import app_commands
import logging
from services.members import format_member_message, has_configured_permission


logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"

class Recruitment(commands.Cog):
    """Trainings logic and commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    
    # TODO: Test this
    # /rekrutacja
    @app_commands.command(
        name="rekrutacja",
        description="Rekrutuje użytkownika oraz nadaje rolę kandydata.",
        extras={"category": "Rekrutacja"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        uzytkownik="Użytkownik, którego chcesz zrekrutować."
    )
    async def rekrutacja(self, interaction: discord.Interaction, uzytkownik: discord.Member):
        # Permission check: allow if user is explicitly allowed OR has an allowed role OR is admin
        allowed = self.bot.permissions.get("recruiters", [])

        if not has_configured_permission(interaction.user, allowed):
            await interaction.response.send_message("Nie masz uprawnień do rekrutacji użytkowników.", ephemeral=True)
            return
        
        candidate_role = interaction.guild.get_role(self.bot.roles.get("candidate_role_id"))
        recruit_role = interaction.guild.get_role(self.bot.roles.get("recruit_role_id"))
        if not candidate_role or not recruit_role:
            await interaction.response.send_message("Rola kandydata lub rekruta nie jest skonfigurowana.", ephemeral=True)
            return
        
        await uzytkownik.remove_roles(candidate_role)
        await uzytkownik.add_roles(recruit_role)
        
        recruitment_message = self.bot.messages.get("recruitment_message", "Gratulacje! Zostałeś zrekrutowany i otrzymałeś rolę Rekrut stając się pełnoprawnym członkiem grupy FOG!")
        recruitment_message = format_member_message(recruitment_message, uzytkownik)
        
        await uzytkownik.send(recruitment_message)
        
        await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} został zrekrutowany i otrzymał rolę Rekrut.", ephemeral=True)
        
        logger.info(
            f"User {interaction.user} ({interaction.user.id}) recruited {uzytkownik} ({uzytkownik.id})"
        )
        
    # /szwi
    @app_commands.command(
        name="szwi",
        description="Nadaje użytkownikowi SzWI.",
        extras={"category": "Rekrutacja"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        uzytkownik="Użytkownik, któremu chcesz nadawać SzWI."
    )
    async def szwi(self, interaction: discord.Interaction, uzytkownik: discord.Member):
        # Permission check: allow if user is explicitly allowed OR has an allowed role OR is admin
        allowed = self.bot.permissions.get("basic_training_tickets_managers", []) + self.bot.permissions.get("recruiters", [])

        if not has_configured_permission(interaction.user, allowed):
            await interaction.response.send_message("Nie masz uprawnień do wysyłania wiadomości do użytkowników.", ephemeral=True)
            return
        
        szwi_role = interaction.guild.get_role(self.bot.roles.get("szwi_role_id"))
        await uzytkownik.add_roles(szwi_role)
        
        recruitment_message = self.bot.messages.get("szwi_message", "Gratulacje! Przeszedłeś szkolenie podstawowe i jesteś gotowy do udziału w misjach grupy FOG!\n")
        recruitment_message = format_member_message(recruitment_message, uzytkownik)
        
        await uzytkownik.send(recruitment_message)
        
        await interaction.response.send_message(f"Użytkownikowi {uzytkownik.mention} nadano rolę SzWI.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Recruitment(bot))
