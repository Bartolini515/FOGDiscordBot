"""Typed, no-shell orchestration for one manually-authorized FogBot deployment.

This module deliberately has no ambient process, network, or service-manager access.
The root-owned helper supplies concrete fixed-argv adapters; tests supply fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from .protocol import SHA_PATTERN, SubmitRequest, parse_version
from .state import OperationRecord, OperationStore, StateError
from .transaction import (
    BackupIdentity,
    CommandRunner,
    DeploymentLock,
    HealthPolicy,
    ProcessIdentity,
    TransactionError,
    backup_sqlite_database,
    execute_command,
    update_configuration_metadata,
    validate_sqlite_backup,
)


class DeploymentFailure(RuntimeError):
    """A stable public deployment diagnostic with no operational detail."""


@dataclass(frozen=True, slots=True)
class DeploymentOutcome:
    """The sole caller-visible deployment result."""

    ok: bool
    diagnostic_code: str


@dataclass(frozen=True, slots=True)
class ReleaseIdentity:
    """A validated immutable release identity; neither field is a filesystem path."""

    sha: str
    release_id: str

    def __post_init__(self) -> None:
        if not SHA_PATTERN.fullmatch(self.sha) or not self.release_id or len(self.release_id) > 128:
            raise DeploymentFailure("release_preparation_failed")


@dataclass(frozen=True, slots=True)
class ServerLayout:
    """Immutable, caller-provided filesystem shape for the root-owned server helper."""

    releases: Path
    shared: Path
    state: Path
    operations: Path
    backups: Path
    configuration: Path
    database: Path
    readiness: Path
    sha_marker: Path
    minimum_free_bytes: int = 512 * 1024 * 1024

    def validate(self) -> None:
        """Fail before mutation unless all server paths satisfy the Linux layout contract."""
        values = (
            self.releases,
            self.shared,
            self.state,
            self.operations,
            self.backups,
            self.configuration,
            self.database,
            self.readiness,
            self.sha_marker,
        )
        if not isinstance(self.minimum_free_bytes, int) or isinstance(self.minimum_free_bytes, bool) or self.minimum_free_bytes < 0:
            raise DeploymentFailure("layout_invalid")
        if any(not path.is_absolute() or ".." in path.parts for path in values):
            raise DeploymentFailure("layout_invalid")
        if not (
            _below(self.operations, self.state)
            and _below(self.backups, self.state)
            and _below(self.configuration, self.shared)
            and _below(self.database, self.shared)
            and _below(self.readiness, self.state)
            and _below(self.sha_marker, self.state)
        ):
            raise DeploymentFailure("layout_invalid")
        try:
            for directory in (self.releases, self.shared, self.state, self.operations, self.backups):
                _trusted_directory(directory)
            for file_path in (self.configuration, self.database):
                _regular_file(file_path)
            if shutil.disk_usage(self.releases).free < self.minimum_free_bytes:
                raise OSError
        except OSError:
            raise DeploymentFailure("layout_invalid") from None


class ReleasePreparer(Protocol):
    def existing_identity(self, sha: str) -> str | None: ...
    def prepare(self, sha: str, timeout_seconds: int) -> ReleaseIdentity: ...
    def verify(self, release: ReleaseIdentity) -> bool: ...
    def preflight(self, release: ReleaseIdentity, timeout_seconds: int) -> bool: ...
    def cleanup(self, release_id: str) -> None: ...


class ServiceController(Protocol):
    def is_active(self, timeout_seconds: int) -> bool: ...
    def stop(self, timeout_seconds: int) -> None: ...
    def start(self, timeout_seconds: int) -> None: ...


class ProcessInspector(Protocol):
    def no_bot_process(self, timeout_seconds: int) -> bool: ...
    def acquire_instance_lock(self, timeout_seconds: int) -> bool: ...
    def identity(self, timeout_seconds: int) -> ProcessIdentity | None: ...


class MigrationRunner(Protocol):
    def rehearse(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool: ...
    def apply(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool: ...
    def validate(self, database: Path, timeout_seconds: int) -> bool: ...


class ReleaseSwitcher(Protocol):
    def current_release_id(self) -> str: ...
    def switch(self, release: ReleaseIdentity) -> None: ...
    def restore(self, release_id: str) -> None: ...


class GitHubVerifier(Protocol):
    def verify(self, request: SubmitRequest) -> object: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class HealthObserver(Protocol):
    def observe(self, expected_sha: str, expected_process: ProcessIdentity, policy: HealthPolicy) -> bool: ...


@dataclass(frozen=True, slots=True)
class DeploymentDependencies:
    preparer: ReleasePreparer
    service: ServiceController
    processes: ProcessInspector
    migrations: MigrationRunner
    switcher: ReleaseSwitcher
    verifier: GitHubVerifier
    clock: Clock
    health: HealthObserver


@dataclass(frozen=True, slots=True)
class _Snapshot:
    previous_release: str
    database: BackupIdentity
    configuration: BackupIdentity


class DeploymentOrchestrator:
    """Run the manual transaction while holding one lock until a durable final state."""

    def __init__(self, layout: ServerLayout, store: OperationStore, dependencies: DeploymentDependencies, policy: HealthPolicy = HealthPolicy()):
        self._layout = layout
        self._store = store
        self._dependencies = dependencies
        self._policy = policy

    def run(self, operation_id: str) -> DeploymentOutcome:
        """Run one durable operation. Interruptions deliberately propagate after their last saved phase."""
        try:
            record = self._store.read(operation_id)
        except (StateError, OSError):
            return DeploymentOutcome(False, "state_invalid")
        try:
            with DeploymentLock(self._layout.state / "deployment.lock"):
                return self._run_locked(record)
        except TransactionError as error:
            return DeploymentOutcome(False, _safe_code(str(error), "deployment_in_progress"))

    def _run_locked(self, record: OperationRecord) -> DeploymentOutcome:
        release: ReleaseIdentity | None = None
        snapshot: _Snapshot | None = None
        stopped = False
        new_process_started = False
        try:
            record = self._persist(record, "preparing", "pending")
            self._validate_target(record)
            self._layout.validate()
            existing = self._dependencies.preparer.existing_identity(record.target["sha"])
            if existing not in {None, record.target["sha"]}:
                raise DeploymentFailure("release_conflict")
            self._assert_capacity()
            if not self._dependencies.service.is_active(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("service_state_invalid")
            release = self._dependencies.preparer.prepare(record.target["sha"], self._policy.startup_timeout_seconds)
            if release.sha != record.target["sha"] or not self._dependencies.preparer.verify(release):
                raise DeploymentFailure("release_identity_invalid")
            if not self._dependencies.preparer.preflight(release, self._policy.startup_timeout_seconds):
                raise DeploymentFailure("preflight_failed")
            record = self._persist(record, "ready_to_stop", "pending")
            self._revalidate(record)
            self._dependencies.service.stop(self._policy.stop_timeout_seconds)
            stopped = True
            if self._dependencies.service.is_active(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("stop_failed")
            if not self._dependencies.processes.no_bot_process(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("exclusion_failed")
            if not self._dependencies.processes.acquire_instance_lock(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("exclusion_failed")
            record = self._persist(record, "stopped", "pending")
            snapshot = self._backup(record)
            record = self._persist(
                record,
                "backed_up",
                "pending",
                previous_release=snapshot.previous_release,
                backup_release_id=snapshot.configuration.filename,
                backup_database_id=snapshot.database.filename,
            )
            warsaw_date = self._warsaw_date()
            update_configuration_metadata(self._layout.configuration, version=record.target["target_version"], last_updated=warsaw_date)
            rehearsal_database = self._layout.backups / f"{record.operation_id}.rehearsal.sqlite"
            _restore_file(self._layout.backups / snapshot.database.filename, rehearsal_database, validate_sqlite_backup)
            if not self._dependencies.migrations.rehearse(release, rehearsal_database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            if not self._dependencies.migrations.apply(release, self._layout.database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            if not self._dependencies.migrations.validate(self._layout.database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            record = self._persist(record, "migrated", "pending", migration_applied=True)
            self._dependencies.switcher.switch(release)
            _write_sha_marker(self._layout.sha_marker, release.sha)
            record = self._persist(record, "switched", "pending")
            record = self._persist(record, "starting", "pending")
            # A failed start command may still have spawned a process. Treat the
            # boundary conservatively: never restore mutable state afterward.
            new_process_started = True
            self._dependencies.service.start(self._policy.startup_timeout_seconds)
            if not self._dependencies.service.is_active(self._policy.startup_timeout_seconds):
                raise DeploymentFailure("start_failed")
            process = self._dependencies.processes.identity(self._policy.startup_timeout_seconds)
            if process is None or not self._dependencies.health.observe(release.sha, process, self._policy):
                raise DeploymentFailure("health_check_failed")
            record = self._persist(record, "health_check", "pending")
            self._persist(record, "succeeded", "completed", result="success")
            return DeploymentOutcome(True, "completed")
        except DeploymentFailure as error:
            return self._recover(record, release, snapshot, stopped, new_process_started, _safe_code(str(error), "preparation_failed"))
        except TransactionError as error:
            return self._recover(record, release, snapshot, stopped, new_process_started, _safe_code(str(error), "preparation_failed"))
        except (OSError, ValueError, TypeError):
            return self._recover(record, release, snapshot, stopped, new_process_started, "preparation_failed")

    def _validate_target(self, record: OperationRecord) -> None:
        try:
            sha = record.target["sha"]
            if not isinstance(sha, str) or not SHA_PATTERN.fullmatch(sha):
                raise ValueError
            parse_version(record.target["target_version"])
            if any(not isinstance(record.target[key], int) or record.target[key] <= 0 for key in ("repository_id", "run_id", "run_attempt")):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise DeploymentFailure("target_invalid") from None

    def _assert_capacity(self) -> None:
        try:
            if shutil.disk_usage(self._layout.releases).free < self._layout.minimum_free_bytes:
                raise OSError
        except OSError:
            raise DeploymentFailure("capacity_insufficient") from None

    def _revalidate(self, record: OperationRecord) -> None:
        request = SubmitRequest(
            sha=record.target["sha"],
            run_id=record.target["run_id"],
            run_attempt=record.target["run_attempt"],
            repository_id=record.target["repository_id"],
            version=record.target["target_version"],
        )
        try:
            verified = self._dependencies.verifier.verify(request)
            if (
                getattr(verified, "sha", None) != request.sha
                or getattr(verified, "repository_id", None) != request.repository_id
                or getattr(verified, "run_id", None) != request.run_id
                or getattr(verified, "run_attempt", None) != request.run_attempt
            ):
                raise ValueError
        except (DeploymentFailure, ValueError, TypeError, AttributeError):
            raise DeploymentFailure("revalidation_failed") from None

    def _backup(self, record: OperationRecord) -> _Snapshot:
        try:
            previous_release = self._dependencies.switcher.current_release_id()
            if not previous_release or len(previous_release) > 128:
                raise ValueError
            database = backup_sqlite_database(self._layout.database, self._layout.backups / f"{record.operation_id}.sqlite")
            configuration = _backup_configuration(
                self._layout.configuration, self._layout.backups / f"{record.operation_id}.configuration.json"
            )
            return _Snapshot(previous_release, database, configuration)
        except (OSError, ValueError, TransactionError):
            raise DeploymentFailure("backup_failed") from None

    def _warsaw_date(self) -> str:
        now = self._dependencies.clock.now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise DeploymentFailure("clock_invalid")
        try:
            return now.astimezone(ZoneInfo("Europe/Warsaw")).date().isoformat()
        except Exception:
            # Windows development images can omit the IANA tzdata database. The
            # production Linux helper uses ZoneInfo; this deterministic EU-DST
            # fallback keeps the tested Warsaw contract available offline.
            return (now.astimezone(UTC) + _warsaw_offset(now.astimezone(UTC))).date().isoformat()

    def _recover(
        self,
        record: OperationRecord,
        release: ReleaseIdentity | None,
        snapshot: _Snapshot | None,
        stopped: bool,
        new_process_started: bool,
        code: str,
    ) -> DeploymentOutcome:
        if not stopped:
            if release is not None:
                try:
                    self._dependencies.preparer.cleanup(release.release_id)
                except (OSError, ValueError, TypeError):
                    pass
            self._persist_final(record, "failed", code)
            return DeploymentOutcome(False, code)
        if new_process_started:
            if new_process_started:
                try:
                    self._dependencies.service.stop(self._policy.stop_timeout_seconds)
                except (DeploymentFailure, OSError, ValueError, TypeError):
                    pass
            self._persist_final(record, "manual_intervention", "manual_intervention_required")
            return DeploymentOutcome(False, "manual_intervention_required")
        if snapshot is None:
            self._persist_final(record, "failed", "recovered")
            return DeploymentOutcome(False, "recovered")
        try:
            _restore_file(self._layout.backups / snapshot.configuration.filename, self._layout.configuration, _validate_configuration)
            _restore_file(self._layout.backups / snapshot.database.filename, self._layout.database, validate_sqlite_backup)
            self._dependencies.switcher.restore(snapshot.previous_release)
        except (DeploymentFailure, TransactionError, OSError, ValueError, TypeError):
            self._persist_final(record, "manual_intervention", "manual_intervention_required")
            return DeploymentOutcome(False, "manual_intervention_required")
        self._persist_final(record, "failed", "recovered")
        return DeploymentOutcome(False, "recovered")

    def _persist(self, record: OperationRecord, phase: str, code: str, **changes: object) -> OperationRecord:
        updated = record.with_phase(phase, code, **changes)
        self._store.write(updated)
        return updated

    def _persist_final(self, record: OperationRecord, phase: str, code: str) -> None:
        try:
            self._persist(record, phase, code, result="failure")
        except (StateError, OSError, ValueError):
            pass


class _FixedService:
    def __init__(self, runner: CommandRunner, cwd: Path): self._runner, self._cwd = runner, cwd
    def is_active(self, timeout_seconds: int) -> bool: return _fixed(self._runner, "/bin/systemctl", ("is-active", "--quiet", "fogbot.service"), self._cwd, timeout_seconds) == "ok"
    def stop(self, timeout_seconds: int) -> None: _require(_fixed(self._runner, "/bin/systemctl", ("stop", "fogbot.service"), self._cwd, timeout_seconds), "stop_failed")
    def start(self, timeout_seconds: int) -> None: _require(_fixed(self._runner, "/bin/systemctl", ("start", "fogbot.service"), self._cwd, timeout_seconds), "start_failed")


class _FixedPreparer:
    def __init__(self, runner: CommandRunner, cwd: Path): self._runner, self._cwd = runner, cwd
    def existing_identity(self, sha: str) -> str | None: return None
    def prepare(self, sha: str, timeout_seconds: int) -> ReleaseIdentity:
        _require(_fixed(self._runner, "/usr/bin/git", ("fetch", "--depth", "1", "origin", sha), self._cwd, timeout_seconds), "release_preparation_failed")
        return ReleaseIdentity(sha, sha)
    def verify(self, release: ReleaseIdentity) -> bool:
        return _fixed(self._runner, "/usr/bin/git", ("cat-file", "-e", release.sha), self._cwd, 60) == "ok"
    def preflight(self, release: ReleaseIdentity, timeout_seconds: int) -> bool:
        sync = _fixed(self._runner, "/usr/local/bin/pipenv", ("sync", "--deploy", "--ignore-pipfile"), self._cwd, timeout_seconds)
        compile_result = _fixed(self._runner, "/usr/local/bin/pipenv", ("run", "python", "-m", "compileall", "."), self._cwd, timeout_seconds)
        return sync == "ok" and compile_result == "ok"
    def cleanup(self, release_id: str) -> None: return None


class _FixedMigrations:
    def __init__(self, runner: CommandRunner, cwd: Path): self._runner, self._cwd = runner, cwd
    def rehearse(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        return _fixed(self._runner, "/usr/local/bin/pipenv", ("run", "yoyo", "apply", "--batch", "--database", str(database)), self._cwd, timeout_seconds) == "ok"
    def apply(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        return _fixed(self._runner, "/usr/local/bin/pipenv", ("run", "yoyo", "apply", "--batch", "--database", str(database)), self._cwd, timeout_seconds) == "ok"
    def validate(self, database: Path, timeout_seconds: int) -> bool:
        return _fixed(self._runner, "/usr/local/bin/pipenv", ("run", "yoyo", "list", "--database", str(database)), self._cwd, timeout_seconds) == "ok"


@dataclass(frozen=True, slots=True)
class FixedArgAdapters:
    """Reviewable concrete adapters. They use only Task 2's no-shell runner."""

    runner: CommandRunner
    cwd: Path

    @property
    def service(self) -> _FixedService: return _FixedService(self.runner, self.cwd)
    @property
    def preparer(self) -> _FixedPreparer: return _FixedPreparer(self.runner, self.cwd)
    @property
    def migrations(self) -> _FixedMigrations: return _FixedMigrations(self.runner, self.cwd)


class AtomicSymlinkSwitcher:
    """Atomically replace ``current`` with a symlink to one verified release SHA."""

    def __init__(self, releases: Path, current: Path):
        self._releases = releases
        self._current = current

    def current_release_id(self) -> str:
        try:
            _trusted_directory(self._releases)
            _trusted_directory(self._current.parent)
            status = self._current.lstat()
            if not stat.S_ISLNK(status.st_mode):
                raise OSError
            resolved = self._current.resolve(strict=True)
            if resolved.parent != self._releases.resolve(strict=True):
                raise OSError
            release_id = resolved.name
            self._release_path(release_id)
            return release_id
        except OSError:
            raise DeploymentFailure("switch_failed") from None

    def switch(self, release: ReleaseIdentity) -> None:
        if release.release_id != release.sha:
            raise DeploymentFailure("switch_failed")
        self._replace(release.sha)

    def restore(self, release_id: str) -> None:
        self._replace(release_id)

    def _replace(self, release_id: str) -> None:
        temporary = self._current.with_name(f".{self._current.name}.{uuid4().hex}.tmp")
        try:
            target = self._release_path(release_id)
            _trusted_directory(self._current.parent)
            temporary.symlink_to(target, target_is_directory=True)
            os.replace(temporary, self._current)
            _fsync_parent(self._current.parent)
        except OSError:
            raise DeploymentFailure("switch_failed") from None
        finally:
            temporary.unlink(missing_ok=True)

    def _release_path(self, release_id: str) -> Path:
        if not isinstance(release_id, str) or not SHA_PATTERN.fullmatch(release_id):
            raise DeploymentFailure("switch_failed")
        target = self._releases / release_id
        try:
            status = target.lstat()
            if not stat.S_ISDIR(status.st_mode):
                raise OSError
        except OSError:
            raise DeploymentFailure("switch_failed") from None
        return target


def _fixed(runner: CommandRunner, executable: str, argv: tuple[str, ...], cwd: Path, timeout: int) -> str:
    return execute_command(runner, executable=Path(executable), argv=argv, environment={"LANG": "C"}, cwd=cwd, timeout_seconds=timeout).category


def _require(category: str, code: str) -> None:
    if category != "ok":
        raise DeploymentFailure(code)


def _below(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return path != parent
    except ValueError:
        return False


def _trusted_directory(path: Path) -> None:
    status = path.lstat()
    if not stat.S_ISDIR(status.st_mode):
        raise OSError
    if os.name == "posix" and (status.st_uid != os.geteuid() or stat.S_IMODE(status.st_mode) & 0o022):
        raise OSError


def _regular_file(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise OSError


def _backup_configuration(source: Path, destination: Path) -> BackupIdentity:
    payload = _configuration_bytes(source)
    _write_private(destination, payload)
    _validate_configuration(destination)
    return BackupIdentity(destination.name, sha256(payload).hexdigest())


def _configuration_bytes(path: Path) -> bytes:
    _regular_file(path)
    payload = path.read_bytes()
    if len(payload) > 64 * 1024:
        raise OSError
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError
    return payload


def _validate_configuration(path: Path) -> BackupIdentity:
    payload = _configuration_bytes(path)
    return BackupIdentity(path.name, sha256(payload).hexdigest())


def _write_private(destination: Path, payload: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _fsync_parent(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _restore_file(source: Path, destination: Path, validator: object) -> None:
    validator(source)  # type: ignore[operator]
    _write_private(destination, source.read_bytes())
    validator(destination)  # type: ignore[operator]


def _write_sha_marker(path: Path, sha: str) -> None:
    if not SHA_PATTERN.fullmatch(sha):
        raise DeploymentFailure("switch_failed")
    _write_private(path, f"{sha}\n".encode("ascii"))


def _safe_code(value: str, fallback: str) -> str:
    allowed = {
        "deployment_in_progress", "layout_invalid", "capacity_insufficient", "service_state_invalid", "release_conflict",
        "release_preparation_failed", "release_identity_invalid", "preflight_failed", "revalidation_failed", "stop_failed",
        "exclusion_failed", "backup_failed", "migration_failed", "switch_failed", "start_failed", "health_check_failed",
        "clock_invalid", "target_invalid", "preparation_failed",
    }
    return value if value in allowed else fallback


def _warsaw_offset(value: datetime) -> timedelta:
    """Return the post-1996 Europe/Warsaw EU summer-time offset without tzdata."""
    year = value.year
    march = datetime(year, 3, 31, 1, tzinfo=UTC)
    october = datetime(year, 10, 31, 1, tzinfo=UTC)
    start = march - timedelta(days=(march.weekday() + 1) % 7)
    end = october - timedelta(days=(october.weekday() + 1) % 7)
    return timedelta(hours=2 if start <= value < end else 1)
