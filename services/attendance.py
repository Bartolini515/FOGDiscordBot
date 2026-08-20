"""Pure mission-attendance transformations and report rendering."""

from collections.abc import Iterable


def build_mission_attendance_maps(
    squad_rows: Iterable[tuple],
    slot_rows: Iterable[tuple],
) -> tuple[dict[int, str], dict[int, list[tuple[str, int | None]]]]:
    """Build the same message-to-squad and message-to-slot maps as the cog."""

    squad_map: dict[int, str] = {}
    for row in squad_rows:
        squad_map[row[0]] = row[2]

    slots_map: dict[int, list[tuple[str, int | None]]] = {}
    for row in slot_rows:
        if row[0] not in slots_map:
            slots_map[row[0]] = []
        slots_map[row[0]].append((row[2], row[3]))
    return squad_map, slots_map


def present_user_ids(
    slots_map: dict[int, list[tuple[str, int | None]]],
    absent_users: Iterable[str],
) -> list[int]:
    """Return occupied slot users excluding explicitly absent IDs."""

    absent = set(absent_users)
    present: list[int] = []
    for users in slots_map.values():
        for _, user in users:
            if user and str(user) not in absent:
                present.append(int(user))
    return present


def mission_attendance_report(
    mission_name: str,
    mission_date: str,
    squad_map: dict[int, str],
    slots_map: dict[int, list[tuple[str, int | None]]],
    present_users: Iterable[int],
) -> tuple[str, list[str]]:
    """Render the mission report and identify squads with no slots."""

    present = list(present_users)
    message_content = f"Obecność na misji {mission_name} ({mission_date}):\n"
    empty_squads: list[str] = []
    for squad_message_id, squad_name in squad_map.items():
        squad_members = slots_map.get(squad_message_id, [])
        if squad_members:
            lines = [f"Obecność **{squad_name}**:"]
            for label, user in squad_members:
                mention = f"<@{user}>" if user else "*Brak*"
                status = "✅" if user in present else "❌"
                lines.append(f"- {label} - {mention} {status}")
            message_content += "\n".join(lines) + "\n"
        else:
            empty_squads.append(squad_name)
    return message_content, empty_squads
