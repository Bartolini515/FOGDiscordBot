"""Pure trigger matching and cooldown decisions."""

from collections.abc import MutableMapping, MutableSequence
from typing import Any


def matching_trigger_responses(
    triggers: MutableSequence[dict[str, Any]],
    content: str,
    last_triggered_times: MutableMapping[str, float],
    *,
    now: float,
) -> list[str]:
    """Return all matching responses and update accepted cooldown timestamps."""

    responses: list[str] = []
    for trigger in triggers:
        if not trigger.get("enabled", False):
            continue

        if trigger.get("case_sensitive", False):
            keyword = trigger.get("keyword", "")
        else:
            keyword = trigger.get("keyword", "").lower()

        if keyword == "":
            continue

        content_to_check = content if trigger.get("case_sensitive", False) else content.lower()
        if trigger.get("whole_word", False):
            matched = keyword in content_to_check.split()
        else:
            matched = content_to_check.find(keyword) != -1

        if not matched:
            continue

        cooldown_seconds = trigger.get("cooldown_seconds", 0)
        if cooldown_seconds > 0:
            last_triggered_time = last_triggered_times.get(keyword, 0)
            if now - last_triggered_time < cooldown_seconds:
                continue
            last_triggered_times[keyword] = now

        response = trigger.get("response", "")
        if response != "":
            responses.append(response)

    return responses
