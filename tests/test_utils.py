from types import SimpleNamespace

import pytest

from utils.database import has_database
from utils.dates import normalize_datetime
from utils.discord import parse_user_mentions
from utils.text import split_response
from services.runtime import collect_non_bot_members, configure_logging, load_cogs, save_runtime_configuration


def test_has_database_matches_existing_bot_attribute_check():
    assert has_database(SimpleNamespace(db=object())) is True
    assert has_database(SimpleNamespace(db=None)) is False
    assert has_database(SimpleNamespace()) is False


def test_split_response_preserves_lines_and_discord_limit():
    chunks = split_response("alpha\nbeta\ngamma", limit=5)

    assert chunks == ["alpha", "beta", "gamma"]
    assert all(len(chunk) <= 5 for chunk in chunks)


def test_split_response_splits_long_lines_and_preserves_empty_response():
    assert split_response("abcdefgh", limit=3) == ["abc", "def", "gh"]
    assert split_response("", limit=3) == [""]


def test_parse_user_mentions_keeps_current_token_slicing():
    assert parse_user_mentions("<@1001> ignored <@!1002> text") == ["1001", "!1002"]
    assert parse_user_mentions(None) == []


def test_normalize_datetime_matches_current_mission_format():
    assert normalize_datetime("2030-01-02 18:30") == "2030-01-02 18:30:00"


def test_normalize_datetime_raises_value_error_for_invalid_input():
    with pytest.raises(ValueError):
        normalize_datetime("not-a-date")


def test_collect_non_bot_members_skips_bots_and_keeps_id_name_pairs():
    guild = SimpleNamespace(
        members=[
            SimpleNamespace(id=1001, name="operator", bot=False),
            SimpleNamespace(id=1002, name="integration", bot=True),
        ]
    )

    assert collect_non_bot_members(guild) == [(1001, "operator")]


def test_save_runtime_configuration_updates_only_mutable_sections(tmp_path):
    path = tmp_path / "configuration.json"
    path.write_text(
        '{"roles": {"keep": true}, "permissions": {}, "technical_info": {}, "channels": {}}',
        encoding="utf-8",
    )

    save_runtime_configuration(
        path,
        {
            "permissions": {"admins": [1001]},
            "technical_info": {"current_run_date": "2030-01-02T18:30:00"},
            "channels": {"log_channel_id": 2001},
            "ticket_system": {"categories": []},
            "message_triggers": [],
            "messages": {"welcome_message": "Welcome"},
            "leveling_system": {"notifications_off_users": []},
            "honeypot_system": {"trap_counter": 0},
        },
    )

    import json

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["roles"] == {"keep": True}
    assert saved["permissions"] == {"admins": [1001]}
    assert saved["technical_info"]["current_run_date"] == "2030-01-02T18:30:00"
    assert saved["channels"] == {"log_channel_id": 2001}


async def test_load_cogs_loads_python_extensions_and_logs_success(monkeypatch):
    loaded = []
    messages = []

    class FakeBot:
        async def load_extension(self, extension):
            loaded.append(extension)

    class FakeLogger:
        def info(self, message):
            messages.append(message)

        def exception(self, message):
            messages.append(message)

    monkeypatch.setattr("services.runtime.os.listdir", lambda _: ["Alpha.py", "README.md"])

    await load_cogs(FakeBot(), FakeLogger())

    assert loaded == ["Cogs.Alpha"]
    assert messages == ["Loaded extension: Cogs.Alpha"]


def test_configure_logging_creates_expected_handlers_once(tmp_path):
    import logging

    bot_logger = logging.getLogger("fogbot")
    discord_logger = logging.getLogger("discord")
    original_bot_handlers = list(bot_logger.handlers)
    original_discord_handlers = list(discord_logger.handlers)
    bot_logger.handlers.clear()
    discord_logger.handlers.clear()

    try:
        configured = configure_logging(False, tmp_path)

        assert configured is bot_logger
        assert len(bot_logger.handlers) == 2
        assert len(discord_logger.handlers) == 2
        assert (tmp_path / "bot.log").exists()

        configure_logging(False, tmp_path)
        assert len(bot_logger.handlers) == 2
        assert len(discord_logger.handlers) == 2
    finally:
        for handler in bot_logger.handlers + discord_logger.handlers:
            handler.close()
        bot_logger.handlers[:] = original_bot_handlers
        discord_logger.handlers[:] = original_discord_handlers
