import os
import discord
import os
import discord
from discord.ext import commands
from discord import app_commands
from db.models import Trainings, TrainingSigned
import logging
import asyncio
import datetime


logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"


def _training_message_content(training_name: str, date_str: str | None, user_ids: list[int]) -> str:
    header = f"📋 Zapisz się na szkolenie **{training_name}** {date_str}".strip()
    lines = [header]
    if not user_ids:
        lines.append("_Brak zapisanych._")
    else:
        for user_id in user_ids:
            lines.append(f"- <@{user_id}>")
    return "\n".join(lines)


class TrainingToggleButton(discord.ui.Button):
    def __init__(self, training_id: int):
        super().__init__(
            label="Zapisz / Wypisz",
            style=discord.ButtonStyle.primary,
            custom_id=f"training_toggle_{training_id}",
        )
        self.training_id = training_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TrainingsCog")
        if cog is None:
            await interaction.response.send_message("Ten moduł nie jest załadowany.", ephemeral=True)
            return
        await cog._handle_toggle(interaction, training_id=self.training_id)


class TrainingSignupView(discord.ui.View):
    def __init__(self, training_id: int):
        super().__init__(timeout=None)
        self.add_item(TrainingToggleButton(training_id=training_id))


class TrainingsCog(commands.Cog):
    """Trainings logic and commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._training_locks: dict[int, asyncio.Lock] = {}
        self._registered_persistent_views: set[int] = set()  # message_ids

    def _get_training_lock(self, training_id: int) -> asyncio.Lock:
        lock = self._training_locks.get(training_id)
        if lock is None:
            lock = asyncio.Lock()
            self._training_locks[training_id] = lock
        return lock

    async def cog_load(self):
        await self._restore_training_views()

    async def _restore_training_views(self):
        try:
            if not hasattr(self.bot, "db") or self.bot.db is None:
                return
            logger.info("Restoring training signup views from database...")
            rows = await Trainings.list(self.bot.db)
            for row in rows:
                training_id = int(row[0])
                message_id = row[3]
                if message_id is None:
                    continue
                message_id = int(message_id)
                if message_id in self._registered_persistent_views:
                    continue
                view = TrainingSignupView(training_id=training_id)
                self.bot.add_view(view, message_id=message_id)
                self._registered_persistent_views.add(message_id)
        except Exception as e:
            logger.exception("Error while restoring training views", exc_info=e)

    async def _rebuild_training_message(self, channel: discord.abc.Messageable, message_id: int, training_id: int):
        msg = channel.get_partial_message(message_id)

        training_row = await Trainings.get(self.bot.db, training_id)
        if not training_row:
            logger.warning(f"Cannot rebuild training message {message_id}: training {training_id} not found")
            return

        training_name = training_row[1]
        training_date = training_row[6]

        signed_rows = await TrainingSigned.list_by_training(self.bot.db, training_id)
        user_ids = [int(r[2]) for r in signed_rows if r[2] is not None]

        view = TrainingSignupView(training_id=training_id)
        await msg.edit(content=_training_message_content(training_name, training_date, user_ids), view=view)

    async def _handle_toggle(self, interaction: discord.Interaction, training_id: int):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        # Edit the message after DB write.
        await interaction.response.defer(ephemeral=True)

        lock = self._get_training_lock(training_id)
        async with lock:
            try:
                is_signed = await TrainingSigned.is_signed(self.bot.db, training_id, interaction.user.id)
                if is_signed:
                    await TrainingSigned.sign_out(self.bot.db, training_id, interaction.user.id)
                    action_text = "Wypisano Cię ze szkolenia."
                else:
                    await TrainingSigned.sign_up(self.bot.db, training_id, interaction.user.id)
                    action_text = "Zapisano Cię na szkolenie."
            except Exception as e:
                logger.exception("Error while toggling training signup", exc_info=e)
                await interaction.followup.send("Wystąpił błąd podczas zapisu.", ephemeral=True)
                return

            try:
                await self._rebuild_training_message(
                    channel=interaction.channel,
                    message_id=interaction.message.id,
                    training_id=training_id,
                )
            except Exception as e:
                logger.exception("Error while rebuilding training message", exc_info=e)

        await interaction.followup.send(action_text, ephemeral=True)

    # =============== Training Section =================
    # TODO: Test this
    # /szkolenie_stworz
    @app_commands.command(
        name="szkolenie_stworz",
        description="Utwórz szkolenie i wiadomość do zapisów w bieżącym kanale.",
        extras={"category": "Szkolenia"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        nazwa="Nazwa szkolenia",
        data="Data szkolenia np. 2026-01-08 18:30:00 (YYYY-MM-DD HH:MM:SS)",
    )
    async def szkolenie_stworz(self, interaction: discord.Interaction, nazwa: str, data: str):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            return

        # Permission check: allow if user is explicitly allowed OR has an allowed role OR is admin
        allowed = self.bot.permissions.get("trainers", [])

        is_allowed_user = str(interaction.user.id) in allowed
        is_allowed_role = any(
            (str(r.id) in allowed)
            for r in interaction.user.roles
        )

        if not (is_allowed_user or is_allowed_role or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Nie masz uprawnień do tworzenia szkoleń.", ephemeral=True)
            return

        rows = await Trainings.get_channel(self.bot.db, interaction.channel.id)
        if rows:
            await interaction.response.send_message("W tym kanale już istnieje szkolenie.", ephemeral=True)
            return

        if data: # Validate date format
            try:
                datetime_obj = datetime.datetime.strptime(data, "%Y-%m-%d %H:%M:%S")
                data = datetime_obj.isoformat(sep=' ')
            except ValueError:
                await interaction.response.send_message("Niepoprawny format daty. Użyj YYYY-MM-DD HH:MM:SS.", ephemeral=True)
                return

        training_id = await Trainings.create(
            self.bot.db,
            channel_id=interaction.channel.id,
            name=nazwa,
            creator_user_id=interaction.user.id,
            date=data,
        )

        view = TrainingSignupView(training_id=training_id)
        await interaction.response.send_message(
            content=_training_message_content(nazwa, data, []),
            view=view,
        )
        message = await interaction.original_response()

        await Trainings.set_message_id(self.bot.db, training_id=training_id, message_id=message.id)

        if message.id not in self._registered_persistent_views:
            self.bot.add_view(view, message_id=message.id)
            self._registered_persistent_views.add(int(message.id))

        logger.info(
            f"User {interaction.user} ({interaction.user.id}) created training {training_id} ({nazwa}) in channel {interaction.channel.id}"
        )

    # TODO: Test this
    # /szkolenie_anuluj
    @app_commands.command(
        name="szkolenie_anuluj",
        description="Anuluj szkolenie w bieżącym kanale (usuwa też wiadomość zapisów).",
        extras={"category": "Szkolenia"},
    )
    @app_commands.guild_only()
    async def szkolenie_anuluj(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            return

        rows = await Trainings.get_channel(self.bot.db, interaction.channel.id)
        if not rows:
            await interaction.response.send_message("W tym kanale nie ma szkolenia.", ephemeral=True)
            return

        training_id = int(rows[0])
        creator_user_id = rows[5]
        message_id = rows[3]

        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tylko twórca szkolenia może je anulować.", ephemeral=True)
            return

        if message_id is not None:
            try:
                msg = interaction.channel.get_partial_message(int(message_id))
                await msg.delete()
            except Exception:
                pass

        await Trainings.delete(self.bot.db, training_id)
        logger.info(
            f"User {interaction.user} ({interaction.user.id}) canceled training {training_id} in channel {interaction.channel.id}"
        )
        await interaction.response.send_message("Szkolenie zostało anulowane.", ephemeral=True)
        
    # TODO: Test this
    # /szkolenie_obecnosc
    @app_commands.command(
        name="szkolenie_obecnosc",
        description="Zatwierdza obecność użytkowników na szkoleniu oraz nadaje im rolę.",
        extras={"category": "Szkolenia"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        rola="Rola do nadania obecnym uczestnikom.",
        nieobecni="Użytkownicy nieobecni na szkoleniu (oddziel ich spacją).",
    )
    async def szkolenie_obecnosc(self, interaction: discord.Interaction, rola: discord.Role, nieobecni: str | None = None):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            return

        rows = await Trainings.get_channel(self.bot.db, interaction.channel.id)
        if not rows:
            await interaction.response.send_message("W tym kanale nie ma szkolenia.", ephemeral=True)
            return

        training_id = int(rows[0])
        training_name = rows[1]
        training_date = rows[6]
        creator_user_id = rows[5]

        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Tylko twórca szkolenia może zatwierdzać obecność.", ephemeral=True)
            return

        absent_users = [u[2:-1] for u in nieobecni.split() if u.startswith("<@") and u.endswith(">")] if nieobecni else []

        rows = await TrainingSigned.list_by_training(self.bot.db, training_id)
        if not rows:
            await interaction.response.send_message("Brak zapisanych użytkowników na to szkolenie.", ephemeral=True)
            return

        present_users = [int(r[2]) for r in rows if str(r[2]) not in absent_users]
        for user_id in present_users:
            member = interaction.guild.get_member(user_id)
            if member:
                try:
                    await member.add_roles(rola, reason=f"Obecność na szkoleniu {training_name}")
                except Exception as e:
                    logger.warning(f"Nie udało się nadać rolę użytkownikowi {user_id}: {e}")
                    continue

        all_user_ids = [int(r[2]) for r in rows if r[2] is not None]

        lines = [f"📌 Obecność na szkoleniu **{training_name}** {training_date}".strip()]
        for uid in all_user_ids:
            status = "✅ obecny" if str(uid) not in absent_users else "❌ nieobecny"
            lines.append(f"- <@{uid}> — {status}")
        message_content = "\n".join(lines)
        
        await interaction.channel.send(message_content)
        channel = self.bot.get_channel(self.bot.channels["attendance_channel_id"])
        await channel.send(message_content)

        await interaction.response.send_message("Obecność została zapisana, a rola nadana obecnym uczestnikom.", ephemeral=True)
        logger.info(f"Attendance for training {training_name} ({training_date}) recorded by {interaction.user.name}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(TrainingsCog(bot))
    