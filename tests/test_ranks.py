from types import SimpleNamespace

from Cogs.Ranks import RanksCog
from db.models.attendance import Attendance
from db.models.users import Users


class FakeMember:
    def __init__(self):
        self.added_roles = []
        self.removed_roles = []

    async def add_roles(self, role):
        self.added_roles.append(role)

    async def remove_roles(self, role):
        self.removed_roles.append(role)

    async def send(self, message):
        pass


class FakeGuild:
    def __init__(self, member, roles):
        self.member = member
        self.roles = roles

    def get_member(self, user_id):
        return self.member

    def get_role(self, role_id):
        return self.roles.get(role_id)


async def test_attendance_listener_promotes_user_at_next_rank_threshold(database):
    user_id = 1201
    await Users.add_user(database, user_id, "operator")
    await Attendance.add_mass_attendance(database, [user_id] * 10, "2030-03-01")

    member = FakeMember()
    recruit_role = object()
    operator_role = object()
    bot = SimpleNamespace(
        db=database,
        guild_id=9001,
        roles={
            "recruit_role_id": 1458467452278149338,
            "operator_role_id": 0,
        },
        get_guild=lambda guild_id: FakeGuild(
            member,
            {1458467452278149338: recruit_role, 1458466593737801739: operator_role},
        ),
    )

    await RanksCog(bot).on_attendance([user_id])

    assert (await Users.get_user(database, user_id))[4] == 2
    assert member.removed_roles == [recruit_role]
    assert member.added_roles == [operator_role]
