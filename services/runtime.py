"""Runtime helpers for loading extensions and persisting bot state."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
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

RUNTIME_SCHEMA_VERSION = 1
READINESS_FILENAME = "ready.json"
HEARTBEAT_INTERVAL_SECONDS = 10


class RuntimePathError(ValueError):
    """Raised when a production runtime path is not absolute."""


class InstanceLockError(RuntimeError):
    """Raised when another process already owns the runtime lock."""


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved file-system contract shared by local and deployed runtimes."""

    config_path: Path
    database_path: Path
    log_dir: Path
    runtime_dir: Path
    release_file: Path
    instance_lock: Path

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str],
        *,
        development_base: Path | None = None,
    ) -> "RuntimePaths":
        """Resolve the six supported ``FOGBOT_*`` paths to absolute paths.

        Explicit relative overrides are deliberately local-development only.  The
        default layout is resolved from the local base (or current directory).
        """

        base = (development_base or Path.cwd()).resolve()

        def resolve(name: str, default: Path) -> Path:
            supplied = environment.get(name)
            candidate = Path(supplied) if supplied else default
            if candidate.is_absolute():
                return candidate.resolve()
            if supplied and development_base is None:
                raise RuntimePathError(f"{name} must be an absolute path outside local development")
            return (base / candidate).resolve()

        runtime_dir = resolve("FOGBOT_RUNTIME_DIR", Path(".runtime"))
        return cls(
            config_path=resolve("FOGBOT_CONFIG_PATH", Path("configuration.json")),
            database_path=resolve("FOGBOT_DB_PATH", Path("db") / "bot.db"),
            log_dir=resolve("FOGBOT_LOG_DIR", Path("logs")),
            runtime_dir=runtime_dir,
            release_file=resolve("FOGBOT_RELEASE_FILE", Path("RELEASE_SHA")),
            instance_lock=resolve("FOGBOT_INSTANCE_LOCK", runtime_dir / "instance.lock"),
        )


def atomic_write_text(path: Path, content: str) -> None:
    """Durably replace one file without exposing a partially written target."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary_file:
            temporary_name = temporary_file.name
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        _fsync_directory(path.parent)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    """Request directory durability where the current platform permits it."""

    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


class InstanceLock:
    """Non-blocking, dependency-free exclusive lock backed by one file."""

    def __init__(self, path: Path):
        self.path = path
        self._descriptor: int | None = None

    def acquire(self) -> None:
        """Acquire this lock immediately or raise if another holder exists."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise InstanceLockError(f"Runtime instance lock is already held: {self.path}") from exc
        os.write(self._descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(self._descriptor)

    def release(self) -> None:
        """Release an acquired lock; repeated release is safe."""

        if self._descriptor is None:
            return
        os.close(self._descriptor)
        self._descriptor = None
        self.path.unlink(missing_ok=True)


def release_sha_from_file(path: Path) -> str:
    """Return a full release SHA or the explicit local-development marker."""

    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value if re.fullmatch(r"[0-9a-fA-F]{40}", value) else "unknown"


def _boot_id() -> str:
    try:
        value = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ReadinessRecord:
    """Own the atomically persisted readiness state for one bot generation."""

    def __init__(self, runtime_dir: Path, release_sha: str, *, generation: str | None = None):
        self.path = runtime_dir / READINESS_FILENAME
        self.release_sha = release_sha
        self.generation = generation or str(uuid.uuid4())
        self.boot_id = _boot_id()
        self._ready_at: str | None = None

    def mark_ready(self) -> None:
        """Write a complete readiness record after Discord reconciliation."""

        now = _utc_timestamp()
        self._ready_at = now
        self._write(now)

    def heartbeat(self) -> None:
        """Refresh the record only after this generation was marked ready."""

        if self._ready_at is not None:
            self._write(_utc_timestamp())

    def invalidate(self) -> None:
        """Remove readiness idempotently when Discord connectivity is lost."""

        self.path.unlink(missing_ok=True)
        _fsync_directory(self.path.parent)

    def _write(self, heartbeat_at: str) -> None:
        data = {
            "schema_version": RUNTIME_SCHEMA_VERSION,
            "release_sha": self.release_sha,
            "pid": os.getpid(),
            "generation": self.generation,
            "boot_id": self.boot_id,
            "ready_at": self._ready_at,
            "heartbeat_at": heartbeat_at,
        }
        atomic_write_text(self.path, json.dumps(data, indent=4))


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

    atomic_write_text(path, json.dumps(data, indent=4))


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
