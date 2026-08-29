"""SQLite connection lifecycle and explicit offline migration helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sqlite3

import aiosqlite
from yoyo import get_backend, read_migrations


DEFAULT_MIGRATIONS_PATH = Path(__file__).with_name("migrations")


class PendingMigrationsError(RuntimeError):
    """Raised when the application database has unapplied committed migrations."""

    def __init__(self, migration_ids: list[str]):
        migrations = ", ".join(migration_ids)
        super().__init__(
            f"Pending database migrations: {migrations}. "
            "Run python -m scripts.migrate --database <path> before starting the bot."
        )
        self.migration_ids = migration_ids


def pending_migration_ids(
    database_path: str | Path, migrations_path: str | Path | None = None
) -> list[str]:
    """List committed migration IDs that have not been applied to ``database_path``."""
    path = Path(database_path).resolve()
    applied = _applied_migration_ids(path)
    return [migration.id for migration in _read_migrations(migrations_path) if migration.id not in applied]


def apply_committed_migrations(
    database_path: str | Path, migrations_path: str | Path | None = None
) -> list[str]:
    """Apply committed migrations to an explicit database and return their IDs."""
    backend, migrations = _migration_backend(database_path, migrations_path)
    with backend.lock():
        pending = backend.to_apply(migrations)
        applied = [migration.id for migration in pending]
        if applied:
            backend.apply_migrations(pending)
        remaining = pending_migration_ids(database_path, migrations_path)
    if remaining:
        raise PendingMigrationsError(remaining)
    return applied


def _migration_backend(database_path: str | Path, migrations_path: str | Path | None):
    path = Path(database_path).resolve()
    return get_backend(f"sqlite:///{path.as_posix()}"), _read_migrations(migrations_path)


def _read_migrations(migrations_path: str | Path | None):
    directory = Path(migrations_path) if migrations_path is not None else DEFAULT_MIGRATIONS_PATH
    return read_migrations(str(directory))


def _applied_migration_ids(database_path: Path) -> set[str]:
    if not database_path.exists():
        return set()
    database_uri = f"file:{database_path.as_posix()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        migration_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = '_yoyo_migration'"
        ).fetchone()
        if migration_table is None:
            return set()
        return {row[0] for row in connection.execute("SELECT migration_id FROM _yoyo_migration")}


class Database:
    """Own one asynchronous SQLite connection for a caller-supplied path."""

    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open a current database and enable SQLite foreign-key enforcement."""
        pending = await asyncio.to_thread(pending_migration_ids, self.path)
        if pending:
            raise PendingMigrationsError(pending)
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA foreign_keys = ON")

    async def close(self) -> None:
        """Close the active connection, if any."""
        if self.conn:
            await self.conn.close()
