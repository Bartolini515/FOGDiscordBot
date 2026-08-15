from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio

from db.database import Database


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated SQLite database isolated from db/bot.db."""
    db = Database(str(tmp_path / "bot.db"))
    await db.connect()
    try:
        yield db
    finally:
        await db.close()
