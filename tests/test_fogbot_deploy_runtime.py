"""Tests for the production argv entry point and runtime composition."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
import importlib
import json
import os
from pathlib import Path

import pytest


SHA = "0123456789abcdef0123456789abcdef01234567"


def _module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.runtime")
    except ModuleNotFoundError:
        pytest.fail("deployment runtime entry point has not been implemented")


def _config(tmp_path: Path) -> dict[str, object]:
    shared = tmp_path / "shared"
    state = tmp_path / "state"
    return {
        "github": {
            "repository_owner": "Bartolini515",
            "repository_name": "FOGDiscordBot",
            "repository_id": 22,
            "head_repository_id": 22,
            "workflow_id": 71,
            "workflow_path": ".github/workflows/ci.yml",
            "main_branch": "main",
            "minimum_activation_run_id": 1,
            "activation_timestamp": "2026-08-20T00:00:00Z",
            "max_run_age_seconds": 86400,
        },
        "layout": {
            "releases": str(tmp_path / "releases"),
            "source_repository": str(tmp_path / "source"),
            "shared": str(shared),
            "state": str(state),
            "operations": str(state / "operations"),
            "backups": str(state / "backups"),
            "configuration": str(shared / "configuration.json"),
            "database": str(shared / "bot.db"),
            "readiness": str(state / "readiness.json"),
            "instance_lock": str(state / "instance.lock"),
            "sha_marker": str(state / "release.sha"),
            "minimum_free_bytes": 0,
        },
        "policy": {
            "stop_timeout_seconds": 180,
            "startup_timeout_seconds": 60,
            "health_timeout_seconds": 30,
            "health_poll_seconds": 1,
        },
    }


def _write_runtime_config(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)


def test_run_from_argv_preserves_forced_command_contract_without_shell_evaluation():
    runtime = _module()
    observed: list[str | None] = []

    class Handler:
        def handle(self, command):
            observed.append(command)
            return runtime.CommandResponse(0, '{"ok":true}')

    stdout, stderr = StringIO(), StringIO()
    exit_code = runtime.run_from_argv(Handler(), ["submit", SHA, "71", "2", "22", "1.2.11"], stdout=stdout, stderr=stderr)

    assert exit_code == 0
    assert observed == [f"submit {SHA} 71 2 22 1.2.11"]
    assert stdout.getvalue() == '{"ok":true}\n'
    assert stderr.getvalue() == ""


def test_run_from_argv_rejects_noncanonical_argument_shape_before_handler():
    runtime = _module()
    cli = importlib.import_module("deployment.server.fogbot_deploy.cli")
    state = importlib.import_module("deployment.server.fogbot_deploy.state")

    class Handler(cli.ForcedCommandHandler):
        def __init__(self):
            super().__init__(object(), state.OperationStore(Path.cwd() / ".pytest-runtime-operations"), object(), object())

    stdout, stderr = StringIO(), StringIO()
    exit_code = runtime.run_from_argv(Handler(), ["current", "extra"], stdout=stdout, stderr=stderr)

    assert exit_code == 2
    assert json.loads(stdout.getvalue()) == {"code": "invalid_command", "ok": False}
    assert stderr.getvalue() == "invalid_command\n"


def test_main_prefers_explicit_argv_when_ssh_supplies_the_full_remote_command(monkeypatch):
    """Normal sudo-over-SSH calls must not parse SSH_ORIGINAL_COMMAND as the helper grammar."""
    runtime = _module()
    observed: list[str | None] = []

    class Handler:
        def handle(self, command):
            observed.append(command)
            return runtime.CommandResponse(0, '{"ok":true}')

    monkeypatch.setattr(runtime, "build_runtime", lambda _configuration: runtime.Runtime(Handler(), object()))
    monkeypatch.setattr(runtime, "load_runtime_config", lambda _path: object())
    stdout, stderr = StringIO(), StringIO()

    exit_code = runtime.main(
        ["current"],
        environ={"SSH_ORIGINAL_COMMAND": "/usr/bin/sudo -n /usr/local/libexec/fogbot-deploy current"},
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert observed == ["current"]
    assert json.loads(stdout.getvalue()) == {"ok": True}
    assert stderr.getvalue() == ""


def test_load_runtime_config_builds_typed_public_configuration_and_paths(tmp_path):
    runtime = _module()
    path = tmp_path / "runtime.json"
    _write_runtime_config(path, _config(tmp_path))

    settings = runtime.load_runtime_config(path)

    assert settings.github.repository_owner == "Bartolini515"
    assert settings.github.workflow_path == ".github/workflows/ci.yml"
    assert settings.github.activation_timestamp == datetime(2026, 8, 20, tzinfo=UTC)
    assert settings.current == tmp_path / "current"
    assert settings.policy.stop_timeout_seconds == 180


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["layout"].__setitem__("releases", "relative/releases"),
        lambda value: value["github"].__setitem__("workflow_path", "other.yml"),
        lambda value: value["github"].__setitem__("activation_timestamp", "2026-08-20"),
        lambda value: value["policy"].__setitem__("stop_timeout_seconds", 0),
        lambda value: value.__setitem__("unexpected", True),
    ],
)
def test_load_runtime_config_rejects_unsafe_or_ambiguous_configuration(tmp_path, mutate):
    runtime = _module()
    value = _config(tmp_path)
    mutate(value)
    path = tmp_path / "runtime.json"
    _write_runtime_config(path, value)

    with pytest.raises(runtime.RuntimeConfigurationError, match="^runtime_configuration_invalid$"):
        runtime.load_runtime_config(path)


def test_fork_launcher_returns_in_parent_without_running_transaction(tmp_path):
    runtime = _module()
    operation_ids: list[str] = []
    fork_calls: list[str] = []

    class Orchestrator:
        def run(self, operation_id):
            operation_ids.append(operation_id)

    launcher = runtime.ForkTransactionLauncher(
        Orchestrator(),
        fork=lambda: fork_calls.append("fork") or 1234,
    )
    record = type("Record", (), {"operation_id": "a" * 32})()

    launcher.start(record)

    assert fork_calls == ["fork"]
    assert operation_ids == []


def test_install_loader_is_a_python_entrypoint_without_shell_execution():
    loader = Path("deployment/server/install/fogbot-deploy")
    assert loader.is_file()
    content = loader.read_text(encoding="utf-8")
    assert "fogbot_deploy.runtime" in content
    assert "shell=True" not in content
    assert "os.system" not in content
