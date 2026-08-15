import asyncio

import discord
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import json
import os
from pathlib import Path

from configuration import ConfigurationError, ensure_configuration_file, load_configuration
from db.database import Database
from db.models import Users

CONFIG_PATH = Path("configuration.json")
CONFIG_TEMPLATE_PATH = Path(__file__).with_name("configuration.example.json")

# Create a safe local configuration without overwriting an existing file.
if ensure_configuration_file(CONFIG_PATH, CONFIG_TEMPLATE_PATH):
    print("Created configuration.json from configuration.example.json. Please edit it and restart the bot.")
    raise SystemExit(1)

# Create .env file if it doesn't exist
if not os.path.exists(".env"):
    with open(".env", "w", encoding="utf-8") as env:
        env.write("DISCORD_BOT_TOKEN=\nDEBUG=False\n")
        print("Created default .env, please edit it and restart the bot.")
        exit()

# Load configuration file
try:
    data = load_configuration(CONFIG_PATH)
except ConfigurationError as exc:
    print(f"Invalid configuration.json: {exc}")
    raise SystemExit(1) from exc

prefix = data["prefix"]
owner_id = data["owner_id"]
guild_id = data["guild_id"]
permissions = data["permissions"]
technical_info = data["technical_info"]
channels = data["channels"]
roles = data["roles"]
ticket_system = data["ticket_system"]
message_triggers = data["message_triggers"]
messages = data["messages"]
leveling_system = data["leveling_system"]
honeypot_system = data["honeypot_system"]

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
        self.messages = messages
        self.leveling_system = leveling_system
        self.honeypot_system = honeypot_system
        
    
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
        
    async def _save_configuration(self):
        with open("configuration.json", "r", encoding="utf-8") as config:
            data = json.load(config)
            data["permissions"] = self.permissions
            data["technical_info"]["current_run_date"] = self.technical_info["current_run_date"]
            data["channels"] = self.channels
            data["ticket_system"] = self.ticket_system
            data["message_triggers"] = self.message_triggers
            data["messages"] = self.messages
            data["leveling_system"] = self.leveling_system
            data["honeypot_system"] = self.honeypot_system
            
        with open("configuration.json", "w", encoding="utf-8") as config:
            json.dump(data, config, indent=4)
            
    async def _autosave_task(self):
        while True:
            await asyncio.sleep(3600)  # Save every hour
            await self._save_configuration()

    # Before startup
    async def setup_hook(self):
        await self.db.connect()
        await self._load_cogs()
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.loop.create_task(self._autosave_task())

    # On startup
    async def on_ready(self):
        logger.info(f"We have logged in as {self.user}")
        logger.info(discord.__version__)
        await self._update_users_on_guild_status()
        
    # On shutdown
    async def close(self):
        # Save changes in configuration file
        await self._save_configuration()
        
        await self.db.close()
        await super().close()

# Run the bot
bot = MyBot(command_prefix=prefix, intents=intents, owner_id=owner_id, guild_id=guild_id)
bot.run(token)
