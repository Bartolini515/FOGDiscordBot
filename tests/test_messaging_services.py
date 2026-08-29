from types import SimpleNamespace

import discord

from services.help import command_category, user_can_see_command
from services.honeypot import counter_entries_for_channel, valid_counter_entries
from services.leveling import (
    calculate_experience,
    calculate_level,
    check_level_up,
    next_experience,
)
from services.triggers import matching_trigger_responses


def test_help_services_use_explicit_category_and_permission_rules():
    categorized = SimpleNamespace(extras={"category": "Poziomy"}, parent=None)
    uncategorized = SimpleNamespace(extras={}, parent=None)
    user = SimpleNamespace(user=SimpleNamespace(guild_permissions=discord.Permissions(administrator=False)))
    administrator = SimpleNamespace(user=SimpleNamespace(guild_permissions=discord.Permissions(administrator=True)))
    restricted = SimpleNamespace(default_permissions=discord.Permissions(administrator=True))
    unrestricted = SimpleNamespace(default_permissions=None)

    assert command_category(categorized) == "Poziomy"
    assert command_category(uncategorized) == "Inne"
    assert user_can_see_command(user, restricted) is False
    assert user_can_see_command(administrator, restricted) is True
    assert user_can_see_command(user, unrestricted) is True


def test_leveling_services_preserve_current_experience_formulas_and_cap():
    assert calculate_experience(0) == 100
    assert calculate_level(100) == 0
    assert check_level_up(99, 100) is False
    assert check_level_up(100, calculate_experience(1)) is True
    assert next_experience(55090, 25, 55100) == 55100


def test_trigger_matching_preserves_case_whole_word_and_cooldown_rules():
    triggers = [
        {"keyword": "Hello", "response": "A", "enabled": True, "case_sensitive": False, "whole_word": True, "cooldown_seconds": 10},
        {"keyword": "ell", "response": "B", "enabled": True, "case_sensitive": False, "whole_word": False, "cooldown_seconds": 0},
        {"keyword": "skip", "response": "C", "enabled": False},
    ]
    last_times = {}

    assert matching_trigger_responses(triggers, "hello there", last_times, now=100.0) == ["A", "B"]
    assert matching_trigger_responses(triggers, "hello there", last_times, now=105.0) == ["B"]
    assert matching_trigger_responses(triggers, "hello there", last_times, now=111.0) == ["A", "B"]


def test_honeypot_services_filter_invalid_entries_and_remove_one_channel():
    entries = [
        {"channel_id": 100, "message_id": 200},
        {"channel_id": None, "message_id": 201},
        "malformed",
        {"channel_id": 101, "message_id": 202},
    ]

    assert valid_counter_entries(entries) == [entries[0], entries[3]]
    assert counter_entries_for_channel(valid_counter_entries(entries), 100) == [entries[3]]
