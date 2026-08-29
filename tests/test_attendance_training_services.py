from services.attendance import (
    build_mission_attendance_maps,
    mission_attendance_report,
    present_user_ids,
)
from services.trainings import (
    format_training_attendance,
    normalize_training_date,
    training_message_content,
    training_present_user_ids,
)


def test_mission_maps_and_present_users_preserve_row_contracts():
    squads = [(101, 1, "Alpha"), (102, 1, "Bravo")]
    slots = [(101, 1, "Leader", 1001), (101, 2, "Medic", None), (102, 3, "Rifleman", 1002)]

    squad_map, slots_map = build_mission_attendance_maps(squads, slots)

    assert squad_map == {101: "Alpha", 102: "Bravo"}
    assert slots_map == {
        101: [("Leader", 1001), ("Medic", None)],
        102: [("Rifleman", 1002)],
    }
    assert present_user_ids(slots_map, ["1002"]) == [1001]


def test_mission_attendance_report_preserves_empty_squad_and_member_lines():
    report, empty_squads = mission_attendance_report(
        "Operation North",
        "2030-01-02",
        {101: "Alpha", 102: "Bravo"},
        {101: [("Leader", 1001), ("Medic", None)], 102: []},
        [1001],
    )

    assert report == (
        "Obecność na misji Operation North (2030-01-02):\n"
        "Obecność **Alpha**:\n"
        "- Leader - <@1001> ✅\n"
        "- Medic - *Brak* ❌\n"
    )
    assert empty_squads == ["Bravo"]


def test_training_message_and_date_normalization_preserve_current_output():
    assert training_message_content("Basic", "2030-01-02 18:00", []) == (
        "📋 Zapisz się na szkolenie **Basic** 2030-01-02 18:00\n_Brak zapisanych._"
    )
    assert training_message_content("Basic", None, [1001, 1002]) == (
        "📋 Zapisz się na szkolenie **Basic** None\n- <@1001>\n- <@1002>"
    )
    assert normalize_training_date("2030-01-02 18:00") == "2030-01-02 18:00:00"


def test_training_attendance_report_excludes_absentees_from_roles_but_lists_all():
    rows = [(1, 10, 1001), (2, 10, 1002)]

    assert training_present_user_ids(rows, ["1002"]) == [1001]
    assert format_training_attendance("Basic", "2030-01-02", rows, ["1002"]) == (
        "📌 Obecność na szkoleniu **Basic** 2030-01-02\n"
        "- <@1001> — ✅ obecny\n"
        "- <@1002> — ❌ nieobecny"
    )
