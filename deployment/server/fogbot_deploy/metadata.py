"""Redacted reader for the two deployment metadata fields in production configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
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
        try:
            file_status = self.configuration_path.lstat()
            if not stat.S_ISREG(file_status.st_mode) or file_status.st_size > MAXIMUM_CONFIGURATION_BYTES:
                raise MetadataError("configuration_unavailable")
            with self.configuration_path.open("rb") as stream:
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
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, MetadataError) as error:
            raise MetadataError("configuration_unavailable") from error
