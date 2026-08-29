"""Start the single-guild Discord bot and own its process lifecycle."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import discord
from discord.ext import commands
from dotenv import load_dotenv

from configuration import ConfigurationError, ensure_configuration_file, load_configuration
from db.database import Database
from db.models.users import Users
from services.runtime import (
    HEARTBEAT_INTERVAL_SECONDS,
    InstanceLock,
    ReadinessRecord,
    RuntimePaths,
    collect_non_bot_members,
    configure_logging,
    load_cogs,
    release_sha_from_file,
    save_runtime_configuration,
)

CONFIG_TEMPLATE_PATH = Path(__file__).with_name("configuration.example.json")


class MyBot(commands.Bot):
    """FOG bot runtime with shared configuration, SQLite, and readiness state."""

    def __init__(self, configuration: Mapping[str, Any], runtime_paths: RuntimePaths, logger: Any, debug: bool, instance_lock: InstanceLock):
        super().__init__(command_prefix=configuration["prefix"], intents=discord.Intents.all(), owner_id=configuration["owner_id"], help_command=None)
        self.guild_id = configuration["guild_id"]
        self.runtime_paths = runtime_paths
        self.logger = logger
        self.debug = debug
        self.instance_lock = instance_lock
        self.readiness = ReadinessRecord(runtime_paths.runtime_dir, release_sha_from_file(runtime_paths.release_file))
        self.db = Database(str(runtime_paths.database_path))
        self.permissions = configuration["permissions"]
        self.technical_info = configuration["technical_info"]
        self.technical_info["current_run_date"] = datetime.now().isoformat()
        self.channels = configuration["channels"]
        self.roles = configuration["roles"]
        self.ticket_system = configuration["ticket_system"]
        self.message_triggers = configuration["message_triggers"]
        self.messages = configuration["messages"]
        self.leveling_system = configuration["leveling_system"]
        self.honeypot_system = configuration["honeypot_system"]
        self._autosave_task_handle: asyncio.Task[None] | None = None
        self._heartbeat_task_handle: asyncio.Task[None] | None = None
        self._shutdown_errors: list[Exception] = []

    async def _load_cogs(self) -> None:
        await load_cogs(self, self.logger)

    async def _update_users_on_guild_status(self) -> None:
        if not hasattr(self, "db") or self.db is None:
            return
        guild = self.get_guild(self.guild_id)
        if not guild:
            return
        self.logger.info("Updating users on_guild status in database...")
        members = collect_non_bot_members(guild)
        if self.debug:
            self.logger.debug(guild)
            self.logger.debug(f"Guild members: {members}")
        await Users.update_users_on_startup(self.db, members)
        self.logger.info("Users on_guild status updated.")

    async def _save_configuration(self) -> None:
        save_runtime_configuration(
            self.runtime_paths.config_path,
            {"permissions": self.permissions, "technical_info": self.technical_info, "channels": self.channels,
             "ticket_system": self.ticket_system, "message_triggers": self.message_triggers, "messages": self.messages,
             "leveling_system": self.leveling_system, "honeypot_system": self.honeypot_system},
        )

    async def _autosave_task(self) -> None:
        while True:
            await asyncio.sleep(3600)
            await self._save_configuration()

    async def _heartbeat_task(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            if self.is_ready():
                self.readiness.heartbeat()

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self._load_cogs()
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self._autosave_task_handle = asyncio.create_task(self._autosave_task())
        self._heartbeat_task_handle = asyncio.create_task(self._heartbeat_task())

    async def on_ready(self) -> None:
        self.logger.info(f"We have logged in as {self.user}")
        self.logger.info(discord.__version__)
        await self._update_users_on_guild_status()
        self.readiness.mark_ready()

    async def on_disconnect(self) -> None:
        self.readiness.invalidate()

    async def _cancel_background_tasks(self) -> None:
        for task in (self._autosave_task_handle, self._heartbeat_task_handle):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    self._shutdown_errors.append(exc)

    def _record_shutdown_error(self, error: Exception) -> None:
        self._shutdown_errors.append(error)
        self.logger.error("Shutdown operation failed: %s", error)

    async def close(self) -> None:
        self.readiness.invalidate()
        await self._cancel_background_tasks()
        try:
            await self._save_configuration()
        except Exception as exc:
            self._record_shutdown_error(exc)
        finally:
            try:
                await self.db.close()
            except Exception as exc:
                self._record_shutdown_error(exc)
            finally:
                try:
                    await super().close()
                except Exception as exc:
                    self._record_shutdown_error(exc)
                finally:
                    self.instance_lock.release()


def main() -> int:
    """Perform side-effecting startup only when the module is run as a program."""

    runtime_paths = RuntimePaths.from_environment(os.environ)
    runtime_paths.config_path.parent.mkdir(parents=True, exist_ok=True)
    if ensure_configuration_file(runtime_paths.config_path, CONFIG_TEMPLATE_PATH):
        print(f"Created {runtime_paths.config_path} from configuration.example.json. Please edit it and restart the bot.")
        return 1
    try:
        configuration = load_configuration(runtime_paths.config_path)
    except ConfigurationError as exc:
        print(f"Invalid configuration.json: {exc}")
        return 1

    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        env_path = Path(".env")
        if not env_path.exists():
            env_path.write_text("DISCORD_BOT_TOKEN=\nDEBUG=False\n", encoding="utf-8")
            print("Created default .env, please edit it and restart the bot.")
        else:
            print("DISCORD_BOT_TOKEN is missing. Please set it and restart the bot.")
        return 1

    debug = os.getenv("DEBUG") == "True"
    logger = configure_logging(debug, runtime_paths.log_dir)
    instance_lock = InstanceLock(runtime_paths.instance_lock)
    instance_lock.acquire()
    bot = MyBot(configuration, runtime_paths, logger, debug, instance_lock)
    try:
        bot.run(token)
    finally:
        instance_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
