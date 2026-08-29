"""Strict grammar and stable identifiers for forced deployment commands."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import shlex


SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
OPERATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
POSITIVE_INTEGER_PATTERN = re.compile(r"[1-9][0-9]*")
SHELL_CHARACTERS = frozenset(";&|$`()<>\\\"'*?![]{}~\r\n\t")


class CommandError(ValueError):
    """Raised for a forced command that does not match the exact grammar."""


@dataclass(frozen=True, slots=True)
class SubmitRequest:
    """The approved immutable deployment identity supplied over SSH."""

    sha: str
    run_id: int
    run_attempt: int
    repository_id: int


@dataclass(frozen=True, slots=True)
class StatusRequest:
    """A status lookup constrained to one opaque operation identifier."""

    operation_id: str


CommandRequest = SubmitRequest | StatusRequest


def parse_command(command: str | None) -> CommandRequest:
    """Parse one allowed forced command without evaluating any shell syntax."""
    if not command or any(character in SHELL_CHARACTERS for character in command):
        raise CommandError("invalid_command")
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as error:
        raise CommandError("invalid_command") from error

    if len(tokens) == 2 and tokens[0] == "status" and OPERATION_ID_PATTERN.fullmatch(tokens[1]):
        return StatusRequest(operation_id=tokens[1])

    if len(tokens) == 5 and tokens[0] == "submit" and SHA_PATTERN.fullmatch(tokens[1]):
        number_tokens = tokens[2:]
        if all(POSITIVE_INTEGER_PATTERN.fullmatch(token) for token in number_tokens):
            return SubmitRequest(
                sha=tokens[1],
                run_id=int(tokens[2]),
                run_attempt=int(tokens[3]),
                repository_id=int(tokens[4]),
            )

    raise CommandError("invalid_command")


def operation_id_for(request: SubmitRequest) -> str:
    """Return the fixed-width, stable idempotency key for a verified submission."""
    material = f"{request.repository_id}:{request.run_id}:{request.run_attempt}:{request.sha}".encode("ascii")
    return sha256(material).hexdigest()[:32]
