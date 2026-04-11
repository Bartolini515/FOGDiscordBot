import os
import discord
from discord.ext import commands
from discord import app_commands
from db.models import Missions, Slots, Squads
import logging
import asyncio
import datetime




logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"

def _message_content(slots_dict: dict[int, tuple[int, str, int | None]], squad: str) -> str:
    header = f"📋 Zapisz się do drużyny **{squad}**:"
    lines = [header]
    for _, (_, label, user) in slots_dict.items():
        mention = f"<@{user}>" if user else "_wolny_"
        status = "✅" if user else "❌"
        lines.append(f"- {label}  {status} - {mention}")
    message_content = "\n".join(lines)
    return message_content

# def _build_mission_embed(slots_dict: dict[int, tuple[int, str, int | None]], squad: str) -> discord.Embed:
#     embed = discord.Embed(
#         title=f"📋 Zapisz się do drużyny: {squad}",
#         color=discord.Color.blue()
#     )
#     for _, (_, label, user_id) in slots_dict.items():
#         if user_id:
#             value = f"<@{user_id}>"
#         else:
#             value = "_wolny_"
#         embed.add_field(name=label, value=value, inline=True)
#     embed.set_footer(text="Kliknij przycisk aby się zapisać")
#     return embed




class SlotSelect(discord.ui.Select):
    # {slot_id: (slot_id, slot, user)}
    def __init__(self, slots: dict[int, tuple[int, str, int | None]], squad: str, mission_id: int, custom_id: str | None = None):
        self.logger = logger

        options = [discord.SelectOption(label=val[1], value=str(key)) for key, val in slots.items() if val[2] is None]
        params = {
            "placeholder": "Wybierz slot",
            "options": options,
        }
        if not options:
            params["options"] = [discord.SelectOption(label="Brak wolnych slotów", value="no_slots")]
            params["disabled"] = True
        if custom_id is not None:
            params["custom_id"] = custom_id
        super().__init__(**params)

        self.slots = slots
        self.custom_id_ = custom_id  # custom_id_ written that way to avoid conflict with parent custom_id property
        self.squad = squad
        self.mission_id = mission_id

    async def callback(self, interaction: discord.Interaction):
        # We will edit potentially MANY messages => don't use interaction.response.edit_message
        await interaction.response.defer(ephemeral=True)

        selected_value = int(self.values[0])
        selected_option = next((option for option in self.options if option.value == str(selected_value)), None)
        selected_label = selected_option.label if selected_option else str(selected_value)
        user_id = interaction.user.id

        cog = interaction.client.get_cog("MissionsCog")

        # Optional: serialize changes per mission to reduce races (single process)
        lock = cog._get_mission_lock(self.mission_id) if cog is not None else None

        async def do_signup():
            # Re-check against current in-memory snapshot (cheap); DB is the real source of truth.
            if selected_value in self.slots and self.slots[selected_value][2] is not None:
                await interaction.followup.send("Ten slot jest już zajęty, wybierz inny.", ephemeral=True)
                return

            logger.info(
                f"User {interaction.user} ({user_id}) is assigning to slot {selected_value} ({selected_label}) in squad {self.squad}"
            )
            
            if debug:
                logger.debug(f"Selected value: {selected_value}, label: {selected_label}")

            # Find previous assignment (so we only rebuild the messages that actually change)
            prev_message_id: int | None = None
            try:
                prev_rows = await Slots.get_by_mission_and_user(interaction.client.db, self.mission_id, user_id)
                if prev_rows:
                    # expected shape used elsewhere in file: rows[1] is message_id
                    prev_message_id = int(prev_rows[1])
            except Exception as e:
                self.logger.exception("Error while checking previous slot assignment", exc_info=e)

            # Move user: remove previous (if any), then assign new
            try:
                if prev_message_id is not None:
                    # Clears the user from whatever slot they currently have in this mission
                    await Slots.remove_user_from_slot(interaction.client.db, self.mission_id, user_id)

                await Slots.assign_user_to_slot(
                    interaction.client.db,
                    interaction.message.id,
                    selected_value,
                    user_id,
                )
            except Exception as e:
                self.logger.exception("Error while assigning user to slot", exc_info=e)
                await interaction.followup.send("Wystąpił błąd podczas zapisywania na slot.", ephemeral=True)
                return

            # Rebuild only affected messages: current + previous (if different)
            if cog is not None and self.mission_id:
                try:
                    await cog._rebuild_signup_message(
                        channel=interaction.channel,
                        message_id=interaction.message.id,
                        mission_id=self.mission_id,
                    )
                    if prev_message_id is not None and prev_message_id != interaction.message.id:
                        await cog._rebuild_signup_message(
                            channel=interaction.channel,
                            message_id=prev_message_id,
                            mission_id=self.mission_id,
                        )
                except Exception as e:
                    logger.exception("Error while rebuilding affected signup messages", exc_info=e)
            else:
                # Fallback: rebuild only the current message
                try:
                    slot_rows = await Slots.get(interaction.client.db, interaction.message.id)
                    slots_dict = {int(r[0]): (int(r[0]), r[1], r[2]) for r in slot_rows}

                    view = discord.ui.View(timeout=None)
                    view.add_item(SlotSelect(slots=slots_dict, custom_id=self.custom_id_, squad=self.squad, mission_id=self.mission_id))
                    view.add_item(SignOutButton(custom_id=f"signout_button_{interaction.message.id}"))
                    await interaction.message.edit(content=_message_content(slots_dict=slots_dict, squad=self.squad), view=view)
                except Exception as e:
                    self.logger.exception("Error while rebuilding current signup message (fallback)", exc_info=e)

            await interaction.followup.send(
                f"Zapisałeś się na {selected_label} do drużyny {self.squad}",
                ephemeral=True,
            )

        if lock is not None:
            async with lock:
                await do_signup()
        else:
            await do_signup()


class SignOutButton(discord.ui.Button):
    def __init__(self, custom_id: str | None = None):
        params = {
            "label": "Wypisz się",
            "style": discord.ButtonStyle.danger,
        }
        if custom_id is not None:
            params["custom_id"] = custom_id
        super().__init__(**params)

        self.custom_id_ = custom_id  # custom_id_ written that way to avoid conflict with parent custom_id property

    async def callback(self, interaction: discord.Interaction):
        rows = await Missions.get_channel(interaction.client.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0] if rows else None
        mission_name = rows[1] if rows else None
        creator_user_id = rows[4] if rows else None
        date = rows[5] if rows else None
        
        rows = await Slots.get_by_mission_and_user(interaction.client.db, mission_id, interaction.user.id)
        if not rows:
            await interaction.response.send_message(f"Nie jesteś zapisany na misję {mission_name}.", ephemeral=True)
            return
        message_id = rows[1]
        
        if datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S") < datetime.datetime.now() + datetime.timedelta(hours=12):
            await interaction.response.send_message("Tylko twórca misji, bądź sztab, może cię wypisać na mniej niż 12 godzin przed jej rozpoczęciem.", ephemeral=True)
            return
        
        # Remove the user from slot and rebuild the view
        await Slots.remove_user_from_slot(interaction.client.db, mission_id, interaction.user.id)
        try:
            cog = interaction.client.get_cog("MissionsCog")
            if cog is not None:
                await cog._rebuild_signup_message(
                    channel=interaction.channel, mission_id=mission_id, message_id=message_id
                )
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            logger.exception("Error while rebuilding signup message after removing user", exc_info=e)

        logger.info(f"User {interaction.user} ({interaction.user.id}) signed out from mission {mission_name} in channel {interaction.channel.id}")
        await interaction.response.send_message(f"Wypisałeś się z misji {mission_name}.", ephemeral=True)




class MissionsCog(commands.Cog):
    """Missions logic and commands."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger
        self._mission_locks: dict[int, asyncio.Lock] = {}
        self._registered_persistent_views: set[int] = set()  # message_ids
        self._scheduled_tasks: set[asyncio.Task] = set()

    def _get_mission_lock(self, mission_id: int) -> asyncio.Lock:
        lock = self._mission_locks.get(mission_id)
        if lock is None:
            lock = asyncio.Lock()
            self._mission_locks[mission_id] = lock
        return lock

    async def _rebuild_signup_message(self, channel: discord.abc.Messageable, message_id: int, mission_id: int):
        """Rebuild one signup message: content + persistent select view."""
        # Avoid fetch; editing a partial message is enough.
        msg = channel.get_partial_message(message_id)

        squad_rows = await Squads.get(self.bot.db, message_id)
        if not squad_rows:
            self.logger.warning(f"Cannot rebuild signup message {message_id}: no squad found")
            return
        squad_name = squad_rows[2]

        slot_rows = await Slots.get(self.bot.db, message_id)
        slots_dict = {int(r[0]): (int(r[0]), r[1], r[2]) for r in slot_rows}

        view = discord.ui.View(timeout=None)
        view.add_item(
            SlotSelect(
                slots=slots_dict,
                custom_id=f"mission_select_{message_id}",
                squad=squad_name,
                mission_id=mission_id,
            )
        )
        view.add_item(SignOutButton(custom_id=f"signout_button_{message_id}"))

        await msg.edit(content=_message_content(slots_dict=slots_dict, squad=squad_name), view=view)

        # IMPORTANT: don't call bot.add_view() here.
        # Persistent views should be registered once (on startup restore or right after creation).

    async def _restore_missions_views(self):
        """Restore persistent mission signup views from the database on bot startup."""
        try:
            if not hasattr(self.bot, "db") or self.bot.db is None:
                return
            logger.info("Restoring mission views from database...")
            rows = await Slots.list(self.bot.db)
            missions_map = {}
            for row in rows:
                message_id = row[0]
                slot_id = row[1]
                slot = row[2]
                user = row[3]
                if message_id not in missions_map:
                    missions_map[message_id] = {}
                missions_map[message_id][int(slot_id)] = (int(slot_id), slot, user)

            if debug:
                logger.debug(missions_map)

            for message_id, data in missions_map.items():
                rows = await Squads.get(self.bot.db, message_id)
                squad_name = rows[2]
                mission_id = rows[1]
                view = discord.ui.View(timeout=None)
                view.add_item(
                    SlotSelect(
                        slots=data,
                        custom_id=f"mission_select_{message_id}",
                        squad=squad_name,
                        mission_id=mission_id,
                    )
                )
                view.add_item(SignOutButton(custom_id=f"signout_button_{message_id}"))
                self.bot.add_view(view, message_id=message_id)
                self._registered_persistent_views.add(int(message_id))
        except Exception as e:
            logger.exception("Error while restoring mission views", exc_info=e)
            pass
        
    
    async def _sleep_until(self, when: datetime.datetime) -> None:
        """Sleep until `when`."""
        delay = (when - datetime.datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

    def _schedule_at(self, when: datetime.datetime, coro_func, *args, **metadata) -> None:
        """Fire `coro_func(*args)` at datetime `when`."""
        async def runner():
            await self._sleep_until(when)
            await coro_func(*args)

        task = asyncio.create_task(runner())
        if metadata: # Attach metadata to taks for later inspection
            task._metadata = metadata
        self._scheduled_tasks.add(task)
        task.add_done_callback(self._scheduled_tasks.discard)
    
    async def _restore_missions_reminders(self):
        """Restore scheduled mission reminders on bot startup."""
        try:
            if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
                return
            logger.info("Restoring mission reminders from database...")
            rows = await Missions.list(self.bot.db)
            for row in rows:
                mission_name = row[1]
                channel_id = row[2]
                date_str = row[5]
                ping_role_id = row[6]
                
                try:
                    date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
                reminder_time = date - datetime.timedelta(hours=1)
                if reminder_time > datetime.datetime.now():
                    self._schedule_at(reminder_time, self._mission_reminder, channel_id, mission_name, date, ping_role_id, channel_id=channel_id)
        except Exception as e:
            logger.exception("Error while restoring mission reminders", exc_info=e)
            pass

    async def _mission_reminder(self, channel_id: int, mission_name: str, when: datetime.datetime, ping_role_id: int) -> None:
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        await channel.send(f"⏰ <@&{ping_role_id}> Misja **{mission_name}** odbędzie się za godzinę! ({when:%Y-%m-%d %H:%M})")
        
    async def _mission_announce(self, channel_id: int, mission_name: str, when: datetime.datetime, ping_role_id: int) -> None:
        channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
        await channel.send(f"🚩 <@&{ping_role_id}> Zapraszam do zapisów na misję **{mission_name}** która odbędzie się {when:%Y-%m-%d}. Szczegóły znajdziecie powyżej!")

    async def cog_load(self):
        await self._restore_missions_views()
        await self._restore_missions_reminders()




    # =============== Mission Overall Section =================
    # /misja_stworz
    @app_commands.command(
        name="misja_stworz",
        description="Utwórz instancję misji w bieżącym kanale.",
        extras={"category": "Misje"}
    )
    @app_commands.guild_only()
    @app_commands.describe(
        nazwa="Nazwa misji",
        data="Data i czas misji np. 2026-01-08 18:30 (YYYY-MM-DD HH:MM)",
        czy_ping="Czy dać ping na misję?",
    )
    async def misja_stworz(self, interaction: discord.Interaction, nazwa: str, data: str, czy_ping: bool):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        # Permission check: allow if user is explicitly allowed OR has an allowed role OR is admin
        allowed = self.bot.permissions.get("mission_makers", [])
        
        if debug:
            logger.debug(f"Allowed mission makers: {allowed}")

        is_allowed_user = interaction.user.id in allowed
        is_allowed_role = any(
            (r.id in allowed)
            for r in interaction.user.roles
        )
        
        if debug:
            logger.debug(f"Permission check - is_allowed_user: {is_allowed_user}, is_allowed_role: {is_allowed_role}")

        if not (is_allowed_user or is_allowed_role or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Nie masz uprawnień do tworzenia misji.", ephemeral=True)
            return
        
        # Validate correct channel for mission creation if configured
        scheduled_missions_channel_id = self.bot.channels.get("scheduled_missions_channel_id")
        if scheduled_missions_channel_id:
            channel = interaction.channel
            
            if isinstance(channel, discord.Thread):
                channel_id = channel.parent.id
            else:
                channel_id = channel.id
                
            if channel_id != scheduled_missions_channel_id:
                await interaction.response.send_message("Nieodpowiedni kanał. Misje muszą być tworzone w kanale od misji.", ephemeral=True)
                return
        
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if rows: # Validation of existing mission in channel
            await interaction.response.send_message("W tym kanale już istnieje misja.", ephemeral=True)
            return
        
        if data: # Validate date format
            try:
                datetime_obj = datetime.datetime.strptime(data, "%Y-%m-%d %H:%M")
                data = datetime_obj.isoformat(sep=' ')
            except ValueError:
                await interaction.response.send_message("Niepoprawny format daty. Użyj YYYY-MM-DD HH:MM.", ephemeral=True)
                return
            
        if datetime_obj < datetime.datetime.now(): # Validate date is in the future
            await interaction.response.send_message("Data misji musi być w przyszłości.", ephemeral=True)
            return
        
        if czy_ping:
            ping_role_id = self.bot.roles.get("mission_ping_role_id", 0)
            
            reminder_time = datetime_obj - datetime.timedelta(hours=1)
            self._schedule_at(reminder_time, self._mission_reminder, interaction.channel.id, nazwa, datetime_obj, ping_role_id, channel_id=interaction.channel.id)
            
            announce_time = datetime.datetime.now() + datetime.timedelta(hours=1)
            self._schedule_at(announce_time, self._mission_announce, interaction.channel.id, nazwa, datetime_obj, ping_role_id, channel_id=interaction.channel.id) 
        
        # Create mission entry in DB
        await Missions.create(
            self.bot.db,
            name=nazwa,
            channel_id=interaction.channel.id,
            creator_user_id=interaction.user.id,
            date=data,
        )
        logger.info(f"User {interaction.user} ({interaction.user.id}) created mission {nazwa} in channel {interaction.channel.id}")
        await interaction.response.send_message(f"Utworzono instancję misji o nazwie {nazwa} w tym kanale. Ten kanał służy teraz jako kanał misji."
                                                "\nZa godzinę zostanie wysłane powiadomienie o jej stworzeniu.", ephemeral=True)
        
    # /misja_anuluj
    @app_commands.command(
        name="misja_anuluj",
        description="Anuluje misję w bieżącym kanale i usuwa wszystkie powiązane dane.",
        extras={"category": "Misje"},
    )
    @app_commands.guild_only()
    async def misja_anuluj(self, interaction: discord.Interaction):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0]
        creator_user_id = rows[4]
        
        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
            await interaction.response.send_message("Tylko twórca misji może anulować misję.", ephemeral=True)
            return
        
        # Cancel scheduled tasks related to this mission
        for task in list(self._scheduled_tasks):
            metadata = getattr(task, "_metadata", {})
            if metadata.get("channel_id") == interaction.channel.id:
                task.cancel()
                self._scheduled_tasks.discard(task)
        
        # Cleanup views and messages
        rows = await Squads.get_by_mission(self.bot.db, mission_id)
        for row in rows:
            message_id = row[0]
            try:
                msg = await interaction.channel.fetch_message(message_id)
                await msg.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass
        
        # Delete mission from DB (cascades to squads and slots)
        await Missions.delete(self.bot.db, mission_id)
        logger.info(f"User {interaction.user} ({interaction.user.id}) canceled mission {mission_id} in channel {interaction.channel.id}")
        await interaction.response.send_message("Misja i wszystkie powiązane dane zostały usunięte.", ephemeral=True)
        
    # /misja_edytuj
    @app_commands.command(
        name="misja_edytuj",
        description="Edytuje nazwę lub datę misji w bieżącym kanale.",
        extras={"category": "Misje"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        nazwa="Nowa nazwa misji (opcjonalne)",
        data="Nowa data i czas misji np. 2026-01-08 18:30 (YYYY-MM-DD HH:MM) (opcjonalne)",
    )
    async def misja_edytuj(self, interaction: discord.Interaction, nazwa: str = None, data: str = None):
        if not nazwa and not data: # Validation of inputs
            await interaction.response.send_message("Musisz podać nową nazwę lub datę misji.", ephemeral=True)
            return
        
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0]
        creator_user_id = rows[4]
        nazwa = nazwa if nazwa else rows[1]
        data = data if data else rows[5]
        
        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
            await interaction.response.send_message("Tylko twórca misji może edytować misję.", ephemeral=True)
            return
        
        # Update mission in DB
        await Missions.update(self.bot.db, mission_id=mission_id, name=nazwa, date=data)
        logger.info(f"User {interaction.user} ({interaction.user.id}) edited mission {mission_id} in channel {interaction.channel.id}")
        await interaction.response.send_message("Misja została zaktualizowana.", ephemeral=True)
    
    
    
    
    # =============== Mission Signup Section =================
    # /misja_zapisy_stworz
    @app_commands.command(
        name="misja_zapisy_stworz",
        description="Utwórz wiadomość do zapisów na misję (musi być w kanale misji)",
        extras={"category": "Misje"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        druzyna="Nazwa drużyny",
        sloty="Lista slotów oddzielona średnikami (np. strzelec;medyk;KM)",
    )
    async def misja_zapisy_stworz(self, interaction: discord.Interaction, druzyna: str, sloty: str):
        slots = [s.strip() for s in sloty.split(";") if s.strip()]
        
        # Validation of inputs
        if len(slots) > 25:
            await interaction.response.send_message("Maksymalna liczba slotów to 25.", ephemeral=True)
            return
        
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0]
        creator_user_id = rows[4]
        
        
        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
            await interaction.response.send_message("Tylko twórca misji może tworzyć wiadomości do zapisów.", ephemeral=True)
            return

        
        # Construct slots dict for SlotSelect
        max_id = await Slots.max_id(self.bot.db)
        slots_dict = {i: (i, slot, None) for i, slot in enumerate(slots, start=max_id[0] + 1 if max_id[0] else 0)}
        
        view = discord.ui.View()
        select = SlotSelect(slots=slots_dict, squad=druzyna, mission_id=mission_id)
        view.add_item(select)
        
        await interaction.response.send_message(content=_message_content(slots_dict=slots_dict, squad=druzyna), view=view)
        message = await interaction.original_response()

        # make the view persistent using the message id as part of the custom_id
        persistent_view = discord.ui.View(timeout=None)
        persistent_view.add_item(SlotSelect(slots_dict, custom_id=f"mission_select_{message.id}", squad=druzyna, mission_id=mission_id))
        persistent_view.add_item(SignOutButton(custom_id=f"signout_button_{message.id}"))
        await message.edit(view=persistent_view)

        # Register persistent view once for this message
        if message.id not in self._registered_persistent_views:
            self.bot.add_view(persistent_view, message_id=message.id)
            self._registered_persistent_views.add(message.id)

        logger.info(f"User {interaction.user} ({interaction.user.id}) created signup message for mission {mission_id} in channel {interaction.channel.id}")
        await Squads.create(self.bot.db, mission_id, message.id, druzyna)
        await Slots.create(self.bot.db, mission_id, message.id, slots)
        
    # # /zapisy_edytuj
    # @app_commands.command(
    #     name="zapisy_edytuj",
    #     description="Edytuje wiadomość do zapisów na misję (musi być w kanale misji). System postara się zachować istniejące zapisy zgodnie z obecną kolejnością slotów i ich nazwami.",
    # )
    # @app_commands.guild_only()
    # @app_commands.describe(
    #     sloty="Lista slotów oddzielona średnikami (np. strzelec;medyk;KM)",
    #     druzyna="Nazwa drużyny slotów do edycji. Jeżeli są 2 drużyny o takiej samej nazwie należy użyć message_id", 
    #     message_id="ID wiadomości do edycji (alternatywa)"
    # )
    # async def zapisy_edytuj(self, interaction: discord.Interaction, sloty: str, druzyna: str = None, message_id: int = None):
    #     slots = [s.strip() for s in sloty.split(";") if s.strip()]
    #     # Validation of inputs
    #     if not druzyna:
    #         await interaction.response.send_message("Nazwa drużyny nie może być pusta.", ephemeral=True)
    #         return
    #     if not slots:
    #         await interaction.response.send_message("Brak poprawnych slotów.", ephemeral=True)
    #         return
    #     if len(slots) > 25:
    #         await interaction.response.send_message("Maksymalna liczba slotów to 25.", ephemeral=True)
    #         return
    #     if not druzyna and not message_id:
    #         await interaction.response.send_message("Musisz podać nazwę drużyny lub ID wiadomości do edycji.", ephemeral=True)
    #         return
        
    #     if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
    #         return
        
    #     rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
    #     if not rows: # Validation of mission existence
    #         await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
    #         return
    #     mission_id = rows[0]
    #     creator_user_id = rows[4]
        
    #     if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
    #         await interaction.response.send_message("Tylko twórca misji może edytować wiadomości do zapisów.", ephemeral=True)
    #         return
        
    #     if not message_id:
    #         rows = await Squads.get_by_name(self.bot.db, druzyna)
    #         if not rows:
    #             await interaction.response.send_message(f"Nie znaleziono drużyny o podanej nazwie {druzyna}.", ephemeral=True)
    #             return
    #         message_id = rows[0]
        
    # /misja_zapisy_usun
    @app_commands.command(
        name="misja_zapisy_usun",
        description="Usuwa wiadomość do zapisów na misję (musi być w kanale misji).",
        extras={"category": "Misje"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        druzyna="Nazwa drużyny do usunięcia",
        message_id="ID wiadomości do usunięcia (alternatywa)",
    )
    async def misja_zapisy_usun(self, interaction: discord.Interaction, druzyna: str, message_id: int = None):
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0]
        creator_user_id = rows[4]
        
        if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
            await interaction.response.send_message("Tylko twórca misji może usuwać wiadomości do zapisów.", ephemeral=True)
            return
        
        if not message_id:
            rows = await Squads.get_by_name(self.bot.db, mission_id, druzyna)
            if not rows:
                await interaction.response.send_message(f"Nie znaleziono drużyny o podanej nazwie {druzyna}.", ephemeral=True)
                return
            message_id = rows[0]
        
        # Delete signup message from channel
        try:
            msg = await interaction.channel.fetch_message(message_id)
            await msg.delete()
        except discord.NotFound:
            pass
        except discord.Forbidden:
            pass
        
        # Delete squad and slots from DB
        await Squads.delete(self.bot.db, message_id)
        await Slots.delete_by_id_message(self.bot.db, message_id)
        
        logger.info(f"User {interaction.user} ({interaction.user.id}) deleted signup message {message_id} for mission {mission_id} in channel {interaction.channel.id}")
        await interaction.response.send_message("Wiadomość do zapisów została usunięta.", ephemeral=True)
        
    # /misja_zapisy_wypisz
    @app_commands.command(
        name="misja_zapisy_wypisz",
        description="Wypisuje użytkownika z misji.",
        extras={"category": "Misje"},
    )
    @app_commands.guild_only()
    @app_commands.describe(
        uzytkownik="Użytkownik do wypisania",
    )
    async def misja_zapisy_wypisz(self, interaction: discord.Interaction, uzytkownik: discord.Member):
            
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        
        rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
        if not rows: # Validation of mission existence
            await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
            return
        mission_id = rows[0] if rows else None
        mission_name = rows[1] if rows else None
        creator_user_id = rows[4] if rows else None
        
        # Only admins or the mission creator can remove someone else.
        is_admin = interaction.user.guild_permissions.administrator
        is_creator = (interaction.user.id == creator_user_id)

        if not (is_admin or is_creator):
            logger.info(
            "User %s (%s) attempted to remove another user %s (%s) from mission (%s) without permission.",
            interaction.user, interaction.user.id, uzytkownik, uzytkownik.id, mission_name
            )
            await interaction.response.send_message(
            "Możesz wypisać tylko siebie, chyba że jesteś administratorem lub twórcą misji.",
            ephemeral=True,
            )
            return
        
        rows = await Slots.get_by_mission_and_user(self.bot.db, mission_id, uzytkownik.id)
        if not rows:
            await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} nie jest zapisany na misję {mission_name}.", ephemeral=True)
            return
        message_id = rows[1]
        
        # Remove the user from slot and rebuild the view
        await Slots.remove_user_from_slot(self.bot.db, mission_id, uzytkownik.id)
        try:
            await self._rebuild_signup_message(
                channel=interaction.channel, mission_id=mission_id, message_id=message_id
            )
        except (discord.NotFound, discord.Forbidden):
            pass
        except Exception as e:
            logger.exception("Error while rebuilding signup message after removing user", exc_info=e)

        logger.info(f"User {interaction.user} ({interaction.user.id}) removed user {uzytkownik} ({uzytkownik.id}) from mission {mission_name} in channel {interaction.channel.id}")
        await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} został wypisany z misji {mission_name}.", ephemeral=True)
        
    # # /misja_zapisy_wpisz
    # @app_commands.command(
    #     name="misja_zapisy_wpisz",
    #     description="Wpisuje użytkownika do misji.",
    #     extras={"category": "Misje"},
    # )
    # @app_commands.guild_only()
    # @app_commands.describe(
    #     uzytkownik="Użytkownik do wpisania",
        
    # )
    # async def misja_zapisy_wpisz(self, interaction: discord.Interaction, uzytkownik: discord.Member, druzyna: str, slot: str):
    #     if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
    #         return
        
    #     rows = await Missions.get_channel(self.bot.db, interaction.channel.id)
    #     if not rows: # Validation of mission existence
    #         await interaction.response.send_message("Ta komenda może być użyta tylko w kanale misji.", ephemeral=True)
    #         return
    #     mission_id = rows[0]
    #     creator_user_id = rows[4]
        
    #     if creator_user_id != interaction.user.id and not interaction.user.guild_permissions.administrator: # Validation of permissions
    #         await interaction.response.send_message("Tylko twórca misji może wpisywać użytkowników do zapisów.", ephemeral=True)
    #         return
        
    #     # Get the message_id for the specified team
    #     rows = await Squads.get_by_name(self.bot.db, mission_id, druzyna)
    #     if not rows:
    #         await interaction.response.send_message(f"Nie znaleziono drużyny o podanej nazwie {druzyna}.", ephemeral=True)
    #         return
    #     message_id = rows[0]
        
        

async def setup(bot:commands.Bot):
    await bot.add_cog(MissionsCog(bot))