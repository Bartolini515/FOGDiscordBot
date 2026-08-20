import discord
from discord.ext import commands
from db.models.users import Users
from datetime import datetime


class Departure(commands.Cog):
    """Actions for departure of members."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.log_channel_id = self.bot.channels.get("log_channel_id")
    
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild is None:
            return
        if member.guild.id != self.bot.guild_id:
            return
        
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validate db connection
            return
        
        # Change user status on guild to left
        await Users.change_user_on_guild_status(self.bot.db, member.id)
        
        # Log to channel
        if self.log_channel_id:
            log_channel = member.guild.get_channel(self.log_channel_id)
            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="Członek opuścił serwer",
                    description=f"{member.mention} ({member.name}) ({member.id}) opuścił serwer.",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="Opuścił serwer", value=datetime.now().strftime("%Y-%m-%d %H:%M"), inline=False)
                embed.add_field(name="Całkowita liczba członków", value=str(member.guild.member_count), inline=False)
                await log_channel.send(embed=embed)

async def setup(bot:commands.Bot):
    await bot.add_cog(Departure(bot))
