from Cogs.Missions import _message_content


def test_message_content_marks_occupied_and_free_slots():
    slots = {
        1: (1, "Leader", 1001),
        2: (2, "Medic", None),
    }

    assert _message_content(slots, "Alpha") == (
        "📋 Zapisz się do drużyny **Alpha**:\n"
        "- Leader  ✅ - <@1001>\n"
        "- Medic  ❌ - _wolny_"
    )
