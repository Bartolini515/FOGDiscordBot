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
    releases, shared, state, source_repository = tmp_path / "releases", tmp_path / "shared", tmp_path / "state", tmp_path / "source.git"
    for directory in (releases, shared, state, state / "operations", state / "backups", source_repository):
        directory.mkdir(parents=True, exist_ok=True)
    configuration, database = shared / "configuration.json", shared / "bot.db"
    configuration.write_text(json.dumps({"technical_info": {"version": "1.0.0", "last_updated": "2026-01-01"}}), encoding="utf-8")
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE checked (value TEXT)")
    connection.commit()
    connection.close()
    return module.ServerLayout(
        releases=releases,
        source_repository=source_repository,
        shared=shared,
        state=state,
        operations=state / "operations",
        backups=state / "backups",
        configuration=configuration,
        database=database,
        readiness=state / "readiness.json",
        instance_lock=state / "instance.lock",
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
            if argv[-2:] == ("-t", SHA):
                return transaction.RawCommandResult(0, b"commit\n", b"")
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
    assert ("-C", layout.source_repository.as_posix(), "cat-file", "-t", SHA) in commands
    assert ("-C", layout.source_repository.as_posix(), "worktree", "add", "--detach", release.path.as_posix(), SHA) in commands
    assert ("-C", release.path.as_posix(), "rev-parse", "HEAD") in commands
    assert ("--python", "3.12") in commands
    assert any(call[2].get("PIPENV_VENV_IN_PROJECT") == "1" and call[3] == release.path for call in runner.calls)
    assert (
        "-m", "scripts.migrate", "--database", layout.database.as_posix(), "--migrations", (release.path / "db" / "migrations").as_posix()
    ) in commands
    assert (
        "-m", "scripts.migrate", "--check", "--database", layout.database.as_posix(), "--migrations", (release.path / "db" / "migrations").as_posix()
    ) in commands


def test_fixed_preparer_rejects_missing_source_repository_before_creating_release(tmp_path):
    """Catch a worktree command that silently treats the releases parent as a Git source."""
    module = _module()
    layout = _layout(tmp_path)
    missing = module.ServerLayout(
        releases=layout.releases,
        source_repository=tmp_path / "missing-source.git",
        shared=layout.shared,
        state=layout.state,
        operations=layout.operations,
        backups=layout.backups,
        configuration=layout.configuration,
        database=layout.database,
        readiness=layout.readiness,
        instance_lock=layout.instance_lock,
        sha_marker=layout.sha_marker,
        minimum_free_bytes=0,
    )

    with pytest.raises(module.DeploymentFailure, match="^layout_invalid$"):
        module.FixedArgAdapters(missing, object())
    assert not (layout.releases / SHA).exists()


def test_fixed_preparer_rejects_a_non_git_source_before_creating_release(tmp_path):
    """Catch a source-directory check that creates a release even though it is not a usable Git repository."""
    module = _module()
    layout = _layout(tmp_path)

    class Runner:
        def __init__(self): self.calls = []
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.calls.append(argv)
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            return transaction.RawCommandResult(1, b"", b"")

    runner = Runner()
    with pytest.raises(module.DeploymentFailure, match="^release_preparation_failed$"):
        module.FixedArgAdapters(layout, runner).preparer.prepare(SHA, 30)

    assert runner.calls == [("-C", layout.source_repository.as_posix(), "rev-parse", "--git-dir")]
    assert not (layout.releases / SHA).exists()


def test_health_waits_for_readiness_then_requires_a_continuous_observation_window(tmp_path, monkeypatch):
    """Catch startup polling that rejects an otherwise healthy process before its readiness file exists."""
    module = _module()
    layout = _layout(tmp_path)
    elapsed = [0.0]
    observations = iter((False, False, True, True, True, True))
    monkeypatch.setattr(module, "evaluate_readiness", lambda *args, **kwargs: type("Ready", (), {"ready": next(observations)})())
    monkeypatch.setattr(module, "_readiness_process_identity", lambda _: module.ProcessIdentity(7, "123e4567-e89b-12d3-a456-426614174000", "boot"))
    health = module._FixedHealth(layout, monotonic=lambda: elapsed[0], sleeper=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    policy = module.HealthPolicy(startup_timeout_seconds=2, stop_timeout_seconds=1, observation_window_seconds=2)

    assert health.observe(SHA, policy) is True


def test_fixed_process_probe_rejects_orphan_fogbot_when_systemd_main_pid_is_zero(tmp_path):
    """Catch an exclusion probe that mistakes an empty systemd MainPID for absence of manual bot processes."""
    module = _module()
    layout = _layout(tmp_path)

    class Runner:
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            if executable.as_posix() == "/bin/systemctl":
                return transaction.RawCommandResult(0, b"0\n", b"")
            return transaction.RawCommandResult(0, b"31415\n", b"")

    assert module.FixedArgAdapters(layout, Runner()).processes.no_bot_process(10) is False


def test_instance_lock_probe_uses_the_layout_bound_runtime_lock_path(tmp_path):
    """Catch a deploy probe that acquires a hard-coded lock instead of the bot runtime's configured lock."""
    module = _module()
    layout = _layout(tmp_path)
    custom_lock = layout.state / "runtime" / "fogbot.lock"
    custom_lock.parent.mkdir()
    layout = module.ServerLayout(
        releases=layout.releases,
        source_repository=layout.source_repository,
        shared=layout.shared,
        state=layout.state,
        operations=layout.operations,
        backups=layout.backups,
        configuration=layout.configuration,
        database=layout.database,
        readiness=layout.readiness,
        instance_lock=custom_lock,
        sha_marker=layout.sha_marker,
        minimum_free_bytes=0,
    )

    class Runner:
        def __init__(self): self.argv = None
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.argv = argv
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            return transaction.RawCommandResult(0, b"", b"")

    runner = Runner()
    assert module.FixedArgAdapters(layout, runner).processes.acquire_instance_lock(10) is True
    assert runner.argv == ("-n", custom_lock.as_posix(), "/usr/bin/true")


def test_fixed_process_identity_rejects_readiness_pid_that_differs_from_systemd_main_pid(tmp_path):
    """Catch a readiness record accepted for a process other than the one systemd actually started."""
    module = _module()
    layout = _layout(tmp_path)
    layout.readiness.write_text(
        json.dumps({"pid": 7, "generation": "123e4567-e89b-12d3-a456-426614174000", "boot_id": "boot"}), encoding="utf-8"
    )

    class Runner:
        def __init__(self): self.calls = []
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.calls.append((executable, argv))
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            return transaction.RawCommandResult(0, b"99\n", b"")

    runner = Runner()
    assert module.FixedArgAdapters(layout, runner).processes.identity(10) is None
    assert runner.calls == [(Path("/bin/systemctl"), ("show", "fogbot.service", "--property=MainPID", "--value"))]


def test_switch_journal_recovers_marker_after_interruption_between_link_and_marker_writes(tmp_path, monkeypatch):
    """Catch a crash window that permanently leaves current at the new release but the marker at the old SHA."""
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
    original = module._write_sha_marker
    monkeypatch.setattr(module, "_write_sha_marker", lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        module.switch_release_and_marker(switcher, layout.sha_marker, module.ReleaseIdentity(new_sha, new_sha, layout.releases / new_sha))

    monkeypatch.setattr(module, "_write_sha_marker", original)
    module.reconcile_release_and_marker(switcher, layout.sha_marker)
    assert switcher.current_release_id() == new_sha
    assert layout.sha_marker.read_text(encoding="ascii") == f"{new_sha}\n"


def test_switch_journal_completes_intended_release_after_crash_before_symlink_replacement(tmp_path):
    """Catch a journaled post-migration switch that starts the old release after crashing before current is replaced."""
    module = _module()
    layout = _layout(tmp_path)
    old_sha, new_sha = "a" * 40, "b" * 40
    layout.sha_marker.write_text(f"{old_sha}\n", encoding="ascii")

    class Switcher:
        def __init__(self): self.current = old_sha
        def current_release_id(self): return self.current
        def switch(self, release): self.current = release.release_id
        def restore(self, release_id): self.current = release_id

    switcher = Switcher()
    module._write_switch_journal(module._switch_journal_path(layout.sha_marker), old_sha, old_sha, new_sha)

    module.reconcile_release_and_marker(switcher, layout.sha_marker)

    assert switcher.current == new_sha
    assert layout.sha_marker.read_text(encoding="ascii") == f"{new_sha}\n"
    assert not module._switch_journal_path(layout.sha_marker).exists()


def test_successful_switch_rollback_marks_then_clears_its_journal(tmp_path, monkeypatch):
    """Catch a completed rollback that leaves an in-flight journal able to reapply the new release later."""
    module = _module()
    layout = _layout(tmp_path)
    old_sha, new_sha = "a" * 40, "b" * 40
    layout.sha_marker.write_text(f"{old_sha}\n", encoding="ascii")

    class Switcher:
        def __init__(self): self.current = old_sha
        def current_release_id(self): return self.current
        def switch(self, release): self.current = release.release_id
        def restore(self, release_id): self.current = release_id

    switcher = Switcher()
    original = module._write_sha_marker
    monkeypatch.setattr(
        module,
        "_write_sha_marker",
        lambda path, sha: (_ for _ in ()).throw(module.DeploymentFailure("switch_failed")) if sha == new_sha else original(path, sha),
    )
    with pytest.raises(module.DeploymentFailure, match="^switch_failed$"):
        module.switch_release_and_marker(switcher, layout.sha_marker, module.ReleaseIdentity(new_sha, new_sha, layout.releases / new_sha))

    assert switcher.current == old_sha
    assert layout.sha_marker.read_text(encoding="ascii") == f"{old_sha}\n"
    assert not module._switch_journal_path(layout.sha_marker).exists()


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


def test_operation_record_reads_legacy_configuration_backup_key_but_writes_only_canonical_key():
    """Catch a field rename that makes an interrupted deployment record from the preceding accepted commit unreadable."""
    state = importlib.import_module("deployment.server.fogbot_deploy.state")
    verifier = importlib.import_module("deployment.server.fogbot_deploy.verifier")
    verified = verifier.VerifiedRun(22, 71, 2, SHA, datetime(2026, 8, 30, tzinfo=UTC))
    record = state.OperationRecord.authorized(verified, "a" * 32, "1.2.11")
    canonical = record.with_phase("backed_up", "pending", backup_configuration_id="operation.configuration.json").as_dict()
    legacy = dict(canonical)
    legacy["backup_release_id"] = legacy.pop("backup_configuration_id")

    restored = state.OperationRecord.from_dict(legacy)

    assert restored.backup_configuration_id == "operation.configuration.json"
    assert "backup_release_id" not in restored.as_dict()
    ambiguous = dict(canonical)
    ambiguous["backup_release_id"] = "different.json"
    with pytest.raises(state.StateError, match="^state_invalid$"):
        state.OperationRecord.from_dict(ambiguous)


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
