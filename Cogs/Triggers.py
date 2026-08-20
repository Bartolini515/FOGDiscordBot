import discord
from discord.ext import commands
from os import getenv
import logging
from services.members import is_target_guild
from services.triggers import matching_trigger_responses

logger = logging.getLogger("fogbot")
debug = getenv("DEBUG", "False") == "True"

class Triggers(commands.Cog):
    """Custom actions triggered by key words in messages."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.last_triggered_times = {} 
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not is_target_guild(message.guild, self.bot.guild_id):
            return
        if message.author.bot:
            return
        
        # Triggers
        # goc -> giphy "fazzer cwel"
        # if message.content.lower().find("goc") != -1:
        #     await message.channel.send("https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExZmN0YjN4OWRlMjU1ZTBrbm92djNtcTVpOG94aGoydzFibTgzbnl0eiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/48kPcmFdifFLHGI1xK/giphy.gif")
            
        # # kisne -> giphy "kacper kisne"
        # if message.content.lower().find("kisne") != -1:
        #     await message.channel.send("https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3kwM3UyMDRtMmRhOXVvdWVhNGw1NWV2ZGppNHdsbDl6Z242ZmE3ZCZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/tNWfeZVEIcG1lmP9Xr/giphy.gif")
        
        # # schildkrote -> giphy "sad spiderman walking"
        # if message.content.lower().find("schildkrote") != -1:
        #     await message.channel.send("https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExajFvb2RiMm8zZW41OXpsenJ5YjNzcGYybWtpdHo0OXNqNmNrMjllciZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/ZgI5P6a3ZBKgSaqmwl/giphy.gif")
            
        # # dewastacja -> tenor "ffs baby sad just stop"
        # if message.content.lower().find("dewastacja") != -1:
        #     await message.channel.send("https://tenor.com/view/ffs-baby-really-oh-god-just-stop-gif-12739180")
            
        # # ukrainiec -> tenor "fish sleeping"
        # if message.content.lower().find("ukrainiec") != -1:
        #     await message.channel.send("https://tenor.com/view/fish-sleeping-gif-7324897647942850226")
        
        
        if debug:
            logger.debug(f"Message content: {message.content}")
            logger.debug(f"Available triggers: {self.bot.message_triggers}")
            logger.debug(f"last_triggered_times: {self.last_triggered_times}")
        
        if not self.bot.message_triggers:
            return

        responses = matching_trigger_responses(
            self.bot.message_triggers,
            message.content,
            self.last_triggered_times,
            now=discord.utils.utcnow().timestamp(),
        )
        for response in responses:
            await message.channel.send(response)
                

async def setup(bot:commands.Bot):
    await bot.add_cog(Triggers(bot))
