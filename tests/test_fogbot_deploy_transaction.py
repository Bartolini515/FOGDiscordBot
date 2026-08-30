"""Tests for side-effect-free deployment transaction primitives."""

import importlib
import json
from pathlib import Path
import sqlite3
from datetime import UTC, datetime

import pytest


def _transaction_module():
    try:
        return importlib.import_module("deployment.server.fogbot_deploy.transaction")
    except ModuleNotFoundError:
        pytest.fail("deployment transaction primitives have not been implemented")


def test_transaction_lock_rejects_contention_and_releases_after_context_exit(tmp_path):
    """Catch a lock regression that permits overlapping deployment transactions."""
    transaction = _transaction_module()
    lock_path = tmp_path / "transaction.lock"

    with transaction.DeploymentLock(lock_path):
        with pytest.raises(transaction.TransactionError, match="^deployment_in_progress$"):
            transaction.DeploymentLock(lock_path).acquire()

    with transaction.DeploymentLock(lock_path):
        pass


def test_fixed_argument_runner_retains_immutable_argv_without_shell_interpolation(tmp_path):
    """Catch a command-boundary regression that turns argv into an interpolated shell string."""
    transaction = _transaction_module()

    class RecordingRunner:
        def __init__(self):
            self.calls = []

        def run(self, executable, argv, environment, cwd, timeout_seconds):
            self.calls.append((executable, argv, environment, cwd, timeout_seconds))
            return transaction.RawCommandResult(exit_code=0, stdout=b"visible", stderr=b"")

    runner = RecordingRunner()
    result = transaction.execute_command(
        runner,
        executable=Path("/opt/fogbot/bin/migrate"),
        argv=("--version", "1.2.3"),
        environment={"LANG": "C"},
        cwd=tmp_path,
        timeout_seconds=5,
        redact=lambda value: f"redacted:{value}",
    )

    assert result.category == "ok"
    assert result.stdout == "redacted:visible"
    assert result.stderr == "redacted:"
    assert runner.calls == [(Path("/opt/fogbot/bin/migrate"), ("--version", "1.2.3"), {"LANG": "C"}, tmp_path, 5)]
    with pytest.raises(transaction.TransactionError, match="^invalid_command$"):
        transaction.execute_command(
            runner,
            executable=Path("/opt/fogbot/bin/migrate"),
            argv=("--version", "1.2.3; id"),
            environment={},
            cwd=tmp_path,
            timeout_seconds=5,
        )


def test_fixed_argument_runner_returns_a_stable_timeout_without_output(tmp_path):
    """Catch a timeout regression that leaks command output or raw exception details."""
    transaction = _transaction_module()

    class TimingOutRunner:
        def run(self, executable, argv, environment, cwd, timeout_seconds):
            raise TimeoutError("untrusted command output")

    result = transaction.execute_command(
        TimingOutRunner(),
        executable=Path("/opt/fogbot/bin/migrate"),
        argv=("--check",),
        environment={},
        cwd=tmp_path,
        timeout_seconds=5,
    )

    assert result.category == "command_timeout"
    assert result.stdout == ""
    assert result.stderr == ""


def test_subprocess_runner_uses_a_list_and_explicitly_disables_shell(tmp_path, monkeypatch):
    """Catch a subprocess implementation that reintroduces shell evaluation."""
    transaction = _transaction_module()
    observed = {}

    class Completed:
        returncode = 0
        stdout = b""
        stderr = b""

    def record_run(arguments, **kwargs):
        observed["arguments"] = arguments
        observed.update(kwargs)
        return Completed()

    monkeypatch.setattr(transaction.subprocess, "run", record_run)
    transaction.SubprocessCommandRunner().run(Path("/opt/fogbot/bin/check"), ("--fixed",), {}, tmp_path, 7)

    assert observed["arguments"] == [str(Path("/opt/fogbot/bin/check")), "--fixed"]
    assert observed["shell"] is False


def test_readiness_evaluator_rejects_stale_or_extra_schema_fields(tmp_path):
    """Catch a health boundary that accepts stale records or arbitrary diagnostic content."""
    transaction = _transaction_module()
    path = tmp_path / "ready.json"
    payload = {
        "schema_version": 1,
        "release_sha": "a" * 40,
        "pid": 1,
        "generation": "123e4567-e89b-12d3-a456-426614174000",
        "boot_id": "boot",
        "ready_at": "2026-08-30T10:00:00Z",
        "heartbeat_at": "2026-08-30T10:00:00Z",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    def now():
        return datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    assert transaction.evaluate_readiness(path, "a" * 40, now=now).diagnostic_code == "readiness_stale"
    payload["untrusted_log"] = "secret"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert transaction.evaluate_readiness(path, "a" * 40, now=now).diagnostic_code == "readiness_schema_invalid"


def test_metadata_update_changes_only_two_validated_fields_and_preserves_original_on_failure(tmp_path):
    """Catch a metadata update that alters unrelated configuration or overwrites it before validation."""
    transaction = _transaction_module()
    path = tmp_path / "configuration.json"
    original = {"technical_info": {"version": "1.0.0", "last_updated": "2026-01-01", "name": "Fog"}, "nested": {"x": [1, 2]}}
    path.write_text(json.dumps(original), encoding="utf-8")

    transaction.update_configuration_metadata(path, version="1.2.3", last_updated="2026-08-30")

    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated == {"technical_info": {"version": "1.2.3", "last_updated": "2026-08-30", "name": "Fog"}, "nested": {"x": [1, 2]}}
    retained = path.read_bytes()
    with pytest.raises(transaction.TransactionError, match="^invalid_metadata$"):
        transaction.update_configuration_metadata(path, version="01.2.3", last_updated="2026-02-30")
    assert path.read_bytes() == retained


def test_metadata_update_rejects_unsafe_or_oversized_input_without_replacing_it(tmp_path):
    """Catch a metadata path regression that follows links or accepts unbounded configuration input."""
    transaction = _transaction_module()
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (transaction.MAXIMUM_CONFIGURATION_BYTES + 1))
    with pytest.raises(transaction.TransactionError, match="^metadata_unavailable$"):
        transaction.update_configuration_metadata(oversized, version="1.2.3", last_updated="2026-08-30")

    target = tmp_path / "target.json"
    target.write_text(json.dumps({"technical_info": {"version": "1.0.0", "last_updated": "2026-01-01"}}), encoding="utf-8")
    link = tmp_path / "configuration-link.json"
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error.winerror}")
    with pytest.raises(transaction.TransactionError, match="^metadata_unavailable$"):
        transaction.update_configuration_metadata(link, version="1.2.3", last_updated="2026-08-30")
    assert json.loads(target.read_text(encoding="utf-8"))["technical_info"]["version"] == "1.0.0"


def test_sqlite_backup_uses_online_backup_for_wal_and_returns_only_stable_identity(tmp_path):
    """Catch a backup regression that copies a WAL database unsafely or exposes its rows."""
    transaction = _transaction_module()
    source = tmp_path / "active.db"
    connection = sqlite3.connect(source)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE records (value TEXT)")
    connection.execute("INSERT INTO records VALUES ('sensitive row')")
    connection.commit()
    before = source.read_bytes()

    identity = transaction.backup_sqlite_database(source, tmp_path / "backup.db")

    assert identity.filename == "backup.db"
    assert len(identity.sha256) == 64
    assert "sensitive" not in repr(identity)
    assert transaction.validate_sqlite_backup(tmp_path / "backup.db") == identity
    assert source.read_bytes() == before
    connection.close()


def test_readiness_evaluator_checks_schema_identity_sha_and_freshness_without_diagnostics(tmp_path):
    """Catch health validation that accepts a stale, foreign, or malformed readiness record."""
    transaction = _transaction_module()
    readiness_path = tmp_path / "ready.json"
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    record = {
        "schema_version": 1,
        "release_sha": "a" * 40,
        "pid": 71,
        "generation": "123e4567-e89b-12d3-a456-426614174000",
        "boot_id": "boot-a",
        "ready_at": "2026-08-30T11:59:00Z",
        "heartbeat_at": "2026-08-30T11:59:50Z",
    }
    readiness_path.write_text(json.dumps(record), encoding="utf-8")
    identity = transaction.ProcessIdentity(71, record["generation"], "boot-a")

    ready = transaction.evaluate_readiness(readiness_path, "a" * 40, now=lambda: now, expected_process=identity)
    stale = transaction.evaluate_readiness(readiness_path, "b" * 40, now=lambda: now, expected_process=identity)

    assert ready == transaction.HealthResult(True, "ready")
    assert stale == transaction.HealthResult(False, "release_mismatch")
    assert "ready.json" not in stale.diagnostic_code


@pytest.mark.parametrize(
    ("boundary", "verified", "action"),
    [
        ("before_stop", True, "restore_pre_start_state"),
        ("after_stop_pre_start", True, "restore_pre_start_state"),
        ("after_migration_before_new_process", True, "restore_pre_start_state"),
        ("after_new_process_start", True, "manual_intervention"),
        ("post_health", True, "manual_intervention"),
        ("after_stop_pre_start", False, "manual_intervention"),
    ],
)
def test_recovery_classification_is_deterministic_at_each_boundary(boundary, verified, action):
    """Catch recovery policy that restores state after a new process or claims an unverified restore."""
    transaction = _transaction_module()

    decision = transaction.classify_recovery(transaction.TransactionBoundary(boundary), pre_state_verified=verified)

    assert decision.action == action
