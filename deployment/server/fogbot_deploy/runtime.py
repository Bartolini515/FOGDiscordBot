"""Production composition root for the root-owned FogBot deployment helper.

The deployment primitives intentionally do not construct processes, read the
production configuration, or contact GitHub on their own.  This module wires
those boundaries together for the installed helper and keeps the only public
interfaces to the strict ``argv`` and SSH forced-command grammars.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, NoReturn, TextIO

from .cli import (
    CommandResponse,
    ForcedCommandHandler,
    run_from_argv,
    run_from_ssh_original_command,
)
from .config import DeploymentConfig
from .metadata import ProductionMetadataReader
from .orchestrator import (
    AtomicSymlinkSwitcher,
    DeploymentDependencies,
    DeploymentOrchestrator,
    FixedArgAdapters,
    ServerLayout,
)
from .protocol import OPERATION_ID_PATTERN
from .state import OperationRecord, OperationStore
from .transaction import HealthPolicy, SubprocessCommandRunner
from .verifier import GitHubRunVerifier


DEFAULT_RUNTIME_CONFIG = Path("/etc/fogbot-deploy/config.json")
MAXIMUM_RUNTIME_CONFIG_BYTES = 64 * 1024
MAXIMUM_RUNTIME_PATH_LENGTH = 4096
MAXIMUM_RUN_AGE_SECONDS = 365 * 24 * 60 * 60


class RuntimeConfigurationError(ValueError):
    """Controlled configuration failure that never carries a file or secret."""

    def __init__(self) -> None:
        super().__init__("runtime_configuration_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeConfiguration:
    """Validated non-secret helper configuration installed outside releases."""

    github: DeploymentConfig
    layout: ServerLayout
    current: Path
    policy: HealthPolicy


@dataclass(frozen=True, slots=True)
class Runtime:
    """Wired command handler and durable transaction runner."""

    handler: ForcedCommandHandler
    orchestrator: DeploymentOrchestrator


class UtcClock:
    """Clock boundary used by the transaction and GitHub verification."""

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class ForkTransactionLauncher:
    """Detach one authorized operation without a shell or an SSH dependency.

    The helper creates the durable operation record before this launcher runs.
    The parent returns the operation identifier immediately; the child creates
    a new session, closes inherited descriptors, and executes the orchestrator
    from the durable record.  Losing the SSH client therefore cannot cancel an
    already-submitted transaction.  On the Linux server the parent exits soon
    after the fork, so the child is reaped by the service manager's init.
    """

    def __init__(
        self,
        orchestrator: DeploymentOrchestrator,
        *,
        fork: Callable[[], int] | None = None,
        setsid: Callable[[], int] | None = None,
        exit_process: Callable[[int], NoReturn] | None = None,
    ) -> None:
        if fork is None:
            fork = getattr(os, "fork", None)
        if fork is None:
            raise RuntimeError("launcher_unavailable")
        self._orchestrator = orchestrator
        self._fork = fork
        self._setsid = setsid or getattr(os, "setsid", _noop_setsid)
        self._exit_process = exit_process or os._exit

    def start(self, record: OperationRecord) -> None:
        """Start an operation in a detached child, returning only in the parent."""
        operation_id = getattr(record, "operation_id", None)
        if not isinstance(operation_id, str) or not OPERATION_ID_PATTERN.fullmatch(operation_id):
            raise RuntimeError("launcher_unavailable")
        child_pid = self._fork()
        if child_pid > 0:
            return
        if child_pid != 0:
            raise RuntimeError("launcher_unavailable")
        self._run_child(operation_id)

    def _run_child(self, operation_id: str) -> NoReturn:
        try:
            self._setsid()
            _detach_child_stdio()
            self._orchestrator.run(operation_id)
        except BaseException:
            # The orchestrator persists a controlled failure for all expected
            # transaction errors.  Never write exception text to an inherited
            # SSH stream if an unexpected child failure occurs.
            pass
        finally:
            self._exit_process(0)
        raise AssertionError("child_exit_returned")


def load_runtime_config(path: Path) -> RuntimeConfiguration:
    """Load and structurally validate the installed, non-secret JSON config."""
    try:
        payload = _read_json(path)
        if set(payload) != {"github", "layout", "policy"}:
            raise RuntimeConfigurationError
        github = _parse_github(payload["github"])
        layout, current = _parse_layout(payload["layout"])
        policy = _parse_policy(payload["policy"])
        return RuntimeConfiguration(github=github, layout=layout, current=current, policy=policy)
    except RuntimeConfigurationError:
        raise
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
        raise RuntimeConfigurationError from error


def build_runtime(configuration: RuntimeConfiguration) -> Runtime:
    """Construct the only production handler from validated fixed boundaries."""
    runner = SubprocessCommandRunner()
    adapters = FixedArgAdapters(configuration.layout, runner)
    verifier = GitHubRunVerifier(configuration.github)
    store = OperationStore(configuration.layout.operations)
    dependencies = DeploymentDependencies(
        preparer=adapters.preparer,
        service=adapters.service,
        processes=adapters.processes,
        migrations=adapters.migrations,
        switcher=AtomicSymlinkSwitcher(configuration.layout.releases, configuration.current),
        verifier=verifier,
        clock=UtcClock(),
        health=adapters.health,
    )
    orchestrator = DeploymentOrchestrator(configuration.layout, store, dependencies, configuration.policy)
    launcher = ForkTransactionLauncher(orchestrator)
    handler = ForcedCommandHandler(
        verifier=verifier,
        store=store,
        launcher=launcher,
        metadata_reader=ProductionMetadataReader(configuration.layout.configuration),
    )
    return Runtime(handler=handler, orchestrator=orchestrator)


def main(
    argv: Sequence[str] | None = None,
    *,
    config_path: Path = DEFAULT_RUNTIME_CONFIG,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the installed helper using argv or the preserved SSH API."""
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    try:
        if os.name == "posix" and os.geteuid() != 0:
            return _emit_error(4, "permission_denied", output, errors)
        runtime = build_runtime(load_runtime_config(config_path))
    except RuntimeConfigurationError:
        return _emit_error(4, "runtime_unavailable", output, errors)
    except (OSError, RuntimeError, ValueError):
        return _emit_error(4, "runtime_unavailable", output, errors)

    environment = os.environ if environ is None else environ
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    # A normal ``ssh host sudo helper current`` invocation carries the full
    # remote command in SSH_ORIGINAL_COMMAND as an incidental environment
    # variable.  Explicit argv therefore has precedence; the environment is
    # used only for a genuine forced-command invocation with no argv.
    if effective_argv:
        return run_from_argv(runtime.handler, effective_argv, stdout=output, stderr=errors)
    if "SSH_ORIGINAL_COMMAND" in environment:
        return run_from_ssh_original_command(runtime.handler, environ=environment, stdout=output, stderr=errors)
    return run_from_argv(runtime.handler, effective_argv, stdout=output, stderr=errors)


def _parse_github(value: object) -> DeploymentConfig:
    mapping = _mapping(value, {
        "repository_owner",
        "repository_name",
        "repository_id",
        "head_repository_id",
        "workflow_id",
        "workflow_path",
        "main_branch",
        "minimum_activation_run_id",
        "activation_timestamp",
        "max_run_age_seconds",
    })
    strings = ("repository_owner", "repository_name", "workflow_path", "main_branch", "activation_timestamp")
    if any(not isinstance(mapping[key], str) or not mapping[key] for key in strings):
        raise RuntimeConfigurationError
    if mapping["main_branch"] != "main":
        raise RuntimeConfigurationError
    if any(not _positive_int(mapping[key]) for key in ("repository_id", "head_repository_id", "workflow_id", "minimum_activation_run_id")):
        raise RuntimeConfigurationError
    max_age = mapping["max_run_age_seconds"]
    if not _positive_int(max_age) or max_age > MAXIMUM_RUN_AGE_SECONDS:
        raise RuntimeConfigurationError
    try:
        activation = datetime.fromisoformat(mapping["activation_timestamp"].replace("Z", "+00:00"))
        if activation.tzinfo is None:
            raise ValueError
        return DeploymentConfig(
            repository_owner=mapping["repository_owner"],
            repository_name=mapping["repository_name"],
            repository_id=mapping["repository_id"],
            head_repository_id=mapping["head_repository_id"],
            workflow_id=mapping["workflow_id"],
            workflow_path=mapping["workflow_path"],
            main_branch=mapping["main_branch"],
            minimum_activation_run_id=mapping["minimum_activation_run_id"],
            activation_timestamp=activation,
            max_run_age=timedelta(seconds=max_age),
        )
    except (TypeError, ValueError) as error:
        raise RuntimeConfigurationError from error


def _parse_layout(value: object) -> tuple[ServerLayout, Path]:
    keys = {
        "releases",
        "source_repository",
        "shared",
        "state",
        "operations",
        "backups",
        "configuration",
        "database",
        "readiness",
        "instance_lock",
        "sha_marker",
        "minimum_free_bytes",
    }
    mapping = _mapping(value, keys)
    path_keys = tuple(key for key in keys if key != "minimum_free_bytes")
    paths: dict[str, Path] = {}
    for key in path_keys:
        raw = mapping[key]
        if not isinstance(raw, str) or not raw or len(raw) > MAXIMUM_RUNTIME_PATH_LENGTH:
            raise RuntimeConfigurationError
        candidate = Path(raw)
        if not candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeConfigurationError
        paths[key] = candidate
    minimum_free = mapping["minimum_free_bytes"]
    if not isinstance(minimum_free, int) or isinstance(minimum_free, bool) or minimum_free < 0:
        raise RuntimeConfigurationError
    layout = ServerLayout(
        releases=paths["releases"],
        source_repository=paths["source_repository"],
        shared=paths["shared"],
        state=paths["state"],
        operations=paths["operations"],
        backups=paths["backups"],
        configuration=paths["configuration"],
        database=paths["database"],
        readiness=paths["readiness"],
        instance_lock=paths["instance_lock"],
        sha_marker=paths["sha_marker"],
        minimum_free_bytes=minimum_free,
    )
    current = layout.releases.parent / "current"
    if current.parent != layout.releases.parent:
        raise RuntimeConfigurationError
    return layout, current


def _parse_policy(value: object) -> HealthPolicy:
    mapping = _mapping(value, {"stop_timeout_seconds", "startup_timeout_seconds", "health_timeout_seconds", "health_poll_seconds"})
    if any(not _bounded_timeout(mapping[key]) for key in mapping):
        raise RuntimeConfigurationError
    try:
        return HealthPolicy(
            startup_timeout_seconds=mapping["startup_timeout_seconds"],
            stop_timeout_seconds=mapping["stop_timeout_seconds"],
            observation_window_seconds=mapping["health_timeout_seconds"],
        )
    except (TypeError, ValueError) as error:
        raise RuntimeConfigurationError from error


def _read_json(path: Path) -> dict[str, Any]:
    if not isinstance(path, Path) or not path.is_absolute() or ".." in path.parts:
        raise RuntimeConfigurationError
    descriptor: int | None = None
    try:
        if os.name == "posix":
            no_follow = getattr(os, "O_NOFOLLOW", None)
            close_on_exec = getattr(os, "O_CLOEXEC", None)
            if no_follow is None or close_on_exec is None:
                raise RuntimeConfigurationError
            descriptor = os.open(path, os.O_RDONLY | no_follow | close_on_exec)
            status = os.fstat(descriptor)
            if (
                not stat.S_ISREG(status.st_mode)
                or status.st_size > MAXIMUM_RUNTIME_CONFIG_BYTES
                # The helper runs as root in production; comparing against the
                # effective UID keeps this loader testable under an unprivileged
                # account while still refusing a config owned by another user.
                or status.st_uid != os.geteuid()
                or stat.S_IMODE(status.st_mode) & 0o077
            ):
                raise RuntimeConfigurationError
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                descriptor = None
                encoded = stream.read(MAXIMUM_RUNTIME_CONFIG_BYTES + 1)
        else:
            initial = path.lstat()
            if not stat.S_ISREG(initial.st_mode):
                raise RuntimeConfigurationError
            descriptor = os.open(path, os.O_RDONLY)
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or not _same_file(initial, status):
                raise RuntimeConfigurationError
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                descriptor = None
                encoded = stream.read(MAXIMUM_RUNTIME_CONFIG_BYTES + 1)
        if len(encoded) > MAXIMUM_RUNTIME_CONFIG_BYTES:
            raise RuntimeConfigurationError
        value = json.loads(encoded.decode("utf-8"))
        if not isinstance(value, dict):
            raise RuntimeConfigurationError
        return value
    except RuntimeConfigurationError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeConfigurationError from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _detach_child_stdio() -> None:
    """Detach inherited SSH descriptors while keeping the child silent."""
    descriptor = os.open(os.devnull, os.O_RDWR)
    try:
        for target in (0, 1, 2):
            os.dup2(descriptor, target)
    finally:
        if descriptor > 2:
            os.close(descriptor)
        try:
            os.closerange(3, 1024)
        except OSError:
            pass


def _noop_setsid() -> int:
    """Portable test/development fallback; production Linux has ``os.setsid``."""
    return 0


def _emit_error(code: str | int, diagnostic: str | TextIO, stdout: TextIO, stderr: TextIO) -> int:
    # This helper is intentionally tiny and accepts only the fixed internal
    # call shape; it keeps startup failures redacted just like cli responses.
    exit_code = int(code)
    message = str(diagnostic)
    response = CommandResponse(exit_code, json.dumps({"code": message, "ok": False}, separators=(",", ":"), sort_keys=True), message)
    print(response.stdout, file=stdout, flush=True)
    if response.stderr:
        print(response.stderr, file=stderr, flush=True)
    return response.exit_code


def _mapping(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise RuntimeConfigurationError
    return value


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _bounded_timeout(value: object) -> bool:
    return type(value) is int and 1 <= value <= 3600


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino
