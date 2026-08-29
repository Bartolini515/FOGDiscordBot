from datetime import datetime
from types import SimpleNamespace

import pytest
from discord.ext import commands

from services.members import (
    find_used_invite,
    has_configured_permission,
    is_target_guild,
    invite_snapshot,
)
from services.moderation import (
    blacklist_expiration,
    format_blacklist_time_left,
    roles_to_remove,
    command_error_message,
    should_enforce_role_whitelist,
)
from services.ranks import should_promote_to_rank


def test_is_target_guild_rejects_missing_or_different_guild():
    assert is_target_guild(SimpleNamespace(id=100), 100) is True
    assert is_target_guild(SimpleNamespace(id=101), 100) is False
    assert is_target_guild(None, 100) is False


def test_find_used_invite_detects_new_or_incremented_invite():
    before = {"old": 2}
    incremented = SimpleNamespace(code="old", uses=3)
    new = SimpleNamespace(code="new", uses=1)

    assert find_used_invite(before, [incremented]) is incremented
    assert find_used_invite(before, [new]) is new
    assert find_used_invite(before, [SimpleNamespace(code="old", uses=2)]) is None


def test_invite_snapshot_keeps_code_and_use_count():
    invites = [SimpleNamespace(code="alpha", uses=4), SimpleNamespace(code="beta", uses=0)]

    assert invite_snapshot(invites) == {"alpha": 4, "beta": 0}


def test_has_configured_permission_allows_user_role_or_administrator():
    allowed_member = SimpleNamespace(id=1001, roles=[], guild_permissions=SimpleNamespace(administrator=False))
    allowed_role = SimpleNamespace(
        id=1002,
        roles=[SimpleNamespace(id=2002)],
        guild_permissions=SimpleNamespace(administrator=False),
    )
    administrator = SimpleNamespace(id=1003, roles=[], guild_permissions=SimpleNamespace(administrator=True))

    assert has_configured_permission(allowed_member, [1001]) is True
    assert has_configured_permission(allowed_role, [2002]) is True
    assert has_configured_permission(administrator, []) is True
    assert has_configured_permission(allowed_member, [9999]) is False


def test_blacklist_expiration_matches_current_storage_format():
    now = datetime(2030, 1, 2, 18, 30)

    expiration, formatted = blacklist_expiration(2, now=now)

    assert expiration == datetime(2030, 1, 4, 18, 30)
    assert formatted == "2030-01-04 18:30"
    assert blacklist_expiration(None, now=now) == (None, None)


def test_format_blacklist_time_left_preserves_day_display_rules():
    now = datetime(2030, 1, 2, 18, 30)

    assert format_blacklist_time_left(None, now=now) == "Nieskończony"
    assert format_blacklist_time_left("2030-01-04 18:30", now=now) == "2"
    assert format_blacklist_time_left("2030-01-02 17:30", now=now) == "-1"


def test_role_whitelist_helpers_skip_everyone_and_keep_allowed_roles():
    before_roles = [SimpleNamespace(id=100, is_default=lambda: False)]
    after_roles = [
        SimpleNamespace(id=0, name="@everyone", is_default=lambda: True),
        SimpleNamespace(id=100, name="Candidate", is_default=lambda: False),
        SimpleNamespace(id=200, name="Unauthorized", is_default=lambda: False),
    ]

    assert should_enforce_role_whitelist(before_roles, 100, 300) is True
    assert should_enforce_role_whitelist([], 100, 300) is False
    assert roles_to_remove(after_roles, [100, 300]) == [after_roles[2]]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (commands.CommandNotFound(), "Ta komenda nie istnieje."),
        (commands.DisabledCommand(), "Ta komenda jest obecnie niedostępna."),
        (commands.MissingPermissions([]), "Nie masz wymaganych uprawnień do uruchomienia tej komendy."),
        (
            commands.CommandOnCooldown(commands.Cooldown(1, 1), 1.25, commands.BucketType.user),
            "Ta komenda jest na cooldownie. Spróbuj ponownie za 1.2s.",
        ),
    ],
)
def test_command_error_message_preserves_existing_user_text(error, expected):
    assert command_error_message(error) == expected


def test_command_error_message_uses_none_for_unhandled_errors():
    assert command_error_message(RuntimeError("boom")) is None


def test_should_promote_to_rank_respects_maximum_and_next_thresholds():
    assert should_promote_to_rank(10, 20, 10) is True
    assert should_promote_to_rank(20, 20, 10) is False
    assert should_promote_to_rank(9, 20, 10) is False
