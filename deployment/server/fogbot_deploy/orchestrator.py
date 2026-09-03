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
import time
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
    _read_regular_bytes,
    _same_file,
    evaluate_readiness,
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
    path: Path

    def __post_init__(self) -> None:
        if (
            not SHA_PATTERN.fullmatch(self.sha)
            or self.release_id != self.sha
            or not isinstance(self.path, Path)
            or not self.path.is_absolute()
            or self.path.name != self.sha
        ):
            raise DeploymentFailure("release_identity_invalid")
        object.__setattr__(self, "path", self.path.resolve(strict=False))


@dataclass(frozen=True, slots=True)
class ServerLayout:
    """Immutable, caller-provided filesystem shape for the root-owned server helper."""

    releases: Path
    source_repository: Path
    shared: Path
    state: Path
    operations: Path
    backups: Path
    configuration: Path
    database: Path
    readiness: Path
    instance_lock: Path
    sha_marker: Path
    minimum_free_bytes: int = 512 * 1024 * 1024

    def validate(self) -> None:
        """Fail before mutation unless all server paths satisfy the Linux layout contract."""
        values = (
            self.releases,
            self.source_repository,
            self.shared,
            self.state,
            self.operations,
            self.backups,
            self.configuration,
            self.database,
            self.readiness,
            self.instance_lock,
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
            and _below(self.instance_lock, self.state)
            and _below(self.sha_marker, self.state)
        ):
            raise DeploymentFailure("layout_invalid")
        try:
            for directory in (self.releases, self.source_repository, self.shared, self.state, self.operations, self.backups):
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
    def validate(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool: ...


class ReleaseSwitcher(Protocol):
    def current_release_id(self) -> str: ...
    def switch(self, release: ReleaseIdentity) -> None: ...
    def restore(self, release_id: str) -> None: ...


class GitHubVerifier(Protocol):
    def verify(self, request: SubmitRequest) -> object: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class HealthObserver(Protocol):
    def observe(self, expected_sha: str, policy: HealthPolicy) -> bool: ...


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
    previous_marker_sha: str
    database: BackupIdentity
    configuration: BackupIdentity


class DeploymentOrchestrator:
    """Run the manual transaction while holding one lock until a durable final state."""

    def __init__(self, layout: ServerLayout, store: OperationStore, dependencies: DeploymentDependencies, policy: HealthPolicy = HealthPolicy()):
        layout.validate()
        if store.directory.resolve(strict=False) != layout.operations.resolve(strict=False):
            raise DeploymentFailure("layout_invalid")
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
                if _switch_journal_path(self._layout.sha_marker).exists():
                    try:
                        reconcile_release_and_marker(self._dependencies.switcher, self._layout.sha_marker)
                    except DeploymentFailure:
                        self._persist_final(record, "manual_intervention", "manual_intervention_required")
                        return DeploymentOutcome(False, "manual_intervention_required")
                    return self._resume_interrupted_switch(record)
                return self._run_locked(record)
        except TransactionError as error:
            return DeploymentOutcome(False, _safe_code(str(error), "deployment_in_progress"))
        except Exception:
            return DeploymentOutcome(False, "preparation_failed")

    def _resume_interrupted_switch(self, record: OperationRecord) -> DeploymentOutcome:
        """Return the bot to a verified running state after a journaled pre-start interruption."""
        try:
            if not self._dependencies.service.is_active(self._policy.stop_timeout_seconds):
                self._dependencies.service.start(self._policy.startup_timeout_seconds)
            if not self._dependencies.service.is_active(self._policy.startup_timeout_seconds):
                raise DeploymentFailure("start_failed")
            if not self._dependencies.health.observe(record.target["sha"], self._policy):
                raise DeploymentFailure("health_check_failed")
            if self._dependencies.processes.identity(self._policy.startup_timeout_seconds) is None:
                raise DeploymentFailure("health_check_failed")
        except (DeploymentFailure, TransactionError, OSError, ValueError, TypeError):
            self._persist_final(record, "manual_intervention", "manual_intervention_required")
            return DeploymentOutcome(False, "manual_intervention_required")
        self._persist_final(record, "failed", "recovered")
        return DeploymentOutcome(False, "recovered")

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
            if not self._valid_release(release, record.target["sha"]) or not self._dependencies.preparer.verify(release):
                raise DeploymentFailure("release_identity_invalid")
            if not self._dependencies.preparer.preflight(release, self._policy.startup_timeout_seconds):
                raise DeploymentFailure("preflight_failed")
            record = self._persist(record, "ready_to_stop", "pending")
            self._revalidate(record)
            record = self._persist(record, "stopping", "pending")
            try:
                self._dependencies.service.stop(self._policy.stop_timeout_seconds)
            except (DeploymentFailure, TransactionError, OSError, ValueError, TypeError):
                try:
                    service_still_active = self._dependencies.service.is_active(self._policy.stop_timeout_seconds)
                except (DeploymentFailure, TransactionError, OSError, ValueError, TypeError):
                    self._persist_final(record, "manual_intervention", "manual_intervention_required")
                    return DeploymentOutcome(False, "manual_intervention_required")
                if not service_still_active:
                    stopped = True
                    record = self._persist(record, "stopped", "pending")
                raise DeploymentFailure("stop_failed") from None
            stopped = True
            record = self._persist(record, "stopped", "pending")
            if self._dependencies.service.is_active(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("stop_failed")
            if not self._dependencies.processes.no_bot_process(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("exclusion_failed")
            if not self._dependencies.processes.acquire_instance_lock(self._policy.stop_timeout_seconds):
                raise DeploymentFailure("exclusion_failed")
            snapshot = self._backup(record)
            record = self._persist(
                record,
                "backed_up",
                "pending",
                previous_release=snapshot.previous_release,
                previous_marker_sha=snapshot.previous_marker_sha,
                backup_configuration_id=snapshot.configuration.filename,
                backup_database_id=snapshot.database.filename,
            )
            warsaw_date = self._warsaw_date()
            update_configuration_metadata(self._layout.configuration, version=record.target["target_version"], last_updated=warsaw_date)
            rehearsal_database = self._layout.backups / f"{record.operation_id}.rehearsal.sqlite"
            _restore_file(self._layout.backups / snapshot.database.filename, rehearsal_database, validate_sqlite_backup, snapshot.database)
            if not self._dependencies.migrations.rehearse(release, rehearsal_database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            if not self._dependencies.migrations.apply(release, self._layout.database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            if not self._dependencies.migrations.validate(release, self._layout.database, self._policy.stop_timeout_seconds):
                raise DeploymentFailure("migration_failed")
            record = self._persist(record, "migrated", "pending", migration_applied=True)
            switch_release_and_marker(self._dependencies.switcher, self._layout.sha_marker, release)
            record = self._persist(record, "switched", "pending")
            record = self._persist(record, "starting", "pending")
            # A failed start command may still have spawned a process. Treat the
            # boundary conservatively: never restore mutable state afterward.
            new_process_started = True
            self._dependencies.service.start(self._policy.startup_timeout_seconds)
            if not self._dependencies.service.is_active(self._policy.startup_timeout_seconds):
                raise DeploymentFailure("start_failed")
            if not self._dependencies.health.observe(release.sha, self._policy):
                raise DeploymentFailure("health_check_failed")
            if self._dependencies.processes.identity(self._policy.startup_timeout_seconds) is None:
                raise DeploymentFailure("health_check_failed")
            record = self._persist(record, "health_check", "pending")
            self._persist(record, "succeeded", "completed", result="success", deployment_date=warsaw_date, deployed_release_id=release.release_id)
            return DeploymentOutcome(True, "completed")
        except DeploymentFailure as error:
            return self._recover(record, release, snapshot, stopped, new_process_started, _safe_code(str(error), "preparation_failed"))
        except TransactionError as error:
            return self._recover(record, release, snapshot, stopped, new_process_started, _safe_code(str(error), "preparation_failed"))
        except Exception:
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

    def _valid_release(self, release: ReleaseIdentity, sha: str) -> bool:
        try:
            if release.sha != sha or release.release_id != sha or release.path != (self._layout.releases / sha).resolve(strict=False):
                return False
            status = release.path.lstat()
            return stat.S_ISDIR(status.st_mode) and not stat.S_ISLNK(status.st_mode)
        except OSError:
            return False

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
            previous_marker_sha = _read_sha_marker(self._layout.sha_marker)
            if not previous_release or len(previous_release) > 128:
                raise ValueError
            database = backup_sqlite_database(self._layout.database, self._layout.backups / f"{record.operation_id}.sqlite")
            configuration = _backup_configuration(
                self._layout.configuration, self._layout.backups / f"{record.operation_id}.configuration.json"
            )
            return _Snapshot(previous_release, previous_marker_sha, database, configuration)
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
            try:
                self._dependencies.service.stop(self._policy.stop_timeout_seconds)
            except (DeploymentFailure, TransactionError, OSError, ValueError, TypeError):
                pass
            self._persist_final(record, "manual_intervention", "manual_intervention_required")
            return DeploymentOutcome(False, "manual_intervention_required")
        if snapshot is None:
            try:
                if not self._dependencies.service.is_active(self._policy.stop_timeout_seconds):
                    self._dependencies.service.start(self._policy.startup_timeout_seconds)
                if not self._dependencies.service.is_active(self._policy.startup_timeout_seconds):
                    raise DeploymentFailure("start_failed")
            except (DeploymentFailure, OSError, ValueError, TypeError):
                self._persist_final(record, "manual_intervention", "manual_intervention_required")
                return DeploymentOutcome(False, "manual_intervention_required")
            self._persist_final(record, "failed", "recovered")
            return DeploymentOutcome(False, "recovered")
        try:
            _restore_file(self._layout.backups / snapshot.configuration.filename, self._layout.configuration, _validate_configuration, snapshot.configuration)
            _restore_file(self._layout.backups / snapshot.database.filename, self._layout.database, validate_sqlite_backup, snapshot.database)
            self._dependencies.switcher.restore(snapshot.previous_release)
            _write_sha_marker(self._layout.sha_marker, snapshot.previous_marker_sha)
            if self._dependencies.switcher.current_release_id() != snapshot.previous_release or _read_sha_marker(self._layout.sha_marker) != snapshot.previous_marker_sha:
                raise ValueError
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
    def __init__(self, layout: ServerLayout, runner: CommandRunner): self._layout, self._runner = layout, runner
    def existing_identity(self, sha: str) -> str | None:
        path = self._layout.releases / sha
        if not path.is_dir() or path.is_symlink():
            return None
        return sha if self.verify(ReleaseIdentity(sha, sha, path)) else "conflict"
    def prepare(self, sha: str, timeout_seconds: int) -> ReleaseIdentity:
        path = self._layout.releases / sha
        if path.exists():
            if self.existing_identity(sha) == sha:
                return ReleaseIdentity(sha, sha, path)
            raise DeploymentFailure("release_conflict")
        source = self._layout.source_repository
        _require(
            _fixed(self._runner, "/usr/bin/git", ("-C", _arg_path(source), "rev-parse", "--git-dir"), source, timeout_seconds),
            "release_preparation_failed",
        )
        commit_type = execute_command(
            self._runner,
            executable=Path("/usr/bin/git"),
            argv=("-C", _arg_path(source), "cat-file", "-t", sha),
            environment={"LANG": "C"},
            cwd=source,
            timeout_seconds=timeout_seconds,
            redact=lambda value: value.strip(),
        )
        if commit_type.category != "ok" or commit_type.stdout != "commit":
            raise DeploymentFailure("release_preparation_failed")
        _require(
            _fixed(self._runner, "/usr/bin/git", ("-C", _arg_path(source), "worktree", "add", "--detach", _arg_path(path), sha), source, timeout_seconds),
            "release_preparation_failed",
        )
        release = ReleaseIdentity(sha, sha, path)
        if not self.verify(release):
            raise DeploymentFailure("release_identity_invalid")
        return release
    def verify(self, release: ReleaseIdentity) -> bool:
        result = execute_command(self._runner, executable=Path("/usr/bin/git"), argv=("-C", _arg_path(release.path), "rev-parse", "HEAD"), environment={"LANG": "C"}, cwd=release.path, timeout_seconds=60, redact=lambda value: value.strip())
        return result.category == "ok" and result.stdout == release.sha
    def preflight(self, release: ReleaseIdentity, timeout_seconds: int) -> bool:
        forbidden = (release.path / ".env", release.path / "configuration.json", release.path / "db" / "bot.db", release.path / "logs", release.path / "runtime")
        if any(path.exists() for path in forbidden):
            return False
        environment = {"LANG": "C", "PIPENV_VENV_IN_PROJECT": "1"}
        python = _fixed(self._runner, "/usr/local/bin/pipenv", ("--python", "3.12"), release.path, timeout_seconds, environment)
        sync = _fixed(self._runner, "/usr/local/bin/pipenv", ("sync", "--deploy", "--ignore-pipfile"), release.path, timeout_seconds, environment)
        compile_result = _fixed(self._runner, "/usr/local/bin/pipenv", ("run", "python", "-m", "compileall", "."), release.path, timeout_seconds, environment)
        return python == "ok" and sync == "ok" and compile_result == "ok"
    def cleanup(self, release_id: str) -> None:
        if not SHA_PATTERN.fullmatch(release_id):
            return
        path = self._layout.releases / release_id
        try:
            status = path.lstat()
            if not stat.S_ISDIR(status.st_mode) or stat.S_ISLNK(status.st_mode):
                return
            _fixed(
                self._runner,
                "/usr/bin/git",
                ("-C", _arg_path(self._layout.source_repository), "worktree", "remove", "--force", _arg_path(path)),
                self._layout.source_repository,
                60,
            )
        except OSError:
            return


class _FixedMigrations:
    def __init__(self, runner: CommandRunner): self._runner = runner
    def rehearse(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        return self._run(release, database, timeout_seconds)
    def apply(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        return self._run(release, database, timeout_seconds)
    def validate(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        python = release.path / ".venv" / "bin" / "python"
        return _fixed(self._runner, _arg_path(python), ("-m", "scripts.migrate", "--check", "--database", _arg_path(database), "--migrations", _arg_path(release.path / "db" / "migrations")), release.path, timeout_seconds) == "ok"
    def _run(self, release: ReleaseIdentity, database: Path, timeout_seconds: int) -> bool:
        python = release.path / ".venv" / "bin" / "python"
        return _fixed(self._runner, _arg_path(python), ("-m", "scripts.migrate", "--database", _arg_path(database), "--migrations", _arg_path(release.path / "db" / "migrations")), release.path, timeout_seconds) == "ok"


class _FixedProcesses:
    def __init__(self, layout: ServerLayout, runner: CommandRunner): self._layout, self._runner = layout, runner
    def no_bot_process(self, timeout_seconds: int) -> bool:
        result = execute_command(self._runner, executable=Path("/bin/systemctl"), argv=("show", "fogbot.service", "--property=MainPID", "--value"), environment={"LANG": "C"}, cwd=self._layout.state, timeout_seconds=timeout_seconds, redact=lambda value: value.strip())
        if result.category != "ok" or result.stdout != "0":
            return False
        try:
            found = self._runner.run(
                Path("/usr/bin/pgrep"),
                ("-f", "--", "python.*(fogbot|main\\.py)|fogbot"),
                {"LANG": "C"},
                self._layout.state,
                timeout_seconds,
            )
            return found.exit_code == 1
        except (OSError, ValueError, TypeError):
            return False
    def acquire_instance_lock(self, timeout_seconds: int) -> bool:
        return _fixed(self._runner, "/usr/bin/flock", ("-n", _arg_path(self._layout.instance_lock), "/usr/bin/true"), self._layout.state, timeout_seconds) == "ok"
    def identity(self, timeout_seconds: int) -> ProcessIdentity | None:
        readiness_identity = _readiness_process_identity(self._layout.readiness)
        if readiness_identity is None:
            return None
        result = execute_command(
            self._runner,
            executable=Path("/bin/systemctl"),
            argv=("show", "fogbot.service", "--property=MainPID", "--value"),
            environment={"LANG": "C"},
            cwd=self._layout.state,
            timeout_seconds=timeout_seconds,
            redact=lambda value: value.strip(),
        )
        try:
            main_pid = int(result.stdout)
        except ValueError:
            return None
        if result.category != "ok" or main_pid <= 0 or readiness_identity.pid != main_pid:
            return None
        return readiness_identity


class _FixedHealth:
    def __init__(self, layout: ServerLayout, monotonic: object = time.monotonic, sleeper: object = time.sleep):
        self._layout, self._monotonic, self._sleeper = layout, monotonic, sleeper
    def observe(self, expected_sha: str, policy: HealthPolicy) -> bool:
        startup_deadline = self._monotonic() + policy.startup_timeout_seconds  # type: ignore[operator]
        while True:
            if evaluate_readiness(self._layout.readiness, expected_sha, now=lambda: datetime.now(UTC), policy=policy).ready:
                break
            remaining = startup_deadline - self._monotonic()  # type: ignore[operator]
            if remaining <= 0:
                return False
            self._sleeper(min(1, remaining))  # type: ignore[operator]
        expected_process = _readiness_process_identity(self._layout.readiness)
        if expected_process is None:
            return False
        observation_deadline = self._monotonic() + policy.observation_window_seconds  # type: ignore[operator]
        while True:
            if not evaluate_readiness(self._layout.readiness, expected_sha, now=lambda: datetime.now(UTC), expected_process=expected_process, policy=policy).ready:
                return False
            remaining = observation_deadline - self._monotonic()  # type: ignore[operator]
            if remaining <= 0:
                return True
            self._sleeper(min(1, remaining))  # type: ignore[operator]


def _readiness_process_identity(path: Path) -> ProcessIdentity | None:
    try:
        payload, _ = _read_regular_bytes(path, 16 * 1024)
        value = json.loads(payload.decode("utf-8"))
        return ProcessIdentity(value["pid"], value["generation"], value["boot_id"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


@dataclass(frozen=True, slots=True)
class FixedArgAdapters:
    """Reviewable concrete adapters. They use only Task 2's no-shell runner."""

    layout: ServerLayout
    runner: CommandRunner

    def __post_init__(self) -> None:
        self.layout.validate()

    @property
    def service(self) -> _FixedService: return _FixedService(self.runner, self.layout.releases.parent)
    @property
    def preparer(self) -> _FixedPreparer: return _FixedPreparer(self.layout, self.runner)
    @property
    def migrations(self) -> _FixedMigrations: return _FixedMigrations(self.runner)
    @property
    def processes(self) -> _FixedProcesses: return _FixedProcesses(self.layout, self.runner)
    @property
    def health(self) -> _FixedHealth: return _FixedHealth(self.layout)


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


def _fixed(runner: CommandRunner, executable: str, argv: tuple[str, ...], cwd: Path, timeout: int, environment: dict[str, str] | None = None) -> str:
    return execute_command(runner, executable=Path(executable), argv=argv, environment=environment or {"LANG": "C"}, cwd=cwd, timeout_seconds=timeout).category


def _arg_path(path: Path) -> str:
    return path.as_posix()


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
    payload, _ = _read_regular_bytes(path, 64 * 1024)
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError
    return payload


def _validate_configuration(path: Path) -> BackupIdentity:
    payload = _configuration_bytes(path)
    return BackupIdentity(path.name, sha256(payload).hexdigest())


def _write_private(destination: Path, payload: bytes) -> None:
    original = destination.lstat() if destination.exists() else None
    if original is not None and not stat.S_ISREG(original.st_mode):
        raise OSError
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if original is not None:
                os.chmod(temporary, stat.S_IMODE(original.st_mode))
                if os.name == "posix" and hasattr(os, "fchown"):
                    os.fchown(stream.fileno(), original.st_uid, original.st_gid)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if original is not None and not _same_file(original, destination.lstat()):
            raise OSError
        os.replace(temporary, destination)
        _fsync_parent(destination.parent)
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


def _restore_file(source: Path, destination: Path, validator: object, expected: BackupIdentity) -> None:
    try:
        source_identity = validator(source)  # type: ignore[operator]
        if source_identity.sha256 != expected.sha256:
            raise ValueError
        payload, _ = _read_regular_bytes(source, 128 * 1024 * 1024)
        _write_private(destination, payload)
        restored = validator(destination)  # type: ignore[operator]
        if restored.sha256 != expected.sha256:
            raise ValueError
    except (OSError, ValueError, TransactionError):
        raise DeploymentFailure("backup_failed") from None


def _write_sha_marker(path: Path, sha: str) -> None:
    if not SHA_PATTERN.fullmatch(sha):
        raise DeploymentFailure("switch_failed")
    _write_private(path, f"{sha}\n".encode("ascii"))


def _read_sha_marker(path: Path) -> str:
    try:
        payload, _ = _read_regular_bytes(path, 64)
        value = payload.decode("ascii")
        value = value.rstrip("\r\n")
        if not SHA_PATTERN.fullmatch(value):
            raise ValueError
        return value
    except (OSError, UnicodeDecodeError, ValueError):
        raise DeploymentFailure("switch_failed") from None


def switch_release_and_marker(switcher: ReleaseSwitcher, marker: Path, release: ReleaseIdentity) -> None:
    """Switch a journaled release identity; interruptions are reconciled before any later action."""
    reconcile_release_and_marker(switcher, marker)
    old_release = switcher.current_release_id()
    old_marker = _read_sha_marker(marker)
    journal = _switch_journal_path(marker)
    _write_switch_journal(journal, old_release, old_marker, release.sha)
    try:
        switcher.switch(release)
        _write_sha_marker(marker, release.sha)
        if switcher.current_release_id() != release.sha or _read_sha_marker(marker) != release.sha:
            raise ValueError
    except (DeploymentFailure, OSError, ValueError):
        try:
            switcher.restore(old_release)
            _write_sha_marker(marker, old_marker)
            if switcher.current_release_id() != old_release or _read_sha_marker(marker) != old_marker:
                raise ValueError
            _mark_switch_journal_rolled_back(journal, old_release, old_marker, release.sha)
            _clear_switch_journal(journal)
        except (DeploymentFailure, OSError, ValueError):
            raise DeploymentFailure("manual_intervention_required") from None
        raise DeploymentFailure("switch_failed") from None
    _clear_switch_journal(journal)


def reconcile_release_and_marker(switcher: ReleaseSwitcher, marker: Path) -> None:
    """Complete a durably-intended switch after interruption without guessing an identity."""
    journal = _switch_journal_path(marker)
    if not journal.exists():
        return
    old_release, old_marker, intended_release, state = _read_switch_journal(journal)
    try:
        current_release = switcher.current_release_id()
        current_marker = _read_sha_marker(marker)
        if current_release == intended_release and current_marker == intended_release:
            _clear_switch_journal(journal)
            return
        if state == "rolled_back" and current_release == old_release and current_marker == old_marker:
            _clear_switch_journal(journal)
            return
        if state == "rolled_back":
            raise ValueError
        # A journal is written and fsynced before either public identity changes.
        # Any mixed identity is completed to the sole durable target rather than
        # guessing a prior state after a crash between the two replacements.
        switcher.restore(intended_release)
        _write_sha_marker(marker, intended_release)
        if switcher.current_release_id() != intended_release or _read_sha_marker(marker) != intended_release:
            raise ValueError
        _clear_switch_journal(journal)
    except (DeploymentFailure, OSError, ValueError):
        raise DeploymentFailure("manual_intervention_required") from None


def _switch_journal_path(marker: Path) -> Path:
    return marker.with_name(f".{marker.name}.switch.json")


def _write_switch_journal(path: Path, old_release: str, old_marker: str, intended_release: str, *, state: str = "switching") -> None:
    if (
        not isinstance(old_release, str)
        or not 1 <= len(old_release) <= 128
        or not SHA_PATTERN.fullmatch(old_marker)
        or not SHA_PATTERN.fullmatch(intended_release)
        or state not in {"switching", "rolled_back"}
    ):
        raise DeploymentFailure("switch_failed")
    _write_private(
        path,
        json.dumps(
            {
                "previous_release": old_release,
                "previous_marker_sha": old_marker,
                "intended_release_sha": intended_release,
                "state": state,
            },
            separators=(",", ":"),
        ).encode("ascii"),
    )


def _read_switch_journal(path: Path) -> tuple[str, str, str, str]:
    try:
        payload, _ = _read_regular_bytes(path, 1024)
        value = json.loads(payload.decode("ascii"))
        legacy_fields = {"previous_release", "previous_marker_sha", "intended_release_sha"}
        current_fields = legacy_fields | {"state"}
        keys = set(value) if isinstance(value, dict) else set()
        if not isinstance(value, dict) or (keys != legacy_fields and keys != current_fields):
            raise ValueError
        old_release = value["previous_release"]
        old_marker = value["previous_marker_sha"]
        intended_release = value["intended_release_sha"]
        state = value.get("state", "switching")
        if (
            not isinstance(old_release, str)
            or not 1 <= len(old_release) <= 128
            or not SHA_PATTERN.fullmatch(old_marker)
            or not SHA_PATTERN.fullmatch(intended_release)
            or state not in {"switching", "rolled_back"}
        ):
            raise ValueError
        return old_release, old_marker, intended_release, state
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        raise DeploymentFailure("manual_intervention_required") from None


def _mark_switch_journal_rolled_back(path: Path, old_release: str, old_marker: str, intended_release: str) -> None:
    _write_switch_journal(path, old_release, old_marker, intended_release, state="rolled_back")


def _clear_switch_journal(path: Path) -> None:
    try:
        status = path.lstat()
        if not stat.S_ISREG(status.st_mode):
            raise OSError
        path.unlink()
        _fsync_parent(path.parent)
    except OSError:
        raise DeploymentFailure("manual_intervention_required") from None


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
