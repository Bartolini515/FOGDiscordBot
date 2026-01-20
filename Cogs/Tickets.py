import os
import io
import json
import logging
import html
import discord
from discord.ext import commands
from discord import app_commands

from ticket import core
from ticket.ui import (
    TicketCreateButtonView,
    TicketCreateSelectView,
    TicketOpenView,
    TicketClosedView,
)


logger = logging.getLogger("fogbot")
debug = os.getenv("DEBUG") == "True"


class TicketsCog(commands.Cog):
    """Tickets logic and commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._registered_create_views: set[int] = set()  # message_ids
        self._registered_ticket_views: set[int] = set()  # channel_ids

    async def cog_load(self):
        await self._restore_ticket_create_messages()
        await self._restore_ticket_views()

    def _is_ticket_admin(self, user: discord.Member) -> bool:
        return user.guild_permissions.administrator

    async def _restore_ticket_create_messages(self):
        try:
            if not hasattr(self.bot, "db") or self.bot.db is None:
                return
            logger.info("Restoring ticket create messages from database...")
            rows = await core.list_ticket_create_messages(self.bot.db)
            for row in rows:
                channel_id, message_id, payload = row
                if message_id is None:
                    continue
                message_id = int(message_id)
                if message_id in self._registered_create_views:
                    continue

                mode, categories = core.parse_categories_payload(payload or "")
                if not categories:
                    continue

                if mode == "button" and len(categories) == 1:
                    view = TicketCreateButtonView(
                        category_name=categories[0],
                        custom_id=f"ticket_create_button_{message_id}",
                    )
                else:
                    view = TicketCreateSelectView(
                        categories=categories,
                        custom_id=f"ticket_create_select_{message_id}",
                    )

                self.bot.add_view(view, message_id=message_id)
                self._registered_create_views.add(message_id)
        except Exception as e:
            logger.exception("Error while restoring ticket create views", exc_info=e)

    async def _restore_ticket_views(self):
        try:
            if not hasattr(self.bot, "db") or self.bot.db is None:
                return
            logger.info("Restoring ticket views from database...")
            rows = await core.list_tickets(self.bot.db)
            for row in rows:
                channel_id, status, type_id, user_id, title = row
                channel_id = int(channel_id)
                if channel_id in self._registered_ticket_views:
                    continue
                status_value = int(status) if status is not None else 1
                view = TicketOpenView(channel_id=channel_id) if status_value == 1 else TicketClosedView(channel_id=channel_id)
                self.bot.add_view(view)
                self._registered_ticket_views.add(channel_id)
        except Exception as e:
            logger.exception("Error while restoring ticket views", exc_info=e)

    async def _handle_ticket_title_submit(self, interaction: discord.Interaction, category_name: str, title: str):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        category = core.get_category_from_config(self.bot, category_name)
        if not category:
            await interaction.response.send_message("Nie znaleziono takiej kategorii ticketów.", ephemeral=True)
            return

        type_id = await core.get_ticket_type_id(self.bot.db, category.type_name)
        if type_id is None:
            logger.error(f"Ticket type '{category.type_name}' not found in database")
            await interaction.response.send_message("Wystąpił błąd konfiguracji typów ticketów.", ephemeral=True)
            return

        try:
            channel = await core.create_ticket_channel(
                guild=interaction.guild,
                user=interaction.user,
                title=title,
                category_id=category.category_id,
            )
        except Exception as e:
            logger.exception("Error while creating ticket channel", exc_info=e)
            await interaction.response.send_message("Nie udało się utworzyć kanału ticketu.", ephemeral=True)
            return

        try:
            await core.create_ticket_record(
                self.bot.db,
                channel_id=channel.id,
                user_id=interaction.user.id,
                type_id=type_id,
                title=title,
            )
        except Exception as e:
            logger.exception("Error while creating ticket record", exc_info=e)
            await interaction.response.send_message("Nie udało się zapisać ticketu w bazie.", ephemeral=True)
            return

        handler = core.get_type_handler(category.type_name)
        view = TicketOpenView(channel_id=channel.id)
        await channel.send(content=handler.get_open_message(interaction.user, title), view=view)

        if channel.id not in self._registered_ticket_views:
            self.bot.add_view(view)
            self._registered_ticket_views.add(channel.id)

        await interaction.response.send_message(
            f"Ticket został utworzony: {channel.mention}",
            ephemeral=True,
        )

        logger.info(
            f"User {interaction.user} ({interaction.user.id}) created ticket in channel {channel.id} (type {category.type_name})"
        )

    async def _handle_ticket_close(self, interaction: discord.Interaction, channel_id: int):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        ticket_row = await core.get_ticket_by_channel(self.bot.db, channel_id)
        if not ticket_row:
            await interaction.followup.send("Nie znaleziono ticketu.", ephemeral=True)
            return

        status = int(ticket_row[4])
        if status == 0:
            await interaction.followup.send("Ten ticket jest już zamknięty.", ephemeral=True)
            return

        await core.update_ticket_status(self.bot.db, channel_id, 0)

        try:
            await core.set_ticket_user_send_permission(
                interaction.channel,
                user_id=int(ticket_row[2]) if ticket_row[2] is not None else 0,
                can_send=False,
            )
        except Exception as e:
            logger.exception("Error while updating ticket permissions on close", exc_info=e)

        view = TicketClosedView(channel_id=channel_id)
        await interaction.message.edit(view=view)

        type_name = await core.get_ticket_type_name(self.bot.db, int(ticket_row[5])) if ticket_row[5] is not None else None
        handler = core.get_type_handler(type_name or "custom")
        await interaction.channel.send(handler.get_closed_message())

        await interaction.followup.send("Ticket został zamknięty.", ephemeral=True)

        logger.info(f"Ticket in channel {channel_id} closed by {interaction.user} ({interaction.user.id})")

    async def _handle_ticket_reopen(self, interaction: discord.Interaction, channel_id: int):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        ticket_row = await core.get_ticket_by_channel(self.bot.db, channel_id)
        if not ticket_row:
            await interaction.followup.send("Nie znaleziono ticketu.", ephemeral=True)
            return

        status = int(ticket_row[4])
        if status == 1:
            await interaction.followup.send("Ten ticket jest już otwarty.", ephemeral=True)
            return

        await core.update_ticket_status(self.bot.db, channel_id, 1)

        try:
            await core.set_ticket_user_send_permission(
                interaction.channel,
                user_id=int(ticket_row[2]) if ticket_row[2] is not None else 0,
                can_send=True,
            )
        except Exception as e:
            logger.exception("Error while updating ticket permissions on reopen", exc_info=e)

        view = TicketOpenView(channel_id=channel_id)
        await interaction.message.edit(view=view)

        type_name = await core.get_ticket_type_name(self.bot.db, int(ticket_row[5])) if ticket_row[5] is not None else None
        handler = core.get_type_handler(type_name or "custom")
        await interaction.channel.send(handler.get_reopened_message())

        await interaction.followup.send("Ticket został ponownie otwarty.", ephemeral=True)

        logger.info(f"Ticket in channel {channel_id} reopened by {interaction.user} ({interaction.user.id})")

    async def _handle_ticket_transcript(self, interaction: discord.Interaction, channel_id: int):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień do generowania transcriptu.", ephemeral=True)
            return

        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        log_channel_id = self.bot.channels.get("log_channel_id") if hasattr(self.bot, "channels") else None
        if not log_channel_id:
            await interaction.followup.send("Nie ustawiono kanału logów w konfiguracji.", ephemeral=True)
            return

        log_channel = interaction.guild.get_channel(int(log_channel_id))
        if not log_channel:
            await interaction.followup.send("Nie znaleziono kanału logów.", ephemeral=True)
            return

        html_content = await self._generate_transcript_html(interaction.channel)
        filename = f"transcript_{interaction.channel.id}.html"
        file_obj = discord.File(fp=io.BytesIO(html_content.encode("utf-8")), filename=filename)

        await log_channel.send(
            content=f"Transkrypt ticketu {interaction.channel.name} (ID: {interaction.channel.id}) wygenerowany przez {interaction.user.mention} (ID: {interaction.user.id})",
            file=file_obj,
        )

        await interaction.followup.send("Transcript został wysłany na kanał logów.", ephemeral=True)

        logger.info(f"Transcript generated for channel {channel_id} by {interaction.user} ({interaction.user.id})")

    async def _handle_ticket_delete(self, interaction: discord.Interaction, channel_id: int):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień do usuwania ticketów.", ephemeral=True)
            return

        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            await core.delete_ticket_record(self.bot.db, channel_id)
        except Exception as e:
            logger.exception("Error while deleting ticket record", exc_info=e)

        await interaction.followup.send("Ticket zostanie usunięty.", ephemeral=True)

        logger.info(f"Ticket in channel {channel_id} deleted by {interaction.user} ({interaction.user.id})")
        await interaction.channel.delete(reason="Ticket deleted")

    async def _generate_transcript_html(self, channel: discord.TextChannel) -> str:
        lines = []
        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='pl'>")
        lines.append("<head><meta charset='UTF-8'><title>Transcript</title>")
        lines.append("<style>body{font-family:Arial, sans-serif;} .msg{margin:8px 0;} .meta{color:#666;font-size:12px;}</style>")
        lines.append("</head><body>")
        lines.append(f"<h2>Transcript kanału {html.escape(channel.name)}</h2>")

        async for message in channel.history(limit=None, oldest_first=True):
            author = html.escape(message.author.display_name)
            created = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = html.escape(message.content) if message.content else ""
            attachments = ""
            if message.attachments:
                links = " ".join(f"<a href='{att.url}'>{html.escape(att.filename)}</a>" for att in message.attachments)
                attachments = f"<div>Załączniki: {links}</div>"
            lines.append("<div class='msg'>")
            lines.append(f"<div class='meta'>{created} | {author}</div>")
            if content:
                lines.append(f"<div>{content}</div>")
            if attachments:
                lines.append(attachments)
            lines.append("</div>")

        lines.append("</body></html>")
        return "\n".join(lines)
    
    
    # Listen for deleted messages to clean up ticket create messages
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return
        if not hasattr(self.bot, "db") or self.bot.db is None:
            return

        # Check if this message is a registered ticket create message
        if message.id not in self._registered_create_views:
            return

        try:
            await core.delete_ticket_create_message(self.bot.db, message.id)
        except Exception as e:
            logger.exception("Error while deleting ticket create message record", exc_info=e)

        self._registered_create_views.discard(message.id)




    # =============== Ticket Messages =================
    # /ticket_wiadomosc_przycisk
    @app_commands.command(
        name="ticket_wiadomosc_przycisk",
        description="Utwórz wiadomość do tworzenia ticketów (przycisk).",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(kategoria="Nazwa kategorii ticketów")
    async def ticket_wiadomosc_przycisk(self, interaction: discord.Interaction, kategoria: str):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return
        if not self._is_ticket_admin(interaction.user):
            await interaction.response.send_message("Nie masz uprawnień do tej komendy.", ephemeral=True)
            return

        category = core.get_category_from_config(self.bot, kategoria)
        if not category:
            await interaction.response.send_message("Nie znaleziono takiej kategorii ticketów.", ephemeral=True)
            return

        content = f"Kliknij przycisk, aby utworzyć ticket w kategorii **{category.name}**."
        await interaction.response.send_message(content)
        message = await interaction.original_response()

        view = TicketCreateButtonView(
            category_name=category.name,
            custom_id=f"ticket_create_button_{message.id}",
        )
        await message.edit(view=view)

        payload = core.serialize_categories_payload("button", [category.name])
        await core.save_ticket_create_message(self.bot.db, interaction.channel.id, message.id, payload)

        if message.id not in self._registered_create_views:
            self.bot.add_view(view, message_id=message.id)
            self._registered_create_views.add(message.id)

        logger.info(f"Ticket create button message created by {interaction.user} ({interaction.user.id})")

    # /ticket_wiadomosc_select
    @app_commands.command(
        name="ticket_wiadomosc_select",
        description="Utwórz wiadomość do tworzenia ticketów (lista wyboru).",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(kategorie="Lista kategorii oddzielona przecinkami")
    async def ticket_wiadomosc_select(self, interaction: discord.Interaction, kategorie: str):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            await interaction.response.send_message("Brak dostępu do bazy danych.", ephemeral=True)
            return
        if not self._is_ticket_admin(interaction.user):
            await interaction.response.send_message("Nie masz uprawnień do tej komendy.", ephemeral=True)
            return

        raw = [c.strip() for c in kategorie.split(",") if c.strip()]
        if not raw:
            await interaction.response.send_message("Podaj przynajmniej jedną kategorię.", ephemeral=True)
            return

        categories = []
        for name in raw:
            category = core.get_category_from_config(self.bot, name)
            if not category:
                await interaction.response.send_message(
                    f"Nie znaleziono kategorii: {name}",
                    ephemeral=True,
                )
                return
            categories.append(category.name)

        content = "Wybierz kategorię, aby utworzyć ticket."
        await interaction.response.send_message(content)
        message = await interaction.original_response()

        view = TicketCreateSelectView(
            categories=categories,
            custom_id=f"ticket_create_select_{message.id}",
        )
        await message.edit(view=view)

        payload = core.serialize_categories_payload("select", categories)
        await core.save_ticket_create_message(self.bot.db, interaction.channel.id, message.id, payload)

        if message.id not in self._registered_create_views:
            self.bot.add_view(view, message_id=message.id)
            self._registered_create_views.add(message.id)

        logger.info(f"Ticket create select message created by {interaction.user} ({interaction.user.id})")
        
        

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))