from pathlib import Path

from db.database import Database


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

    first = Database(str(path))
    await first.connect()
    await first.close()

    second = Database(str(path))
    await second.connect()
    assert second.conn is not None
    migration_cursor = await second.conn.execute("SELECT COUNT(*) FROM _yoyo_migration")
    assert await migration_cursor.fetchone() == (2,)
    await second.close()
