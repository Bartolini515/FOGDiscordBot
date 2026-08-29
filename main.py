"""Start the single-guild Discord bot and own its process lifecycle."""

import asyncio

import discord
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
import os
from pathlib import Path

from configuration import ConfigurationError, ensure_configuration_file, load_configuration
from db.database import Database
from db.models.users import Users
from services.runtime import collect_non_bot_members, configure_logging, load_cogs, save_runtime_configuration

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
logger = configure_logging(debug)

# Intents
intents = discord.Intents.all()


# The bot
class MyBot(commands.Bot):
    """FOG bot runtime with shared configuration and one SQLite connection."""

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
        """Load every Python extension found directly under ``Cogs``."""
        await load_cogs(self, logger)

    # Update users currently on guild in db
    async def _update_users_on_guild_status(self):
        """Reconcile stored membership flags with the configured guild."""
        if not hasattr(self, "db") or self.db is None:
            return
        guild = self.get_guild(self.guild_id)
        if not guild:
            return
        logger.info("Updating users on_guild status in database...")
        members = collect_non_bot_members(guild)
        if debug:
            logger.debug(guild)
            logger.debug(f"Guild members: {members}")
        await Users.update_users_on_startup(self.db, members)
        logger.info("Users on_guild status updated.")
        
    async def _save_configuration(self):
        """Persist mutable in-memory configuration sections to the local JSON file."""
        save_runtime_configuration(
            Path("configuration.json"),
            {
                "permissions": self.permissions,
                "technical_info": self.technical_info,
                "channels": self.channels,
                "ticket_system": self.ticket_system,
                "message_triggers": self.message_triggers,
                "messages": self.messages,
                "leveling_system": self.leveling_system,
                "honeypot_system": self.honeypot_system,
            },
        )
            
    async def _autosave_task(self):
        """Persist runtime configuration once per hour until cancellation."""
        while True:
            await asyncio.sleep(3600)  # Save every hour
            await self._save_configuration()

    # Before startup
    async def setup_hook(self):
        """Migrate SQLite, load cogs, and sync commands to the FOG guild."""
        await self.db.connect()
        await self._load_cogs()
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.loop.create_task(self._autosave_task())

    # On startup
    async def on_ready(self):
        """Log the connected identity and reconcile current guild members."""
        logger.info(f"We have logged in as {self.user}")
        logger.info(discord.__version__)
        await self._update_users_on_guild_status()
        
    # On shutdown
    async def close(self):
        """Save configuration and close SQLite before Discord shutdown."""
        # Save changes in configuration file
        await self._save_configuration()
        
        await self.db.close()
        await super().close()

# Run the bot
bot = MyBot(command_prefix=prefix, intents=intents, owner_id=owner_id, guild_id=guild_id)
bot.run(token)
