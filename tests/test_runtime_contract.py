"""Executable deployment-runtime contract tests using only local resources."""

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.runtime import InstanceLock, InstanceLockError, ReadinessRecord, RuntimePathError, RuntimePaths, save_runtime_configuration


def test_runtime_paths_resolve_literal_defaults_from_an_injected_local_base(tmp_path: Path):
    """Catch a production regression that returns relative or cwd-dependent default paths."""

    paths = RuntimePaths.from_environment({}, development_base=tmp_path)

    assert paths.config_path == (tmp_path / "configuration.json").resolve()
    assert paths.database_path == (tmp_path / "db" / "bot.db").resolve()
    assert paths.log_dir == (tmp_path / "logs").resolve()
    assert paths.runtime_dir == (tmp_path / ".runtime").resolve()
    assert paths.release_file == (tmp_path / "RELEASE_SHA").resolve()
    assert paths.instance_lock == (tmp_path / ".runtime" / "instance.lock").resolve()


def test_runtime_paths_resolve_each_configured_literal_path(tmp_path: Path):
    """Catch a production regression that ignores one configured FOFBOT runtime path."""

    paths = RuntimePaths.from_environment(
        {
            "FOGBOT_CONFIG_PATH": "state/config.json",
            "FOGBOT_DB_PATH": "state/data.sqlite3",
            "FOGBOT_LOG_DIR": "state/logs",
            "FOGBOT_RUNTIME_DIR": "state/runtime",
            "FOGBOT_RELEASE_FILE": "state/RELEASE_SHA",
            "FOGBOT_INSTANCE_LOCK": "state/lock/fogbot.lock",
        },
        development_base=tmp_path,
    )

    assert paths.config_path == (tmp_path / "state" / "config.json").resolve()
    assert paths.database_path == (tmp_path / "state" / "data.sqlite3").resolve()
    assert paths.log_dir == (tmp_path / "state" / "logs").resolve()
    assert paths.runtime_dir == (tmp_path / "state" / "runtime").resolve()
    assert paths.release_file == (tmp_path / "state" / "RELEASE_SHA").resolve()
    assert paths.instance_lock == (tmp_path / "state" / "lock" / "fogbot.lock").resolve()


def test_runtime_paths_reject_relative_production_overrides():
    """Catch a deployment regression that accepts a release-relative production state path."""

    with pytest.raises(RuntimePathError, match="FOGBOT_DB_PATH"):
        RuntimePaths.from_environment({"FOGBOT_DB_PATH": str(Path("db") / "bot.db")})


def test_instance_lock_excludes_a_second_holder_and_releases(tmp_path: Path):
    """Catch a production regression that allows two bots to write one runtime state directory."""

    path = tmp_path / "runtime" / "instance.lock"
    first = InstanceLock(path)
    first.acquire()
    with pytest.raises(InstanceLockError):
        InstanceLock(path).acquire()
    first.release()
    second = InstanceLock(path)
    second.acquire()
    second.release()


def test_instance_lock_acquires_when_a_stale_lock_file_exists(tmp_path: Path):
    """Catch a production regression where a crashed process leaves a permanent sentinel lock."""

    path = tmp_path / "runtime" / "instance.lock"
    path.parent.mkdir()
    path.write_text("stale", encoding="utf-8")

    lock = InstanceLock(path)
    lock.acquire()
    lock.release()


def test_instance_lock_release_keeps_a_reusable_lock_file(tmp_path: Path):
    """Catch a production regression where lock-file existence, rather than its descriptor lock, blocks restart."""

    path = tmp_path / "runtime" / "instance.lock"
    first = InstanceLock(path)
    first.acquire()
    first.release()

    assert path.exists()
    second = InstanceLock(path)
    second.acquire()
    second.release()


def test_readiness_record_contains_deployment_identity_and_invalidates(tmp_path: Path):
    """Catch a production regression that publishes incomplete or stale health state."""

    ready = ReadinessRecord(tmp_path, "a" * 40, generation="123e4567-e89b-12d3-a456-426614174000")
    ready.mark_ready()
    saved = json.loads((tmp_path / "ready.json").read_text(encoding="utf-8"))

    assert saved["schema_version"] == 1
    assert saved["release_sha"] == "a" * 40
    assert saved["pid"] == os.getpid()
    assert saved["generation"] == "123e4567-e89b-12d3-a456-426614174000"
    assert saved["boot_id"]
    assert saved["ready_at"].endswith("Z")
    assert saved["heartbeat_at"].endswith("Z")

    ready.invalidate()
    ready.invalidate()
    assert not (tmp_path / "ready.json").exists()


def test_readiness_invalidation_prevents_a_later_heartbeat_from_republishing(tmp_path: Path):
    """Catch a production regression where a disconnected bot recreates ready.json from stale in-memory state."""

    ready = ReadinessRecord(tmp_path, "unknown", generation="123e4567-e89b-12d3-a456-426614174000")
    ready.mark_ready()
    ready.invalidate()
    ready.heartbeat()

    assert not (tmp_path / "ready.json").exists()


@pytest.mark.parametrize(("release_sha", "generation"), [("A" * 40, None), ("abc", None), ("unknown", "not-a-uuid")])
def test_readiness_record_rejects_invalid_runtime_identity(tmp_path: Path, release_sha: str, generation: str | None):
    """Catch a production regression that emits ambiguous release or generation identity in health state."""

    with pytest.raises(ValueError):
        ReadinessRecord(tmp_path, release_sha, generation=generation)


def test_configuration_save_keeps_the_previous_file_when_atomic_replace_fails(tmp_path: Path, monkeypatch):
    """Catch a production regression that truncates configuration before a failed persistence write."""

    path = tmp_path / "configuration.json"
    original = '{"roles": {"keep": true}, "permissions": {}, "technical_info": {}, "channels": {}}'
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr("services.runtime.os.replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        save_runtime_configuration(
            path,
            {"permissions": {}, "technical_info": {"current_run_date": "2030-01-01T00:00:00"}, "channels": {},
             "ticket_system": {}, "message_triggers": [], "messages": {}, "leveling_system": {}, "honeypot_system": {}},
        )
    assert path.read_text(encoding="utf-8") == original


def test_importing_main_creates_no_local_files(tmp_path: Path):
    """Catch a production regression that starts bootstrap side effects during module import."""

    environment = os.environ.copy()
    environment.pop("DISCORD_BOT_TOKEN", None)
    environment["PYTHONPATH"] = str(Path(__file__).parents[1])
    result = subprocess.run([sys.executable, "-c", "import main"], cwd=tmp_path, env=environment, capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert list(tmp_path.iterdir()) == []


async def test_ready_and_disconnect_publish_then_invalidate_local_readiness(tmp_path: Path):
    """Catch a production regression that marks ready before reconciliation or retains readiness after disconnect."""

    import main

    bot = object.__new__(main.MyBot)
    bot._connection = SimpleNamespace(user="local-test-bot")
    bot.logger = SimpleNamespace(info=lambda _: None)
    bot.readiness = ReadinessRecord(tmp_path, "unknown", generation="123e4567-e89b-12d3-a456-426614174000")
    reconciled = []

    async def reconcile() -> None:
        reconciled.append(True)

    bot._update_users_on_guild_status = reconcile
    await bot.on_ready()
    assert reconciled == [True]
    assert (tmp_path / "ready.json").exists()
    await bot.on_disconnect()
    assert not (tmp_path / "ready.json").exists()


async def test_heartbeat_writes_only_when_the_bot_reports_ready(tmp_path: Path, monkeypatch):
    """Catch a production regression that refreshes deployment health while Discord is unavailable."""

    import main

    bot = object.__new__(main.MyBot)
    bot.readiness = ReadinessRecord(tmp_path, "unknown", generation="123e4567-e89b-12d3-a456-426614174000")
    bot.readiness.mark_ready()
    before = (tmp_path / "ready.json").read_text(encoding="utf-8")
    ready_state = False
    bot.is_ready = lambda: ready_state
    sleeps = 0

    async def one_iteration_then_cancel(_: int) -> None:
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", one_iteration_then_cancel)
    with pytest.raises(asyncio.CancelledError):
        await bot._heartbeat_task()
    assert (tmp_path / "ready.json").read_text(encoding="utf-8") == before

    ready_state = True
    sleeps = 0
    with pytest.raises(asyncio.CancelledError):
        await bot._heartbeat_task()
    assert json.loads((tmp_path / "ready.json").read_text(encoding="utf-8"))["heartbeat_at"] >= json.loads(before)["heartbeat_at"]


async def test_close_attempts_database_and_discord_shutdown_after_a_failed_background_task(tmp_path: Path):
    """Catch a production regression where a failed task prevents SQLite and Discord shutdown before unlock."""

    import main

    config_path = tmp_path / "configuration.json"
    config_path.write_text(
        json.dumps({"prefix": "!", "owner_id": 0, "guild_id": 0, "permissions": {}, "technical_info": {}, "channels": {},
                    "roles": {}, "ticket_system": {}, "message_triggers": [], "messages": {}, "leveling_system": {}, "honeypot_system": {}}),
        encoding="utf-8",
    )
    paths = RuntimePaths.from_environment({}, development_base=tmp_path)
    lock = InstanceLock(paths.instance_lock)
    lock.acquire()
    bot = main.MyBot(config_path and json.loads(config_path.read_text(encoding="utf-8")), paths, logging.getLogger("runtime-contract"), False, lock)
    database_closed = tmp_path / "database-closed"

    class LocalDatabase:
        async def close(self) -> None:
            database_closed.write_text("closed", encoding="utf-8")

    async def failed_background_task() -> None:
        raise RuntimeError("autosave failed")

    bot.db = LocalDatabase()
    bot._autosave_task_handle = asyncio.create_task(failed_background_task())
    bot._heartbeat_task_handle = asyncio.create_task(asyncio.sleep(3600))
    await asyncio.sleep(0)
    await bot.close()

    assert database_closed.read_text(encoding="utf-8") == "closed"
    assert bot.is_closed()
    assert bot._heartbeat_task_handle.cancelled()
    assert [str(error) for error in bot._shutdown_errors] == ["autosave failed"]
    replacement = InstanceLock(paths.instance_lock)
    replacement.acquire()
    replacement.release()
