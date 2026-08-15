"""Load and validate the bot's local JSON configuration."""

from __future__ import annotations

from json import JSONDecodeError
import json
from pathlib import Path
import shutil
from typing import Any


class ConfigurationError(ValueError):
    """Raised when the local configuration cannot be loaded safely."""


REQUIRED_SECTIONS: dict[str, type[object]] = {
    "prefix": str,
    "owner_id": int,
    "guild_id": int,
    "permissions": dict,
    "technical_info": dict,
    "channels": dict,
    "roles": dict,
    "ticket_system": dict,
    "message_triggers": list,
    "messages": dict,
    "leveling_system": dict,
    "honeypot_system": dict,
}

REQUIRED_HONEYPOT_FIELDS: dict[str, type[object]] = {
    "honeypot_channels": list,
    "counter_messages": list,
    "trap_counter": int,
}

TYPE_NAMES = {
    str: "a string",
    int: "an integer",
    dict: "an object",
    list: "a list",
}


def ensure_configuration_file(destination: Path, template: Path) -> bool:
    """Copy the example configuration when the destination does not exist."""
    if destination.exists():
        return False

    shutil.copyfile(template, destination)
    return True


def _validate_mapping(data: dict[str, Any], required: dict[str, type[object]], context: str = "") -> None:
    missing = sorted(required.keys() - data.keys())
    if missing:
        label = f"{context} is missing required keys" if context else "Missing required configuration sections"
        raise ConfigurationError(f"{label}: {', '.join(missing)}")

    for key, expected_type in required.items():
        if type(data[key]) is not expected_type:
            qualified_key = f"{context}.{key}" if context else key
            raise ConfigurationError(f"{qualified_key} must be {TYPE_NAMES[expected_type]}")


def load_configuration(path: Path) -> dict[str, Any]:
    """Read a JSON configuration and validate its required structure."""
    try:
        with path.open("r", encoding="utf-8") as config_file:
            data = json.load(config_file)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file does not exist: {path}") from exc
    except (OSError, JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read configuration file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigurationError("Configuration root must be an object")

    _validate_mapping(data, REQUIRED_SECTIONS)
    honeypot_system = data["honeypot_system"]
    _validate_mapping(honeypot_system, REQUIRED_HONEYPOT_FIELDS, "honeypot_system")
    return data
