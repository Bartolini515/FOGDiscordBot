from ticket.core import get_type_handler, normalize_channel_name, parse_categories_payload, serialize_categories_payload


def test_normalize_channel_name_produces_safe_discord_channel_name():
    assert normalize_channel_name("  Mission Alpha / 2  ") == "mission-alpha-2"
    assert normalize_channel_name("!!!") == "ticket"


def test_ticket_category_payload_round_trips_unicode_categories():
    payload = serialize_categories_payload("select", ["Misja", "SzWI"])

    assert payload == '{"mode": "select", "categories": ["Misja", "SzWI"]}'
    assert parse_categories_payload(payload) == ("select", ["Misja", "SzWI"])


def test_parse_categories_payload_normalizes_single_value_and_malformed_input():
    assert parse_categories_payload('{"mode": "button", "categories": "Misja"}') == ("button", ["Misja"])
    assert parse_categories_payload("not-json") == ("select", [])


def test_unknown_ticket_type_uses_custom_handler():
    assert get_type_handler("mission").type_name == "mission"
    assert get_type_handler("unknown").type_name == "custom"
