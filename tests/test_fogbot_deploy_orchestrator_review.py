"""Regression tests for the Task 3 independent-review blockers."""

from __future__ import annotations

from datetime import UTC, datetime
import importlib
import json
from pathlib import Path
import sqlite3

import pytest


SHA = "0123456789abcdef0123456789abcdef01234567"


def _module():
    return importlib.import_module("deployment.server.fogbot_deploy.orchestrator")


def _layout(tmp_path: Path):
    module = _module()
    releases, shared, state = tmp_path / "releases", tmp_path / "shared", tmp_path / "state"
    for directory in (releases, shared, state, state / "operations", state / "backups"):
        directory.mkdir(parents=True, exist_ok=True)
    configuration, database = shared / "configuration.json", shared / "bot.db"
    configuration.write_text(json.dumps({"technical_info": {"version": "1.0.0", "last_updated": "2026-01-01"}}), encoding="utf-8")
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE checked (value TEXT)")
    connection.commit()
    connection.close()
    return module.ServerLayout(
        releases=releases,
        shared=shared,
        state=state,
        operations=state / "operations",
        backups=state / "backups",
        configuration=configuration,
        database=database,
        readiness=state / "readiness.json",
        sha_marker=state / "release.sha",
        minimum_free_bytes=0,
    )


def test_release_identity_is_exact_sha_and_absolute_child_of_release_root(tmp_path):
    """Catch a release identity that can point the current link at any arbitrary directory."""
    module = _module()
    layout = _layout(tmp_path)
    release = layout.releases / SHA
    release.mkdir()

    identity = module.ReleaseIdentity(sha=SHA, release_id=SHA, path=release)

    assert identity.path == release.resolve()
    with pytest.raises(module.DeploymentFailure, match="^release_identity_invalid$"):
        module.ReleaseIdentity(sha=SHA, release_id="not-the-sha", path=release)


def test_fixed_adapters_prepare_a_release_local_python_312_environment_and_exact_migrations(tmp_path):
    """Catch fixed adapters that operate on a generic checkout rather than releases/<sha>."""
    module = _module()
    layout = _layout(tmp_path)

    class Runner:
        def __init__(self): self.calls = []
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.calls.append((executable, argv, dict(environment), cwd, timeout_seconds))
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            return transaction.RawCommandResult(0, SHA.encode(), b"")

    runner = Runner()
    adapters = module.FixedArgAdapters(layout, runner)
    release = adapters.preparer.prepare(SHA, 30)
    assert release == module.ReleaseIdentity(SHA, SHA, layout.releases / SHA)
    assert adapters.preparer.verify(release) is True
    assert adapters.preparer.preflight(release, 30) is True
    assert adapters.migrations.apply(release, layout.database, 30) is True
    assert adapters.migrations.validate(release, layout.database, 30) is True

    commands = [call[1] for call in runner.calls]
    assert ("worktree", "add", "--detach", release.path.as_posix(), SHA) in commands
    assert ("-C", release.path.as_posix(), "rev-parse", "HEAD") in commands
    assert ("--python", "3.12") in commands
    assert any(call[2].get("PIPENV_VENV_IN_PROJECT") == "1" and call[3] == release.path for call in runner.calls)
    assert (
        "-m", "scripts.migrate", "--database", layout.database.as_posix(), "--migrations", (release.path / "db" / "migrations").as_posix()
    ) in commands
    assert (
        "-m", "scripts.migrate", "--check", "--database", layout.database.as_posix(), "--migrations", (release.path / "db" / "migrations").as_posix()
    ) in commands


def test_atomic_switch_restores_link_and_marker_when_marker_update_fails(tmp_path, monkeypatch):
    """Catch a half-switched current/marker pair that could make readiness target the wrong release."""
    module = _module()
    layout = _layout(tmp_path)
    old_sha, new_sha = "a" * 40, "b" * 40
    for value in (old_sha, new_sha):
        (layout.releases / value).mkdir()
    current = tmp_path / "current"
    try:
        current.symlink_to(layout.releases / old_sha, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error.winerror}")
    layout.sha_marker.write_text(f"{old_sha}\n", encoding="ascii")
    switcher = module.AtomicSymlinkSwitcher(layout.releases, current)

    monkeypatch.setattr(module, "_write_sha_marker", lambda *_: (_ for _ in ()).throw(module.DeploymentFailure("switch_failed")))
    with pytest.raises(module.DeploymentFailure, match="^switch_failed$"):
        module.switch_release_and_marker(switcher, layout.sha_marker, module.ReleaseIdentity(new_sha, new_sha, layout.releases / new_sha))

    assert switcher.current_release_id() == old_sha
    assert layout.sha_marker.read_text(encoding="ascii") == f"{old_sha}\n"


def test_operation_record_persists_redacted_success_date_and_release_identity():
    """Catch a succeeded record that cannot report its exact deployment version/date/release."""
    state = importlib.import_module("deployment.server.fogbot_deploy.state")
    verifier = importlib.import_module("deployment.server.fogbot_deploy.verifier")
    verified = verifier.VerifiedRun(22, 71, 2, SHA, datetime(2026, 8, 30, tzinfo=UTC))
    record = state.OperationRecord.authorized(verified, "a" * 32, "1.2.11")

    completed = record.with_phase("succeeded", "completed", result="success", deployment_date="2026-08-31", deployed_release_id=SHA)

    assert completed.as_dict()["deployment_date"] == "2026-08-31"
    assert completed.as_dict()["deployed_release_id"] == SHA


def test_layout_binds_store_before_lock_creation(tmp_path):
    """Catch an orchestrator that writes a lock under an unvalidated state parent or foreign operation store."""
    module = _module()
    state = importlib.import_module("deployment.server.fogbot_deploy.state")
    layout = _layout(tmp_path)
    foreign = state.OperationStore(tmp_path / "foreign-operations")

    with pytest.raises(module.DeploymentFailure, match="^layout_invalid$"):
        module.DeploymentOrchestrator(layout, foreign, object())
    assert not (layout.state / "deployment.lock").exists()


def test_restore_preserves_target_mode_and_rejects_digest_mismatch(tmp_path):
    """Catch a restore that changes service access bits or accepts a substituted backup file."""
    module = _module()
    source, target = tmp_path / "backup.json", tmp_path / "configuration.json"
    source.write_text(json.dumps({"technical_info": {"version": "1.0.0", "last_updated": "2026-01-01"}}), encoding="utf-8")
    target.write_text(json.dumps({"technical_info": {"version": "1.2.0", "last_updated": "2026-02-01"}}), encoding="utf-8")
    target.chmod(0o640)
    identity = module._validate_configuration(source)

    module._restore_file(source, target, module._validate_configuration, identity)

    assert module._validate_configuration(target).sha256 == identity.sha256
    if __import__("os").name == "posix":
        assert target.stat().st_mode & 0o777 == 0o640
    with pytest.raises(module.DeploymentFailure, match="^backup_failed$"):
        module._restore_file(source, target, module._validate_configuration, module.BackupIdentity("wrong", "0" * 64))
