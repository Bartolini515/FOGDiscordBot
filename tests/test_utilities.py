import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

from db.database import Database


def _utilities_class():
    return importlib.import_module("Cogs.Utilities").Utilities


def _interaction(user_id: int, owner_id: int):
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id),
        client=SimpleNamespace(owner_id=owner_id),
    )


class FakeResponse:
    def __init__(self):
        self.defer_kwargs = None

    async def defer(self, **kwargs):
        self.defer_kwargs = kwargs


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content, **kwargs):
        self.messages.append((content, kwargs))


def _command_interaction(owner_id: int = 9001):
    return SimpleNamespace(
        user=SimpleNamespace(id=owner_id),
        client=SimpleNamespace(owner_id=owner_id),
        response=FakeResponse(),
        followup=FakeFollowup(),
    )


def test_utility_command_descriptions_match_callback_parameters():
    source_path = Path(__file__).parents[1] / "Cogs" / "Utilities.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) or node.name != "send_message":
            continue

        parameters = {argument.arg for argument in node.args.args}
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute) or decorator.func.attr != "describe":
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app_commands":
                continue

            described_parameters = {keyword.arg for keyword in decorator.keywords}
            assert described_parameters <= parameters
            return

    raise AssertionError("send_message command description was not found")


async def test_sql_query_command_is_registered_with_owner_check():
    command = getattr(_utilities_class(), "sql_query", None)
    assert command is not None
    assert callable(getattr(command, "callback", None))
    assert len(command.checks) == 1


async def test_owner_predicate_allows_only_configured_owner():
    command = getattr(_utilities_class(), "sql_query", None)
    assert command is not None
    predicate = command.checks[0]

    assert await predicate(_interaction(9001, 9001)) is True
    assert await predicate(_interaction(9002, 9001)) is False


async def test_owner_receives_select_columns_and_rows(database: Database):
    utilities = _utilities_class()
    bot = SimpleNamespace(owner_id=9001, db=database)
    interaction = _command_interaction()

    await utilities.sql_query.callback(
        utilities(bot), interaction, "SELECT 1 AS value"
    )

    assert interaction.response.defer_kwargs == {"ephemeral": True, "thinking": True}
    assert len(interaction.followup.messages) == 1
    content, kwargs = interaction.followup.messages[0]
    assert "Columns: value" in content
    assert "(1,)" in content
    assert kwargs["ephemeral"] is True


async def test_write_statement_is_committed_and_reports_affected_rows(database: Database):
    await database.conn.execute("CREATE TABLE sql_query_test (value INTEGER)")
    await database.conn.commit()
    utilities = _utilities_class()
    bot = SimpleNamespace(owner_id=9001, db=database)
    interaction = _command_interaction()

    await utilities.sql_query.callback(
        utilities(bot), interaction, "INSERT INTO sql_query_test VALUES (42)"
    )

    cursor = await database.conn.execute("SELECT value FROM sql_query_test")
    assert await cursor.fetchall() == [(42,)]
    assert "Rows affected: 1" in interaction.followup.messages[0][0]


async def test_invalid_sql_returns_ephemeral_error(database: Database):
    utilities = _utilities_class()
    bot = SimpleNamespace(owner_id=9001, db=database)
    interaction = _command_interaction()

    await utilities.sql_query.callback(
        utilities(bot), interaction, "SELECT * FROM missing_sql_query_table"
    )

    content, kwargs = interaction.followup.messages[0]
    assert content.startswith("Błąd SQL:")
    assert kwargs["ephemeral"] is True


async def test_multiple_statements_are_rejected(database: Database):
    utilities = _utilities_class()
    bot = SimpleNamespace(owner_id=9001, db=database)
    interaction = _command_interaction()

    await utilities.sql_query.callback(utilities(bot), interaction, "SELECT 1; SELECT 2")

    assert interaction.followup.messages[0][0].startswith("Błąd SQL:")


async def test_missing_connection_returns_availability_error():
    utilities = _utilities_class()
    bot = SimpleNamespace(owner_id=9001, db=SimpleNamespace(conn=None))
    interaction = _command_interaction()

    await utilities.sql_query.callback(utilities(bot), interaction, "SELECT 1")

    assert interaction.followup.messages[0][0] == "Baza danych jest niedostępna."


def test_split_sql_response_keeps_chunks_within_discord_limit():
    import Cogs.Utilities as utilities_module

    splitter = getattr(utilities_module, "_split_sql_response", None)
    assert splitter is not None
    chunks = splitter("alpha\nbeta\ngamma", limit=5)

    assert chunks == ["alpha", "beta", "gamma"]
    assert all(len(chunk) <= 5 for chunk in chunks)
