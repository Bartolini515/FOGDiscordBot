import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from db.database import Database, PendingMigrationsError, apply_committed_migrations, pending_migration_ids
from scripts import migrate


def test_empty_database_lists_all_committed_migrations_without_creating_schema(tmp_path: Path):
    path = tmp_path / "empty.sqlite3"

    assert pending_migration_ids(path) == ["001_init", "002_warns"]
    assert not path.exists()


async def test_connect_refuses_a_database_with_pending_migrations(tmp_path: Path):
    database = Database(str(tmp_path / "pending.sqlite3"))

    with pytest.raises(PendingMigrationsError, match=r"python -m scripts\.migrate --database"):
        await database.connect()

    assert database.conn is None


async def test_connect_opens_an_explicitly_migrated_database_with_foreign_keys(tmp_path: Path):
    path = tmp_path / "current.sqlite3"
    assert apply_committed_migrations(path) == ["001_init", "002_warns"]

    database = Database(str(path))
    await database.connect()
    try:
        assert database.conn is not None
        pragma_cursor = await database.conn.execute("PRAGMA foreign_keys")
        assert await pragma_cursor.fetchone() == (1,)
    finally:
        await database.close()


def test_applying_current_migrations_is_a_noop(tmp_path: Path):
    path = tmp_path / "current.sqlite3"

    apply_committed_migrations(path)

    assert apply_committed_migrations(path) == []
    assert pending_migration_ids(path) == []


def test_failed_migration_remains_pending(tmp_path: Path):
    path = tmp_path / "failed.sqlite3"
    migrations_path = tmp_path / "migrations"
    migrations_path.mkdir()
    (migrations_path / "001_broken.sql").write_text("-- name: 001_broken\nCREATE TABL broken (id INTEGER);\n", encoding="utf-8")

    with pytest.raises(Exception):
        apply_committed_migrations(path, migrations_path)

    assert pending_migration_ids(path, migrations_path) == ["001_broken"]


def test_migrate_cli_requires_an_explicit_database_path(tmp_path: Path):
    result = _run_migrate_cli(tmp_path)

    assert result.returncode != 0
    assert "--database" in result.stderr
    assert list(tmp_path.iterdir()) == []


def test_migrate_cli_check_is_read_only_when_migrations_are_pending(tmp_path: Path):
    path = tmp_path / "check.sqlite3"

    result = _run_migrate_cli(tmp_path, "--database", str(path), "--check")

    assert result.returncode != 0
    assert "Pending migrations: 001_init, 002_warns" in result.stdout
    assert not path.exists()


def test_migrate_cli_check_reports_a_corrupt_database_without_a_traceback(tmp_path: Path):
    path = tmp_path / "corrupt.sqlite3"
    path.write_bytes(b"not a SQLite database")

    result = _run_migrate_cli(tmp_path, "--database", str(path), "--check")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("Migration failed: ")
    assert "Traceback" not in result.stderr
    assert "not a SQLite database" not in result.stderr


def test_migrate_cli_reports_a_post_apply_recheck_failure(tmp_path: Path, monkeypatch, capsys):
    path = tmp_path / "recheck.sqlite3"
    monkeypatch.setattr(sys, "argv", ["migrate", "--database", str(path)])
    monkeypatch.setattr(migrate, "apply_committed_migrations", lambda *_: ["001_init"])

    def raise_database_error(*_: object) -> list[str]:
        raise sqlite3.DatabaseError("database recheck failed")

    monkeypatch.setattr(migrate, "pending_migration_ids", raise_database_error)

    assert migrate.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("Migration failed: ")
    assert "Traceback" not in captured.err
    assert "database recheck failed" not in captured.err


def test_migrate_cli_applies_then_checks_migrations(tmp_path: Path):
    path = tmp_path / "migrated.sqlite3"

    apply_result = _run_migrate_cli(tmp_path, "--database", str(path))
    check_result = _run_migrate_cli(tmp_path, "--database", str(path), "--check")

    assert apply_result.returncode == 0, apply_result.stderr
    assert "Applied migrations: 001_init, 002_warns" in apply_result.stdout
    assert check_result.returncode == 0, check_result.stderr
    assert "No pending migrations." in check_result.stdout


def _run_migrate_cli(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[1])
    environment["PIPENV_DONT_LOAD_ENV"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "scripts.migrate", *arguments],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


async def test_migrations_create_expected_schema_and_seed_domain_data(database: Database):
    assert database.conn is not None

    table_cursor = await database.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {row[0] for row in await table_cursor.fetchall()}
    assert {
        "_yoyo_migration",
        "attendance",
        "blacklist",
        "missions",
        "ranks",
        "slots",
        "squads",
        "ticket_create_messages",
        "ticket_types",
        "tickets",
        "training_signed",
        "trainings",
        "users",
        "warns",
    } <= tables

    trigger_cursor = await database.conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
    assert {row[0] for row in await trigger_cursor.fetchall()} == {
        "update_warns_count_delete",
        "update_warns_count_insert",
    }

    rank_cursor = await database.conn.execute("SELECT name, required_missions FROM ranks ORDER BY id")
    assert await rank_cursor.fetchall() == [
        ("Rekrut", 0),
        ("Operator I", 10),
        ("Operator II", 60),
        ("Operator III", 90),
        ("Operator IV", 140),
        ("Operator V", 200),
    ]

    type_cursor = await database.conn.execute("SELECT name FROM ticket_types ORDER BY id")
    assert [row[0] for row in await type_cursor.fetchall()] == [
        "mission",
        "proposal",
        "recruitment",
        "basic_training",
        "custom",
    ]

    pragma_cursor = await database.conn.execute("PRAGMA foreign_keys")
    assert await pragma_cursor.fetchone() == (1,)


async def test_connect_is_idempotent_for_an_already_migrated_database(tmp_path: Path):
    path = tmp_path / "reconnect.db"

    apply_committed_migrations(path)
    first = Database(str(path))
    await first.connect()
    await first.close()

    second = Database(str(path))
    await second.connect()
    assert second.conn is not None
    migration_cursor = await second.conn.execute("SELECT COUNT(*) FROM _yoyo_migration")
    assert await migration_cursor.fetchone() == (2,)
    await second.close()
