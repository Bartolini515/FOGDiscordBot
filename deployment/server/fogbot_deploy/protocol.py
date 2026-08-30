"""Strict grammar and stable identifiers for forced deployment commands."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re


SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
OPERATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*")
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SHELL_CHARACTERS = frozenset(";&|$`()<>\\\"'*?![]{}~\r\n\t")
MAXIMUM_COMMAND_LENGTH = 512
MAXIMUM_TOKEN_LENGTH = 128
MAXIMUM_NUMERIC_TOKEN_LENGTH = 19
MAXIMUM_VERSION_COMPONENT_LENGTH = 9
MAXIMUM_VERSION_LENGTH = MAXIMUM_VERSION_COMPONENT_LENGTH * 3 + 2


class CommandError(ValueError):
    """Raised for a forced command that does not match the exact grammar."""


class VersionError(ValueError):
    """Raised when a version is not canonical decimal SemVer."""


@dataclass(frozen=True, slots=True)
class CanonicalVersion:
    """One validated MAJOR.MINOR.PATCH operator version."""

    value: str

    def __post_init__(self) -> None:
        if len(self.value) > MAXIMUM_VERSION_LENGTH or not VERSION_PATTERN.fullmatch(self.value):
            raise VersionError("invalid_version")
        if any(len(component) > MAXIMUM_VERSION_COMPONENT_LENGTH for component in self.value.split(".")):
            raise VersionError("invalid_version")


def parse_version(value: str) -> CanonicalVersion:
    """Return one canonical decimal SemVer value or a controlled validation error."""
    if not isinstance(value, str):
        raise VersionError("invalid_version")
    return CanonicalVersion(value)


@dataclass(frozen=True, slots=True)
class SubmitRequest:
    """The approved immutable deployment identity supplied over SSH."""

    sha: str
    run_id: int
    run_attempt: int
    repository_id: int
    version: str


@dataclass(frozen=True, slots=True)
class CurrentRequest:
    """A request for the current redacted production version metadata."""


@dataclass(frozen=True, slots=True)
class StatusRequest:
    """A status lookup constrained to one opaque operation identifier."""

    operation_id: str


CommandRequest = CurrentRequest | SubmitRequest | StatusRequest


def parse_command(command: str | None) -> CommandRequest:
    """Parse one allowed forced command without evaluating any shell syntax."""
    try:
        if not isinstance(command, str) or not command or len(command) > MAXIMUM_COMMAND_LENGTH:
            raise CommandError("invalid_command")
        if any(character in SHELL_CHARACTERS for character in command):
            raise CommandError("invalid_command")
        tokens = command.split(" ")
        if any(not token or len(token) > MAXIMUM_TOKEN_LENGTH for token in tokens):
            raise CommandError("invalid_command")

        if len(tokens) == 1 and tokens[0] == "current":
            return CurrentRequest()

        if len(tokens) == 2 and tokens[0] == "status" and OPERATION_ID_PATTERN.fullmatch(tokens[1]):
            return StatusRequest(operation_id=tokens[1])

        if len(tokens) == 6 and tokens[0] == "submit" and SHA_PATTERN.fullmatch(tokens[1]):
            number_tokens = tokens[2:5]
            if all(
                len(token) <= MAXIMUM_NUMERIC_TOKEN_LENGTH and POSITIVE_INTEGER_PATTERN.fullmatch(token)
                for token in number_tokens
            ):
                return SubmitRequest(
                    sha=tokens[1],
                    run_id=int(tokens[2]),
                    run_attempt=int(tokens[3]),
                    repository_id=int(tokens[4]),
                    version=parse_version(tokens[5]).value,
                )
    except ValueError as error:
        raise CommandError("invalid_command") from error

    raise CommandError("invalid_command")


def operation_id_for(request: SubmitRequest) -> str:
    """Return the fixed-width, stable idempotency key for a verified submission."""
    material = (
        f"{request.repository_id}:{request.run_id}:{request.run_attempt}:{request.sha}:{request.version}".encode("ascii")
    )
    return sha256(material).hexdigest()[:32]
