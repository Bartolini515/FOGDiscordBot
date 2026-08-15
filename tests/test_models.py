from db.database import Database
from db.models import Attendance, Missions, Ranks, Slots, Squads, TicketTypes, Tickets, Users, Warns


async def test_user_moves_between_slots_within_one_mission(database: Database):
    await Users.add_user(database, 1001, "creator")
    await Users.add_user(database, 1002, "operator")
    await Missions.create(database, 2001, "Operation North", 1001, "2030-01-02 18:00:00")
    mission = await Missions.get_channel(database, 2001)
    mission_id = mission[0]

    await Squads.create(database, mission_id, 3001, "Alpha")
    await Squads.create(database, mission_id, 3002, "Bravo")
    await Slots.create(database, mission_id, 3001, ["Leader", "Medic"])
    await Slots.create(database, mission_id, 3002, ["Leader", "Rifleman"])

    alpha_slot_id = (await Slots.get(database, 3001))[0][0]
    bravo_slot_id = (await Slots.get(database, 3002))[0][0]
    await Slots.assign_user_to_slot(database, 3001, str(alpha_slot_id), 1002)
    await Slots.assign_user_to_slot(database, 3002, str(bravo_slot_id), 1002)

    alpha_slots = await Slots.get(database, 3001)
    bravo_slots = await Slots.get(database, 3002)
    assert [row[2] for row in alpha_slots] == [None, None]
    assert [row[2] for row in bravo_slots] == [1002, None]

    await Slots.remove_user_from_slot(database, mission_id, 1002)
    assert all(row[3] is None for row in await Slots.get_by_mission(database, mission_id))


async def test_deleting_mission_cascades_to_squads_and_slots(database: Database):
    await Users.add_user(database, 1101, "creator")
    await Missions.create(database, 2101, "Operation South", 1101, "2030-02-03 19:00:00")
    mission_id = (await Missions.get_channel(database, 2101))[0]
    await Squads.create(database, mission_id, 3101, "Alpha")
    await Slots.create(database, mission_id, 3101, ["Leader"])

    await Missions.delete(database, mission_id)

    assert await Squads.get_by_mission(database, mission_id) == []
    assert await Slots.get_by_mission(database, mission_id) == []


async def test_attendance_increments_and_next_rank_uses_threshold_order(database: Database):
    await Users.add_user(database, 1201, "operator")

    await Attendance.add_mass_attendance(database, [1201], "2030-03-01")
    await Attendance.add_mass_attendance(database, [1201], "2030-03-08")

    assert await Attendance.get_by_user(database, 1201) == (1201, "2030-03-08", 2)
    next_rank = await Ranks.get_next_rank(database, 0)
    assert next_rank[1] == "Operator I"
    assert next_rank[3] == 10


async def test_ticket_status_lifecycle_and_warning_counter(database: Database):
    await Users.add_user(database, 1301, "member")
    custom_type_id = await TicketTypes.get_id_by_name(database, "custom")
    assert custom_type_id is not None

    await Tickets.create(database, 2301, 1301, custom_type_id, "Need help")
    ticket = await Tickets.get_by_channel(database, 2301)
    assert ticket[1] == 2301
    assert ticket[2] == 1301
    assert ticket[3] is not None
    assert ticket[4:] == (1, custom_type_id, "Need help")

    await Tickets.update_status(database, 2301, 0)
    assert (await Tickets.get_by_channel(database, 2301))[4] == 0
    await Tickets.delete_by_channel(database, 2301)
    assert await Tickets.get_by_channel(database, 2301) is None

    await Warns.create(database, 1301, "First warning")
    await Warns.create(database, 1301, "Second warning")
    assert (await Users.get_user(database, 1301))[8] == 2

    first_warning_id = (await Warns.get_by_user_id(database, 1301))[0][0]
    await Warns.delete(database, first_warning_id)
    assert (await Users.get_user(database, 1301))[8] == 1
