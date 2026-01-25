import discord
from datetime import datetime
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import json
import os
from db.database import Database
from db.models import Users

# Create configuration file if it doesn't exist
if not os.path.exists("configuration.json"):
    with open("configuration.json", "w", encoding="utf-8") as config:
        json.dump({
            "prefix": "!",
            "owner_id": 0,
            "guild_id": 0,
            "permissions": {},
            "technical_info": {},
            "channels": {},
            "roles": {},
            "ticket_system": {},
            "message_triggers": []
            }, config, indent=4)
        print("Created default configuration.json, please edit it and restart the bot.")
        exit()

# Create .env file if it doesn't exist
if not os.path.exists(".env"):
    with open(".env", "w", encoding="utf-8") as env:
        env.write("DISCORD_BOT_TOKEN=\nDEBUG=False\n")
        print("Created default .env, please edit it and restart the bot.")
        exit()

# Load configuration file
with open("configuration.json", "r", encoding="utf-8") as config: 
    data = json.load(config)
    prefix = data["prefix"]
    owner_id = data["owner_id"]
    guild_id = data["guild_id"]
    permissions = data.get("permissions", {})
    technical_info = data.get("technical_info", {})
    channels = data.get("channels", {})
    roles = data.get("roles", {})
    ticket_system = data.get("ticket_system", {})
    message_triggers = data.get("message_triggers", [])

# Load .env variables
load_dotenv()
token = os.getenv("DISCORD_BOT_TOKEN")
debug = os.getenv("DEBUG") == "True"


# Logging
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("fogbot")
logger.setLevel(logging.DEBUG if debug else logging.INFO)

formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG if debug else logging.INFO)
stream_handler.setFormatter(formatter)

file_handler = RotatingFileHandler("logs/bot.log", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
file_handler.setFormatter(formatter)

# Avoid duplicate handlers if reloading
if not logger.handlers:
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)

# Also route discord.py logs to same handlers
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.DEBUG if debug else logging.INFO)
if not discord_logger.handlers:
    discord_logger.addHandler(stream_handler)
    discord_logger.addHandler(file_handler)

# Intents
intents = discord.Intents.all()


# The bot
class MyBot(commands.Bot):
    def __init__(self, command_prefix, intents, owner_id, guild_id):
        super().__init__(command_prefix=command_prefix, intents=intents, owner_id=owner_id, help_command=None)
        self.guild_id = guild_id
        self.db = Database("db/bot.db")
        self.permissions = permissions
        self.technical_info = technical_info
        self.technical_info["current_run_date"] = datetime.now().isoformat()
        self.channels = channels
        self.roles = roles
        self.ticket_system = ticket_system
        self.message_triggers = message_triggers
        
    
    # Load cogs
    async def _load_cogs(self):
        for filename in os.listdir("Cogs"):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"Cogs.{filename[:-3]}")
                    logger.info(f"Loaded extension: Cogs.{filename[:-3]}")
                except Exception:
                    logger.exception(f"Failed to load extension Cogs.{filename[:-3]}")

    # Update users currently on guild in db
    async def _update_users_on_guild_status(self):
        if not hasattr(self, "db") or self.db is None:
            return
        if not self.get_guild(self.guild_id):
            return
        logger.info("Updating users on_guild status in database...")
        members = []
        for member in self.get_guild(self.guild_id).members:
            if member.bot:
                continue
            members.append((member.id, member.name))
        if debug:
            logger.debug(self.get_guild(self.guild_id))
            logger.debug(f"Guild members: {members}")
        await Users.update_users_on_startup(self.db, members)
        logger.info("Users on_guild status updated.")

    # Before startup
    async def setup_hook(self):
        await self.db.connect()
        await self._load_cogs()
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

    # On startup
    async def on_ready(self):
        logger.info(f"We have logged in as {self.user}")
        logger.info(discord.__version__)
        await self._update_users_on_guild_status()
        
    # On shutdown
    async def close(self):
        # Save changes in configuration file
        with open("configuration.json", "r", encoding="utf-8") as config:
            data = json.load(config)
            data["permissions"] = self.permissions
            data["technical_info"]["current_run_date"] = self.technical_info["current_run_date"]
            data["channels"] = self.channels
        with open("configuration.json", "w", encoding="utf-8") as config:
            json.dump(data, config, indent=4)
        
        await self.db.close()
        await super().close()

# Run the bot
bot = MyBot(command_prefix=prefix, intents=intents, owner_id=owner_id, guild_id=guild_id)
bot.run(token)