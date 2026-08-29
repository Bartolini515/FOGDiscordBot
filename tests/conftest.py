from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from db.database import Database, apply_committed_migrations


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database isolated from production data."""
    path = tmp_path / "bot.db"
    apply_committed_migrations(path)
    db = Database(str(path))
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
