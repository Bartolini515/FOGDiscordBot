import os
import discord
from discord.ext import commands
from discord import app_commands
from db.models import Attendance, Slots, Missions, Squads
import logging

logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"

class AttendanceCog(commands.Cog):
    """Attendance related commands and listeners."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot

    
    # TODO: Test this
    # /misja_obecnosc
    @app_commands.command(
        name="misja_obecnosc",
        description="Wprowadza obecność użytkowników na misji.",
        extras={"category": "Obecność"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        nieobecni="Lista użytkowników nieobecnych na misji (wzór: @użytkownik @użytkownik ...)."
    )
    async def misja_obecnosc(self, interaction: discord.Interaction, nieobecni: str | None = None):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0]
        mission_name = rows[1]
        mission_date = rows[5].split(" ")[0]
        creator_user_id = rows[4]
        
        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
            await interaction.response.send_message("Tylko twórca misji może anulować misję.", ephemeral=True)
            return
        
        absent_users = [u[2:-1] for u in nieobecni.split() if u.startswith("<@") and u.endswith(">")] if nieobecni else []
        
        squad_map = {}
        rows = await Squads.get_by_mission(self.bot.db, mission_id)
        if not rows:
            await interaction.response.send_message("Brak zapisanych drużyn na tę misję.", ephemeral=True)
            return
        for row in rows:
            squad_map[row[0]] = row[2] # message_id: name
            
        slots_map = {} # message_id: [(name, user_id)]
        rows = await Slots.get_by_mission(self.bot.db, mission_id)
        if not rows:
            await interaction.response.send_message("Brak zapisanych użytkowników na tę misję.", ephemeral=True)
            return
        for row in rows:
            if debug:
                logger.debug(f"Slot row: {row}")
            if row[0] not in slots_map:
                slots_map[row[0]] = []
            slots_map[row[0]].append((row[2], row[3])) # (name, user_id)
            
        if debug:
            logger.debug(f"Slots map for mission {mission_name} ({mission_date}): {slots_map}")
        present_users = []
        for mid, users in slots_map.items():
            for label, user in users:
                if user and str(user) not in absent_users:
                    present_users.append(int(user))
        if present_users:
            if debug:
                logger.debug(f"Recording attendance for mission {mission_name} ({mission_date}): Present users: {present_users}, Absent users: {absent_users}")
            await Attendance.add_mass_attendance(self.bot.db, present_users, mission_date)
            self.bot.dispatch("attendance", present_users)
        
        
        message_content = f"Obecność na misji {mission_name} ({mission_date}):\n"
        for squad in squad_map.items():
            squad_message_id = squad[0]
            squad_name = squad[1]
            squad_members = slots_map.get(squad_message_id, [])
            if squad_members:
                header = f"Obecność **{squad_name}**:"
                lines = [header]
                for label, user in squad_members:
                    mention = f"<@{user}>" if user else "*Brak*"
                    status = "✅" if user in present_users else "❌"
                    lines.append(f"- {label} - {mention} {status}")
                message_content += "\n".join(lines) + "\n"
            else:
                await interaction.channel.send(f"Drużyna **{squad_name}** nie ma obecnych członków.")
                
        await interaction.channel.send(message_content)
        channel = self.bot.get_channel(self.bot.channels["attendance_channel_id"])
        await channel.send(message_content)
        await interaction.response.send_message("Obecność została zapisana.", ephemeral=True)
        logger.info(f"Attendance for mission {mission_name} ({mission_date}) recorded by {interaction.user.name}.")
        
    #TODO: Test this
    #/obecnosc_sprawdz
    @app_commands.command(
        name="obecnosc_sprawdz",
        description="Sprawdza statystykę obecności użytkownika w misjach.",
        extras={"category": "Obecność"},
    )
    @app_commands.guild_only()
    @app_commands.describe(uzytkownik="Użytkownik, którego obecność chcesz sprawdzić.")
    async def obecnosc_sprawdz(self, interaction: discord.Interaction, uzytkownik: discord.User = None):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        user_id = uzytkownik.id if uzytkownik else interaction.user.id
        attendance_record = await Attendance.get_by_user(self.bot.db, user_id)
        if not attendance_record:
            await interaction.response.send_message("Brak danych o obecności tego użytkownika.", ephemeral=True)
            return
        last_mission_date = attendance_record[1]
        all_time_missions = attendance_record[2]
        
        user = interaction.guild.get_member(user_id)
        username = user.name if user else f"Użytkownik {user_id}"
        
        embed = discord.Embed(
            title=f"Obecność użytkownika {username}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Ostatnia misja", value=last_mission_date if last_mission_date else "Brak danych", inline=False)
        embed.add_field(name="Łączna liczba misji", value=str(all_time_missions), inline=False)

        await interaction.response.send_message(embed=embed)
    
    # TODO: Test this
    #/obecnosc_ranking
    @app_commands.command(
        name="obecnosc_ranking",
        description="Pokazuje ranking obecności użytkowników w misjach.",
        extras={"category": "Obecność"},
    )
    @app_commands.guild_only()
    @app_commands.describe(limit="Liczba użytkowników do wyświetlenia w rankingu (domyślnie 10).")
    async def obecnosc_ranking(self, interaction: discord.Interaction, limit: int = 10):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        leaderboard = await Attendance.get_leaderboard(self.bot.db, limit)
        if not leaderboard:
            await interaction.response.send_message("Brak danych o obecności użytkowników.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Ranking obecności w misjach",
            color=discord.Color.green()
        )
        description_lines = []
        for rank, (user_id, last_mission_date, all_time_missions) in enumerate(leaderboard, start=1):
            user = interaction.guild.get_member(user_id)
            username = user.name if user else f"Użytkownik {user_id}"
            description_lines.append(f"**#{rank}** - {username}: {all_time_missions} misji (ostatnia: {last_mission_date if last_mission_date else 'Brak danych'})")
        embed.description = "\n".join(description_lines)
        await interaction.response.send_message(embed=embed)

async def setup(bot:commands.Bot):
    await bot.add_cog(AttendanceCog(bot))