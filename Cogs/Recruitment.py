import os
import discord
import os
import discord
from discord.ext import commands
from discord import app_commands
import logging


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

        is_allowed_user = str(interaction.user.id) in allowed
        is_allowed_role = any(
            (str(r.id) in allowed)
            for r in interaction.user.roles
        )

        if not (is_allowed_user or is_allowed_role or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Nie masz uprawnień do rekrutacji użytkowników.", ephemeral=True)
            return
        
        candidate_role = interaction.guild.get_role(self.bot.roles.get("candidate_role_id"))
        recruit_role = interaction.guild.get_role(self.bot.roles.get("recruit_role_id"))
        if not candidate_role or not recruit_role:
            await interaction.response.send_message("Rola kandydata lub rekruta nie jest skonfigurowana.", ephemeral=True)
            return
        
        await uzytkownik.add_roles(recruit_role)
        await uzytkownik.remove_roles(candidate_role)
        await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} został zrekrutowany i otrzymał rolę Rekrut.", ephemeral=False)
        
        logger.info(
            f"User {interaction.user} ({interaction.user.id}) recruited {uzytkownik} ({uzytkownik.id})"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Recruitment(bot))
    