"""Tests for the offline, injected server deployment transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import importlib
import json
from pathlib import Path, PurePosixPath
import sqlite3

import pytest


SHA = "0123456789abcdef0123456789abcdef01234567"


def _module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.orchestrator")
    except ModuleNotFoundError:
        pytest.fail("deployment orchestrator has not been implemented")


def _record(tmp_path: Path):
    state = importlib.import_module("deployment.server.fogbot_deploy.state")
    verifier = importlib.import_module("deployment.server.fogbot_deploy.verifier")
    now = datetime(2026, 8, 30, 12, tzinfo=UTC)
    verified = verifier.VerifiedRun(repository_id=22, run_id=71, run_attempt=2, sha=SHA, verified_at=now)
    record = state.OperationRecord.authorized(verified, "a" * 32, "1.2.11")
    return record, state.OperationStore(tmp_path / "operations")


def _database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE records (value TEXT)")
    connection.execute("INSERT INTO records VALUES ('fixture only')")
    connection.commit()
    connection.close()


def _layout(tmp_path: Path):
    module = _module()
    shared = tmp_path / "shared"
    state = tmp_path / "state"
    for directory in (tmp_path / "releases", shared, state, state / "operations", state / "backups"):
        directory.mkdir(parents=True, exist_ok=True)
    configuration = shared / "configuration.json"
    if not configuration.exists():
        configuration.write_text(
            json.dumps({"technical_info": {"version": "1.2.10", "last_updated": "2026-08-01"}, "other": [1]}),
            encoding="utf-8",
        )
    database = shared / "bot.db"
    if not database.exists():
        _database(database)
    return module.ServerLayout(
        releases=tmp_path / "releases",
        shared=shared,
        state=state,
        operations=state / "operations",
        backups=state / "backups",
        configuration=configuration,
        database=database,
        readiness=state / "readiness.json",
        sha_marker=state / "release.sha",
    )


@dataclass
class Fakes:
    module: object
    events: list[str]
    failure: str | None = None
    main_sha: str = SHA
    active: bool = True
    process_free: bool = True
    lock_free: bool = True
    ready: bool = True
    migrated: bool = False
    switched: str = "previous-release"

    def dependencies(self):
        module = self.module
        events = self.events
        failure = self.failure

        class Preparer:
            def existing_identity(self, sha):
                events.append(f"existing:{sha}")
                return None

            def prepare(self, sha, timeout_seconds):
                events.append(f"prepare:{sha}")
                if failure == "prepare":
                    raise module.DeploymentFailure("release_preparation_failed")
                return module.ReleaseIdentity(sha=sha, release_id="release-a")

            def verify(self, release):
                events.append("verify-release")
                return release.sha == SHA

            def preflight(self, release, timeout_seconds):
                events.append("preflight-no-network")
                if failure == "preflight":
                    return False
                return True

            def cleanup(self, release_id):
                events.append(f"cleanup:{release_id}")

        class Service:
            def is_active(self, timeout_seconds):
                events.append("service-status")
                return self_outer.active

            def stop(self, timeout_seconds):
                events.append("stop")
                if failure == "stop":
                    raise module.DeploymentFailure("stop_failed")
                self_outer.active = False

            def start(self, timeout_seconds):
                events.append("start")
                if failure == "start":
                    raise module.DeploymentFailure("start_failed")
                self_outer.active = True

        class Processes:
            def no_bot_process(self, timeout_seconds):
                events.append("process-free")
                return self_outer.process_free

            def acquire_instance_lock(self, timeout_seconds):
                events.append("instance-lock")
                return self_outer.lock_free

            def identity(self, timeout_seconds):
                events.append("identity")
                if not self_outer.active:
                    return None
                return module.ProcessIdentity(71, "123e4567-e89b-12d3-a456-426614174000", "boot-a")

        class Migrations:
            def rehearse(self, release, database, timeout_seconds):
                events.append("rehearse")
                return failure != "rehearse"

            def apply(self, release, database, timeout_seconds):
                events.append("apply")
                if failure == "apply":
                    return False
                self_outer.migrated = True
                return True

            def validate(self, database, timeout_seconds):
                events.append("validate-migrations")
                return failure != "migration-validation"

        class Switcher:
            def current_release_id(self):
                events.append("read-current")
                return self_outer.switched

            def switch(self, release):
                events.append(f"switch:{release.sha}")
                if failure == "switch":
                    raise module.DeploymentFailure("switch_failed")
                self_outer.switched = release.release_id

            def restore(self, release_id):
                events.append(f"restore-link:{release_id}")
                self_outer.switched = release_id

        class Verifier:
            def verify(self, request):
                events.append("revalidate")
                if failure == "revalidate":
                    raise module.DeploymentFailure("revalidation_failed")
                return type("Verified", (), {"repository_id": 22, "run_id": 71, "run_attempt": 2, "sha": self_outer.main_sha})()

        class Clock:
            def now(self):
                return datetime(2026, 8, 30, 23, 30, tzinfo=UTC)

        class Health:
            def observe(self, expected_sha, expected_process, policy):
                events.append(f"observe:{expected_sha}")
                return self_outer.ready and failure != "health"

        self_outer = self
        return module.DeploymentDependencies(
            preparer=Preparer(),
            service=Service(),
            processes=Processes(),
            migrations=Migrations(),
            switcher=Switcher(),
            verifier=Verifier(),
            clock=Clock(),
            health=Health(),
        )


def _run(tmp_path: Path, *, failure: str | None = None, **changes):
    module = _module()
    record, store = _record(tmp_path)
    store.create_or_read(record)
    fakes = Fakes(module=module, events=[], failure=failure, **changes)
    orchestrator = module.DeploymentOrchestrator(_layout(tmp_path), store, fakes.dependencies())
    return orchestrator.run(record.operation_id), store, fakes, _layout


def test_successful_transaction_uses_exact_sha_redacts_result_and_updates_only_two_metadata_fields(tmp_path):
    """Catch a deployment that retargets a branch, leaks detail, or changes more metadata than allowed."""
    outcome, store, fakes, make_layout = _run(tmp_path)
    saved = store.read("a" * 32)
    configuration = json.loads(make_layout(tmp_path).configuration.read_text(encoding="utf-8"))

    assert outcome == _module().DeploymentOutcome(True, "completed")
    assert saved.phase == "succeeded"
    assert saved.result == "success"
    assert saved.target["sha"] == SHA
    assert saved.target["target_version"] == "1.2.11"
    assert configuration == {"technical_info": {"version": "1.2.11", "last_updated": "2026-08-31"}, "other": [1]}
    assert fakes.events == [
        f"existing:{SHA}", "service-status", f"prepare:{SHA}", "verify-release", "preflight-no-network", "revalidate",
        "stop", "service-status", "process-free", "instance-lock", "read-current", "rehearse", "apply",
        "validate-migrations", f"switch:{SHA}", "start", "service-status", "identity", f"observe:{SHA}",
    ]
    assert str(make_layout(tmp_path).shared) not in outcome.diagnostic_code


def test_layout_rejects_relative_and_traversal_paths_before_any_preparation(tmp_path):
    """Catch a layout validator that permits paths outside the immutable server root."""
    module = _module()
    layout = _layout(tmp_path)
    unsafe = module.ServerLayout(
        releases=Path("relative/releases"), shared=layout.shared, state=layout.state, operations=layout.operations,
        backups=layout.backups, configuration=layout.configuration, database=layout.database,
        readiness=layout.readiness, sha_marker=layout.sha_marker,
    )
    record, store = _record(tmp_path)
    store.create_or_read(record)
    fakes = Fakes(module=module, events=[])

    outcome = module.DeploymentOrchestrator(unsafe, store, fakes.dependencies()).run(record.operation_id)

    assert outcome == module.DeploymentOutcome(False, "layout_invalid")
    assert fakes.events == []


def test_revalidation_race_aborts_before_stopping_the_service(tmp_path):
    """Catch a stale CI authorization that stops a running bot before checking current main."""
    outcome, store, fakes, _ = _run(tmp_path, failure="revalidate")

    assert outcome == _module().DeploymentOutcome(False, "revalidation_failed")
    assert "stop" not in fakes.events
    assert store.read("a" * 32).phase == "failed"


def test_stop_exclusion_failure_keeps_current_release_and_recovers_before_start(tmp_path):
    """Catch a stop path that switches releases despite a bot process or instance-lock conflict."""
    outcome, store, fakes, _ = _run(tmp_path, process_free=False)

    assert outcome == _module().DeploymentOutcome(False, "recovered")
    assert not any(event.startswith("switch:") for event in fakes.events)
    assert store.read("a" * 32).diagnostic_code == "recovered"


@pytest.mark.parametrize("failure", ["rehearse", "apply", "migration-validation", "switch"])
def test_pre_start_failures_restore_verified_backup_and_classify_recovery(tmp_path, failure):
    """Catch recovery that leaves an offline failed migration/configuration/current link in production."""
    outcome, store, fakes, _ = _run(tmp_path, failure=failure)

    assert outcome == _module().DeploymentOutcome(False, "recovered")
    assert "restore-link:previous-release" in fakes.events
    assert store.read("a" * 32).phase == "failed"
    assert store.read("a" * 32).backup_database_id is not None


@pytest.mark.parametrize("failure", ["start", "health"])
def test_post_start_failures_never_restore_database_or_configuration_automatically(tmp_path, failure):
    """Catch a rollback that overwrites data after the new release could have written it."""
    outcome, store, fakes, _ = _run(tmp_path, failure=failure)

    assert outcome == _module().DeploymentOutcome(False, "manual_intervention_required")
    assert "restore-link:previous-release" not in fakes.events
    assert store.read("a" * 32).phase == "manual_intervention"


def test_lock_contention_returns_only_a_stable_code_without_calling_dependencies(tmp_path):
    """Catch a concurrent transaction that performs any deployment work while another lock is held."""
    module = _module()
    record, store = _record(tmp_path)
    store.create_or_read(record)
    layout = _layout(tmp_path)
    fakes = Fakes(module=module, events=[])
    orchestrator = module.DeploymentOrchestrator(layout, store, fakes.dependencies())

    with module.DeploymentLock(layout.state / "deployment.lock"):
        outcome = orchestrator.run(record.operation_id)

    assert outcome == module.DeploymentOutcome(False, "deployment_in_progress")
    assert fakes.events == []


def test_interruption_leaves_the_last_durable_phase_for_later_status(tmp_path):
    """Catch interruption handling that overwrites durable recovery state with an invented final result."""
    module = _module()
    record, store = _record(tmp_path)
    store.create_or_read(record)
    layout = _layout(tmp_path)
    fakes = Fakes(module=module, events=[])
    dependencies = fakes.dependencies()

    class InterruptingPreparer:
        def existing_identity(self, sha): return None
        def prepare(self, sha, timeout_seconds): raise KeyboardInterrupt
        def verify(self, release): return True
        def preflight(self, release, timeout_seconds): return True
        def cleanup(self, release_id): pass

    dependencies = module.DeploymentDependencies(
        preparer=InterruptingPreparer(), service=dependencies.service, processes=dependencies.processes,
        migrations=dependencies.migrations, switcher=dependencies.switcher, verifier=dependencies.verifier,
        clock=dependencies.clock, health=dependencies.health,
    )
    with pytest.raises(KeyboardInterrupt):
        module.DeploymentOrchestrator(layout, store, dependencies).run(record.operation_id)

    assert store.read(record.operation_id).phase == "preparing"


def test_fixed_argv_adapters_keep_systemctl_git_pipenv_and_migration_calls_shell_free(tmp_path):
    """Catch a concrete adapter that joins deployment arguments into a shell command."""
    module = _module()

    class Runner:
        def __init__(self): self.calls = []
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.calls.append((executable, argv, environment, cwd, timeout_seconds))
            transaction = importlib.import_module("deployment.server.fogbot_deploy.transaction")
            return transaction.RawCommandResult(0, b"", b"")

    runner = Runner()
    adapters = module.FixedArgAdapters(runner, tmp_path)
    adapters.service.stop(9)
    adapters.preparer.prepare(SHA, 9)
    database = PurePosixPath("/var/lib/fogbot/shared/bot.db")
    adapters.migrations.apply(module.ReleaseIdentity(SHA, "release-a"), database, 9)

    assert [call[1] for call in runner.calls] == [
        ("stop", "fogbot.service"),
        ("fetch", "--depth", "1", "origin", SHA),
        ("run", "yoyo", "apply", "--batch", "--database", str(database)),
    ]
    assert all(isinstance(call[1], tuple) for call in runner.calls)


def test_atomic_symlink_switcher_only_targets_verified_release_directories(tmp_path):
    """Catch a current-link swap that accepts a traversal target or exposes a partially written link."""
    module = _module()
    releases = tmp_path / "releases"
    old_sha, new_sha = "a" * 40, "b" * 40
    (releases / old_sha).mkdir(parents=True)
    (releases / new_sha).mkdir()
    current = tmp_path / "current"
    switcher = module.AtomicSymlinkSwitcher(releases, current)
    try:
        current.symlink_to(releases / old_sha, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error.winerror}")
    switcher.switch(module.ReleaseIdentity(new_sha, new_sha))

    assert switcher.current_release_id() == new_sha
    switcher.restore(old_sha)
    assert switcher.current_release_id() == old_sha
    with pytest.raises(module.DeploymentFailure, match="^switch_failed$"):
        switcher.restore("../outside")


def test_static_installation_assets_are_placeholder_only_and_exclude_cd_workflow():
    """Catch static installation material that becomes an executable automatic deployment workflow."""
    root = Path("deployment/server/install")
    files = {path.name for path in root.iterdir() if path.is_file()}

    assert {"fogbot.service.template", "fogbot-deploy.sudoers.template", "fogbot.sysusers.template", "fogbot.tmpfiles.template", "README.md"} <= files
    assert not Path(".github/workflows/cd.yml").exists()
    assert "<FOGBOT_USER>" in (root / "fogbot.service.template").read_text(encoding="utf-8")
    assert "must not be installed verbatim" in (root / "README.md").read_text(encoding="utf-8")
