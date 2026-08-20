from services.administration import (
    add_permission_entry,
    add_ticket_category,
    edit_trigger,
    format_sql_result,
    remove_permission_entry,
    remove_ticket_category,
    remove_trigger,
    set_channel_mapping,
    split_sql_response,
)


def test_sql_service_preserves_columns_rows_and_affected_row_messages():
    assert format_sql_result([("value",)], [(1,)], 1) == "Columns: value\n(1,)"
    assert format_sql_result([("value",)], [], 0) == "Columns: value\nNo rows returned."
    assert format_sql_result(None, [], 2) == "Statement executed successfully. Rows affected: 2."
    assert split_sql_response("alpha\nbeta", limit=5) == ["alpha", "beta"]


def test_permission_mutations_preserve_duplicate_and_missing_statuses():
    permissions = {"admins": [1001]}

    assert add_permission_entry(permissions, "missing", user_id=1002) == "missing_category"
    assert add_permission_entry(permissions, "admins") == "missing_target"
    assert add_permission_entry(permissions, "admins", user_id=1001) == "user_exists"
    assert add_permission_entry(permissions, "admins", user_id=1002) is None
    assert permissions["admins"] == [1001, 1002]
    assert remove_permission_entry(permissions, "admins", user_id=9999) == "user_missing"
    assert remove_permission_entry(permissions, "admins", user_id=1001) is None
    assert permissions["admins"] == [1002]


def test_channel_mapping_updates_only_known_categories():
    channels = {"log": 100}

    assert set_channel_mapping(channels, "unknown", 200) is False
    assert set_channel_mapping(channels, "log", 200) is True
    assert channels == {"log": 200}


def test_ticket_category_mutations_preserve_custom_category_rules():
    categories = [{"name": "builtin", "type": "mission"}, {"name": "custom", "type": "custom"}]
    added = {"name": "new", "type": "custom"}

    add_ticket_category(categories, added)
    assert categories[-1] is added
    assert remove_ticket_category(categories, "builtin") == "protected"
    assert remove_ticket_category(categories, "missing") == "missing"
    assert remove_ticket_category(categories, "custom") is None
    assert [category["name"] for category in categories] == ["builtin", "new"]


def test_trigger_mutations_edit_and_remove_in_place():
    triggers = [{"keyword": "hello", "response": "old", "enabled": True}]

    assert edit_trigger(triggers, "missing", response="new") is False
    assert edit_trigger(triggers, "hello", response="new", enabled=False) is True
    assert triggers == [{"keyword": "hello", "response": "new", "enabled": False}]
    assert remove_trigger(triggers, "missing") is False
    assert remove_trigger(triggers, "hello") is True
    assert triggers == []
