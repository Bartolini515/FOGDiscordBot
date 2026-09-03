"""Forced-command entry point with no shell evaluation or remote execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
import sys
from typing import Protocol, Sequence, TextIO

from .metadata import CurrentMetadata
from .protocol import CurrentRequest, CommandError, StatusRequest, SubmitRequest, operation_id_for, parse_command
from .state import OperationNotFound, OperationRecord, OperationStore, StateError
from .verifier import VerificationError, VerifiedRun


class RunVerifier(Protocol):
    """Interface used by the command and re-used by the transaction before stop."""

    def verify(self, request: SubmitRequest) -> VerifiedRun: ...


class TransactionLauncher(Protocol):
    """Local launcher boundary; implementations must not use an SSH command string."""

    def start(self, record: OperationRecord) -> None: ...


class MetadataReader(Protocol):
    """Boundary that returns only safe current deployment metadata."""

    def read(self) -> CurrentMetadata: ...


@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Compact machine-readable forced-command result."""

    exit_code: int
    stdout: str
    stderr: str = ""


class ForcedCommandHandler:
    """Create/status deployment operations from one strict SSH original command."""

    def __init__(
        self,
        verifier: RunVerifier,
        store: OperationStore,
        launcher: TransactionLauncher,
        metadata_reader: MetadataReader,
    ) -> None:
        self._verifier = verifier
        self._store = store
        self._launcher = launcher
        self._metadata_reader = metadata_reader

    def handle(self, original_command: str | None) -> CommandResponse:
        """Process a command without starting a shell or interpolating any user text."""
        try:
            command = parse_command(original_command)
        except CommandError:
            return _error(2, "invalid_command")
        if isinstance(command, CurrentRequest):
            return self._current()
        if isinstance(command, StatusRequest):
            return self._status(command)
        return self._submit(command)

    def _submit(self, request: SubmitRequest) -> CommandResponse:
        try:
            verified = self._verifier.verify(request)
            if (
                verified.repository_id != request.repository_id
                or verified.run_id != request.run_id
                or verified.run_attempt != request.run_attempt
                or verified.sha != request.sha
            ):
                return _error(3, "verification_failed")
        except VerificationError as error:
            return _error(3, error.diagnostic_code)
        except Exception:
            return _error(3, "verification_failed")

        operation_id = operation_id_for(request)
        record = OperationRecord.authorized(verified, operation_id, request.version)
        try:
            persisted, created = self._store.create_or_read(record)
        except StateError:
            return _error(4, "state_invalid")
        if created:
            try:
                self._launcher.start(persisted)
            except Exception:
                self._store.write(persisted.with_phase("failed", "launcher_failed", result="failure"))
                return _error(4, "launcher_failed")
        return _success({"operation_id": persisted.operation_id, "phase": persisted.phase})

    def _current(self) -> CommandResponse:
        try:
            metadata = self._metadata_reader.read()
        except Exception:
            return _error(4, "configuration_unavailable")
        return _success({"version": metadata.version, "last_updated": metadata.last_updated})

    def _status(self, request: StatusRequest) -> CommandResponse:
        try:
            record = self._store.read(request.operation_id)
        except OperationNotFound:
            return _error(4, "operation_not_found")
        except StateError:
            return _error(4, "state_invalid")
        return _success(record.as_dict())


def run_from_ssh_original_command(
    handler: ForcedCommandHandler,
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Read only SSH_ORIGINAL_COMMAND, write compact JSON, and return its controlled code."""
    environment = os.environ if environ is None else environ
    response = handler.handle(environment.get("SSH_ORIGINAL_COMMAND"))
    return _write_response(response, stdout=stdout, stderr=stderr)


def run_from_argv(
    handler: ForcedCommandHandler,
    argv: Sequence[str],
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Process one strict argv command without invoking a shell.

    The root-owned helper is normally called by ``sudo`` with this interface.
    Joining already-separated arguments is safe here because ``parse_command``
    applies the same exact grammar and rejects shell metacharacters, empty
    tokens, and all unexpected shapes.  SSH forced-command callers continue to
    use :func:`run_from_ssh_original_command` unchanged.
    """
    if isinstance(argv, (str, bytes)) or any(not isinstance(token, str) for token in argv):
        command = None
    else:
        command = " ".join(argv)
    response = handler.handle(command)
    return _write_response(response, stdout=stdout, stderr=stderr)


def _write_response(
    response: CommandResponse,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Emit one redacted response through the caller-supplied streams."""
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    print(response.stdout, file=output, flush=True)
    if response.stderr:
        print(response.stderr, file=errors, flush=True)
    return response.exit_code


def _success(payload: dict[str, object]) -> CommandResponse:
    return CommandResponse(0, _compact_json({"ok": True, **payload}))


def _error(exit_code: int, code: str) -> CommandResponse:
    return CommandResponse(exit_code, _compact_json({"ok": False, "code": code}), code)


def _compact_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)
