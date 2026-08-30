"""Reusable, side-effect-bounded primitives for manual deployment transactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import tempfile
import time
from types import MappingProxyType
from typing import BinaryIO, Callable, Mapping, Protocol, Self

from .protocol import VersionError, parse_version


class TransactionError(RuntimeError):
    """Controlled transaction failure without paths, commands, or operational data."""


SHELL_CHARACTERS = frozenset(";&|$`()<>\\\"'*?![]{}~\r\n\t")
MAXIMUM_CONFIGURATION_BYTES = 64 * 1024
MAXIMUM_READINESS_BYTES = 16 * 1024
MAXIMUM_SQLITE_BYTES = 128 * 1024 * 1024
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")


@dataclass(frozen=True, slots=True)
class RawCommandResult:
    """Untrusted process output that must be redacted before it can be exposed."""

    exit_code: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Stable command result with output included only through a caller redactor."""

    category: str
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Injected no-shell execution boundary used by the transaction orchestrator."""

    def run(
        self,
        executable: Path,
        argv: tuple[str, ...],
        environment: Mapping[str, str],
        cwd: Path,
        timeout_seconds: float,
    ) -> RawCommandResult:
        """Execute one already-validated fixed argument vector."""


class SubprocessCommandRunner:
    """Concrete fixed-argument runner that always invokes subprocess without a shell."""

    def run(
        self,
        executable: Path,
        argv: tuple[str, ...],
        environment: Mapping[str, str],
        cwd: Path,
        timeout_seconds: float,
    ) -> RawCommandResult:
        try:
            completed = subprocess.run(
                [os.fspath(executable), *argv],
                check=False,
                cwd=os.fspath(cwd),
                env=dict(environment),
                shell=False,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError from None
        return RawCommandResult(completed.returncode, completed.stdout, completed.stderr)


def execute_command(
    runner: CommandRunner,
    *,
    executable: Path,
    argv: tuple[str, ...],
    environment: Mapping[str, str],
    cwd: Path,
    timeout_seconds: float,
    redact: Callable[[str], str] | None = None,
) -> CommandResult:
    """Run fixed arguments and expose output only after the caller explicitly redacts it."""
    _validate_command(executable, argv, environment, cwd, timeout_seconds)
    try:
        result = runner.run(executable, tuple(argv), MappingProxyType(dict(environment)), cwd, timeout_seconds)
    except TimeoutError:
        return CommandResult("command_timeout")
    except OSError:
        return CommandResult("command_unavailable")

    category = "ok" if result.exit_code == 0 else "command_failed"
    if redact is None:
        return CommandResult(category)
    return CommandResult(category, redact(result.stdout.decode("utf-8", errors="replace")), redact(result.stderr.decode("utf-8", errors="replace")))


def _validate_command(
    executable: Path,
    argv: tuple[str, ...],
    environment: Mapping[str, str],
    cwd: Path,
    timeout_seconds: float,
) -> None:
    if (
        not isinstance(argv, tuple)
        or not os.fspath(executable)
        or not os.fspath(cwd)
        or not all(isinstance(value, str) and value and not any(char in SHELL_CHARACTERS for char in value) for value in argv)
        or not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items())
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
    ):
        raise TransactionError("invalid_command")


class DeploymentLock:
    """A non-blocking advisory lock retained by its open file descriptor."""

    def __init__(self, path: Path):
        self._path = path
        self._stream: BinaryIO | None = None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    def acquire(self) -> None:
        """Acquire the caller-supplied lock immediately or fail with a stable code."""
        if self._stream is not None:
            return
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            stream = self._path.open("a+b")
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
                os.fsync(stream.fileno())
            stream.seek(0)
            _lock_nonblocking(stream)
        except OSError:
            try:
                stream.close()
            except UnboundLocalError:
                pass
            raise TransactionError("deployment_in_progress") from None
        self._stream = stream

    def release(self) -> None:
        """Release the held descriptor without deleting or changing the lock path."""
        if self._stream is None:
            return
        stream, self._stream = self._stream, None
        try:
            _unlock(stream)
        finally:
            stream.close()


def _lock_nonblocking(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def update_configuration_metadata(path: Path, *, version: str, last_updated: str) -> None:
    """Durably replace a regular JSON configuration after changing only two metadata fields.

    The descriptor is checked before reading and the destination is checked again before
    replacement. On POSIX the replacement inherits mode, uid, and gid; on Windows it
    intentionally relies on the parent directory's ACL policy because the standard
    library cannot preserve a file's ACL across replacement. A hostile swap in the
    narrow interval before ``os.replace`` remains a filesystem-level TOCTOU boundary
    for the future privileged caller to contain.
    """
    try:
        parse_version(version)
        if not isinstance(last_updated, str) or datetime.strptime(last_updated, "%Y-%m-%d").strftime("%Y-%m-%d") != last_updated:
            raise ValueError
    except (TypeError, ValueError, VersionError):
        raise TransactionError("invalid_metadata") from None
    try:
        payload, source_status = _read_regular_bytes(path, MAXIMUM_CONFIGURATION_BYTES)
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("technical_info"), dict):
            raise ValueError
        technical_info = value["technical_info"]
        technical_info["version"] = version
        technical_info["last_updated"] = last_updated
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_replace_verified(path, source_status, encoded)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise TransactionError("metadata_unavailable") from None


def _read_regular_bytes(path: Path, maximum: int) -> tuple[bytes, os.stat_result]:
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode) or initial.st_size > maximum:
        raise OSError("unsafe input")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if os.name == "posix":
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > maximum or not _same_file(initial, opened):
            raise OSError("unsafe input")
        payload = os.read(descriptor, maximum + 1)
        if len(payload) > maximum:
            raise OSError("oversized input")
        return payload, opened
    finally:
        os.close(descriptor)


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _atomic_replace_verified(path: Path, source_status: os.stat_result, payload: bytes) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="xb", dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
            temporary_name = stream.name
            if hasattr(os, "fchmod"):
                os.fchmod(stream.fileno(), stat.S_IMODE(source_status.st_mode))
            else:
                os.chmod(temporary_name, stat.S_IMODE(source_status.st_mode))
            if os.name == "posix" and hasattr(os, "fchown"):
                os.fchown(stream.fileno(), source_status.st_uid, source_status.st_gid)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        current = path.lstat()
        if not stat.S_ISREG(current.st_mode) or not _same_file(source_status, current):
            raise OSError("replaced input")
        os.replace(temporary_name, path)
        temporary_name = None
        _fsync_directory(path.parent)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    """Flush a parent directory, failing closed on POSIX and best-effort on Windows.

    Windows does not provide a portable standard-library directory ``fsync`` path.
    This module is a Linux server primitive, so a POSIX failure is always propagated;
    Windows callers receive only the platform's parent-directory ACL policy.
    """
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        if os.name == "posix":
            raise
        return
    try:
        os.fsync(descriptor)
    except OSError:
        if os.name == "posix":
            raise
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class BackupIdentity:
    """Redacted reference to one validated SQLite backup."""

    filename: str
    sha256: str


def backup_sqlite_database(source: Path, destination: Path, *, timeout_seconds: float = 30) -> BackupIdentity:
    """Create, durably write, and validate an online SQLite backup without reopening it by name.

    SQLite writes its online snapshot to a private temporary database.  The verified
    bytes are then copied through one exclusively-created destination descriptor, read
    back from that descriptor, and validated before return.  The final ``lstat`` only
    proves that the caller-visible name still denotes the reserved inode; it is never
    used to read the returned backup.
    """
    destination_status: os.stat_result | None = None
    temporary_path: Path | None = None
    temporary_status: os.stat_result | None = None
    try:
        source_status = _assert_regular_file(source)
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError
        deadline = time.monotonic() + timeout_seconds
        with tempfile.NamedTemporaryFile(mode="xb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".sqlite", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary_status = os.fstat(temporary.fileno())
        source_connection = sqlite3.connect(f"{source.absolute().as_uri()}?mode=ro", uri=True, timeout=timeout_seconds)
        temporary_connection = sqlite3.connect(temporary_path, timeout=timeout_seconds)
        try:
            def progress(status: int, _remaining: int, _total: int) -> None:
                if status in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED} and time.monotonic() >= deadline:
                    raise TimeoutError
                if time.monotonic() >= deadline:
                    raise TimeoutError

            source_connection.backup(temporary_connection, pages=128, progress=progress, sleep=min(0.01, timeout_seconds))
            # A WAL-mode source copies its journal-mode marker into the temporary
            # database. Switch only the private copy back to a self-contained file
            # before validating the exact bytes copied to the destination descriptor.
            temporary_connection.execute("PRAGMA journal_mode=DELETE").fetchone()
        finally:
            temporary_connection.close()
            source_connection.close()
        if not _same_file(source_status, source.lstat()):
            raise OSError("replaced source")
        payload, _ = _read_regular_bytes(temporary_path, MAXIMUM_SQLITE_BYTES)
        _validate_sqlite_bytes(payload)
        descriptor = os.open(
            destination,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            destination_status = os.fstat(descriptor)
            if not stat.S_ISREG(destination_status.st_mode):
                raise OSError("unsafe output")
            _write_all(descriptor, payload)
            os.fsync(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            saved_payload = _read_all(descriptor, MAXIMUM_SQLITE_BYTES)
            if saved_payload != payload:
                raise OSError("short write")
            digest = _validate_sqlite_bytes(saved_payload)
        finally:
            os.close(descriptor)
        _fsync_directory(destination.parent)
        if not _same_file(destination_status, destination.lstat()):
            raise OSError("replaced destination")
        return BackupIdentity(destination.name, digest)
    except (OSError, sqlite3.Error, ValueError, TimeoutError):
        if destination_status is not None:
            _unlink_if_same(destination, destination_status)
        raise TransactionError("backup_unavailable") from None
    finally:
        if temporary_path is not None and temporary_status is not None:
            _unlink_if_same(temporary_path, temporary_status)


def validate_sqlite_backup(path: Path) -> BackupIdentity:
    """Validate a backup without returning any database contents."""
    try:
        payload, _ = _read_regular_bytes(path, MAXIMUM_SQLITE_BYTES)
        return BackupIdentity(path.name, _validate_sqlite_bytes(payload))
    except (OSError, sqlite3.Error, ValueError):
        raise TransactionError("backup_invalid") from None


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError
        view = view[written:]


def _read_all(descriptor: int, maximum: int) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum + 1
    while remaining:
        chunk = os.read(descriptor, min(64 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) > maximum:
        raise OSError("oversized input")
    return payload


def _validate_sqlite_bytes(payload: bytes) -> str:
    connection = sqlite3.connect(":memory:")
    try:
        connection.deserialize(payload)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchone()
    finally:
        connection.close()
    if integrity != ("ok",) or foreign_keys is not None:
        raise ValueError("integrity")
    return sha256(payload).hexdigest()


def _unlink_if_same(path: Path, expected: os.stat_result) -> None:
    try:
        if _same_file(expected, path.lstat()):
            path.unlink()
    except OSError:
        pass


def _fsync_regular_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR | getattr(os, "O_BINARY", 0))
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError("unsafe output")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _assert_regular_file(path: Path) -> os.stat_result:
    status = path.lstat()
    if not stat.S_ISREG(status.st_mode):
        raise OSError("unsafe input")
    return status


def _digest_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    generation: str
    boot_id: str


@dataclass(frozen=True, slots=True)
class HealthPolicy:
    startup_timeout_seconds: int = 60
    stop_timeout_seconds: int = 180
    observation_window_seconds: int = 30

    def __post_init__(self) -> None:
        values = (self.startup_timeout_seconds, self.stop_timeout_seconds, self.observation_window_seconds)
        if any(not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 3600 for value in values):
            raise TransactionError("invalid_health_policy")


@dataclass(frozen=True, slots=True)
class HealthResult:
    ready: bool
    diagnostic_code: str


def evaluate_readiness(
    path: Path,
    expected_sha: str,
    *,
    now: Callable[[], datetime],
    expected_process: ProcessIdentity | None = None,
    policy: HealthPolicy = HealthPolicy(),
) -> HealthResult:
    """Evaluate a bounded local readiness JSON file without reading logs or contacting Discord."""
    try:
        payload, _ = _read_regular_bytes(path, MAXIMUM_READINESS_BYTES)
        value = json.loads(payload.decode("utf-8"))
        expected_keys = {"schema_version", "release_sha", "pid", "generation", "boot_id", "ready_at", "heartbeat_at"}
        if not isinstance(value, dict) or set(value) != expected_keys or type(value["schema_version"]) is not int or value["schema_version"] != 1:
            return HealthResult(False, "readiness_schema_invalid")
        if not isinstance(expected_sha, str) or not SHA_PATTERN.fullmatch(expected_sha) or value["release_sha"] != expected_sha:
            return HealthResult(False, "release_mismatch")
        if type(value["pid"]) is not int or value["pid"] <= 0 or not _valid_uuid(value["generation"]) or not isinstance(value["boot_id"], str) or not 1 <= len(value["boot_id"]) <= 128:
            return HealthResult(False, "readiness_schema_invalid")
        if expected_process is not None and (value["pid"], value["generation"], value["boot_id"]) != (
            expected_process.pid,
            expected_process.generation,
            expected_process.boot_id,
        ):
            return HealthResult(False, "process_mismatch")
        current = now()
        heartbeat = _parse_timestamp(value["heartbeat_at"])
        ready_at = _parse_timestamp(value["ready_at"])
        if current.tzinfo is None or ready_at > heartbeat or heartbeat > current or heartbeat < current - timedelta(seconds=policy.observation_window_seconds):
            return HealthResult(False, "readiness_stale")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError, KeyError, TypeError):
        return HealthResult(False, "readiness_unavailable")
    return HealthResult(True, "ready")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp")
    return parsed


def _valid_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        from uuid import UUID
        return str(UUID(value)) == value
    except ValueError:
        return False


class TransactionBoundary(StrEnum):
    BEFORE_STOP = "before_stop"
    AFTER_STOP_PRE_START = "after_stop_pre_start"
    AFTER_MIGRATION_BEFORE_NEW_PROCESS = "after_migration_before_new_process"
    AFTER_NEW_PROCESS_START = "after_new_process_start"
    POST_HEALTH = "post_health"


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    action: str


def classify_recovery(boundary: TransactionBoundary, *, pre_state_verified: bool) -> RecoveryDecision:
    """Choose recovery without ever reporting an unverified restore as a success."""
    before_new_process = {
        TransactionBoundary.AFTER_STOP_PRE_START,
        TransactionBoundary.AFTER_MIGRATION_BEFORE_NEW_PROCESS,
    }
    if boundary is TransactionBoundary.BEFORE_STOP:
        return RecoveryDecision("untouched")
    if boundary in before_new_process and pre_state_verified:
        return RecoveryDecision("restore_pre_start_state")
    return RecoveryDecision("manual_intervention")
