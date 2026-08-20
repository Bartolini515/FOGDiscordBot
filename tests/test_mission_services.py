from datetime import datetime, timedelta

import pytest

from services.missions import (
    build_slot_mapping,
    mission_message_content,
    mission_select_custom_id,
    parse_mission_date,
    parse_signup_slots,
    parse_stored_mission_date,
    signout_custom_id,
    signout_is_too_close,
)


def test_mission_message_content_preserves_occupied_and_free_slot_format():
    slots = {
        1: (1, "Leader", 1001),
        2: (2, "Medic", None),
    }

    assert mission_message_content(slots, "Alpha") == (
        "📋 Zapisz się do drużyny **Alpha**:\n"
        "- Leader  ✅ - <@1001>\n"
        "- Medic  ❌ - _wolny_"
    )


def test_mission_date_helpers_preserve_input_and_stored_formats():
    assert parse_mission_date("2030-01-02 18:30") == datetime(2030, 1, 2, 18, 30)
    assert parse_stored_mission_date("2030-01-02 18:30:00") == datetime(2030, 1, 2, 18, 30)
    assert parse_stored_mission_date("2030-01-02 18:30") == datetime(2030, 1, 2, 18, 30)
    with pytest.raises(ValueError):
        parse_mission_date("not-a-date")


def test_signout_cutoff_and_signup_slot_parsing_preserve_boundaries():
    now = datetime(2030, 1, 2, 12, 0)
    assert signout_is_too_close(now + timedelta(hours=11, minutes=59), now=now) is True
    assert signout_is_too_close(now + timedelta(hours=12), now=now) is False
    assert parse_signup_slots(" Leader; ;Medic ") == ["Leader", "Medic"]
    assert parse_signup_slots("") == []


def test_slot_mapping_and_custom_ids_preserve_persistent_wire_values():
    assert build_slot_mapping(["Leader", "Medic"], 10) == {
        11: (11, "Leader", None),
        12: (12, "Medic", None),
    }
    assert mission_select_custom_id(1001) == "mission_select_1001"
    assert signout_custom_id(1001) == "signout_button_1001"
