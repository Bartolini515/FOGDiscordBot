import json
import logging
import re
from dataclasses import dataclass
from typing import Any
import discord

from db.models import Tickets, TicketTypes, TicketCreateMessages

from ticket.types.mission import MissionTicketType
from ticket.types.proposal import ProposalTicketType
from ticket.types.custom import CustomTicketType


logger = logging.getLogger("fogbot")


@dataclass
class TicketCategory:
    name: str
    description: str
    type_name: str
    category_id: int


TYPE_HANDLERS = {
    "mission": MissionTicketType(),
    "proposal": ProposalTicketType(),
    "custom": CustomTicketType(),
}


def normalize_channel_name(title: str) -> str:
    base = title.strip().lower()
    base = base.replace(" ", "-")
    base = re.sub(r"[^a-z0-9\-]", "", base)
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "ticket"
    return base[:90]


def get_category_from_config(bot: discord.Client, category_name: str) -> TicketCategory | None:
    categories = getattr(bot, "ticket_system", {}).get("ticket_categories", [])
    for category in categories:
        if str(category.get("name", "")).casefold() == category_name.casefold():
            return TicketCategory(
                name=category.get("name", category_name),
                description=category.get("description", ""),
                type_name=category.get("type", "custom"),
                category_id=int(category.get("category_id", 0) or 0),
            )
    return None


def get_type_handler(type_name: str):
    return TYPE_HANDLERS.get(type_name, TYPE_HANDLERS["custom"])


def serialize_categories_payload(mode: str, categories: list[str]) -> str:
    return json.dumps({"mode": mode, "categories": categories}, ensure_ascii=False)


def parse_categories_payload(payload: str) -> tuple[str, list[str]]:
    try:
        data = json.loads(payload)
        mode = data.get("mode", "select")
        categories = data.get("categories", [])
        if isinstance(categories, str):
            categories = [categories]
        return mode, [str(c) for c in categories]
    except Exception:
        return "select", []


async def get_ticket_type_id(db, type_name: str) -> int | None:
    """Gets ticket type id by name

    Args:
        db (_type_): Database to be used
        type_name (str): Ticket type name

    Returns:
        fetchone: id
    """
    return await TicketTypes.get_id_by_name(db, type_name)


async def get_ticket_type_name(db, type_id: int) -> str | None:
    """Gets ticket type name by id

    Args:
        db (_type_): Database to be used
        type_id (int): Ticket type id

    Returns:
        fetchone: name
    """
    return await TicketTypes.get_name_by_id(db, type_id)


async def create_ticket_record(db, channel_id: int, user_id: int, type_id: int, title: str):
    """Creates a new ticket

    Args:
        db (_type_): Database to be used
        channel_id (int): Discord channel id
        user_id (int): Discord user id of the ticket creator.
        type_id (int): Ticket type id
        title (str): Title of the ticket
    """
    await Tickets.create(db, channel_id, user_id, type_id, title)


async def update_ticket_status(db, channel_id: int, status: int):
    """Updates ticket status by channel id

    Args:
        db (_type_): Database to be used
        channel_id (int): Discord channel id
        status (int): 1 for open, 0 for closed
    """
    await Tickets.update_status(db, channel_id, status)


async def delete_ticket_record(db, channel_id: int):
    """Deletes ticket by channel id

    Args:
        db (_type_): Database to be used
        channel_id (int): Discord channel id
    """
    await Tickets.delete_by_channel(db, channel_id)


async def get_ticket_by_channel(db, channel_id: int) -> tuple[Any, ...] | None:
    """Gets ticket by channel id

    Args:
        db (_type_): Database to be used
        channel_id (int): Discord channel id

    Returns:
        fetchone: id, channel_id, user_id, created_at, status, type_id, title
    """
    return await Tickets.get_by_channel(db, channel_id)


async def list_tickets(db) -> list[tuple[Any, ...]]:
    """Lists all tickets (basic fields)

    Args:
        db (_type_): Database to be used

    Returns:
        fetchall: channel_id, status, type_id, user_id, title
    """
    return await Tickets.list_basic(db)


async def save_ticket_create_message(db, channel_id: int, message_id: int, categories_payload: str):
    """Creates or updates ticket create message

    Args:
        db (_type_): Database to be used
        channel_id (int): Discord channel id
        message_id (int): Discord message id
        categories_payload (str): JSON payload with categories
    """
    await TicketCreateMessages.save(db, channel_id, message_id, categories_payload)


async def list_ticket_create_messages(db) -> list[tuple[Any, ...]]:
    """Lists all ticket create messages

    Args:
        db (_type_): Database to be used

    Returns:
        fetchall: channel_id, message_id, categories
    """
    return await TicketCreateMessages.list(db)

async def delete_ticket_create_message(db, message_id: int):
    """Deletes ticket create message by message id

    Args:
        db (_type_): Database to be used
        message_id (int): Discord message id
    """
    await TicketCreateMessages.delete_by_message_id(db, message_id)


async def create_ticket_channel(
    guild: discord.Guild,
    user: discord.Member,
    title: str,
    category_id: int,
) -> discord.TextChannel:
    channel_name = normalize_channel_name(title)

    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }

    me = guild.me
    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_permissions=True,
        )

    admin_roles = [role for role in guild.roles if role.permissions.administrator]
    for role in admin_roles:
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        )

    category = guild.get_channel(category_id) if category_id else None

    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason="Ticket created",
    )
    return channel


async def set_ticket_user_send_permission(
    channel: discord.TextChannel,
    user_id: int,
    can_send: bool,
):
    member = channel.guild.get_member(user_id)
    if not member:
        return
    overwrite = channel.overwrites_for(member)
    overwrite.send_messages = can_send
    overwrite.view_channel = True
    await channel.set_permissions(member, overwrite=overwrite)

