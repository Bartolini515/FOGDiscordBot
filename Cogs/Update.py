import discord
from discord.ext import commands
from db.models.users import Users
from services.members import is_target_guild


class Update(commands.Cog):
    """Actions for updating users data."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not is_target_guild(after.guild, self.bot.guild_id):
            return
        if before.name != after.name:
            await Users.update_username(self.bot.db, after.id, after.name)
            
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not is_target_guild(message.guild, self.bot.guild_id):
            return
        if message.author.bot:
            return
        await Users.update_last_message_at(self.bot.db, message.author.id, message.created_at.isoformat().split(".")[0])
        

async def setup(bot:commands.Bot):
    await bot.add_cog(Update(bot))
