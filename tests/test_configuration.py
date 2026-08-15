import importlib
import json
from pathlib import Path

import pytest


def _configuration_module():
    try:
        return importlib.import_module("configuration")
    except ModuleNotFoundError:
        pytest.fail("configuration module has not been implemented")


def _minimal_configuration() -> dict:
    return {
        "prefix": "!",
        "owner_id": 0,
        "guild_id": 0,
        "permissions": {},
        "technical_info": {},
        "channels": {},
        "roles": {},
        "ticket_system": {},
        "message_triggers": [],
        "messages": {},
        "leveling_system": {},
        "honeypot_system": {
            "honeypot_channels": [],
            "counter_messages": [],
            "trap_counter": 0,
        },
    }


def test_ensure_configuration_file_copies_once_without_overwriting(tmp_path: Path):
    configuration = _configuration_module()
    template = tmp_path / "configuration.example.json"
    destination = tmp_path / "configuration.json"
    template.write_text('{"prefix": "!"}\n', encoding="utf-8")

    assert configuration.ensure_configuration_file(destination, template) is True
    assert destination.read_text(encoding="utf-8") == template.read_text(encoding="utf-8")

    destination.write_text('{"preserve": true}\n', encoding="utf-8")
    assert configuration.ensure_configuration_file(destination, template) is False
    assert destination.read_text(encoding="utf-8") == '{"preserve": true}\n'


def test_load_configuration_accepts_minimal_valid_document(tmp_path: Path):
    configuration = _configuration_module()
    path = tmp_path / "configuration.json"
    expected = _minimal_configuration()
    path.write_text(json.dumps(expected), encoding="utf-8")

    assert configuration.load_configuration(path) == expected


def test_load_configuration_reports_all_missing_sections(tmp_path: Path):
    configuration = _configuration_module()
    path = tmp_path / "configuration.json"
    data = _minimal_configuration()
    del data["roles"]
    del data["messages"]
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(configuration.ConfigurationError, match=r"messages, roles"):
        configuration.load_configuration(path)


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (lambda data: data.update(owner_id="not-an-integer"), "owner_id must be an integer"),
        (lambda data: data.update(message_triggers={}), "message_triggers must be a list"),
        (
            lambda data: data["honeypot_system"].pop("trap_counter"),
            "honeypot_system is missing required keys: trap_counter",
        ),
    ],
)
def test_load_configuration_rejects_invalid_types_and_nested_keys(tmp_path: Path, mutate, expected_message: str):
    configuration = _configuration_module()
    path = tmp_path / "configuration.json"
    data = _minimal_configuration()
    mutate(data)
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(configuration.ConfigurationError, match=expected_message):
        configuration.load_configuration(path)


def test_example_configuration_is_valid_and_contains_no_real_ids():
    configuration = _configuration_module()
    example_path = Path(__file__).parents[1] / "configuration.example.json"

    data = configuration.load_configuration(example_path)

    def assert_safe_ids(value, key: str = "root"):
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                assert_safe_ids(child_value, child_key)
        elif key.endswith("_id"):
            assert value == 0
        elif key.endswith("_ids"):
            assert value == []

    assert_safe_ids(data)
    assert "DISCORD_BOT_TOKEN" not in example_path.read_text(encoding="utf-8")
