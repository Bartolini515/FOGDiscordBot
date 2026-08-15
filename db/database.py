"""SQLite connection lifecycle with yoyo migrations applied before use."""

import aiosqlite
import asyncio
from pathlib import Path
from yoyo import get_backend, read_migrations

class Database:
    """Own one asynchronous SQLite connection for a caller-supplied path."""

    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def _apply_migrations(self) -> None:
        """Apply pending repository migrations in a worker thread."""
        db_path = Path(self.path).resolve()
        db_url = f"sqlite:///{db_path.as_posix()}"
        migrations_path = Path(__file__).parent / "migrations"

        def run_migrations() -> None:
            backend = get_backend(db_url)
            migrations = read_migrations(str(migrations_path))
            with backend.lock():
                backend.apply_migrations(backend.to_apply(migrations))

        await asyncio.to_thread(run_migrations)

    async def connect(self):
        """Migrate, connect, and enable SQLite foreign-key enforcement."""
        await self._apply_migrations()
        self.conn = await aiosqlite.connect(self.path)
        await self.conn.execute("PRAGMA foreign_keys = ON")
    async def close(self):
        """Close the active connection, if any."""
        if self.conn:
            await self.conn.close()
