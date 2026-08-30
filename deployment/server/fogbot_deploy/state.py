"""Durable, redacted operation records for deployment transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping
from uuid import uuid4

from .protocol import VersionError, parse_version
from .verifier import VerifiedRun


PHASES = frozenset(
    {
        "submitted",
        "authorized",
        "preparing",
        "ready_to_stop",
        "stopped",
        "backed_up",
        "migrated",
        "switched",
        "starting",
        "health_check",
        "succeeded",
        "failed",
        "manual_intervention",
    }
)
DIAGNOSTIC_CODES = frozenset(
    {
        "authorized",
        "pending",
        "completed",
        "verification_failed",
        "launcher_failed",
        "preparation_failed",
        "backup_failed",
        "migration_failed",
        "switch_failed",
        "start_failed",
        "health_check_failed",
        "manual_intervention_required",
        "state_invalid",
    }
)
OPERATION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


class StateError(ValueError):
    """Controlled state-store failure without operational details."""


class OperationNotFound(StateError):
    """Raised when a syntactically valid operation identifier has no record."""


@dataclass(frozen=True, slots=True)
class OperationRecord:
    """The complete non-secret transaction state required for recovery and status."""

    operation_id: str
    idempotency_key: str
    target: dict[str, int | str]
    result: str | None
    phase: str
    timestamps: dict[str, str]
    previous_release: str | None = None
    backup_release_id: str | None = None
    backup_database_id: str | None = None
    migration_applied: bool = False
    diagnostic_code: str = "pending"

    def __post_init__(self) -> None:
        if not OPERATION_ID_PATTERN.fullmatch(self.operation_id) or self.idempotency_key != self.operation_id:
            raise StateError("state_invalid")
        if self.phase not in PHASES or self.diagnostic_code not in DIAGNOSTIC_CODES:
            raise StateError("state_invalid")
        if self.result not in {None, "pending", "success", "failure"}:
            raise StateError("state_invalid")
        if set(self.target) != {"repository_id", "run_id", "run_attempt", "sha", "target_version"}:
            raise StateError("state_invalid")
        if not isinstance(self.target["repository_id"], int) or not isinstance(self.target["run_id"], int):
            raise StateError("state_invalid")
        if (
            not isinstance(self.target["run_attempt"], int)
            or not isinstance(self.target["sha"], str)
            or not isinstance(self.target["target_version"], str)
        ):
            raise StateError("state_invalid")
        try:
            parse_version(self.target["target_version"])
        except VersionError as error:
            raise StateError("state_invalid") from error

    @classmethod
    def authorized(cls, verified: VerifiedRun, operation_id: str, target_version: str) -> OperationRecord:
        """Create the first durable record after external authorization succeeds."""
        timestamp = _format_timestamp(verified.verified_at)
        return cls(
            operation_id=operation_id,
            idempotency_key=operation_id,
            target={
                "repository_id": verified.repository_id,
                "run_id": verified.run_id,
                "run_attempt": verified.run_attempt,
                "sha": verified.sha,
                "target_version": target_version,
            },
            result="pending",
            phase="authorized",
            timestamps={"submitted": timestamp, "authorized": timestamp},
            diagnostic_code="authorized",
        )

    def with_phase(
        self,
        phase: str,
        diagnostic_code: str,
        *,
        result: str | None = None,
        previous_release: str | None = None,
        backup_release_id: str | None = None,
        backup_database_id: str | None = None,
        migration_applied: bool | None = None,
        when: datetime | None = None,
    ) -> OperationRecord:
        """Return a validated phase update without accepting error or log text."""
        timestamps = dict(self.timestamps)
        timestamps[phase] = _format_timestamp(when or datetime.now(UTC))
        return OperationRecord(
            operation_id=self.operation_id,
            idempotency_key=self.idempotency_key,
            target=dict(self.target),
            result=result if result is not None else self.result,
            phase=phase,
            timestamps=timestamps,
            previous_release=previous_release if previous_release is not None else self.previous_release,
            backup_release_id=backup_release_id if backup_release_id is not None else self.backup_release_id,
            backup_database_id=backup_database_id if backup_database_id is not None else self.backup_database_id,
            migration_applied=migration_applied if migration_applied is not None else self.migration_applied,
            diagnostic_code=diagnostic_code,
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialize only whitelisted non-secret operation fields."""
        return {
            "operation_id": self.operation_id,
            "idempotency_key": self.idempotency_key,
            "target": self.target,
            "result": self.result,
            "phase": self.phase,
            "timestamps": self.timestamps,
            "previous_release": self.previous_release,
            "backup_release_id": self.backup_release_id,
            "backup_database_id": self.backup_database_id,
            "migration_applied": self.migration_applied,
            "diagnostic_code": self.diagnostic_code,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OperationRecord:
        """Load and validate an operation record without preserving extra input fields."""
        expected = {
            "operation_id",
            "idempotency_key",
            "target",
            "result",
            "phase",
            "timestamps",
            "previous_release",
            "backup_release_id",
            "backup_database_id",
            "migration_applied",
            "diagnostic_code",
        }
        if set(value) != expected or not isinstance(value.get("target"), dict) or not isinstance(value.get("timestamps"), dict):
            raise StateError("state_invalid")
        try:
            return cls(
                operation_id=value["operation_id"],
                idempotency_key=value["idempotency_key"],
                target=value["target"],
                result=value["result"],
                phase=value["phase"],
                timestamps=value["timestamps"],
                previous_release=value["previous_release"],
                backup_release_id=value["backup_release_id"],
                backup_database_id=value["backup_database_id"],
                migration_applied=value["migration_applied"],
                diagnostic_code=value["diagnostic_code"],
            )
        except (KeyError, TypeError) as error:
            raise StateError("state_invalid") from error


@dataclass(slots=True)
class OperationStore:
    """Atomic JSON persistence rooted in a root-owned directory outside releases."""

    directory: Path
    _directory_created: bool = field(init=False, default=False)

    def create_or_read(self, record: OperationRecord) -> tuple[OperationRecord, bool]:
        """Atomically create the operation or return the existing idempotent record."""
        self._ensure_directory()
        destination = self._path_for(record.operation_id)
        encoded = _encode(record)
        try:
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self.read(record.operation_id), False
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_directory(self.directory)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return record, True

    def read(self, operation_id: str) -> OperationRecord:
        """Read one validated operation record by its strict opaque identifier."""
        if not OPERATION_ID_PATTERN.fullmatch(operation_id):
            raise OperationNotFound("operation_not_found")
        try:
            with self._path_for(operation_id).open("r", encoding="utf-8") as stream:
                value = json.load(stream)
        except FileNotFoundError as error:
            raise OperationNotFound("operation_not_found") from error
        except (OSError, json.JSONDecodeError) as error:
            raise StateError("state_invalid") from error
        if not isinstance(value, dict):
            raise StateError("state_invalid")
        return OperationRecord.from_dict(value)

    def write(self, record: OperationRecord) -> None:
        """Atomically replace an existing record after a transaction phase transition."""
        self._ensure_directory()
        destination = self._path_for(record.operation_id)
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(_encode(record))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            _fsync_directory(self.directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _ensure_directory(self) -> None:
        if not self._directory_created:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._directory_created = True

    def _path_for(self, operation_id: str) -> Path:
        if not OPERATION_ID_PATTERN.fullmatch(operation_id):
            raise StateError("state_invalid")
        return self.directory / f"{operation_id}.json"


def _encode(record: OperationRecord) -> bytes:
    return json.dumps(record.as_dict(), separators=(",", ":"), sort_keys=True).encode("utf-8")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise StateError("state_invalid")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _fsync_directory(directory: Path) -> None:
    """Persist directory metadata where the platform permits directory fsync."""
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
