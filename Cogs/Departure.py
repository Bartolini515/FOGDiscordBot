import discord
from discord.ext import commands
from discord import app_commands
from db.models import Users


class Departure(commands.Cog):
    """Actions for departure of members."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot


    # Don't implement until new structure is ready
    # TODO: Log Departures to specified channel
    # TODO: Perform cleanups from queues etc.
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild is None:
            return
        if member.guild.id != self.bot.guild_id:
            return
        
        await Users.change_user_on_guild_status(self.bot.db, member.id)

async def setup(bot:commands.Bot):
    await bot.add_cog(Departure(bot))