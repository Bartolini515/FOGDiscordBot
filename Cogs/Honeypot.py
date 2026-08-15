import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("fogbot")

class HoneypotCog(commands.Cog):
    """Honeypot trap mechanism for catching automated bots."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.tracked_channels = {channel_id for channel_id in self.bot.honeypot_system["honeypot_channels"]}
        self.trap_counter = self.bot.honeypot_system.get("trap_counter", 0)
        self.counter_messages = [
            entry for entry in self.bot.honeypot_system.get("counter_messages", [])
            if isinstance(entry, dict)
            and entry.get("channel_id") is not None
            and entry.get("message_id") is not None
        ]

    async def _update_counter_messages(self):
        if not self.counter_messages:
            return

        for entry in self.counter_messages:
            if not isinstance(entry, dict):
                continue

            channel_id = entry.get("channel_id")
            message_id = entry.get("message_id")
            if not channel_id or not message_id:
                continue

            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                message = await channel.fetch_message(message_id)
                await message.edit(content=f"Obecna ilość banów: {self.trap_counter}")
            except discord.NotFound:
                self.counter_messages = [
                    item for item in self.counter_messages
                    if not (isinstance(item, dict) and item.get("channel_id") == channel_id)
                ]
                self.bot.honeypot_system["counter_messages"] = self.counter_messages
            except discord.Forbidden:
                logger.warning(f"Missing permissions to update counter message in {channel.name}.")

    async def _remove_counter_message(self, channel: discord.TextChannel):
        if not isinstance(channel, discord.TextChannel):
            return

        existing_entry = next(
            (
                entry for entry in self.counter_messages
                if isinstance(entry, dict) and entry.get("channel_id") == channel.id
            ),
            None,
        )

        if existing_entry is None:
            return

        try:
            message = await channel.fetch_message(existing_entry["message_id"])
            await message.delete()
        except discord.NotFound:
            pass

        self.counter_messages = [
            entry for entry in self.counter_messages
            if not (isinstance(entry, dict) and entry.get("channel_id") == channel.id)
        ]
        self.bot.honeypot_system["counter_messages"] = self.counter_messages

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in self.tracked_channels:
            return
        if message.author.guild_permissions.administrator:
            return

        user = message.author

        logger.info(f"Bot detected in honeypot channel {message.channel.name} ({message.channel.id}) - {user} ({user.id}).")

        self.trap_counter += 1
        self.bot.honeypot_system["trap_counter"] = self.trap_counter

        await self._update_counter_messages()

        if isinstance(user, discord.Member) and message.guild is not None:
            try:
                await message.guild.ban(user, reason="Automated bot detected", delete_message_seconds=300)
            except discord.NotFound:
                logger.info(f"Could not ban {user} because the user is no longer present.")

    # /honeypot_trap_add
    @app_commands.command(
        name="honeypot_trap_add",
        description="Ustala kanał jako honeypot trap, który automatycznie banuje boty",
        extras={"category": "Honeypot"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def honeypot_trap_add(self, interaction: discord.Interaction):
        channel = interaction.channel
        if channel.id in self.tracked_channels:
            await interaction.response.send_message("Ten kanał jest już honeypot trapem.", ephemeral=True)
            return
        
        self.tracked_channels.add(channel.id)
        self.bot.honeypot_system["honeypot_channels"].append(channel.id)

        message = await channel.send(f"Obecna ilość banów: {self.trap_counter}")
        self.counter_messages.append({"channel_id": channel.id, "message_id": message.id})
        self.bot.honeypot_system["counter_messages"] = self.counter_messages

        await interaction.response.send_message(f"Kanał {channel.mention} został dodany do honeypot traps.", ephemeral=True)

    # /honeypot_trap_delete
    @app_commands.command(
        name="honeypot_trap_delete",
        description="Usuwa kanał z listy honeypot traps.",
        extras={"category": "Honeypot"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def honeypot_trap_delete(self, interaction: discord.Interaction):
        channel = interaction.channel
        if channel.id not in self.tracked_channels:
            await interaction.response.send_message("Ten kanał nie jest honeypot trapem.", ephemeral=True)
            return
        
        self.tracked_channels.remove(channel.id)
        self.bot.honeypot_system["honeypot_channels"].remove(channel.id)
        await self._remove_counter_message(channel)

        await interaction.response.send_message(f"Kanał {channel.mention} został usunięty z honeypot traps.", ephemeral=True)

async def setup(bot:commands.Bot):
    await bot.add_cog(HoneypotCog(bot))