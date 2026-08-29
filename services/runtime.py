"""Runtime helpers for loading extensions and persisting bot state."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Protocol


class CogLoader(Protocol):
    async def load_extension(self, name: str) -> None:
        """Load one bot extension."""


MUTABLE_CONFIGURATION_KEYS = (
    "permissions",
    "channels",
    "ticket_system",
    "message_triggers",
    "messages",
    "leveling_system",
    "honeypot_system",
)


def configure_logging(debug_mode: bool, log_directory: str | Path = "logs") -> logging.Logger:
    """Configure bot and Discord loggers with the existing handlers."""

    os.makedirs(log_directory, exist_ok=True)
    level = logging.DEBUG if debug_mode else logging.INFO
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        Path(log_directory) / "bot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    logger = logging.getLogger("fogbot")
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    discord_logger = logging.getLogger("discord")
    discord_logger.setLevel(level)
    if not discord_logger.handlers:
        discord_logger.addHandler(stream_handler)
        discord_logger.addHandler(file_handler)

    return logger


def collect_non_bot_members(guild: object) -> list[tuple[int, str]]:
    """Return ``(id, name)`` pairs for human guild members."""

    return [
        (member.id, member.name)
        for member in getattr(guild, "members", [])
        if not member.bot
    ]


def save_runtime_configuration(path: Path, values: Mapping[str, Any]) -> None:
    """Persist the same mutable configuration sections as the bot runtime."""

    with path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)

    for key in MUTABLE_CONFIGURATION_KEYS:
        data[key] = values[key]
    data["technical_info"]["current_run_date"] = values["technical_info"]["current_run_date"]

    with path.open("w", encoding="utf-8") as config_file:
        json.dump(data, config_file, indent=4)


async def load_cogs(bot: CogLoader, logger: logging.Logger, directory: str = "Cogs") -> None:
    """Load every Python extension found directly under ``directory``."""

    module_prefix = Path(directory).name
    for filename in os.listdir(directory):
        if filename.endswith(".py"):
            extension = f"{module_prefix}.{filename[:-3]}"
            try:
                await bot.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception:
                logger.exception(f"Failed to load extension {extension}")
