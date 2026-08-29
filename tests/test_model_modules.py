from importlib import import_module

import pytest


MODEL_MODULES = (
    ("users", "Users"),
    ("blacklist", "Blacklist"),
    ("attendance", "Attendance"),
    ("ranks", "Ranks"),
    ("missions", "Missions"),
    ("squads", "Squads"),
    ("slots", "Slots"),
    ("trainings", "Trainings"),
    ("training_signed", "TrainingSigned"),
    ("tickets", "Tickets"),
    ("ticket_types", "TicketTypes"),
    ("ticket_create_messages", "TicketCreateMessages"),
    ("warns", "Warns"),
)


@pytest.mark.parametrize(("module_name", "class_name"), MODEL_MODULES)
def test_model_class_is_defined_in_its_dedicated_module(module_name: str, class_name: str):
    module_path = f"db.models.{module_name}"
    module = import_module(module_path)
    model_class = getattr(module, class_name)

    assert model_class.__module__ == module_path


def test_model_package_does_not_reexport_model_classes():
    model_package = import_module("db.models")

    for _, class_name in MODEL_MODULES:
        assert not hasattr(model_package, class_name)
