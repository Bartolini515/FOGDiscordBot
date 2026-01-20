import logging
import discord
from discord.ext import commands
from discord import app_commands

logger = logging.getLogger("fogbot")


class ErrorHandler(commands.Cog):
    """Centralization of error handling for prefix and application commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        # Let local command error handlers run if present
        if ctx.command and getattr(ctx.command, "on_error", None):
            return

        # Unwrap original error if it's a CommandInvokeError
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            await ctx.send("Ta komenda nie istnieje.")
            return

        if isinstance(error, commands.DisabledCommand):
            await ctx.send("Ta komenda jest obecnie niedostępna.")
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("Nie masz wymaganych uprawnień do uruchomienia tej komendy.")
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Ta komenda jest na cooldownie. Spróbuj ponownie za {error.retry_after:.1f}s.")
            return

        # Fallback for unhandled errors
        await ctx.send("Wystąpił nieoczekiwany błąd.")
        self.logger.exception("Unhandled command error", exc_info=error)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        # Unwrap original error where available
        orig = getattr(error, "original", error)

        try:
            if isinstance(orig, commands.CommandNotFound):
                msg = "Ta komenda nie istnieje."
            elif isinstance(orig, commands.DisabledCommand):
                msg = "Ta komenda jest obecnie niedostępna."
            elif isinstance(orig, commands.MissingPermissions) or isinstance(orig, app_commands.CheckFailure):
                msg = "Nie masz wymaganych uprawnień do uruchomienia tej komendy."
            elif isinstance(orig, commands.CommandOnCooldown):
                msg = f"Ta komenda jest na cooldownie. Spróbuj ponownie za {orig.retry_after:.1f}s."
            else:
                # Fallback for unhandled errors
                msg = "Wystąpił nieoczekiwany błąd."

            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        except Exception:
            # If error occurs while sending the response, log it
            self.logger.exception("Error while handling app command error", exc_info=error)
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("Wystąpił nieoczekiwany błąd.", ephemeral=True)
                else:
                    await interaction.response.send_message("Wystąpił nieoczekiwany błąd.", ephemeral=True)
            except Exception:
                # Give up silently if we cannot notify the user
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandler(bot))
