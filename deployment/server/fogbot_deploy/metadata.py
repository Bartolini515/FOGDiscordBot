"""Redacted reader for the two deployment metadata fields in production configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import stat

from .protocol import VersionError, parse_version


MAXIMUM_CONFIGURATION_BYTES = 64 * 1024
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class MetadataError(ValueError):
    """Controlled metadata diagnostic with no configuration details."""


@dataclass(frozen=True, slots=True)
class CurrentMetadata:
    """The only production configuration data exposed by the current command."""

    version: str
    last_updated: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not isinstance(self.last_updated, str):
            raise MetadataError("configuration_unavailable")
        try:
            parse_version(self.version)
        except VersionError as error:
            raise MetadataError("configuration_unavailable") from error
        if not DATE_PATTERN.fullmatch(self.last_updated):
            raise MetadataError("configuration_unavailable")
        try:
            date.fromisoformat(self.last_updated)
        except ValueError as error:
            raise MetadataError("configuration_unavailable") from error


@dataclass(frozen=True, slots=True)
class ProductionMetadataReader:
    """Read and validate only technical_info.version and technical_info.last_updated."""

    configuration_path: Path

    def read(self) -> CurrentMetadata:
        """Return redacted current metadata without exposing configuration contents or paths."""
        descriptor: int | None = None
        try:
            descriptor = _open_configuration_descriptor(self.configuration_path)
            file_status = os.fstat(descriptor)
            if not stat.S_ISREG(file_status.st_mode) or file_status.st_size > MAXIMUM_CONFIGURATION_BYTES:
                raise MetadataError("configuration_unavailable")
            stream = os.fdopen(descriptor, "rb", closefd=True)
            descriptor = None
            with stream:
                payload = stream.read(MAXIMUM_CONFIGURATION_BYTES + 1)
            if len(payload) > MAXIMUM_CONFIGURATION_BYTES:
                raise MetadataError("configuration_unavailable")
            configuration = json.loads(payload.decode("utf-8"))
            if not isinstance(configuration, dict):
                raise MetadataError("configuration_unavailable")
            technical_info = configuration.get("technical_info")
            if not isinstance(technical_info, dict):
                raise MetadataError("configuration_unavailable")
            version = technical_info.get("version")
            last_updated = technical_info.get("last_updated")
            if not isinstance(version, str) or not isinstance(last_updated, str):
                raise MetadataError("configuration_unavailable")
            return CurrentMetadata(version, last_updated)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise MetadataError("configuration_unavailable") from error
        finally:
            if descriptor is not None:
                os.close(descriptor)


def _open_configuration_descriptor(configuration_path: Path) -> int:
    """Open one configuration descriptor without following a replacement symlink."""
    if os.name == "posix":
        no_follow = getattr(os, "O_NOFOLLOW", None)
        close_on_exec = getattr(os, "O_CLOEXEC", None)
        if no_follow is None or close_on_exec is None:
            raise MetadataError("configuration_unavailable")
        return os.open(configuration_path, os.O_RDONLY | no_follow | close_on_exec)

    if os.name == "nt":
        initial_status = configuration_path.lstat()
        if not stat.S_ISREG(initial_status.st_mode):
            raise MetadataError("configuration_unavailable")
        descriptor = os.open(configuration_path, os.O_RDONLY | getattr(os, "O_NOINHERIT", 0))
        try:
            os.set_inheritable(descriptor, False)
            opened_status = os.fstat(descriptor)
            if not stat.S_ISREG(opened_status.st_mode) or not _same_file(initial_status, opened_status):
                raise MetadataError("configuration_unavailable")
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    raise MetadataError("configuration_unavailable")


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    """Return whether path inspection and descriptor inspection identify one file."""
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino
