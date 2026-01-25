import discord
from discord.ext import commands
from discord import app_commands
from os import getenv
import logging

logger = logging.getLogger("fogbot")
debug = getenv("DEBUG", "False") == "True"

class Triggers(commands.Cog):
    """Custom actions triggered by key words in messages."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.last_triggered_times = {} 
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if message.guild.id != self.bot.guild_id:
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

        for trigger in self.bot.message_triggers: # Iterate through each trigger
            if not trigger.get("enabled", False): # Skip if trigger is not enabled
                if debug:
                    logger.debug(f"Trigger '{trigger.get('keyword', '')}' is not enabled, skipping.")
                continue
            
            if trigger.get("case_sensitive", False): # Check case sensitivity
                if debug:
                    logger.debug(f"Trigger '{trigger.get('keyword', '')}' is case sensitive.")
                keyword = trigger.get("keyword", "")
            else:
                keyword = trigger.get("keyword", "").lower()
            
            if keyword == "": # Skip if keyword is empty
                if debug:
                    logger.debug("Trigger keyword is empty, skipping.")
                continue
            
            # if len(trigger.get("channels", [])) > 0 and message.channel.id not in trigger.get("channels", []): # Check channel restrictions
            #     if debug:
            #         logger.debug(f"Trigger '{keyword}' is not allowed in this channel, skipping.")
            #     continue
            
            # if len(trigger.get("roles", [])) > 0: # Check role restrictions
            #     if debug:
            #         logger.debug(f"Trigger '{keyword}' has role restrictions, checking user roles.")
            #     has_role = False
            #     for role in message.author.roles:
            #         if role.id in trigger.get("roles", []):
            #             has_role = True
            #             break
            #     if not has_role:
            #         continue
            
            content_to_check = message.content if trigger.get("case_sensitive", False) else message.content.lower() # Prepare content for checking based on case sensitivity
            if debug:
                logger.debug(f"Content to check for trigger '{keyword}': {content_to_check}")
            matched = False
            if trigger.get("whole_word", False): # Check the word based on whole word match setting
                if debug:
                    logger.debug(f"Trigger '{keyword}' requires whole word match.")
                words = content_to_check.split()
                if keyword in words:
                    matched = True
            else:
                if content_to_check.find(keyword) != -1:
                    matched = True
                    
            if matched:
                cooldown_seconds = trigger.get("cooldown_seconds", 0)
                if cooldown_seconds > 0: # Check cooldown
                    last_triggered_time = self.last_triggered_times.get(keyword, 0)
                    current_time = discord.utils.utcnow().timestamp()
                    if current_time - last_triggered_time < cooldown_seconds:
                        if debug:
                            logger.debug(f"Trigger '{keyword}' is on cooldown, skipping.")
                        continue
                    self.last_triggered_times[keyword] = current_time
                    
                response = trigger.get("response", "")
                if response != "":
                    await message.channel.send(response)
                

async def setup(bot:commands.Bot):
    await bot.add_cog(Triggers(bot))